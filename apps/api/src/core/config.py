from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NeedWise Copilot API"
    environment: str = "development"
    database_url: str = "sqlite:///./needwise.db"
    cors_origins: list[str] | str = ["http://localhost:3000"]
    products_data_path: str = "../../data/demo/products.json"
    realdata_processed_path: str = "../../data/realdata/processed"

    # LLM router (ADR A6): primary = local vLLM (OpenAI-compatible), fallback = cloud.
    llm_base_url: str = "http://localhost:8001/v1"
    llm_api_key: str = ""
    llm_model: str = "local-model"
    llm_fallback_base_url: str = "https://api.openai.com/v1"
    llm_fallback_api_key: str = ""
    llm_fallback_model: str = "gpt-4o-mini"
    # Off by default: demo runs pure on-prem; enable in dev for cloud fallback.
    llm_fallback_enabled: bool = False
    llm_timeout_seconds: float = 30.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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

