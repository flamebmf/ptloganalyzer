# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
import asyncio
import structlog

from app.config import Config
from app.ai_worker.scheduler import Scheduler
from app.version import APP_VERSION

log = structlog.get_logger()


async def main():
    cfg = Config()
    log.info("ai_worker_starting", version=APP_VERSION, provider=cfg.ai_provider,
             enabled=cfg.ai_enabled)

    scheduler = Scheduler(cfg)
    await scheduler.start()

    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        log.info("ai_worker_stopping")
    finally:
        await scheduler.stop()


if __name__ == "__main__":
    asyncio.run(main())
