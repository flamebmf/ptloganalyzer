# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
import json

import httpx

from app.ai.provider import AIProvider
from app.ai.prompts import ANOMALY_LANG_PROMPTS


class OllamaProvider(AIProvider):
    def __init__(self, config):
        self.base_url = config.ollama_base_url.rstrip("/")
        self.chat_model = config.ollama_chat_model
        self.embed_model = config.ollama_embedding_model
        self._dims = config.ollama_embedding_dims
        self._timeout = config.ollama_timeout
        self._client = httpx.AsyncClient(timeout=self._timeout)
        self.language = getattr(config, "ai_language", "ru")

    @property
    def embedding_dims(self) -> int:
        return self._dims

    async def chat(self, messages: list[dict], **kwargs) -> str:
        payload = {
            "model": kwargs.get("model", self.chat_model),
            "messages": messages,
            "stream": False,
            **{k: v for k, v in kwargs.items() if k != "model"},
        }
        try:
            resp = await self._client.post(
                f"{self.base_url}/api/chat", json=payload
            )
        except httpx.ReadTimeout:
            raise TimeoutError(f"ReadTimeout after {self._timeout}s")
        if resp.status_code == 404:
            # Fallback to /api/generate for older Ollama versions
            system = next((m["content"] for m in messages if m["role"] == "system"), "")
            user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
            gen_payload = {"model": payload["model"], "prompt": user, "stream": False}
            if system:
                gen_payload["system"] = system
            resp = await self._client.post(f"{self.base_url}/api/generate", json=gen_payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content") or data.get("response", "")

    async def embed(self, text: str) -> list[float]:
        resp = await self._client.post(
            f"{self.base_url}/api/embed",
            json={"model": self.embed_model, "input": text},
        )
        resp.raise_for_status()
        return resp.json()["embeddings"][0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        results = []
        for text in texts:
            embedding = await self.embed(text)
            results.append(embedding)
        return results

    async def summarize(self, logs: list[dict]) -> str:
        log_lines = "\n".join(
            f"#{l.get('id','?')} [{l['ts']}] {l.get('app_name','-')}"
            f" sev={l.get('severity','?')}: {l['message']}"
            for l in logs[:200]
        )
        prompt = (
            "Проведи глубокий анализ syslog-сообщений. "
            "Ответь на русском языке, используй чёткую структуру:\n\n"
            "=== ОБЩАЯ ИНФОРМАЦИЯ ===\n"
            "• Общее кол-во сообщений, распределение по severity\n\n"
            "=== КЛЮЧЕВЫЕ СОБЫТИЯ ===\n"
            "• 3-5 самых важных событий с номерами логов (#NNN) и временем\n"
            "• Для каждого: что произошло, почему важно\n\n"
            "=== ПРИЛОЖЕНИЯ И СЛУЖБЫ ===\n"
            "• Топ приложений по количеству сообщений и ошибок\n\n"
            "=== АНОМАЛИИ И ПОДОЗРИТЕЛЬНАЯ АКТИВНОСТЬ ===\n"
            "• Повторяющиеся ошибки, всплески, необычные паттерны\n"
            "• Укажи ID логов для каждой аномалии\n\n"
            "=== РЕКОМЕНДАЦИИ ===\n"
            "• Что нужно проверить или исправить\n\n"
            "Логи для анализа:\n" + log_lines
        )
        return await self.chat([
            {"role": "system", "content": (
                "Ты — эксперт по анализу системных логов и сетевой безопасности. "
                "Отвечай только на русском языке. "
                "Будь конкретным, ссылайся на номера логов (#ID) и время. "
                "Используй разделители === для секций."
            )},
            {"role": "user", "content": prompt},
        ])

    async def detect_anomalies(self, recent_logs: list[dict],
                                baseline: dict | None = None) -> list[dict]:
        lang = self.language if self.language in ANOMALY_LANG_PROMPTS else "ru"
        prompts = ANOMALY_LANG_PROMPTS[lang]
        log_text = "\n".join(
            f"#{l.get('id','?')} [{l['ts']}] sev={l.get('severity',6)}"
            f" {l.get('app_name','-')}: {l['message']}"
            for l in recent_logs[:200]
        )
        resp = await self.chat([
            {"role": "system", "content": prompts["system"]},
            {"role": "user", "content": prompts["user"] + log_text},
        ])
        try:
            json_start = resp.index("[")
            json_end = resp.rindex("]") + 1
            return json.loads(resp[json_start:json_end])
        except (ValueError, json.JSONDecodeError):
            return []
