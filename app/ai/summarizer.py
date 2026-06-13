# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
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

        last = await self.db.fetchval(
            "SELECT MAX(period_end) FROM summaries "
            "WHERE device_id = $1 AND summary_type = 'period'",
            device_id,
        )
        if not last:
            last = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)

        now = datetime.datetime.now(datetime.timezone.utc)
        hour_start = now.replace(minute=0, second=0, microsecond=0)

        if last.year <= 1970:
            # Первый запуск — берём последний завершённый час
            period_end = hour_start
        else:
            period_end = last + datetime.timedelta(hours=1)

        if period_end > now:
            return  # ещё не прошёл час, ждём

        period_start = period_end - datetime.timedelta(hours=1)

        logs = await self.db.fetch(
            "SELECT id, ts, facility, severity, app_name, message "
            "FROM syslog_messages WHERE device_id = $1 "
            "AND ts > $2 AND ts <= $3 ORDER BY ts",
            device_id, period_start, period_end,
        )

        if not logs:
            return
        logs_list = [dict(r) for r in logs]

        try:
            summary = await self.provider.summarize(logs_list)
            summary_id = await self.db.insert_summary(
                device_id, period_start, period_end, summary,
                model=f"{self.cfg.ai_provider}/{self.provider.chat_model}",
                summary_type="period",
            )
            log.info("summary_created", device_id=device_id,
                      summary_id=summary_id, logs_count=len(logs_list))
        except Exception as e:
            log.warning("summary_failed", device_id=device_id, error=repr(e), type=type(e).__name__)

    async def run_daily_for_device(self, device_id: int):
        if not self.provider:
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        yesterday = now - datetime.timedelta(hours=24)

        summaries = await self.db.get_summaries_in_range(
            device_id, yesterday, now, summary_type="period",
        )
        if not summaries:
            log.info("no_hourly_summaries_for_daily", device_id=device_id)
            return

        try:
            daily_text = await self._summarize_daily(summaries)
            await self.db.insert_summary(
                device_id, yesterday, now, daily_text,
                model=f"{self.cfg.ai_provider}/{self.provider.chat_model}",
                summary_type="daily",
            )
            log.info("daily_summary_created", device_id=device_id,
                      summaries_count=len(summaries))
        except Exception as e:
            log.warning("daily_summary_failed", device_id=device_id, error=repr(e), type=type(e).__name__)

    async def _summarize_daily(self, summaries: list[dict]) -> str:
        summaries_text = "\n\n---\n\n".join(
            f"Период: {s['period_start']} — {s['period_end']}\n{s['summary']}"
            for s in summaries
        )
        prompt = (
            "На основе почасовых анализов syslog-логов за последние 24 часа составь "
            "ежедневный отчёт. Ответь на русском языке, используй чёткую структуру:\n\n"
            "=== ОБЩАЯ ИНФОРМАЦИЯ ===\n"
            "• Общее состояние устройства за день, стабильность работы\n\n"
            "=== КЛЮЧЕВЫЕ СОБЫТИЯ ===\n"
            "• 3-5 самых важных событий за день с указанием времени и номеров логов (#NNN)\n"
            "• Динамика: какие проблемы возникли, какие решились\n\n"
            "=== ТРЕНДЫ И ПАТТЕРНЫ ===\n"
            "• Повторяющиеся ошибки или проблемы в течение дня\n"
            "• Изменение интенсивности логов, аномальные всплески\n\n"
            "=== ОБЩИЕ ВЫВОДЫ ===\n"
            "• Стабильность устройства: нормально / есть проблемы / критично\n\n"
            "=== РЕКОМЕНДАЦИИ ===\n"
            "• Конкретные действия по каждому выявленному событию с номерами логов (#NNN)\n"
            "• Приоритет: что требует немедленного внимания\n\n"
            "ВАЖНО: в ответе обязательно сохраняй ссылки на номера логов (#NNN) из исходных "
            "анализов. Каждое упоминание события должно сопровождаться хотя бы одним #ID.\n\n"
            "Почасовые анализы для обобщения:\n" + summaries_text
        )
        return await self.provider.chat([
            {"role": "system", "content": (
                "Ты — эксперт по анализу системных логов. Составляй ежедневные отчёты "
                "на основе почасовых анализов. Отвечай только на русском языке. "
                "Будь конкретным, давай практические рекомендации. "
                "ОБЯЗАТЕЛЬНО сохраняй ссылки на номера логов (#NNN) в ответе."
            )},
            {"role": "user", "content": prompt},
        ])