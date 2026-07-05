"""Application configuration.

All settings come from environment variables (or a `.env` file). Secrets such
as connector API keys and the encryption key are only ever read from the
environment — never hardcoded or stored in the database.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Adverse Intelligence Platform"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://aip:change-me@localhost:5432/aip"

    # Security
    encryption_key: str = ""  # Fernet key; empty => plaintext (dev only)
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    api_rate_limit: str = "60/minute"

    # Pipeline behaviour
    inline_worker: bool = False
    mock_connectors: bool = True
    connector_timeout_seconds: float = 20.0
    connector_max_retries: int = 2
    connector_rate_limit_per_second: float = 2.0
    worker_poll_interval_seconds: float = 2.0
    data_retention_days: int = 365

    # AI summarisation
    anthropic_api_key: str = ""
    ai_model: str = "claude-opus-4-8"
    ai_max_tokens: int = 16000

    # Connector credentials / endpoints
    google_api_key: str = ""
    google_cse_id: str = ""
    newsapi_key: str = ""
    brave_api_key: str = ""
    companies_house_api_key: str = ""
    fca_api_email: str = ""
    fca_api_key: str = ""
    # Live FCDO XML feed — the authoritative UK list (OFSI JSON retired 01/2026).
    uk_sanctions_list_url: str = (
        "https://sanctionslist.fcdo.gov.uk/docs/UK-Sanctions-List.xml"
    )
    insolvency_api_url: str = ""
    insolvency_api_key: str = ""

    # Config files (tunable without code changes)
    risk_config_path: Path = Field(default=BASE_DIR / "config" / "risk_weights.yaml")
    matching_config_path: Path = Field(default=BASE_DIR / "config" / "matching_weights.yaml")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
