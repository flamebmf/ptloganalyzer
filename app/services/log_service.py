from app.main import db


class LogService:
    @staticmethod
    async def get_log_volume(device_id: int, hours: int = 24) -> list[dict]:
        rows = await db.fetch(
            "SELECT date_trunc('hour', ts) AS hour, COUNT(*) AS count "
            "FROM syslog_messages WHERE device_id = $1 "
            "AND ts > NOW() - ($2 || ' hours')::INTERVAL "
            "GROUP BY hour ORDER BY hour",
            device_id, str(hours),
        )
        return [dict(r) for r in rows]

    @staticmethod
    async def get_severity_distribution(device_id: int, hours: int = 24) -> list[dict]:
        rows = await db.fetch(
            "SELECT severity, COUNT(*) AS count "
            "FROM syslog_messages WHERE device_id = $1 "
            "AND ts > NOW() - ($2 || ' hours')::INTERVAL "
            "GROUP BY severity ORDER BY severity",
            device_id, str(hours),
        )
        return [dict(r) for r in rows]

    @staticmethod
    async def get_recent_logs(device_id: int, limit: int = 50) -> list[dict]:
        return await db.search_logs(device_id=device_id, limit=limit)
