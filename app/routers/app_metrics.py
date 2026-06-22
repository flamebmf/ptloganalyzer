# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
import json
import re
from pathlib import Path

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import structlog

log = structlog.get_logger()

from app.main import db
from app.collector.app_parsers import APP_PARSERS

router = APIRouter(tags=["app_metrics"])
_MANIFEST_DIR = Path(__file__).resolve().parent.parent / "manifests"


@router.get("/app-manifest/{app_id}")
async def get_app_manifest(app_id: str):
    """Return unified manifest (parser config + panel definitions) for an app."""
    fpath = _MANIFEST_DIR / f"{app_id}.json"
    if not fpath.is_file():
        raise HTTPException(404, f"No manifest for app '{app_id}'")
    return JSONResponse(content=json.loads(fpath.read_text()))


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
    filter: str | None = Query(None),
):
    """Aggregate app_metrics by dimension. Optional filter like 'action:deny' or 'type:utm'."""
    dim_col = f"fields->>'{dim}'"
    valid = {"srcip", "dstip", "srcintf", "dstintf", "app", "policy", "action", "service",
             "policyname", "appcat", "srcport", "dstport", "proto", "osname", "type", "subtype",
             "attack", "severity", "eventtype", "direction", "crlevel", "hostname", "url",
             "srccountry", "dstcountry", "httpmethod", "agent", "msg", "profile", "ref",
             "process", "event", "peerip", "peerport", "_metric"}
    if dim not in valid:
        raise HTTPException(400, f"Invalid dim: {dim}. Valid: {', '.join(sorted(valid))}")

    where_dim = f"jsonb_exists(fields, '{dim}')"
    filter_sql = ""
    filter_args = []
    if filter and ':' in filter:
        fk, fv = filter.split(':', 1)
        fi = 5  # next $ position
        filter_sql = f" AND fields->>'{fk}' = ${fi}"
        filter_args.append(fv)

    # Choose aggregation metric
    if metric == "sentbyte":
        agg = f"COALESCE(SUM((fields->>'sentbyte')::bigint), 0)"
        order = "value DESC"
    elif metric == "rcvdbyte":
        agg = f"COALESCE(SUM((fields->>'rcvdbyte')::bigint), 0)"
        order = "value DESC"
    elif metric == "duration":
        agg = f"COALESCE(SUM((fields->>'duration')::bigint), 0)"
        order = "value DESC"
    else:
        agg = "COUNT(*)"
        order = "sessions DESC"

    rows = await db.fetch(
        f"SELECT {dim_col} AS label, {agg} AS value, COUNT(*) AS sessions "
        "FROM app_metrics "
        "WHERE device_id = $1 AND app_id = $2 "
        f"AND ts > NOW() - ($3 || ' hours')::INTERVAL "
        f"AND {where_dim} "
        f"{filter_sql} "
        f"GROUP BY {dim_col} "
        f"ORDER BY {order} "
        "LIMIT $4",
        device_id, app_id, str(hours), limit, *filter_args,
    )
    return {"items": [dict(r) for r in rows], "dim": dim}


_FIELD_RE = re.compile(r'^[a-zA-Z0-9_:\-/.%]+$')


@router.get("/app-metrics/field-series")
async def get_field_series(
    device_id: int = Query(...),
    app_id: str = Query(...),
    field: str = Query(...),
    hours: int = Query(24, ge=1, le=168),
    bucket: str = Query("hour", regex=r"^(hour|day)$"),
    agg: str = Query("avg", regex=r"^(avg|max|min|sum)$"),
):
    """Time-series of a numeric JSONB field aggregated into time buckets."""
    if not _FIELD_RE.match(field):
        raise HTTPException(400, f"Invalid field name: {field}")
    numeric_re = "^[-]?[0-9]+[.]?[0-9]*$"
    rows = await db.fetch(
        "SELECT date_trunc($4, ts) AS bucket, "
        f"ROUND({agg}(NULLIF(TRIM((fields->>'{field}')::text), '')::numeric), 2) AS value "
        "FROM app_metrics "
        "WHERE device_id = $1 AND app_id = $2 "
        "AND ts > NOW() - ($3 || ' hours')::INTERVAL "
        f"AND (fields->>'{field}')::text ~ '{numeric_re}' "
        "GROUP BY bucket ORDER BY bucket",
        device_id, app_id, str(hours), bucket,
    )
    return {"items": [{"ts": r["bucket"].isoformat(), "value": float(r["value"]) if r["value"] is not None else None} for r in rows], "field": field}
