# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
import structlog

log = structlog.get_logger()

from app.main import db
from app.collector.app_parsers import APP_PARSERS

router = APIRouter(tags=["app_metrics"])


@router.get("/app-metrics/list")
async def list_app_metrics(device_id: int):
    rows = await db.fetch(
        "SELECT DISTINCT app_id FROM app_metrics "
        "WHERE device_id = $1 ORDER BY app_id",
        device_id,
    )
    return {"apps": [r["app_id"] for r in rows]}


@router.get("/app-metrics/series")
async def get_app_series(
    device_id: int = Query(...),
    app_id: str = Query(...),
    hours: int = Query(24, ge=1, le=168),
):
    rows = await db.fetch(
        "SELECT ts, fields FROM app_metrics "
        "WHERE device_id = $1 AND app_id = $2 "
        "AND ts > NOW() - ($3 || ' hours')::INTERVAL "
        "ORDER BY ts",
        device_id, app_id, str(hours),
    )
    items = []
    for r in rows:
        f = r["fields"]
        if isinstance(f, str):
            import json
            f = json.loads(f)
        items.append({"ts": r["ts"].isoformat(), "fields": f})
    return {"items": items}


class DeviceAppToggle(BaseModel):
    app_id: str
    enabled: bool


@router.get("/device-apps/{device_id}")
async def get_device_apps(device_id: int):
    rows = await db.fetch(
        "SELECT app_id, enabled FROM device_apps WHERE device_id = $1",
        device_id,
    )
    apps = {r["app_id"]: r["enabled"] for r in rows}
    for aid in APP_PARSERS:
        if aid not in apps:
            apps[aid] = True  # new parsers enabled by default
    return apps


@router.patch("/device-apps/{device_id}")
async def update_device_app(device_id: int, data: DeviceAppToggle):
    if data.enabled:
        await db.execute(
            "INSERT INTO device_apps (device_id, app_id, enabled) "
            "VALUES ($1, $2, true) "
            "ON CONFLICT (device_id, app_id) DO UPDATE SET enabled = true",
            device_id, data.app_id,
        )
    else:
        await db.execute(
            "DELETE FROM device_apps WHERE device_id = $1 AND app_id = $2",
            device_id, data.app_id,
        )
    return {"ok": True}


@router.get("/app-metrics/stats")
async def get_app_stats(
    device_id: int = Query(...),
    app_id: str = Query(...),
    dim: str = Query(...),
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(10, ge=1, le=50),
    metric: str | None = Query(None),
):
    """Aggregate app_metrics by dimension (srcip, dstip, app, srcintf, etc)."""
    dim_col = f"fields->>'{dim}'"
    valid = {"srcip", "dstip", "srcintf", "dstintf", "app", "policy", "action", "service",
             "policyname", "appcat", "srcport", "dstport", "proto", "osname"}
    if dim not in valid:
        raise HTTPException(400, f"Invalid dim: {dim}. Valid: {', '.join(sorted(valid))}")

    where_dim = f"fields ? '{dim}'"
    # Choose aggregation metric
    if metric == "sentbyte":
        agg = f"COALESCE(SUM((fields->>'sentbyte')::bigint), 0)"
        order = "sentbyte DESC"
    elif metric == "rcvdbyte":
        agg = f"COALESCE(SUM((fields->>'rcvdbyte')::bigint), 0)"
        order = "rcvdbyte DESC"
    elif metric == "duration":
        agg = f"COALESCE(SUM((fields->>'duration')::bigint), 0)"
        order = "duration DESC"
    else:
        agg = "COUNT(*)"
        order = "sessions DESC"

    rows = await db.fetch(
        f"SELECT {dim_col} AS label, {agg} AS value, COUNT(*) AS sessions "
        "FROM app_metrics "
        "WHERE device_id = $1 AND app_id = $2 "
        f"AND ts > NOW() - ($3 || ' hours')::INTERVAL "
        f"AND {where_dim} "
        f"GROUP BY {dim_col} "
        f"ORDER BY {order} "
        "LIMIT $4",
        device_id, app_id, str(hours), limit,
    )
    return {"items": [dict(r) for r in rows], "dim": dim}
