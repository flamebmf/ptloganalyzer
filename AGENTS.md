# Agent Rules

## Before editing code
- Always propose a plan first and get user confirmation before making code changes.
- Do not edit files without agreement on the approach.

## Project Context (as of 2026-06-20, session about to end)

### Active Problems (current session)
1. **Severity=0 (EMERGENCY) timeout** — `search_logs` with `severity=0` and `device_id=36` times out because existing `idx_syslog_device_ts(device_id, ts DESC)` scans ALL 1.7M rows for device_id to find severity matches; with zero matches in 48h window, LIMIT 20 doesn't help.
   - Fix: added `idx_syslog_device_severity_ts ON syslog_messages(device_id, severity, ts DESC)` in `_ensure_indexes`, `SCHEMA_SQL`, and `schema.sql`
   - User can create index manually via podman exec without restart.

2. **`_ensure_indexes` crash on startup** — `conn._command_timeout = 300` fails with `'PoolConnectionProxy' object has no attribute '_command_timeout'` in this asyncpg version.
   - Fix: replaced with `timeout=300` param on each slow `conn.execute()` call (backfill, GIN indexes, big B-tree indexes)
   - Pool `command_timeout` increased 30→60

3. **No visual feedback on logs search** — changing severity/search/filter in logs.html and device.html didn't show loading state.
   - Fix: added `showLoading(el)` in `app.js` (uses existing `.modal-loading` / `.spinner` CSS classes)
   - Integrated into `searchLogs()` (logs.html) and `loadDeviceLogs()` (device.html) before each fetch

### Changes NOT YET COMMITTED
All edits from this session are uncommitted. Need `git add -A && git commit -m "..." && git push` before next session.

Changed files:
- `app/database.py` — `_ensure_indexes`: removed `conn._command_timeout`, added `timeout=300` to slow execute calls; added `idx_syslog_device_severity_ts` index; command_timeout 30→60
- `app/db/schema.sql` — added `idx_syslog_device_severity_ts`
- `web/js/app.js` — added `showLoading(el)` function
- `web/logs.html` — `searchLogs()`: added `showLoading()`, fixed `el`→`resultsEl`
- `web/device.html` — `loadDeviceLogs()`: added `showLoading()`

### Known Server Issues
- App runs in podman pod. Containers: `ptlog-app-backend`, `ptlog-collector-collector`, `ptlog-ai-ai-worker`, `ptlog-infra-postgres`
- Current running code doesn't have the `_ensure_indexes` timeout fix → app starts but _ensure_indexes may still timeout on slow DDL
- `pid 1` in app container may exit on crash (need `Restart=always` or pod auto-restart)
- Server has 65M rows in syslog_messages; index creation on new columns takes 2-10 min

### Index Strategy for Log Queries
- `idx_syslog_device_ts(device_id, ts DESC)` — fast for device log list without severity filter
- `idx_syslog_device_severity_ts(device_id, severity, ts DESC)` — fast for device + severity filter (NEW, NOT YET CREATED ON SERVER)
- `idx_syslog_ts_desc(ts DESC)` — general 48h time-bound searches
- `idx_syslog_app_ts(app_name, ts DESC)` — app-specific queries

### How to Create Missing Index on Server (without app restart)
```bash
podman exec -it ptlog-infra-postgres psql -U ptlog -d ptlog -c "
CREATE INDEX IF NOT EXISTS idx_syslog_device_severity_ts
ON syslog_messages(device_id, severity, ts DESC);
"
```

### Pod/Container Names
- `ptlog-app` (backend) — API сервер (uvicorn, порт 8000)
- `ptlog-collector` — syslog collector (UDP/TCP 514)
- `ptlog-ai` — AI worker (summarization, anomalies, embeddings)
- `ptlog-infra` — PostgreSQL (pgvector, порт 5432)
- `ptlog-web` — Nginx, статика (порт 80)
- Полные имена контейнеров в podman: `ptlog-app-backend`, `ptlog-collector-collector`, `ptlog-ai-ai-worker`, `ptlog-infra-postgres`

### Parse Templates
- `parse_templates` table: built-in `default`, `rfc3164_tag`, `aruba_iap`
- `devices.template_id` FK — задаётся в UI (settings.html)
- Collector кеширует template по source_ip, применяет при парсинге
- API: `GET /api/parse-templates`, `PATCH /api/devices/:id` (template_id)

### Runtime Settings in DB
- `app_settings(key, value)` — runtime-настройки в БД
- Сидятся из config.yaml при первом деплое (только если ключа нет)
- При PATCH /api/settings → сохраняются в БД
- AI worker раз в 5 мин проверяет `ai_provider`, пересоздаёт сервисы без рестарта
- `apply_overrides()` читает runtime-настройки из БД в config при старте web app

### AI Provider Timeouts
- Per-provider timeout в config.yaml: `ai.openai.timeout`, `ai.ollama.timeout`, `ai.routerai.timeout`
- Дефолты: OpenAI 180, Ollama 600, RouterAI 180
- Меняется без рестарта — `_check_config` подхватывает новое значение из БД и пересоздаёт сервисы

### Device Page (web/device.html)
- Аномалии: кликабельные строки открывают detail-модалку (title, severity, time, description)
- Пагинация аномалий: 10 на страницу
- AI-сводка: схлопнута до ~10 строк с кнопкой «Читать дальше»
- App metrics карточка: скрыта если нет данных; fortigate — traffic+security панели
- Графики: Volume (area chart) + Severity (donut) с заголовками
- Header stats: компактно, числа с toLocaleString

### PostgreSQL Config (infra.kube)
- `shared_buffers=2GB`, `effective_cache_size=6GB`, `synchronous_commit=off`
- `max_wal_size=8GB`, `checkpoint_timeout=10min`, `wal_buffers=64MB`
- `work_mem=64MB`, `maintenance_work_mem=512MB`, `random_page_cost=1.1`
