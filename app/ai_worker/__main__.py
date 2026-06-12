import asyncio
import structlog

from app.config import Config
from app.ai_worker.scheduler import Scheduler

log = structlog.get_logger()


async def main():
    cfg = Config()
    log.info("ai_worker_starting", provider=cfg.ai_provider,
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
