from __future__ import annotations

import re
from typing import Iterable

STYLE_PRESETS: list[dict[str, object]] = [
    {
        "id": "none",
        "label": "自由",
        "positive": "",
        "negative": "",
        "accent": "#8b93a7",
    },
    {
        "id": "cinematic",
        "label": "电影感",
        "positive": "cinematic lighting, anamorphic lens, volumetric atmosphere, film grain, dramatic composition, 35mm photograph",
        "negative": "flat lighting, low contrast, snapshot",
        "accent": "#e6b86a",
    },
    {
        "id": "photography",
        "label": "真实摄影",
        "positive": "professional photography, natural light, shallow depth of field, ultra detailed, realistic textures, 50mm lens",
        "negative": "illustration, painting, cartoon, plastic skin",
        "accent": "#87c8b2",
    },
    {
        "id": "illustration",
        "label": "精致插画",
        "positive": "delicate digital illustration, expressive brushwork, harmonious palette, intricate details, clean composition",
        "negative": "photorealistic, blurry, cluttered",
        "accent": "#c59bf5",
    },
    {
        "id": "anime-cel",
        "label": "赛璐珞",
        "positive": "hand-drawn anime cel shading, bold clean lineart, flat colors, limited palette, soft cel shadows, expressive detailed eyes, 2D animation key visual, detailed background, masterpiece, best quality",
        "negative": "3d render, cgi, photorealistic, realistic skin texture, painterly, blurry lineart, messy lines, extra fingers, bad hands, watermark, text, jpeg artifacts",
        "accent": "#ff9f68",
    },
    {
        "id": "anime-modern",
        "label": "日系插画",
        "positive": "modern Japanese anime illustration, crisp lineart, vibrant colors, detailed eyes, dynamic lighting, high quality key visual, clean composition",
        "negative": "photorealistic, 3d render, muddy colors, lowres, bad anatomy",
        "accent": "#f28cbd",
    },
    {
        "id": "anime-sketch",
        "label": "手绘线稿",
        "positive": "hand-drawn anime sketch, expressive pencil linework, loose construction lines, monochrome, subtle paper texture, character design sheet",
        "negative": "photorealistic, 3d render, full color, digital painting, blurry lines",
        "accent": "#d7c7b8",
    },
    {
        "id": "anime",
        "label": "动画",
        "positive": "anime key visual, expressive linework, cel shading, vibrant colors, dynamic composition, detailed background",
        "negative": "photorealistic, 3d render, muddy colors",
        "accent": "#f28cbd",
    },
    {
        "id": "three-d",
        "label": "3D 渲染",
        "positive": "high-end 3d render, octane, subsurface scattering, studio lighting, tactile materials, depth of field",
        "negative": "2d flat, sketch, low poly",
        "accent": "#8fb8ff",
    },
    {
        "id": "watercolor",
        "label": "水彩",
        "positive": "loose watercolor painting, translucent washes, visible paper grain, soft edges, delicate pigment blooms",
        "negative": "digital sharpness, photo, neon",
        "accent": "#8ad5ea",
    },
    {
        "id": "cyberpunk",
        "label": "赛博朋克",
        "positive": "cyberpunk atmosphere, neon reflections, rain-slick streets, volumetric fog, teal and magenta palette, cinematic",
        "negative": "daylight, rustic, pastel",
        "accent": "#50d8ff",
    },
    {
        "id": "oil",
        "label": "油画",
        "positive": "museum oil painting, impasto brush strokes, rich chiaroscuro, canvas texture, classical composition",
        "negative": "flat vector, photo, low detail",
        "accent": "#d6a66f",
    },
    {
        "id": "minimal",
        "label": "极简",
        "positive": "minimalist composition, generous negative space, restrained palette, precise geometry, editorial design",
        "negative": "cluttered, busy, ornate",
        "accent": "#d5d9e5",
    },
    {
        "id": "pixel",
        "label": "像素艺术",
        "positive": "pixel art, 16-bit sprite, crisp pixels, limited palette, isometric detail, retro game aesthetic",
        "negative": "blurry, photorealistic, smooth gradient",
        "accent": "#b6e36b",
    },
    {
        "id": "product",
        "label": "产品视觉",
        "positive": "premium product photography, studio softbox lighting, seamless backdrop, macro detail, commercial composition",
        "negative": "cluttered background, harsh shadows, low resolution",
        "accent": "#f0d58a",
    },
]

SCHEDULER_PRESETS: list[dict[str, str]] = [
    {"id": "auto", "label": "自动"},
    {"id": "dpmpp_2m_karras", "label": "DPM++ 2M Karras"},
    {"id": "euler", "label": "Euler"},
    {"id": "euler_a", "label": "Euler a"},
    {"id": "lcm", "label": "LCM"},
    {"id": "ddim", "label": "DDIM"},
]

STYLE_MAP = {str(item["id"]): item for item in STYLE_PRESETS}
SCHEDULER_MAP = {item["id"]: item for item in SCHEDULER_PRESETS}

STOPWORDS = {
    "the",
    "and",
    "with",
    "from",
    "this",
    "that",
    "into",
    "over",
    "under",
    "very",
    "high",
    "low",
    "photo",
    "image",
    "style",
    "quality",
    "best",
    "detailed",
    "detail",
    "ultra",
    "realistic",
    "beautiful",
    "cinematic",
    "professional",
    "composition",
    "lighting",
    "color",
    "colors",
    "background",
    "foreground",
    "render",
    "highly",
    "masterpiece",
}


def model_defaults(model: str | None) -> tuple[int, float]:
    name = (model or "").lower()
    if "turbo" in name:
        return 4, 0.0
    if "schnell" in name:
        return 4, 0.0
    if "lightning" in name:
        return 8, 1.0
    if "lcm" in name:
        return 8, 1.0
    if "flux" in name:
        return 4, 3.5
    if "sd3" in name or "stable-diffusion-3" in name:
        return 28, 4.5
    if "xl" in name:
        return 28, 6.0
    if "1.5" in name or "v1-5" in name:
        return 25, 7.5
    return 25, 7.0


def scheduler_aliases(value: str) -> tuple[str, str]:
    """Return (diffusers scheduler, comfy scheduler)."""
    key = (value or "auto").lower()
    if key in ("euler", "euler_discrete"):
        return "EulerDiscreteScheduler", "normal"
    if key in ("euler_a", "euler_ancestral"):
        return "EulerAncestralDiscreteScheduler", "karras"
    if key in ("lcm",):
        return "LCMScheduler", "normal"
    if key in ("ddim",):
        return "DDIMScheduler", "normal"
    if key in ("dpmpp_2m", "dpmpp_2m_karras", "dpm++ 2m karras"):
        return "DPMSolverMultistepScheduler", "karras"
    return "DPMSolverMultistepScheduler", "karras"


def comfy_sampler(value: str) -> tuple[str, str]:
    key = (value or "auto").lower()
    if key in ("euler", "euler_discrete"):
        return "euler", "normal"
    if key in ("euler_a", "euler_ancestral"):
        return "euler_ancestral", "normal"
    if key == "lcm":
        return "lcm", "normal"
    if key == "ddim":
        return "ddim", "normal"
    return "dpmpp_2m", "karras"


def style_positive(style: str) -> str:
    item = STYLE_MAP.get(style or "none", STYLE_MAP["none"])
    return str(item.get("positive", ""))


def style_negative(style: str) -> str:
    item = STYLE_MAP.get(style or "none", STYLE_MAP["none"])
    return str(item.get("negative", ""))


def _contains_phrase(prompt: str, phrase: str) -> bool:
    if not phrase:
        return True
    return phrase.lower() in prompt.lower()


def compose_prompt(
    prompt: str,
    style: str = "none",
    learned_tokens: Iterable[str] | None = None,
    enhance: bool = False,
) -> str:
    parts = [prompt.strip()]
    style_part = style_positive(style)
    if style_part and not _contains_phrase(prompt, style_part):
        parts.append(style_part)
    if enhance:
        additions = [
            "coherent composition",
            "refined details",
            "balanced lighting",
            "intentional color palette",
        ]
        for phrase in additions:
            if not _contains_phrase(prompt, phrase):
                parts.append(phrase)
    for token in learned_tokens or []:
        token = token.strip()
        if 2 <= len(token) <= 40 and not _contains_phrase(prompt, token):
            parts.append(token)
    # Avoid runaway prompts that dilute the subject.
    result = ", ".join(part.strip(" ,") for part in parts if part.strip(" ,"))
    return result[:3500]


def compose_negative(prompt: str, style: str = "none", learned_negative: Iterable[str] | None = None) -> str:
    parts = [prompt.strip(), style_negative(style)]
    for token in learned_negative or []:
        token = token.strip()
        if 2 <= len(token) <= 40 and not _contains_phrase(" ".join(parts), token):
            parts.append(token)
    return ", ".join(part.strip(" ,") for part in parts if part.strip(" ,"))[:2000]


def tokenize(text: str) -> list[str]:
    if not text:
        return []
    lowered = text.lower()
    latin = re.findall(r"[a-z][a-z0-9_-]{2,}", lowered)
    chinese = re.findall(r"[\u4e00-\u9fff]{2,6}", lowered)
    tokens = []
    for token in [*latin, *chinese]:
        if token in STOPWORDS:
            continue
        if token.isascii() and len(token) < 3:
            continue
        tokens.append(token)
    return tokens
