from __future__ import annotations

import io
from typing import Any

import httpx
from PIL import Image

from backend.engines.base import (
    Availability,
    BaseEngine,
    CancelCheck,
    EngineError,
    GeneratedImage,
    GenerationContext,
    ProgressCallback,
)
from backend.security import SecretStore
from backend.utils.dimensions import nearest_aspect
from backend.utils.images import image_to_png_bytes

ASPECTS = ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9", "9:21"]


class StabilityEngine(BaseEngine):
    kind = "stability"
    display_name = "Stability AI"

    @staticmethod
    def _base(provider: dict[str, Any]) -> str:
        base = str(provider.get("base_url") or "https://api.stability.ai").strip().rstrip("/")
        if not base:
            base = "https://api.stability.ai"
        return base

    @staticmethod
    def _key(provider: dict[str, Any], secrets: SecretStore) -> str | None:
        return secrets.get(str(provider.get("id")))

    def availability(self, provider: dict[str, Any], secrets: SecretStore) -> Availability:
        if not self._key(provider, secrets):
            return Availability(available=False, reason="尚未填写 Stability API Key", detail="在模型页编辑供应商并保存密钥")
        return Availability(available=True, reason="已配置 API Key", detail=self._base(provider))

    def _aspect(self, width: int, height: int) -> str:
        wanted = nearest_aspect(width, height)
        return wanted if wanted in ASPECTS else "1:1"

    def _error(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
            errors = payload.get("errors") or payload.get("message") or payload
            return str(errors)[:400]
        except Exception:
            return response.text[:400] or f"HTTP {response.status_code}"

    def generate(
        self,
        context: GenerationContext,
        provider: dict[str, Any],
        secrets: SecretStore,
        progress: ProgressCallback,
        cancelled: CancelCheck,
    ) -> list[GeneratedImage]:
        key = self._key(provider, secrets)
        if not key:
            raise EngineError("缺少 Stability API Key", code="missing_api_key", status_code=412)
        base = self._base(provider)
        headers = {"Authorization": f"Bearer {key}", "Accept": "image/*"}
        aspect = self._aspect(context.width, context.height)
        model = str(context.extra.get("model") or provider.get("model") or "sd3.5-large")
        endpoint = "core" if context.mode == "txt2img" else "sd3"
        results: list[GeneratedImage] = []
        with httpx.Client(timeout=httpx.Timeout(300, connect=20)) as client:
            for index in range(context.batch_size):
                self.check_cancel(cancelled)
                progress(0.15 + index * 0.75 / context.batch_size, f"请求 Stability {endpoint}")
                fields: list[tuple[str, tuple[None, str]]] = [
                    ("prompt", (None, context.prompt)),
                    ("negative_prompt", (None, context.negative_prompt)),
                    ("aspect_ratio", (None, aspect)),
                    ("output_format", (None, "png")),
                ]
                if context.seed >= 0:
                    fields.append(("seed", (None, str(context.seed + index))))
                files: dict[str, Any] = {}
                if context.mode == "img2img":
                    assert context.init_image is not None
                    fields.extend(
                        [
                            ("mode", (None, "image-to-image")),
                            ("strength", (None, str(context.strength))),
                            ("model", (None, model)),
                        ]
                    )
                    files["image"] = ("init.png", image_to_png_bytes(context.init_image.convert("RGB")), "image/png")
                response = client.post(
                    f"{base}/v2beta/stable-image/generate/{endpoint}",
                    headers=headers,
                    files={**files, **{name: value for name, value in fields}},  # type: ignore[dict-item]
                )
                if response.status_code >= 400:
                    hint = ""
                    if response.status_code == 401:
                        hint = "检查 API Key。"
                    elif response.status_code == 402:
                        hint = "账户余额不足。"
                    elif response.status_code == 403:
                        hint = "内容被安全策略拦截，或密钥无模型权限。"
                    raise EngineError(
                        f"Stability 返回错误：{self._error(response)}",
                        code="stability_error",
                        hint=hint,
                    )
                if "application/json" in response.headers.get("content-type", ""):
                    raise EngineError(f"Stability 未返回图片：{response.text[:300]}", code="stability_no_image")
                try:
                    image = Image.open(io.BytesIO(response.content))
                    image.load()
                    image = image.convert("RGB")
                except Exception as exc:
                    raise EngineError("Stability 返回的图片无法解析", code="stability_bad_image") from exc
                results.append(
                    GeneratedImage(
                        image=image,
                        seed=context.seed + index,
                        meta={
                            "remote": True,
                            "provider": "stability",
                            "requested_aspect": aspect,
                            "actual_size": f"{image.width}x{image.height}",
                            "model": model,
                        },
                    )
                )
                progress(0.15 + (index + 1) * 0.75 / context.batch_size, f"收到图片 {index + 1}/{context.batch_size}")
        return results

    def test_connection(self, provider: dict[str, Any], secrets: SecretStore) -> dict[str, Any]:
        key = self._key(provider, secrets)
        if not key:
            return {"ok": False, "message": "尚未填写 API Key", "models": []}
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.get(
                    f"{self._base(provider)}/v1/user/account",
                    headers={"Authorization": f"Bearer {key}"},
                )
                if response.status_code == 200:
                    return {"ok": True, "message": "连接成功", "detail": self._base(provider), "models": ["sd3.5-large", "sd3.5-medium", "core"]}
                return {"ok": False, "message": f"HTTP {response.status_code}", "detail": self._error(response), "models": []}
        except Exception as exc:
            return {"ok": False, "message": "无法连接 Stability", "detail": str(exc)[:200], "models": []}

    def list_models(self, provider: dict[str, Any], secrets: SecretStore) -> list[str]:
        return ["sd3.5-large", "sd3.5-medium", "core"]
