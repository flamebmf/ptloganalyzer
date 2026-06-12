from app.main import db


class AnomalyService:
    @staticmethod
    async def get_recent_anomalies(limit: int = 10) -> list[dict]:
        return await db.list_anomalies(limit=limit)
