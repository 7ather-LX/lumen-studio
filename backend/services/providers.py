from __future__ import annotations

import re
from typing import Any

from backend.db import Database
from backend.engines.diffusers_engine import LOCAL_MODEL_CATALOG
from backend.engines.registry import KIND_LABELS, get_engine
from backend.schemas import ProviderUpsert
from backend.security import SecretStore


class ProviderService:
    def __init__(self, db: Database, secrets: SecretStore):
        self.db = db
        self.secrets = secrets

    def serialize(self, provider: dict[str, Any], with_availability: bool = True) -> dict[str, Any]:
        data = {
            key: value for key, value in provider.items() if key not in ("secret_cipher",)
        }
        data["kind_label"] = KIND_LABELS.get(provider["kind"], provider["kind"])
        data["secret_set"] = self.secrets.has(provider["id"])
        data["secret_masked"] = self.secrets.masked(provider["id"])
        if with_availability:
            try:
                availability = get_engine(provider["kind"]).availability(provider, self.secrets)
                data["availability"] = availability.as_dict()
            except Exception as exc:
                data["availability"] = {
                    "available": False,
                    "reason": "引擎不可用",
                    "detail": str(exc)[:200],
                    "installable": False,
                }
        if provider["kind"] == "diffusers":
            data["model_catalog"] = LOCAL_MODEL_CATALOG
        return data

    def list(self) -> list[dict[str, Any]]:
        return [self.serialize(provider) for provider in self.db.list_providers()]

    def get(self, provider_id: str, with_availability: bool = True) -> dict[str, Any] | None:
        provider = self.db.get_provider(provider_id)
        return self.serialize(provider, with_availability) if provider else None

    @staticmethod
    def _slug(name: str) -> str:
        value = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip()).strip("-").lower()
        return value or "provider"

    def upsert(self, payload: ProviderUpsert) -> dict[str, Any]:
        provider_id = (payload.id or "").strip() or self._slug(payload.name)
        if payload.id is None:
            existing_ids = {item["id"] for item in self.db.list_providers()}
            base = provider_id
            counter = 2
            while provider_id in existing_ids:
                provider_id = f"{base}-{counter}"
                counter += 1
        old = self.db.get_provider(provider_id)
        if payload.kind not in KIND_LABELS:
            raise ValueError("不支持的引擎类型")
        if payload.kind == "comfyui" and not payload.base_url.strip():
            raise ValueError("ComfyUI 需要填写服务地址")
        if payload.kind in ("openai", "stability") and not payload.base_url.strip():
            raise ValueError("该供应商需要填写 API 地址")
        if payload.is_default and not payload.enabled:
            raise ValueError("默认供应商必须处于启用状态")
        if old and old.get("is_default") and not payload.enabled:
            raise ValueError("默认供应商不能停用，请先把其他供应商设为默认")
        is_default = payload.is_default or bool(old and old.get("is_default"))
        provider = self.db.upsert_provider(
            {
                "id": provider_id,
                "name": payload.name.strip(),
                "kind": payload.kind,
                "base_url": payload.base_url.strip(),
                "model": payload.model.strip(),
                "enabled": payload.enabled,
                "is_default": is_default,
                "options": payload.options or {},
            }
        )
        if payload.clear_secret:
            self.secrets.set(provider_id, None)
        elif payload.api_key and not payload.api_key.startswith("••"):
            self.secrets.set(provider_id, payload.api_key.strip())
        return self.serialize(provider)

    def delete(self, provider_id: str) -> tuple[bool, str]:
        provider = self.db.get_provider(provider_id)
        if not provider:
            return False, "供应商不存在"
        if provider["is_default"]:
            return False, "不能删除默认供应商，请先把其他供应商设为默认"
        if provider["kind"] == "demo":
            return False, "示例引擎不能删除"
        self.db.delete_provider(provider_id)
        self.secrets.set(provider_id, None)
        return True, "已删除"

    def test(self, provider_id: str) -> dict[str, Any]:
        provider = self.db.get_provider(provider_id)
        if not provider:
            raise ValueError("供应商不存在")
        return get_engine(provider["kind"]).test_connection(provider, self.secrets)

    def models(self, provider_id: str) -> list[str]:
        provider = self.db.get_provider(provider_id)
        if not provider:
            raise ValueError("供应商不存在")
        try:
            models = get_engine(provider["kind"]).list_models(provider, self.secrets)
        except Exception:
            models = []
        if provider["kind"] == "diffusers":
            from backend.engines.diffusers_engine import LOCAL_MODEL_CATALOG

            models = list(dict.fromkeys([*models, *(str(item["id"]) for item in LOCAL_MODEL_CATALOG)]))
        return models

    def set_default(self, provider_id: str) -> None:
        provider = self.db.get_provider(provider_id)
        if not provider:
            raise ValueError("供应商不存在")
        if not provider["enabled"]:
            raise ValueError("请先启用该供应商")
        self.db.set_default_provider(provider_id)
