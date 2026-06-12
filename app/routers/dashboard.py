from fastapi import APIRouter

from app.main import db

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/history")
async def dashboard_history():
    volume = await db.fetch(
        "SELECT date_trunc('hour', ts) AS hour, COUNT(*) AS count "
        "FROM syslog_messages "
        "WHERE ts > NOW() - INTERVAL '24 hours' "
        "GROUP BY hour ORDER BY hour"
    )
    severity = await db.fetch(
        "SELECT severity, COUNT(*) AS count "
        "FROM syslog_messages "
        "WHERE ts > NOW() - INTERVAL '24 hours' "
        "GROUP BY severity ORDER BY severity"
    )
    total = await db.fetchval(
        "SELECT COUNT(*) FROM syslog_messages "
        "WHERE ts > NOW() - INTERVAL '24 hours'"
    )
    top_errors = await db.fetch(
        "SELECT d.hostname, COUNT(*) AS errors "
        "FROM syslog_messages m "
        "JOIN devices d ON d.id = m.device_id "
        "WHERE m.severity <= 3 AND m.ts > NOW() - INTERVAL '24 hours' "
        "GROUP BY d.id, d.hostname ORDER BY errors DESC LIMIT 5"
    )
    per_device = await db.fetch(
        "SELECT d.hostname, COUNT(*) AS count "
        "FROM syslog_messages m "
        "JOIN devices d ON d.id = m.device_id "
        "WHERE m.ts > NOW() - INTERVAL '24 hours' "
        "GROUP BY d.id, d.hostname ORDER BY count DESC"
    )
    top_apps = await db.fetch(
        "SELECT app_name, COUNT(*) AS count "
        "FROM syslog_messages "
        "WHERE ts > NOW() - INTERVAL '24 hours' AND app_name IS NOT NULL AND app_name != '-' "
        "GROUP BY app_name ORDER BY count DESC LIMIT 10"
    )
    return {
        "volume": [dict(r) for r in volume],
        "severity": [dict(r) for r in severity],
        "total": total or 0,
        "top_errors": [dict(r) for r in top_errors],
        "per_device": [dict(r) for r in per_device],
        "top_apps": [dict(r) for r in top_apps],
    }
