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
                            self.cfg.summary_interval * 60,
                            self._run_summarization))
        asyncio.create_task(self._loop("anomaly_detection",
                            self.cfg.anomaly_interval * 60,
                            self._run_anomaly_detection))
        asyncio.create_task(self._loop("embeddings",
                            300,  # every 5 minutes
                            self._run_embeddings))

        log.info("scheduler_started",
                  summary_interval=self.cfg.summary_interval,
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

    async def _run_all(self):
        await self._run_summarization()
        await self._run_anomaly_detection()
        await self._run_embeddings()

    async def _run_summarization(self):
        devices = await self.db.list_devices()
        for d in devices:
            if self.cfg.ai_enabled and d["enabled"]:
                await self.summarizer.run_for_device(d["id"])

    async def _run_anomaly_detection(self):
        devices = await self.db.list_devices()
        for d in devices:
            if d["enabled"]:
                await self.anomaly_detector.run_for_device(d["id"])

    async def _run_embeddings(self):
        if self.cfg.ai_enabled:
            await self.embeddings.process_unembedded()
