# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
from app.ai.provider import AIProvider
from app.ai.openai_provider import OpenAIProvider
from app.ai.ollama_provider import OllamaProvider
from app.ai.routerai_provider import RouterAIProvider


def create_provider(config) -> AIProvider:
    if not config.ai_enabled:
        return None
    if config.ai_provider == "openai":
        return OpenAIProvider(config)
    if config.ai_provider == "routerai":
        return RouterAIProvider(config)
    return OllamaProvider(config)
