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

    # --- xAI / Grok (cloud LLM) ---    
    XAI_API_KEY: str = ""
    GROK_MODEL: str = "grok-4.3"

    # --- Google Gemini (cloud LLM) ---
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"

    # --- Ollama (local LLM) ---
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3:8b"
    OLLAMA_EMBEDDING_MODEL: str = "bge-m3"

    # --- Provider selection ---
    # LLM_PROVIDER controls text generation only.
    # EMBEDDING_PROVIDER controls retrieval/index vectors and should be changed
    # only with an embedding-profile migration/re-embedding plan.
    LLM_PROVIDER: Literal["openai", "ollama", "grok", "gemini"] = "gemini"
    EMBEDDING_PROVIDER: Literal["openai", "ollama", ] = "ollama"

    # --- Cohere (reranking) ---
    CO_API_KEY: str = ""
    COHERE_RERANK_MODEL: str = "rerank-v3.5"
    # ---------- Reranking ----------
    RERANK_PROVIDER: Literal["cohere", "bge"] = "bge"

    # Local BGE
    BGE_RERANK_MODEL: str = "BAAI/bge-reranker-v2-m3"


    # --- Embedding config ---
    EMBEDDING_DIMENSION: int = 1024

    # --- Document processing ---
    MAX_DOCUMENT_PAGES: int = 100
    DOCUMENT_CHUNK_SIZE_TOKENS: int = 500
    DOCUMENT_CHUNK_OVERLAP_TOKENS: int = 100

    # --- OCR ---
    TESSERACT_PATH: str = ""

    # --- MVP ---
    MVP_COMPANY_ID: str = "7bf697fc-7220-40c7-9678-542d624d22ad"

    # --- Email delivery ---
    # "mock" → logs to console only, never fails
    # "sendgrid" → calls SendGrid API v3
    EMAIL_PROVIDER: Literal["mock", "sendgrid"] = "mock"
    SENDGRID_API_KEY: str = ""
    SENDGRID_FROM_EMAIL: str = "noreply@invoicesystem.com"

    # --- SMS delivery ---
    # "mock" → logs to console only, never fails
    # "twilio" → calls Twilio REST API
    SMS_PROVIDER: Literal["mock", "twilio"] = "mock"
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
