"""
app/config.py
Application settings loaded from environment variables.

Local dev: copy .env.example → .env and fill in values.
Production: set as Fly.io secrets.
"""
from __future__ import annotations

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Core ──────────────────────────────────────────────────────────────
    ENVIRONMENT: str = "development"
    APP_NAME: str = "tailor-resume-web"
    API_VERSION: str = "v1"

    # ── Clerk Auth ─────────────────────────────────────────────────────────
    # RS256 public key PEM from Clerk Dashboard → API Keys → JWT Templates
    CLERK_PEM_KEY: str = ""
    CLERK_FRONTEND_API_URL: str = ""  # e.g. https://clerk.your-domain.com

    # ── Supabase (optional — falls back to SQLite if not set) ──────────────
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""

    # ── Pinecone (optional) ────────────────────────────────────────────────
    PINECONE_API_KEY: str = ""
    PINECONE_INDEX: str = "tailor-resume-profiles"

    # ── OpenAI embeddings (optional — falls back to TF-IDF) ───────────────
    OPENAI_API_KEY: str = ""

    # ── Anthropic (for Claude-assisted PDF parsing / bullet enrichment) ────
    ANTHROPIC_API_KEY: str = ""

    # ── CORS ───────────────────────────────────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def has_supabase(self) -> bool:
        return bool(self.SUPABASE_URL and self.SUPABASE_SERVICE_KEY)

    @property
    def has_pinecone(self) -> bool:
        return bool(self.PINECONE_API_KEY)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
