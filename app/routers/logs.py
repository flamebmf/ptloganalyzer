from fastapi import APIRouter, Query

from app.main import db

router = APIRouter(tags=["logs"])


@router.get("/logs")
async def search_logs(
    device_id: int | None = None,
    severity: int | None = None,
    facility: int | None = None,
    query: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    results = await db.search_logs(
        device_id=device_id,
        severity=severity,
        facility=facility,
        query=query,
        limit=limit,
        offset=offset,
    )
    return {"items": results, "limit": limit, "offset": offset}
