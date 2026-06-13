# ptloganalyzer

> **Version 0.7.0** — Self-hosted syslog analysis platform with AI-powered summarization, anomaly detection, and device-specific log parsing.

Collect syslogs from network devices (routers, switches, firewalls, access points), parse them with device-specific templates, and get structured AI analysis in Russian — hourly summaries, daily reports, and real-time anomaly alerts.

---

## Architecture

```
┌──────────────┐    UDP/TCP :514     ┌──────────────────┐
│  Network     │ ──────────────────→ │  Collector        │
│  Devices     │    (RFC 3164/5424)  │  (async batch)    │
└──────────────┘                     └────────┬─────────┘
                                              │ batch insert
                                              ▼
┌──────────────┐    ┌─────────────────────────────────────┐
│  Ollama      │    │  PostgreSQL + pgvector               │
│  (external)  │    │  - syslog_messages (partitioned)     │
├──────────────┤    │  - devices                           │
│  OpenAI      │    │  - summaries (hourly + daily)        │
├──────────────┤    │  - anomalies                         │
│  RouterAI    │    │  - log_embeddings (vector search)    │
└──────────────┘    └──────────┬──────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  AI Worker   │    │  FastAPI App      │    │  Web UI (SPA)    │
│  - summarizer│    │  - REST API       │    │  - Dashboard     │
│  - anomaly   │    │  - SSE push       │    │  - Logs/Search   │
│  - embeddings│    │  - SPA redirect   │    │  - Devices       │
│  - scheduler │    │  - Static files   │    │  - Anomalies     │
└──────────────┘    └──────────────────┘    │  - Settings      │
                                             └──────────────────┘
```

### Components

| Component | Role | Deployment |
|-----------|------|------------|
| **Collector** | Asynchronous UDP/TCP syslog receiver, batched inserts | Container (Podman/k8s) |
| **PostgreSQL** | Core storage with pgvector for embeddings | Container (pgvector/pgvector:pg17) |
| **FastAPI App** | REST API + static file serving + SPA engine | Container |
| **AI Worker** | Background scheduler for summarization & anomaly detection | Container (separate process) |
| **Web UI** | Single-page application (vanilla JS, ApexCharts) | Bundled with App |
| **AI Providers** | Ollama (local), OpenAI, RouterAI (pluggable) | External / API |

---

## Features

### Syslog Collection
- UDP and TCP listeners on port 514
- RFC 5424 and RFC 3164 parsing with fallback
- Batch inserts with configurable size/interval
- Device identification by source IP (not hostname)

### Device-Specific Parsers
- **`default`** — Universal RFC 5424/3164 parser
- **`rfc3164_tag`** — RFC 3164 with structured app_name[pid] extraction
- **`aruba_iap`** — Aruba Instant Access Point parser (extracts AP name from message body)
- Extensible via `PARSERS` dict in `parser.py` — add custom regex templates per device

### AI Analysis (in Russian)

| Type | Interval | Description |
|------|----------|-------------|
| **Hourly summary** | Configurable (default 60 min) | All logs since last analysis, structured by events, apps, anomalies, recommendations |
| **Daily report** | Every 24h | Aggregates hourly summaries into cross-day trends, conclusions, prioritized actions |
| **Anomaly detection** | Configurable (default 15 min) | Statistical (volume z-score, error flood, duplicate burst, app spike) + AI content analysis |

- Time-period-based analysis — complete log coverage, no gaps
- Log IDs (`#12345`) are clickable in the UI — opens the original log record in a modal
- Three AI backends: **Ollama** (local), **OpenAI**, **RouterAI** (switchable at runtime)

### Web UI
- **Dark theme** with animated gradient background (35-bar JS engine)
- **Dashboard** — log volume (today vs yesterday), anomaly trend chart, storage info, devices grid, severity distribution, top apps, per-device stats, top errors, live log tail
- **Devices** — grid view with per-device stats, ON/OFF toggle, rename
- **Logs** — searchable log table with severity/device filters
- **Anomalies** — categorized anomaly list with real-time SSE push
- **Settings** — AI provider switch, language (ru/en), device management
- **SPA** — single-page application with hash routing, no full page reloads

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
git clone https://github.com/plurumtech/ptloganalyzer.git
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
git clone https://github.com/plurumtech/ptloganalyzer.git
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

Edit `config.yaml` or use `deploy.yaml` + `setup.pl` generation:

```yaml
ai:
  provider: ollama        # ollama | openai | routerai
  ollama:
    base_url: http://ollama.ptlog:11434
    chat_model: llama3.2:1b
  summarization:
    interval_minutes: 60
  anomaly_detection:
    interval_minutes: 15
```

### Run

```bash
# Start all pods
podman play kube pod/infra.kube
podman play kube pod/collector.kube
podman play kube pod/app.kube
podman play kube pod/ai.kube
```

Open `http://localhost:8000` (or configured API port).

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
| `ai.openai` | base_url, chat_model, embedding_model |
| `ai.ollama` | base_url, chat_model, embedding_model |
| `ai.routerai` | base_url, chat_model, embedding_model |
| `ai.summarization` | interval_minutes |
| `ai.anomaly_detection` | interval_minutes, sensitivity |
| `devices` | list of devices with hostname, ip, device_type, enabled |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/api/version` | Version info |
| `GET` | `/api/devices` | List devices |
| `GET` | `/api/devices/{id}` | Get device |
| `PATCH` | `/api/devices/{id}` | Update device (name, enabled) |
| `GET` | `/api/logs` | Search logs (device_id, severity, query, etc.) |
| `GET` | `/api/logs/{id}` | Get single log record |
| `GET` | `/api/summaries` | List summaries by device |
| `GET` | `/api/anomalies` | List anomalies |
| `GET` | `/api/settings` | Get settings |
| `PATCH` | `/api/settings` | Update settings (ai_provider, language) |
| `GET` | `/api/dashboard/history` | Dashboard aggregate data (volume, severity, per-device, anomaly trend, today vs yesterday) |
| `GET` | `/api/dashboard/storage` | Database size, total logs, avg/day, oldest log |
| `GET` | `/api/dashboard/logtail` | Last N log messages with device info |
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
│   ├── collector/
│   │   ├── server.py           # Async UDP/TCP syslog receiver
│   │   └── parser.py           # RFC 5424/3164 + device-specific parsers
│   ├── ai/
│   │   ├── provider.py         # Abstract AI provider
│   │   ├── openai_provider.py  # OpenAI implementation
│   │   ├── ollama_provider.py  # Ollama implementation
│   │   ├── routerai_provider.py# RouterAI implementation
│   │   ├── summarizer.py       # Hourly + daily AI summarization
│   │   ├── anomaly_detector.py # Statistical + AI anomaly detection
│   │   └── embeddings.py       # pgvector embedding service
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
│       └── sse.py              # Server-Sent Events for real-time push
├── web/
│   ├── index.html              # SPA shell + dashboard (navbar, footer, modal, bg)
│   ├── devices.html            # Device grid
│   ├── device.html             # Per-device detail + logs + AI summary
│   ├── logs.html               # Global log search
│   ├── anomalies.html          # Anomaly list
│   ├── settings.html           # Settings page
│   ├── css/
│   │   └── pt-dark.css         # Dark theme (single file, all styles)
│   └── js/
│       ├── app.js              # SPA engine, toast, log modal, helpers
│       ├── bg-bars.js          # Animated gradient background (35 bars)
│       ├── charts.js           # ApexCharts wrappers
│       ├── lang.js             # i18n (ru/en)
│       └── sse-client.js       # SSE event listener
├── pod/                         # Kubernetes/Podman pod manifests
│   ├── infra.kube               # PostgreSQL with pgvector
│   ├── collector.kube           # Syslog collector
│   ├── app.kube                 # FastAPI web app
│   └── ai.kube                  # AI worker
├── VERSION                      # Single source of version
├── config.yaml                  # Runtime config template
├── deploy.yaml                  # Install params for setup.pl
├── Dockerfile                   # Multi-stage build
├── Dockerfile.ai                # AI worker image
├── requirements.txt
└── setup.pl                     # Interactive install/update
```

### Version Management

Single source of truth: **`VERSION`** file. The version auto-propagates to:
- `config.yaml` (via `generate_config.pl`)
- HTML cache-busting query strings (`?v=__APP_VERSION__`, substituted by `setup.pl`)
- Docker image labels (via `ARG VERSION`)

### Adding a New Device Parser

1. Add a regex and parse function in `app/collector/parser.py`
2. Register in the `PARSERS` dict
3. Set `parser: your_parser_name` on the device in config or DB

### Adding a New AI Provider

1. Implement `AIProvider` abstract class in `app/ai/`
2. Add config fields in `app/config.py` and `config.yaml`
3. Register in the factory `app/ai/__init__.py`
4. Add env vars to `setup.pl` and `.kube` manifests

---

## License

Personal Use Only. See [LICENSE](LICENSE) for details.

Copyright (c) 2026 PlurumTech.com
