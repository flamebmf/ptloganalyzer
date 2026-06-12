import datetime
import structlog

from app.ai import create_provider

log = structlog.get_logger()


class Summarizer:
    def __init__(self, config, db):
        self.cfg = config
        self.db = db
        self.provider = create_provider(config)

    async def run_for_device(self, device_id: int):
        if not self.provider:
            log.warning("ai_disabled_skip_summary", device_id=device_id)
            return

        # Get latest summary timestamp
        last = await self.db.fetchval(
            "SELECT MAX(period_end) FROM summaries WHERE device_id = $1",
            device_id,
        )
        if not last:
            last = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)

        # Fetch logs since last summary
        logs = await self.db.fetch(
            "SELECT id, ts, facility, severity, app_name, message "
            "FROM syslog_messages WHERE device_id = $1 "
            "AND ts > $2 ORDER BY ts LIMIT $3",
            device_id, last, self.cfg.summary_max_logs,
        )

        if not logs:
            return

        period_start = logs[0]["ts"]
        period_end = logs[-1]["ts"]
        logs_list = [dict(r) for r in logs]

        try:
            summary = await self.provider.summarize(logs_list)
            summary_id = await self.db.insert_summary(
                device_id, period_start, period_end, summary,
                model=f"{self.cfg.ai_provider}/{self.provider.chat_model}",
            )
            log.info("summary_created", device_id=device_id,
                      summary_id=summary_id, logs_count=len(logs_list))
        except Exception as e:
            log.warning("summary_failed", device_id=device_id, error=repr(e), type=type(e).__name__)
