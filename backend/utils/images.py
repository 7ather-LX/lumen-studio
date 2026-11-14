from __future__ import annotations

import base64
import io
import math
import mimetypes
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, PngImagePlugin

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000

DATA_URL_RE = re.compile(r"^data:(image/(?:png|jpeg|jpg|webp|bmp));base64,([A-Za-z0-9+/=\s]+)$", re.I)


class ImageValidationError(ValueError):
    pass


def decode_data_url(data_url: str) -> Image.Image:
    match = DATA_URL_RE.match(data_url or "")
    if not match:
        raise ImageValidationError("参考图格式无效，请使用 PNG、JPG、WEBP 或 BMP")
    encoded = re.sub(r"\s+", "", match.group(2))
    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ImageValidationError("参考图数据损坏") from exc
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ImageValidationError("参考图不能超过 25 MB")
    return open_image_bytes(raw)


def open_image_bytes(raw: bytes) -> Image.Image:
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
        image = ImageOps.exif_transpose(image)
    except Exception as exc:
        raise ImageValidationError("无法读取图片，文件可能已损坏") from exc
    if image.width < 64 or image.height < 64:
        raise ImageValidationError("参考图至少需要 64×64 像素")
    if image.width * image.height > MAX_IMAGE_PIXELS:
        raise ImageValidationError("参考图像素过大")
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    return image


def flatten_for_model(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image
    background = Image.new("RGB", image.size, (18, 18, 22))
    background.paste(image, mask=image.getchannel("A"))
    return background


def save_png(image: Image.Image, path: Path, metadata: dict[str, str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    info = PngImagePlugin.PngInfo()
    for key, value in (metadata or {}).items():
        if value:
            info.add_text(str(key)[:79], str(value)[:8000])
    save_image = image.convert("RGBA") if image.mode == "RGBA" else image.convert("RGB")
    save_image.save(path, format="PNG", pnginfo=info, optimize=False, compress_level=6)


def save_jpeg(image: Image.Image, path: Path, quality: int = 94) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(path, format="JPEG", quality=quality, optimize=True)


def save_thumbnail(image: Image.Image, path: Path, max_edge: int = 480) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    thumb = image.copy()
    thumb.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    if thumb.mode == "RGBA":
        thumb.save(path, format="WEBP", quality=86, method=4)
    else:
        thumb.convert("RGB").save(path, format="WEBP", quality=86, method=4)


def image_to_png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def image_from_bytes(raw: bytes) -> Image.Image:
    return open_image_bytes(raw)


def guess_mime(path: Path) -> str:
    return mimetypes.guess_type(str(path))[0] or "image/png"


def fit_within(image: Image.Image, max_edge: int) -> Image.Image:
    if max(image.size) <= max_edge:
        return image
    copy = image.copy()
    copy.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    return copy


def average_hash(image: Image.Image, size: int = 8) -> str:
    """Difference hash (dHash), returned as 16 hex characters."""
    import numpy as np

    gray = image.convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
    pixels = np.asarray(gray, dtype=np.uint8)
    bits = 0
    index = 0
    for row in range(size):
        for col in range(size):
            if pixels[row, col] > pixels[row, col + 1]:
                bits |= 1 << index
            index += 1
    return f"{bits:016x}"


def hamming_hex(a: str, b: str) -> int:
    try:
        return (int(a, 16) ^ int(b, 16)).bit_count()
    except (TypeError, ValueError):
        return 64


def image_dimensions_note(width: int, height: int) -> str:
    ratio = width / height
    common = {1.0: "1:1", 4 / 3: "4:3", 3 / 4: "3:4", 3 / 2: "3:2", 2 / 3: "2:3", 16 / 9: "16:9", 9 / 16: "9:16"}
    for value, label in common.items():
        if abs(value - ratio) < 0.02:
            return label
    return f"{ratio:.2f}:1"


def estimated_bytes(width: int, height: int) -> int:
    return int(width * height * 1.8)


def megapixels(width: int, height: int) -> float:
    return round(width * height / 1_000_000, 2)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalized(value: float, low: float, high: float) -> float:
    if math.isclose(high, low):
        return 0.0
    return clamp((value - low) / (high - low), 0.0, 1.0)


def safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def cel_shading_enhance(image: Image.Image) -> Image.Image:
    """A conservative posterize + ink-edge pass for cel-shaded illustration.

    This is intentionally optional: it can flatten gradients and is not a
    replacement for an anime-specific checkpoint.
    """

    from PIL import ImageEnhance, ImageFilter, ImageOps

    rgb = image.convert("RGB")
    flat = ImageOps.posterize(rgb, 5)
    edges = (
        rgb.convert("L")
        .filter(ImageFilter.GaussianBlur(0.7))
        .filter(ImageFilter.FIND_EDGES)
        .point(lambda value: int(min(150, value * 1.4)) if value > 46 else 0)
    )
    ink = Image.new("RGB", rgb.size, (30, 26, 34))
    mask = edges.filter(ImageFilter.GaussianBlur(0.45)).point(lambda value: int(value * 0.42))
    composited = Image.composite(ink, flat, mask)
    return ImageEnhance.Color(composited).enhance(1.06)
