import asyncio
import structlog

from app.config import Config
from app.collector.server import SyslogServer


async def main():
    log = structlog.get_logger()
    cfg = Config()

    server = SyslogServer(cfg)
    try:
        await server.start()
    except Exception as e:
        log.error("collector_start_failed", error=str(e))
        raise

    log.info("collector_started", port=cfg.collector_port,
             udp=cfg.collector_udp, tcp=cfg.collector_tcp)

    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        log.info("collector_stopping")
    except Exception as e:
        log.error("collector_crashed", error=str(e))
        raise
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
