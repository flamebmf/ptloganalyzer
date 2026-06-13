# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
import datetime

from fastapi import APIRouter, Query

from app.main import db

router = APIRouter(tags=["summaries"])


@router.get("/summaries")
async def list_summaries(
    device_id: int | None = None,
    summary_type: str | None = None,
    date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    tz_offset: int = 0,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    dt_from = None
    dt_to = None
    if date:
        try:
            d = datetime.date.fromisoformat(date)
            offset_minutes = datetime.timedelta(minutes=tz_offset)
            dt_from = datetime.datetime(d.year, d.month, d.day, tzinfo=datetime.timezone.utc) - offset_minutes
            dt_to = dt_from + datetime.timedelta(days=1)
        except ValueError:
            pass
    if date_from and not dt_from:
        try:
            d = datetime.date.fromisoformat(date_from)
            offset_minutes = datetime.timedelta(minutes=tz_offset)
            dt_from = datetime.datetime(d.year, d.month, d.day, tzinfo=datetime.timezone.utc) - offset_minutes
        except ValueError:
            pass
    if date_to and not dt_to:
        try:
            d = datetime.date.fromisoformat(date_to)
            offset_minutes = datetime.timedelta(minutes=tz_offset)
            dt_to = datetime.datetime(d.year, d.month, d.day, tzinfo=datetime.timezone.utc) - offset_minutes
        except ValueError:
            pass

    return await db.search_summaries(
        device_id=device_id,
        summary_type=summary_type,
        date_from=dt_from,
        date_to=dt_to,
        limit=limit,
        offset=offset,
    )