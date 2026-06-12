from fastapi import APIRouter, Query

from app.main import db

router = APIRouter(tags=["anomalies"])


@router.get("/anomalies")
async def list_anomalies(
    device_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    results = await db.list_anomalies(
        device_id=device_id,
        limit=limit,
        offset=offset,
    )
    return {"items": results, "limit": limit, "offset": offset}
