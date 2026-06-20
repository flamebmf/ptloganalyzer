# ptloganalyzer

> **Version 0.9.8** — Self-hosted syslog analysis platform with AI-powered summarization, anomaly detection, and application-level metric extraction.

Collect syslogs from network devices (routers, switches, firewalls, access points), parse them with device-specific templates and application parsers (FortiGate, Postfix, Zimbra), and get structured AI analysis in Russian or English — hourly summaries, daily reports, real-time anomaly alerts, and per-app KPIs.

---

## Architecture

```
┌──────────────┐    UDP/TCP :514     ┌──────────────────┐
│  Network     │ ──────────────────→ │  Collector        │
│  Devices     │    (RFC 3164/5424)  │  (async batch)    │
└──────────────┘                     └────────┬─────────┘
                                               │ batch insert
                                               ▼
┌──────────────────────────────────────────────┐
│  PostgreSQL + pgvector                        │
│  - syslog_messages (partitioned)             │
│  - devices                                   │
│  - summaries (hourly + daily)                │
│  - anomalies                                 │
│  - log_embeddings (vector search)            │
└──────────────────┬───────────────────────────┘
                   │
    ┌──────────────┼──────────────┐
    ▼              ▼              ▼
┌──────────┐ ┌────────────┐ ┌──────────────┐
│ AI Worker│ │ FastAPI    │ │ Web UI (SPA) │
│-summarizer│ │ - REST API│ │ - Dashboard  │
│-anomaly  │ │ - SSE push│ │ - Log/Search │
│-embedding│ │ - Static   │ │ - Devices    │
│-scheduler│ │ - SPA      │ │ - Anomalies  │
└──────────┘ └────────────┘ │ - Settings   │
                             └──────────────┘

AI Providers (external): Ollama · OpenAI · RouterAI
```

### Components

| Component | Role | Deployment |
|-----------|------|------------|
| **Collector** | Asynchronous UDP/TCP syslog receiver, batched inserts | Container (Podman/k8s) |
| **PostgreSQL** | Core storage with pgvector for embeddings | Container (pgvector/pgvector:pg17) |
| **FastAPI App** | REST API + static file serving + SPA engine | Container |
| **AI Worker** | Background scheduler for summarization & anomaly detection | Container (separate process) |
| **Web UI** | Single-page application (vanilla JS, ApexCharts) | Bundled with App |
| **AI Providers** | Ollama, OpenAI, RouterAI (switchable at runtime) | External / API |

---

## Features

### Syslog Collection
- UDP and TCP listeners on port 514
- RFC 5424 and RFC 3164 parsing with fallback
- Batch inserts with configurable size/interval
- Device identification by source IP (not hostname)

### Device-Specific Parse Templates
- **`default`** — Universal RFC 5424/3164 parser
- **`rfc3164_tag`** — RFC 3164 with structured app_name[pid] extraction
- **`aruba_iap`** — Aruba Instant Access Point parser (extracts AP name from message body)
- Templates stored in `parse_templates` DB table, assigned per device in UI (settings page)
- Add new templates via `INSERT INTO parse_templates` — no Python code changes needed

### Application-Level Metric Parsers (Plugin System)
- **FortiGate** — extracts key=value fields (srcip, dstip, app, sentbyte, rcvdbyte, action, type, attack) with separate traffic and security panels
- **Postfix** — extracts SMTP transactions (process, event, client/dest IPs, ehlo/quit/commands)
- **Zimbra/Carbonio** — extracts CSV zmstat metrics (count, latency, queue size)
- Plugin system via `app/manifests/<app_id>.json` — single-file definition of parser rules and UI panels
- No code changes needed to add a new app parser — create a manifest file only

### AI Analysis (in Russian / English)

| Type | Interval | Description |
|------|----------|-------------|
| **Hourly summary** | Configurable (default 60 min) | All logs since last analysis, structured by events, apps, anomalies, recommendations |
| **Daily report** | Every 24h | Aggregates hourly summaries into cross-day trends, conclusions, prioritized actions |
| **Anomaly detection** | Configurable (default 15 min) | Statistical (volume z-score, error flood, duplicate burst, app spike) + AI content analysis |

- Time-period-based analysis — complete log coverage, no gaps
- Log IDs (`#12345`) are clickable in the UI — opens the original log record in a modal
- Three AI backends: **Ollama**, **OpenAI**, **RouterAI** (switchable at runtime)

### Web UI
- **Dark theme** with animated gradient background (35-bar JS engine)
- **Dashboard** — log volume (today vs yesterday, week vs week, month vs month), anomaly trend with regression forecast, storage info, devices grid, severity distribution, top apps, per-device stats, top errors, live log tail
- **Devices** — searchable/filterable grid with pagination, per-device stats, ON/OFF toggle, rename, anomaly and AI report quick filters
- **Device detail** — per-device logs, AI summary (expandable), anomaly list with detail modals, app metrics panels (FortiGate traffic/security, Postfix, Zimbra), volume and severity charts
- **Logs** — searchable log table with severity/device filters, safe 48h default time window
- **Anomalies** — categorized anomaly list with real-time SSE push, trend chart with forecast
- **Settings** — AI provider switch, per-task model selection, language (ru/en), device parse template assignment
- **SPA** — single-page application with hash routing, no full page reloads

### Dashboard
- Log volume charts: **today vs yesterday** (D2D), **this week vs last week** (W2W), **this month vs last month** (M2M) — area charts with gradient fill
- Anomaly trend with **linear regression** and **1-hour forecast**
- Severity distribution (donut), storage info, per-device stats, top errors, live log tail
- In-memory caching for slow queries (5 min), parallel SQL via `asyncio.gather`

### Vector Search (pgvector)
- Automatic embeddings generation for log messages
- Semantic similarity search across historical logs
- Pluggable embedding models per AI provider

---

## Quick Start

### Prerequisites
- Podman or Docker
- Python 3.12+ (for local development)

### Deploy from source

```bash
# Clone
git clone https://github.com/flamebmf/ptloganalyzer.git
cd ptloganalyzer

# Install dependencies
pip install -r requirements.txt

# Interactive setup
perl setup.pl

# Or non-interactive with specific components
perl setup.pl --update=all
perl setup.pl --update=infra  # PostgreSQL + pgvector only
perl setup.pl --update=ai     # AI worker + web files
```

### Deploy with pre-built images (faster)

```bash
# Clone config + web files only
git clone https://github.com/flamebmf/ptloganalyzer.git
cd ptloganalyzer
pip install -r requirements.txt

# Pull images from Docker Hub and deploy
perl setup.pl --pull
```

### Build and publish

```bash
# Build locally
podman build -t ptlog-base:latest --target base .
podman build -t ptlog-server:latest --target app .

# Publish to registry
perl setup.pl --push
```

### Configure

Edit `config.yaml` or use `setup.pl` interactive setup:

```yaml
ai:
  provider: routerai        # ollama | openai | routerai
  ollama:
    base_url: http://192.168.1.100:11434
    chat_model: qwen2.5:7b
  summarization:
    interval_minutes: 60
  anomaly_detection:
    interval_minutes: 15
```

### Run

```bash
# Start all pods (Ollama must be running separately if used)
podman play kube pod/infra.kube
podman play kube pod/collector.kube
podman play kube pod/app.kube
podman play kube pod/ai.kube
```

Open `http://localhost:8000` (or configured API port).

### AI Provider Hardware Requirements

| Provider | Min RAM | Min CPU | Recommendation |
|----------|---------|---------|----------------|
| **OpenAI** | — | — | External API, no local hardware needed |
| **RouterAI** | — | — | External API, no local hardware needed |
| **Ollama** (local) | 8 GB | 4 cores | 16 GB + 8 cores for Qwen 2.5 7B / DeepSeek R1 7B |

**Ollama minimum models for quality reports:**
- **Chat model**: `qwen2.5:7b` (7B params, ~4.7 GB) or `llama3.2:3b` (~2.3 GB) for lightweight setups — smaller models produce noticeably worse summaries and anomaly descriptions
- **Embedding model**: `nomic-embed-text` (~274 MB) — sufficient for semantic search
- Do **not** use `llama3.2:1b` for production — output quality is too low for reliable analysis
- Ollama runs on a **separate machine** (not deployed by `setup.pl`), point `ai.ollama.base_url` to its API

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DB_PASSWORD` | Yes | PostgreSQL password |
| `OPENAI_API_KEY` | For OpenAI | OpenAI API key |
| `ROUTERAI_API_KEY` | For RouterAI | RouterAI API key |
| `CONFIG_PATH` | No | Config file path (default: `/app/config.yaml`) |

### Key Config Sections

| Section | Fields |
|---------|--------|
| `database` | host, port, name, user, password |
| `collector` | port, udp, tcp, bind, batch_size, batch_interval |
| `ai.providers` | per-provider base_url, model, timeout |
| `ai.summarization` | interval_minutes, provider, model |
| `ai.anomaly_detection` | interval_minutes, sensitivity, provider, model |
| `ai.embeddings` | provider, model |
| `devices` | list of devices with hostname, ip, device_type, enabled |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/api/version` | Version info |
| `GET` | `/api/devices` | List devices (search, filter, pagination) |
| `GET` | `/api/devices/{id}` | Get device with stats |
| `PATCH` | `/api/devices/{id}` | Update device (name, enabled, template_id) |
| `GET` | `/api/logs` | Search logs (device_id, severity, query, time window) |
| `GET` | `/api/logs/{id}` | Get single log record |
| `GET` | `/api/summaries` | List summaries by device |
| `GET` | `/api/anomalies` | List anomalies |
| `GET` | `/api/settings` | Get settings |
| `PATCH` | `/api/settings` | Update settings (ai_provider, language, ai_language, per-task model) |
| `GET` | `/api/dashboard/history` | Dashboard aggregate (volume, severity, per-device, anomaly trend, W2W, M2M) |
| `GET` | `/api/dashboard/storage` | Database size, total logs, avg/day, oldest log |
| `GET` | `/api/dashboard/logtail` | Last N log messages with device info |
| `GET` | `/api/parse-templates` | List parse templates |
| `GET` | `/api/app-manifest/{app_id}` | Get app plugin manifest definition |
| `GET` | `/api/app-metrics/list` | List app metric types per device |
| `GET` | `/api/app-metrics/stats` | Aggregated app metrics (dimension + filter + metric) |
| `GET` | `/api/device-apps/{id}` | Get app parsers enabled for device |
| `PATCH` | `/api/device-apps/{id}` | Toggle app parser for device |
| `GET` | `/api/ai-config` | Get AI provider/model config |
| `PATCH` | `/api/ai-config` | Update AI per-task provider/model |
| `GET` | `/api/sse/events` | Server-Sent Events (real-time anomaly push) |

---

## Development

### Project Structure

```
ptloganalyzer/
├── app/
│   ├── main.py                 # FastAPI entry, lifespan, router registration
│   ├── config.py               # Config loader (YAML + .env)
│   ├── database.py             # PostgreSQL + pgvector, all queries
│   ├── version.py              # Version constants
│   ├── generate_config.pl      # YAML config generator from deploy.yaml
│   ├── manifests/              # App plugin manifests (FortiGate, Postfix, Zimbra)
│   │   ├── fortigate.json
│   │   ├── postfix.json
│   │   └── zimbramon.json
│   ├── collector/
│   │   ├── server.py           # Async UDP/TCP syslog receiver
│   │   ├── parser.py           # RFC 5424/3164 + device-specific parsers
│   │   └── app_parsers.py      # App-level KV parsers (manifest-driven)
│   ├── ai/
│   │   ├── provider.py         # Abstract AI provider
│   │   ├── openai_provider.py  # OpenAI implementation
│   │   ├── ollama_provider.py  # Ollama implementation
│   │   ├── routerai_provider.py# RouterAI implementation
│   │   ├── summarizer.py       # Hourly + daily AI summarization
│   │   ├── anomaly_detector.py # Statistical + AI anomaly detection
│   │   ├── embeddings.py       # pgvector embedding service
│   │   └── prompts.py          # Prompt templates (ru/en)
│   ├── ai_worker/
│   │   ├── __main__.py         # Worker entry point
│   │   └── scheduler.py        # Periodic task scheduler
│   └── routers/
│       ├── devices.py          # Device CRUD
│       ├── logs.py             # Log search + single log endpoint
│       ├── anomalies.py        # Anomaly listing
│       ├── summaries.py        # Summary listing
│       ├── settings.py         # Runtime settings + persistence
│       ├── dashboard.py        # Dashboard aggregate data
│       ├── app_metrics.py      # App metrics + manifest API
│       ├── parse_templates.py  # Parse template CRUD
│       └── sse.py              # Server-Sent Events for real-time push
├── web/
│   ├── index.html              # SPA shell + dashboard (navbar, footer, modal, bg)
│   ├── devices.html            # Device grid (search, filter, pagination)
│   ├── device.html             # Per-device detail + logs + AI summary + app metrics
│   ├── logs.html               # Global log search
│   ├── anomalies.html          # Anomaly list
│   ├── settings.html           # Settings page
│   ├── css/
│   │   └── pt-dark.css         # Dark theme (single file, all styles)
│   └── js/
│       ├── app.js              # SPA engine, toast, log modal, helpers
│       ├── bg-bars.js          # Animated gradient background (35 bars)
│       ├── charts.js           # ApexCharts wrappers (area, bar, donut, trend+forecast)
│       ├── lang.js             # i18n (ru/en)
│       └── sse-client.js       # SSE event listener
├── pod/                         # Podman pod manifests
│   ├── infra.kube               # PostgreSQL with pgvector
│   ├── collector.kube           # Syslog collector
│   ├── app.kube                 # FastAPI web app
│   └── ai.kube                  # AI worker
├── VERSION                      # Single source of version
├── config.yaml                  # Runtime config template
├── deploy.yaml                  # Install params for setup.pl
├── setup.pl                     # Interactive install/update
```

### Version Management

Single source of truth: **`VERSION`** file. The version auto-propagates to:
- `config.yaml` (via `generate_config.pl`)
- HTML cache-busting query strings (`?v=__APP_VERSION__`, substituted by `setup.pl`)
- Docker image labels (via `ARG VERSION`)

### Adding a New Device Parse Template

1. Insert a row into `parse_templates` with `parser_type` (e.g. `'default'`, `'rfc3164_tag'`, `'aruba_iap'`)
2. Optionally store regex config in the `config` JSONB column
3. Assign the template to a device via UI (`settings.html` → device card → template dropdown)
4. The collector caches templates by device IP and applies them at parse time
5. No Python code changes needed — templates are stored in DB

### Adding a New App Metrics Parser (Plugin System)

1. Create `app/manifests/<app_id>.json` with parser rules and panel definitions
2. For KV parsers: specify `kv_delimiter`, `field_delimiter`, and `require_keys` — the factory handles extraction
3. For custom logic: implement a parse function in `app/collector/app_parsers.py` and reference it in the manifest
4. Define UI panels: `dimension`, `filter`, `metric` for the stats API — panels auto-appear on device.html
5. No Python router or HTML changes needed — create a manifest file only

### Adding a New AI Provider

1. Implement `AIProvider` abstract class in `app/ai/`
2. Add config fields in `app/config.py` and `config.yaml`
3. Register in the factory `app/ai/__init__.py`
4. Add env vars to `setup.pl` and `.kube` manifests

---

## License

Personal Use Only. See [LICENSE](LICENSE) for details.

Copyright (c) 2026 PlurumTech.com
