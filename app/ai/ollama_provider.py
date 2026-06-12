import json

import httpx

from app.ai.provider import AIProvider


class OllamaProvider(AIProvider):
    def __init__(self, config):
        self.base_url = config.ollama_base_url.rstrip("/")
        self.chat_model = config.ollama_chat_model
        self.embed_model = config.ollama_embedding_model
        self._dims = config.ollama_embedding_dims
        self._client = httpx.AsyncClient(timeout=120)

    @property
    def embedding_dims(self) -> int:
        return self._dims

    async def chat(self, messages: list[dict], **kwargs) -> str:
        resp = await self._client.post(
            f"{self.base_url}/api/chat",
            json={
                "model": kwargs.get("model", self.chat_model),
                "messages": messages,
                "stream": False,
                **{k: v for k, v in kwargs.items() if k != "model"},
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

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
            "• Диапазон времени, общее кол-во сообщений, распределение по severity\n\n"
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
        log_text = "\n".join(
            f"#{l.get('id','?')} [{l['ts']}] sev={l.get('severity',6)}"
            f" {l.get('app_name','-')}: {l['message']}"
            for l in recent_logs[:200]
        )
        prompt = (
            "Проанализируй логи на аномалии. "
            "Верни JSON-массив объектов со следующими полями:\n"
            "- severity: одна из (critical, warning, info)\n"
            "- title: краткий заголовок на русском (до 100 символов)\n"
            "- description: подробное описание на русском с номерами логов (#ID) и временем\n\n"
            "Что искать:\n"
            "- Ошибки аутентификации, отказы в доступе\n"
            "- Сбои сервисов, перезапуски, таймауты\n"
            "- Подозрительные подключения, сканирования\n"
            "- Аппаратные сбои (диски, память, температура)\n"
            "- Необычные паттерны в логах\n\n"
            "Логи:\n" + log_text
        )
        resp = await self.chat([
            {"role": "system", "content": (
                "Ты — система обнаружения аномалий в логах. "
                "Отвечай ТОЛЬКО валидным JSON-массивом, без пояснений. "
                "Пиши на русском языке. "
                "Указывай номера логов и время в описании. "
                "Не выдумывай аномалии — только реальные."
            )},
            {"role": "user", "content": prompt},
        ])
        try:
            json_start = resp.index("[")
            json_end = resp.rindex("]") + 1
            return json.loads(resp[json_start:json_end])
        except (ValueError, json.JSONDecodeError):
            return []
