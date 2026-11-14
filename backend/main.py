from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.background import BackgroundTask

from backend import __version__
from backend.config import APP_NAME, SettingsStore
from backend.db import Database
from backend.engines.base import EngineError
from backend.engines.diffusers_engine import LOCAL_MODEL_CATALOG
from backend.engines.registry import KIND_LABELS
from backend.schemas import CropRequest, FeedbackRequest, GenerateRequest, ImagePatch, ProviderUpsert, RuntimeInstallRequest
from backend.security import SecretStore
from backend.services.generation import GenerationService
from backend.services.image_store import ImageStore
from backend.services.jobs import JobManager
from backend.services.learning import LearningService
from backend.services.providers import ProviderService
from backend.services.runtime import RuntimeService
from backend.utils.dimensions import ASPECT_PRESETS
from backend.utils.prompts import SCHEDULER_PRESETS, STYLE_PRESETS, compose_prompt
from backend.utils.system import gpu_inventory

logger = logging.getLogger("lumen")


def default_data_dir() -> Path:
    configured = os.environ.get("LUMEN_DATA_DIR")
    if configured:
        return Path(configured)
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "Lumen Studio"


class AppState:
    def __init__(self, data_dir: Path, token: str | None):
        self.data_dir = data_dir
        self.token = token or ""
        self.started_at = time.time()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "logs").mkdir(parents=True, exist_ok=True)
        self.settings = SettingsStore(self.data_dir)
        self.db = Database(self.data_dir)
        self.secrets = SecretStore(self.data_dir)
        self.learning = LearningService(self.db, self.data_dir, self.settings)
        self.images = ImageStore(self.db, self.data_dir, self.settings, self.learning)
        self.providers = ProviderService(self.db, self.secrets)
        self.runtime = RuntimeService(self.db, self.settings, self.secrets, self.data_dir)
        self.generation = GenerationService(
            self.db,
            self.settings,
            self.secrets,
            self.providers,
            self.images,
            self.learning,
            os.environ.get("LUMEN_VERSION", __version__),
        )
        self.jobs = JobManager(self.db, self.generation)


def configure_logging(data_dir: Path) -> None:
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if getattr(root, "_lumen_configured", False):
        return
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    root.addHandler(stream)
    try:
        from logging.handlers import RotatingFileHandler

        file_handler = RotatingFileHandler(log_dir / "backend.log", maxBytes=4_000_000, backupCount=2, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        pass
    root._lumen_configured = True  # type: ignore[attr-defined]


def _authorized(request: Request, state: AppState) -> bool:
    if not state.token:
        return True
    supplied = request.headers.get("x-lumen-token") or request.query_params.get("token")
    return bool(supplied and supplied == state.token)


def create_app(data_dir: Path | str | None = None, token: str | None = None) -> FastAPI:
    resolved_dir = Path(data_dir) if data_dir else default_data_dir()
    state = AppState(resolved_dir, token or os.environ.get("LUMEN_TOKEN"))
    configure_logging(resolved_dir)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        logger.info("Lumen backend %s starting in %s", __version__, resolved_dir)
        state.images.prune_uploads()
        yield
        state.jobs.shutdown()
        logger.info("Lumen backend stopped")

    app = FastAPI(
        title="Lumen Studio API",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.lumen = state
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        if request.url.path.startswith("/api/") and not _authorized(request, state):
            return JSONResponse({"detail": "未授权的本地请求", "code": "unauthorized"}, status_code=401)
        return await call_next(request)

    @app.exception_handler(EngineError)
    async def engine_error_handler(_request: Request, exc: EngineError):
        return JSONResponse(
            {"detail": exc.message, "code": exc.code, "hint": exc.hint},
            status_code=exc.status_code,
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError):
        return JSONResponse({"detail": str(exc), "code": "invalid_request"}, status_code=400)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError):
        errors = exc.errors()
        first = errors[0] if errors else {}
        location = ".".join(str(part) for part in first.get("loc", []) if part != "body")
        message = first.get("msg", "请求参数无效")
        return JSONResponse(
            {"detail": f"{location}: {message}" if location else message, "code": "validation_error", "errors": errors},
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(_request: Request, exc: Exception):
        logger.exception("unhandled API error")
        return JSONResponse(
            {"detail": f"内部错误：{str(exc)[:240]}", "code": "internal_error"},
            status_code=500,
        )

    # ------------------------------------------------------------------ health
    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "app": APP_NAME,
            "version": __version__,
            "data_dir": str(resolved_dir),
            "token_required": bool(state.token),
            "uptime": round(time.time() - state.started_at, 1),
        }

    @app.post("/api/shutdown")
    async def shutdown() -> dict[str, Any]:
        def exit_process() -> None:
            time.sleep(0.25)
            os._exit(0)

        threading.Thread(target=exit_process, daemon=True).start()
        return {"ok": True}

    # ------------------------------------------------------------------ system
    @app.get("/api/system")
    async def system() -> dict[str, Any]:
        data = state.runtime.status()
        data["stats"] = state.db.stats()
        return data

    @app.get("/api/stats")
    async def stats() -> dict[str, Any]:
        data = state.db.stats()
        images_size = 0
        for directory in (state.images.images_dir, state.images.thumbs_dir):
            try:
                images_size += sum(item.stat().st_size for item in directory.glob("*") if item.is_file())
            except OSError:
                pass
        data["storage_mb"] = round(images_size / (1024**2), 1)
        return data

    @app.get("/api/meta/presets")
    async def presets() -> dict[str, Any]:
        gpus = gpu_inventory()
        return {
            "app": {"name": APP_NAME, "version": __version__},
            "styles": [{key: item[key] for key in ("id", "label", "accent")} for item in STYLE_PRESETS],
            "aspects": ASPECT_PRESETS,
            "schedulers": SCHEDULER_PRESETS,
            "provider_kinds": [
                {"id": key, "label": value} for key, value in KIND_LABELS.items()
            ],
            "local_models": LOCAL_MODEL_CATALOG,
            "hardware": {
                "detected": gpus,
                "tiers": [
                    {
                        "id": "minimum",
                        "label": "最低配置",
                        "cpu": "4 核现代 CPU",
                        "ram": "16 GB",
                        "gpu": "无独显也可（CPU，速度慢）",
                        "vram": "—",
                        "experience": "SD 1.5 / SD-Turbo 512，约 1–5 分钟/张",
                    },
                    {
                        "id": "recommended",
                        "label": "推荐配置",
                        "cpu": "6 核以上",
                        "ram": "32 GB",
                        "gpu": "NVIDIA RTX 3060 12 GB / 4070 12 GB 或同级",
                        "vram": "8–12 GB",
                        "experience": "SDXL 1024 或 SD-Turbo 快速出图",
                    },
                    {
                        "id": "shared",
                        "label": "与其他 AI 共用显卡",
                        "cpu": "6 核以上",
                        "ram": "32 GB",
                        "gpu": "剩余显存 ≥ 2 GB",
                        "vram": "2–6 GB 可用",
                        "experience": "低显存模式：SD-Turbo 512 + 顺序卸载，生成后自动释放",
                    },
                    {
                        "id": "comfortable",
                        "label": "舒适配置",
                        "cpu": "8 核以上",
                        "ram": "64 GB",
                        "gpu": "RTX 4080 / 4090 16–24 GB",
                        "vram": "16 GB+",
                        "experience": "FLUX / SD 3.5 / SDXL 高分辨率",
                    },
                ],
            },
        }

    # ----------------------------------------------------------------- settings
    @app.get("/api/settings")
    async def get_settings() -> dict[str, Any]:
        return state.settings.all()

    @app.patch("/api/settings")
    async def patch_settings(patch: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "default_provider_id",
            "default_aspect",
            "default_long_edge",
            "default_steps",
            "default_guidance",
            "default_scheduler",
            "auto_analyze",
            "adaptive_enabled",
            "adaptive_prompt",
            "auto_tune_default",
            "max_pixels",
            "max_batch",
            "local_engine",
            "comfyui",
            "privacy",
            "ui",
        }
        unknown = [key for key in patch if key not in allowed]
        if unknown:
            raise ValueError(f"未知设置项：{', '.join(unknown)}")
        if "max_pixels" in patch:
            pixels = int(patch["max_pixels"])
            if pixels < 262_144 or pixels > 4_194_304:
                raise ValueError("max_pixels 必须在 262144 到 4194304 之间")
        if "max_batch" in patch:
            batch = int(patch["max_batch"])
            if batch < 1 or batch > 4:
                raise ValueError("max_batch 必须在 1 到 4 之间")
        return state.settings.update(patch)

    # ---------------------------------------------------------------- providers
    @app.get("/api/providers")
    async def list_providers() -> list[dict[str, Any]]:
        return state.providers.list()

    @app.post("/api/providers")
    async def create_provider(payload: ProviderUpsert) -> dict[str, Any]:
        return state.providers.upsert(payload)

    @app.put("/api/providers/{provider_id}")
    async def update_provider(provider_id: str, payload: ProviderUpsert) -> dict[str, Any]:
        payload.id = provider_id
        return state.providers.upsert(payload)

    @app.delete("/api/providers/{provider_id}")
    async def delete_provider(provider_id: str) -> dict[str, Any]:
        ok, message = state.providers.delete(provider_id)
        if not ok:
            raise ValueError(message)
        return {"ok": True, "message": message}

    @app.post("/api/providers/{provider_id}/test")
    async def test_provider(provider_id: str) -> dict[str, Any]:
        return state.providers.test(provider_id)

    @app.get("/api/providers/{provider_id}/models")
    async def provider_models(provider_id: str) -> dict[str, Any]:
        return {"models": state.providers.models(provider_id)}

    @app.post("/api/providers/{provider_id}/default")
    async def set_default_provider(provider_id: str) -> dict[str, Any]:
        state.providers.set_default(provider_id)
        return {"ok": True}

    # ----------------------------------------------------------------- runtime
    @app.get("/api/runtime")
    async def runtime_status() -> dict[str, Any]:
        return state.runtime.status()

    @app.post("/api/runtime/install")
    async def install_runtime(payload: RuntimeInstallRequest) -> dict[str, Any]:
        return state.runtime.start_install(payload.variant)

    @app.post("/api/runtime/cancel-install")
    async def cancel_install() -> dict[str, Any]:
        return state.runtime.cancel_install()

    @app.get("/api/runtime/models")
    async def local_models() -> dict[str, Any]:
        return {"models": state.runtime.local_models()}

    # ---------------------------------------------------------------- generate
    @app.post("/api/generate")
    async def generate(payload: GenerateRequest) -> dict[str, Any]:
        return state.jobs.submit(payload)

    @app.get("/api/jobs")
    async def list_jobs(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
        return {"items": state.jobs.list(limit)}

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str) -> dict[str, Any]:
        job = state.jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="任务不存在")
        return job

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str) -> dict[str, Any]:
        return state.jobs.cancel(job_id)

    # ------------------------------------------------------------------ images
    @app.get("/api/images")
    async def list_images(
        limit: int = Query(default=60, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        favorite: bool | None = None,
        mode: str | None = None,
        search: str | None = None,
        min_rating: int | None = Query(default=None, ge=1, le=5),
        sort: str = "newest",
    ) -> dict[str, Any]:
        data = state.db.list_images(
            limit=limit,
            offset=offset,
            favorite=favorite,
            mode=mode,
            search=search,
            min_rating=min_rating,
            sort=sort,
        )
        for item in data["items"]:
            item["file_url"] = f"/api/images/{item['id']}/file"
            item["thumb_url"] = f"/api/images/{item['id']}/file?thumb=1"
        return data

    @app.get("/api/images/{image_id}")
    async def get_image(image_id: str) -> dict[str, Any]:
        image = state.db.get_image(image_id)
        if not image:
            raise HTTPException(status_code=404, detail="图片不存在")
        image["file_url"] = f"/api/images/{image_id}/file"
        image["thumb_url"] = f"/api/images/{image_id}/file?thumb=1"
        return image

    @app.get("/api/images/{image_id}/file")
    async def image_file(image_id: str, thumb: bool = False, download: bool = False):
        image = state.db.get_image(image_id)
        if not image:
            raise HTTPException(status_code=404, detail="图片不存在")
        relative = image["thumb"] if thumb else image["file"]
        try:
            path = state.images.resolve(relative)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="非法文件路径") from exc
        if not path.exists():
            raise HTTPException(status_code=404, detail="图片文件缺失")
        stat = path.stat()
        etag = f'"{int(stat.st_mtime)}-{stat.st_size}-{image_id}-{int(thumb)}"'
        headers = {"Cache-Control": "private, max-age=3600", "ETag": etag}
        if thumb:
            media_type = "image/webp"
        else:
            media_type = image.get("mime") or "image/png"
        filename = f"lumen-{image_id}.webp" if thumb else f"lumen-{image_id}.png"
        return FileResponse(
            path,
            media_type=media_type,
            filename=filename if download else None,
            headers=headers,
            content_disposition_type="attachment" if download else "inline",
        )

    @app.post("/api/images/{image_id}/crop")
    async def crop_image(image_id: str, payload: CropRequest) -> dict[str, Any]:
        if payload.x + payload.width > 1.0001 or payload.y + payload.height > 1.0001:
            raise HTTPException(status_code=422, detail="裁切区域超出图片范围")
        try:
            record = state.images.crop(image_id, payload.x, payload.y, payload.width, payload.height)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not record:
            raise HTTPException(status_code=404, detail="图片不存在")
        record["file_url"] = f"/api/images/{record['id']}/file"
        record["thumb_url"] = f"/api/images/{record['id']}/file?thumb=1"
        return record

    @app.get("/api/images/{image_id}/reveal")
    async def reveal_image(image_id: str) -> dict[str, Any]:
        path = state.images.reveal(image_id)
        if not path:
            raise HTTPException(status_code=404, detail="图片文件不存在")
        return {"path": path}

    @app.patch("/api/images/{image_id}")
    async def patch_image(image_id: str, payload: ImagePatch) -> dict[str, Any]:
        image = state.db.get_image(image_id)
        if not image:
            raise HTTPException(status_code=404, detail="图片不存在")
        patch = payload.model_dump(exclude_none=True)
        updated = state.db.update_image(image_id, patch)
        state.learning.sync_feedback(image_id)
        if updated:
            updated["file_url"] = f"/api/images/{image_id}/file"
            updated["thumb_url"] = f"/api/images/{image_id}/file?thumb=1"
        return updated or {}

    @app.post("/api/images/{image_id}/feedback")
    async def feedback(image_id: str, payload: FeedbackRequest) -> dict[str, Any]:
        image = state.db.get_image(image_id)
        if not image:
            raise HTTPException(status_code=404, detail="图片不存在")
        patch: dict[str, Any] = {}
        if payload.rating is not None:
            patch["rating"] = None if payload.rating == 0 else payload.rating
        if payload.favorite is not None:
            patch["favorite"] = payload.favorite
        if payload.notes is not None:
            patch["notes"] = payload.notes
        if payload.tags is not None:
            patch["tags"] = payload.tags
        state.db.update_image(image_id, patch)
        state.learning.sync_feedback(image_id)
        updated = state.db.get_image(image_id)
        if updated:
            updated["file_url"] = f"/api/images/{image_id}/file"
            updated["thumb_url"] = f"/api/images/{image_id}/file?thumb=1"
        return {"image": updated, "feedback_count": state.db.feedback_count()}

    @app.delete("/api/images/{image_id}")
    async def delete_image(image_id: str) -> dict[str, Any]:
        ok = state.images.delete(image_id)
        if not ok:
            raise HTTPException(status_code=404, detail="图片不存在")
        return {"ok": True}

    # ----------------------------------------------------------------- learning
    @app.get("/api/learning/insights")
    async def learning_insights() -> dict[str, Any]:
        return state.learning.insights()

    @app.post("/api/learning/train")
    async def train_learning() -> dict[str, Any]:
        model = state.learning.train(force=True)
        return {"ok": model is not None, "model": model, "insights": state.learning.insights()}

    @app.post("/api/learning/reset")
    async def reset_learning() -> dict[str, Any]:
        state.learning.reset()
        return {"ok": True}

    @app.post("/api/prompt/enhance")
    async def enhance_prompt(payload: dict[str, Any]) -> dict[str, Any]:
        prompt = str(payload.get("prompt") or "")[:6000]
        style = str(payload.get("style") or "none")
        enhance = bool(payload.get("enhance", True))
        positive, negative = state.learning.learned_prompt_additions()
        composed = compose_prompt(prompt, style, positive, enhance)
        return {
            "prompt": composed,
            "added_style": bool(style and style != "none"),
            "learned_tokens": positive,
            "learned_negative": negative,
        }

    # ------------------------------------------------------------------- export
    @app.get("/api/export/library")
    async def export_library():
        import json
        import tempfile

        data = state.db.list_images(limit=200, offset=0)
        handle, temp_name = tempfile.mkstemp(prefix="lumen-library-", suffix=".json")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(
                {"version": __version__, "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "images": data["items"]},
                stream,
                ensure_ascii=False,
                indent=2,
            )

        def cleanup() -> None:
            try:
                os.unlink(temp_name)
            except OSError:
                pass

        return FileResponse(
            temp_name,
            media_type="application/json",
            filename="lumen-library.json",
            background=BackgroundTask(cleanup),
        )

    return app
