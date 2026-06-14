# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
import datetime
import structlog

from app.ai import create_provider

log = structlog.get_logger()


LANG_PROMPTS = {
    "ru": {
        "system_hourly": (
            "Ты — эксперт по анализу системных логов и сетевой безопасности. "
            "Отвечай только на русском языке. "
            "Будь конкретным, ссылайся на номера логов (#ID) и время. "
            "Используй разделители === для секций."
        ),
        "user_hourly": (
            "Проведи глубокий анализ syslog-сообщений. "
            "Ответь на русском языке, используй чёткую структуру:\n\n"
            "=== ОБЩАЯ ИНФОРМАЦИЯ ===\n"
            "• Диапазон времени, общее кол-во сообщений, распределение по severity\n\n"
            "=== КЛЮЧЕВЫЕ СОБЫТИЯ ===\n"
            "• 3-5 самых важных событий с номерами логов (#NNN) и временем\n"
            "• Для каждого: что произошло, почему важно\n\n"
            "=== ПРИЛОЖЕНИЯ И СЛУЖБЫ ===\n"
            "• Топ приложений по количеству сообщений и ошибок\n\n"
            "=== АНОМАЛИИ И ПОДОЗРИТЕЛЬНАЯ АКТИВНОСТЬ ===\n"
            "• Повторяющиеся ошибки, всплески, необычные паттерны\n"
            "• Укажи ID логов для каждой аномалии\n\n"
            "=== РЕКОМЕНДАЦИИ ===\n"
            "• Что нужно проверить или исправить\n\n"
            "Логи для анализа:\n{log_lines}"
        ),
        "empty_placeholder": "нет данных для отчета за требуемый период",
        "error_placeholder": "ошибка генерации отчета",
        "system_daily": (
            "Ты — эксперт по анализу системных логов. Составляй ежедневные отчёты "
            "на основе почасовых анализов. Отвечай только на русском языке. "
            "Будь конкретным, давай практические рекомендации. "
            "ОБЯЗАТЕЛЬНО сохраняй ссылки на номера логов (#NNN) в ответе."
        ),
        "user_daily_header": (
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
            "Почасовые анализы для обобщения:\n{summaries_text}"
        ),
    },
    "en": {
        "system_hourly": (
            "You are an expert in system log analysis and network security. "
            "Answer in English only. "
            "Be specific, reference log numbers (#ID) and time. "
            "Use === as section dividers."
        ),
        "user_hourly": (
            "Perform a deep analysis of syslog messages. "
            "Answer in English, use a clear structure:\n\n"
            "=== GENERAL INFORMATION ===\n"
            "• Time range, total messages, severity distribution\n\n"
            "=== KEY EVENTS ===\n"
            "• 3-5 most important events with log numbers (#NNN) and time\n"
            "• For each: what happened, why it matters\n\n"
            "=== APPLICATIONS AND SERVICES ===\n"
            "• Top applications by message count and errors\n\n"
            "=== ANOMALIES AND SUSPICIOUS ACTIVITY ===\n"
            "• Recurring errors, spikes, unusual patterns\n"
            "• Include log IDs for each anomaly\n\n"
            "=== RECOMMENDATIONS ===\n"
            "• What to check or fix\n\n"
            "Logs for analysis:\n{log_lines}"
        ),
        "empty_placeholder": "no data available for the requested period",
        "error_placeholder": "error generating report",
        "system_daily": (
            "You are an expert in system log analysis. Compile daily reports "
            "based on hourly log analyses. Answer in English only. "
            "Be specific, give practical recommendations. "
            "ALWAYS keep log number references (#NNN) in the response."
        ),
        "user_daily_header": (
            "Based on hourly syslog analyses for the last 24 hours, "
            "compile a daily report. Answer in English, use a clear structure:\n\n"
            "=== GENERAL INFORMATION ===\n"
            "• Overall device state for the day, stability\n\n"
            "=== KEY EVENTS ===\n"
            "• 3-5 most important events of the day with time and log numbers (#NNN)\n"
            "• Dynamics: what issues appeared, what got resolved\n\n"
            "=== TRENDS AND PATTERNS ===\n"
            "• Recurring errors or issues throughout the day\n"
            "• Changes in log intensity, anomalous spikes\n\n"
            "=== OVERALL CONCLUSIONS ===\n"
            "• Device stability: normal / has issues / critical\n\n"
            "=== RECOMMENDATIONS ===\n"
            "• Specific actions for each identified event with log numbers (#NNN)\n"
            "• Priority: what needs immediate attention\n\n"
            "IMPORTANT: always keep log number references (#NNN) from the source "
            "analyses in the response. Each event mention must have at least one #ID.\n\n"
            "Hourly analyses to summarize:\n{summaries_text}"
        ),
    },
}


class Summarizer:
    def __init__(self, config, db):
        self.cfg = config
        self.db = db
        self.provider = create_provider(config)
        self.language = getattr(config, "ai_language", "ru")

    def _prompts(self):
        return LANG_PROMPTS.get(self.language, LANG_PROMPTS["ru"])

    async def run_for_device(self, device_id: int):
        if not self.provider:
            log.warning("ai_disabled_skip_summary", device_id=device_id)
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

        logs = await self.db.fetch(
            "SELECT id, ts, facility, severity, app_name, message "
            "FROM syslog_messages WHERE device_id = $1 "
            "AND ts > $2 AND ts <= $3 ORDER BY ts",
            device_id, period_start, period_end,
        )

        p = self._prompts()
        if not logs:
            await self.db.insert_summary(
                device_id, period_start, period_end,
                p["empty_placeholder"],
                model=None, summary_type="period",
            )
            log.info("empty_period_skipped", device_id=device_id,
                      period_start=period_start.isoformat())
            return

        logs_list = [dict(r) for r in logs]
        try:
            log_lines = "\n".join(
                f"#{l.get('id','?')} [{l['ts']}] {l.get('app_name','-')}"
                f" sev={l.get('severity','?')}: {l['message']}"
                for l in logs_list[:200]
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
            log.info("summary_created", device_id=device_id,
                      period_start=period_start.isoformat(), logs_count=len(logs_list))
        except Exception as e:
            log.warning("summary_failed", device_id=device_id, error=repr(e))
            await self.db.insert_summary(
                device_id, period_start, period_end,
                p["error_placeholder"], model=None, summary_type="period",
            )

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
