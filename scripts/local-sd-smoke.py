"""Load the assembled local SD-Turbo folder and generate one image."""

from __future__ import annotations

import time
from pathlib import Path

import torch
from diffusers import AutoPipelineForText2Image

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / ".models" / "sd-turbo"

print("torch", torch.__version__, "cuda", torch.cuda.is_available())
start = time.perf_counter()
pipe = AutoPipelineForText2Image.from_pretrained(
    str(MODEL),
    torch_dtype=torch.float32,
    variant="fp16",
    local_files_only=True,
    safety_checker=None,
    requires_safety_checker=False,
)
pipe.enable_attention_slicing()
pipe.set_progress_bar_config(disable=False)
print("loaded in", round(time.perf_counter() - start, 2), "s")
start = time.perf_counter()
image = pipe(
    "a quiet lake at blue hour, mist over the water, cinematic, soft light",
    width=512,
    height=512,
    num_inference_steps=4,
    guidance_scale=0.0,
    generator=torch.Generator(device="cpu").manual_seed(20261114),
).images[0]
path = ROOT / "build" / "local-sd.png"
path.parent.mkdir(exist_ok=True)
image.save(path)
print("generated", image.size, "in", round(time.perf_counter() - start, 2), "s", "->", path)
