"""Configure the dev local provider and generate through the real API."""

import time

import httpx

base = "http://127.0.0.1:8765"
provider = {
    "id": "local-diffusers",
    "name": "本地 Diffusers",
    "kind": "diffusers",
    "base_url": "",
    "model": r"F:\DSH WORKSPACE\.models\sd-turbo",
    "enabled": True,
    "is_default": False,
    "options": {
        "device": "cpu",
        "dtype": "float32",
        "variant": "fp16",
        "local_files_only": True,
        "unload_after_generate": False,
        "cpu_offload": True,
    },
}
print("provider", httpx.put(base + "/api/providers/local-diffusers", json=provider).json()["availability"])
response = httpx.post(
    base + "/api/generate",
    json={
        "prompt": "a quiet lake at blue hour, mist over the water, cinematic, soft light",
        "style": "cinematic",
        "provider_id": "local-diffusers",
        "model": r"F:\DSH WORKSPACE\.models\sd-turbo",
        "long_edge": 512,
        "steps": 4,
        "guidance": 0,
        "auto_tune": False,
    },
    timeout=30,
).json()
print("submit", response)
for _ in range(900):
    job = httpx.get(base + "/api/jobs/" + response["job_id"]).json()
    if job["status"] in ("succeeded", "failed", "cancelled"):
        break
    time.sleep(1)
print("job", job["status"], job.get("error"))
if job["status"] == "succeeded":
    image = job["result"]["images"][0]
    print("image", image["id"], image["width"], image["height"], image["provider_name"], image["analysis"]["technical_score"])
