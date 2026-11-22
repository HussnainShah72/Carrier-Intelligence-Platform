"""
Module 4 - CV bullet improvement, with invention made impossible to hide.

The requirement is "rewrites weak bullet points without inventing experience".
Prompt instructions alone are not enough for that -- a model under pressure to
sound impressive will add "resulting in a 30% improvement" to a bullet that
never mentioned a number.  So every rewrite is mechanically verified after the
fact and before the user sees it:

  1. NUMBERS      every numeric token in the rewrite must also appear in the
                  original.  A new number is a hard failure -> the rewrite is
                  rejected and the original is kept.
  2. TECHNOLOGIES every canonical skill named in the rewrite must appear in the
                  original bullet, or elsewhere in the candidate's own CV.
                  A new technology is a hard failure.
  3. SCOPE        verbs that escalate seniority ("led", "owned", "managed",
                  "architected") may only appear if the original already
                  implied that scope.  An escalation is a hard failure.
  4. CONTENT      unexplained new content words are reported as a soft warning
                  (paraphrasing legitimately introduces synonyms), shown to the
                  user rather than silently accepted.

A rejected rewrite is not hidden: the row comes back with `accepted: false`, the
reason, and the original text, so the user sees that the system caught it.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from app.core.db import dumps, execute, loads, new_id, query_all, query_one, utcnow
from app.core.errors import NotFoundError, ValidationError
from app.core.logging_setup import get_logger
from app.services.llm import json_guard
from app.services.llm.client import LLMUsage, get_llm
from app.services.llm.prompts import BULLET_IMPROVE_SYSTEM, bullet_improve_prompt
from app.services.skills.matcher import skills_in_text

log = get_logger(__name__)

MAX_BULLETS_PER_REQUEST = 12

# Verbs that claim leadership/ownership the original may not support.
_ESCALATION_VERBS = {
    "led", "leading", "managed", "managing", "owned", "owning", "directed", "headed",
    "architected", "spearheaded", "oversaw", "overseeing", "supervised", "mentored",
    "founded", "established", "pioneered", "drove", "championed", "orchestrated",
}
# Evidence in the original that such scope is legitimate.
_SCOPE_EVIDENCE = {
    "led", "lead", "leader", "leadership", "managed", "manager", "management", "owned",
    "owner", "ownership", "head", "senior", "principal", "supervisor", "supervised",
    "mentor", "mentored", "mentoring", "coordinator", "coordinated", "in charge",
    "responsible", "directed", "director", "architect", "architected", "founded",
    "founder", "team of", "oversaw", "chaired", "captain", "president",
}

_WEAK_OPENERS = re.compile(
    r"^\s*(?:responsible for|worked on|worked with|helped|assisted|involved in|participated in|"
    r"duties included|tasks included|was tasked with|did |made |handled |dealt with|took part)",
    re.I,
)

REASON_OK = ""
REASON_NUMBERS = "invented_metric"
REASON_TECH = "invented_technology"
REASON_SCOPE = "escalated_scope"
REASON_EMPTY = "empty_rewrite"
REASON_TOO_LONG = "rewrite_too_long"


@dataclass
class BulletImprovement:
    id: str
    original: str
    improved: str
    explanation: str = ""
    changes: list[str] = field(default_factory=list)
    flags: list[dict[str, Any]] = field(default_factory=list)
    accepted: bool = True
    rejection_reason: str = ""
    already_strong: bool = False
    metrics_preserved: list[str] = field(default_factory=list)
    weakness_signals: list[str] = field(default_factory=list)
    decision: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "original": self.original,
            "improved": self.improved,
            "explanation": self.explanation,
            "changes": self.changes,
            "flags": self.flags,
            "accepted": self.accepted,
            "rejection_reason": self.rejection_reason,
            "already_strong": self.already_strong,
            "metrics_preserved": self.metrics_preserved,
            "weakness_signals": self.weakness_signals,
            "decision": self.decision,
            "word_count_before": len(self.original.split()),
            "word_count_after": len(self.improved.split()),
        }


# ===========================================================================
# Public entry point
# ===========================================================================


def improve_bullets(
    bullets: Sequence[str],
    *,
    role_title: str = "",
    cv_id: str = "",
    cv_skills: Sequence[str] = (),
    cv_text: str = "",
    persist: bool = True,
) -> tuple[list[BulletImprovement], LLMUsage | None, dict[str, Any]]:
    """Rewrite bullets, verify each rewrite, and persist the accepted ones."""
    cleaned = [b.strip() for b in bullets if b and b.strip()]
    if not cleaned:
        raise ValidationError("No bullet points were provided to improve.")
    if len(cleaned) > MAX_BULLETS_PER_REQUEST:
        raise ValidationError(
            f"Please improve at most {MAX_BULLETS_PER_REQUEST} bullet points at a time "
            f"(you sent {len(cleaned)})."
        )
    for bullet in cleaned:
        if len(bullet) > 600:
            raise ValidationError("One of those bullet points is too long (maximum 600 characters).")

    started = time.perf_counter()
    client = get_llm()
    allowed_skills = list(cv_skills) or skills_in_text(cv_text, limit=40)

    try:
        payload, usage = client.complete_json(
            bullet_improve_prompt(cleaned, role_title, allowed_skills),
            system=BULLET_IMPROVE_SYSTEM,
            task="bullet_improve",
            temperature=0.25,
            max_tokens=2200,
        )
    except Exception as exc:
        log.error("Bullet improvement failed: %s", exc)
        raise

    by_index: dict[int, dict[str, Any]] = {}
    for item in json_guard.as_dict_list(payload.get("results"), limit=MAX_BULLETS_PER_REQUEST * 2):
        index = int(json_guard.as_float(item.get("index"), default=-1.0))
        if 0 <= index < len(cleaned) and index not in by_index:
            by_index[index] = item

    results: list[BulletImprovement] = []
    for index, original in enumerate(cleaned):
        item = by_index.get(index, {})
        results.append(
            _verify_one(
                original=original,
                item=item,
                cv_skills=allowed_skills,
                cv_text=cv_text,
                role_title=role_title,
            )
        )

    if persist:
        for improvement in results:
            _persist(improvement, cv_id=cv_id, role_title=role_title)

    summary = {
        "requested": len(cleaned),
        "returned_by_model": len(by_index),
        "accepted": sum(1 for r in results if r.accepted),
        "rejected": sum(1 for r in results if not r.accepted),
        "already_strong": sum(1 for r in results if r.already_strong),
        "with_warnings": sum(1 for r in results if r.flags and r.accepted),
        "rejections_by_reason": _count_reasons(results),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "engine": f"{usage.provider}/{usage.model}" if usage else "unknown",
        "degraded": bool(usage.degraded) if usage else True,
        "guard_note": (
            "Every rewrite is checked automatically for invented metrics, invented technologies "
            "and escalated scope. Rewrites that fail are rejected and the original is kept."
        ),
    }
    log.info("Bullet improvement: %d requested, %d accepted, %d rejected (%s)",
             summary["requested"], summary["accepted"], summary["rejected"], summary["rejections_by_reason"])
    return results, usage, summary


def _count_reasons(results: Sequence[BulletImprovement]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        if not result.accepted and result.rejection_reason:
            counts[result.rejection_reason] = counts.get(result.rejection_reason, 0) + 1
    return counts


# ===========================================================================
# Verification
# ===========================================================================


def _verify_one(
    *,
    original: str,
    item: dict[str, Any],
    cv_skills: Sequence[str],
    cv_text: str,
    role_title: str,
) -> BulletImprovement:
    improvement = BulletImprovement(
        id=new_id("imp"),
        original=original,
        improved=original,
        weakness_signals=detect_weakness(original),
    )

    improved = json_guard.as_text(item.get("improved"), max_len=600).strip().strip('"')
    improvement.explanation = json_guard.as_text(item.get("explanation"), max_len=600)
    improvement.changes = json_guard.as_str_list(item.get("changes"), limit=6, max_len=60)
    improvement.metrics_preserved = json_guard.as_str_list(item.get("metrics_preserved"), limit=6, max_len=40)
    improvement.already_strong = bool(item.get("already_strong"))

    if not improved:
        improvement.accepted = False
        improvement.rejection_reason = REASON_EMPTY
        improvement.explanation = "The model returned no rewrite for this bullet, so the original is unchanged."
        return improvement

    if len(improved.split()) > 60:
        improvement.accepted = False
        improvement.rejection_reason = REASON_TOO_LONG
        improvement.explanation = (
            "The rewrite was far longer than a CV bullet should be, so it was rejected and the "
            "original kept."
        )
        return improvement

    # ---- check 1: invented numbers ---------------------------------------
    new_numbers = json_guard.unsupported_numbers(improved, [original])
    if new_numbers:
        improvement.accepted = False
        improvement.rejection_reason = REASON_NUMBERS
        improvement.flags.append(
            {
                "type": REASON_NUMBERS,
                "severity": "blocking",
                "detail": f"The rewrite introduced {', '.join(new_numbers[:4])}, which is not in your "
                          "original bullet. Invented metrics are rejected automatically.",
            }
        )
        improvement.explanation = (
            "Rejected: the rewrite invented a metric that your original bullet does not contain. "
            "Your original text has been kept."
        )
        return improvement

    # ---- check 2: invented technologies ----------------------------------
    original_skills = {s.lower() for s in skills_in_text(original, limit=25)}
    cv_skill_set = {s.lower() for s in cv_skills}
    cv_text_low = (cv_text or "").lower()

    invented: list[str] = []
    for skill in skills_in_text(improved, limit=25):
        low = skill.lower()
        if low in original_skills or low in cv_skill_set:
            continue
        if low in cv_text_low:
            continue
        invented.append(skill)

    if invented:
        improvement.accepted = False
        improvement.rejection_reason = REASON_TECH
        improvement.flags.append(
            {
                "type": REASON_TECH,
                "severity": "blocking",
                "detail": f"The rewrite introduced {', '.join(invented[:4])}, which appears nowhere "
                          "in your original bullet or your CV.",
            }
        )
        improvement.explanation = (
            "Rejected: the rewrite added a technology that is not in your CV. Your original text "
            "has been kept."
        )
        return improvement

    # ---- check 3: escalated scope ----------------------------------------
    escalation = _escalated_scope(original, improved)
    if escalation:
        improvement.accepted = False
        improvement.rejection_reason = REASON_SCOPE
        improvement.flags.append(
            {
                "type": REASON_SCOPE,
                "severity": "blocking",
                "detail": f"The rewrite claims '{escalation}', which implies more seniority or "
                          "ownership than your original bullet states.",
            }
        )
        improvement.explanation = (
            f"Rejected: the rewrite upgraded your role to '{escalation}', which your original "
            "bullet does not support. Your original text has been kept."
        )
        return improvement

    # ---- check 4: unexplained new content (soft) -------------------------
    sources = [original]
    if cv_text:
        sources.append(cv_text)
    novel = json_guard.unsupported_terms(improved, sources, allowlist=list(cv_skills) + [role_title])
    if len(novel) >= 3:
        improvement.flags.append(
            {
                "type": "new_wording",
                "severity": "warning",
                "detail": "The rewrite introduces wording not in your original: "
                          f"{', '.join(novel[:6])}. Check that each word is still accurate for you.",
            }
        )

    improvement.improved = improved
    improvement.accepted = True
    if not improvement.explanation:
        improvement.explanation = "Rewritten for a stronger opening verb and tighter phrasing."
    if not improvement.changes:
        improvement.changes = _infer_changes(original, improved)
    return improvement


# Verbs that claim authority over PEOPLE. "Responsible for the API" supports
# "owned the API" but not "led the API team" -- found in QA when a real model
# rewrote "Responsible for the shipment tracking API" as "Led the ...".
_PEOPLE_LEADERSHIP_VERBS = {
    "led", "leading", "managed", "managing", "directed", "headed", "supervised",
    "oversaw", "overseeing", "mentored", "spearheaded", "championed", "orchestrated",
}
_PEOPLE_LEADERSHIP_EVIDENCE = {
    "led", "lead", "leader", "leadership", "managed", "manager", "management",
    "head", "supervisor", "supervised", "mentor", "mentored", "mentoring",
    "directed", "director", "oversaw", "chaired", "captain", "president",
    "coordinated", "coordinator", "in charge", "team of",
}


def _has_word(phrase: str, text_low: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", text_low) is not None


def _escalated_scope(original: str, improved: str) -> str:
    """Return the escalating verb used without support, or '' if none."""
    original_low = original.lower()
    improved_words = re.findall(r"[a-z]+", improved.lower())
    original_words = set(re.findall(r"[a-z]+", original_low))

    people_ok = any(_has_word(e, original_low) for e in _PEOPLE_LEADERSHIP_EVIDENCE)
    scope_ok = people_ok or any(_has_word(e, original_low) for e in _SCOPE_EVIDENCE)

    for word in improved_words:
        if word in original_words:
            continue  # the candidate used this verb themselves
        if word in _PEOPLE_LEADERSHIP_VERBS and not people_ok:
            return word
        if word in _ESCALATION_VERBS and not scope_ok:
            return word
    return ""


def _infer_changes(original: str, improved: str) -> list[str]:
    changes: list[str] = []
    if _WEAK_OPENERS.match(original) and not _WEAK_OPENERS.match(improved):
        changes.append("removed filler opening")
    if original.split()[:1] != improved.split()[:1]:
        changes.append("stronger action verb")
    if len(improved.split()) < len(original.split()):
        changes.append("tightened")
    elif len(improved.split()) > len(original.split()):
        changes.append("added specificity")
    return changes or ["rephrased"]


def detect_weakness(bullet: str) -> list[str]:
    """
    Why this bullet is worth rewriting -- shown as badges in the Studio.

    Deterministic, so the UI can rank bullets by weakness before any LLM call.
    """
    signals: list[str] = []
    text = (bullet or "").strip()
    if not text:
        return signals

    words = text.split()
    if _WEAK_OPENERS.match(text):
        signals.append("weak opening ('responsible for', 'worked on')")
    if len(words) < 8:
        signals.append("very short")
    if len(words) > 38:
        signals.append("too long for one bullet")
    if not re.search(r"\d", text):
        signals.append("no measurable detail")
    if re.search(r"\b(?:various|several|multiple|many|different|some|stuff|things)\b", text, re.I):
        signals.append("vague quantifiers")
    if re.search(r"\b(?:utilis|utiliz|leverag|synerg|facilitat)", text, re.I):
        signals.append("corporate filler words")
    if not skills_in_text(text, limit=3):
        signals.append("no concrete technology named")
    if re.match(r"^\s*(?:i|we|my team)\b", text, re.I):
        signals.append("starts with a pronoun, not a verb")
    first = words[0].lower().strip(".,") if words else ""
    if first.endswith("ing"):
        signals.append("present participle instead of past tense")
    return signals


def rank_bullets(bullets: Sequence[str]) -> list[dict[str, Any]]:
    """Bullets ordered worst-first, so the user improves what matters."""
    rows: list[dict[str, Any]] = []
    for index, bullet in enumerate(bullets):
        signals = detect_weakness(bullet)
        rows.append(
            {
                "index": index,
                "text": bullet,
                "weakness_signals": signals,
                "weakness_score": len(signals),
                "word_count": len(bullet.split()),
            }
        )
    rows.sort(key=lambda r: (-r["weakness_score"], r["index"]))
    return rows


# ===========================================================================
# Persistence
# ===========================================================================


def _persist(improvement: BulletImprovement, *, cv_id: str, role_title: str) -> None:
    execute(
        "INSERT INTO bullet_improvements(id, cv_id, role_title, original, improved, explanation, "
        "changes_json, flags_json, decision, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            improvement.id, cv_id, role_title, improvement.original, improvement.improved,
            improvement.explanation, dumps(improvement.changes), dumps(improvement.flags),
            improvement.decision, utcnow(),
        ),
    )


def set_decision(improvement_id: str, decision: str) -> dict[str, Any]:
    if decision not in ("accepted", "rejected", "pending"):
        raise ValidationError("Decision must be one of: accepted, rejected, pending.")

    row = query_one("SELECT * FROM bullet_improvements WHERE id = ?", (improvement_id,))
    if row is None:
        raise NotFoundError("That improvement could not be found.")

    execute("UPDATE bullet_improvements SET decision=? WHERE id=?", (decision, improvement_id))
    return {"id": improvement_id, "decision": decision}


def history(cv_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
    if cv_id:
        rows = query_all(
            "SELECT * FROM bullet_improvements WHERE cv_id = ? ORDER BY created_at DESC LIMIT ?",
            (cv_id, limit),
        )
    else:
        rows = query_all("SELECT * FROM bullet_improvements ORDER BY created_at DESC LIMIT ?", (limit,))

    return [
        {
            "id": r["id"],
            "cv_id": r["cv_id"],
            "role_title": r["role_title"],
            "original": r["original"],
            "improved": r["improved"],
            "explanation": r["explanation"],
            "changes": loads(r["changes_json"], []) or [],
            "flags": loads(r["flags_json"], []) or [],
            "decision": r["decision"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
