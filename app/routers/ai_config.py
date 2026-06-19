from fastapi import APIRouter
from pydantic import BaseModel

from app.main import config, db

TASKS = ["summarization", "anomaly_detection", "embeddings"]

router = APIRouter(tags=["ai_config"])


@router.get("/ai-config")
async def get_ai_config():
    current = {}
    for task in TASKS:
        prov = getattr(config, f"{task}_provider", config.ai_provider)
        model = getattr(config, f"{task}_model", "")
        # Check DB overrides
        db_prov = await db.get_setting(f"{task}_provider")
        db_model = await db.get_setting(f"{task}_model")
        current[task] = {
            "provider": db_prov or prov,
            "model": db_model or model,
        }
    return {
        "providers": {k: {"name": v["name"], "models": v["models"]} for k, v in config.providers.items()},
        "current": current,
    }


class TaskConfigUpdate(BaseModel):
    provider: str
    model: str


class AiConfigUpdate(BaseModel):
    summarization: TaskConfigUpdate | None = None
    anomaly_detection: TaskConfigUpdate | None = None
    embeddings: TaskConfigUpdate | None = None


@router.patch("/ai-config")
async def update_ai_config(data: AiConfigUpdate):
    changed = {}
    for task in TASKS:
        tcu = getattr(data, task, None)
        if tcu:
            await db.set_setting(f"{task}_provider", tcu.provider)
            await db.set_setting(f"{task}_model", tcu.model)
            setattr(config, f"{task}_provider", tcu.provider)
            setattr(config, f"{task}_model", tcu.model)
            changed[task] = {"provider": tcu.provider, "model": tcu.model}
    return {"ok": True, "changed": changed}
