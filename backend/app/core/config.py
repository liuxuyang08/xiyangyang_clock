from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="dev", validation_alias="APP_ENV")
    app_name: str = Field(default="语音版日历工具", validation_alias="APP_NAME")
    database_url: str = Field(default="", validation_alias="DATABASE_URL")
    redis_url: str = Field(default="", validation_alias="REDIS_URL")
    jwt_secret: str = Field(default="", validation_alias="JWT_SECRET")
    timezone: str = Field(default="Asia/Shanghai", validation_alias="TIMEZONE")
    openai_api_base_url: str = Field(
        default="https://api.openai.com/v1",
        validation_alias=AliasChoices("OPENAI_API_BASE_URL", "API_BASE_URL"),
    )
    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("OPENAI_API_KEY", "API_KEY"),
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("OPENAI_MODEL", "API_MODEL"),
    )
    ws_heartbeat_interval: int = Field(
        default=30,
        validation_alias="WS_HEARTBEAT_INTERVAL",
        gt=0,
    )
    reminder_scan_interval: int = Field(
        default=60,
        validation_alias="REMINDER_SCAN_INTERVAL",
        gt=0,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
