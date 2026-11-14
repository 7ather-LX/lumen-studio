from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from backend.config import SettingsStore
from backend.db import Database
from backend.engines.base import EngineError, GenerationContext
from backend.engines.registry import get_engine
from backend.schemas import GenerateRequest
from backend.security import SecretStore
from backend.services.image_store import ImageStore
from backend.services.learning import LearningService
from backend.services.providers import ProviderService
from backend.utils.dimensions import resolve_dimensions
from backend.utils.prompts import compose_negative, compose_prompt, model_defaults
from backend.utils.system import gpu_inventory, hardware_profile


@dataclass
class PreparedGeneration:
    request: GenerateRequest
    provider: dict[str, Any]
    model: str
    width: int
    height: int
    size_note: str
    prompt: str
    negative_prompt: str
    steps: int
    guidance: float
    scheduler: str
    style: str
    batch_size: int
    seed: int
    strength: float
    low_vram: bool
    tuning: dict[str, Any] | None
    warnings: list[str] = field(default_factory=list)
    init_image: Image.Image | None = None
    init_image_id: str | None = None
    upload_path: str | None = None
    started_at: float = 0.0
    free_vram_mb: int | None = None


class GenerationService:
    def __init__(
        self,
        db: Database,
        settings: SettingsStore,
        secrets: SecretStore,
        providers: ProviderService,
        images: ImageStore,
        learning: LearningService,
        version: str,
    ):
        self.db = db
        self.settings = settings
        self.secrets = secrets
        self.providers = providers
        self.images = images
        self.learning = learning
        self.version = version

    def _provider(self, request: GenerateRequest) -> dict[str, Any]:
        if request.provider_id:
            provider = self.db.get_provider(request.provider_id)
            if not provider:
                raise EngineError("选择的供应商不存在", code="provider_not_found", status_code=404)
        else:
            provider = next((item for item in self.db.list_providers() if item["is_default"]), None)
            if not provider:
                provider = self.db.get_provider(str(self.settings.get("default_provider_id", "demo")))
            if not provider:
                raise EngineError("没有可用的供应商，请先在模型页配置", code="no_provider", status_code=412)
        if not provider["enabled"]:
            raise EngineError("该供应商已停用", code="provider_disabled", status_code=412)
        return provider

    def prepare(self, request: GenerateRequest) -> PreparedGeneration:
        provider = self._provider(request)
        engine = get_engine(provider["kind"])
        availability = engine.availability(provider, self.secrets)
        if not availability.available:
            raise EngineError(
                availability.reason or "供应商不可用",
                code="engine_unavailable",
                hint=availability.detail,
                status_code=412,
            )
        if request.mode == "img2img" and not request.init_image and not request.init_image_id:
            raise EngineError("图生图需要提供参考图片", code="missing_init_image", status_code=422)

        model = (request.model or provider.get("model") or "").strip()
        if provider["kind"] == "diffusers":
            model = model or str(self.settings.get("local_engine.model", "stabilityai/sd-turbo"))
            if not model:
                raise EngineError("请选择本地模型", code="model_missing", status_code=412)

        size = resolve_dimensions(
            aspect_ratio=request.aspect_ratio,
            long_edge=request.long_edge,
            width=request.width,
            height=request.height,
            max_pixels=int(self.settings.get("max_pixels", 4_194_304)),
        )
        warnings: list[str] = []
        if size.note:
            warnings.append(size.note)

        gpus = gpu_inventory()
        free_vram = gpus[0]["free_mb"] if gpus else None
        profile = hardware_profile(free_vram)
        local_low = bool(self.settings.get("local_engine.low_vram", True))
        low_vram = bool(provider["kind"] == "diffusers" and local_low and (free_vram is None or free_vram < 5200))
        if provider["kind"] == "diffusers" and free_vram is not None and free_vram < 1800:
            warnings.append(f"仅剩 {free_vram} MB 显存；建议使用 SD-Turbo 512 或先释放其他 AI 程序")
        if provider["kind"] == "diffusers" and size.width * size.height > 1_048_576 and free_vram is not None and free_vram < 3800:
            warnings.append("当前显存低于 3.8 GB，高分辨率可能触发显存不足")
        if provider["kind"] == "diffusers" and "xl" in model.lower() and free_vram is not None and free_vram < 3800:
            warnings.append("SDXL 在低显存下会启用顺序 CPU 卸载，速度明显变慢；SD-Turbo 更轻量")

        default_steps, default_guidance = model_defaults(model)
        settings_steps = self.settings.get("default_steps")
        settings_guidance = self.settings.get("default_guidance")
        steps = int(request.steps or settings_steps or default_steps)
        guidance = float(
            request.guidance if request.guidance is not None else (settings_guidance if settings_guidance is not None else default_guidance)
        )
        scheduler = request.scheduler or str(self.settings.get("default_scheduler", "auto"))
        tuning: dict[str, Any] | None = None
        learned_positive: list[str] = []
        learned_negative: list[str] = []

        if request.auto_tune and self.settings.get("adaptive_enabled", True):
            suggestion = self.learning.suggest(
                prompt=request.prompt,
                negative_prompt=request.negative_prompt,
                style=request.style,
                width=size.width,
                height=size.height,
                provider_id=provider["id"],
                model=model,
                mode=request.mode,
                strength=request.strength,
            )
            if suggestion:
                tuning = dict(suggestion)
                applied = {"steps": False, "guidance": False, "scheduler": False}
                if request.steps is None:
                    steps = int(suggestion["steps"])
                    applied["steps"] = True
                if request.guidance is None:
                    guidance = float(suggestion["guidance"])
                    applied["guidance"] = True
                if request.scheduler in ("", "auto"):
                    scheduler = str(suggestion["scheduler"])
                    applied["scheduler"] = True
                tuning["applied"] = applied
                tuning["source"] = "local_preference_model"
            if self.settings.get("adaptive_prompt", True):
                learned_positive, learned_negative = self.learning.learned_prompt_additions()

        prompt = compose_prompt(request.prompt, request.style, learned_positive, request.enhance_prompt)
        negative = compose_negative(request.negative_prompt, request.style, learned_negative)
        if learned_positive:
            warnings.append("提示词已融入学习到的偏好片段")
        if tuning and tuning.get("explore"):
            warnings.append("本次采用探索性参数，用于收集新的偏好数据")

        init_image = None
        init_image_id = request.init_image_id
        upload_path = None
        if request.mode == "img2img":
            from backend.utils.images import decode_data_url

            decoded = decode_data_url(request.init_image) if request.init_image else None
            try:
                init_image, init_image_id, upload_path = self.images.load_init(request.init_image_id, decoded)
            except ValueError as exc:
                raise EngineError(str(exc), code="invalid_init_image", status_code=422) from exc
            if init_image is None:
                raise EngineError("参考图片读取失败", code="invalid_init_image", status_code=422)

        import secrets as pysecrets

        seed = request.seed if request.seed >= 0 else int.from_bytes(pysecrets.token_bytes(4), "little")
        batch_size = max(1, min(int(self.settings.get("max_batch", 4)), request.batch_size))
        return PreparedGeneration(
            request=request,
            provider=provider,
            model=model,
            width=size.width,
            height=size.height,
            size_note=size.note,
            prompt=prompt,
            negative_prompt=negative,
            steps=steps,
            guidance=guidance,
            scheduler=scheduler,
            style=request.style,
            batch_size=batch_size,
            seed=seed,
            strength=request.strength,
            low_vram=low_vram,
            tuning=tuning,
            warnings=list(dict.fromkeys(warnings)),
            init_image=init_image,
            init_image_id=init_image_id,
            upload_path=upload_path,
            started_at=time.time(),
            free_vram_mb=free_vram,
        )

    def generate(
        self,
        prepared: PreparedGeneration,
        progress,
        cancelled,
    ) -> dict[str, Any]:
        context = GenerationContext(
            prompt=prepared.prompt,
            negative_prompt=prepared.negative_prompt,
            width=prepared.width,
            height=prepared.height,
            steps=prepared.steps,
            guidance=prepared.guidance,
            seed=prepared.seed,
            batch_size=prepared.batch_size,
            scheduler=prepared.scheduler,
            style=prepared.style,
            mode=prepared.request.mode,
            strength=prepared.strength,
            init_image=prepared.init_image,
            init_image_name="lumen-init.png",
            low_vram=prepared.low_vram,
            extra={"model": prepared.model},
        )
        engine = get_engine(prepared.provider["kind"])
        started = time.perf_counter()

        def engine_progress(value: float, stage: str) -> None:
            progress(min(0.9, 0.08 + max(0.0, value) * 0.82), stage)

        progress(0.04, "预检硬件与提示词")
        results = engine.generate(context, prepared.provider, self.secrets, engine_progress, cancelled)
        elapsed = int((time.perf_counter() - started) * 1000)
        if not results:
            raise EngineError("引擎没有返回任何图片", code="empty_result")
        records = []
        for index, result in enumerate(results):
            if cancelled():
                raise EngineError("任务已取消", code="cancelled", status_code=409)
            progress(0.92 + index * 0.02, f"分析并保存 {index + 1}/{len(results)}")
            actual_width, actual_height = result.image.size
            params = {
                "app_version": self.version,
                "provider_kind": prepared.provider["kind"],
                "requested_width": prepared.request.width,
                "requested_height": prepared.request.height,
                "actual_width": actual_width,
                "actual_height": actual_height,
                "resolved_prompt": prepared.prompt,
                "resolved_negative": prepared.negative_prompt,
                "tuning": prepared.tuning,
                "warnings": prepared.warnings,
                "low_vram": prepared.low_vram,
                "free_vram_mb": prepared.free_vram_mb,
                "size_note": prepared.size_note,
                "engine_meta": result.meta,
            }
            record = self.images.save_generated(
                result.image,
                prompt=prepared.request.prompt,
                negative_prompt=prepared.request.negative_prompt,
                resolved_prompt=prepared.prompt,
                resolved_negative=prepared.negative_prompt,
                mode=prepared.request.mode,
                provider=prepared.provider,
                model=prepared.model,
                width=actual_width,
                height=actual_height,
                steps=prepared.steps,
                guidance=prepared.guidance,
                seed=result.seed,
                strength=prepared.strength if prepared.request.mode == "img2img" else 0.0,
                scheduler=prepared.scheduler,
                style=prepared.style,
                init_image_id=prepared.init_image_id,
                batch_index=index,
                generation_ms=elapsed,
                params=params,
            )
            records.append(record)
        for record in records:
            record["file_url"] = f"/api/images/{record['id']}/file"
            record["thumb_url"] = f"/api/images/{record['id']}/file?thumb=1"
        if prepared.upload_path and not self.settings.get("privacy.keep_init_uploads", True):
            try:
                from pathlib import Path

                Path(prepared.upload_path).unlink(missing_ok=True)
            except OSError:
                pass
        progress(0.99, "完成")
        return {
            "image_ids": [record["id"] for record in records],
            "images": records,
            "tuning": prepared.tuning,
            "warnings": prepared.warnings,
            "resolved_prompt": prepared.prompt,
            "resolved_negative": prepared.negative_prompt,
            "low_vram": prepared.low_vram,
            "provider_id": prepared.provider["id"],
            "provider_name": prepared.provider["name"],
            "model": prepared.model,
            "steps": prepared.steps,
            "guidance": prepared.guidance,
            "scheduler": prepared.scheduler,
            "seed": prepared.seed,
            "width": prepared.width,
            "height": prepared.height,
            "generation_ms": elapsed,
        }
