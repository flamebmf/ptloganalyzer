-- ptloganalyzer — Database Schema
-- PostgreSQL 17 + pgvector

CREATE EXTENSION IF NOT EXISTS vector;

-- ── Devices ──
CREATE TABLE IF NOT EXISTS devices (
    id          SERIAL PRIMARY KEY,
    hostname    VARCHAR(255) NOT NULL,
    ip          INET,
    name        VARCHAR(255),
    description TEXT,
    device_type VARCHAR(50) DEFAULT 'other',
    parser      VARCHAR(50) DEFAULT 'default',
    enabled     BOOLEAN DEFAULT true,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_devices_hostname ON devices(hostname);
CREATE INDEX IF NOT EXISTS idx_devices_ip ON devices(ip);

-- ── Syslog messages (partitioned by timestamp) ──
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

CREATE TABLE IF NOT EXISTS syslog_messages_default
    PARTITION OF syslog_messages DEFAULT;

CREATE INDEX IF NOT EXISTS idx_syslog_device_ts ON syslog_messages(device_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_syslog_device_severity_ts ON syslog_messages(device_id, severity, ts DESC);
CREATE INDEX IF NOT EXISTS idx_syslog_severity ON syslog_messages(severity);
CREATE INDEX IF NOT EXISTS idx_syslog_app ON syslog_messages(app_name);

-- ── Partitions (monthly) ──
-- Create partitions for current and next 3 months
SELECT to_char(d, 'YYYYMM') AS part_name,
       date_trunc('month', d) AS part_start,
       date_trunc('month', d + INTERVAL '1 month') AS part_end
FROM generate_series(
    date_trunc('month', NOW()),
    date_trunc('month', NOW() + INTERVAL '3 months'),
    INTERVAL '1 month'
) AS d;

DO $$
DECLARE
    rec record;
    exists boolean;
BEGIN
    FOR rec IN
        SELECT to_char(d, 'YYYYMM') AS part_name,
               date_trunc('month', d)::text AS part_start,
               (date_trunc('month', d + INTERVAL '1 month'))::text AS part_end
        FROM generate_series(
            date_trunc('month', NOW()),
            date_trunc('month', NOW() + INTERVAL '3 months'),
            INTERVAL '1 month'
        ) AS d
    LOOP
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS syslog_messages_%s PARTITION OF syslog_messages '
            'FOR VALUES FROM (''%s'') TO (''%s'')',
            rec.part_name, rec.part_start, rec.part_end
        );
    END LOOP;
END $$;

-- ── Log embeddings (pgvector) ──
CREATE TABLE IF NOT EXISTS log_embeddings (
    id          BIGSERIAL PRIMARY KEY,
    log_id      BIGINT NOT NULL,
    device_id   INT NOT NULL REFERENCES devices(id),
    embedding   vector,
    model       VARCHAR(64) DEFAULT 'text-embedding-3-small',
    snippet     TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_embeddings_device ON log_embeddings(device_id);
-- Enable pgvector's ivfflat index for similarity search
-- CREATE INDEX IF NOT EXISTS idx_embeddings_ivfflat ON log_embeddings
--     USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ── Summaries ──
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

-- ── Anomalies ──
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
