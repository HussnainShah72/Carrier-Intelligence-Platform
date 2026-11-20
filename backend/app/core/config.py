"""
Central configuration.

Every tunable lives here and is overridable from the environment (.env), so no
secret is ever hard-coded or committed.  See `.env.example` for the full list.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
MODELS_DIR = DATA_DIR / "models"
UPLOADS_DIR = DATA_DIR / "uploads"
AUDIO_DIR = DATA_DIR / "audio"
LOG_DIR = DATA_DIR / "logs"

LLMProvider = Literal["anthropic", "openai", "gemini", "groq", "ollama", "offline"]


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------------------------------------------------------------- general
    app_name: str = "Career Intelligence Platform"
    environment: Literal["development", "production"] = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    database_path: Path = DATA_DIR / "career_intelligence.db"

    # ------------------------------------------------------------------- LLM
    # Which provider to talk to.  The default is "ollama": a local model server,
    # so the product works out of the box with no API key and no data leaving
    # the machine.  Set a cloud provider + key in .env for higher quality.
    # "offline" uses the deterministic built-in engine (no LLM at all) and is
    # what the reproducible unit tests run against.
    llm_provider: LLMProvider = "ollama"
    llm_model: str = ""
    # Separate, smaller model for the latency-critical interview turn.  Keeping
    # the two apart is a deliberate trade-off: reasoning quality for the heavy
    # JSON tasks, response speed for the live conversation.
    llm_fast_model: str = ""
    llm_temperature: float = 0.3
    llm_max_tokens: int = 1400
    llm_timeout_seconds: float = 90.0

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    groq_api_key: str = ""
    ollama_base_url: str = "http://127.0.0.1:11434"

    # --------------------------------------------------------------- uploads
    max_upload_bytes: int = 5 * 1024 * 1024          # 5 MB
    allowed_upload_suffixes: str = ".pdf,.docx,.txt"
    max_cv_characters: int = 60_000

    # ------------------------------------------------- job posting collection
    scrape_enabled: bool = True
    scrape_timeout_seconds: float = 20.0
    scrape_max_postings: int = 24
    scrape_per_source_limit: int = 10
    scrape_min_interval_seconds: float = 1.2         # politeness / rate limit
    scrape_user_agent: str = (
        "CareerIntelligencePlatform/1.0 (university NLP course project; "
        "contact: via repository issues)"
    )
    scrape_cache_ttl_seconds: int = 60 * 60 * 6      # 6 h on-disk cache

    # ------------------------------------------------------- speech (LOCAL!)
    stt_enabled: bool = True
    stt_model_size: str = "base.en"                  # tiny.en|base.en|small.en
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"
    stt_beam_size: int = 1
    stt_language: str = "en"
    stt_max_audio_seconds: float = 180.0

    tts_enabled: bool = True
    tts_engine: Literal["piper", "sapi", "auto"] = "auto"
    tts_voice: str = "en_US-amy-medium"
    tts_speed: float = 1.0
    tts_sample_rate: int = 22050

    # ----------------------------------------------------------- interviewing
    interview_max_turns: int = 26
    interview_history_turns: int = 10

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _normalise_provider(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip().lower()
            if v in ("", "none", "mock", "local-rules"):
                return "offline"
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_suffixes(self) -> set[str]:
        return {s.strip().lower() for s in self.allowed_upload_suffixes.split(",") if s.strip()}

    # Model ids rotate, especially on Groq, where the Llama models this project
    # originally defaulted to are no longer served. Verify against the provider
    # before trusting a default:
    #     curl -H "Authorization: Bearer $GROQ_API_KEY" \
    #          https://api.groq.com/openai/v1/models
    _PROVIDER_DEFAULT_MODELS = {
        "anthropic": "claude-sonnet-5-5",
        "openai": "gpt-4o-mini",
        "gemini": "gemini-2.0-flash",
        "groq": "openai/gpt-oss-120b",
        "ollama": "qwen2.5:3b-instruct-q4_K_M",
        "offline": "offline-deterministic-v1",
    }

    _PROVIDER_FAST_MODELS = {
        "anthropic": "claude-haiku-5-5",
        "openai": "gpt-4o-mini",
        "gemini": "gemini-2.0-flash",
        "groq": "openai/gpt-oss-20b",
        "ollama": "llama3.2:3b",
        "offline": "offline-deterministic-v1",
    }

    # Free API tiers rate-limit aggressively (Groq's free tier allows roughly
    # 8,000 tokens per minute, and one interview turn costs ~2,800). Requests
    # are retried with backoff, honouring the provider's Retry-After header,
    # rather than failing the user's turn.
    llm_max_retries: int = 6

    @property
    def default_model(self) -> str:
        """Model id to use when LLM_MODEL is not set explicitly."""
        if self.llm_model:
            return self.llm_model
        return self._PROVIDER_DEFAULT_MODELS[self.llm_provider]

    @property
    def fast_model(self) -> str:
        """Model id for the live interview turn (latency over depth)."""
        if self.llm_fast_model:
            return self.llm_fast_model
        return self._PROVIDER_FAST_MODELS[self.llm_provider]

    def api_key_for_provider(self) -> str:
        return {
            "anthropic": self.anthropic_api_key,
            "openai": self.openai_api_key,
            "gemini": self.gemini_api_key,
            "groq": self.groq_api_key,
            "ollama": "n/a",
            "offline": "n/a",
        }[self.llm_provider]

    @property
    def llm_configured(self) -> bool:
        if self.llm_provider in ("offline", "ollama"):
            return True
        return bool(self.api_key_for_provider())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    for folder in (DATA_DIR, MODELS_DIR, UPLOADS_DIR, AUDIO_DIR, LOG_DIR):
        folder.mkdir(parents=True, exist_ok=True)
    return settings


settings = get_settings()
