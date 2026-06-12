import os
from pathlib import Path

import yaml
from dotenv import load_dotenv


class Config:
    def __init__(self, path: str | None = None):
        path = path or os.getenv("CONFIG_PATH", "/app/config.yaml")

        # Load .env from same directory as config file (best-effort)
        try:
            env_path = Path(path).parent / ".env"
            if env_path.exists():
                load_dotenv(env_path)
        except PermissionError:
            pass

        with open(path) as f:
            raw = yaml.safe_load(f)

        a = raw["app"]
        self.name: str = a["name"]
        self.version: str = a["version"]
        self.data_dir: str = a.get("data_dir", "/srv/ptloganalyzer")
        self.log_level: str = a.get("log_level", "info")

        d = raw["database"]
        self.db_host: str = d["host"]
        self.db_port: int = d["port"]
        self.db_name: str = d["name"]
        self.db_user: str = d["user"]
        self.db_password: str = os.getenv("DB_PASSWORD", d.get("password", ""))
        self.db_pool_min: int = d.get("pool_min", 5)
        self.db_pool_max: int = d.get("pool_max", 20)

        c = raw["collector"]
        self.collector_enabled: bool = c["enabled"]
        self.collector_udp: bool = c.get("udp", True)
        self.collector_tcp: bool = c.get("tcp", True)
        self.collector_port: int = c.get("port", 514)
        self.collector_bind: str = c.get("bind", "0.0.0.0")
        self.collector_recv_buffer: int = c.get("recv_buffer", 65536)
        self.collector_batch_size: int = c.get("batch_size", 500)
        self.collector_batch_interval: float = c.get("batch_interval", 1.0)

        ai = raw.get("ai", {})
        self.ai_enabled: bool = ai.get("enabled", False)
        self.ai_provider: str = ai.get("provider", "ollama")
        oai = ai.get("openai", {})
        self.openai_api_key: str = os.getenv("OPENAI_API_KEY", oai.get("api_key", ""))
        self.openai_base_url: str = oai.get("base_url", "https://api.openai.com/v1")
        self.openai_chat_model: str = oai.get("chat_model", "gpt-4o-mini")
        self.openai_embedding_model: str = oai.get("embedding_model", "text-embedding-3-small")
        self.openai_embedding_dims: int = oai.get("embedding_dims", 1536)
        oll = ai.get("ollama", {})
        self.ollama_base_url: str = oll.get("base_url", "http://localhost:11434")
        self.ollama_chat_model: str = oll.get("chat_model", "llama3.2:1b")
        self.ollama_embedding_model: str = oll.get("embedding_model", "nomic-embed-text")
        self.ollama_embedding_dims: int = oll.get("embedding_dims", 768)
        rai = ai.get("routerai", {})
        self.routerai_api_key: str = os.getenv("ROUTERAI_API_KEY", rai.get("api_key", ""))
        self.routerai_base_url: str = rai.get("base_url", "https://api.routerai.ai/v1")
        self.routerai_chat_model: str = rai.get("chat_model", "deepseek/deepseek-v4-pro")
        self.routerai_embedding_model: str = rai.get("embedding_model", "text-embedding-3-small")
        self.routerai_embedding_dims: int = rai.get("embedding_dims", 1536)
        summ = ai.get("summarization", {})
        self.summary_interval: int = summ.get("interval_minutes", 60)
        self.summary_max_logs: int = summ.get("max_logs_per_batch", 1000)
        anom = ai.get("anomaly_detection", {})
        self.anomaly_interval: int = anom.get("interval_minutes", 15)
        self.anomaly_sensitivity: str = anom.get("sensitivity", "medium")

        w = raw.get("web", {})
        self.web_enabled: bool = w.get("enabled", False)
        self.web_serve_static: bool = w.get("serve_static", False)
        self.language: str = w.get("language", "ru")

        self.devices: list[dict] = raw.get("devices") or []

    @property
    def db_dsn(self) -> str:
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )
