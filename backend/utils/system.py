from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
import sys
import time
from typing import Any

_GPU_CACHE: dict[str, Any] = {"time": 0.0, "value": []}
_GPU_CACHE_TTL = 5.0


def _run(command: list[str], timeout: int = 6) -> str:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=0x08000000 if os.name == "nt" else 0,
            check=False,
        )
        if completed.returncode == 0:
            return completed.stdout.strip()
    except Exception:
        pass
    return ""


def gpu_inventory() -> list[dict[str, Any]]:
    now = time.time()
    if now - float(_GPU_CACHE["time"]) < _GPU_CACHE_TTL:
        return list(_GPU_CACHE["value"])
    if not shutil.which("nvidia-smi"):
        _GPU_CACHE.update(time=now, value=[])
        return []
    output = _run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.used,memory.free,driver_version,temperature.gpu,utilization.gpu",
            "--format=csv,noheader,nounits",
        ]
    )
    gpus: list[dict[str, Any]] = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 4:
            continue
        try:
            total = int(float(parts[1]))
            used = int(float(parts[2]))
            free = int(float(parts[3]))
        except ValueError:
            continue
        gpus.append(
            {
                "vendor": "NVIDIA",
                "name": parts[0],
                "total_mb": total,
                "used_mb": used,
                "free_mb": free,
                "driver": parts[4] if len(parts) > 4 else "",
                "temperature_c": parts[5] if len(parts) > 5 else "",
                "utilization": parts[6] if len(parts) > 6 else "",
            }
        )
    _GPU_CACHE.update(time=now, value=gpus)
    return gpus


def clear_gpu_cache() -> None:
    _GPU_CACHE.update(time=0.0, value=[])


def total_ram_gb() -> float | None:
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        try:
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return round(status.ullTotalPhys / (1024**3), 1)
        except Exception:
            return None
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024**3), 1)
    except (AttributeError, ValueError, OSError):
        return None


def cpu_name() -> str:
    if os.name == "nt":
        return os.environ.get("PROCESSOR_IDENTIFIER", platform.processor() or "CPU")
    return platform.processor() or platform.machine() or "CPU"


def hardware_profile(free_vram_mb: int | None) -> dict[str, Any]:
    if free_vram_mb is None:
        return {
            "id": "unknown",
            "label": "未检测到 NVIDIA GPU",
            "detail": "可使用 CPU 模式、ComfyUI 或云端引擎",
            "suggested_long_edge": 768,
            "suggested_model": "runwayml/stable-diffusion-v1-5",
        }
    if free_vram_mb >= 8192:
        return {
            "id": "roomy",
            "label": "显存充裕",
            "detail": "可运行 SDXL 1024；FLUX 需要 16 GB 以上或量化版",
            "suggested_long_edge": 1024,
            "suggested_model": "stabilityai/stable-diffusion-xl-base-1.0",
        }
    if free_vram_mb >= 4096:
        return {
            "id": "balanced",
            "label": "平衡模式",
            "detail": "建议 SDXL + 分块 VAE / 768–1024",
            "suggested_long_edge": 896,
            "suggested_model": "stabilityai/stable-diffusion-xl-base-1.0",
        }
    if free_vram_mb >= 1600:
        return {
            "id": "low",
            "label": "低显存模式",
            "detail": "建议 SD-Turbo 512、顺序 CPU 卸载，生成后释放模型",
            "suggested_long_edge": 512,
            "suggested_model": "stabilityai/sd-turbo",
        }
    return {
        "id": "critical",
        "label": "显存紧张",
        "detail": "建议先释放其他 AI 的显存，或使用 CPU / 云端引擎",
        "suggested_long_edge": 512,
        "suggested_model": "stabilityai/sd-turbo",
    }


def system_snapshot() -> dict[str, Any]:
    gpus = gpu_inventory()
    free = gpus[0]["free_mb"] if gpus else None
    return {
        "cpu": {"name": cpu_name(), "logical_cores": os.cpu_count()},
        "ram_gb": total_ram_gb(),
        "gpus": gpus,
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "profile": hardware_profile(free),
        "npu_note": "NPU 可通过 ComfyUI 的 OpenVINO / DirectML 后端使用（实验性），内置 Diffusers 引擎默认选择 CUDA 或 CPU。",
    }
