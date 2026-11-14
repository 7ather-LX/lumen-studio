from __future__ import annotations

from backend.engines.base import BaseEngine
from backend.engines.comfyui import ComfyUIEngine
from backend.engines.demo import DemoEngine
from backend.engines.diffusers_engine import DiffusersEngine
from backend.engines.openai_images import OpenAIImagesEngine
from backend.engines.stability import StabilityEngine

_ENGINES: dict[str, BaseEngine] = {
    "diffusers": DiffusersEngine(),
    "comfyui": ComfyUIEngine(),
    "openai": OpenAIImagesEngine(),
    "stability": StabilityEngine(),
    "demo": DemoEngine(),
}

KIND_LABELS = {
    "diffusers": "本地 Diffusers",
    "comfyui": "ComfyUI",
    "openai": "OpenAI 兼容",
    "stability": "Stability AI",
    "demo": "离线示例",
}


def get_engine(kind: str) -> BaseEngine:
    engine = _ENGINES.get(kind)
    if engine is None:
        raise KeyError(f"unknown provider kind: {kind}")
    return engine


def all_engines() -> dict[str, BaseEngine]:
    return dict(_ENGINES)
