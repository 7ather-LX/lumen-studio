from __future__ import annotations

import gc
import inspect
import os
import threading
from typing import Any

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
from backend.utils.prompts import model_defaults, scheduler_aliases
from backend.utils.system import clear_gpu_cache, gpu_inventory

LOCAL_MODEL_CATALOG = [
    {
        "id": "stabilityai/sd-turbo",
        "label": "SD-Turbo",
        "family": "SD 2.1 Turbo",
        "download_gb": 2.5,
        "min_vram_mb": 1800,
        "comfort_vram_mb": 6000,
        "default_edge": 512,
        "license": "Stability AI Community License",
        "note": "4 步出图，低显存模式首选；512 分辨率最佳",
    },
    {
        "id": "runwayml/stable-diffusion-v1-5",
        "label": "Stable Diffusion 1.5",
        "family": "SD 1.5",
        "download_gb": 4.0,
        "min_vram_mb": 2200,
        "comfort_vram_mb": 6000,
        "default_edge": 512,
        "license": "CreativeML OpenRAIL-M",
        "note": "生态成熟，模型与 LoRA 最多，512 原生",
    },
    {
        "id": "gsdf/Counterfeit-V3.0",
        "label": "Counterfeit V3",
        "family": "Anime SD 1.5",
        "download_gb": 4.0,
        "min_vram_mb": 2200,
        "comfort_vram_mb": 6000,
        "default_edge": 512,
        "license": "CreativeML OpenRAIL-M",
        "note": "经典赛璐珞动漫角色模型；512 原生，适合手绘线稿与平涂",
    },
    {
        "id": "Meina/MeinaMix",
        "label": "MeinaMix",
        "family": "Anime SD 1.5",
        "download_gb": 4.0,
        "min_vram_mb": 2200,
        "comfort_vram_mb": 6000,
        "default_edge": 512,
        "license": "CreativeML OpenRAIL-M",
        "note": "日系角色与柔和色彩；与 anime 提示词配合良好",
    },
    {
        "id": "stabilityai/stable-diffusion-xl-base-1.0",
        "label": "SDXL 1.0",
        "family": "SDXL",
        "download_gb": 7.0,
        "min_vram_mb": 3800,
        "comfort_vram_mb": 9000,
        "default_edge": 1024,
        "license": "CreativeML OpenRAIL++-M",
        "note": "高分辨率与细节更好；低显存模式建议 768",
    },
    {
        "id": "black-forest-labs/FLUX.1-schnell",
        "label": "FLUX.1 schnell",
        "family": "FLUX",
        "download_gb": 24.0,
        "min_vram_mb": 10000,
        "comfort_vram_mb": 20000,
        "default_edge": 1024,
        "license": "Apache 2.0",
        "note": "质量高但下载大；12 GB 显存需要卸载与量化，非低显存首选",
    },
]


class DiffusersEngine(BaseEngine):
    kind = "diffusers"
    display_name = "本地 Diffusers"
    _lock = threading.RLock()
    _pipelines: dict[str, Any] = {}
    _loaded_key: str | None = None

    def __init__(self) -> None:
        self._torch = None
        self._diffusers = None

    def _imports(self) -> tuple[Any, Any]:
        if self._torch is not None and self._diffusers is not None:
            return self._torch, self._diffusers
        try:
            import torch
            import diffusers
        except Exception as exc:  # pragma: no cover - depends on optional runtime
            raise EngineError(
                "尚未安装本地生成运行时（PyTorch + Diffusers）",
                code="local_runtime_missing",
                hint="在「模型」页点击一键安装本地引擎，或在终端运行 scripts\\install-local-engine.ps1。",
                status_code=412,
            ) from exc
        self._torch = torch
        self._diffusers = diffusers
        return torch, diffusers

    def availability(self, provider: dict[str, Any], secrets: SecretStore) -> Availability:
        endpoint = str(provider.get("options", {}).get("hf_endpoint") or os.environ.get("HF_ENDPOINT") or "")
        if endpoint:
            os.environ["HF_ENDPOINT"] = endpoint
        try:
            torch, diffusers = self._imports()
        except EngineError as exc:
            return Availability(
                available=False,
                reason=exc.message,
                detail=exc.hint,
                installable=True,
            )
        cuda = bool(torch.cuda.is_available())
        gpu_name = torch.cuda.get_device_name(0) if cuda else "CPU"
        return Availability(
            available=True,
            reason=f"运行时就绪 · {gpu_name}",
            detail=f"torch {torch.__version__} · diffusers {diffusers.__version__}",
            version=f"{torch.__version__}/{diffusers.__version__}",
        )

    def _device(self, provider: dict[str, Any]) -> str:
        torch, _ = self._imports()
        requested = str(provider.get("options", {}).get("device") or "auto")
        if requested == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        if requested == "cuda" and not torch.cuda.is_available():
            raise EngineError("配置为 CUDA，但当前 PyTorch 无法使用 CUDA", code="cuda_unavailable", status_code=412)
        return requested

    def _dtype(self, torch: Any, device: str, model: str, provider: dict[str, Any]) -> Any:
        requested = str(provider.get("options", {}).get("dtype") or "auto")
        if requested == "float32":
            return torch.float32
        if requested == "bfloat16":
            return torch.bfloat16
        if requested == "float16":
            return torch.float16
        if device == "cuda":
            if "flux" in model.lower():
                return torch.bfloat16
            return torch.float16
        return torch.float32

    def _load_pipeline(
        self,
        provider: dict[str, Any],
        model: str,
        mode: str,
        low_vram: bool,
    ) -> Any:
        torch, diffusers = self._imports()
        device = self._device(provider)
        dtype = self._dtype(torch, device, model, provider)
        options = provider.get("options", {})
        key = f"{model}|{mode}|{device}|{dtype}|{low_vram}|{options.get('local_files_only')}"
        with self._lock:
            if key in self._pipelines:
                return self._pipelines[key]
            # A single resident pipeline keeps the footprint predictable.
            for cached in list(self._pipelines):
                self._pipelines.pop(cached, None)
            gc.collect()
            if device == "cuda":
                torch.cuda.empty_cache()

            local_only = bool(options.get("local_files_only"))
            endpoint = str(options.get("hf_endpoint") or os.environ.get("HF_ENDPOINT") or "")
            if endpoint:
                os.environ["HF_ENDPOINT"] = endpoint

            pipeline_class = (
                diffusers.AutoPipelineForImage2Image
                if mode == "img2img"
                else diffusers.AutoPipelineForText2Image
            )
            base_kwargs: dict[str, Any] = {
                "torch_dtype": dtype,
                "use_safetensors": True,
                "local_files_only": local_only,
            }
            variant_option = str(options.get("variant") or "auto")
            if variant_option == "fp16" or (variant_option == "auto" and dtype == torch.float16):
                base_kwargs["variant"] = "fp16"
            if model and os.path.isdir(model):
                base_kwargs["local_files_only"] = True

            attempts: list[dict[str, Any]] = [base_kwargs]
            if "variant" in base_kwargs:
                attempts.append({key: value for key, value in base_kwargs.items() if key != "variant"})
            if base_kwargs.get("use_safetensors"):
                attempts.append({**base_kwargs, "use_safetensors": False})
            if "variant" in base_kwargs:
                attempts.append(
                    {key: value for key, value in base_kwargs.items() if key not in ("variant", "use_safetensors")}
                    | {"use_safetensors": False}
                )

            pipe = None
            last_error: Exception | None = None
            for attempt in attempts:
                try:
                    pipe = pipeline_class.from_pretrained(model, **attempt)
                    break
                except Exception as exc:  # try the next compatibility fallback
                    last_error = exc
            if pipe is None:
                message = str(last_error or "unknown error")
                lowered = message.lower()
                hint = "检查模型 ID、网络与磁盘空间。国内网络可在设置中配置 HF_ENDPOINT 镜像。"
                if "gated" in lowered or "401" in lowered or "403" in lowered:
                    hint = "该模型需要先在 Hugging Face 接受许可并配置访问令牌，或改用 SD-Turbo / SDXL。"
                if "no such file" in lowered or "not found" in lowered:
                    hint = "模型不存在或下载不完整；也可以直接填写本地 Diffusers 文件夹路径。"
                raise EngineError(f"模型加载失败：{message[:320]}", code="model_load_failed", hint=hint) from last_error

            pipe.set_progress_bar_config(disable=True)
            if low_vram or (device == "cuda" and self._free_vram() is not None and self._free_vram() < 4500):
                try:
                    pipe.enable_attention_slicing("max")
                except Exception:
                    pass
                for method in ("enable_vae_slicing", "enable_vae_tiling"):
                    try:
                        getattr(pipe, method)()
                    except Exception:
                        pass
                try:
                    pipe.enable_sequential_cpu_offload()
                except Exception:
                    try:
                        pipe.enable_model_cpu_offload()
                    except Exception:
                        pipe.to(device)
            else:
                pipe.to(device)

            self._pipelines[key] = pipe
            self._loaded_key = key
            clear_gpu_cache()
            return pipe

    @staticmethod
    def _free_vram() -> int | None:
        gpus = gpu_inventory()
        return gpus[0]["free_mb"] if gpus else None

    def _apply_scheduler(self, pipe: Any, scheduler: str, model: str) -> str:
        _, diffusers = self._imports()
        name, _ = scheduler_aliases(scheduler)
        if scheduler in ("auto", ""):
            name = "DPMSolverMultistepScheduler"
            if "turbo" in model.lower() or "schnell" in model.lower():
                name = "EulerAncestralDiscreteScheduler"
        scheduler_class = getattr(diffusers, name, None)
        if scheduler_class is None:
            return type(pipe.scheduler).__name__
        try:
            pipe.scheduler = scheduler_class.from_config(pipe.scheduler.config)
        except Exception:
            pass
        return type(pipe.scheduler).__name__

    def _unload(self) -> None:
        with self._lock:
            self._pipelines.clear()
            self._loaded_key = None
        gc.collect()
        try:
            torch, _ = self._imports()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except Exception:
            pass
        clear_gpu_cache()

    def generate(
        self,
        context: GenerationContext,
        provider: dict[str, Any],
        secrets: SecretStore,
        progress: ProgressCallback,
        cancelled: CancelCheck,
    ) -> list[GeneratedImage]:
        torch, diffusers = self._imports()
        device = self._device(provider)
        model = context.extra.get("model") or provider.get("model") or "stabilityai/sd-turbo"
        options = provider.get("options", {})
        unload_after = bool(options.get("unload_after_generate", context.low_vram))
        free = self._free_vram()
        if device == "cuda" and free is not None and free < 650:
            raise EngineError(
                f"可用显存仅 {free} MB，无法安全加载模型",
                code="insufficient_vram",
                hint="关闭其他占用显存的 AI 程序，或在「模型」页切换 CPU 模式 / ComfyUI / 云端引擎。",
                status_code=412,
            )
        if context.mode == "img2img" and context.init_image is None:
            raise EngineError("图生图需要提供参考图片", code="missing_init_image", status_code=422)

        progress(0.03, "检查显存并加载模型")
        pipe = self._load_pipeline(provider, model, context.mode, context.low_vram)
        scheduler_name = self._apply_scheduler(pipe, context.scheduler, model)
        steps = context.steps
        guidance = context.guidance
        if "turbo" in model.lower() or "schnell" in model.lower():
            guidance = min(guidance, 1.0)
        progress(0.12, f"模型已加载 · {scheduler_name}")

        outputs: list[GeneratedImage] = []
        base_seed = context.seed
        signal = {"value": 0.12}

        def on_step_end(_pipe: Any, step: int, _timestep: Any, callback_kwargs: dict[str, Any]) -> dict[str, Any]:
            self.check_cancel(cancelled)
            effective = max(1, int(steps * (context.strength if context.mode == "img2img" else 1.0)))
            fraction = min(1.0, (step + 1) / effective)
            signal["value"] = 0.12 + (fraction * 0.72) / context.batch_size
            progress(min(0.86, signal["value"]), f"采样 {step + 1}/{effective}")
            return callback_kwargs

        supports_callback = "callback_on_step_end" in inspect.signature(pipe.__call__).parameters
        try:
            for index in range(context.batch_size):
                self.check_cancel(cancelled)
                image_seed = (base_seed + index) & 0xFFFFFFFF
                generator = torch.Generator(device=device).manual_seed(image_seed)
                kwargs: dict[str, Any] = {
                    "prompt": context.prompt,
                    "num_inference_steps": steps,
                    "guidance_scale": guidance,
                    "generator": generator,
                }
                if context.negative_prompt:
                    kwargs["negative_prompt"] = context.negative_prompt
                if context.mode == "img2img":
                    image = context.init_image
                    assert image is not None
                    kwargs["image"] = image.convert("RGB").resize((context.width, context.height))
                    kwargs["strength"] = context.strength
                else:
                    kwargs["width"] = context.width
                    kwargs["height"] = context.height
                if supports_callback:
                    kwargs["callback_on_step_end"] = on_step_end
                with torch.inference_mode():
                    result = pipe(**kwargs)
                outputs.append(
                    GeneratedImage(
                        image=result.images[0],
                        seed=image_seed,
                        meta={
                            "device": device,
                            "dtype": str(pipe.dtype).replace("torch.", ""),
                            "scheduler": scheduler_name,
                            "low_vram": context.low_vram,
                            "model": model,
                            "unload_after": unload_after,
                        },
                    )
                )
                progress(0.12 + ((index + 1) / context.batch_size) * 0.78, f"完成 {index + 1}/{context.batch_size}")
        except EngineError:
            raise
        except Exception as exc:
            message = str(exc)
            if "out of memory" in message.lower() or "cuda error" in message.lower():
                self._unload()
                raise EngineError(
                    "显存不足，模型加载或采样被中断",
                    code="vram_oom",
                    hint="启用「低显存模式」、把分辨率降到 512、关闭其他 AI 程序，或改用 ComfyUI/云端引擎。",
                    status_code=412,
                ) from exc
            raise EngineError(f"本地生成失败：{message[:400]}", code="local_generation_failed") from exc
        finally:
            if unload_after:
                progress(0.9, "释放模型与显存")
                self._unload()
        return outputs

    def list_models(self, provider: dict[str, Any], secrets: SecretStore) -> list[str]:
        return [item["id"] for item in LOCAL_MODEL_CATALOG]

    def test_connection(self, provider: dict[str, Any], secrets: SecretStore) -> dict[str, Any]:
        state = self.availability(provider, secrets)
        gpus = gpu_inventory()
        free = gpus[0]["free_mb"] if gpus else None
        return {
            "ok": state.available,
            "message": state.reason,
            "detail": state.detail,
            "free_vram_mb": free,
            "models": [item["id"] for item in LOCAL_MODEL_CATALOG] if state.available else [],
        }
