from __future__ import annotations

import json
import re
from typing import Any

import httpx

from backend.config import SettingsStore
from backend.security import SecretStore

SYSTEM_PROMPT = """You are Lumen's anime prompt engineer. Turn the user's idea into a concise English Danbooru-style tag prompt for a hand-drawn cel-shaded anime character illustration.

Rules:
- Output strict JSON only: {"prompt": "...", "negative_prompt": "..."}.
- Keep the user's subject, character count, clothing and intent.
- Use comma-separated booru-style tags, then a short natural-language sentence.
- Include: character count (1girl/1boy), hair, eyes, expression, pose, framing, background, lighting, cel shading, clean lineart, flat colors.
- Add quality tags only when they do not fight the requested style.
- Negative prompt should target bad anatomy, extra fingers, messy lineart, 3D/CGI, photorealistic skin, watermark and text.
- No sexual content, no minors in suggestive contexts, no real-person likeness.
- Keep the prompt under 200 words."""


class AssistantService:
    def __init__(self, settings: SettingsStore, secrets: SecretStore):
        self.settings = settings
        self.secrets = secrets
        self.secret_key = "assistant"

    def config(self) -> dict[str, Any]:
        data = self.settings.get("assistant", {}) or {}
        return {
            "enabled": bool(data.get("enabled")),
            "base_url": str(data.get("base_url") or "http://127.0.0.1:8000/v1"),
            "model": str(data.get("model") or ""),
            "timeout": int(data.get("timeout") or 90),
            "has_key": self.secrets.has(self.secret_key),
            "key_masked": self.secrets.masked(self.secret_key),
        }

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        allowed = {"enabled", "base_url", "model", "timeout"}
        clean = {key: patch[key] for key in patch if key in allowed}
        if "base_url" in clean:
            clean["base_url"] = str(clean["base_url"]).strip().rstrip("/")
        if "model" in clean:
            clean["model"] = str(clean["model"]).strip()
        if "timeout" in clean:
            clean["timeout"] = max(10, min(300, int(clean["timeout"])))
        if "api_key" in patch:
            key = str(patch.get("api_key") or "").strip()
            if key:
                self.secrets.set(self.secret_key, key)
        if patch.get("clear_key"):
            self.secrets.set(self.secret_key, None)
        current = self.settings.get("assistant", {}) or {}
        self.settings.update({"assistant": {**current, **clean}})
        return self.config()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        key = self.secrets.get(self.secret_key)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def _url(self, path: str) -> str:
        base = str(self.settings.get("assistant.base_url", "http://127.0.0.1:8000/v1")).rstrip("/")
        return base + path

    def test(self) -> dict[str, Any]:
        timings = {"timeout": float(self.settings.get("assistant.timeout", 90))}
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.get(self._url("/models"), headers=self._headers())
                if response.status_code in (401, 403):
                    return {"ok": False, "message": "API Key 无效", "models": []}
                if response.status_code >= 400:
                    return {"ok": False, "message": f"HTTP {response.status_code}", "models": []}
                payload = response.json()
                models = [str(item.get("id")) for item in payload.get("data", []) if item.get("id")]
                return {"ok": True, "message": f"连接成功 · {len(models)} 个模型", "models": models, **timings}
        except Exception as exc:
            return {"ok": False, "message": "无法连接提示词助手", "detail": str(exc)[:200], "models": []}

    def enhance(self, prompt: str, style: str, mode: str = "txt2img") -> dict[str, Any]:
        if not self.config()["model"]:
            raise ValueError("尚未配置提示词助手模型")
        user = (
            f"Style: {style}\nMode: {mode}\n"
            f"User idea: {prompt}\n\n"
            "Rewrite this for a safe, high-quality anime cel-shaded character illustration."
        )
        payload = {
            "model": self.settings.get("assistant.model"),
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            "temperature": 0.65,
            "max_tokens": 700,
        }
        try:
            with httpx.Client(timeout=float(self.settings.get("assistant.timeout", 90))) as client:
                response = client.post(self._url("/chat/completions"), headers=self._headers(), json=payload)
                if response.status_code >= 400:
                    raise ValueError(f"提示词助手返回 HTTP {response.status_code}: {response.text[:240]}")
                data = response.json()
                content = data["choices"][0]["message"]["content"]
        except httpx.HTTPError as exc:
            raise ValueError(f"提示词助手请求失败：{str(exc)[:200]}") from exc
        parsed = self._parse(content)
        if not parsed["prompt"]:
            raise ValueError("提示词助手没有返回有效结果")
        return {
            **parsed,
            "raw": content[:4000],
            "model": self.settings.get("assistant.model"),
            "style": style,
        }

    @staticmethod
    def _parse(content: str) -> dict[str, str]:
        text = str(content or "").strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                data = json.loads(text[start : end + 1])
                prompt = re.sub(r"\s*--(?:ar|v|style|seed)\s+\S+", "", str(data.get("prompt") or "")).strip()
                return {
                    "prompt": prompt,
                    "negative_prompt": str(data.get("negative_prompt") or "").strip(),
                }
        except (json.JSONDecodeError, TypeError):
            pass
        return {"prompt": text[:3500], "negative_prompt": ""}
