import json
import os

import httpx

base = "http://127.0.0.1:8765"
key = os.environ["LUMEN_LLM_KEY"]
config = {
    "enabled": True,
    "base_url": "http://127.0.0.1:8000/v1",
    "model": "deepseek-v4-pro-qwen3.5-9b-uncensored-heretic",
    "api_key": key,
    "timeout": 120,
}
print("config", httpx.put(base + "/api/assistant", json=config).json())
print("test", httpx.post(base + "/api/assistant/test").json())
result = httpx.post(
    base + "/api/assistant/enhance",
    json={
        "prompt": "银发红瞳的少女站在樱花树下，黑色水手服，微风吹动裙摆，微笑着看向镜头",
        "style": "anime-cel",
        "mode": "txt2img",
    },
    timeout=180,
)
print("enhance", result.status_code)
print(json.dumps(result.json(), ensure_ascii=False, indent=2)[:3000])
