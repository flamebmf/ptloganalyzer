# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
import asyncio
import os
import structlog

from app.config import Config as AppConfig
from app.database import Database
from app.ai import create_provider
from app.ai.summarizer import Summarizer
from app.ai.anomaly_detector import AnomalyDetector
from app.ai.embeddings import EmbeddingService

log = structlog.get_logger()


class Scheduler:
    def __init__(self, config):
        self.cfg = config
        self.db = Database(config)
        self._config_path = os.getenv("CONFIG_PATH", "/app/config/config.yaml")
        self._config_mtime = self._get_config_mtime()
        self._create_services()
        self._running = True

    def _get_config_mtime(self) -> float:
        try:
            return os.path.getmtime(self._config_path)
        except Exception:
            return 0

    def _create_services(self):
        self.summarizer = Summarizer(self.cfg, self.db)
        self.anomaly_detector = AnomalyDetector(self.cfg, self.db)
        self.embeddings = EmbeddingService(self.cfg, self.db)
        log.info("services_created", provider=self.cfg.ai_provider)

    async def start(self):
        await self.db.connect()

        # Check DB config FIRST, before any scheduled tasks
        await self._check_config()

        # Check for runtime config changes every 30 seconds
        asyncio.create_task(self._loop("config_check",
                            30,
                            self._check_config))

        # Schedule periodic tasks FIRST — они должны работать всегда,
        # даже если начальный прогон упадёт или затянется
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

        # Run immediately on start (best-effort, не ломает scheduler)
        for name, coro in [("summarization", self._run_summarization),
                           ("anomaly_detection", self._run_anomaly_detection),
                           ("embeddings", self._run_embeddings)]:
            try:
                await coro()
            except Exception as e:
                log.error("initial_run_failed", task=name, error=str(e))

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

    async def _check_config(self):
        """Check if AI config has changed and recreate services if needed."""
        try:
            changed = False

            cfg_mtime = self._get_config_mtime()
            if cfg_mtime and cfg_mtime != self._config_mtime:
                log.info("config_file_changed", mtime=cfg_mtime)
                self._config_mtime = cfg_mtime
                self.cfg = AppConfig(self._config_path)
                changed = True

            db_provider = await self.db.get_setting("ai_provider")
            if db_provider and db_provider != self.cfg.ai_provider:
                log.info("config_provider_changed", old=self.cfg.ai_provider, new=db_provider)
                self.cfg.ai_provider = db_provider
                changed = True

            # Apply per-task config from DB
            for task in ("summarization", "anomaly_detection", "embeddings"):
                db_task_prov = await self.db.get_setting(f"{task}_provider")
                db_task_model = await self.db.get_setting(f"{task}_model")
                cfg_prov = getattr(self.cfg, f"{task}_provider", None)
                cfg_model = getattr(self.cfg, f"{task}_model", None)

                if db_task_prov and db_task_prov != cfg_prov:
                    setattr(self.cfg, f"{task}_provider", db_task_prov)
                    log.info("task_config_changed", task=task, key="provider",
                             value=db_task_prov)
                    changed = True
                if db_task_model and db_task_model != cfg_model:
                    setattr(self.cfg, f"{task}_model", db_task_model)
                    log.info("task_config_changed", task=task, key="model",
                             value=db_task_model)
                    changed = True

            # Summary toggles
            for key in ("summary_enabled", "daily_summary_enabled"):
                db_val = await self.db.get_setting(key)
                if db_val is not None:
                    current = getattr(self.cfg, key, None)
                    db_bool = str(db_val).lower() in ("true", "t", "1")
                    if db_bool != current:
                        setattr(self.cfg, key, db_bool)
                        log.info("summary_toggle_changed", key=key, value=db_val)
                        changed = True

            # Provider URLs from DB
            url_map = {"ollama_url": "ollama_base_url",
                       "openai_url": "openai_base_url",
                       "routerai_url": "routerai_base_url"}
            for db_key, cfg_attr in url_map.items():
                db_val = await self.db.get_setting(db_key)
                if db_val and db_val != getattr(self.cfg, cfg_attr, None):
                    setattr(self.cfg, cfg_attr, db_val)
                    log.info("provider_url_changed", key=db_key, url=db_val)
                    changed = True

            if changed:
                self._create_services()
        except Exception as e:
            log.warning("config_check_failed", error=str(e))

    async def _run_summarization(self):
        if not getattr(self.cfg, "summary_enabled", True):
            log.info("hourly_summary_disabled")
            return
        devices = await self.db.list_devices()
        for d in devices:
            if not self._running:
                return
            if self.cfg.ai_enabled and d.get("ai_enabled", True):
                await self.summarizer.run_for_device(d["id"], d.get("hostname", ""))
                await asyncio.sleep(180)  # 3 min between devices

    async def _run_daily_summarization(self):
        if not getattr(self.cfg, "daily_summary_enabled", True):
            log.info("daily_summary_disabled")
            return
        devices = await self.db.list_devices()
        for d in devices:
            if self.cfg.ai_enabled and d.get("ai_enabled", True):
                await self.summarizer.run_daily_for_device(d["id"], d.get("hostname", ""))

    async def _run_anomaly_detection(self):
        devices = await self.db.list_devices()
        for d in devices:
            if d["enabled"]:
                await self.anomaly_detector.run_for_device(d["id"], d.get("ai_enabled", True), d.get("hostname", ""))

    async def _run_embeddings(self):
        if self.cfg.ai_enabled:
            await self.embeddings.process_unembedded()
