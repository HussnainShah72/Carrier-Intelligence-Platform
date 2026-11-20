"""API routes for Module 1 - CV upload and parsing."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, UploadFile

from app.core.config import settings
from app.core.db import dumps, execute, loads, log_activity, new_id, query_all, query_one, utcnow
from app.core.errors import EmptyDocumentError, NotFoundError
from app.core.logging_setup import get_logger
from app.services.cv.extractor import extract_document
from app.services.cv.parser import parse_cv
from app.services.improve.bullets import rank_bullets

log = get_logger(__name__)
router = APIRouter(prefix="/cv", tags=["CV"])


@router.post("/upload")
async def upload_cv(file: UploadFile = File(...)) -> dict[str, Any]:
    """
    Upload a PDF/DOCX/TXT CV, extract its text and parse it into structured data.

    The response is the complete profile plus the parser's own honesty
    reporting: warnings, which sections were found, and anything the LLM
    proposed that the CV did not support (`rejected_claims`).
    """
    data = await file.read()
    document = extract_document(file.filename or "cv", data)

    if not document.text.strip():
        raise EmptyDocumentError("No readable text was found in that file.")

    profile, usage = parse_cv(document.text)

    cv_id = new_id("cv")
    execute(
        "INSERT INTO cv_documents(id, filename, file_type, size_bytes, sha256, raw_text, char_count, "
        "extractor, profile_json, parse_warnings, parse_mode, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            cv_id, file.filename or "cv", document.file_type, document.size_bytes, document.sha256,
            document.text, document.char_count, document.extractor, dumps(profile.to_dict()),
            dumps(list(document.warnings or []) + profile.warnings), profile.parse_mode, utcnow(),
        ),
    )
    log_activity("cv_upload", f"Parsed CV: {file.filename}",
                 f"{len(profile.skills)} skills, {len(profile.experience)} roles", cv_id)

    return {
        "cv_id": cv_id,
        "filename": file.filename,
        "file_type": document.file_type,
        "size_bytes": document.size_bytes,
        "char_count": document.char_count,
        "page_count": document.page_count,
        "extractor": document.extractor,
        "extraction_warnings": document.warnings,
        "profile": profile.to_dict(),
        "bullet_ranking": rank_bullets(profile.all_bullets),
        "llm_usage": usage.to_dict() if usage else None,
        "created_at": utcnow(),
    }


@router.get("/limits")
def upload_limits() -> dict[str, Any]:
    return {
        "max_upload_bytes": settings.max_upload_bytes,
        "max_upload_mb": round(settings.max_upload_bytes / 1_048_576, 1),
        "allowed_suffixes": sorted(settings.allowed_suffixes),
        "max_cv_characters": settings.max_cv_characters,
        "notes": [
            "Scanned (image-only) PDFs are rejected: this tool does not run OCR.",
            "Password-protected PDFs must be unlocked before upload.",
            "Your CV stays on this machine. It is stored in the local SQLite database only.",
        ],
    }


@router.get("")
def list_cvs(limit: int = 25) -> dict[str, Any]:
    rows = query_all(
        "SELECT id, filename, file_type, size_bytes, char_count, extractor, profile_json, "
        "parse_mode, created_at FROM cv_documents ORDER BY created_at DESC LIMIT ?",
        (max(1, min(limit, 100)),),
    )
    items = []
    for row in rows:
        profile = loads(row["profile_json"], {}) or {}
        items.append(
            {
                "cv_id": row["id"],
                "filename": row["filename"],
                "file_type": row["file_type"],
                "size_bytes": row["size_bytes"],
                "char_count": row["char_count"],
                "parse_mode": row["parse_mode"],
                "created_at": row["created_at"],
                "full_name": profile.get("full_name", ""),
                "skill_count": len(profile.get("skills") or []),
                "experience_count": len(profile.get("experience") or []),
                "project_count": len(profile.get("projects") or []),
            }
        )
    return {"items": items, "count": len(items)}


@router.get("/{cv_id}")
def get_cv(cv_id: str) -> dict[str, Any]:
    row = query_one("SELECT * FROM cv_documents WHERE id = ?", (cv_id,))
    if row is None:
        raise NotFoundError("That CV could not be found. It may have been cleared from storage.")

    profile = loads(row["profile_json"], {}) or {}
    return {
        "cv_id": row["id"],
        "filename": row["filename"],
        "file_type": row["file_type"],
        "size_bytes": row["size_bytes"],
        "char_count": row["char_count"],
        "extractor": row["extractor"],
        "parse_mode": row["parse_mode"],
        "extraction_warnings": loads(row["parse_warnings"], []) or [],
        "profile": profile,
        "bullet_ranking": rank_bullets(profile.get("all_bullets") or []),
        "created_at": row["created_at"],
    }


@router.get("/{cv_id}/text")
def get_cv_text(cv_id: str) -> dict[str, Any]:
    """The raw extracted text, for the 'show me what you actually read' view."""
    row = query_one("SELECT raw_text, filename, char_count FROM cv_documents WHERE id = ?", (cv_id,))
    if row is None:
        raise NotFoundError("That CV could not be found.")
    return {"cv_id": cv_id, "filename": row["filename"], "char_count": row["char_count"], "text": row["raw_text"]}


@router.delete("/{cv_id}")
def delete_cv(cv_id: str) -> dict[str, Any]:
    row = query_one("SELECT filename FROM cv_documents WHERE id = ?", (cv_id,))
    if row is None:
        raise NotFoundError("That CV could not be found.")
    execute("DELETE FROM cv_documents WHERE id = ?", (cv_id,))
    log_activity("cv_delete", f"Deleted CV: {row['filename']}", "", cv_id)
    return {"deleted": True, "cv_id": cv_id}
