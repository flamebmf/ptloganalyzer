# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
import asyncpg
import re
import structlog

log = structlog.get_logger()


# ── Core schema. pgvector objects are created separately so they can be added
# ── to existing databases after the core tables already exist.
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS devices (
    id          SERIAL PRIMARY KEY,
    hostname    VARCHAR(255) NOT NULL,
    ip          INET,
    name        VARCHAR(255),
    description TEXT,
    device_type VARCHAR(50) DEFAULT 'other',
    parser      VARCHAR(50) DEFAULT 'default',
    enabled     BOOLEAN DEFAULT true,
    ai_enabled  BOOLEAN DEFAULT true,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_devices_hostname ON devices(hostname);

CREATE TABLE IF NOT EXISTS syslog_messages (
    id          BIGSERIAL,
    device_id   INT NOT NULL REFERENCES devices(id),
    ts          TIMESTAMPTZ NOT NULL,
    facility    SMALLINT,
    severity    SMALLINT,
    app_name    VARCHAR(255),
    msgid       VARCHAR(64),
    message     TEXT NOT NULL,
    raw         TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (id, ts)
) PARTITION BY RANGE (ts);
CREATE TABLE IF NOT EXISTS syslog_messages_default PARTITION OF syslog_messages DEFAULT;
CREATE INDEX IF NOT EXISTS idx_syslog_device_ts ON syslog_messages(device_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_syslog_severity ON syslog_messages(severity);
CREATE INDEX IF NOT EXISTS idx_syslog_app ON syslog_messages(app_name);

DO $$ DECLARE
    rec record;
BEGIN
    FOR rec IN
        SELECT to_char(d, 'YYYYMM') AS pn,
               date_trunc('month', d)::text AS ps,
               (date_trunc('month', d + INTERVAL '1 month'))::text AS pe
        FROM generate_series(date_trunc('month', NOW()), date_trunc('month', NOW() + INTERVAL '3 months'), INTERVAL '1 month') AS d
    LOOP
        EXECUTE format('CREATE TABLE IF NOT EXISTS syslog_messages_%s PARTITION OF syslog_messages FOR VALUES FROM (''%s'') TO (''%s'')', rec.pn, rec.ps, rec.pe);
    END LOOP;
END $$;

CREATE TABLE IF NOT EXISTS summaries (
    id           SERIAL PRIMARY KEY,
    device_id    INT NOT NULL REFERENCES devices(id),
    period_start TIMESTAMPTZ NOT NULL,
    period_end   TIMESTAMPTZ NOT NULL,
    summary      TEXT NOT NULL,
    model        VARCHAR(64),
    summary_type VARCHAR(20) DEFAULT 'period',
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_summaries_device_period ON summaries(device_id, period_start DESC);

CREATE TABLE IF NOT EXISTS anomalies (
    id           SERIAL PRIMARY KEY,
    device_id    INT NOT NULL REFERENCES devices(id),
    severity     VARCHAR(20) DEFAULT 'warning',
    title        VARCHAR(255) NOT NULL,
    description  TEXT,
    detected_at  TIMESTAMPTZ DEFAULT NOW(),
    resolved_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_anomalies_device ON anomalies(device_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_anomalies_severity ON anomalies(severity);

CREATE TABLE IF NOT EXISTS log_stats_hourly (
    device_id INT NOT NULL REFERENCES devices(id),
    hour      TIMESTAMPTZ NOT NULL,
    severity  SMALLINT NOT NULL DEFAULT 6,
    count     INT NOT NULL DEFAULT 0,
    PRIMARY KEY (device_id, hour, severity)
);
"""


class Database:
    def __init__(self, config):
        self._dsn = config.db_dsn
        self._pool_min = config.db_pool_min
        self._pool_max = config.db_pool_max
        self._pool: asyncpg.Pool | None = None

    async def connect(self):
        self._pool = await asyncpg.create_pool(
            dsn=self._dsn,
            min_size=self._pool_min,
            max_size=self._pool_max,
            command_timeout=30,
        )
        await self._ensure_schema()
        await self._ensure_indexes()
        await self._seed_templates()

    async def _ensure_schema(self):
        exists = await self.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'devices')"
        )
        if not exists:
            async with self.pool.acquire() as conn:
                await conn.execute(SCHEMA_SQL)

        await self._ensure_vector_schema()
        await self._ensure_hourly_stats()

    async def _ensure_vector_schema(self):
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS log_embeddings (
                        id BIGSERIAL PRIMARY KEY,
                        log_id BIGINT NOT NULL,
                        device_id INT NOT NULL REFERENCES devices(id),
                        embedding vector,
                        model VARCHAR(64) DEFAULT 'text-embedding-3-small',
                        snippet TEXT,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_embeddings_device
                    ON log_embeddings(device_id)
                """)
        except Exception:
            pass  # pgvector не доступен — логируем без эмбеддингов

    async def _ensure_hourly_stats(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS log_stats_hourly (
                    device_id INT NOT NULL REFERENCES devices(id),
                    hour      TIMESTAMPTZ NOT NULL,
                    severity  SMALLINT NOT NULL DEFAULT 6,
                    count     INT NOT NULL DEFAULT 0,
                    PRIMARY KEY (device_id, hour, severity)
                )
            """)
            # Backfill if table is empty
            exists = await conn.fetchval("SELECT EXISTS (SELECT 1 FROM log_stats_hourly LIMIT 1)")
            if not exists:
                await conn.execute("""
                    INSERT INTO log_stats_hourly (device_id, hour, severity, count)
                    SELECT device_id, date_trunc('hour', ts) AS hour, severity, COUNT(*) AS count
                    FROM syslog_messages GROUP BY device_id, date_trunc('hour', ts), severity
                    ON CONFLICT (device_id, hour, severity) DO NOTHING
                """)
                log.info("hourly_stats_backfilled")

    async def _ensure_indexes(self):
        async with self.pool.acquire() as conn:
            # Remove duplicate IPs with cascade, keep lowest id
            dups = await conn.fetch(
                "SELECT a.id FROM devices a JOIN devices b ON a.ip = b.ip WHERE a.id > b.id AND a.ip IS NOT NULL"
            )
            dup_ids = [r["id"] for r in dups]
            if dup_ids:
                for table in ('log_embeddings', 'summaries', 'anomalies', 'syslog_messages'):
                    await conn.execute(f"DELETE FROM {table} WHERE device_id = ANY($1::int[])", dup_ids)
                await conn.execute("DELETE FROM devices WHERE id = ANY($1::int[])", dup_ids)
            await conn.execute("DROP INDEX IF EXISTS idx_devices_ip")
            try:
                await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_devices_ip ON devices(ip) WHERE ip IS NOT NULL")
            except Exception:
                pass  # non-fatal; missing unique index means duplicates are handled at app level
            await conn.execute(
                "ALTER TABLE devices DROP CONSTRAINT IF EXISTS devices_hostname_key"
            )
            await conn.execute(
                "ALTER TABLE devices ADD COLUMN IF NOT EXISTS parser VARCHAR(50) DEFAULT 'default'"
            )
            await conn.execute(
                "ALTER TABLE devices ADD COLUMN IF NOT EXISTS ai_enabled BOOLEAN DEFAULT true"
            )
            await conn.execute(
                "ALTER TABLE summaries ADD COLUMN IF NOT EXISTS summary_type VARCHAR(20) DEFAULT 'period'"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_summaries_type ON summaries(summary_type)"
            )
            await conn.execute(
                "ALTER TABLE anomalies ADD COLUMN IF NOT EXISTS last_seen TIMESTAMPTZ DEFAULT NOW()"
            )
            await conn.execute(
                "ALTER TABLE anomalies ADD COLUMN IF NOT EXISTS count INT DEFAULT 1"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_anomalies_merge ON anomalies(device_id, title)"
            )
            await conn.execute(
                "ALTER TABLE anomalies ADD COLUMN IF NOT EXISTS recommendation TEXT"
            )
            await conn.execute(
                "ALTER TABLE syslog_messages ADD COLUMN IF NOT EXISTS linked_ips TEXT[]"
            )
            await conn.execute(
                "ALTER TABLE syslog_messages ADD COLUMN IF NOT EXISTS linked_names TEXT[]"
            )
            await conn.execute(
                "ALTER TABLE syslog_messages ADD COLUMN IF NOT EXISTS source_ip INET"
            )
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS device_last_seen (
                    device_id INT NOT NULL PRIMARY KEY REFERENCES devices(id),
                    ts TIMESTAMPTZ NOT NULL
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_device_last_seen_ts "
                "ON device_last_seen(ts)"
            )
            # Backfill if empty
            has_rows = await conn.fetchval("SELECT EXISTS (SELECT 1 FROM device_last_seen LIMIT 1)")
            if not has_rows:
                await conn.execute("""
                    INSERT INTO device_last_seen (device_id, ts)
                    SELECT device_id, MAX(ts) FROM syslog_messages GROUP BY device_id
                    ON CONFLICT (device_id) DO NOTHING
                """)
                log.info("device_last_seen_backfilled")
            try:
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_syslog_linked_ips "
                    "ON syslog_messages USING GIN (linked_ips)"
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_syslog_linked_names "
                    "ON syslog_messages USING GIN (linked_names)"
                )
            except Exception:
                pass  # GIN on partitioned table needs PG14+
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_stats_hour "
                "ON log_stats_hourly(hour)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_stats_hour_severity "
                "ON log_stats_hourly(hour, severity)"
            )
            await conn.execute("ANALYZE log_stats_hourly")

            # ── Parse templates ──
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS parse_templates (
                    id          SERIAL PRIMARY KEY,
                    name        VARCHAR(100) NOT NULL UNIQUE,
                    description TEXT,
                    parser_type VARCHAR(50) NOT NULL DEFAULT 'default',
                    config      JSONB DEFAULT '{}',
                    is_builtin  BOOLEAN DEFAULT false,
                    created_at  TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute(
                "ALTER TABLE devices ADD COLUMN IF NOT EXISTS template_id INT REFERENCES parse_templates(id)"
            )

            # ── Runtime settings (key-value) ──
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    key         VARCHAR(100) PRIMARY KEY,
                    value       TEXT NOT NULL,
                    updated_at  TIMESTAMPTZ DEFAULT NOW()
                )
            """)

    async def _seed_templates(self):
        builtins = [
            ("default", "Автоопределение формата", "default", False),
            ("rfc3164_tag", "RFC3164 с извлечением APPNAME[PID]: из сообщения", "rfc3164_tag", True),
            ("aruba_iap", "Aruba IAP (Instant Access Point)", "aruba_iap", True),
        ]
        for name, desc, ptype, is_builtin in builtins:
            existing = await self.fetchval(
                "SELECT id FROM parse_templates WHERE name = $1", name
            )
            if not existing:
                await self.execute(
                    "INSERT INTO parse_templates (name, description, parser_type, is_builtin) "
                    "VALUES ($1, $2, $3, $4)",
                    name, desc, ptype, is_builtin,
                )

    async def close(self):
        if self._pool:
            await self._pool.close()

    async def backfill_links(self, batch_size: int = 10000):
        """One-shot backfill of linked_ips/linked_names for old rows (SQL-only, fast)."""
        log.info("backfill_links_started")
        done = 0
        while True:
            result = await self.execute("""
                WITH batch AS (
                    SELECT id, ts FROM syslog_messages
                    WHERE linked_ips IS NULL OR linked_names IS NULL
                    ORDER BY ts
                    LIMIT $1
                )
                UPDATE syslog_messages m SET
                    linked_ips = ARRAY(
                        SELECT m1[1] FROM regexp_matches(
                            m.message, '\\m(?:\\d{1,3}\\.){3}\\d{1,3}\\M', 'g'
                        ) AS m1
                    ),
                    linked_names = ARRAY(
                        SELECT m2[1] FROM regexp_matches(
                            m.message,
                            '\\m([a-zA-Z0-9][a-zA-Z0-9.-]*\\.[a-zA-Z]{2,}[a-zA-Z0-9.-]*)\\M',
                            'g'
                        ) AS m2
                    )
                FROM batch b
                WHERE m.id = b.id AND m.ts = b.ts
            """, batch_size)
            count = int(result.split()[-1])
            done += count
            log.info("backfill_links_batch", done=done, batch=count)
            if count < batch_size:
                break
        log.info("backfill_links_done", total=done)

    @property
    def pool(self) -> asyncpg.Pool:
        assert self._pool is not None, "Database not connected"
        return self._pool

    async def execute(self, query: str, *args):
        return await self.pool.execute(query, *args)

    async def executemany(self, query: str, args):
        async with self.pool.acquire() as conn:
            return await conn.executemany(query, args)

    async def fetch(self, query: str, *args):
        return await self.pool.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        return await self.pool.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        return await self.pool.fetchval(query, *args)

    # ── Devices ──

    async def get_or_create_device(self, hostname: str, ip: str | None = None) -> int:
        row = await self.fetchrow(
            "SELECT id FROM devices WHERE hostname = $1", hostname
        )
        if row:
            if ip:
                await self.execute(
                    "UPDATE devices SET ip = $1 WHERE id = $2", ip, row["id"]
                )
            return row["id"]
        return await self.fetchval(
            "INSERT INTO devices (hostname, ip) VALUES ($1, $2) RETURNING id",
            hostname, ip,
        )

    async def list_devices(self) -> list[dict]:
        rows = await self.fetch(
            "SELECT d.id, d.hostname, d.ip, d.name, d.device_type, "
            "d.enabled, d.ai_enabled, d.created_at, d.template_id, "
            "t.name AS template_name "
            "FROM devices d "
            "LEFT JOIN parse_templates t ON t.id = d.template_id "
            "ORDER BY d.hostname"
        )
        return [dict(r) for r in rows]

    async def get_device(self, device_id: int) -> dict | None:
        row = await self.fetchrow(
            "SELECT d.id, d.hostname, d.ip, d.name, d.device_type, "
            "d.enabled, d.ai_enabled, d.created_at, d.template_id, "
            "t.name AS template_name "
            "FROM devices d "
            "LEFT JOIN parse_templates t ON t.id = d.template_id "
            "WHERE d.id = $1", device_id
        )
        return dict(row) if row else None

    async def update_device(self, device_id: int, **kwargs):
        sets = ", ".join(f"{k} = ${i+1}" for i, k in enumerate(kwargs))
        vals = list(kwargs.values()) + [device_id]
        await self.execute(
            f"UPDATE devices SET {sets} WHERE id = ${len(kwargs)+1}", *vals
        )

    async def list_templates(self) -> list[dict]:
        rows = await self.fetch(
            "SELECT id, name, description, parser_type, config, is_builtin "
            "FROM parse_templates ORDER BY name"
        )
        return [dict(r) for r in rows]

    async def get_setting(self, key: str) -> str | None:
        row = await self.fetchrow(
            "SELECT value FROM app_settings WHERE key = $1", key
        )
        return row["value"] if row else None

    async def set_setting(self, key: str, value: str):
        await self.execute(
            "INSERT INTO app_settings (key, value, updated_at) VALUES ($1, $2, NOW()) "
            "ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = NOW()",
            key, value,
        )

    async def clear_device_logs(self, device_id: int) -> int:
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM log_embeddings WHERE device_id = $1", device_id)
            await conn.execute("DELETE FROM summaries WHERE device_id = $1", device_id)
            await conn.execute("DELETE FROM anomalies WHERE device_id = $1", device_id)
            result = await conn.execute("DELETE FROM syslog_messages WHERE device_id = $1", device_id)
            return int(result.split()[-1]) if result else 0

    async def delete_device(self, device_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM log_embeddings WHERE device_id = $1", device_id)
            await conn.execute("DELETE FROM summaries WHERE device_id = $1", device_id)
            await conn.execute("DELETE FROM anomalies WHERE device_id = $1", device_id)
            await conn.execute("DELETE FROM syslog_messages WHERE device_id = $1", device_id)
            await conn.execute("DELETE FROM devices WHERE id = $1", device_id)

    # ── Logs ──

    async def insert_log(self, device_id: int, ts, facility: int,
                          severity: int, app_name: str | None,
                          msgid: str | None, message: str, raw: str | None = None):
        return await self.fetchval(
            "INSERT INTO syslog_messages "
            "(device_id, ts, facility, severity, app_name, msgid, message, raw) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id",
            device_id, ts, facility, severity, app_name, msgid, message, raw,
        )

    async def insert_logs_batch(self, records: list[tuple]):
        if not records:
            return
        await self.pool.executemany(
            "INSERT INTO syslog_messages "
            "(device_id, ts, facility, severity, app_name, msgid, message, raw) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
            records,
        )

    async def search_logs(self, device_id: int | None = None,
                           severity: int | None = None,
                           facility: int | None = None,
                           query: str | None = None,
                           limit: int = 100, offset: int = 0):
        where = []
        args = []
        i = 1
        if device_id is not None:
            where.append(f"device_id = ${i}"); args.append(device_id); i += 1
        if severity is not None:
            where.append(f"severity = ${i}"); args.append(severity); i += 1
        if facility is not None:
            where.append(f"facility = ${i}"); args.append(facility); i += 1
        if query:
            where.append(f"message ILIKE ${i}"); args.append(f"%{query}%"); i += 1
        where_sql = " AND ".join(where) if where else "TRUE"

        # Use log_stats_hourly for count when no full-text search
        if not query and device_id is not None:
            count_args = [device_id]
            if severity is not None:
                total = await self.fetchval(
                    "SELECT COALESCE(SUM(count), 0) FROM log_stats_hourly "
                    "WHERE device_id = $1 AND severity = $2", *count_args, severity
                )
            else:
                total = await self.fetchval(
                    "SELECT COALESCE(SUM(count), 0) FROM log_stats_hourly "
                    "WHERE device_id = $1", *count_args
                )
        else:
            total = await self.fetchval(
                f"SELECT COUNT(*) FROM syslog_messages WHERE {where_sql}", *args
            )
        rows = await self.fetch(
            f"SELECT id, device_id, ts, facility, severity, app_name, message, "
            f"linked_ips, linked_names, source_ip "
            f"FROM syslog_messages WHERE {where_sql} "
            f"ORDER BY ts DESC LIMIT ${i} OFFSET ${i+1}",
            *args, limit, offset,
        )
        return {"items": [dict(r) for r in rows], "total": total or 0,
                "limit": limit, "offset": offset}

    async def get_log_by_id(self, log_id: int) -> dict | None:
        row = await self.fetchrow(
            "SELECT m.id, m.device_id, d.hostname, m.ts, m.facility, m.severity, "
            "m.app_name, m.msgid, m.message, m.raw, m.source_ip, m.linked_ips, m.linked_names, m.created_at "
            "FROM syslog_messages m JOIN devices d ON d.id = m.device_id "
            "WHERE m.id = $1", log_id
        )
        return dict(row) if row else None

    # ── Anomalies ──

    @staticmethod
    def _anomaly_keywords(text):
        t = text.lower()
        t = re.sub(r'#\d+(?:[–\-]\d+)*', '', t)
        t = re.sub(r'\d[\d:.,]*(?::\d+)?', '', t)
        t = re.sub(r'[^\w\sа-яё-]', ' ', t)
        words = t.split()
        stop = {'в','на','с','и','о','по','к','у','из','от','для','не','no','the','an','a',
                'is','as','be','or','at','to','of','in','it','with','this','that',
                'после','при','через','без','до','за','но','же','так','для','об',
                'его','ее','их','its','was','are','been','has','had', 'x', 'id'}
        sig = []
        for w in words:
            w = w.strip('-')
            if len(w) < 4 and not any(c in w for c in 'tcpipsipdnssshhttp'):
                continue
            if w in stop:
                continue
            sig.append(w[:20])
        return set(sig)

    @staticmethod
    def _anomaly_msg_fingerprint(description):
        """Extract message pattern signature from description for merge matching."""
        if not description:
            return ''
        # Try quoted patterns first
        for q in ["'", '"']:
            i = description.find(q)
            if i >= 0:
                j = description.find(q, i + 1)
                if j > i:
                    return description[i+1:j].lower().strip()[:60]
        # Try <...> for syslog messages
        i = description.find('<')
        if i >= 0:
            j = description.find('>', i)
            if j > i and j - i < 40:
                rest = description[j+1:j+80].strip()
                return rest[:60]
        # Fallback: text before "repeated" or "повтор"
        for marker in [' repeated', ' повтор']:
            idx = description.lower().find(marker)
            if idx > 10:
                return description[max(0, idx-40):idx].strip()[:60]
        return ''

    async def insert_anomaly(self, device_id: int, severity: str,
                                title: str, description: str | None = None):
        new_title_kw = self._anomaly_keywords(title)
        new_desc_kw = self._anomaly_keywords(description or '')
        new_fp = self._anomaly_msg_fingerprint(description)
        recent = await self.fetch(
            "SELECT id, title, description, count FROM anomalies "
            "WHERE device_id = $1 AND last_seen > NOW() - INTERVAL '48 hours'",
            device_id,
        )
        best_match = None
        best_score = 0
        for r in recent:
            existing_title_kw = self._anomaly_keywords(r["title"])
            existing_desc_kw = self._anomaly_keywords(r["description"] or '')
            existing_fp = self._anomaly_msg_fingerprint(r["description"])
            if not new_title_kw or not existing_title_kw:
                continue
            title_overlap = len(new_title_kw & existing_title_kw)
            desc_overlap = len(new_desc_kw & existing_desc_kw)
            title_score = title_overlap / max(len(new_title_kw), len(existing_title_kw))
            desc_score = desc_overlap / max(len(new_desc_kw), len(existing_desc_kw)) if max(len(new_desc_kw), len(existing_desc_kw)) else 0
            # If titles are very similar, require matching description fingerprint
            if title_score >= 0.8 and new_fp and existing_fp and new_fp != existing_fp:
                continue
            score = title_score * 0.6 + desc_score * 0.4
            if score > best_score:
                best_score = score
                best_match = r
        if best_match and best_score >= 0.22:
            mid = best_match["id"]
            old_desc = best_match["description"] or ""
            new_count = (best_match["count"] or 1) + 1
            merged_desc = old_desc
            if description and description not in old_desc and old_desc.count("\n——") < 3:
                merged_desc = old_desc + "\n——\n" + title + "\n" + description
            await self.execute(
                "UPDATE anomalies SET count = $1, last_seen = NOW(), title = $2, description = $3, resolved_at = NULL WHERE id = $4",
                new_count, title, merged_desc, mid,
            )
            return mid
        return await self.fetchval(
            "INSERT INTO anomalies (device_id, severity, title, description, count, last_seen) "
            "VALUES ($1,$2,$3,$4,1,NOW()) RETURNING id",
            device_id, severity, title, description,
        )

    async def list_anomalies(self, device_id: int | None = None,
                              limit: int = 50, offset: int = 0,
                              resolved: bool | None = None,
                              min_severity: str | None = None):
        # Auto-resolve stale anomalies
        await self.execute(
            "UPDATE anomalies SET resolved_at = NOW() "
            "WHERE resolved_at IS NULL AND last_seen < NOW() - INTERVAL '24 hours'"
        )
        where = "TRUE"
        args = []
        i = 1
        if device_id is not None:
            where = f"a.device_id = ${i}"
            args.append(device_id)
            i += 1
        if resolved is True:
            where += f" AND a.resolved_at IS NOT NULL"
        elif resolved is False:
            where += f" AND a.resolved_at IS NULL"
        if min_severity:
            sev_order = {"info": 0, "warning": 1, "critical": 2}
            thr = sev_order.get(min_severity, 0)
            # Inline severity rank: critical=2, warning=1, info=0
            where += f" AND CASE a.severity WHEN 'critical' THEN 2 WHEN 'warning' THEN 1 ELSE 0 END >= {thr}"
        total = await self.fetchval(
            f"SELECT COUNT(*) FROM anomalies a WHERE {where}", *args
        )
        rows = await self.fetch(
            f"SELECT a.id, a.device_id, d.name, d.hostname, a.severity, a.title, "
            f"a.description, a.detected_at, a.resolved_at, a.count, a.last_seen "
            f"FROM anomalies a JOIN devices d ON d.id = a.device_id "
            f"WHERE {where} ORDER BY a.last_seen DESC "
            f"LIMIT ${i} OFFSET ${i+1}",
            *args, limit, offset,
        )
        return {"items": [dict(r) for r in rows], "total": total}

    # ── Summaries ──

    async def insert_summary(self, device_id: int, period_start, period_end,
                               summary: str, model: str | None = None,
                               summary_type: str = "period"):
        return await self.fetchval(
            "INSERT INTO summaries (device_id, period_start, period_end, summary, model, summary_type) "
            "VALUES ($1,$2,$3,$4,$5,$6) RETURNING id",
            device_id, period_start, period_end, summary, model, summary_type,
        )

    async def get_recent_summaries(self, device_id: int, limit: int = 10):
        rows = await self.fetch(
            "SELECT id, device_id, period_start, period_end, summary, model, summary_type, created_at "
            "FROM summaries WHERE device_id = $1 "
            "ORDER BY period_start DESC LIMIT $2",
            device_id, limit,
        )
        return [dict(r) for r in rows]

    async def search_summaries(self, device_id: int | None = None,
                                 summary_type: str | None = None,
                                 date_from=None, date_to=None,
                                 limit: int = 20, offset: int = 0):
        where = []
        args = []
        i = 1
        if device_id is not None:
            where.append(f"device_id = ${i}"); args.append(device_id); i += 1
        if summary_type is not None:
            where.append(f"summary_type = ${i}"); args.append(summary_type); i += 1
        if date_from is not None:
            where.append(f"period_end >= ${i}"); args.append(date_from); i += 1
        if date_to is not None:
            where.append(f"period_start <= ${i}"); args.append(date_to); i += 1
        where_sql = " AND ".join(where) if where else "TRUE"

        total = await self.fetchval(
            f"SELECT COUNT(*) FROM summaries WHERE {where_sql}", *args
        )
        rows = await self.fetch(
            f"SELECT id, device_id, period_start, period_end, summary, model, summary_type, created_at "
            f"FROM summaries WHERE {where_sql} "
            f"ORDER BY period_start DESC LIMIT ${i} OFFSET ${i+1}",
            *args, limit, offset,
        )
        return {"items": [dict(r) for r in rows], "total": total or 0, "limit": limit, "offset": offset}

    async def get_summaries_in_range(self, device_id: int, start, end,
                                       summary_type: str | None = None):
        if summary_type:
            rows = await self.fetch(
                "SELECT id, device_id, period_start, period_end, summary, model, summary_type, created_at "
                "FROM summaries WHERE device_id = $1 AND summary_type = $2 "
                "AND period_start >= $3 AND period_end <= $4 "
                "ORDER BY period_start",
                device_id, summary_type, start, end,
            )
        else:
            rows = await self.fetch(
                "SELECT id, device_id, period_start, period_end, summary, model, summary_type, created_at "
                "FROM summaries WHERE device_id = $1 "
                "AND period_start >= $2 AND period_end <= $3 "
                "ORDER BY period_start",
                device_id, start, end,
            )
        return [dict(r) for r in rows]
