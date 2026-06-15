# Agent Rules

## Before editing code
- Always propose a plan first and get user confirmation before making code changes.
- Do not edit files without agreement on the approach.

## Project Context (as of 2026-06-15)

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
- `apply_overrides()` синхронизирует runtime.json → БД при старте web app

### Известные проблемы
- IAP "2026" год как hostname — лечится шаблоном `aruba_iap`
- `green-mkt1` дубликат (ids 33, 43) — один hostname, разные source IP
- IP как hostname у SIP/embedded устройств

### AI Provider Timeouts
- Per-provider timeout в config.yaml: `ai.openai.timeout`, `ai.ollama.timeout`, `ai.routerai.timeout`
- Дефолты: OpenAI 180, Ollama 300, RouterAI 180
- Меняется без рестарта — `_check_config` подхватывает новое значение из БД и пересоздаёт сервисы
