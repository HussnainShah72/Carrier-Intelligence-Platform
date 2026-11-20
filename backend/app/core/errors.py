"""
Application error types.

Every error surfaced to the browser carries a stable `code` and a message that
is safe to display.  Internal details (stack traces, provider payloads, API
keys) stay in the server log and never reach the client.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for all expected, user-presentable failures."""

    status_code: int = 400
    code: str = "app_error"

    def __init__(self, message: str, *, details: Any | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code:
            self.code = code

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"error": {"code": self.code, "message": self.message}}
        if self.details is not None:
            payload["error"]["details"] = self.details
        return payload


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class UnsupportedFileError(AppError):
    status_code = 415
    code = "unsupported_file"


class FileTooLargeError(AppError):
    status_code = 413
    code = "file_too_large"


class ExtractionError(AppError):
    status_code = 422
    code = "extraction_failed"


class EmptyDocumentError(AppError):
    status_code = 422
    code = "empty_document"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class LLMError(AppError):
    status_code = 502
    code = "llm_unavailable"


class LLMOutputError(AppError):
    status_code = 502
    code = "llm_invalid_output"


class ScrapeError(AppError):
    status_code = 502
    code = "scrape_failed"


class SpeechError(AppError):
    status_code = 503
    code = "speech_unavailable"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
