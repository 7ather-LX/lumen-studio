from __future__ import annotations

import io
import time
import uuid
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
from backend.utils.prompts import comfy_sampler
from backend.utils.images import image_to_png_bytes


class ComfyUIEngine(BaseEngine):
    kind = "comfyui"
    display_name = "ComfyUI"
    _availability_cache: dict[str, tuple[float, Availability]] = {}

    @staticmethod
    def _base(provider: dict[str, Any]) -> str:
        base = str(provider.get("base_url") or "").strip().rstrip("/")
        if not base:
            raise EngineError("未配置 ComfyUI 地址", code="comfyui_url_missing", status_code=422)
        if not base.startswith(("http://", "https://")):
            base = "http://" + base
        return base

    @staticmethod
    def _headers(provider: dict[str, Any], secrets: SecretStore) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        key = secrets.get(str(provider.get("id")))
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def availability(self, provider: dict[str, Any], secrets: SecretStore) -> Availability:
        provider_id = str(provider.get("id"))
        cached = self._availability_cache.get(provider_id)
        if cached and time.time() - cached[0] < 12:
            return cached[1]
        try:
            base = self._base(provider)
        except EngineError as exc:
            result = Availability(available=False, reason=exc.message, detail="在模型页填写 ComfyUI 服务地址")
            self._availability_cache[provider_id] = (time.time(), result)
            return result
        try:
            with httpx.Client(timeout=4.0) as client:
                response = client.get(f"{base}/system_stats", headers=self._headers(provider, secrets))
                if response.status_code == 401:
                    result = Availability(available=False, reason="ComfyUI 需要 API Key", detail="在模型页填写访问令牌")
                elif response.status_code >= 400:
                    result = Availability(available=False, reason=f"ComfyUI 返回 HTTP {response.status_code}")
                else:
                    data = response.json()
                    devices = data.get("devices") or []
                    device_name = devices[0].get("name") if devices else "ComfyUI"
                    version = (data.get("system") or {}).get("comfyui_version", "")
                    result = Availability(
                        available=True,
                        reason=f"已连接 · {device_name}",
                        detail=f"ComfyUI {version}".strip(),
                        version=str(version),
                    )
        except Exception as exc:
            result = Availability(
                available=False,
                reason="无法连接 ComfyUI",
                detail=f"{base} · 请确认服务已启动并允许本机访问（{str(exc)[:100]}）",
            )
        self._availability_cache[provider_id] = (time.time(), result)
        return result

    def _checkpoints(self, provider: dict[str, Any], secrets: SecretStore) -> list[str]:
        base = self._base(provider)
        try:
            with httpx.Client(timeout=8.0) as client:
                response = client.get(f"{base}/object_info/CheckpointLoaderSimple", headers=self._headers(provider, secrets))
                response.raise_for_status()
                payload = response.json()
                node = payload.get("CheckpointLoaderSimple", {})
                required = node.get("input", {}).get("required", {})
                entry = required.get("ckpt_name")
                if isinstance(entry, list) and entry:
                    values = entry[0]
                    if isinstance(values, list):
                        return [str(value) for value in values]
                if isinstance(entry, dict):
                    values = entry.get("options") or entry.get("default")
                    if isinstance(values, list):
                        return [str(value) for value in values]
        except Exception:
            pass
        return []

    def list_models(self, provider: dict[str, Any], secrets: SecretStore) -> list[str]:
        return self._checkpoints(provider, secrets)

    def test_connection(self, provider: dict[str, Any], secrets: SecretStore) -> dict[str, Any]:
        self._availability_cache.pop(str(provider.get("id")), None)
        state = self.availability(provider, secrets)
        checkpoints = self._checkpoints(provider, secrets) if state.available else []
        return {
            "ok": state.available,
            "message": state.reason,
            "detail": state.detail,
            "models": checkpoints,
        }

    def _workflow(
        self,
        context: GenerationContext,
        checkpoint: str,
        sampler_name: str,
        scheduler_name: str,
        seed: int,
        uploaded_name: str | None,
    ) -> dict[str, Any]:
        workflow: dict[str, Any] = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": context.prompt, "clip": ["1", 1]}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": context.negative_prompt, "clip": ["1", 1]}},
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": context.steps,
                    "cfg": context.guidance,
                    "sampler_name": sampler_name,
                    "scheduler": scheduler_name,
                    "denoise": context.strength if context.mode == "img2img" else 1.0,
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                },
            },
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
            "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "lumen", "images": ["6", 0]}},
        }
        if context.mode == "img2img" and uploaded_name:
            workflow["8"] = {"class_type": "LoadImage", "inputs": {"image": uploaded_name}}
            workflow["9"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["8", 0], "vae": ["1", 2]}}
            workflow["5"]["inputs"]["latent_image"] = ["9", 0]
        else:
            workflow["4"] = {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": context.width, "height": context.height, "batch_size": 1},
            }
            workflow["5"]["inputs"]["latent_image"] = ["4", 0]
        return workflow

    def _upload(self, base: str, context: GenerationContext, provider: dict[str, Any], secrets: SecretStore) -> str:
        assert context.init_image is not None
        raw = image_to_png_bytes(context.init_image.convert("RGB"))
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{base}/upload/image",
                    headers=self._headers(provider, secrets),
                    files={"image": (context.init_image_name or "init.png", raw, "image/png")},
                    data={"type": "input", "overwrite": "true"},
                )
                response.raise_for_status()
                payload = response.json()
                name = str(payload.get("name") or "")
                subfolder = str(payload.get("subfolder") or "")
                if not name:
                    raise EngineError("ComfyUI 上传参考图失败", code="comfyui_upload_failed")
                return f"{subfolder}/{name}" if subfolder else name
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError(f"ComfyUI 上传参考图失败：{str(exc)[:180]}", code="comfyui_upload_failed") from exc

    def generate(
        self,
        context: GenerationContext,
        provider: dict[str, Any],
        secrets: SecretStore,
        progress: ProgressCallback,
        cancelled: CancelCheck,
    ) -> list[GeneratedImage]:
        base = self._base(provider)
        checkpoints = self._checkpoints(provider, secrets)
        checkpoint = str(context.extra.get("model") or provider.get("model") or "").strip()
        if not checkpoint:
            if not checkpoints:
                raise EngineError(
                    "ComfyUI 中没有可用 checkpoint",
                    code="comfyui_no_checkpoint",
                    hint="把模型放入 ComfyUI/models/checkpoints，并在模型页点击刷新。",
                    status_code=412,
                )
            checkpoint = checkpoints[0]
        if checkpoints and checkpoint not in checkpoints:
            # ComfyUI accepts subfolder paths; only warn through metadata rather than fail.
            pass

        uploaded = None
        if context.mode == "img2img":
            progress(0.04, "上传参考图到 ComfyUI")
            uploaded = self._upload(base, context, provider, secrets)

        client_id = uuid.uuid4().hex
        timeout = float(provider.get("options", {}).get("timeout") or 420)
        sampler_name, scheduler_name = comfy_sampler(context.scheduler)
        if context.scheduler in ("auto", ""):
            sampler_name = str(provider.get("options", {}).get("sampler") or "dpmpp_2m")
            scheduler_name = str(provider.get("options", {}).get("scheduler") or "karras")
        results: list[GeneratedImage] = []
        try:
            with httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
                for index in range(context.batch_size):
                    self.check_cancel(cancelled)
                    seed = (context.seed + index) & 0xFFFFFFFF
                    workflow = self._workflow(context, checkpoint, sampler_name, scheduler_name, seed, uploaded)
                    progress(0.08 + index * 0.8 / context.batch_size, "提交 ComfyUI 工作流")
                    queued = client.post(
                        f"{base}/prompt",
                        headers={**self._headers(provider, secrets), "Content-Type": "application/json"},
                        json={"prompt": workflow, "client_id": client_id},
                    )
                    if queued.status_code >= 400:
                        detail = queued.text[:500]
                        raise EngineError(
                            f"ComfyUI 拒绝了工作流（HTTP {queued.status_code}）",
                            code="comfyui_prompt_rejected",
                            hint=detail,
                        )
                    prompt_id = str(queued.json().get("prompt_id") or "")
                    if not prompt_id:
                        raise EngineError("ComfyUI 未返回 prompt_id", code="comfyui_bad_response")

                    deadline = time.time() + timeout
                    history_item: dict[str, Any] | None = None
                    spinner = ["采样中", "解码中", "整理输出"]
                    tick = 0
                    while time.time() < deadline:
                        self.check_cancel(cancelled)
                        history_response = client.get(
                            f"{base}/history/{prompt_id}", headers=self._headers(provider, secrets)
                        )
                        if history_response.status_code == 200:
                            history = history_response.json()
                            item = history.get(prompt_id)
                            if item:
                                status = item.get("status") or {}
                                if status.get("status_str") == "error" or status.get("completed") is False and status.get("messages"):
                                    messages = status.get("messages") or []
                                    error_text = "ComfyUI 执行失败"
                                    for message in messages:
                                        if isinstance(message, list) and len(message) > 1 and message[0] in ("execution_error", "execution_interrupted"):
                                            payload = message[1] or {}
                                            error_text = str(payload.get("exception_message") or error_text)[:350]
                                    raise EngineError(error_text, code="comfyui_execution_failed")
                                if status.get("completed") or item.get("outputs"):
                                    history_item = item
                                    break
                        tick += 1
                        progress(
                            min(0.88, 0.12 + index * 0.8 / context.batch_size + min(0.7, tick * 0.015)),
                            f"{spinner[min(len(spinner) - 1, tick // 8)]} · ComfyUI",
                        )
                        time.sleep(0.7)
                    if history_item is None:
                        raise EngineError(
                            "ComfyUI 生成超时",
                            code="comfyui_timeout",
                            hint="检查 ComfyUI 日志；首次加载大模型可能超过 7 分钟，可在模型页调高超时。",
                        )

                    images = []
                    for node_output in (history_item.get("outputs") or {}).values():
                        for image in node_output.get("images", []) or []:
                            if image.get("type", "output") == "output":
                                images.append(image)
                    if not images:
                        raise EngineError("ComfyUI 未返回输出图片", code="comfyui_no_output")
                    image_info = images[0]
                    params = {
                        "filename": image_info.get("filename", ""),
                        "subfolder": image_info.get("subfolder", ""),
                        "type": image_info.get("type", "output"),
                    }
                    view = client.get(f"{base}/view", params=params, headers=self._headers(provider, secrets))
                    view.raise_for_status()
                    image = Image.open(io.BytesIO(view.content))
                    image.load()
                    results.append(
                        GeneratedImage(
                            image=image.convert("RGB"),
                            seed=seed,
                            meta={
                                "checkpoint": checkpoint,
                                "sampler": sampler_name,
                                "scheduler": scheduler_name,
                                "low_vram": context.low_vram,
                            },
                        )
                    )
                    progress(0.9, f"ComfyUI 完成 {index + 1}/{context.batch_size}")
        except EngineError:
            raise
        except httpx.TimeoutException as exc:
            raise EngineError(
                "ComfyUI 请求超时",
                code="comfyui_timeout",
                hint="检查 ComfyUI 是否仍在生成，或在模型页提高超时时间。",
            ) from exc
        except Exception as exc:
            raise EngineError(f"ComfyUI 生成失败：{str(exc)[:300]}", code="comfyui_error") from exc
        return results
