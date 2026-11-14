from __future__ import annotations

import base64
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
from backend.utils.images import image_to_png_bytes


class OpenAIImagesEngine(BaseEngine):
    kind = "openai"
    display_name = "OpenAI Images"

    @staticmethod
    def _base(provider: dict[str, Any]) -> str:
        base = str(provider.get("base_url") or "https://api.openai.com/v1").strip().rstrip("/")
        if not base:
            base = "https://api.openai.com/v1"
        if not base.endswith("/v1") and "openai.com" in base:
            base += "/v1"
        return base

    @staticmethod
    def _headers(provider: dict[str, Any], secrets: SecretStore) -> dict[str, str]:
        key = secrets.get(str(provider.get("id")))
        headers = {"Accept": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def _key(self, provider: dict[str, Any], secrets: SecretStore) -> str | None:
        return secrets.get(str(provider.get("id")))

    def availability(self, provider: dict[str, Any], secrets: SecretStore) -> Availability:
        base = self._base(provider)
        key = self._key(provider, secrets)
        if "api.openai.com" in base and not key:
            return Availability(available=False, reason="尚未填写 OpenAI API Key", detail="在模型页编辑此供应商并保存密钥")
        if key:
            return Availability(available=True, reason="已配置 API Key", detail=base)
        return Availability(available=True, reason="自定义端点（无密钥）", detail=base)

    def _size(self, width: int, height: int, model: str) -> str:
        ratio = width / height
        name = model.lower()
        if name.startswith("gpt-image"):
            options = [(1024, 1024), (1536, 1024), (1024, 1536)]
        elif "dall-e-3" in name:
            options = [(1024, 1024), (1792, 1024), (1024, 1792)]
        elif "dall-e-2" in name:
            return "1024x1024"
        else:
            return f"{width}x{height}"
        best = min(options, key=lambda item: abs((item[0] / item[1]) - ratio))
        return f"{best[0]}x{best[1]}"

    def _error_message(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                error = payload.get("error")
                if isinstance(error, dict) and error.get("message"):
                    return str(error["message"])[:400]
                if isinstance(error, str):
                    return error[:400]
                if payload.get("message"):
                    return str(payload["message"])[:400]
        except Exception:
            pass
        return response.text[:400] or f"HTTP {response.status_code}"

    def _decode(self, payload: dict[str, Any], client: httpx.Client, provider: dict[str, Any], secrets: SecretStore) -> list[Image.Image]:
        items = payload.get("data")
        if not isinstance(items, list):
            items = payload.get("images") if isinstance(payload.get("images"), list) else []
        images: list[Image.Image] = []
        for item in items:
            raw: bytes | None = None
            if isinstance(item, str):
                try:
                    raw = base64.b64decode(item)
                except Exception:
                    raw = None
            elif isinstance(item, dict):
                encoded = item.get("b64_json") or item.get("base64") or item.get("image")
                if isinstance(encoded, str):
                    if encoded.startswith("data:"):
                        encoded = encoded.split(",", 1)[-1]
                    try:
                        raw = base64.b64decode(encoded)
                    except Exception:
                        raw = None
                elif item.get("url"):
                    response = client.get(str(item["url"]))
                    response.raise_for_status()
                    raw = response.content
            if not raw:
                continue
            try:
                image = Image.open(io.BytesIO(raw))
                image.load()
                images.append(image.convert("RGB"))
            except Exception:
                continue
        return images

    def generate(
        self,
        context: GenerationContext,
        provider: dict[str, Any],
        secrets: SecretStore,
        progress: ProgressCallback,
        cancelled: CancelCheck,
    ) -> list[GeneratedImage]:
        base = self._base(provider)
        key = self._key(provider, secrets)
        if "api.openai.com" in base and not key:
            raise EngineError("缺少 OpenAI API Key", code="missing_api_key", status_code=412)
        model = str(context.extra.get("model") or provider.get("model") or "gpt-image-1")
        headers = self._headers(provider, secrets)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        size = self._size(context.width, context.height, model)
        results: list[GeneratedImage] = []

        with httpx.Client(timeout=httpx.Timeout(600, connect=20)) as client:
            for index in range(context.batch_size):
                self.check_cancel(cancelled)
                progress(0.12 + index * 0.8 / context.batch_size, f"请求 {model}")
                if context.mode == "img2img":
                    if "dall-e-3" in model.lower():
                        raise EngineError("DALL·E 3 不支持图生图，请改用 gpt-image-1 或本地引擎", code="provider_unsupported")
                    assert context.init_image is not None
                    raw = image_to_png_bytes(context.init_image.convert("RGB"))
                    data = {
                        "model": model,
                        "prompt": context.prompt,
                        "size": size,
                        "n": "1",
                    }
                    if "gpt-image" not in model.lower():
                        data["response_format"] = "b64_json"
                    response = client.post(
                        f"{base}/images/edits",
                        headers=headers,
                        data=data,
                        files={"image": ("init.png", raw, "image/png")},
                    )
                else:
                    payload: dict[str, Any] = {
                        "model": model,
                        "prompt": context.prompt,
                        "n": 1,
                        "size": size,
                    }
                    if "gpt-image" not in model.lower():
                        payload["response_format"] = "b64_json"
                    if context.negative_prompt:
                        payload["negative_prompt"] = context.negative_prompt
                    response = client.post(f"{base}/images/generations", headers=headers, json=payload)

                if response.status_code >= 400:
                    message = self._error_message(response)
                    code = "provider_auth" if response.status_code in (401, 403) else "provider_error"
                    hint = ""
                    if response.status_code == 401:
                        hint = "检查 API Key 是否正确、是否有该模型的访问权限。"
                    elif response.status_code == 429:
                        hint = "配额不足或请求过快。"
                    elif "size" in message.lower():
                        hint = "该供应商不支持所选尺寸，请在设置中调整分辨率。"
                    elif "moderation" in message.lower() or "safety" in message.lower():
                        hint = "提示词被云端供应商的安全策略拦截。"
                    raise EngineError(f"{model} 返回错误：{message}", code=code, hint=hint, status_code=502)
                try:
                    payload_json = response.json()
                except Exception as exc:
                    raise EngineError("供应商返回了无法解析的响应", code="provider_bad_response") from exc
                images = self._decode(payload_json, client, provider, secrets)
                if not images:
                    raise EngineError("供应商未返回图片数据", code="provider_no_image")
                results.append(
                    GeneratedImage(
                        image=images[0],
                        seed=context.seed + index,
                        meta={
                            "remote": True,
                            "provider": "openai",
                            "requested_size": f"{context.width}x{context.height}",
                            "actual_size": f"{images[0].width}x{images[0].height}",
                            "size_note": "" if size == f"{context.width}x{context.height}" else f"供应商使用最接近的尺寸 {size}",
                        },
                    )
                )
                progress(0.12 + (index + 1) * 0.8 / context.batch_size, f"收到图片 {index + 1}/{context.batch_size}")
        return results

    def test_connection(self, provider: dict[str, Any], secrets: SecretStore) -> dict[str, Any]:
        state = self.availability(provider, secrets)
        if not state.available:
            return {"ok": False, "message": state.reason, "detail": state.detail, "models": []}
        base = self._base(provider)
        key = self._key(provider, secrets)
        headers = self._headers(provider, secrets)
        models: list[str] = []
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.get(f"{base}/models", headers=headers)
                if response.status_code == 200:
                    payload = response.json()
                    models = [str(item.get("id")) for item in payload.get("data", []) if item.get("id")]
                    return {"ok": True, "message": f"连接成功 · {len(models)} 个模型", "detail": base, "models": models}
                if response.status_code in (401, 403):
                    return {"ok": False, "message": "API Key 无效或无权限", "detail": self._error_message(response), "models": []}
                return {
                    "ok": True,
                    "message": "端点可访问（未提供模型列表）",
                    "detail": f"HTTP {response.status_code}",
                    "models": models,
                }
        except Exception as exc:
            return {"ok": False, "message": "无法连接供应商", "detail": str(exc)[:200], "models": []}

    def list_models(self, provider: dict[str, Any], secrets: SecretStore) -> list[str]:
        base = self._base(provider)
        headers = self._headers(provider, secrets)
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.get(f"{base}/models", headers=headers)
                if response.status_code == 200:
                    payload = response.json()
                    wanted = [
                        str(item["id"])
                        for item in payload.get("data", [])
                        if item.get("id")
                        and any(token in str(item["id"]).lower() for token in ("image", "dall-e", "flux", "sd", "kolors", "seedream"))
                    ]
                    if wanted:
                        return sorted(set(wanted))
        except Exception:
            pass
        return ["gpt-image-1", "dall-e-3", "dall-e-2"]
