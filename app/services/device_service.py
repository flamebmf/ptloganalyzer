# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
from app.main import db


class DeviceService:
    @staticmethod
    async def get_dashboard_stats() -> dict:
        total = await db.fetchval("SELECT COUNT(*) FROM devices")
        active = await db.fetchval(
            "SELECT COUNT(DISTINCT device_id) FROM syslog_messages "
            "WHERE ts > NOW() - INTERVAL '1 hour'"
        )
        recent_count = await db.fetchval(
            "SELECT COUNT(*) FROM syslog_messages "
            "WHERE ts > NOW() - INTERVAL '1 hour'"
        )
        anomaly_count = await db.fetchval(
            "SELECT COUNT(*) FROM anomalies "
            "WHERE detected_at > NOW() - INTERVAL '24 hours'"
        )
        return {
            "total_devices": total,
            "active_devices": active,
            "logs_last_hour": recent_count,
            "anomalies_24h": anomaly_count,
        }

    @staticmethod
    async def get_device_list_with_status() -> list[dict]:
        devices = await db.list_devices()
        result = []
        for d in devices:
            stats = await db.fetchrow(
                "SELECT COUNT(*) AS total, "
                "MAX(ts) AS last_seen, "
                "COUNT(*) FILTER (WHERE severity <= 3) AS errors "
                "FROM syslog_messages WHERE device_id = $1 "
                "AND ts > NOW() - INTERVAL '24 hours'",
                d["id"],
            )
            result.append({**d, **(dict(stats) if stats else {
                "total": 0, "last_seen": None, "errors": 0,
            })})
        return result
