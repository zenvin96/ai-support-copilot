from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    openai_base_url: str = ""  # 中转站/聚合站填这里，例如 https://api.b.ai/v1
    openai_models: str = ""  # 逗号分隔，覆盖默认模型列表
    deepseek_api_key: str = ""
    default_model: str = "gpt-4o-mini"
    embedding_provider: str = "openai"  # openai | local
    embedding_model: str = "text-embedding-3-small"
    local_embedding_model: str = "BAAI/bge-small-zh-v1.5"  # fastembed ONNX，中文友好，无需 torch

    slack_bot_token: str = ""
    slack_team_id: str = ""
    slack_channel_id: str = ""

    # Email 通知（可选，留空则不发邮件）
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""  # 留空用 smtp_user
    smtp_starttls: bool = True
    notify_email_to: str = ""  # 逗号分隔多个收件人

    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 60 * 24
    require_human_confirm: bool = False
    rate_limit_per_minute: int = 20

    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "app"
    mysql_password: str = "app"
    mysql_database: str = "copilot"
    mysql_readonly_user: str = "readonly"
    mysql_readonly_password: str = "readonly"
    redis_url: str = "redis://localhost:6379/0"
    chroma_host: str = "localhost"
    chroma_port: int = 8001

    upload_dir: str = "uploads"
    chunk_size: int = 220
    chunk_overlap: int = 40
    rag_top_k: int = 4

    @property
    def mysql_url(self) -> str:
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
