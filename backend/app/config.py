"""Application settings loaded from environment."""
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    master_key: str          # base64, 32 bytes
    jwt_secret: str
    jwt_expiry_hours: int = 720
    database_url: str
    log_level: str = "INFO"
    sessions_dir: str = "/app/sessions"


settings = Settings()
