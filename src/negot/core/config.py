"""
Application configuration and settings.

Configuration values are loaded from environment variables using
`pydantic-settings`. See the file `.env.example` in the repository root
for an example of the required variables.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly typed runtime settings for the Negotiation Companion.

    All configuration options are read from environment variables at
    application startup. Default values are provided where appropriate.
    """

    # Pydantic v2 replacement for `class Config: ...`
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    env: str = Field("dev", validation_alias="NEGOT_ENV", description="Runtime environment.")
    log_level: str = Field("INFO", validation_alias="NEGOT_LOG_LEVEL", description="Logging level.")
    app_url: str = Field("http://localhost:8000", validation_alias="NEGOT_APP_URL", description="Public URL of the API.")

    # Database
    database_url: str = Field(
        ...,
        validation_alias="DATABASE_URL",
        description="SQLAlchemy database URL, e.g. postgresql+asyncpg://user:pass@host:port/db",
    )

    # LLM provider (via LiteLLM)
    litellm_model: Optional[str] = Field(None, validation_alias="LITELLM_MODEL", description="Default model name for LLM calls.")
    litellm_api_key: Optional[str] = Field(None, validation_alias="LITELLM_API_KEY", description="API key for the LLM provider.")
    litellm_base_url: Optional[str] = Field(None, validation_alias="LITELLM_BASE_URL", description="Optional base URL override for LLM provider.")

    # Tavily (web grounding)
    tavily_api_key: Optional[str] = Field(None, validation_alias="TAVILY_API_KEY", description="API key for Tavily search.")
    tavily_search_depth: str = Field(
        "basic",
        validation_alias="TAVILY_SEARCH_DEPTH",
        description="Search depth for Tavily queries (basic or advanced).",
    )
    tavily_max_results: int = Field(
        5,
        validation_alias="TAVILY_MAX_RESULTS",
        description="Maximum number of search results to retrieve per query.",
    )
    tavily_cache_ttl_hours: int = Field(
        48,
        validation_alias="TAVILY_CACHE_TTL_HOURS",
        description="Number of hours to cache Tavily query results.",
    )

    # Optional observability settings for Langfuse
    langfuse_public_key: Optional[str] = Field(None, validation_alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: Optional[str] = Field(None, validation_alias="LANGFUSE_SECRET_KEY")
    langfuse_host: Optional[str] = Field(None, validation_alias="LANGFUSE_HOST")

    @field_validator("env")
    @classmethod
    def validate_env(cls, value: str) -> str:
        valid = {"dev", "test", "prod"}
        if value not in valid:
            raise ValueError(f"NEGOT_ENV must be one of {valid}, got {value}")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()
