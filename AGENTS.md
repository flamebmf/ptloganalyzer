# Agent Rules

## Before editing code
- Always propose a plan first and get user confirmation before making code changes.
- Do not edit files without agreement on the approach.

## Project Context (as of 2026-06-19)

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

### Известные проблемы
- IAP "2026" год как hostname — лечится шаблоном `aruba_iap`
- `green-mkt1` дубликат (ids 33, 43) — один hostname, разные source IP
- IP как hostname у SIP/embedded устройств

### AI Provider Timeouts
- Per-provider timeout в config.yaml: `ai.openai.timeout`, `ai.ollama.timeout`, `ai.routerai.timeout`
- Дефолты: OpenAI 180, Ollama 600, RouterAI 180
- Меняется без рестарта — `_check_config` подхватывает новое значение из БД и пересоздаёт сервисы

### Model Lists (config.yaml)
- Список моделей для каждого провайдера — в `config.yaml` секция `ai.providers`
- Генерируется `generate_config.pl`, читается `config.py` → `self.providers`
- `GET /api/ai-config` отдаёт `config.providers` (не хардкод в Python)
- `registry.py` удалён — больше нет жёсткой привязки моделей в коде
- Для добавления модели достаточно добавить в `ai.providers` в `generate_config.pl`, перегенерить config.yaml и передеплоить

### YAML::XS everywhere
- `generate_config.pl` и `setup.pl` переписаны на `YAML::XS` вместо самописного `yaml()` sub и regex-парсинга
- Установлен пакет `perl-YAML-LibYAML` на сервере и локально
- `setup.pl:read_deploy_yaml()` читает config.yaml через `YAML::XS::LoadFile`, без regex

### Timeout & Error Logging
- Все провайдеры ловят `httpx.ReadTimeout` в `chat()` и поднимают `TimeoutError` с указанием таймаута
- `device_name` добавлен во все логи `summary_failed`, `daily_summary_failed`, `ai_anomaly_detection_failed`
- Scheduler передаёт `hostname` из списка устройств

### AI Language Support
- `app_settings(ai_language)` — `ru` или `en`, меняется в UI (settings.html)
- AI worker раз в 5 мин проверяет `ai_language`, пересоздаёт сервисы
- Все промпты в `app/ai/prompts.py`: `ANOMALY_LANG_PROMPTS`, `SUMMARIZE_LANG_PROMPTS`, `RECOMMEND_PROMPT`
- Провайдеры импортируют промпты из `prompts.py`, не содержат inline-текстов

### Dashboard Performance
- 10 SQL запросов `/api/dashboard/history` выполняются параллельно через `asyncio.gather`
- `/api/dashboard/storage` и `top_apps` кешируются в памяти на 5 минут (in-memory cache, module-level переменные)
- Добавлены индексы: `idx_stats_hour` ON `log_stats_hourly(hour)`, `idx_stats_hour_severity` ON `log_stats_hourly(hour, severity)`
- `ANALYZE log_stats_hourly` запускается после создания индексов в `_ensure_indexes()`

### Anomaly Display
- Статистические детекторы включают `MAX(id) AS sample_id` в SQL — #ID ссылается на конкретный лог
- #ID кликабельны в заголовке и описании аномалии (`convertLogIds(text, deviceId)` в `app.js`)
- Модальное окно лога поддерживает `?device_id=N` — жёлтый баннер при несовпадении device
- `d.name` возвращается в `list_anomalies` наряду с `d.hostname`
- Окно мержа аномалий: 48ч (было 24ч), `resolved_at` сбрасывается при мерже
- Промпт аномалий: "НЕ используй #ID как заголовок", "Цитаты из логов оставляй в оригинале"

### DNS / Container Networking
- DB host: `host.containers.internal` (не `ptlog-infra`) — обход aardvark-dns
- `hostPort: 5432` добавлен в `infra.kube`

### Setup.pl
- `$FORCE` flag: `--update=all` без интерактивных промптов
- `--update` (bare) — интерактивный: выбирает компоненты из `%comp`
- `read_deploy_yaml()` через `YAML::XS::LoadFile`

### Charts (web/js/charts.js)
- W2W/M2M: `type: 'area'` (было `bar`), градиентная заливка, smooth stroke
- Аномалии: линия тренда (линейная регрессия) поверх столбцов + прогноз на следующий час

### App Parsers (app/collector/app_parsers.py)
- `APP_PARSERS` — registry: `app_id → parse_fn(message) → (app_id, fields) | None`
- Парсеры работают на `message` тексте, не затрагивают основной парсинг syslog
- Первый парсер: `zimbramon` — извлекает CSV-поля из Carbonio/Zimbra zmstat
- `fortigate` — извлекает все key=value поля из FortiOS логов (type, subtype, srcip, dstip, app, sentbyte, rcvdbyte, duration, etc.) — требует BOTH type= AND logid=
- `postfix` — извлекает postfix-транзакции (process, event, src/dst ip:port, ehlo/quit/commands)
- `app_metrics(device_id, app_id, ts, fields JSONB)` — структурированные данные приложений (непартицированная)
- `device_apps(device_id, app_id, enabled)` — какие приложения ВЫКЛЮЧЕНЫ для устройства
- По умолчанию все новые парсеры включены для всех устройств (если нет явной записи в device_apps)
- Коллектор: сохраняет лог как есть, потом проверяет включённые приложения для device,
  запускает парсеры, пишет результат в `app_metrics`
- API: `GET /api/app-metrics/list`, `/series`, `/stats` (dim+filter+metric агрегация), `GET/PATCH /api/device-apps/:id`
- UI: карточка App metrics на device.html, для fortigate — 7 панелей (Source/Dest IPs, Apps, Interfaces, Actions, Threats, Policies)

### Device Page (web/device.html)
- Аномалии: кликабельные строки открывают detail-модалку (title, severity, time, description)
- Пагинация аномалий: 10 на страницу
- AI-сводка: схлопнута до ~10 строк с кнопкой «Читать дальше»
- App metrics карточка: скрыта если нет данных; fortigate — traffic+security панели
- Графики: Volume (area chart) + Severity (donut) с заголовками
- Header stats: компактно, числа с toLocaleString

### Dashboard Performance (known issues)
- `/api/dashboard/history`: 10 запросов параллельно через `asyncio.gather`, кеш 5 мин
- `top_apps` — фоновый таск, не блокирует дашборд
- `log_stats_hourly` — 5000 строк, индекс по hour, EXPLAIN=0.5ms
- PostgreSQL: shared_buffers=2GB, synchronous_commit=off, max_wal_size=8GB
- `log_stats_daily` — daily rollup, 90-day retention на hourly
- BRIN индекс на log_stats_hourly(hour) для долгосрочных сканов
- Проблема: дашборд грузится ~20с несмотря на SQL 0.5ms — причина не найдена
- Добавлены тайминг-логи `dashboard_history_done` — ждут деплоя

### FortiGate API
- `GET /api/app-metrics/stats`: агрегация по dimension (srcip,dstip,app,srcintf,action,type,etc.)
  + опциональный `filter=action:deny` и `metric=sentbyte`
- Исправлен баг: `fields ? key` → `jsonb_exists(fields, key)` (asyncpg конфликт)
- Исправлен баг: `ORDER BY sentbyte` → `ORDER BY value` (alias колонки)

### PostgreSQL Config (infra.kube)
- `shared_buffers=2GB`, `effective_cache_size=6GB`, `synchronous_commit=off`
- `max_wal_size=8GB`, `checkpoint_timeout=10min`, `wal_buffers=64MB`
- `work_mem=64MB`, `maintenance_work_mem=512MB`, `random_page_cost=1.1`
