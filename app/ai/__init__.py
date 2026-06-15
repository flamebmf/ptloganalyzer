# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
from app.ai.provider import AIProvider
from app.ai.openai_provider import OpenAIProvider
from app.ai.ollama_provider import OllamaProvider
from app.ai.routerai_provider import RouterAIProvider


_TASK_CFG_MAP = {
    "summarization": ("summarization_provider", "summarization_model"),
    "anomaly_detection": ("anomaly_detection_provider", "anomaly_detection_model"),
    "embeddings": ("embeddings_provider", "embeddings_model"),
}

_EMBEDDING_MODEL_MAP = {
    "ollama": "ollama_embedding_model",
    "openai": "openai_embedding_model",
    "routerai": "routerai_embedding_model",
}

_EMBEDDING_DIMS_MAP = {
    "ollama": "ollama_embedding_dims",
    "openai": "openai_embedding_dims",
    "routerai": "routerai_embedding_dims",
}


def create_provider(config, task: str | None = None) -> AIProvider:
    if not config.ai_enabled:
        return None

    if task and task in _TASK_CFG_MAP:
        prov_attr, model_attr = _TASK_CFG_MAP[task]
        provider = getattr(config, prov_attr, config.ai_provider)
        model = getattr(config, model_attr, "")
    else:
        provider = config.ai_provider
        model = ""

    if task == "embeddings":
        # Embedding model is separate for each provider
        return _create_embedding_provider(config)

    cfg = _task_config(config, provider, model)
    if provider == "openai":
        return OpenAIProvider(cfg)
    if provider == "routerai":
        return RouterAIProvider(cfg)
    return OllamaProvider(cfg)


def _create_embedding_provider(config):
    provider = getattr(config, "embeddings_provider", config.ai_provider)
    model_attr = _EMBEDDING_MODEL_MAP.get(provider, "routerai_embedding_model")
    dims_attr = _EMBEDDING_DIMS_MAP.get(provider, "routerai_embedding_dims")
    cfg = _task_config(config, provider, getattr(config, model_attr, ""))
    setattr(cfg, f"{provider}_embedding_dims", getattr(config, dims_attr, 768))
    if provider == "openai":
        return OpenAIProvider(cfg)
    if provider == "routerai":
        return RouterAIProvider(cfg)
    return OllamaProvider(cfg)


def _task_config(config, provider: str, model: str):
    """Create a config-like object with overridden provider+model for a task."""
    class _TaskConfig:
        pass

    c = _TaskConfig()
    c.ai_enabled = config.ai_enabled
    c.ai_provider = provider

    # Copy all provider-specific attributes
    for prefix in ("openai", "ollama", "routerai"):
        for attr in ("api_key", "base_url", "chat_model", "embedding_model", "embedding_dims", "timeout"):
            src = f"{prefix}_{attr}"
            if hasattr(config, src):
                setattr(c, src, getattr(config, src))

    # Override chat_model if specified
    if model:
        setattr(c, f"{provider}_chat_model", model)
        setattr(c, f"{provider}_model", model)

    return c
