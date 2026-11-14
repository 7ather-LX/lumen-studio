import time

import httpx

base = "http://127.0.0.1:8765"
provider = {
    "id": "comfy-mock",
    "name": "ComfyUI Mock",
    "kind": "comfyui",
    "base_url": "http://127.0.0.1:8199",
    "model": "mock-model.safetensors",
    "enabled": True,
    "options": {"timeout": 30},
}
print("save", httpx.put(base + "/api/providers/comfy-mock", json=provider).json()["availability"])
print("test", httpx.post(base + "/api/providers/comfy-mock/test").json())
response = httpx.post(
    base + "/api/generate",
    json={
        "prompt": "a mock comfyui integration test",
        "provider_id": "comfy-mock",
        "model": "mock-model.safetensors",
        "long_edge": 512,
        "steps": 4,
        "guidance": 0,
    },
).json()
print("submit", response)
for _ in range(120):
    job = httpx.get(base + "/api/jobs/" + response["job_id"]).json()
    if job["status"] in ("succeeded", "failed"):
        break
    time.sleep(0.25)
print("job", job["status"], job.get("error"))
if job["status"] == "succeeded":
    image = job["result"]["images"][0]
    print("image", image["width"], image["height"], image["provider_name"], image["analysis"]["technical_score"])
