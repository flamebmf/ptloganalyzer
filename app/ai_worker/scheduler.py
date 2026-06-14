# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
import asyncio
import structlog

from app.database import Database
from app.ai.summarizer import Summarizer
from app.ai.anomaly_detector import AnomalyDetector
from app.ai.embeddings import EmbeddingService

log = structlog.get_logger()


class Scheduler:
    def __init__(self, config):
        self.cfg = config
        self.db = Database(config)
        self.summarizer = Summarizer(config, self.db)
        self.anomaly_detector = AnomalyDetector(config, self.db)
        self.embeddings = EmbeddingService(config, self.db)
        self._running = True

    async def start(self):
        await self.db.connect()

        # Run immediately on start
        await self._run_all()

        # Schedule periodic tasks
        asyncio.create_task(self._loop("summarization",
                            3600,  # once per hour
                            self._run_summarization))
        asyncio.create_task(self._daily_loop(
                            self._run_daily_summarization))
        asyncio.create_task(self._loop("anomaly_detection",
                            self.cfg.anomaly_interval * 60,
                            self._run_anomaly_detection))
        asyncio.create_task(self._loop("embeddings",
                            300,  # every 5 minutes
                            self._run_embeddings))

        log.info("scheduler_started",
                  summary_interval_min=60,
                  anomaly_interval=self.cfg.anomaly_interval)

    async def stop(self):
        self._running = False
        await self.db.close()

    async def _loop(self, name: str, interval: float, coro):
        while self._running:
            await asyncio.sleep(interval)
            try:
                await coro()
            except Exception as e:
                log.error("scheduler_task_failed", task=name, error=str(e))

    async def _daily_loop(self, coro):
        # Ждём до полуночи UTC
        import datetime
        while self._running:
            now = datetime.datetime.now(datetime.timezone.utc)
            midnight = (now + datetime.timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0)
            wait = (midnight - now).total_seconds()
            await asyncio.sleep(wait)
            if not self._running:
                break
            try:
                await coro()
            except Exception as e:
                log.error("scheduler_task_failed", task="daily_summarization", error=str(e))

    async def _run_all(self):
        await self._run_summarization()
        await self._run_anomaly_detection()
        await self._run_embeddings()

    async def _run_summarization(self):
        """Process devices sequentially — one summary per hour, 3 min gap between devices."""
        devices = await self.db.list_devices()
        for d in devices:
            if not self._running:
                return
            if self.cfg.ai_enabled and d.get("ai_enabled", True):
                await self.summarizer.run_for_device(d["id"])
                await asyncio.sleep(180)  # 3 min between devices

    async def _run_daily_summarization(self):
        devices = await self.db.list_devices()
        for d in devices:
            if self.cfg.ai_enabled and d.get("ai_enabled", True):
                await self.summarizer.run_daily_for_device(d["id"])

    async def _run_anomaly_detection(self):
        devices = await self.db.list_devices()
        for d in devices:
            if d["enabled"]:
                await self.anomaly_detector.run_for_device(d["id"], d.get("ai_enabled", True))

    async def _run_embeddings(self):
        if self.cfg.ai_enabled:
            await self.embeddings.process_unembedded()
