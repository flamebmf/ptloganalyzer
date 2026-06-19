# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
import asyncio
from datetime import datetime, timedelta, timezone
from time import time

from fastapi import APIRouter, Query

from app.main import db
import structlog
_log = structlog.get_logger()

router = APIRouter(tags=["dashboard"])

_storage_cache = None
_storage_cache_ts = 0
_top_apps_cache = None
_top_apps_cache_ts = 0
_history_cache = None
_history_cache_ts = 0


@router.get("/dashboard/history")
async def dashboard_history():
    global _history_cache, _history_cache_ts
    t0 = time()
    if time() - _history_cache_ts < 300 and _history_cache:
        return _history_cache

    now = datetime.now(timezone.utc)
    rounded_now = now.replace(minute=0, second=0, microsecond=0)
    cutoff_day = rounded_now - timedelta(hours=24)
    cutoff_48h = rounded_now - timedelta(hours=48)
    cutoff_week = rounded_now - timedelta(days=7)
    cutoff_14d = rounded_now - timedelta(days=14)
    cutoff_month = rounded_now - timedelta(days=30)
    cutoff_60d = rounded_now - timedelta(days=60)

    async def q(sql, *args):
        return await db.fetch(sql, *args)

    volume_sql = (
        "SELECT hour, SUM(count)::int AS count "
        "FROM log_stats_hourly WHERE hour > $1 GROUP BY hour ORDER BY hour"
    )
    vol_today = q(volume_sql, cutoff_day)
    vol_yesterday = q(
        "SELECT hour + INTERVAL '24 hours' AS hour, SUM(count)::int AS count "
        "FROM log_stats_hourly WHERE hour BETWEEN $1 AND $2 GROUP BY hour ORDER BY hour",
        cutoff_48h, cutoff_day,
    )
    severity_q = q(
        "SELECT severity, SUM(count)::int AS count "
        "FROM log_stats_hourly WHERE hour > $1 GROUP BY severity ORDER BY severity",
        cutoff_day,
    )
    top_errors_q = q(
        "SELECT COALESCE(d.name, d.hostname, host(d.ip)) AS hostname, t.cnt::int AS errors "
        "FROM ("
        "  SELECT device_id, SUM(count) AS cnt "
        "  FROM log_stats_hourly WHERE hour > $1 AND severity <= 3 "
        "  GROUP BY device_id ORDER BY cnt DESC LIMIT 5"
        ") t JOIN devices d ON d.id = t.device_id "
        "ORDER BY errors DESC",
        cutoff_day,
    )
    per_device_q = q(
        "SELECT COALESCE(d.name, d.hostname, host(d.ip)) AS hostname, t.cnt::int AS count "
        "FROM ("
        "  SELECT device_id, SUM(count) AS cnt "
        "  FROM log_stats_hourly WHERE hour > $1 "
        "  GROUP BY device_id"
        ") t JOIN devices d ON d.id = t.device_id "
        "ORDER BY count DESC",
        cutoff_day,
    )
    week_q = q(
        "SELECT date_trunc('day', hour) AS day, SUM(count)::int AS count "
        "FROM log_stats_hourly WHERE hour > $1 GROUP BY day ORDER BY day",
        cutoff_week,
    )
    week_prev_q = q(
        "SELECT date_trunc('day', hour + INTERVAL '7 days') AS day, SUM(count)::int AS count "
        "FROM log_stats_hourly WHERE hour BETWEEN $1 AND $2 GROUP BY day ORDER BY day",
        cutoff_14d, cutoff_week,
    )
    month_q = q(
        "SELECT date_trunc('day', hour) AS day, SUM(count)::int AS count "
        "FROM log_stats_hourly WHERE hour > $1 GROUP BY day ORDER BY day",
        cutoff_month,
    )
    month_prev_q = q(
        "SELECT date_trunc('day', hour + INTERVAL '30 days') AS day, SUM(count)::int AS count "
        "FROM log_stats_hourly WHERE hour BETWEEN $1 AND $2 GROUP BY day ORDER BY day",
        cutoff_60d, cutoff_month,
    )
    anomaly_q = q(
        "SELECT date_trunc('hour', detected_at) AS hour, COUNT(*) AS count "
        "FROM anomalies WHERE detected_at > $1 GROUP BY hour ORDER BY hour",
        cutoff_day,
    )

    # Top apps fetch runs in background (don't block dashboard)
    global _top_apps_cache, _top_apps_cache_ts
    if time() - _top_apps_cache_ts > 300:
        asyncio.create_task(_refresh_top_apps())

    all_results = await asyncio.gather(
        vol_today, vol_yesterday, severity_q, top_errors_q, per_device_q,
        week_q, week_prev_q, month_q, month_prev_q, anomaly_q,
    )

    (volume, volume_yesterday, severity, top_errors, per_device,
     volume_week, volume_week_prev, volume_month, volume_month_prev,
     anomaly_trend) = all_results


async def _refresh_top_apps():
    global _top_apps_cache, _top_apps_cache_ts
    try:
        rows = await asyncio.wait_for(
            db.fetch(
                "SELECT app_name, COUNT(*)::int AS count "
                "FROM syslog_messages "
                "WHERE ts > NOW() - INTERVAL '24 hours' AND app_name IS NOT NULL AND app_name != '-' "
                "GROUP BY app_name ORDER BY count DESC LIMIT 10"
            ),
            timeout=10,
        )
        _top_apps_cache = rows
        _top_apps_cache_ts = time()
    except Exception:
        pass

    total = sum(r["count"] for r in volume) if volume else 0

    # Compute trend forecast (linear regression)
    anomaly_forecast = []
    if len(anomaly_trend) >= 3:
        pts = [dict(r) for r in anomaly_trend]
        n = len(pts)
        sum_x = sum(i for i in range(n))
        sum_y = sum(p["count"] for p in pts)
        sum_xy = sum(i * p["count"] for i, p in enumerate(pts))
        sum_xx = sum(i * i for i in range(n))
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x * sum_x) if (n * sum_xx - sum_x * sum_x) else 0
        intercept = (sum_y - slope * sum_x) / n
        for i, p in enumerate(pts):
            y = max(0, round(intercept + slope * i, 1))
            if y > 0:
                anomaly_forecast.append({"hour": p["hour"], "count": y})
        next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        y_next = max(0, round(intercept + slope * n, 1))
        if y_next > 0:
            anomaly_forecast.append({"hour": next_hour, "count": y_next})
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
        "top_apps": [dict(r) for r in top_apps_rows] if top_apps_rows else [],
        "anomaly_trend": [dict(r) for r in anomaly_trend],
        "anomaly_forecast": anomaly_forecast,
    }
    _history_cache = result
    _history_cache_ts = time()
    _log.info("dashboard_history_done", elapsed_ms=int((time()-t0)*1000))
    return result


@router.get("/dashboard/storage")
async def dashboard_storage():
    global _storage_cache, _storage_cache_ts
    if time() - _storage_cache_ts <= 300 and _storage_cache:
        return _storage_cache
    results = await asyncio.gather(
        db.fetchval("SELECT pg_database_size(current_database())"),
        db.fetchval("SELECT COALESCE(SUM(count), 0)::bigint FROM log_stats_hourly"),
        db.fetchval("SELECT MIN(hour) FROM log_stats_hourly"),
    )
    db_size, total_logs, oldest = results
    avg_per_day = 0
    if oldest and total_logs:
        days = max((datetime.now(timezone.utc) - oldest).days, 1)
        avg_per_day = total_logs / days
    _storage_cache = {
        "db_size": db_size or 0,
        "total_logs": total_logs or 0,
        "oldest_log": oldest.isoformat() if oldest else None,
        "avg_per_day": round(avg_per_day or 0),
    }
    _storage_cache_ts = time()
    return _storage_cache


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
