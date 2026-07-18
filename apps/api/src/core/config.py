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

    # LLM router (ADR A6): primary = OpenRouter API, Qwen3.6-27B (ADR A2'',
    # supersedes A2/A2' -- no self-host, no FPT AI Factory). OpenAI-compatible.
    # No fallback provider chosen yet (only one provider = OpenRouter today).
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_api_key: str = ""
    llm_model: str = "qwen/qwen3.6-27b"
    llm_fallback_base_url: str = ""
    llm_fallback_api_key: str = ""
    llm_fallback_model: str = ""
    llm_fallback_enabled: bool = False
    llm_timeout_seconds: float = 30.0

    # Chat pipeline switch: "ai" = S1–S8 advisory pipeline (needs LLM_API_KEY),
    # "mock" = legacy rule-based MockChatService (no LLM, demo-safe).
    chat_pipeline: str = "ai"

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

