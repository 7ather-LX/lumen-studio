"""Download SD-Turbo fp16 weights from ModelScope for local testing.

The Hugging Face CDN can be slow or truncated on some networks. ModelScope
mirrors the same weights and supports byte-range requests, so this helper
downloads only the Diffusers fp16 components in parallel and assembles a local
Diffusers folder with the small config files already present in the HF cache.

Usage:
    python scripts/download_sd_turbo_modelscope.py
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / ".models" / "sd-turbo"
BASE = "https://modelscope.cn/models/AI-ModelScope/sd-turbo/resolve/master"
CHUNK = 16 * 1024 * 1024
THREADS = 6

FILES = [
    {
        "name": "unet/diffusion_pytorch_model.fp16.safetensors",
        "size": 1_731_904_736,
        "sha256": "40ec400881e27d1376c7c95c5bd495f407b33756e80eb6365e301c33a07af6e5",
    },
    {
        "name": "text_encoder/model.fp16.safetensors",
        "size": 680_820_392,
        "sha256": "bc1827c465450322616f06dea41596eac7d493f4e95904dcb51f0fc745c4e13f",
    },
    {
        "name": "vae/diffusion_pytorch_model.fp16.safetensors",
        "size": 167_335_342,
        "sha256": "3e4c08995484ee61270175e9e7a072b66a6e4eeb5f0c266667fe1f45b90daf9a",
    },
]

CONFIGS = [
    "model_index.json",
    "scheduler/scheduler_config.json",
    "text_encoder/config.json",
    "tokenizer/merges.txt",
    "tokenizer/special_tokens_map.json",
    "tokenizer/tokenizer_config.json",
    "tokenizer/vocab.json",
    "unet/config.json",
    "vae/config.json",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch_range(url: str, start: int, end: int, destination: Path, retries: int = 6) -> int:
    headers = {"Range": f"bytes={start}-{end}", "User-Agent": "LumenStudio/0.1"}
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=120) as response:
                data = response.read()
            if len(data) != end - start + 1:
                raise IOError(f"short range {start}-{end}: {len(data)}")
            with destination.open("r+b") as stream:
                stream.seek(start)
                stream.write(data)
            return len(data)
        except Exception as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"range {start}-{end} failed: {last_error}")


def download(item: dict) -> None:
    relative = item["name"]
    destination = TARGET / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    size = item["size"]
    if destination.exists() and destination.stat().st_size == size:
        print(f"cached {relative}")
        return
    with destination.open("wb") as stream:
        stream.truncate(size)
    ranges = [(start, min(size - 1, start + CHUNK - 1)) for start in range(0, size, CHUNK)]
    url = f"{BASE}/{relative}"
    print(f"downloading {relative} ({size / 1024 / 1024:.0f} MB, {len(ranges)} chunks)")
    started = time.time()
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as pool:
        futures = [pool.submit(fetch_range, url, start, end, destination) for start, end in ranges]
        for future in concurrent.futures.as_completed(futures):
            done += future.result()
            elapsed = max(0.1, time.time() - started)
            print(f"  {done / 1024 / 1024:.0f}/{size / 1024 / 1024:.0f} MB · {done / 1024 / 1024 / elapsed:.1f} MB/s", flush=True)
    actual = sha256(destination)
    if actual != item["sha256"]:
        raise RuntimeError(f"checksum mismatch for {relative}: {actual}")


def main() -> int:
    TARGET.mkdir(parents=True, exist_ok=True)
    for item in FILES:
        download(item)

    snapshots = sorted(
        (Path(os.environ.get("HF_HOME", ROOT / ".hf-test")) / "hub" / "models--stabilityai--sd-turbo" / "snapshots").glob("*")
    )
    if not snapshots:
        print("HF config snapshot missing; run a Hugging Face metadata download first.", file=sys.stderr)
        return 1
    snapshot = snapshots[-1]
    for relative in CONFIGS:
        source = snapshot / relative
        destination = TARGET / relative
        if not source.exists():
            print(f"missing config {relative} in {snapshot}", file=sys.stderr)
            return 1
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    print(f"LOCAL_MODEL={TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
