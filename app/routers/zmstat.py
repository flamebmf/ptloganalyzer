# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
from fastapi import APIRouter, Query

from app.main import db

router = APIRouter(tags=["zmstat"])


@router.get("/zmstat/metrics")
async def list_zmstat_metrics(device_id: int | None = None):
    """List available zmstat metric names for a device (or all)."""
    if device_id:
        rows = await db.fetch(
            "SELECT DISTINCT metric_name FROM zmstat_metrics "
            "WHERE device_id = $1 ORDER BY metric_name",
            device_id,
        )
    else:
        rows = await db.fetch(
            "SELECT DISTINCT metric_name FROM zmstat_metrics ORDER BY metric_name"
        )
    return {"metrics": [r["metric_name"] for r in rows]}


@router.get("/zmstat/series")
async def get_zmstat_series(
    device_id: int = Query(...),
    metric: str = Query(...),
    hours: int = Query(24, ge=1, le=168),
):
    """Return time series for a given zmstat metric on a device."""
    rows = await db.fetch(
        "SELECT ts, fields FROM zmstat_metrics "
        "WHERE device_id = $1 AND metric_name = $2 "
        "AND ts > NOW() - ($3 || ' hours')::INTERVAL "
        "ORDER BY ts",
        device_id, metric, str(hours),
    )
    return {"items": [{"ts": r["ts"].isoformat(), "fields": dict(r["fields"])} for r in rows]}
