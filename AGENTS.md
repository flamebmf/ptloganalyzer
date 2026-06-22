# Agent Rules

## Before editing code
- Always propose a plan first and get user confirmation before making code changes.
- Do not edit files without agreement on the approach.

## Project Context (as of 2026-06-21, session about to end)

### Active Problems (current session)
1. **Garbage AI summary output** — hourly/daily summaries contain gibberish instead of structured sections (`=== ОБЩАЯ ИНФОРМАЦИЯ ===` etc.)
   - Root cause: `summarization_provider` not set → falls back to global `ai_provider=ollama` with `model=llama3.2:1b` (1B params, too weak for structured prompts)
   - Fix: configure per-task provider via UI (Settings → AI → Суммаризация) or `/api/ai-config`:
     ```bash
     curl -X PATCH http://192.168.5.12:8000/api/ai-config \
       -H "Content-Type: application/json" \
       -d '{"summarization":{"provider":"routerai","model":"deepseek/deepseek-v4-pro"},"anomaly_detection":{"provider":"ollama","model":"llama3.2:1b"}}'
     ```
   - Anomaly detection works fine with llama3.2:1b (simple JSON output)

2. **Summarizer language mismatch** — AI language setting wasn't propagated to AI worker
   - Fix: added `ai_language` read from DB in `_check_config()` (scheduler.py:151-156)

3. **`_ensure_indexes` issues** (from prev session, now fixed in code):
   - `CREATE INDEX CONCURRENTLY IF NOT EXISTS` on partitioned table → silently failed (error caught by try/except, index never created)
   - `pg_try_advisory_lock` — unnecessary complexity; `IF NOT EXISTS` makes concurrent CREATE safe
   - Fix: removed advisory lock, changed to plain `CREATE INDEX IF NOT EXISTS`
   - Also removed `pg_advisory_unlock_all()` in finally block

4. **initAppMetrics crash** — `Cannot set properties of null (setting 'hidden')` when `zmstatCard` element missing
   - Fix: added null guard `if (card) card.hidden = true` in catch block

5. **Log row clicks** — clicking a log row in search results navigated to device page instead of opening detail modal
   - Fix: message/time/sev cells → `openLogModal()`, host/app cells → device page

### Changes COMMITTED AND PUSHED (this session)
All pushed to master:
- `ff1c079` — `web/logs.html`: split click behavior (message/time/sev → modal, host/app → device)
- `dfe5fe4` — `app/database.py`: removed CONCURRENTLY + advisory lock; `web/device.html`: null guard in initAppMetrics
- `08ad2df` — `app/ai_worker/scheduler.py`: added `ai_language` to `_check_config()` for AI worker sync
- `58d8f61` — `app/routers/settings.py`: reverted redundant per-task fields (UI uses `/api/ai-config`)

### NOT YET DEPLOYED
Server needs `git pull && perl setup.pl --rebuild --update=all` to apply:
- scheduler.py language sync
- database.py index fixes (CONCURRENTLY → plain, no advisory lock)
- device.html null guard
- logs.html click behavior split

pg_trgm GIN index will be created on next startup via `_ensure_indexes()` (~20-60 min, blocks INSERT but not SELECT).

### Known Server Issues
- App runs in podman pod. Containers: `ptlog-app-backend`, `ptlog-collector-collector`, `ptlog-ai-ai-worker`, `ptlog-infra-postgres`
- Current running code doesn't have the `_ensure_indexes` / language sync fixes → app works but DDL may timeout
- `pid 1` in app container may exit on crash (need `Restart=always` or pod auto-restart)
- Server has 65M rows in syslog_messages; index creation on new columns takes 2-10 min

### Per-Task AI Provider Configuration
- UI in Settings → AI → task rows (Суммаризация, Аномалии, Эмбеддинги)
- Backend: `PATCH /api/ai-config` saves to `app_settings` table
- AI worker picks up changes via `_check_config()` every 30 sec, recreates services
- Available providers: ollama (llama3.2:1b), openai (gpt-4o-mini), routerai (deepseek/deepseek-v4-pro)
- Recommended: summarization → routerai/deepseek, anomalies → ollama/llama3.2:1b

### Index Strategy for Log Queries
- `idx_syslog_device_ts(device_id, ts DESC)` — fast for device log list without severity filter
- `idx_syslog_device_severity_ts(device_id, severity, ts DESC)` — fast for device + severity filter
- `idx_syslog_ts_desc(ts DESC)` — general 48h time-bound searches
- `idx_syslog_app_ts(app_name, ts DESC)` — app-specific queries
- `idx_syslog_message_trgm USING GIN (message gin_trgm_ops)` — instant ILIKE search (NOT YET CREATED on server)

### Pod/Container Names
- `ptlog-app` (backend) — API сервер (uvicorn, порт 8000)
- `ptlog-collector` — syslog collector (UDP/TCP 514)
- `ptlog-ai` — AI worker (summarization, anomalies, embeddings)
- `ptlog-infra` — PostgreSQL (pgvector, порт 5432)
- `ptlog-web` — Nginx, статика (порт 80)
- Полные имена контейнеров в podman: `ptlog-app-backend`, `ptlog-collector-collector`, `ptlog-ai-ai-worker`, `ptlog-infra-postgres`

### PostgreSQL Config (infra.kube)
- `shared_buffers=2GB`, `effective_cache_size=6GB`, `synchronous_commit=off`
- `max_wal_size=8GB`, `checkpoint_timeout=10min`, `wal_buffers=64MB`
- `work_mem=64MB`, `maintenance_work_mem=512MB`, `random_page_cost=1.1`
