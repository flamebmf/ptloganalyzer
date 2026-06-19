# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.main import db

router = APIRouter(tags=["devices"])


class DeviceUpdate(BaseModel):
    name: str | None = None
    ip: str | None = None
    description: str | None = None
    device_type: str | None = None
    enabled: bool | None = None
    ai_enabled: bool | None = None
    template_id: int | None = None


@router.get("/devices")
async def list_devices():
    devices = await db.list_devices()
    last_seen_rows = await db.fetch(
        "SELECT device_id, ts AS last_seen FROM device_last_seen"
    )
    ls_map = {r["device_id"]: r["last_seen"] for r in last_seen_rows}
    stats_rows = await db.fetch(
        "SELECT device_id, SUM(count)::int AS total "
        "FROM log_stats_hourly GROUP BY device_id"
    )
    stats_map = {r["device_id"]: r["total"] for r in stats_rows}
    now = datetime.now(timezone.utc)
    for d in devices:
        ts = ls_map.get(d["id"])
        d["last_seen"] = ts
        d["online"] = bool(ts and (now - ts).total_seconds() < 300)
        d["total"] = stats_map.get(d["id"], 0)
    return devices


@router.get("/devices/bulk-data")
async def bulk_data():
    # Stats for all devices in one query
    # Aggregate stats from hourly summary (much faster than scanning syslog_messages)
    stats_rows = await db.fetch(
        "SELECT device_id, SUM(count)::int AS total, "
        "SUM(count) FILTER (WHERE severity <= 3)::int AS errors "
        "FROM log_stats_hourly "
        "GROUP BY device_id"
    )
    last_seen_rows = await db.fetch(
        "SELECT device_id, ts AS last_seen FROM device_last_seen"
    )
    ls_map = {r["device_id"]: r["last_seen"] for r in last_seen_rows}
    stats = {}
    for r in stats_rows:
        did = r["device_id"]
        ts = ls_map.get(did)
        online = ts and (datetime.now(timezone.utc) - ts).total_seconds() < 300
        stats[did] = {
            "total": r["total"], "last_seen": ts,
            "errors": r["errors"], "online": online,
        }
    # Anomaly counts per device
    anom_rows = await db.fetch(
        "SELECT device_id, COUNT(*) AS cnt FROM anomalies "
        "WHERE resolved_at IS NULL GROUP BY device_id"
    )
    for r in anom_rows:
        did_key = r["device_id"]  # int
        if did_key in stats:
            stats[did_key]["anomalies"] = r["cnt"]
        else:
            stats[did_key] = {"anomalies": r["cnt"]}
    # Last AI summary per device
    summary_rows = await db.fetch(
        "SELECT device_id, MAX(created_at) AS last_summary_at "
        "FROM summaries WHERE summary_type IN ('period', 'daily') "
        "GROUP BY device_id"
    )
    for r in summary_rows:
        did = r["device_id"]
        if did in stats:
            stats[did]["last_summary_at"] = r["last_summary_at"]
        else:
            stats[did] = {"last_summary_at": r["last_summary_at"]}
    # Mini-chart data for all devices
    chart_rows = await db.fetch(
        "SELECT device_id, hour, severity, count "
        "FROM log_stats_hourly "
        "WHERE hour > date_trunc('hour', NOW() - INTERVAL '24 hours') "
        "ORDER BY device_id, hour"
    )
    sev_labels = ['Emerg','Alert','Crit','Err','Warning','Notice','Info','Debug']
    dev_data = {}
    for r in chart_rows:
        did = r["device_id"]
        if did not in dev_data:
            dev_data[did] = {}
        h = r["hour"].isoformat() if hasattr(r["hour"], 'isoformat') else str(r["hour"])
        if h not in dev_data[did]:
            dev_data[did][h] = {s: 0 for s in range(8)}
        dev_data[did][h][r["severity"]] = r["count"]
    sev_labels = ['Emerg','Alert','Crit','Err','Warning','Notice','Info','Debug']
    result = {}
    for did, buckets in dev_data.items():
        cats = sorted(buckets.keys())
        series = []
        for s in range(8):
            vals = [buckets[h][s] for h in cats]
            if sum(vals) > 0:
                series.append({"name": sev_labels[s], "data": vals})
        if series:
            result[did] = {"categories": cats, "series": series}
    return {"stats": stats, "charts": result}


@router.get("/parse-templates")
async def list_templates():
    return await db.list_templates()

@router.get("/devices/{device_id}")
async def get_device(device_id: int):
    dev = await db.get_device(device_id)
    if not dev:
        raise HTTPException(404, "Device not found")
    return dev


@router.patch("/devices/{device_id}")
async def update_device(device_id: int, data: DeviceUpdate):
    kwargs = {k: v for k, v in data.model_dump().items() if v is not None}
    # Allow explicitly setting template_id to null to clear template
    if data.template_id is None and "template_id" in data.model_dump(exclude_unset=True):
        kwargs["template_id"] = None
    if not kwargs:
        raise HTTPException(400, "No fields to update")
    await db.update_device(device_id, **kwargs)
    return await db.get_device(device_id)


@router.get("/devices/{device_id}/history")
async def device_history(device_id: int):
    volume = await db.fetch(
        "SELECT hour, SUM(count)::int AS count "
        "FROM log_stats_hourly "
        "WHERE device_id = $1 AND hour > date_trunc('hour', NOW() - INTERVAL '48 hours') "
        "GROUP BY hour ORDER BY hour",
        device_id,
    )
    severity = await db.fetch(
        "SELECT severity, SUM(count)::int AS count "
        "FROM log_stats_hourly "
        "WHERE device_id = $1 AND hour > date_trunc('hour', NOW() - INTERVAL '48 hours') "
        "GROUP BY severity ORDER BY severity",
        device_id,
    )
    sev_timeline = await db.fetch(
        "SELECT hour, severity, count "
        "FROM log_stats_hourly "
        "WHERE device_id = $1 AND hour > date_trunc('hour', NOW() - INTERVAL '24 hours') "
        "ORDER BY hour, severity",
        device_id,
    )
    sev_labels = ['Emerg','Alert','Crit','Err','Warning','Notice','Info','Debug']
    buckets = {}
    for r in sev_timeline:
        h = r["hour"].isoformat() if hasattr(r["hour"], 'isoformat') else str(r["hour"])
        if h not in buckets:
            buckets[h] = {s: 0 for s in range(8)}
        buckets[h][r["severity"]] = r["count"]
    categories = sorted(buckets.keys())
    series = [{"name": sev_labels[s], "data": [buckets[h][s] for h in categories]} for s in range(8)]
    return {
        "volume": [dict(r) for r in volume],
        "severity": [dict(r) for r in severity],
        "severity_timeline": {"categories": categories, "series": series},
    }


@router.post("/devices/{device_id}/clear-logs")
async def clear_device_logs(device_id: int):
    dev = await db.get_device(device_id)
    if not dev:
        raise HTTPException(404, "Device not found")
    deleted = await db.clear_device_logs(device_id)
    return {"ok": True, "device_id": device_id, "deleted": deleted}


@router.delete("/devices/{device_id}")
async def delete_device(device_id: int):
    dev = await db.get_device(device_id)
    if not dev:
        raise HTTPException(404, "Device not found")
    await db.delete_device(device_id)
    return {"ok": True, "device_id": device_id}


@router.get("/devices/{device_id}/stats")
async def device_stats(device_id: int):
    row = await db.fetchrow(
        "SELECT COUNT(*) AS total, "
        "MAX(ts) AS last_seen, "
        "COUNT(*) FILTER (WHERE severity <= 3) AS errors "
        "FROM syslog_messages WHERE device_id = $1",
        device_id,
    )
    result = dict(row) if row else {"total": 0}
    ts = result.get("last_seen")
    result["online"] = bool(ts and (datetime.now(timezone.utc) - ts).total_seconds() < 300)
    return result
