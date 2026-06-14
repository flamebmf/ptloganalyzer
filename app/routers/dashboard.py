# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from app.main import db

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/history")
async def dashboard_history():
    volume = await db.fetch(
        "SELECT hour, SUM(count)::int AS count "
        "FROM log_stats_hourly "
        "WHERE hour > date_trunc('hour', NOW() - INTERVAL '24 hours') "
        "GROUP BY hour ORDER BY hour"
    )
    volume_yesterday = await db.fetch(
        "SELECT hour + INTERVAL '24 hours' AS hour, SUM(count)::int AS count "
        "FROM log_stats_hourly "
        "WHERE hour BETWEEN date_trunc('hour', NOW() - INTERVAL '48 hours') "
        "AND date_trunc('hour', NOW() - INTERVAL '24 hours') "
        "GROUP BY hour ORDER BY hour"
    )
    severity = await db.fetch(
        "SELECT severity, SUM(count)::int AS count "
        "FROM log_stats_hourly "
        "WHERE hour > date_trunc('hour', NOW() - INTERVAL '24 hours') "
        "GROUP BY severity ORDER BY severity"
    )
    total = sum(r["count"] for r in volume) if volume else 0
    top_errors = await db.fetch(
        "SELECT COALESCE(d.name, d.hostname, host(d.ip)) AS hostname, SUM(s.count)::int AS errors "
        "FROM log_stats_hourly s "
        "JOIN devices d ON d.id = s.device_id "
        "WHERE s.hour > date_trunc('hour', NOW() - INTERVAL '24 hours') "
        "AND s.severity <= 3 "
        "GROUP BY d.id, d.hostname, d.name, d.ip ORDER BY errors DESC LIMIT 5"
    )
    per_device = await db.fetch(
        "SELECT COALESCE(d.name, d.hostname, host(d.ip)) AS hostname, SUM(s.count)::int AS count "
        "FROM log_stats_hourly s "
        "JOIN devices d ON d.id = s.device_id "
        "WHERE s.hour > date_trunc('hour', NOW() - INTERVAL '24 hours') "
        "GROUP BY d.id, d.hostname, d.name, d.ip ORDER BY count DESC"
    )
    top_apps = await db.fetch(
        "SELECT app_name, COUNT(*)::int AS count "
        "FROM syslog_messages "
        "WHERE ts > NOW() - INTERVAL '24 hours' AND app_name IS NOT NULL AND app_name != '-' "
        "GROUP BY app_name ORDER BY count DESC LIMIT 10"
    )
    volume_week = await db.fetch(
        "SELECT date_trunc('day', hour) AS day, SUM(count)::int AS count "
        "FROM log_stats_hourly "
        "WHERE hour > NOW() - INTERVAL '7 days' "
        "GROUP BY day ORDER BY day"
    )
    volume_week_prev = await db.fetch(
        "SELECT date_trunc('day', hour + INTERVAL '7 days') AS day, SUM(count)::int AS count "
        "FROM log_stats_hourly "
        "WHERE hour BETWEEN NOW() - INTERVAL '14 days' AND NOW() - INTERVAL '7 days' "
        "GROUP BY day ORDER BY day"
    )
    volume_month = await db.fetch(
        "SELECT date_trunc('day', hour) AS day, SUM(count)::int AS count "
        "FROM log_stats_hourly "
        "WHERE hour > NOW() - INTERVAL '30 days' "
        "GROUP BY day ORDER BY day"
    )
    volume_month_prev = await db.fetch(
        "SELECT date_trunc('day', hour + INTERVAL '30 days') AS day, SUM(count)::int AS count "
        "FROM log_stats_hourly "
        "WHERE hour BETWEEN NOW() - INTERVAL '60 days' AND NOW() - INTERVAL '30 days' "
        "GROUP BY day ORDER BY day"
    )
    anomaly_trend = await db.fetch(
        "SELECT date_trunc('hour', detected_at) AS hour, COUNT(*) AS count "
        "FROM anomalies WHERE detected_at > NOW() - INTERVAL '24 hours' "
        "GROUP BY hour ORDER BY hour"
    )
    return {
        "volume": [dict(r) for r in volume],
        "volume_yesterday": [dict(r) for r in volume_yesterday],
        "volume_week": [dict(r) for r in volume_week],
        "volume_week_prev": [dict(r) for r in volume_week_prev],
        "volume_month": [dict(r) for r in volume_month],
        "volume_month_prev": [dict(r) for r in volume_month_prev],
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
