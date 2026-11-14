from __future__ import annotations

import math
from dataclasses import dataclass

ASPECT_PRESETS: list[dict[str, object]] = [
    {"id": "1:1", "label": "方形 1:1", "ratio": 1.0, "hint": "头像 / 图标"},
    {"id": "4:3", "label": "经典 4:3", "ratio": 4 / 3, "hint": "摄影 / 插画"},
    {"id": "3:4", "label": "竖版 3:4", "ratio": 3 / 4, "hint": "人像 / 海报"},
    {"id": "3:2", "label": "相机 3:2", "ratio": 3 / 2, "hint": "风景 / 产品"},
    {"id": "2:3", "label": "竖版 2:3", "ratio": 2 / 3, "hint": "人物 / 封面"},
    {"id": "16:9", "label": "宽屏 16:9", "ratio": 16 / 9, "hint": "壁纸 / 视频封面"},
    {"id": "9:16", "label": "竖屏 9:16", "ratio": 9 / 16, "hint": "短视频 / 手机壁纸"},
    {"id": "21:9", "label": "超宽 21:9", "ratio": 21 / 9, "hint": "电影画幅"},
]


@dataclass(frozen=True)
class ResolvedSize:
    width: int
    height: int
    note: str = ""
    ratio: float = 1.0


def parse_aspect(value: str | None) -> tuple[float, str]:
    if not value:
        return 1.0, "1:1"
    cleaned = value.strip().lower().replace("：", ":").replace("x", ":").replace("/", ":")
    if cleaned in ("square", "方图"):
        return 1.0, "1:1"
    if ":" in cleaned:
        left, _, right = cleaned.partition(":")
        try:
            width, height = float(left), float(right)
            if width > 0 and height > 0:
                return width / height, f"{int(width)}:{int(height)}"
        except ValueError:
            pass
    for preset in ASPECT_PRESETS:
        if preset["id"] == cleaned:
            return float(preset["ratio"]), str(preset["id"])
    return 1.0, "1:1"


def snap(value: float, multiple: int = 16) -> int:
    return max(multiple, int(round(value / multiple)) * multiple)


def resolve_dimensions(
    aspect_ratio: str = "1:1",
    long_edge: int = 1024,
    width: int | None = None,
    height: int | None = None,
    max_pixels: int = 4_194_304,
) -> ResolvedSize:
    """Resolve a requested canvas, preserving ratio and staying 16px aligned."""

    notes: list[str] = []
    if width and height:
        w = snap(width)
        h = snap(height)
        ratio = w / h
        notes.append("使用自定义尺寸")
    else:
        ratio, canonical = parse_aspect(aspect_ratio)
        edge = int(max(256, min(2048, long_edge)))
        if ratio >= 1:
            w, h = edge, edge / ratio
        else:
            w, h = edge * ratio, edge
        w, h = snap(w), snap(h)
        if canonical not in ("1:1",):
            notes.append(f"{canonical} 画幅")

    max_w = int(math.sqrt(max_pixels * (w / h)))
    max_h = int(max_pixels / max_w)
    if w * h > max_pixels:
        scale = math.sqrt(max_pixels / (w * h))
        w, h = snap(w * scale), snap(h * scale)
        notes.append("已按像素上限缩放")

    w = max(256, min(2048, w))
    h = max(256, min(2048, h))
    # Keep the requested aspect after clamping while remaining 16px aligned.
    if not (width and height):
        if ratio >= 1:
            h = snap(w / ratio)
        else:
            w = snap(h * ratio)
        w, h = max(256, w), max(256, h)

    if w * h > max_pixels:
        w, h = snap(w * 0.95), snap(h * 0.95)
        notes.append("已按像素上限微调")

    return ResolvedSize(width=w, height=h, note=" · ".join(notes), ratio=w / h)


def nearest_aspect(width: int, height: int) -> str:
    ratio = width / height
    best = min(ASPECT_PRESETS, key=lambda item: abs(float(item["ratio"]) - ratio))
    return str(best["id"])


def size_for_aspect(aspect_ratio: str, long_edge: int) -> tuple[int, int]:
    resolved = resolve_dimensions(aspect_ratio=aspect_ratio, long_edge=long_edge)
    return resolved.width, resolved.height
