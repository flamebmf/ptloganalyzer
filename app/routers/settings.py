# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
import json
import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from app.main import config

router = APIRouter(tags=["settings"])

RUNTIME_OVERRIDES = Path(config.data_dir) / "config" / "runtime.json"


def load_overrides():
    try:
        return json.loads(RUNTIME_OVERRIDES.read_text())
    except Exception:
        return {}


def save_overrides(data: dict):
    RUNTIME_OVERRIDES.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_OVERRIDES.write_text(json.dumps(data))


def apply_overrides():
    ov = load_overrides()
    if ov.get("ai_provider"):
        config.ai_provider = ov["ai_provider"]
    if ov.get("language"):
        config.language = ov["language"]


class SettingsUpdate(BaseModel):
    ai_provider: str | None = None
    language: str | None = None


@router.get("/settings")
async def get_settings():
    return {
        "app": {"name": config.name, "version": config.version},
        "ai": {
            "enabled": config.ai_enabled,
            "provider": config.ai_provider,
            "summarization_interval": config.summary_interval,
            "anomaly_interval": config.anomaly_interval,
            "openai": {"url": config.openai_base_url, "model": config.openai_chat_model, "has_key": bool(config.openai_api_key)},
            "ollama": {"url": config.ollama_base_url, "model": config.ollama_chat_model},
            "routerai": {"url": config.routerai_base_url, "model": config.routerai_chat_model, "has_key": bool(config.routerai_api_key)},
        },
        "web": {"language": config.language},
        "collector": {"port": config.collector_port, "enabled": config.collector_enabled},
    }


@router.patch("/settings")
async def update_settings(data: SettingsUpdate):
    changed = {}
    if data.ai_provider and data.ai_provider in ("ollama", "openai", "routerai"):
        config.ai_provider = data.ai_provider
        changed["ai_provider"] = data.ai_provider
    if data.language and data.language in ("ru", "en"):
        config.language = data.language
        changed["language"] = data.language
    if changed:
        ov = load_overrides()
        ov.update(changed)
        save_overrides(ov)
    return {"ok": True, "changed": changed, "ai_restart_required": bool(changed.get("ai_provider"))}
