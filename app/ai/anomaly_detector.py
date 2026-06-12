import structlog
from collections import Counter

from app.ai import create_provider

log = structlog.get_logger()


class AnomalyDetector:
    def __init__(self, config, db):
        self.cfg = config
        self.db = db
        self.provider = create_provider(config)

    async def run_for_device(self, device_id: int):
        # Always run statistical detectors (no AI needed)
        await self._check_volume(device_id)
        await self._check_error_flood(device_id)
        await self._check_duplicate_burst(device_id)
        await self._check_app_spike(device_id)

        # AI-based content analysis (only if provider configured)
        if self.provider:
            await self._check_ai_content(device_id)

    async def _check_volume(self, device_id: int):
        baseline = await self.db.fetchrow(
            "SELECT AVG(cnt) AS avg_per_hour, "
            "STDDEV(cnt) AS std_per_hour "
            "FROM ("
            "  SELECT date_trunc('hour', ts) AS h, COUNT(*) AS cnt "
            "  FROM syslog_messages WHERE device_id = $1 "
            "  AND ts > NOW() - INTERVAL '7 days' "
            "  GROUP BY h"
            ") sub",
            device_id,
        )
        recent = await self.db.fetchrow(
            "SELECT COUNT(*) AS cnt FROM syslog_messages "
            "WHERE device_id = $1 AND ts > NOW() - INTERVAL '1 hour'",
            device_id,
        )
        if baseline and baseline["std_per_hour"] and baseline["std_per_hour"] > 0:
            z_score = (recent["cnt"] - baseline["avg_per_hour"]) / baseline["std_per_hour"]
            if abs(z_score) > 3:
                await self.db.insert_anomaly(
                    device_id,
                    "critical" if abs(z_score) > 5 else "warning",
                    "Anomalous log volume detected",
                    f"Device {device_id}: {recent['cnt']} logs in last hour "
                    f"(avg={baseline['avg_per_hour']:.0f}, z-score={z_score:.2f})",
                )
                log.warning("volume_anomaly", device_id=device_id,
                             z_score=z_score, count=recent["cnt"])

    async def _check_error_flood(self, device_id: int):
        recent = await self.db.fetch(
            "SELECT COUNT(*) AS cnt, MAX(ts) AS last_ts "
            "FROM syslog_messages "
            "WHERE device_id = $1 AND ts > NOW() - INTERVAL '15 minutes' "
            "AND severity <= 3",
            device_id,
        )
        row = recent[0] if recent else None
        if not row or not row["cnt"]:
            return

        # Compare to 24h error rate
        total = await self.db.fetchrow(
            "SELECT COUNT(*) AS cnt FROM syslog_messages "
            "WHERE device_id = $1 AND ts > NOW() - INTERVAL '24 hours' "
            "AND severity <= 3",
            device_id,
        )
        total_errors = total["cnt"] if total else 0
        if total_errors < 10:
            return

        flood_ratio = row["cnt"] / max(total_errors, 1) * 100
        if flood_ratio > 30 and row["cnt"] >= 10:
            await self.db.insert_anomaly(
                device_id, "warning",
                "Error rate spike",
                f"{row['cnt']} errors in 15 min ({flood_ratio:.0f}% of 24h total)",
            )
            log.warning("error_flood", device_id=device_id,
                         count=row["cnt"], pct=flood_ratio)

    async def _check_duplicate_burst(self, device_id: int):
        rows = await self.db.fetch(
            "SELECT message, COUNT(*) AS cnt "
            "FROM syslog_messages "
            "WHERE device_id = $1 AND ts > NOW() - INTERVAL '5 minutes' "
            "GROUP BY message HAVING COUNT(*) >= 10 "
            "ORDER BY cnt DESC LIMIT 5",
            device_id,
        )
        for r in rows:
            msg = r["message"]
            short = msg[:80] + ("..." if len(msg) > 80 else "")
            await self.db.insert_anomaly(
                device_id, "warning" if r["cnt"] < 50 else "critical",
                "Message flood detected",
                f"'{short}' repeated {r['cnt']}x in 5 min",
            )
            log.warning("message_flood", device_id=device_id,
                         count=r["cnt"], message=short)

    async def _check_app_spike(self, device_id: int):
        recent_apps = await self.db.fetch(
            "SELECT app_name, COUNT(*) AS cnt "
            "FROM syslog_messages "
            "WHERE device_id = $1 AND ts > NOW() - INTERVAL '15 minutes' "
            "AND app_name IS NOT NULL AND app_name != '-' "
            "GROUP BY app_name ORDER BY cnt DESC LIMIT 5",
            device_id,
        )
        if not recent_apps:
            return

        baseline_apps = await self.db.fetch(
            "SELECT app_name, AVG(cnt) AS avg_cnt "
            "FROM ("
            "  SELECT app_name, date_trunc('hour', ts) AS h, COUNT(*) AS cnt "
            "  FROM syslog_messages WHERE device_id = $1 "
            "  AND ts > NOW() - INTERVAL '7 days' AND ts < NOW() - INTERVAL '1 hour' "
            "  GROUP BY app_name, h"
            ") sub "
            "GROUP BY app_name",
            device_id,
        )
        avg_map = {r["app_name"]: r["avg_cnt"] for r in baseline_apps}

        for r in recent_apps:
            aname = r["app_name"]
            recent_cnt = r["cnt"]
            avg_cnt = avg_map.get(aname, 0)
            if avg_cnt > 0 and recent_cnt > avg_cnt * 5 and recent_cnt >= 20:
                await self.db.insert_anomaly(
                    device_id, "warning",
                    f"Application spike: {aname}",
                    f"{recent_cnt} logs in 15 min (avg={avg_cnt:.0f}/h, {recent_cnt/avg_cnt:.0f}x)",
                )
                log.warning("app_spike", device_id=device_id,
                             app=aname, count=recent_cnt, avg=avg_cnt)

    async def _check_ai_content(self, device_id: int):
        recent = await self.db.fetch(
            "SELECT id, ts, facility, severity, app_name, message "
            "FROM syslog_messages WHERE device_id = $1 "
            "AND ts > NOW() - INTERVAL '15 minutes' "
            "AND severity <= 3 "
            "ORDER BY ts DESC LIMIT 100",
            device_id,
        )
        if not recent or len(recent) < 3:
            return
        try:
            anomalies = await self.provider.detect_anomalies(
                [dict(r) for r in recent],
                baseline=None,
            )
            for a in anomalies:
                if isinstance(a, dict) and "title" in a:
                    await self.db.insert_anomaly(
                        device_id,
                        a.get("severity", "warning"),
                        a["title"],
                        a.get("description"),
                    )
                    log.info("ai_anomaly_detected", device_id=device_id,
                              title=a["title"])
        except Exception as e:
            log.error("ai_anomaly_detection_failed",
                       device_id=device_id, error=repr(e), type=type(e).__name__)
