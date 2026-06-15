# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only

PROVIDERS = {
    "ollama": {
        "name": "Ollama",
        "models": {
            "llama3.2:1b": "Llama 3.2 1B",
            "llama3.2:3b": "Llama 3.2 3B",
            "qwen2.5:7b": "Qwen 2.5 7B",
            "nomic-embed-text": "Nomic Embed Text",
        },
    },
    "openai": {
        "name": "OpenAI",
        "models": {
            "gpt-4o-mini": "GPT-4o Mini",
            "gpt-4o": "GPT-4o",
            "text-embedding-3-small": "Text Embedding 3 Small",
        },
    },
    "routerai": {
        "name": "RouterAI",
        "api_key_env": "ROUTERAI_API_KEY",
        "models": {
            "qwen/qwen3.5-9b": "Qwen 3.5 9B",
            "deepseek/deepseek-v4-pro": "DeepSeek V4 Pro",
            "openai/text-embedding-3-small": "Text Embedding 3 Small",
        },
    },
}

TASKS = {
    "summarization": "summarization",
    "anomaly_detection": "anomaly_detection",
    "embeddings": "embeddings",
}


def get_models_by_type(task: str) -> dict[str, dict]:
    """Return {provider_id: {model_id: model_name, ...}} filtered by task."""
    result = {}
    for pid, pdata in PROVIDERS.items():
        matched = {}
        for mid, mname in pdata.get("models", {}).items():
            if task == "embeddings":
                if "embed" in mid.lower():
                    matched[mid] = mname
            else:
                if "embed" not in mid.lower():
                    matched[mid] = mname
        if matched:
            result[pid] = {"name": pdata["name"], "models": matched}
    return result
