from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS providers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    base_url TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    is_default INTEGER NOT NULL DEFAULT 0,
    options TEXT NOT NULL DEFAULT '{}',
    secret_cipher TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS images (
    id TEXT PRIMARY KEY,
    file TEXT NOT NULL,
    thumb TEXT NOT NULL,
    mime TEXT NOT NULL DEFAULT 'image/png',
    prompt TEXT NOT NULL,
    negative_prompt TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL DEFAULT 'txt2img',
    provider_id TEXT NOT NULL DEFAULT '',
    provider_name TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    steps INTEGER NOT NULL DEFAULT 0,
    guidance REAL NOT NULL DEFAULT 0,
    seed INTEGER NOT NULL DEFAULT 0,
    strength REAL NOT NULL DEFAULT 0,
    scheduler TEXT NOT NULL DEFAULT 'auto',
    style TEXT NOT NULL DEFAULT 'none',
    init_image_id TEXT,
    batch_index INTEGER NOT NULL DEFAULT 0,
    favorite INTEGER NOT NULL DEFAULT 0,
    rating INTEGER,
    notes TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    analysis TEXT NOT NULL DEFAULT '{}',
    params TEXT NOT NULL DEFAULT '{}',
    generation_ms INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_images_created ON images(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_images_favorite ON images(favorite, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_images_rating ON images(rating);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    stage TEXT NOT NULL DEFAULT '排队中',
    request TEXT NOT NULL,
    result TEXT,
    error TEXT,
    provider_id TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id TEXT NOT NULL UNIQUE,
    reward REAL NOT NULL,
    features TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prompt_recipes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    prompt TEXT NOT NULL,
    negative_prompt TEXT NOT NULL DEFAULT '',
    style TEXT NOT NULL DEFAULT 'none',
    params TEXT NOT NULL DEFAULT '{}',
    uses INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    avg_rating REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_id(prefix: str = "") -> str:
    value = uuid.uuid4().hex
    return f"{prefix}{value}" if prefix else value


def parse_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


class Database:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.path = data_dir / "lumen.db"
        self._init_lock = threading.Lock()
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._init_lock:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with self.connection() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("PRAGMA synchronous = NORMAL")
                connection.executescript(SCHEMA)
                connection.execute(
                    "UPDATE jobs SET status='failed', error=?, finished_at=? WHERE status IN ('queued','running')",
                    ("应用重启，任务已中断", utcnow()),
                )
            self.seed_providers()

    def seed_providers(self) -> None:
        now = utcnow()
        defaults = [
            {
                "id": "local-diffusers",
                "name": "本地 Diffusers",
                "kind": "diffusers",
                "base_url": "",
                "model": "stabilityai/sd-turbo",
                "enabled": 1,
                "is_default": 0,
                "options": {
                    "device": "auto",
                    "dtype": "auto",
                    "cpu_offload": True,
                    "allow_download": True,
                    "local_files_only": False,
                },
            },
            {
                "id": "comfyui",
                "name": "ComfyUI（本地 / 局域网）",
                "kind": "comfyui",
                "base_url": "http://127.0.0.1:8188",
                "model": "",
                "enabled": 1,
                "is_default": 0,
                "options": {"timeout": 420},
            },
            {
                "id": "openai",
                "name": "OpenAI Images",
                "kind": "openai",
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-image-1",
                "enabled": 0,
                "is_default": 0,
                "options": {"quality": "auto"},
            },
            {
                "id": "stability",
                "name": "Stability AI",
                "kind": "stability",
                "base_url": "https://api.stability.ai",
                "model": "sd3.5-large",
                "enabled": 0,
                "is_default": 0,
                "options": {},
            },
            {
                "id": "demo",
                "name": "离线示例引擎",
                "kind": "demo",
                "base_url": "",
                "model": "lumen-demo-v1",
                "enabled": 1,
                "is_default": 1,
                "options": {},
            },
        ]
        with self.connection() as connection:
            current = connection.execute("SELECT COUNT(*) AS n FROM providers").fetchone()["n"]
            if current:
                return
            for provider in defaults:
                connection.execute(
                    """INSERT INTO providers
                    (id,name,kind,base_url,model,enabled,is_default,options,secret_cipher,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,'',?,?)""",
                    (
                        provider["id"],
                        provider["name"],
                        provider["kind"],
                        provider["base_url"],
                        provider["model"],
                        provider["enabled"],
                        provider["is_default"],
                        json.dumps(provider["options"], ensure_ascii=False),
                        now,
                        now,
                    ),
                )

    # ------------------------------------------------------------------ providers
    def provider_row(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        data = dict(row)
        data["enabled"] = bool(data["enabled"])
        data["is_default"] = bool(data["is_default"])
        data["options"] = parse_json(data.get("options"), {})
        return data

    def list_providers(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM providers ORDER BY is_default DESC, created_at ASC"
            ).fetchall()
        return [self.provider_row(row) for row in rows if row is not None]  # type: ignore[misc]

    def get_provider(self, provider_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM providers WHERE id=?", (provider_id,)).fetchone()
        return self.provider_row(row)

    def upsert_provider(self, data: dict[str, Any]) -> dict[str, Any]:
        now = utcnow()
        with self.connection() as connection:
            existing = connection.execute("SELECT * FROM providers WHERE id=?", (data["id"],)).fetchone()
            if existing:
                connection.execute(
                    """UPDATE providers SET name=?, kind=?, base_url=?, model=?, enabled=?, is_default=?,
                    options=?, updated_at=? WHERE id=?""",
                    (
                        data["name"],
                        data["kind"],
                        data["base_url"],
                        data["model"],
                        1 if data["enabled"] else 0,
                        1 if data["is_default"] else 0,
                        json.dumps(data.get("options", {}), ensure_ascii=False),
                        now,
                        data["id"],
                    ),
                )
            else:
                connection.execute(
                    """INSERT INTO providers
                    (id,name,kind,base_url,model,enabled,is_default,options,secret_cipher,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,'',?,?)""",
                    (
                        data["id"],
                        data["name"],
                        data["kind"],
                        data["base_url"],
                        data["model"],
                        1 if data["enabled"] else 0,
                        1 if data["is_default"] else 0,
                        json.dumps(data.get("options", {}), ensure_ascii=False),
                        now,
                        now,
                    ),
                )
            if data.get("is_default"):
                connection.execute("UPDATE providers SET is_default=0 WHERE id<>?", (data["id"],))
        return self.get_provider(data["id"])  # type: ignore[return-value]

    def set_default_provider(self, provider_id: str) -> None:
        with self.connection() as connection:
            connection.execute("UPDATE providers SET is_default=0")
            connection.execute("UPDATE providers SET is_default=1 WHERE id=?", (provider_id,))

    def delete_provider(self, provider_id: str) -> bool:
        with self.connection() as connection:
            cursor = connection.execute("DELETE FROM providers WHERE id=? AND is_default=0", (provider_id,))
            return cursor.rowcount > 0

    # --------------------------------------------------------------------- images
    @staticmethod
    def image_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        data = dict(row)
        data["favorite"] = bool(data["favorite"])
        data["tags"] = parse_json(data.get("tags"), [])
        data["analysis"] = parse_json(data.get("analysis"), {})
        data["params"] = parse_json(data.get("params"), {})
        data["favorite"] = bool(data["favorite"])
        return data

    def insert_image(self, data: dict[str, Any]) -> dict[str, Any]:
        fields = [
            "id",
            "file",
            "thumb",
            "mime",
            "prompt",
            "negative_prompt",
            "mode",
            "provider_id",
            "provider_name",
            "model",
            "width",
            "height",
            "steps",
            "guidance",
            "seed",
            "strength",
            "scheduler",
            "style",
            "init_image_id",
            "batch_index",
            "favorite",
            "rating",
            "notes",
            "tags",
            "analysis",
            "params",
            "generation_ms",
            "created_at",
        ]
        values = []
        for field in fields:
            value = data.get(field)
            if field in ("tags", "analysis", "params"):
                value = json.dumps(value or ([] if field == "tags" else {}), ensure_ascii=False)
            elif field == "favorite":
                value = 1 if value else 0
            values.append(value)
        with self.connection() as connection:
            connection.execute(
                f"INSERT INTO images ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",
                values,
            )
        return self.get_image(data["id"])  # type: ignore[return-value]

    def get_image(self, image_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM images WHERE id=?", (image_id,)).fetchone()
        return self.image_row(row)

    def list_images(
        self,
        limit: int = 60,
        offset: int = 0,
        favorite: bool | None = None,
        mode: str | None = None,
        search: str | None = None,
        min_rating: int | None = None,
        sort: str = "newest",
    ) -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        if favorite is not None:
            clauses.append("favorite=?")
            params.append(1 if favorite else 0)
        if mode in ("txt2img", "img2img"):
            clauses.append("mode=?")
            params.append(mode)
        if search:
            clauses.append("(prompt LIKE ? OR notes LIKE ? OR tags LIKE ?)")
            needle = f"%{search}%"
            params.extend([needle, needle, needle])
        if min_rating:
            clauses.append("rating>=?")
            params.append(min_rating)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order = "created_at DESC"
        if sort == "oldest":
            order = "created_at ASC"
        elif sort == "rating":
            order = "COALESCE(rating,0) DESC, created_at DESC"
        with self.connection() as connection:
            total = connection.execute(f"SELECT COUNT(*) AS n FROM images {where}", params).fetchone()["n"]
            rows = connection.execute(
                f"SELECT * FROM images {where} ORDER BY {order} LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        return {
            "items": [self.image_row(row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def update_image(self, image_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        allowed = ["favorite", "rating", "notes", "tags"]
        fields: list[str] = []
        values: list[Any] = []
        for key in allowed:
            if key not in patch:
                continue
            value = patch[key]
            if key == "tags":
                value = json.dumps(value, ensure_ascii=False)
            elif key == "favorite":
                value = 1 if value else 0
            fields.append(f"{key}=?")
            values.append(value)
        if not fields:
            return self.get_image(image_id)
        values.append(image_id)
        with self.connection() as connection:
            connection.execute(f"UPDATE images SET {','.join(fields)} WHERE id=?", values)
        return self.get_image(image_id)

    def delete_image(self, image_id: str) -> dict[str, Any] | None:
        image = self.get_image(image_id)
        if not image:
            return None
        with self.connection() as connection:
            connection.execute("DELETE FROM feedback WHERE image_id=?", (image_id,))
            connection.execute("DELETE FROM images WHERE id=?", (image_id,))
        return image

    def recent_images(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.list_images(limit=limit)["items"]

    # ----------------------------------------------------------------------- jobs
    def insert_job(self, job: dict[str, Any]) -> None:
        with self.connection() as connection:
            connection.execute(
                """INSERT INTO jobs (id,status,progress,stage,request,result,error,provider_id,created_at,started_at,finished_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job["id"],
                    job["status"],
                    job.get("progress", 0),
                    job.get("stage", "排队中"),
                    json.dumps(job.get("request", {}), ensure_ascii=False),
                    None,
                    None,
                    job.get("provider_id"),
                    job["created_at"],
                    None,
                    None,
                ),
            )

    def job_row(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        data = dict(row)
        data["request"] = parse_json(data.get("request"), {})
        data["result"] = parse_json(data.get("result"), None)
        return data

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self.job_row(row)

    def update_job(self, job_id: str, **fields: Any) -> None:
        if not fields:
            return
        allowed = ["status", "progress", "stage", "result", "error", "started_at", "finished_at", "provider_id"]
        keys = [key for key in fields if key in allowed]
        if not keys:
            return
        values: list[Any] = []
        for key in keys:
            value = fields[key]
            if key == "result" and value is not None:
                value = json.dumps(value, ensure_ascii=False)
            values.append(value)
        values.append(job_id)
        with self.connection() as connection:
            connection.execute(f"UPDATE jobs SET {','.join(f'{key}=?' for key in keys)} WHERE id=?", values)

    def list_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self.job_row(row) for row in rows if row is not None]  # type: ignore[misc]

    # ------------------------------------------------------------------- feedback
    def upsert_feedback(self, image_id: str, reward: float, features: dict[str, float]) -> None:
        with self.connection() as connection:
            connection.execute(
                """INSERT INTO feedback (image_id,reward,features,created_at) VALUES (?,?,?,?)
                ON CONFLICT(image_id) DO UPDATE SET reward=excluded.reward, features=excluded.features, created_at=excluded.created_at""",
                (image_id, reward, json.dumps(features), utcnow()),
            )

    def delete_feedback(self, image_id: str) -> None:
        with self.connection() as connection:
            connection.execute("DELETE FROM feedback WHERE image_id=?", (image_id,))

    def feedback_rows(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT f.image_id, f.reward, f.features, f.created_at, i.rating, i.favorite,
                i.prompt, i.negative_prompt, i.style, i.steps, i.guidance, i.scheduler, i.width, i.height,
                i.provider_id, i.model, i.analysis, i.mode, i.strength, i.tags
                FROM feedback f JOIN images i ON i.id=f.image_id ORDER BY f.created_at ASC"""
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["features"] = parse_json(item["features"], {})
            item["analysis"] = parse_json(item["analysis"], {})
            item["tags"] = parse_json(item["tags"], [])
            item["favorite"] = bool(item["favorite"])
            result.append(item)
        return result

    def feedback_count(self) -> int:
        with self.connection() as connection:
            return int(connection.execute("SELECT COUNT(*) AS n FROM feedback").fetchone()["n"])

    # ---------------------------------------------------------------------- stats
    def stats(self) -> dict[str, Any]:
        with self.connection() as connection:
            row = connection.execute(
                """SELECT COUNT(*) AS images, COALESCE(AVG(rating),0) AS avg_rating,
                SUM(CASE WHEN favorite=1 THEN 1 ELSE 0 END) AS favorites,
                SUM(CASE WHEN rating IS NOT NULL THEN 1 ELSE 0 END) AS rated
                FROM images"""
            ).fetchone()
            jobs = connection.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"]
        data = dict(row)
        data["favorites"] = int(data["favorites"] or 0)
        data["jobs"] = int(jobs)
        data["feedback"] = self.feedback_count()
        return data

    # ---------------------------------------------------------------------- meta
    def get_meta(self, key: str, default: Any = None) -> Any:
        with self.connection() as connection:
            row = connection.execute("SELECT value FROM app_meta WHERE key=?", (key,)).fetchone()
        return parse_json(row["value"], default) if row else default

    def set_meta(self, key: str, value: Any) -> None:
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO app_meta (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value, ensure_ascii=False)),
            )
