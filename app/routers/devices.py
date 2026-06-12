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


@router.get("/devices")
async def list_devices():
    return await db.list_devices()


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
