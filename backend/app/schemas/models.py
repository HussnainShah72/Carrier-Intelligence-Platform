"""
Request/response models.

Validation lives here so a malformed request is rejected at the edge with a
clear message, before it reaches any service.  Field limits are deliberate:
they are the first line of defence against oversized input and prompt-injection
payloads smuggled through a "job title".
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class RoleAnalysisRequest(BaseModel):
    role_title: str = Field(min_length=2, max_length=120)
    location: str = Field(default="", max_length=80)
    seniority: Literal["any", "entry", "junior", "mid", "senior", "lead"] = "any"
    use_scraping: bool = True
    use_llm: bool = True
    max_postings: int = Field(default=24, ge=1, le=60)

    @field_validator("role_title")
    @classmethod
    def _clean_title(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("A job title is required.")
        # A "job title" containing newlines or braces is an injection attempt,
        # not a job title.
        if any(ch in cleaned for ch in "{}<>|`"):
            raise ValueError("That job title contains characters that are not allowed.")
        return cleaned

    @field_validator("location")
    @classmethod
    def _clean_location(cls, value: str) -> str:
        return " ".join(value.split())


class GapAnalysisRequest(BaseModel):
    cv_id: str = Field(min_length=3, max_length=64)
    role_analysis_id: str = Field(min_length=3, max_length=64)
    with_advice: bool = True


class ImproveBulletsRequest(BaseModel):
    bullets: list[str] = Field(min_length=1, max_length=12)
    role_title: str = Field(default="", max_length=120)
    cv_id: str = Field(default="", max_length=64)

    @field_validator("bullets")
    @classmethod
    def _clean_bullets(cls, value: list[str]) -> list[str]:
        cleaned = [" ".join(b.split()) for b in value if b and b.strip()]
        if not cleaned:
            raise ValueError("At least one non-empty bullet point is required.")
        for bullet in cleaned:
            if len(bullet) > 600:
                raise ValueError("Each bullet point must be 600 characters or fewer.")
        return cleaned


class BulletDecisionRequest(BaseModel):
    decision: Literal["accepted", "rejected", "pending"]


class StartInterviewRequest(BaseModel):
    role_title: str = Field(min_length=2, max_length=120)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    mode: Literal["voice", "text"] = "voice"
    cv_id: str = Field(default="", max_length=64)
    role_analysis_id: str = Field(default="", max_length=64)

    @field_validator("role_title")
    @classmethod
    def _clean_title(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if any(ch in cleaned for ch in "{}<>|`"):
            raise ValueError("That job title contains characters that are not allowed.")
        return cleaned


class InterviewTurnRequest(BaseModel):
    """A text-mode turn, or the fallback when speech recognition fails."""

    text: str = Field(default="", max_length=6000)
    speak: bool = True

    @field_validator("text")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        return value.strip()


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2400)
    voice: str = Field(default="", max_length=80)


class SettingsUpdateRequest(BaseModel):
    """Runtime-adjustable settings (persisted to the backend .env file)."""

    llm_provider: Literal["anthropic", "openai", "gemini", "groq", "ollama", "offline"] | None = None
    llm_model: str | None = Field(default=None, max_length=120)
    llm_fast_model: str | None = Field(default=None, max_length=120)
    stt_model_size: str | None = Field(default=None, max_length=40)
    tts_engine: Literal["piper", "sapi", "auto"] | None = None
    tts_voice: str | None = Field(default=None, max_length=80)
    scrape_enabled: bool | None = None
    stt_enabled: bool | None = None
    tts_enabled: bool | None = None


class ErrorResponse(BaseModel):
    error: dict[str, Any]
