from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "EchoWhale API"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    default_user_id: str = "demo-user"
    default_user_name: str = "Echo Learner"
    allowed_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    database_url: str = ""
    r2_bucket: str = "echo-whale-media"
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_endpoint: str = ""
    r2_signed_url_ttl_seconds: int = 900
    media_max_file_size: int = 10 * 1024 * 1024
    media_allowed_content_types: Annotated[list[str], NoDecode] = [
        "image/jpeg",
        "image/png",
        "image/webp",
    ]
    llm_provider: str = "mock"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("allowed_origins", "media_allowed_content_types", mode="before")
    @classmethod
    def split_csv_values(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
