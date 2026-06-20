# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
import structlog

from app.config import Config
from app.database import Database
from app.version import APP_VERSION, APP_VENDOR, COMPONENTS

log = structlog.get_logger()
config = Config()
db = Database(config)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("app_starting", version=config.version)
    await db.connect()
    from app.routers.settings import apply_overrides
    await apply_overrides()
    # Seed defaults from config.yaml on first deploy
    for k, cfg_attr in [("ai_provider", "ai_provider"),
                        ("language", "language"),
                        ("ai_language", "ai_language"),
                        ("anomaly_min_severity", "anomaly_min_severity"),
                        ("summary_enabled", "summary_enabled"),
                        ("daily_summary_enabled", "daily_summary_enabled")]:
        existing = await db.get_setting(k)
        if existing is None:
            val = getattr(config, cfg_attr)
            if isinstance(val, bool):
                val = "true" if val else "false"
            await db.set_setting(k, val)

    # Seed per-task AI config from config.yaml
    for task in ("summarization", "anomaly_detection", "embeddings"):
        for key in ("provider", "model"):
            db_key = f"{task}_{key}"
            existing = await db.get_setting(db_key)
            if existing is None:
                val = getattr(config, f"{task}_{key}", None)
                if val:
                    await db.set_setting(db_key, val)

    # Seed devices from config
    for d in config.devices:
        await db.get_or_create_device(d["hostname"], d.get("ip"))
        log.info("device_seeded", hostname=d["hostname"])

    yield

    await db.close()
    log.info("app_stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title=config.name,
        version=config.version,
        lifespan=lifespan,
    )

    # Health check
    @app.get("/favicon.ico")
    async def favicon():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f4ca.png")

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "version": APP_VERSION,
            "vendor": APP_VENDOR,
            "components": COMPONENTS,
        }

    @app.get("/api/version")
    async def version_info():
        return {
            "app": config.name,
            "version": APP_VERSION,
            "vendor": APP_VENDOR,
            "components": COMPONENTS,
        }

    # Routers
    from app.routers import devices, logs, anomalies, sse, settings, summaries, dashboard, ai_config, app_metrics

    app.include_router(devices.router, prefix="/api")
    app.include_router(logs.router, prefix="/api")
    app.include_router(anomalies.router, prefix="/api")
    app.include_router(sse.router, prefix="/api")
    app.include_router(settings.router, prefix="/api")
    app.include_router(summaries.router, prefix="/api")
    app.include_router(dashboard.router, prefix="/api")
    app.include_router(ai_config.router, prefix="/api")
    app.include_router(app_metrics.router, prefix="/api")

    @app.middleware("http")
    async def spa_redirect(request: Request, call_next):
        path = request.url.path
        if path.endswith(".html") and path != "/" and path != "/index.html":
            if not request.url.query:
                return RedirectResponse(f"/#{path.lstrip('/')}", status_code=302)
        return await call_next(request)

    # Serve static files if enabled
    if config.web_serve_static:
        static_dir = Path("/app/web")
        if not static_dir.exists():
            static_dir = Path(config.data_dir) / "web"
        if static_dir.exists():
            app.mount("/", StaticFiles(directory=str(static_dir), html=True),
                       name="static")
            log.info("static_files_enabled", path=str(static_dir))

    return app


app = create_app()
