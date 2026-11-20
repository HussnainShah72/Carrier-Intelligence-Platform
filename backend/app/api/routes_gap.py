"""API routes for Module 3 (match and gap analysis) and Module 4 (CV improvement)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.core.db import dumps, execute, loads, log_activity, new_id, query_all, query_one, utcnow
from app.core.errors import NotFoundError
from app.core.logging_setup import get_logger
from app.schemas.models import BulletDecisionRequest, GapAnalysisRequest, ImproveBulletsRequest
from app.services.improve import bullets as improve_service
from app.services.jobs.collector import requirements_from_dict
from app.services.llm import json_guard
from app.services.llm.client import get_llm
from app.services.llm.prompts import GAP_ADVICE_SYSTEM, gap_advice_prompt
from app.services.skills.matcher import analyse_gap, candidate_skill_set

log = get_logger(__name__)
router = APIRouter(tags=["Gap analysis & CV improvement"])


# ===========================================================================
# Module 3 - gap analysis
# ===========================================================================


@router.post("/gap/analyse")
def analyse(request: GapAnalysisRequest) -> dict[str, Any]:
    """Compare one CV against one role analysis and produce the gap report."""
    cv_row = query_one("SELECT profile_json, filename FROM cv_documents WHERE id = ?", (request.cv_id,))
    if cv_row is None:
        raise NotFoundError("That CV could not be found. Upload it again from the CV Analysis page.")

    role_row = query_one(
        "SELECT requirements_json, role_title FROM role_analyses WHERE id = ?", (request.role_analysis_id,)
    )
    if role_row is None:
        raise NotFoundError("That role analysis could not be found. Run the role analysis again.")

    profile = loads(cv_row["profile_json"], {}) or {}
    requirements = requirements_from_dict(loads(role_row["requirements_json"], {}) or {})

    analysis = analyse_gap(
        candidate_skill_set(profile),
        requirements.combined_skills,
        role_title=role_row["role_title"],
    )

    if request.with_advice:
        analysis.advice = _generate_advice(analysis, role_row["role_title"])

    payload = analysis.to_dict()
    gap_id = new_id("gap")
    execute(
        "INSERT INTO gap_analyses(id, cv_id, role_analysis_id, result_json, match_percent, created_at) "
        "VALUES(?,?,?,?,?,?)",
        (gap_id, request.cv_id, request.role_analysis_id, dumps(payload), analysis.match_percent, utcnow()),
    )
    log_activity(
        "gap_analysis",
        f"Gap analysis: {role_row['role_title']}",
        f"{analysis.match_percent:.0f}% coverage, {len(analysis.missing)} missing",
        gap_id,
    )

    return {
        "gap_analysis_id": gap_id,
        "cv_id": request.cv_id,
        "cv_filename": cv_row["filename"],
        "role_analysis_id": request.role_analysis_id,
        "role_title": role_row["role_title"],
        "result": payload,
        "created_at": utcnow(),
    }


def _generate_advice(analysis: Any, role_title: str) -> dict[str, Any]:
    """Learning plan for the computed gaps.  Failure here is not fatal."""
    client = get_llm()
    try:
        payload, _ = client.complete_json(
            gap_advice_prompt(
                role_title,
                [c.requirement for c in analysis.matched],
                [c.requirement for c in analysis.missing],
                [c.requirement for c in analysis.partial],
                analysis.match_percent,
            ),
            system=GAP_ADVICE_SYSTEM,
            task="gap_advice",
            temperature=0.3,
            max_tokens=1800,
        )
    except Exception as exc:
        log.warning("Gap advice generation failed: %s", exc)
        return {
            "available": False,
            "detail": "The learning plan could not be generated because the language model was "
                      "unavailable. The computed gap analysis above is unaffected.",
        }

    # Only keep priority gaps that are genuinely in the missing list -- the
    # model must not invent a gap, nor "advise" on a skill the CV already has.
    valid_missing = {c.requirement.lower() for c in analysis.missing}
    priority: list[dict[str, Any]] = []
    for item in json_guard.as_dict_list(payload.get("priority_gaps"), limit=10):
        skill = json_guard.as_text(item.get("skill"), max_len=80)
        if skill.lower() not in valid_missing:
            continue
        priority.append(
            {
                "skill": skill,
                "why_it_matters": json_guard.as_text(item.get("why_it_matters"), max_len=500),
                "how_to_close": json_guard.as_text(item.get("how_to_close"), max_len=500),
                "estimated_effort": json_guard.as_text(item.get("estimated_effort"), max_len=80),
            }
        )

    valid_matched = {c.requirement.lower() for c in analysis.matched}
    return {
        "available": True,
        "headline": json_guard.as_text(payload.get("headline"), max_len=400),
        "priority_gaps": priority,
        "quick_wins": [
            s for s in json_guard.as_str_list(payload.get("quick_wins"), limit=8, max_len=80)
            if s.lower() in valid_missing
        ],
        "strengths_to_lead_with": [
            s for s in json_guard.as_str_list(payload.get("strengths_to_lead_with"), limit=10, max_len=80)
            if s.lower() in valid_matched
        ],
        "learning_sequence": json_guard.as_str_list(payload.get("learning_sequence"), limit=8, max_len=220),
        "caveat": json_guard.as_text(
            payload.get("caveat"),
            default="This is automated guidance generated from a keyword comparison, not an "
                    "assessment of your suitability for any job.",
            max_len=400,
        ),
        "filtered_out": max(0, len(json_guard.as_dict_list(payload.get("priority_gaps"), limit=10)) - len(priority)),
    }


@router.get("/gap")
def list_gaps(limit: int = 25) -> dict[str, Any]:
    rows = query_all(
        "SELECT g.id, g.cv_id, g.role_analysis_id, g.match_percent, g.created_at, "
        "c.filename, r.role_title FROM gap_analyses g "
        "LEFT JOIN cv_documents c ON c.id = g.cv_id "
        "LEFT JOIN role_analyses r ON r.id = g.role_analysis_id "
        "ORDER BY g.created_at DESC LIMIT ?",
        (max(1, min(limit, 100)),),
    )
    return {
        "items": [
            {
                "gap_analysis_id": r["id"],
                "cv_id": r["cv_id"],
                "cv_filename": r["filename"],
                "role_analysis_id": r["role_analysis_id"],
                "role_title": r["role_title"],
                "match_percent": round(float(r["match_percent"] or 0), 1),
                "created_at": r["created_at"],
            }
            for r in rows
        ],
        "count": len(rows),
    }


@router.get("/gap/{gap_analysis_id}")
def get_gap(gap_analysis_id: str) -> dict[str, Any]:
    row = query_one(
        "SELECT g.*, c.filename, r.role_title FROM gap_analyses g "
        "LEFT JOIN cv_documents c ON c.id = g.cv_id "
        "LEFT JOIN role_analyses r ON r.id = g.role_analysis_id WHERE g.id = ?",
        (gap_analysis_id,),
    )
    if row is None:
        raise NotFoundError("That gap analysis could not be found.")
    return {
        "gap_analysis_id": row["id"],
        "cv_id": row["cv_id"],
        "cv_filename": row["filename"],
        "role_analysis_id": row["role_analysis_id"],
        "role_title": row["role_title"],
        "result": loads(row["result_json"], {}) or {},
        "created_at": row["created_at"],
    }


# ===========================================================================
# Module 4 - CV improvement
# ===========================================================================


@router.post("/improve/bullets")
def improve_bullets(request: ImproveBulletsRequest) -> dict[str, Any]:
    """
    Rewrite CV bullet points.

    Every rewrite is verified against the original for invented metrics,
    invented technologies and escalated scope; failures are returned rejected
    with the reason rather than shown as an improvement.
    """
    cv_skills: list[str] = []
    cv_text = ""
    if request.cv_id:
        row = query_one("SELECT profile_json, raw_text FROM cv_documents WHERE id = ?", (request.cv_id,))
        if row is not None:
            profile = loads(row["profile_json"], {}) or {}
            cv_skills = [s.get("canonical", "") for s in (profile.get("skills") or []) if s.get("canonical")]
            cv_text = row["raw_text"] or ""

    results, usage, summary = improve_service.improve_bullets(
        request.bullets,
        role_title=request.role_title,
        cv_id=request.cv_id,
        cv_skills=cv_skills,
        cv_text=cv_text,
    )

    log_activity(
        "cv_improve",
        f"Improved {summary['accepted']} of {summary['requested']} bullet points",
        f"{summary['rejected']} rejected by the invention guard",
        request.cv_id,
    )

    return {
        "results": [r.to_dict() for r in results],
        "summary": summary,
        "llm_usage": usage.to_dict() if usage else None,
    }


@router.post("/improve/bullets/{improvement_id}/decision")
def set_decision(improvement_id: str, request: BulletDecisionRequest) -> dict[str, Any]:
    return improve_service.set_decision(improvement_id, request.decision)


@router.get("/improve/history")
def improvement_history(cv_id: str = "", limit: int = 100) -> dict[str, Any]:
    items = improve_service.history(cv_id, max(1, min(limit, 300)))
    return {"items": items, "count": len(items)}


@router.post("/improve/rank")
def rank(request: ImproveBulletsRequest) -> dict[str, Any]:
    """Score bullets for weakness without calling an LLM (instant, free)."""
    return {"ranking": improve_service.rank_bullets(request.bullets)}
