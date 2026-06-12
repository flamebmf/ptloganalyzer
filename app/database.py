import asyncpg


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
    enabled     BOOLEAN DEFAULT true,
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

    async def _ensure_schema(self):
        exists = await self.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'devices')"
        )
        if not exists:
            async with self.pool.acquire() as conn:
                await conn.execute(SCHEMA_SQL)

        await self._ensure_vector_schema()

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

    async def _ensure_indexes(self):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_devices_ip ON devices(ip)"
            )
            await conn.execute(
                "ALTER TABLE devices DROP CONSTRAINT IF EXISTS devices_hostname_key"
            )

    async def close(self):
        if self._pool:
            await self._pool.close()

    @property
    def pool(self) -> asyncpg.Pool:
        assert self._pool is not None, "Database not connected"
        return self._pool

    async def execute(self, query: str, *args):
        return await self.pool.execute(query, *args)

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
            "SELECT id, hostname, ip, name, device_type, enabled, created_at "
            "FROM devices ORDER BY hostname"
        )
        return [dict(r) for r in rows]

    async def get_device(self, device_id: int) -> dict | None:
        row = await self.fetchrow(
            "SELECT id, hostname, ip, name, device_type, enabled, created_at "
            "FROM devices WHERE id = $1", device_id
        )
        return dict(row) if row else None

    async def update_device(self, device_id: int, **kwargs):
        sets = ", ".join(f"{k} = ${i+1}" for i, k in enumerate(kwargs))
        vals = list(kwargs.values()) + [device_id]
        await self.execute(
            f"UPDATE devices SET {sets} WHERE id = ${len(kwargs)+1}", *vals
        )

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
        rows = await self.fetch(
            f"SELECT id, device_id, ts, facility, severity, app_name, message "
            f"FROM syslog_messages WHERE {where_sql} "
            f"ORDER BY ts DESC LIMIT ${i} OFFSET ${i+1}",
            *args, limit, offset,
        )
        return [dict(r) for r in rows]

    # ── Anomalies ──

    async def insert_anomaly(self, device_id: int, severity: str,
                               title: str, description: str | None = None):
        return await self.fetchval(
            "INSERT INTO anomalies (device_id, severity, title, description) "
            "VALUES ($1,$2,$3,$4) RETURNING id",
            device_id, severity, title, description,
        )

    async def list_anomalies(self, device_id: int | None = None,
                              limit: int = 50, offset: int = 0):
        where = "TRUE"
        args = []
        i = 1
        if device_id is not None:
            where = f"device_id = ${i}"
            args.append(device_id)
            i += 1
        rows = await self.fetch(
            f"SELECT a.id, a.device_id, d.hostname, a.severity, a.title, "
            f"a.description, a.detected_at, a.resolved_at "
            f"FROM anomalies a JOIN devices d ON d.id = a.device_id "
            f"WHERE {where} ORDER BY a.detected_at DESC "
            f"LIMIT ${i} OFFSET ${i+1}",
            *args, limit, offset,
        )
        return [dict(r) for r in rows]

    # ── Summaries ──

    async def insert_summary(self, device_id: int, period_start, period_end,
                               summary: str, model: str | None = None):
        return await self.fetchval(
            "INSERT INTO summaries (device_id, period_start, period_end, summary, model) "
            "VALUES ($1,$2,$3,$4,$5) RETURNING id",
            device_id, period_start, period_end, summary, model,
        )

    async def get_recent_summaries(self, device_id: int, limit: int = 10):
        rows = await self.fetch(
            "SELECT id, device_id, period_start, period_end, summary, model, created_at "
            "FROM summaries WHERE device_id = $1 "
            "ORDER BY period_start DESC LIMIT $2",
            device_id, limit,
        )
        return [dict(r) for r in rows]
