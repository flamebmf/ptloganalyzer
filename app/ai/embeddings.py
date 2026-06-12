import structlog

from app.ai import create_provider

log = structlog.get_logger()


class EmbeddingService:
    def __init__(self, config, db):
        self.cfg = config
        self.db = db
        self.provider = create_provider(config)

    async def process_unembedded(self, limit: int = 100):
        if not self.provider:
            log.warning("ai_disabled_skip_embeddings")
            return

        logs = await self.db.fetch(
            "SELECT sm.id, sm.device_id, sm.message "
            "FROM syslog_messages sm "
            "LEFT JOIN log_embeddings le ON le.log_id = sm.id "
            "WHERE le.id IS NULL "
            "ORDER BY sm.id LIMIT $1",
            limit,
        )
        if not logs:
            return

        texts = [l["message"] for l in logs]
        try:
            embeddings = await self.provider.embed_batch(texts)
            for log_row, emb in zip(logs, embeddings):
                snippet = log_row["message"][:512]
                emb_str = "[" + ",".join(str(x) for x in emb) + "]"
                await self.db.execute(
                    "INSERT INTO log_embeddings "
                    "(log_id, device_id, embedding, model, snippet) "
                    "VALUES ($1, $2, $3::vector, $4, $5)",
                    log_row["id"], log_row["device_id"],
                    emb_str, self.provider.embed_model, snippet,
                )
            log.info("embeddings_created", count=len(logs))
        except Exception as e:
            log.warning("embeddings_failed", error=repr(e), type=type(e).__name__)

    async def search_similar(self, query: str, device_id: int | None = None,
                              limit: int = 10) -> list[dict]:
        if not self.provider:
            return []

        query_emb = await self.provider.embed(query)
        emb_str = "[" + ",".join(str(x) for x in query_emb) + "]"

        where = ""
        if device_id is not None:
            where = f"AND le.device_id = {device_id}"

        rows = await self.db.fetch(
            f"SELECT le.id, le.log_id, le.device_id, le.snippet, "
            f"1 - (le.embedding <=> $1::vector) AS score, "
            f"sm.message, sm.ts "
            f"FROM log_embeddings le "
            f"JOIN syslog_messages sm ON sm.id = le.log_id "
            f"WHERE 1=1 {where} "
            f"ORDER BY le.embedding <=> $1::vector "
            f"LIMIT $2",
            emb_str, limit,
        )
        return [dict(r) for r in rows]
