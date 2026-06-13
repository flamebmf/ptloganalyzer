# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
import asyncio
import json
import time

from fastapi import APIRouter, Request

from app.main import db

router = APIRouter(tags=["sse"])


@router.get("/sse/events")
async def sse_events(request: Request):
    async def event_stream():
        last_anomaly_id = 0
        while True:
            if await request.is_disconnected():
                break

            # Check for new anomalies
            anomalies = await db.fetch(
                "SELECT id, device_id, severity, title, description, detected_at "
                "FROM anomalies WHERE id > $1 ORDER BY id LIMIT 10",
                last_anomaly_id,
            )
            for a in anomalies:
                data = json.dumps({
                    "type": "anomaly",
                    "id": a["id"],
                    "device_id": a["device_id"],
                    "severity": a["severity"],
                    "title": a["title"],
                    "description": a["description"],
                    "detected_at": a["detected_at"].isoformat(),
                })
                yield f"event: anomaly\ndata: {data}\n\n"
                last_anomaly_id = max(last_anomaly_id, a["id"])

            # Heartbeat
            yield f"event: heartbeat\ndata: {time.time()}\n\n"
            await asyncio.sleep(5)

    return _sse_response(event_stream())


def _sse_response(stream):
    # Manual SSE response since FastAPI/Starlette needs custom streaming
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
