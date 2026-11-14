"""Tiny ComfyUI API mock used for local end-to-end testing.

Run on port 8199, then add a ComfyUI provider pointing at
http://127.0.0.1:8199 in Lumen Studio.
"""

from __future__ import annotations

import io
import time

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import Response
from PIL import Image, ImageDraw

app = FastAPI()
submitted: dict[str, float] = {}


@app.get("/system_stats")
async def system_stats():
    return {
        "system": {"comfyui_version": "mock-1.0", "python_version": "3.12"},
        "devices": [{"name": "Lumen Mock GPU", "type": "cuda", "vram_total": 12 * 1024**3}],
    }


@app.get("/object_info/CheckpointLoaderSimple")
async def object_info():
    return {
        "CheckpointLoaderSimple": {
            "input": {"required": {"ckpt_name": [["mock-model.safetensors"], {}]}},
            "output": ["MODEL", "CLIP", "VAE"],
        }
    }


@app.post("/upload/image")
async def upload_image(image: UploadFile = File(...)):
    await image.read()
    return {"name": "mock-init.png", "subfolder": "", "type": "input"}


@app.post("/prompt")
async def prompt(payload: dict):
    prompt_id = f"mock-{len(submitted) + 1}"
    submitted[prompt_id] = time.time()
    # Deliberately validate the key nodes so the integration test catches a
    # malformed workflow rather than silently succeeding.
    workflow = payload.get("prompt", {})
    assert workflow["5"]["class_type"] == "KSampler"
    assert workflow["7"]["class_type"] == "SaveImage"
    return {"prompt_id": prompt_id, "number": 1, "node_errors": {}}


@app.get("/history/{prompt_id}")
async def history(prompt_id: str):
    if prompt_id not in submitted:
        return {}
    if time.time() - submitted[prompt_id] < 0.6:
        return {}
    return {
        prompt_id: {
            "status": {"completed": True, "status_str": "success", "messages": []},
            "outputs": {"7": {"images": [{"filename": "mock.png", "subfolder": "", "type": "output"}]}},
        }
    }


@app.get("/view")
async def view(filename: str = "mock.png"):
    image = Image.new("RGB", (512, 512), (33, 42, 38))
    draw = ImageDraw.Draw(image)
    draw.ellipse((120, 120, 392, 392), outline=(201, 245, 109), width=4)
    draw.ellipse((220, 220, 292, 292), fill=(105, 216, 196))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return Response(content=buffer.getvalue(), media_type="image/png")
