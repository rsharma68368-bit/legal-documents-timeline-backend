"""
Application configuration using Pydantic Settings.

Centralizes all environment variables and app settings.
Using Pydantic BaseSettings gives us validation and type safety for config.
"""

from functools import lru_cache
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    All sensitive/configurable values should live here.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra env vars not defined here
    )

    # Application
    app_name: str = "Legal Document Timeline API"
    debug: bool = False

    # MongoDB - Motor (async driver) connection string
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_database: str = "legal_timeline_db"

    # Supabase JWT validation - must match Dashboard → Project Settings → API → JWT Secret
    supabase_url: str = "https://your-project.supabase.co"
    supabase_jwt_secret: Optional[str] = None

    @field_validator("supabase_jwt_secret", mode="before")
    @classmethod
    def strip_jwt_secret(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not isinstance(v, str):
            return v
        return v.strip() or None

    # File upload - local storage path
    upload_dir: str = "uploads"
    max_upload_size_mb: int = 50

    # LLM - Groq (free tier; get key at https://console.groq.com)
    groq_api_key: Optional[str] = None
    llm_model: str = "llama-3.1-8b-instant"  # Fast free model on Groq


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings instance.
    Using lru_cache avoids re-reading .env on every request.
    """
    return Settings()
