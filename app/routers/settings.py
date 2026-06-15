# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
import json
import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from app.main import config, db

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
    if ov.get("ai_language"):
        config.ai_language = ov["ai_language"]
    if ov.get("anomaly_min_severity"):
        config.anomaly_min_severity = ov["anomaly_min_severity"]


class SettingsUpdate(BaseModel):
    ai_provider: str | None = None
    language: str | None = None
    ai_language: str | None = None
    anomaly_min_severity: str | None = None
    chat_model: str | None = None
    ollama_url: str | None = None
    openai_url: str | None = None
    routerai_url: str | None = None
    summary_enabled: bool | None = None
    daily_summary_enabled: bool | None = None


@router.get("/settings")
async def get_settings():
    return {
        "app": {"name": config.name, "version": config.version},
        "ai": {
            "enabled": config.ai_enabled,
            "provider": config.ai_provider,
            "language": config.ai_language,
            "summarization_interval": config.summary_interval,
            "anomaly_interval": config.anomaly_interval,
            "anomaly_min_severity": config.anomaly_min_severity,
            "summary_enabled": True,
            "daily_summary_enabled": True,
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
    if data.ai_language and data.ai_language in ("ru", "en"):
        config.ai_language = data.ai_language
        changed["ai_language"] = data.ai_language
    if data.anomaly_min_severity and data.anomaly_min_severity in ("info", "warning", "critical"):
        config.anomaly_min_severity = data.anomaly_min_severity
        changed["anomaly_min_severity"] = data.anomaly_min_severity
    if data.ollama_url is not None:
        config.ollama_base_url = data.ollama_url
        changed["ollama_url"] = data.ollama_url
    if data.openai_url is not None:
        config.openai_base_url = data.openai_url
        changed["openai_url"] = data.openai_url
    if data.routerai_url is not None:
        config.routerai_base_url = data.routerai_url
        changed["routerai_url"] = data.routerai_url
    if data.summary_enabled is not None:
        changed["summary_enabled"] = str(data.summary_enabled).lower()
    if data.daily_summary_enabled is not None:
        changed["daily_summary_enabled"] = str(data.daily_summary_enabled).lower()
    if changed:
        ov = load_overrides()
        ov.update(changed)
        save_overrides(ov)
        for k in ("ai_provider", "language", "ai_language", "anomaly_min_severity",
                   "summary_enabled", "daily_summary_enabled",
                   "ollama_url", "openai_url", "routerai_url"):
            if k in changed:
                await db.set_setting(k, changed[k])
    if data.chat_model:
        provider = config.ai_provider
        key = f"{provider}_chat_model"
        await db.set_setting(key, data.chat_model)
        ov = load_overrides()
        ov["chat_model"] = data.chat_model
        save_overrides(ov)
    return {"ok": True, "changed": changed, "ai_restart_required": False}
