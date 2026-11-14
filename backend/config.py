from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

APP_NAME = "Lumen Studio"
DEFAULT_SETTINGS: dict[str, Any] = {
    "default_provider_id": "demo",
    "default_aspect": "1:1",
    "default_long_edge": 1024,
    "default_steps": None,
    "default_guidance": None,
    "default_scheduler": "auto",
    "auto_analyze": True,
    "adaptive_enabled": True,
    "adaptive_prompt": True,
    "auto_tune_default": True,
    "max_pixels": 4_194_304,
    "max_batch": 4,
    "local_engine": {
        "device": "auto",
        "dtype": "auto",
        "cpu_offload": True,
        "low_vram": True,
        "unload_after_generate": True,
        "model": "stabilityai/sd-turbo",
        "hf_endpoint": "",
        "local_files_only": False,
    },
    "comfyui": {
        "timeout": 420,
        "sampler": "dpmpp_2m",
        "scheduler": "karras",
    },
    "assistant": {
        "enabled": False,
        "base_url": "http://127.0.0.1:8000/v1",
        "model": "",
        "timeout": 90,
    },
    "privacy": {
        "strip_png_metadata": False,
        "keep_init_uploads": True,
    },
    "ui": {
        "reduce_motion": False,
        "gallery_columns": 3,
    },
}


def deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class SettingsStore:
    """Small atomic JSON settings store."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.path = data_dir / "settings.json"
        self._lock = threading.RLock()
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            data = copy.deepcopy(DEFAULT_SETTINGS)
            self._write(data)
            return data
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(saved, dict):
                raise ValueError("settings root must be an object")
            return deep_merge(DEFAULT_SETTINGS, saved)
        except Exception:
            broken = self.path.with_suffix(".broken.json")
            try:
                self.path.replace(broken)
            except OSError:
                pass
            data = copy.deepcopy(DEFAULT_SETTINGS)
            self._write(data)
            return data

    def _write(self, data: dict[str, Any]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        handle, temp_name = tempfile.mkstemp(prefix="settings-", suffix=".json", dir=self.data_dir)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
        os.replace(temp_name, self.path)

    def all(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            value: Any = self._data
            for part in key.split("."):
                if not isinstance(value, dict) or part not in value:
                    return default
                value = value[part]
            return copy.deepcopy(value)

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._data = deep_merge(self._data, patch)
            self._write(self._data)
            return copy.deepcopy(self._data)
