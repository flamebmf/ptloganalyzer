# ptloganalyzer — Job Status

## Current State (2026-06-12)

### Инфраструктура
- **Infra (PostgreSQL + pgvector)**: работает, pgvector/pgvector:pg17, сеть ptlog
- **Collector**: работает, UDP+TCP :514, батч-вставка
- **App (FastAPI)**: работает, /health, /api/version, API порт 8000
- **AI-worker**: работает, provider=ollama, scheduler запущен
- **Web**: не развёрнут (режим no-proxy, статику раздаёт FastAPI)
- **Ollama**: внешний `http://192.168.5.12:11434`, модели llama3.2:3b + nomic-embed-text

### Setup
- **setup.pl**: ~1000 строк, чистый Perl, поддержка `--update=comp`
- **generate_config.pl**: YAML-генератор, читает APP_VERSION из VERSION файла
- **VERSION**: 0.3.0

### Конфигурация
- `.env`: DB_PASSWORD (единый источник пароля)
- `deploy.yaml`: настройки деплоя + ai.provider + ai.ollama_url
- `.kube`: плейсхолдеры `__DB_PASSWORD__` — не хардкодятся, подставляются при деплое через sed

## Последние изменения

### Фиксы SPA
- `app.js loadPage`: `const/let` → `var` во всех inline-скриптах (автоматическая замена)
- Dashboard: `location.reload()` вместо SPA-загрузки
- navbar: SVG-логотип "Pt" + "log" (белый) + "analyzer" (градиент)
- Все страницы: консистентная SPA-навигация без ошибок

### Пароли
- Единый источник: `.env` (DB_PASSWORD)
- `read_deploy_yaml()` вызывается перед `generate_configs` при пересборке
- `.kube` файлы не содержат пароль (плейсхолдеры, подстановка через `play_kube`)

### Дашборд / UI
- Карточки хостов вынесены на отдельную страницу `devices.html`
- `index.html`: статистика + чарты + top apps (без device grid)
- API: `/api/dashboard/history` (volume, severity, top errors, per-device, top apps)
- Бэкграунд: CSS radial-gradient + shimmer animation (как в pt проекте)

### Таймстампы
- `parser.py`: RFC3164 — timezone из TZ контейнера (не hardcoded UTC)
- `collector.kube`: TZ=Europe/Moscow
- DB: старые записи с 1900 годом — фикс через `replace_year`

### AI / Ollama
- endpoint'ы: `/api/chat` + `/api/embed` (не `/api/embeddings`)
- Модель по умолчанию: `llama3.2:1b` (быстрее чем 3b)
- `ensure_ollama_models`: авто-pull моделей при деплое
- Таймаут: 120с
- Логи ошибок: `type` + `repr` (понятно что упало)
- Scheduler: последовательная обработка устройств (не параллельно)
- Статистические детекторы без AI: volume, error flood, duplicate burst, app spike
- AI content analysis: только при доступном провайдере

### Probes
- Collector: `kill -0 1` (было tcpSocket:514 — создавал лишние соединения)
- AI worker: `kill -0 1` (было httpGet:8000/health — AI не HTTP-сервер)
- App: httpGet /health (FastAPI — корректно)
- Infra: pg_isready (корректно)

### Баги исправленные
1. `generate_config.pl` версия hardcoded → читает APP_VERSION/VERSION
2. `read_deploy_yaml` не сохранял ollama_url → добавлено в deploy.yaml
3. `ask_ai` не вызывалось → заголовок был, вызова не было
4. Пароль регенерился при пересборке → `read_deploy_yaml()` перед `generate_configs`
5. SPA `const` redeclare → авто-замена `const/let` → `var` в `loadPage`

## Known Issues
- Ollama инференс медленный (~2мин на 3b модели), перешли на 1b
- Контейнер ptlog-ai может не достучаться до внешнего Ollama если сеть изолирована
- После пересоздания pod'ов без `--update=infra` пароль может рассинхрониться (решается `play_kube`)
- Старые записи в БД до фикса TZ сохранены с неверной timezone (нужен UPDATE)

## Next Steps
- Мониторить AI worker: `podman logs ptlog-ai`
- Проверить скорость llama3.2:1b на хосте Ollama
- При необходимости — ещё легче модель (qwen2.5:0.5b)

### RouterAI (2026-06-12)
- Добавлен третий AI провайдер: **RouterAI** (маршрутизация моделей через OpenAI-совместимый API)
- **Файлы**:
  - `app/ai/routerai_provider.py` — новый провайдер (аналог OpenAI, таймаут 120с)
  - `app/ai/__init__.py` — ветка `routerai` в фабрике `create_provider()`
  - `app/config.py` — поля `routerai_api_key`, `routerai_base_url`, `routerai_chat_model`, `routerai_embedding_model`, `routerai_embedding_dims`
  - `config.yaml` — блок `routerai:` с `${ROUTERAI_API_KEY}`, дефолтная модель `deepseek/deepseek-v4-pro`
  - `app/generate_config.pl` — блок `routerai` с env-переменными `AI_ROUTERAI_URL`, `AI_ROUTERAI_MODEL`, `AI_ROUTERAI_EMBED`
  - `setup.pl` — опция 3 (RouterAI) в `ask_ai()`, запись `ROUTERAI_API_KEY` в `.env`, подстановка `__ROUTERAI_API_KEY__` при деплое
  - `pod/ai.kube` — env `ROUTERAI_API_KEY` = `__ROUTERAI_API_KEY__`
- **Бэкапы**: все изменённые файлы сохранены с расширением `.20260612-145530.bak`
- **Для активации**: в `config.yaml` сменить `provider: routerai`, задать `ROUTERAI_API_KEY` (через `.env` или env), опционально `routerai.base_url` / `routerai.chat_model`
