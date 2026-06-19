# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
from abc import ABC, abstractmethod

from app.ai.prompts import ANOMALY_LANG_PROMPTS


class AIProvider(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs) -> str:
        ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        ...

    @abstractmethod
    async def summarize(self, logs: list[dict]) -> str:
        ...

    @abstractmethod
    async def detect_anomalies(self, recent_logs: list[dict],
                                baseline: dict | None = None) -> list[dict]:
        ...

    @property
    @abstractmethod
    def embedding_dims(self) -> int:
        ...
