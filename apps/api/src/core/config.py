from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NeedWise Copilot API"
    environment: str = "development"
    database_url: str = "sqlite:///./needwise.db"
    cors_origins: list[str] | str = ["http://localhost:3000"]
    products_data_path: str = "../../data/demo/products.json"
    policy_embedding_dimension: int = 384

    # Support both documented execution locations: repository root and apps/api.
    # Explicit process environment variables still have higher priority.
    model_config = SettingsConfigDict(env_file=("../../.env", ".env"), extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",")]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
