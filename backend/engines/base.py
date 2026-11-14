from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from PIL import Image

from backend.security import SecretStore

ProgressCallback = Callable[[float, str], None]
CancelCheck = Callable[[], bool]


class EngineError(RuntimeError):
    def __init__(
        self,
        message: str,
        code: str = "engine_error",
        hint: str = "",
        status_code: int = 502,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.hint = hint
        self.status_code = status_code


@dataclass
class GenerationContext:
    prompt: str
    negative_prompt: str
    width: int
    height: int
    steps: int
    guidance: float
    seed: int
    batch_size: int
    scheduler: str
    style: str
    mode: str = "txt2img"
    strength: float = 0.55
    init_image: Image.Image | None = None
    init_image_name: str = "init.png"
    low_vram: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class GeneratedImage:
    image: Image.Image
    seed: int
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Availability:
    available: bool
    reason: str = ""
    detail: str = ""
    version: str = ""
    installable: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "reason": self.reason,
            "detail": self.detail,
            "version": self.version,
            "installable": self.installable,
        }


class BaseEngine:
    kind = "base"
    display_name = "Base"

    def availability(self, provider: dict[str, Any], secrets: SecretStore) -> Availability:
        return Availability(available=True)

    def test_connection(self, provider: dict[str, Any], secrets: SecretStore) -> dict[str, Any]:
        state = self.availability(provider, secrets)
        return {"ok": state.available, "message": state.reason or "连接可用", "detail": state.detail}

    def list_models(self, provider: dict[str, Any], secrets: SecretStore) -> list[str]:
        return []

    def generate(
        self,
        context: GenerationContext,
        provider: dict[str, Any],
        secrets: SecretStore,
        progress: ProgressCallback,
        cancelled: CancelCheck,
    ) -> list[GeneratedImage]:
        raise NotImplementedError

    @staticmethod
    def check_cancel(cancelled: CancelCheck) -> None:
        if cancelled():
            raise EngineError("任务已取消", code="cancelled", status_code=409)
