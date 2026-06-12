from fastapi import APIRouter
from pydantic import BaseModel

from app.main import config

router = APIRouter(tags=["settings"])


@router.get("/settings")
async def get_settings():
    return {
        "app": {"name": config.name, "version": config.version},
        "ai": {
            "enabled": config.ai_enabled,
            "provider": config.ai_provider,
            "summarization_interval": config.summary_interval,
            "anomaly_interval": config.anomaly_interval,
        },
        "web": {"language": config.language},
        "collector": {"port": config.collector_port, "enabled": config.collector_enabled},
    }
