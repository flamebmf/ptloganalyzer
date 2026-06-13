# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
from datetime import datetime, timezone

from fastapi import APIRouter, Query

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
    volume_yesterday = await db.fetch(
        "SELECT date_trunc('hour', ts + INTERVAL '24 hours') AS hour, COUNT(*) AS count "
        "FROM syslog_messages "
        "WHERE ts BETWEEN NOW() - INTERVAL '48 hours' AND NOW() - INTERVAL '24 hours' "
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
    anomaly_trend = await db.fetch(
        "SELECT date_trunc('hour', detected_at) AS hour, COUNT(*) AS count "
        "FROM anomalies WHERE detected_at > NOW() - INTERVAL '24 hours' "
        "GROUP BY hour ORDER BY hour"
    )
    return {
        "volume": [dict(r) for r in volume],
        "volume_yesterday": [dict(r) for r in volume_yesterday],
        "severity": [dict(r) for r in severity],
        "total": total or 0,
        "top_errors": [dict(r) for r in top_errors],
        "per_device": [dict(r) for r in per_device],
        "top_apps": [dict(r) for r in top_apps],
        "anomaly_trend": [dict(r) for r in anomaly_trend],
    }


@router.get("/dashboard/storage")
async def dashboard_storage():
    db_size = await db.fetchval(
        "SELECT pg_database_size(current_database())"
    )
    total_logs = await db.fetchval(
        "SELECT COUNT(*) FROM syslog_messages"
    )
    oldest = await db.fetchval(
        "SELECT MIN(ts) FROM syslog_messages"
    )
    avg_per_day = await db.fetchval(
        "SELECT COUNT(*) / NULLIF(EXTRACT(DAY FROM NOW() - MIN(ts)), 0) "
        "FROM syslog_messages"
    )
    return {
        "db_size": db_size or 0,
        "total_logs": total_logs or 0,
        "oldest_log": oldest.isoformat() if oldest else None,
        "avg_per_day": round(avg_per_day or 0),
    }


@router.get("/dashboard/logtail")
async def dashboard_logtail(limit: int = Query(20, ge=1, le=100)):
    rows = await db.fetch(
        "SELECT m.id, m.ts, m.severity, m.app_name, m.message, "
        "COALESCE(d.name, d.hostname, host(d.ip)) AS device "
        "FROM syslog_messages m "
        "JOIN devices d ON d.id = m.device_id "
        "ORDER BY m.id DESC LIMIT $1",
        limit,
    )
    items = []
    for r in rows:
        items.append({
            "id": r["id"],
            "ts": r["ts"].isoformat(),
            "severity": r["severity"],
            "app_name": r["app_name"],
            "message": r["message"],
            "device": r["device"],
        })
    items.reverse()
    return {"items": items}
