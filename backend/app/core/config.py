"""
Application configuration. All secrets from env vars.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Literal


class Settings(BaseSettings):
    # --- App ---
    APP_NAME: str = "Invoice Analysis API"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # --- CORS ---
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # --- Supabase ---
    SUPABASE_URL: str
    SUPABASE_SERVICE_KEY: str  # service_role key — bypasses RLS

    # --- OpenAI ---
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    # --- Ollama (local LLM) ---
    # Base URL for Ollama API. Default is localhost standard port.
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"  # outputs 768-dim, zero-padded to 1536

    # --- LLM Provider ---
    # Controls which backend handles chat completion AND embeddings.
    # "openai"  → uses OpenAI API (requires OPENAI_API_KEY)
    # "ollama"  → uses local Ollama instance (requires Ollama running locally)
    LLM_PROVIDER: Literal["openai", "ollama"] = "openai"

    # --- Embedding config ---
    # Stored vector dimension in pgvector. Do NOT change after first backfill
    # without dropping and recreating invoice_embeddings table.
    EMBEDDING_DIMENSION: int = 1536

    # --- OCR ---
    TESSERACT_PATH: str = ""  # e.g. "D:\\tess\\tesseract.exe" on Windows

    # --- MVP ---
    # Hardcoded company_id until auth layer is added.
    MVP_COMPANY_ID: str = "7bf697fc-7220-40c7-9678-542d624d22ad"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()