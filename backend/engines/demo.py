from __future__ import annotations

import colorsys
import hashlib
import math
import random
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from backend.engines.base import BaseEngine, CancelCheck, GeneratedImage, GenerationContext, ProgressCallback
from backend.security import SecretStore


def _seed_from(text: str) -> int:
    return int.from_bytes(hashlib.blake2b(text.encode("utf-8"), digest_size=4).digest(), "little")


def _palette(prompt: str) -> list[tuple[int, int, int]]:
    digest = hashlib.blake2b(prompt.encode("utf-8"), digest_size=8).digest()
    base_hue = digest[0] / 255.0
    colors = []
    for index in range(4):
        hue = (base_hue + index * 0.19 + digest[index + 1] / 900.0) % 1.0
        saturation = 0.45 + digest[index + 2] / 510.0
        value = 0.45 + digest[index + 3] / 620.0
        red, green, blue = colorsys.hsv_to_rgb(hue, saturation, value)
        colors.append((int(red * 255), int(green * 255), int(blue * 255)))
    return colors


def _render(prompt: str, width: int, height: int, seed: int) -> Image.Image:
    """A deterministic generative composition used for offline previews.

    It is intentionally *not* presented as a diffusion result: it combines
    seeded light fields, contour lines, grain and a vignette to exercise the
    complete generation/preview/feedback pipeline without any model download.
    """
    rng = random.Random(seed)
    palette = _palette(prompt)
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    nx = xx / max(1, width - 1)
    ny = yy / max(1, height - 1)

    # Diagonal background gradient with a darker floor.
    t = np.clip(0.68 * ny + 0.32 * nx, 0.0, 1.0)[..., None]
    top = np.array(palette[0], dtype=np.float32) * 0.30
    bottom = np.array(palette[1], dtype=np.float32) * 0.10
    array = top * (1.0 - t) + bottom * t

    # Large light fields. Screen blending keeps highlights luminous without
    # washing the whole frame out to grey.
    for index in range(7):
        cx = rng.uniform(-0.2, 1.2)
        cy = rng.uniform(-0.1, 1.1)
        radius = rng.uniform(0.18, 0.58)
        color = np.array(palette[(index + 1) % len(palette)], dtype=np.float32) / 255.0
        distance = ((nx - cx) ** 2 + (ny - cy) ** 2) / (radius * radius)
        alpha = np.clip(1.0 - distance, 0.0, 1.0) ** 3.0
        alpha *= rng.uniform(0.12, 0.38)
        glow = color[None, None, :] * alpha[..., None]
        array = 1.0 - (1.0 - array / 255.0) * (1.0 - glow)
        array *= 255.0

    # Interfering wave field adds fine, atmospheric structure.
    phase = rng.uniform(0, math.tau)
    wave = np.sin(nx * rng.uniform(7, 13) + phase + np.sin(ny * rng.uniform(4, 8) + phase) * 1.8)
    wave += np.sin(ny * rng.uniform(9, 17) - phase * 0.7) * 0.55
    wave = np.clip((wave + 1.0) / 2.0, 0.0, 1.0) ** 5
    wave_color = np.array(palette[2], dtype=np.float32)
    array = np.clip(array + wave[..., None] * wave_color[None, None, :] * 0.26, 0, 255)

    # Radial falloff preserves deep blacks at the edges.
    radial = np.sqrt((nx - 0.5) ** 2 + (ny - 0.5) ** 2)
    falloff = np.clip(1.0 - 2.1 * np.clip(radial - 0.16, 0.0, 1.0) ** 1.7, 0.16, 1.0)
    array *= falloff[..., None]

    image = Image.fromarray(array.astype(np.uint8), "RGB")

    # Contour topography.
    lines = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(lines)
    step = max(14, int(min(width, height) / 32))
    for index in range(-height, height, step):
        points = []
        for x in range(-8, width + 8, max(4, width // 180)):
            y = index + math.sin(x / max(34, width / 6.5) + phase + index / 210) * (7 + abs(index) % 17)
            points.append((x, y))
        alpha = 26 + (abs(index) % 3) * 10
        draw.line(points, fill=(*palette[3], alpha), width=1)

    # Luminous ring and small satellite dots.
    radius = min(width, height) * rng.uniform(0.16, 0.24)
    cx = width * rng.uniform(0.42, 0.62)
    cy = height * rng.uniform(0.38, 0.58)
    for offset, alpha, line_width in ((0, 230, 2), (6, 80, 3), (15, 30, 5)):
        draw.ellipse(
            (cx - radius - offset, cy - radius - offset, cx + radius + offset, cy + radius + offset),
            outline=(*palette[1], alpha),
            width=max(1, int(min(width, height) / 700) + line_width),
        )
    draw.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill=(245, 251, 232, 245))
    for _ in range(32):
        sx, sy = rng.uniform(0, width), rng.uniform(0, height)
        size = rng.uniform(0.6, 2.4)
        draw.ellipse((sx, sy, sx + size, sy + size), fill=(*palette[0], rng.randint(40, 150)))
    image = Image.alpha_composite(image.convert("RGBA"), lines).convert("RGB")

    # Grain and vignette keep the preview from looking like flat vector art.
    grain = np.random.default_rng(seed).normal(0, 5.5, (height, width, 1)).repeat(3, axis=2)
    image = Image.fromarray(np.clip(np.asarray(image, dtype=np.float32) + grain, 0, 255).astype(np.uint8), "RGB")

    vignette = Image.new("L", (width, height), 0)
    vdraw = ImageDraw.Draw(vignette)
    vdraw.ellipse((-width * 0.22, -height * 0.22, width * 1.22, height * 1.22), fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(min(width, height) / 7))
    dark = Image.new("RGB", (width, height), (4, 5, 8))
    image = Image.composite(image, dark, vignette)
    return image.filter(ImageFilter.UnsharpMask(radius=1.2, percent=80, threshold=3))


class DemoEngine(BaseEngine):
    kind = "demo"
    display_name = "离线示例引擎"

    def availability(self, provider: dict[str, Any], secrets: SecretStore):
        from backend.engines.base import Availability

        return Availability(
            available=True,
            reason="无需模型，完全离线，用于预览界面与测试工作流",
            detail="生成的是算法抽象画，不是扩散模型作品。安装本地引擎后即可使用真实 AI 生成。",
            version="1.0",
        )

    def generate(
        self,
        context: GenerationContext,
        provider: dict[str, Any],
        secrets: SecretStore,
        progress: ProgressCallback,
        cancelled: CancelCheck,
    ) -> list[GeneratedImage]:
        results: list[GeneratedImage] = []
        for index in range(context.batch_size):
            self.check_cancel(cancelled)
            progress(index / max(1, context.batch_size) * 0.8 + 0.05, f"绘制示例画面 {index + 1}/{context.batch_size}")
            image_seed = (context.seed + index) & 0xFFFFFFFF
            image = _render(context.prompt, context.width, context.height, image_seed)
            if context.init_image is not None and context.mode == "img2img":
                base = context.init_image.convert("RGB").resize((context.width, context.height), Image.Resampling.LANCZOS)
                mix = max(0.15, min(0.9, context.strength))
                image = Image.blend(base, image, mix)
                image = ImageOps.autocontrast(image, cutoff=1)
            results.append(
                GeneratedImage(
                    image=image,
                    seed=image_seed,
                    meta={
                        "demo": True,
                        "engine_note": "算法示例图，非扩散模型输出",
                    },
                )
            )
            progress((index + 1) / context.batch_size * 0.85 + 0.05, f"完成 {index + 1}/{context.batch_size}")
        return results
