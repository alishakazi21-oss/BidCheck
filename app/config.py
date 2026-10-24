"""
BidCheck application configuration.

Reads settings from environment variables (with sensible defaults for
local development). All sensitive values come from .env / docker-compose env;
nothing is hard-coded here.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent  # project root


class Settings(BaseSettings):
    """Application-wide settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -----------------------------------------------------------------------
    # Database
    # -----------------------------------------------------------------------
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'bidcheck.db'}"
    db_echo: bool = False  # Set True to log all SQL statements

    # -----------------------------------------------------------------------
    # Extractor backend: "fake" (offline, sidecar JSON) | "llm" (OpenAI)
    # -----------------------------------------------------------------------
    extractor: str = "fake"

    # -----------------------------------------------------------------------
    # LLM settings (only used when EXTRACTOR=llm)
    # -----------------------------------------------------------------------
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    llm_temperature: float = 0.0

    # -----------------------------------------------------------------------
    # Confidence threshold below which a value becomes NEEDS_REVIEW
    # -----------------------------------------------------------------------
    confidence_threshold: float = 0.7

    # -----------------------------------------------------------------------
    # Fuzzy-match threshold for cross-document name comparison (0-100)
    # -----------------------------------------------------------------------
    fuzzy_threshold: int = 85

    # -----------------------------------------------------------------------
    # Paths
    # -----------------------------------------------------------------------
    data_dir: Path = BASE_DIR / "data"
    rules_dir: Path = BASE_DIR / "app" / "rules" / "definitions"
    upload_dir: Path = BASE_DIR / "data" / "uploads"

    # -----------------------------------------------------------------------
    # Application metadata
    # -----------------------------------------------------------------------
    app_name: str = "BidCheck"
    app_version: str = "0.1.0-prototype"
    environment: str = "development"

    # -----------------------------------------------------------------------
    # Mock registry base URL (the tiny FastAPI registry service)
    # -----------------------------------------------------------------------
    registry_base_url: str = "http://localhost:8001"

    # -----------------------------------------------------------------------
    # API server
    # -----------------------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    def __init__(self, **values):
        super().__init__(**values)
        # Ensure data directories exist (silently skip on read-only filesystems, e.g. Vercel)
        for directory in (self.data_dir, self.upload_dir, self.rules_dir):
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass  # Read-only filesystem (serverless environment)


# Singleton settings instance used throughout the application
settings = Settings()
