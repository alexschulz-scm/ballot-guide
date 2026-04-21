"""
Application configuration via environment variables.

Uses pydantic-settings BaseSettings. Module-level singleton: ``settings``.
All required variables (no default) cause startup failure if missing.
"""

import logging

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # Database
    DB_PATH: str = "/data/ballot-guide.db"

    # API
    APP_VERSION: str = "1.0.0"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # Gemini (LLM for orchestrator)
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # External APIs (passed to MCP servers)
    GOOGLE_CIVIC_API_KEY: str
    NEWSAPI_KEY: str
    OPENFEC_API_KEY: str

    # Development — master mock override
    MOCK_EXTERNAL_APIS: bool = False
    MOCK_LLM: bool = False

    # Per-source mock flags (checked when MOCK_EXTERNAL_APIS=false)
    MOCK_CIVIC_API: bool = False
    MOCK_OPENFEC_API: bool = False
    MOCK_FL_FINANCE_API: bool = False
    MOCK_BALLOTPEDIA_API: bool = False
    MOCK_FL_ELECTIONS_API: bool = False
    MOCK_NEWSAPI: bool = False
    MOCK_LEGISLATION_API: bool = False

    def validate_required(self) -> None:
        """
        Called at startup for explicit logging.
        Pydantic already validates presence; this logs confirmation.
        """
        required_keys = [
            "GEMINI_API_KEY",
            "GOOGLE_CIVIC_API_KEY",
            "NEWSAPI_KEY",
            "OPENFEC_API_KEY",
        ]
        for key in required_keys:
            value = getattr(self, key, "")
            if value:
                logger.info("Config: %s = <loaded>", key)
            else:
                logger.warning("Config: %s is EMPTY", key)
        logger.info(
            "Config: DB_PATH=%s, LOG_LEVEL=%s, MOCK_LLM=%s, MOCK_EXTERNAL_APIS=%s",
            self.DB_PATH,
            self.LOG_LEVEL,
            self.MOCK_LLM,
            self.MOCK_EXTERNAL_APIS,
        )


# Module-level singleton — crashes at import time if required vars missing.
# This is intentional: fail fast at startup, not on first request.
# Tests that don't need config should avoid importing this module.
settings = Settings()
