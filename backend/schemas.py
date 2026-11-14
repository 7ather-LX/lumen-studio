from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ProviderKind = Literal["diffusers", "comfyui", "openai", "stability", "demo"]
Mode = Literal["txt2img", "img2img"]


class ProviderUpsert(BaseModel):
    id: str | None = Field(default=None, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=80)
    kind: ProviderKind
    base_url: str = Field(default="", max_length=500)
    model: str = Field(default="", max_length=300)
    enabled: bool = True
    is_default: bool = False
    options: dict[str, Any] = Field(default_factory=dict)
    api_key: str | None = Field(default=None, max_length=400)
    clear_secret: bool = False


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=6000)
    negative_prompt: str = Field(default="", max_length=3000)
    mode: Mode = "txt2img"
    provider_id: str | None = None
    model: str | None = Field(default=None, max_length=300)
    width: int | None = Field(default=None, ge=128, le=4096)
    height: int | None = Field(default=None, ge=128, le=4096)
    aspect_ratio: str = "1:1"
    long_edge: int = Field(default=1024, ge=256, le=2048)
    steps: int | None = Field(default=None, ge=1, le=100)
    guidance: float | None = Field(default=None, ge=0, le=30)
    seed: int = Field(default=-1, ge=-1, le=2**32 - 1)
    strength: float = Field(default=0.55, ge=0.05, le=1.0)
    batch_size: int = Field(default=1, ge=1, le=4)
    scheduler: str = Field(default="auto", max_length=40)
    style: str = Field(default="none", max_length=40)
    init_image_id: str | None = Field(default=None, max_length=80)
    init_image: str | None = None
    auto_tune: bool = True
    enhance_prompt: bool = False
    cel_shading: bool = False


class FeedbackRequest(BaseModel):
    rating: int | None = Field(default=None, ge=0, le=5)
    favorite: bool | None = None
    notes: str | None = Field(default=None, max_length=3000)
    tags: list[str] | None = None


class ImagePatch(BaseModel):
    favorite: bool | None = None
    notes: str | None = Field(default=None, max_length=3000)
    tags: list[str] | None = None


class CropRequest(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0.02, le=1)
    height: float = Field(gt=0.02, le=1)


class RuntimeInstallRequest(BaseModel):
    variant: Literal["auto", "cuda", "cpu"] = "auto"


class SettingsPatch(BaseModel):
    patch: dict[str, Any]
