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


@router.get("/devices")
async def list_devices():
    return await db.list_devices()


@router.get("/devices/bulk-data")
async def bulk_data():
    # Stats for all devices in one query
    stats_rows = await db.fetch(
        "SELECT device_id, COUNT(*) AS total, MAX(ts) AS last_seen, "
        "COUNT(*) FILTER (WHERE severity <= 3) AS errors "
        "FROM syslog_messages GROUP BY device_id"
    )
    stats = {}
    for r in stats_rows:
        online = r["last_seen"] and (datetime.now(timezone.utc) - r["last_seen"]).total_seconds() < 300
        stats[r["device_id"]] = {
            "total": r["total"], "last_seen": r["last_seen"],
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
    # Mini-chart data for all devices in one query
    chart_rows = await db.fetch(
        "SELECT device_id, date_trunc('hour', ts) AS hour, severity, COUNT(*) AS count "
        "FROM syslog_messages "
        "WHERE ts > NOW() - INTERVAL '24 hours' "
        "GROUP BY device_id, hour, severity ORDER BY device_id, hour"
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


@router.get("/devices/{device_id}")
async def get_device(device_id: int):
    dev = await db.get_device(device_id)
    if not dev:
        raise HTTPException(404, "Device not found")
    return dev


@router.patch("/devices/{device_id}")
async def update_device(device_id: int, data: DeviceUpdate):
    kwargs = {k: v for k, v in data.model_dump().items() if v is not None}
    if not kwargs:
        raise HTTPException(400, "No fields to update")
    await db.update_device(device_id, **kwargs)
    return await db.get_device(device_id)


@router.get("/devices/{device_id}/history")
async def device_history(device_id: int):
    volume = await db.fetch(
        "SELECT date_trunc('hour', ts) AS hour, COUNT(*) AS count "
        "FROM syslog_messages "
        "WHERE device_id = $1 AND ts > NOW() - INTERVAL '48 hours' "
        "GROUP BY hour ORDER BY hour",
        device_id,
    )
    severity = await db.fetch(
        "SELECT severity, COUNT(*) AS count "
        "FROM syslog_messages "
        "WHERE device_id = $1 AND ts > NOW() - INTERVAL '48 hours' "
        "GROUP BY severity ORDER BY severity",
        device_id,
    )
    sev_timeline_raw = await db.fetch(
        "SELECT date_trunc('hour', ts) AS hour, severity, COUNT(*) AS count "
        "FROM syslog_messages "
        "WHERE device_id = $1 AND ts > NOW() - INTERVAL '24 hours' "
        "GROUP BY hour, severity ORDER BY hour, severity",
        device_id,
    )
    sev_labels = ['Emerg','Alert','Crit','Err','Warning','Notice','Info','Debug']
    buckets = {}
    for r in sev_timeline_raw:
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
    return dict(row) if row else {"total": 0}
