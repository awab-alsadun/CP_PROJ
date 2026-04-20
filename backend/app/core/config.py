"""
Application configuration. All secrets from env vars.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


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
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    # --- OCR ---
    TESSERACT_PATH: str = ""  # e.g. "D:\\tess\\tesseract.exe" on Windows

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()