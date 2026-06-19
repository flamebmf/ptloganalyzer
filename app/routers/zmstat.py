# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
from fastapi import APIRouter, Query
from pydantic import BaseModel

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
    return {"items": [{"ts": r["ts"].isoformat(), "fields": dict(r["fields"])} for r in rows]}


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
            apps[aid] = False
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
