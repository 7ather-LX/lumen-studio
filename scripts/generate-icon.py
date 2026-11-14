"""Generate app-icon candidates with the local SD-Turbo installation."""

from __future__ import annotations

import base64
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "icon-candidates"
OUT.mkdir(parents=True, exist_ok=True)
icon = (ROOT / "build" / "icon.png").read_bytes()
data_url = "data:image/png;base64," + base64.b64encode(icon).decode("ascii")
base = "http://127.0.0.1:8765"
payload = {
    "prompt": (
        "minimalist premium app icon, dark obsidian rounded square, "
        "a luminous lime-green sun aperture symbol, thin concentric ring, "
        "one small teal accent dot, flat vector, crisp geometry, centered, "
        "soft inner glow, no text, no letters, high contrast, professional software logo"
    ),
    "negative_prompt": (
        "text, letters, typography, words, photorealistic, 3d, clutter, "
        "detailed background, watermark, multiple symbols, noise, blurry"
    ),
    "mode": "img2img",
    "init_image": data_url,
    "strength": 0.58,
    "provider_id": "local-diffusers",
    "model": r"F:\DSH WORKSPACE\.models\sd-turbo",
    "long_edge": 512,
    "steps": 4,
    "guidance": 0,
    "batch_size": 4,
    "style": "minimal",
    "auto_tune": False,
}
response = httpx.post(base + "/api/generate", json=payload, timeout=30).json()
print("submitted", response)
for _ in range(1200):
    job = httpx.get(base + "/api/jobs/" + response["job_id"]).json()
    if job["status"] in ("succeeded", "failed", "cancelled"):
        break
    time.sleep(1)
print("job", job["status"], job.get("error"))
if job["status"] != "succeeded":
    raise SystemExit(1)
for index, image in enumerate(job["result"]["images"]):
    data = httpx.get(base + image["file_url"], timeout=60).content
    path = OUT / f"candidate-{index + 1}-{image['seed']}.png"
    path.write_bytes(data)
    print(path, image["width"], image["height"])
