# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
from fastapi import APIRouter, Query, HTTPException
import re

from app.main import db, config
from app.ai import create_provider
from app.ai.prompts import RECOMMEND_PROMPT

router = APIRouter(tags=["anomalies"])


@router.get("/anomalies")
async def list_anomalies(
    device_id: int | None = None,
    resolved: bool | None = None,
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    result = await db.list_anomalies(
        device_id=device_id, limit=limit, offset=offset, resolved=resolved,
        min_severity=config.anomaly_min_severity,
    )
    result["limit"] = limit
    result["offset"] = offset
    return result


@router.delete("/anomalies/resolved")
async def delete_resolved_anomalies():
    total = await db.fetchval("SELECT COUNT(*) FROM anomalies WHERE resolved_at IS NOT NULL")
    await db.execute("DELETE FROM anomalies WHERE resolved_at IS NOT NULL")
    return {"ok": True, "deleted": total}


@router.post("/anomalies/{anomaly_id}/recommend")
async def recommend_anomaly(anomaly_id: int, refresh: bool = False):
    anomaly = await db.fetchrow(
        "SELECT a.*, d.hostname, d.ip, d.name FROM anomalies a "
        "JOIN devices d ON d.id = a.device_id WHERE a.id = $1",
        anomaly_id,
    )
    if not anomaly:
        raise HTTPException(404, "Anomaly not found")

    # Return cached recommendation if exists and no refresh requested
    if not refresh and anomaly.get("recommendation"):
        return {"recommendation": anomaly["recommendation"], "cached": True}

    # Fetch related log messages mentioned in the description
    log_ids = set()
    desc_text = anomaly["description"] or ''
    for m in re.finditer(r'#(\d+)', desc_text):
        log_ids.add(int(m.group(1)))
    related_logs = []
    if log_ids:
        log_ids_list = sorted(log_ids)[:30]
        placeholders = ','.join(str(i) for i in log_ids_list)
        rows = await db.fetch(
            f"SELECT id, ts, severity, app_name, message FROM syslog_messages "
            f"WHERE id IN ({placeholders}) ORDER BY ts"
        )
        related_logs = [dict(r) for r in rows]

    device_name = anomaly["name"] or anomaly["hostname"] or ""
    device_ip = anomaly["ip"] or ""
    log_summary = ""
    if related_logs:
        log_summary = "\nСвязанные логи:\n" + "\n".join(
            f"#{r['id']} {r['ts']} sev={r['severity']} app={r['app_name'] or '-'}: {r['message'][:200]}"
            for r in related_logs[:10]
        )
        if len(related_logs) > 10:
            log_summary += f"\n... и ещё {len(related_logs) - 10} записей"

    prompt = RECOMMEND_PROMPT.format(
        device_name=device_name,
        device_ip=device_ip,
        title=anomaly['title'],
        severity=anomaly['severity'],
        count=anomaly.get('count') or 1,
        description=desc_text or '(нет)',
        log_summary=log_summary,
    )

    provider = create_provider(config)
    if not provider:
        return {"error": "AI не настроен", "recommendation": ""}

    try:
        recommendation = await provider.chat([
            {"role": "user", "content": prompt},
        ], temperature=0.3, max_tokens=4096)
        # Save to DB
        await db.execute(
            "UPDATE anomalies SET recommendation = $1 WHERE id = $2",
            recommendation, anomaly_id,
        )
        return {"recommendation": recommendation, "cached": False}
    except Exception as e:
        return {"error": str(e), "recommendation": ""}
