from __future__ import annotations

import importlib
import importlib.util
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from backend.config import SettingsStore
from backend.db import Database
from backend.engines.registry import get_engine
from backend.security import SecretStore
from backend.utils.system import clear_gpu_cache, gpu_inventory, hardware_profile, system_snapshot


class RuntimeService:
    def __init__(self, db: Database, settings: SettingsStore, secrets: SecretStore, data_dir: Path):
        self.db = db
        self.settings = settings
        self.secrets = secrets
        self.data_dir = data_dir
        self.log_dir = data_dir / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.log_dir / "engine-install.log"
        self._lock = threading.RLock()
        self._process: subprocess.Popen[str] | None = None
        self._status: dict[str, Any] = {
            "state": "idle",
            "variant": None,
            "progress": 0,
            "message": "尚未安装本地运行时",
            "tail": [],
            "started_at": None,
            "finished_at": None,
            "error": None,
        }

    def _tail(self, lines: list[str], limit: int = 24) -> list[str]:
        return [line.rstrip() for line in lines[-limit:] if line.strip()]

    def status(self) -> dict[str, Any]:
        with self._lock:
            install = dict(self._status)
            install["tail"] = list(self._status["tail"])[-24:]
        provider = self.db.get_provider("local-diffusers") or {
            "id": "local-diffusers",
            "kind": "diffusers",
            "options": {},
        }
        try:
            availability = get_engine("diffusers").availability(provider, self.secrets).as_dict()
        except Exception as exc:
            availability = {"available": False, "reason": str(exc)[:200], "detail": "", "installable": True}
        gpus = gpu_inventory()
        free = gpus[0]["free_mb"] if gpus else None
        profile = hardware_profile(free)
        low_vram = self.settings.get("local_engine", {}).get("low_vram", True)
        try:
            disk = shutil.disk_usage(self.data_dir)
            disk_free_gb = round(disk.free / (1024**3), 1)
        except OSError:
            disk_free_gb = None
        return {
            "install": install,
            "local_engine": availability,
            "system": system_snapshot(),
            "hardware_profile": profile,
            "free_vram_mb": free,
            "low_vram": {
                "enabled": bool(low_vram),
                "recommended": free is not None and free < 5000,
                "free_vram_mb": free,
                "profile": profile,
            },
            "python": sys.executable,
            "python_version": sys.version.split()[0],
            "data_dir": str(self.data_dir),
            "disk_free_gb": disk_free_gb,
            "install_log": str(self.log_path),
            "pip": self._pip_version(),
        }

    @staticmethod
    def _pip_version() -> str:
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "pip", "--version"],
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=0x08000000 if os.name == "nt" else 0,
                check=False,
            )
            return completed.stdout.strip().split(" ")[1] if completed.returncode == 0 else "不可用"
        except Exception:
            return "不可用"

    def _variant(self, requested: str) -> str:
        if requested != "auto":
            return requested
        gpus = gpu_inventory()
        return "cuda" if gpus else "cpu"

    def start_install(self, requested: str = "auto") -> dict[str, Any]:
        with self._lock:
            if self._process and self._process.poll() is None:
                return {"ok": False, "message": "本地运行时正在安装中", "status": self.status()}
            variant = self._variant(requested)
            command = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input"]
            if variant == "cuda":
                command += [
                    "torch",
                    "torchvision",
                    "--index-url",
                    "https://download.pytorch.org/whl/cu128",
                ]
            else:
                command += [
                    "torch",
                    "torchvision",
                    "--index-url",
                    "https://download.pytorch.org/whl/cpu",
                ]
            command += ["diffusers>=0.31", "transformers>=4.44", "accelerate>=1.0", "safetensors>=0.4"]
            self.log_path.write_text(
                f"# Lumen Studio local engine install\n# {time.strftime('%Y-%m-%d %H:%M:%S')}\n# {' '.join(command)}\n\n",
                encoding="utf-8",
            )
            env = {**os.environ, "PYTHONUNBUFFERED": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1"}
            try:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=env,
                    creationflags=0x08000000 if os.name == "nt" else 0,
                )
            except Exception as exc:
                self._status.update(
                    state="failed",
                    message="无法启动安装进程",
                    error=str(exc),
                    finished_at=time.time(),
                )
                return {"ok": False, "message": str(exc), "status": self.status()}
            self._process = process
            self._status.update(
                state="running",
                variant=variant,
                progress=0.02,
                message="正在下载 PyTorch 与 Diffusers（通常 2–6 GB，请保持网络连接）",
                tail=[],
                started_at=time.time(),
                finished_at=None,
                error=None,
            )
            thread = threading.Thread(target=self._monitor, args=(process, variant), daemon=True, name="lumen-engine-install")
            thread.start()
            return {"ok": True, "message": "安装已开始", "status": self.status()}

    def _monitor(self, process: subprocess.Popen[str], variant: str) -> None:
        tail: list[str] = []
        assert process.stdout is not None
        with self.log_path.open("a", encoding="utf-8") as log:
            for line in process.stdout:
                log.write(line)
                log.flush()
                tail.append(line.rstrip())
                if len(tail) > 80:
                    tail = tail[-80:]
                lowered = line.lower()
                progress = self._status.get("progress", 0.02)
                if "collecting torch" in lowered or "downloading torch" in lowered:
                    progress = max(progress, 0.08)
                elif "installing collected packages" in lowered:
                    progress = max(progress, 0.72)
                elif "successfully installed" in lowered:
                    progress = 0.96
                with self._lock:
                    self._status.update(progress=progress, tail=self._tail(tail))
        code = process.wait()
        log.write(f"\n# process exited with {code}\n")
        try:
            importlib.invalidate_caches()
            clear_gpu_cache()
        except Exception:
            pass
        with self._lock:
            if code == 0:
                self._status.update(
                    state="done",
                    progress=1.0,
                    message="本地运行时安装完成",
                    finished_at=time.time(),
                    error=None,
                )
            else:
                self._status.update(
                    state="failed",
                    message="安装失败，请查看日志",
                    finished_at=time.time(),
                    error=f"pip exited with {code}",
                )
            self._status["tail"] = self._tail(tail)
            self._process = None

    def cancel_install(self) -> dict[str, Any]:
        with self._lock:
            if self._process and self._process.poll() is None:
                self._process.terminate()
                self._status.update(state="failed", message="安装已取消", finished_at=time.time())
                return {"ok": True, "message": "安装已取消"}
        return {"ok": False, "message": "当前没有正在进行的安装"}

    def local_models(self) -> list[dict[str, Any]]:
        """Discover downloaded Diffusers folders without loading torch."""
        models: list[dict[str, Any]] = []
        roots = [
            Path(os.environ.get("HF_HOME", "")) / "hub" if os.environ.get("HF_HOME") else None,
            self.data_dir / "models" / "huggingface" / "hub",
        ]
        seen: set[str] = set()
        for root in roots:
            if not root or not root.exists():
                continue
            for candidate in root.glob("models--*"):
                parts = candidate.name.split("--")
                if len(parts) >= 3:
                    model_id = "/".join(parts[1:])
                    if model_id not in seen:
                        seen.add(model_id)
                        snapshots = list((candidate / "snapshots").glob("*")) if (candidate / "snapshots").exists() else []
                        size = 0
                        for snapshot in snapshots:
                            for file in snapshot.rglob("*"):
                                if file.is_file():
                                    try:
                                        size += file.stat().st_size
                                    except OSError:
                                        pass
                        models.append(
                            {
                                "id": model_id,
                                "path": str(candidate),
                                "size_gb": round(size / (1024**3), 1),
                                "downloaded": True,
                            }
                        )
        return sorted(models, key=lambda item: item["id"])

    def open_path(self) -> str:
        return str(self.data_dir)
