# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
from fastapi import APIRouter, Query, HTTPException

from app.main import db, config
from app.ai.embeddings import EmbeddingService

router = APIRouter(tags=["logs"])


@router.get("/logs/{log_id}")
async def get_log(log_id: int):
    row = await db.get_log_by_id(log_id)
    if not row:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "not found"}, status_code=404)
    return row


@router.get("/logs/similar")
async def search_similar_logs(
    q: str = Query(..., min_length=1),
    device_id: int | None = None,
    limit: int = Query(20, ge=1, le=100),
):
    if not config.ai_enabled:
        raise HTTPException(503, "AI disabled")
    svc = EmbeddingService(config, db)
    results = await svc.search_similar(q, device_id=device_id, limit=limit)
    return {"items": results, "query": q, "limit": limit}


@router.get("/logs")
async def search_logs(
    device_id: int | None = None,
    severity: int | None = None,
    facility: int | None = None,
    query: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    return await db.search_logs(
        device_id=device_id,
        severity=severity,
        facility=facility,
        query=query,
        limit=limit,
        offset=offset,
    )


@router.get("/diagnostics/linked")
async def diagnostics_linked():
    """Check linked_ips/linked_names status in syslog_messages."""
    total = await db.fetchval("SELECT COUNT(*) FROM syslog_messages")
    with_links = await db.fetchval(
        "SELECT COUNT(*) FROM syslog_messages WHERE linked_ips IS NOT NULL"
    )
    recent = await db.fetch(
        "SELECT id, ts, linked_ips, linked_names "
        "FROM syslog_messages WHERE linked_ips IS NOT NULL "
        "ORDER BY id DESC LIMIT 3"
    )
    cols = await db.fetch(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'syslog_messages' "
        "AND column_name IN ('linked_ips', 'linked_names', 'source_ip')"
    )
    return {
        "columns_exist": [c["column_name"] for c in cols],
        "total_rows": total,
        "rows_with_links": with_links,
        "recent_with_links": [dict(r) for r in recent],
    }
