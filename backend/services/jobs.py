from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from backend.db import Database, new_id, utcnow
from backend.engines.base import EngineError
from backend.schemas import GenerateRequest
from backend.services.generation import GenerationService

logger = logging.getLogger("lumen.jobs")


class JobManager:
    def __init__(self, db: Database, generation: GenerationService):
        self.db = db
        self.generation = generation
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lumen-generate")
        self._events: dict[str, threading.Event] = {}
        self._lock = threading.RLock()
        self._started = time.time()

    def submit(self, request: GenerateRequest) -> dict[str, Any]:
        prepared = self.generation.prepare(request)
        job_id = new_id("job_")
        event = threading.Event()
        with self._lock:
            self._events[job_id] = event
        payload = request.model_dump(exclude={"init_image"})
        payload["has_init_image"] = bool(request.init_image)
        self.db.insert_job(
            {
                "id": job_id,
                "status": "queued",
                "progress": 0,
                "stage": "排队中",
                "request": payload,
                "provider_id": prepared.provider["id"],
                "created_at": utcnow(),
            }
        )
        self.executor.submit(self._run, job_id, prepared, event)
        return {
            "job_id": job_id,
            "status": "queued",
            "provider_id": prepared.provider["id"],
            "provider_name": prepared.provider["name"],
            "width": prepared.width,
            "height": prepared.height,
            "steps": prepared.steps,
            "guidance": prepared.guidance,
            "tuning": prepared.tuning,
            "warnings": prepared.warnings,
        }

    def _run(self, job_id: str, prepared, event: threading.Event) -> None:
        if event.is_set():
            self.db.update_job(job_id, status="cancelled", stage="已取消", finished_at=utcnow())
            return
        self.db.update_job(job_id, status="running", stage="准备中", started_at=utcnow(), progress=0.01)
        last_update = {"time": 0.0, "progress": -1.0}

        def progress(value: float, stage: str) -> None:
            now = time.time()
            value = max(0.0, min(1.0, value))
            if now - last_update["time"] < 0.35 and abs(value - last_update["progress"]) < 0.02:
                return
            last_update["time"] = now
            last_update["progress"] = value
            self.db.update_job(job_id, progress=round(value, 3), stage=stage)

        try:
            result = self.generation.generate(prepared, progress, event.is_set)
            stored = {
                "image_ids": result["image_ids"],
                "tuning": result.get("tuning"),
                "warnings": result.get("warnings", []),
                "resolved_prompt": result.get("resolved_prompt"),
                "resolved_negative": result.get("resolved_negative"),
                "low_vram": result.get("low_vram"),
                "provider_id": result.get("provider_id"),
                "provider_name": result.get("provider_name"),
                "model": result.get("model"),
                "steps": result.get("steps"),
                "guidance": result.get("guidance"),
                "scheduler": result.get("scheduler"),
                "seed": result.get("seed"),
                "width": result.get("width"),
                "height": result.get("height"),
                "generation_ms": result.get("generation_ms"),
            }
            self.db.update_job(
                job_id,
                status="succeeded",
                progress=1.0,
                stage="完成",
                result=stored,
                finished_at=utcnow(),
            )
        except EngineError as exc:
            if exc.code == "cancelled":
                self.db.update_job(job_id, status="cancelled", stage="已取消", finished_at=utcnow())
            else:
                logger.warning("job %s failed: %s", job_id, exc.message)
                self.db.update_job(
                    job_id,
                    status="failed",
                    stage="失败",
                    error={"message": exc.message, "code": exc.code, "hint": exc.hint},
                    finished_at=utcnow(),
                )
        except Exception as exc:
            logger.exception("job %s crashed", job_id)
            self.db.update_job(
                job_id,
                status="failed",
                stage="失败",
                error={
                    "message": f"生成失败：{str(exc)[:300]}",
                    "code": "unexpected_error",
                    "hint": "查看应用日志获取更多信息。",
                },
                finished_at=utcnow(),
            )
        finally:
            with self._lock:
                self._events.pop(job_id, None)

    def cancel(self, job_id: str) -> dict[str, Any]:
        job = self.db.get_job(job_id)
        if not job:
            raise ValueError("任务不存在")
        if job["status"] in ("succeeded", "failed", "cancelled"):
            return {"ok": False, "message": "任务已结束", "status": job["status"]}
        with self._lock:
            event = self._events.get(job_id)
            if event:
                event.set()
        if job["status"] == "queued":
            self.db.update_job(job_id, status="cancelled", stage="已取消", finished_at=utcnow())
        return {"ok": True, "message": "已请求取消", "status": "cancelling"}

    def get(self, job_id: str, include_images: bool = True) -> dict[str, Any] | None:
        job = self.db.get_job(job_id)
        if not job:
            return None
        if include_images and job.get("result"):
            images = []
            for image_id in job["result"].get("image_ids", []):
                record = self.db.get_image(image_id)
                if record:
                    record["file_url"] = f"/api/images/{image_id}/file"
                    record["thumb_url"] = f"/api/images/{image_id}/file?thumb=1"
                    images.append(record)
            job["result"]["images"] = images
        job["queue_position"] = self._queue_position(job_id) if job["status"] == "queued" else 0
        return job

    def _queue_position(self, job_id: str) -> int:
        jobs = self.db.list_jobs(50)
        queued = [job for job in reversed(jobs) if job["status"] == "queued"]
        try:
            return queued.index(next(job for job in queued if job["id"] == job_id)) + 1
        except (StopIteration, ValueError):
            return 0

    def list(self, limit: int = 30) -> list[dict[str, Any]]:
        return self.db.list_jobs(limit)

    def shutdown(self) -> None:
        with self._lock:
            for event in self._events.values():
                event.set()
        self.executor.shutdown(wait=False, cancel_futures=True)
