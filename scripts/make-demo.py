import time

import httpx

base = "http://127.0.0.1:8765"
response = httpx.post(
    base + "/api/generate",
    json={
        "prompt": "a geometric garden at dusk, cinematic, soft mist",
        "style": "cinematic",
        "provider_id": "demo",
        "long_edge": 768,
    },
).json()
print(response.get("job_id"))
for _ in range(100):
    job = httpx.get(base + "/api/jobs/" + response["job_id"]).json()
    if job["status"] in ("succeeded", "failed"):
        break
    time.sleep(0.3)
print(job["status"], len(job.get("result", {}).get("images", [])))
