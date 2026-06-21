# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only

from fastapi import APIRouter
from pydantic import BaseModel

from app.main import config, db

router = APIRouter(tags=["settings"])


async def apply_overrides():
    """Load all settings from DB into in-memory config at startup."""
    SETTING_MAP = {
        "ai_provider": ("ai_provider", str),
        "language": ("language", str),
        "ai_language": ("ai_language", str),
        "anomaly_min_severity": ("anomaly_min_severity", str),
        "ollama_url": ("ollama_base_url", str),
        "openai_url": ("openai_base_url", str),
        "routerai_url": ("routerai_base_url", str),
        "summary_enabled": ("summary_enabled", bool),
        "daily_summary_enabled": ("daily_summary_enabled", bool),
        "summarization_provider": ("summarization_provider", str),
        "summarization_model": ("summarization_model", str),
        "anomaly_detection_provider": ("anomaly_detection_provider", str),
        "anomaly_detection_model": ("anomaly_detection_model", str),
        "embeddings_provider": ("embeddings_provider", str),
        "embeddings_model": ("embeddings_model", str),
    }
    for db_key, (cfg_attr, val_type) in SETTING_MAP.items():
        val = await db.get_setting(db_key)
        if val is not None:
            if val_type is bool:
                if isinstance(val, str):
                    val = str(val).lower() in ("true", "t", "1")
                else:
                    val = bool(val)
            setattr(config, cfg_attr, val)


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
    summarization_provider: str | None = None
    summarization_model: str | None = None
    anomaly_detection_provider: str | None = None
    anomaly_detection_model: str | None = None
    embeddings_provider: str | None = None
    embeddings_model: str | None = None


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
            "summary_enabled": config.summary_enabled,
            "daily_summary_enabled": config.daily_summary_enabled,
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
        config.summary_enabled = data.summary_enabled
        changed["summary_enabled"] = str(data.summary_enabled).lower()
    if data.daily_summary_enabled is not None:
        config.daily_summary_enabled = data.daily_summary_enabled
        changed["daily_summary_enabled"] = str(data.daily_summary_enabled).lower()
    if changed:
        for k, v in changed.items():
            await db.set_setting(k, v)
    for task_attr in ("summarization_provider", "summarization_model",
                       "anomaly_detection_provider", "anomaly_detection_model",
                       "embeddings_provider", "embeddings_model"):
        val = getattr(data, task_attr, None)
        if val:
            setattr(config, task_attr, val)
            changed[task_attr] = val
    if data.chat_model:
        provider = config.ai_provider
        key = f"{provider}_chat_model"
        await db.set_setting(key, data.chat_model)
    return {"ok": True, "changed": changed, "ai_restart_required": False}
