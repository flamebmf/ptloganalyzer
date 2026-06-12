from fastapi import APIRouter

from app.main import db

router = APIRouter(tags=["summaries"])


@router.get("/summaries")
async def list_summaries(device_id: int):
    return await db.get_recent_summaries(device_id)
