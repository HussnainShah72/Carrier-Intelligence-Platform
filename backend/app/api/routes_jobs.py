"""API routes for Module 2 - job posting collection and role skill generation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.core.db import dumps, execute, loads, log_activity, new_id, query_all, query_one, utcnow
from app.core.errors import NotFoundError
from app.core.logging_setup import get_logger
from app.schemas.models import RoleAnalysisRequest
from app.services.jobs import sources as job_sources
from app.services.jobs.collector import analyse_role
from app.services.jobs.http import fetcher
from app.services.llm.client import summarise_usages
from app.services.skills.text_norm import normalise_key

log = get_logger(__name__)
router = APIRouter(prefix="/roles", tags=["Job roles"])


@router.post("/analyse")
def analyse(request: RoleAnalysisRequest) -> dict[str, Any]:
    """
    Collect live job postings for a role AND generate its requirements with an
    LLM, then return the combined, normalised, provenance-tagged skill list.
    """
    requirements, usages = analyse_role(
        request.role_title,
        location=request.location,
        seniority=request.seniority,
        use_scraping=request.use_scraping,
        use_llm=request.use_llm,
        max_postings=request.max_postings,
    )
    payload = requirements.to_dict()

    role_id = new_id("role")
    execute(
        "INSERT INTO role_analyses(id, role_title, role_slug, location, seniority, requirements_json, "
        "scrape_json, llm_json, source_summary, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            role_id, requirements.role_title, normalise_key(requirements.role_title),
            request.location, request.seniority, dumps(payload),
            dumps([r.to_dict() for r in requirements.source_reports]),
            dumps(requirements.llm_raw), dumps(payload["stats"]), utcnow(),
        ),
    )

    for posting in requirements.postings:
        execute(
            "INSERT INTO job_postings(id, role_analysis_id, source, source_type, title, company, "
            "location, url, posted_at, description, skills_json, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                new_id("job"), role_id, posting.source, posting.source_type, posting.title,
                posting.company, posting.location, posting.url, posting.posted_at,
                posting.description[:8000], dumps(posting.skills), utcnow(),
            ),
        )

    log_activity(
        "role_analysis",
        f"Analysed role: {requirements.role_title}",
        f"{len(requirements.combined_skills)} skills from {len(requirements.postings)} postings",
        role_id,
    )

    return {
        "role_analysis_id": role_id,
        "requirements": payload,
        "llm_usage": summarise_usages(usages),
        "created_at": utcnow(),
    }


@router.get("/sources")
def list_sources() -> dict[str, Any]:
    """The source catalogue, with the compliance notes shown in the UI."""
    return {
        "sources": job_sources.describe_sources(),
        "cache": fetcher.cache_stats(),
        "compliance": {
            "robots_txt": "Fetched, cached and obeyed for every host before any request.",
            "user_agent": "Identifies this project rather than impersonating a browser.",
            "rate_limiting": "Minimum interval enforced per host; robots.txt crawl-delay honoured.",
            "excluded_sites": (
                "LinkedIn, Indeed and Glassdoor are deliberately NOT scraped: their terms of "
                "service prohibit automated access. Only boards that publish their listings for "
                "programmatic use are queried."
            ),
            "known_limitation": (
                "These boards skew towards remote and technology roles, so coverage for local, "
                "non-technical or highly regulated roles is thinner. This is reported per analysis "
                "rather than hidden."
            ),
        },
    }


@router.get("/sources/health")
def sources_health() -> dict[str, Any]:
    """Live reachability check for every source (bypasses the cache)."""
    results = job_sources.check_sources()
    return {
        "sources": results,
        "reachable": sum(1 for r in results if r.get("reachable")),
        "total": len(results),
    }


@router.get("")
def list_analyses(limit: int = 25) -> dict[str, Any]:
    rows = query_all(
        "SELECT id, role_title, location, seniority, source_summary, created_at "
        "FROM role_analyses ORDER BY created_at DESC LIMIT ?",
        (max(1, min(limit, 100)),),
    )
    return {
        "items": [
            {
                "role_analysis_id": r["id"],
                "role_title": r["role_title"],
                "location": r["location"],
                "seniority": r["seniority"],
                "stats": loads(r["source_summary"], {}) or {},
                "created_at": r["created_at"],
            }
            for r in rows
        ],
        "count": len(rows),
    }


@router.get("/{role_analysis_id}")
def get_analysis(role_analysis_id: str) -> dict[str, Any]:
    row = query_one("SELECT * FROM role_analyses WHERE id = ?", (role_analysis_id,))
    if row is None:
        raise NotFoundError("That role analysis could not be found.")
    return {
        "role_analysis_id": row["id"],
        "role_title": row["role_title"],
        "location": row["location"],
        "seniority": row["seniority"],
        "requirements": loads(row["requirements_json"], {}) or {},
        "source_reports": loads(row["scrape_json"], []) or [],
        "llm_raw": loads(row["llm_json"], {}) or {},
        "created_at": row["created_at"],
    }


@router.get("/{role_analysis_id}/postings")
def get_postings(role_analysis_id: str) -> dict[str, Any]:
    rows = query_all(
        "SELECT * FROM job_postings WHERE role_analysis_id = ? ORDER BY created_at ASC",
        (role_analysis_id,),
    )
    return {
        "role_analysis_id": role_analysis_id,
        "postings": [
            {
                "id": r["id"],
                "source": r["source"],
                "source_type": r["source_type"],
                "title": r["title"],
                "company": r["company"],
                "location": r["location"],
                "url": r["url"],
                "posted_at": r["posted_at"],
                "description": r["description"],
                "skills": loads(r["skills_json"], []) or [],
            }
            for r in rows
        ],
        "count": len(rows),
    }


@router.delete("/cache")
def clear_scrape_cache() -> dict[str, Any]:
    removed = fetcher.clear_cache()
    return {"cleared": removed}


@router.delete("/{role_analysis_id}")
def delete_analysis(role_analysis_id: str) -> dict[str, Any]:
    row = query_one("SELECT role_title FROM role_analyses WHERE id = ?", (role_analysis_id,))
    if row is None:
        raise NotFoundError("That role analysis could not be found.")
    execute("DELETE FROM role_analyses WHERE id = ?", (role_analysis_id,))
    return {"deleted": True, "role_analysis_id": role_analysis_id}
