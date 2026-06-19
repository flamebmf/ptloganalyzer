# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
import datetime
import structlog

from app.ai import create_provider
from app.ai.prompts import SUMMARIZE_LANG_PROMPTS

log = structlog.get_logger()


class Summarizer:
    def __init__(self, config, db):
        self.cfg = config
        self.db = db
        self.provider = create_provider(config, task="summarization")
        self.language = getattr(config, "ai_language", "ru")

    def _prompts(self):
        return SUMMARIZE_LANG_PROMPTS.get(self.language, SUMMARIZE_LANG_PROMPTS["ru"])

    async def run_for_device(self, device_id: int, device_name: str = ""):
        if not self.provider:
            log.warning("ai_disabled_skip_summary", device_id=device_id, device_name=device_name)
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        period_end = now.replace(minute=0, second=0, microsecond=0)
        period_start = period_end - datetime.timedelta(hours=1)

        existing = await self.db.fetchval(
            "SELECT 1 FROM summaries "
            "WHERE device_id = $1 AND summary_type = 'period' "
            "AND period_start = $2 AND period_end = $3",
            device_id, period_start, period_end,
        )
        if existing:
            return  # already done for this hour

        limit = self.cfg.summary_max_logs or 500
        logs = await self.db.fetch(
            "SELECT id, ts, facility, severity, app_name, message "
            "FROM syslog_messages WHERE device_id = $1 "
            "AND ts > $2 AND ts <= $3 "
            "ORDER BY ts "
            "LIMIT $4",
            device_id, period_start, period_end, limit,
        )
        logs_list = [dict(r) for r in logs]

        p = self._prompts()
        if not logs_list:
            log.info("empty_period_skipped", device_id=device_id, device_name=device_name,
                      period_start=period_start.isoformat())
            return

        try:
            log_lines = "\n".join(
                f"#{l.get('id','?')} [{l['ts']}] {l.get('app_name','-')}"
                f" sev={l.get('severity','?')}: {l['message']}"
                for l in logs_list[:self.cfg.summary_max_logs]
            )
            summary = await self.provider.chat([
                {"role": "system", "content": p["system_hourly"]},
                {"role": "user", "content": p["user_hourly"].format(log_lines=log_lines)},
            ])
            await self.db.insert_summary(
                device_id, period_start, period_end, summary,
                model=f"{self.cfg.ai_provider}/{self.provider.chat_model}",
                summary_type="period",
            )
            log.info("summary_created", device_id=device_id, device_name=device_name,
                      period_start=period_start.isoformat(), logs_count=len(logs_list))
        except Exception as e:
            log.warning("summary_failed", device_id=device_id, device_name=device_name, error=repr(e))

    async def run_daily_for_device(self, device_id: int, device_name: str = ""):
        if not self.provider:
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        yesterday = now - datetime.timedelta(hours=24)

        summaries = await self.db.get_summaries_in_range(
            device_id, yesterday, now, summary_type="period",
        )
        if not summaries:
            log.info("no_hourly_summaries_for_daily", device_id=device_id, device_name=device_name)
            return

        try:
            daily_text = await self._summarize_daily(summaries)
            await self.db.insert_summary(
                device_id, yesterday, now, daily_text,
                model=f"{self.cfg.ai_provider}/{self.provider.chat_model}",
                summary_type="daily",
            )
            log.info("daily_summary_created", device_id=device_id, device_name=device_name,
                      summaries_count=len(summaries))
        except Exception as e:
            log.warning("daily_summary_failed", device_id=device_id, device_name=device_name, error=repr(e), type=type(e).__name__)

    async def _summarize_daily(self, summaries: list[dict]) -> str:
        p = self._prompts()
        summaries_text = "\n\n---\n\n".join(
            f"Period: {s['period_start']} — {s['period_end']}\n{s['summary']}"
            for s in summaries
        )
        prompt = p["user_daily_header"].format(summaries_text=summaries_text)
        return await self.provider.chat([
            {"role": "system", "content": p["system_daily"]},
            {"role": "user", "content": prompt},
        ])
