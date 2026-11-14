from __future__ import annotations

import math
from typing import Any

import numpy as np
from PIL import Image

from backend.utils.images import average_hash, fit_within, normalized

ANALYSIS_VERSION = 1


def _entropy(channel: np.ndarray) -> float:
    histogram, _ = np.histogram(channel, bins=64, range=(0.0, 1.0))
    probabilities = histogram.astype(np.float64)
    total = probabilities.sum()
    if total <= 0:
        return 0.0
    probabilities /= total
    probabilities = probabilities[probabilities > 0]
    return float(-(probabilities * np.log2(probabilities)).sum() / 6.0)


def _colorfulness(rgb: np.ndarray) -> float:
    red, green, blue = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    rg = red - green
    yb = 0.5 * (red + green) - blue
    std_root = math.sqrt(float(rg.std()) ** 2 + float(yb.std()) ** 2)
    mean_root = math.sqrt(float(rg.mean()) ** 2 + float(yb.mean()) ** 2)
    return float(std_root + 0.3 * mean_root)


def analyze_image(image: Image.Image) -> dict[str, Any]:
    """Compute fast, deterministic technical and composition metrics.

    This is deliberately a transparent image-analysis model rather than a
    claimed aesthetic oracle. User ratings are combined with these features by
    the preference learner.
    """

    sample = fit_within(image.convert("RGB"), 512)
    rgb = np.asarray(sample, dtype=np.float32) / 255.0
    luminance = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    height, width = luminance.shape

    padded = np.pad(luminance, 1, mode="edge")
    laplacian = (
        -4.0 * luminance
        + padded[0:height, 1 : width + 1]
        + padded[2 : height + 2, 1 : width + 1]
        + padded[1 : height + 1, 0:width]
        + padded[1 : height + 1, 2 : width + 2]
    )
    sharpness_raw = float(laplacian.var())

    brightness = float(luminance.mean())
    contrast = float(luminance.std())
    hsv = np.asarray(sample.convert("HSV"), dtype=np.float32) / 255.0
    saturation = float(hsv[..., 1].mean())
    colorfulness = _colorfulness(rgb)
    entropy = _entropy(luminance)

    gy, gx = np.gradient(luminance)
    magnitude = np.sqrt(gx * gx + gy * gy)
    total_edges = float(magnitude.sum()) + 1e-6
    ys, xs = np.mgrid[0:height, 0:width]
    centroid_x = float((magnitude * xs).sum() / total_edges) / max(1, width - 1)
    centroid_y = float((magnitude * ys).sum() / total_edges) / max(1, height - 1)
    center_distance = math.sqrt((centroid_x - 0.5) ** 2 + (centroid_y - 0.5) ** 2)
    left = float(luminance[:, : width // 2].mean())
    right = float(luminance[:, width - width // 2 :].mean())
    top = float(luminance[: height // 2, :].mean())
    bottom = float(luminance[height - height // 2 :, :].mean())
    balance = 1.0 - min(1.0, (abs(left - right) + abs(top - bottom)) / 0.65)

    sharpness = 100.0 * (1.0 - math.exp(-sharpness_raw / 420.0))
    exposure = 100.0 * max(0.0, 1.0 - abs(brightness - 0.48) / 0.48)
    contrast_score = 100.0 * normalized(contrast, 0.03, 0.28)
    saturation_score = 100.0 * normalized(saturation, 0.02, 0.62)
    color_score = 100.0 * normalized(colorfulness, 2.0, 80.0)
    entropy_score = 100.0 * normalized(entropy, 0.35, 0.97)
    composition = 100.0 * max(0.0, min(1.0, 0.68 * (1.0 - min(1.0, center_distance / 0.62)) + 0.32 * balance))

    technical = (
        sharpness * 0.30
        + exposure * 0.16
        + contrast_score * 0.17
        + color_score * 0.13
        + entropy_score * 0.10
        + composition * 0.14
    )

    tags: list[str] = []
    if sharpness > 62:
        tags.append("细节清晰")
    if sharpness < 28:
        tags.append("画面偏软")
    if brightness < 0.28:
        tags.append("暗调")
    elif brightness > 0.76:
        tags.append("高亮")
    if contrast_score < 28:
        tags.append("低对比")
    if color_score > 55:
        tags.append("色彩丰富")
    elif color_score < 14:
        tags.append("低饱和")
    if composition > 74:
        tags.append("构图平衡")
    if saturation > 0.55:
        tags.append("高饱和")

    palette_image = sample.copy()
    palette_image.thumbnail((96, 96), Image.Resampling.NEAREST)
    quantized = palette_image.quantize(colors=6, method=Image.Quantize.MEDIANCUT)
    palette = []
    palette_pixels = max(1, palette_image.width * palette_image.height)
    for count, index in sorted(quantized.getcolors() or [], reverse=True)[:6]:
        red, green, blue = quantized.getpalette()[index * 3 : index * 3 + 3]
        palette.append({"hex": f"#{red:02x}{green:02x}{blue:02x}", "share": round(count / palette_pixels, 3)})

    return {
        "version": ANALYSIS_VERSION,
        "technical_score": round(technical, 1),
        "sharpness": round(sharpness, 1),
        "exposure": round(exposure, 1),
        "contrast": round(contrast_score, 1),
        "saturation": round(saturation_score, 1),
        "colorfulness": round(color_score, 1),
        "entropy": round(entropy_score, 1),
        "composition": round(composition, 1),
        "brightness": round(brightness, 3),
        "raw_sharpness": round(sharpness_raw, 1),
        "tags": tags,
        "palette": palette,
        "phash": average_hash(sample, 8),
        "width": image.width,
        "height": image.height,
    }


def duplicate_distance(a: dict[str, Any], b: dict[str, Any]) -> int:
    from backend.utils.images import hamming_hex

    return hamming_hex(str(a.get("phash", "")), str(b.get("phash", "")))
