"""
System routes: dashboard data, health checks, settings and storage management.

These back the Dashboard and Settings pages, and the health endpoint is what a
marker or examiner should hit first: it states plainly which engine is running
each part of the pipeline and whether anything is degraded.
"""

from __future__ import annotations

import platform
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from app.core.config import BACKEND_DIR, settings
from app.core.db import loads, query_all, query_one, reset_database, storage_stats
from app.core.logging_setup import get_logger
from app.schemas.models import SettingsUpdateRequest
from app.services.interview import rubric
from app.services.jobs import sources as job_sources
from app.services.jobs.http import fetcher
from app.services.llm.client import check_ollama, get_llm, probe_llm, reset_llm
from app.services.metrics import recorder as metrics
from app.services.skills import taxonomy as tx
from app.services.speech import stt, tts

log = get_logger(__name__)
router = APIRouter(tags=["System"])

_STARTED_AT = time.time()
ENV_PATH = BACKEND_DIR / ".env"

# Only these may be changed from the UI; nothing secret is writable this way.
WRITABLE_SETTINGS = {
    "llm_provider": "LLM_PROVIDER",
    "llm_model": "LLM_MODEL",
    "llm_fast_model": "LLM_FAST_MODEL",
    "stt_model_size": "STT_MODEL_SIZE",
    "tts_engine": "TTS_ENGINE",
    "tts_voice": "TTS_VOICE",
    "scrape_enabled": "SCRAPE_ENABLED",
    "stt_enabled": "STT_ENABLED",
    "tts_enabled": "TTS_ENABLED",
}


# ===========================================================================
# Health
# ===========================================================================


@router.get("/system/health")
def health(deep: bool = False) -> dict[str, Any]:
    """
    Health of every subsystem.

    `deep=true` additionally probes the LLM and every job source over the
    network, which is slower but is what you want before a demo.
    """
    client = get_llm()
    llm_info = probe_llm() if deep else client.describe() | {"reachable": None}

    components = {
        "database": _database_health(),
        "llm": llm_info,
        "speech_recognition": stt.describe(),
        "text_to_speech": tts.describe(),
        "job_sources": (
            {"checked": True, "results": job_sources.check_sources()}
            if deep
            else {"checked": False, "configured": len(job_sources.ALL_SOURCES),
                  "enabled": settings.scrape_enabled}
        ),
        "skill_taxonomy": tx.taxonomy_stats(),
        "scrape_cache": fetcher.cache_stats(),
    }

    degradations: list[str] = []
    if client.is_offline:
        degradations.append(
            "No language model is configured, so the deterministic offline engine is being used. "
            "Output quality is visibly lower. Set LLM_PROVIDER and the matching key in backend/.env."
        )
    elif client.provider == "ollama":
        ollama = check_ollama()
        llm_info = llm_info | {"ollama": ollama}
        components["llm"] = llm_info
        if llm_info.get("reachable") is None:
            llm_info["reachable"] = bool(ollama.get("reachable")) and not ollama.get("models_missing")
        if not ollama.get("reachable") or ollama.get("models_missing"):
            degradations.append(ollama.get("detail", "Ollama is not ready."))
    if not stt.is_available():
        degradations.append("faster-whisper is not installed, so the voice interview cannot transcribe.")
    elif not settings.stt_enabled:
        degradations.append("Speech recognition is switched off in settings.")
    if not any(v["ready"] for v in tts.list_piper_voices()):
        degradations.append(
            "No Piper voice is installed, so the interviewer will use the lower-quality operating "
            "system voice. Run: python scripts/download_speech_models.py"
        )
    if not settings.scrape_enabled:
        degradations.append("Live job posting collection is switched off in settings.")

    return {
        "status": "degraded" if degradations else "ok",
        "app": settings.app_name,
        "version": "1.0.0",
        "uptime_seconds": round(time.time() - _STARTED_AT, 1),
        "environment": settings.environment,
        "components": components,
        "degradations": degradations,
        "runtime": {
            "python": sys.version.split()[0],
            "platform": f"{platform.system()} {platform.release()}",
            "machine": platform.machine(),
        },
        "privacy": {
            "cv_storage": "Local SQLite file on this machine only.",
            "audio_storage": "Recordings are transcribed in memory and the temporary file is "
                             "deleted immediately. No audio is retained.",
            "speech_processing": "Fully local (faster-whisper + Piper). No audio leaves the machine.",
            "llm_processing": (
                "Fully local (no external calls)." if client.provider in ("offline", "ollama")
                else f"CV text, role titles and interview answers are sent to {client.provider} "
                     "for analysis. Switch LLM_PROVIDER to 'ollama' or 'offline' to keep everything local."
            ),
            "scraping": "Only public job-board APIs and feeds are queried. No personal data is sent.",
        },
    }


def _database_health() -> dict[str, Any]:
    try:
        row = query_one("SELECT value FROM schema_meta WHERE key = 'version'")
        stats = storage_stats()
        return {
            "ok": True,
            "schema_version": row["value"] if row else "unknown",
            "path": stats["path"],
            "size_bytes": stats["size_bytes"],
            "row_counts": stats["row_counts"],
        }
    except Exception as exc:
        log.error("Database health check failed: %s", exc)
        return {"ok": False, "detail": str(exc)[:200]}


@router.get("/system/taxonomy")
def taxonomy() -> dict[str, Any]:
    """The skill taxonomy, for the Settings page and the viva demo."""
    return {
        "stats": tx.taxonomy_stats(),
        "categories": tx.ALL_CATEGORIES,
        "skills": [
            {
                "canonical": name,
                "category": meta["category"],
                "aliases": meta["aliases"],
                "implies": meta["implies"],
            }
            for name, meta in sorted(tx.CANONICAL_SKILLS.items())
        ],
    }


@router.post("/system/normalise")
def normalise_probe(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Live skill-normalisation demo: paste variants, see them collapse.

    Exists for the viva - it is the clearest way to show that "React", "ReactJS"
    and "React.js" really do become one skill, and which stage decided it.
    """
    from app.services.skills.normalizer import explain_merge, normalise_skills
    from app.services.skills.text_norm import normalise_key, split_skill_list

    raw = payload.get("skills")
    if isinstance(raw, str):
        items = split_skill_list(raw)
    elif isinstance(raw, list):
        items = [str(s) for s in raw]
    else:
        items = []

    resolved = normalise_skills(items)
    return {
        "input": items,
        "input_count": len(items),
        "output": [s.to_dict() for s in resolved],
        "output_count": len(resolved),
        "merge_evidence": explain_merge(resolved),
        "lookup_keys": {item: normalise_key(item) for item in items[:40]},
    }


# ===========================================================================
# Dashboard
# ===========================================================================


@router.get("/system/dashboard")
def dashboard() -> dict[str, Any]:
    """Everything the Dashboard page needs, in one round trip."""
    cv_rows = query_all(
        "SELECT id, filename, profile_json, created_at FROM cv_documents ORDER BY created_at DESC LIMIT 5"
    )
    latest_cv = None
    if cv_rows:
        profile = loads(cv_rows[0]["profile_json"], {}) or {}
        latest_cv = {
            "cv_id": cv_rows[0]["id"],
            "filename": cv_rows[0]["filename"],
            "created_at": cv_rows[0]["created_at"],
            "full_name": profile.get("full_name", ""),
            "headline": profile.get("headline", ""),
            "skill_count": len(profile.get("skills") or []),
            "experience_count": len(profile.get("experience") or []),
            "project_count": len(profile.get("projects") or []),
            "education_count": len(profile.get("education") or []),
            "certification_count": len(profile.get("certifications") or []),
            "top_skills": [s.get("canonical") for s in (profile.get("skills") or [])[:12]],
            "warnings": profile.get("warnings") or [],
        }

    gap_rows = query_all(
        "SELECT g.id, g.match_percent, g.created_at, g.result_json, r.role_title "
        "FROM gap_analyses g LEFT JOIN role_analyses r ON r.id = g.role_analysis_id "
        "ORDER BY g.created_at DESC LIMIT 6"
    )
    gaps = []
    for row in gap_rows:
        result = loads(row["result_json"], {}) or {}
        stats = result.get("stats") or {}
        gaps.append(
            {
                "gap_analysis_id": row["id"],
                "role_title": row["role_title"] or "(unknown role)",
                "match_percent": round(float(row["match_percent"] or 0), 1),
                "matched": stats.get("matched", 0),
                "partial": stats.get("partial", 0),
                "missing": stats.get("missing", 0),
                "created_at": row["created_at"],
            }
        )

    interview_rows = query_all(
        "SELECT id, role_title, difficulty, status, started_at, report_json FROM interviews "
        "ORDER BY started_at DESC LIMIT 6"
    )
    interviews = []
    for row in interview_rows:
        report = loads(row["report_json"], None) or {}
        interviews.append(
            {
                "interview_id": row["id"],
                "role_title": row["role_title"],
                "difficulty": row["difficulty"],
                "status": row["status"],
                "started_at": row["started_at"],
                "overall_score": report.get("overall_score"),
                "overall_band": report.get("overall_band"),
            }
        )

    role_rows = query_all(
        "SELECT id, role_title, source_summary, created_at FROM role_analyses "
        "ORDER BY created_at DESC LIMIT 6"
    )
    roles = [
        {
            "role_analysis_id": r["id"],
            "role_title": r["role_title"],
            "stats": loads(r["source_summary"], {}) or {},
            "created_at": r["created_at"],
        }
        for r in role_rows
    ]

    activity = query_all(
        "SELECT kind, title, detail, ref_id, created_at FROM activity_log ORDER BY created_at DESC LIMIT 12"
    )

    counts = storage_stats()["row_counts"]
    client = get_llm()

    return {
        "latest_cv": latest_cv,
        "cv_count": counts.get("cv_documents", 0),
        "recent_gaps": gaps,
        "recent_interviews": interviews,
        "recent_roles": roles,
        "activity": [dict(a) for a in activity],
        "counts": counts,
        "performance": metrics.global_metrics(),
        "preparation_progress": _preparation_progress(latest_cv, gaps, interviews),
        "engine_status": {
            "llm": client.describe(),
            "stt_ready": stt.is_available() and settings.stt_enabled,
            "tts_engine": tts.active_engine(),
            "scraping_enabled": settings.scrape_enabled,
        },
    }


def _preparation_progress(latest_cv: Any, gaps: list[dict[str, Any]], interviews: list[dict[str, Any]]) -> dict[str, Any]:
    """A simple, honest checklist of how far the user has got."""
    steps = [
        {"key": "cv", "label": "Upload and parse your CV", "done": latest_cv is not None,
         "href": "/cv"},
        {"key": "role", "label": "Analyse a target job role", "done": bool(gaps) or False,
         "href": "/roles"},
        {"key": "gap", "label": "Run a skill gap analysis", "done": bool(gaps), "href": "/gap"},
        {"key": "improve", "label": "Improve your CV bullet points", "done": False, "href": "/improve"},
        {"key": "interview", "label": "Complete a mock interview", "done": bool(interviews), "href": "/interview"},
        {"key": "feedback", "label": "Review your scored feedback",
         "done": any(i.get("overall_score") is not None for i in interviews), "href": "/results"},
    ]

    counts = storage_stats()["row_counts"]
    if counts.get("role_analyses", 0) > 0:
        next(s for s in steps if s["key"] == "role")["done"] = True
    if counts.get("bullet_improvements", 0) > 0:
        next(s for s in steps if s["key"] == "improve")["done"] = True

    done = sum(1 for s in steps if s["done"])
    best = max((g["match_percent"] for g in gaps), default=0.0)
    scores = [i["overall_score"] for i in interviews if i.get("overall_score") is not None]

    return {
        "steps": steps,
        "completed": done,
        "total": len(steps),
        "percent": round(done / len(steps) * 100, 1),
        "best_match_percent": best,
        "best_interview_score": max(scores) if scores else None,
        "interviews_completed": len([i for i in interviews if i["status"] == "complete"]),
    }


# ===========================================================================
# Settings
# ===========================================================================


@router.get("/system/settings")
def get_settings() -> dict[str, Any]:
    """
    Current settings.

    API keys are reported as present/absent only - the values are never
    returned to the browser.
    """
    return {
        "llm": {
            "provider": settings.llm_provider,
            "model": settings.default_model,
            "fast_model": settings.fast_model,
            "temperature": settings.llm_temperature,
            "max_tokens": settings.llm_max_tokens,
            "configured": settings.llm_configured,
            "available_providers": ["ollama", "offline", "anthropic", "openai", "gemini", "groq"],
            "keys_present": {
                "anthropic": bool(settings.anthropic_api_key),
                "openai": bool(settings.openai_api_key),
                "gemini": bool(settings.gemini_api_key),
                "groq": bool(settings.groq_api_key),
            },
            "ollama_base_url": settings.ollama_base_url,
        },
        "speech": {"stt": stt.describe(), "tts": tts.describe()},
        "scraping": {
            "enabled": settings.scrape_enabled,
            "max_postings": settings.scrape_max_postings,
            "per_source_limit": settings.scrape_per_source_limit,
            "min_interval_seconds": settings.scrape_min_interval_seconds,
            "cache_ttl_seconds": settings.scrape_cache_ttl_seconds,
            "user_agent": settings.scrape_user_agent,
            "sources": job_sources.describe_sources(),
        },
        "uploads": {
            "max_bytes": settings.max_upload_bytes,
            "allowed_suffixes": sorted(settings.allowed_suffixes),
            "max_cv_characters": settings.max_cv_characters,
        },
        "rubric": rubric.as_dict(),
        "storage": storage_stats(),
        "writable": sorted(WRITABLE_SETTINGS),
        "env_file": str(ENV_PATH),
        "env_file_exists": ENV_PATH.exists(),
        "note": "API keys are only ever read from backend/.env and are never returned by this API.",
    }


@router.patch("/system/settings")
def update_settings(request: SettingsUpdateRequest) -> dict[str, Any]:
    """
    Persist a settings change to backend/.env and apply it immediately.

    Only the keys in WRITABLE_SETTINGS can be changed, so this endpoint cannot
    be used to write a secret or an arbitrary variable.
    """
    changes = {k: v for k, v in request.model_dump(exclude_none=True).items() if k in WRITABLE_SETTINGS}
    if not changes:
        return {"updated": {}, "message": "No recognised settings were supplied."}

    _write_env(changes)

    applied: dict[str, Any] = {}
    for key, value in changes.items():
        if hasattr(settings, key):
            object.__setattr__(settings, key, value)
            applied[key] = value

    reset_llm()
    log.info("Settings updated from the UI: %s", applied)
    return {
        "updated": applied,
        "env_file": str(ENV_PATH),
        "llm": get_llm().describe(),
        "message": "Settings saved. Model changes take effect on the next request; a backend restart "
                   "is only needed if a model fails to load.",
    }


def _write_env(changes: dict[str, Any]) -> None:
    """Rewrite backend/.env, preserving comments, other keys and any secrets."""
    lines: list[str] = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    remaining = {WRITABLE_SETTINGS[k]: v for k, v in changes.items()}
    out: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            out.append(line)
            continue
        name = stripped.split("=", 1)[0].strip()
        if name in remaining:
            out.append(f"{name}={_env_value(remaining.pop(name))}")
        else:
            out.append(line)

    if remaining:
        if out and out[-1].strip():
            out.append("")
        out.append("# Updated from the Settings page")
        for name, value in remaining.items():
            out.append(f"{name}={_env_value(value)}")

    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    ENV_PATH.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def _env_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


# ===========================================================================
# Storage management
# ===========================================================================


@router.get("/system/storage")
def storage() -> dict[str, Any]:
    stats = storage_stats()
    stats["scrape_cache"] = fetcher.cache_stats()
    stats["model_cache"] = _directory_size(Path(settings.database_path).parent / "models")
    return stats


def _directory_size(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "size_bytes": 0, "files": 0}
    files = [f for f in path.rglob("*") if f.is_file()]
    return {
        "path": str(path),
        "exists": True,
        "size_bytes": sum(f.stat().st_size for f in files),
        "files": len(files),
    }


@router.delete("/system/storage")
def clear_storage(include_cache: bool = True, include_metrics: bool = True) -> dict[str, Any]:
    """
    Delete all stored user data.

    This is the privacy control: it removes every CV, transcript and analysis
    from the local database.  Downloaded speech models are kept (they contain
    no personal data and are expensive to re-download).
    """
    before = storage_stats()["row_counts"]
    reset_database()
    cache_cleared = fetcher.clear_cache() if include_cache else 0
    metrics_cleared = 0 if include_metrics else 0  # reset_database already removed them

    log.info("User cleared all stored data from the Settings page")
    return {
        "cleared": True,
        "rows_before": before,
        "rows_after": storage_stats()["row_counts"],
        "scrape_cache_entries_cleared": cache_cleared,
        "metrics_cleared": metrics_cleared,
        "note": "Downloaded speech models were kept; they contain no personal data.",
    }
