"""
Module 3 - match and gap analysis.

Compares the candidate's normalised CV skills with the combined role
requirements and classifies every requirement into one of three buckets.

Classification rules (in order)
-------------------------------
MATCHED     the canonical names are identical -- the CV names this exact skill.

PARTIAL     one of:
              (a) a CV skill *implies* the requirement via the taxonomy
                  (holding "React" partially evidences "JavaScript");
              (b) the requirement implies a skill the CV has, i.e. the
                  foundation is present but the specific technology is not
                  (CV has "JavaScript", role wants "React");
              (c) the two names are near-duplicates by fuzzy/vector similarity
                  but did not merge during normalisation.
            Partial credit is 0.5, and the UI always says *why* it is partial.

MISSING     no evidence at all.

Weighted match score
--------------------
    score = sum(importance_i * credit_i) / sum(importance_i) * 100

Weighting by importance (not a raw count) is the honest choice: missing one
core requirement should hurt more than missing three "nice to have" tools.
The number is presented as "requirement coverage", never as a probability of
being hired -- see `readiness_label()`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from app.core.logging_setup import get_logger
from app.services.skills import taxonomy as tx
from app.services.skills.normalizer import FUZZY_ACCEPT, resolve_skill
from app.services.skills.text_norm import normalise_key

log = get_logger(__name__)

MATCHED = "matched"
PARTIAL = "partial"
MISSING = "missing"

CREDIT = {MATCHED: 1.0, PARTIAL: 0.5, MISSING: 0.0}

# A near-duplicate that normalisation did not merge still deserves part credit.
PARTIAL_FUZZY_THRESHOLD = 78.0

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

SEVERITY_ORDER = {SEVERITY_CRITICAL: 0, SEVERITY_HIGH: 1, SEVERITY_MEDIUM: 2, SEVERITY_LOW: 3}


@dataclass
class SkillComparison:
    """One requirement, and what the CV offers against it."""

    requirement: str
    category: str
    status: str
    importance: float
    provenance: str
    posting_count: int
    essential: bool
    credit: float = 0.0
    severity: str = SEVERITY_LOW
    evidence: str = ""
    matched_via: str = ""
    cv_skill: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement": self.requirement,
            "category": self.category,
            "status": self.status,
            "importance": round(self.importance, 3),
            "provenance": self.provenance,
            "posting_count": self.posting_count,
            "essential": self.essential,
            "credit": self.credit,
            "severity": self.severity,
            "evidence": self.evidence,
            "matched_via": self.matched_via,
            "cv_skill": self.cv_skill,
            "confidence": round(self.confidence, 3),
        }


@dataclass
class GapAnalysis:
    role_title: str
    match_percent: float = 0.0
    unweighted_percent: float = 0.0
    comparisons: list[SkillComparison] = field(default_factory=list)
    extra_skills: list[dict[str, Any]] = field(default_factory=list)
    category_breakdown: list[dict[str, Any]] = field(default_factory=list)
    essential_coverage: dict[str, Any] = field(default_factory=dict)
    advice: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    # --------------------------------------------------------------- buckets
    def by_status(self, status: str) -> list[SkillComparison]:
        return [c for c in self.comparisons if c.status == status]

    @property
    def matched(self) -> list[SkillComparison]:
        return self.by_status(MATCHED)

    @property
    def partial(self) -> list[SkillComparison]:
        return self.by_status(PARTIAL)

    @property
    def missing(self) -> list[SkillComparison]:
        return self.by_status(MISSING)

    def priority_gaps(self, limit: int = 10) -> list[SkillComparison]:
        gaps = [c for c in self.comparisons if c.status in (MISSING, PARTIAL)]
        gaps.sort(key=lambda c: (SEVERITY_ORDER[c.severity], -c.importance, c.requirement.lower()))
        return gaps[:limit]

    def to_dict(self) -> dict[str, Any]:
        return {
            "role_title": self.role_title,
            "match_percent": round(self.match_percent, 1),
            "unweighted_percent": round(self.unweighted_percent, 1),
            "readiness_label": readiness_label(self.match_percent),
            "comparisons": [c.to_dict() for c in self.comparisons],
            "matched": [c.to_dict() for c in self.matched],
            "partial": [c.to_dict() for c in self.partial],
            "missing": [c.to_dict() for c in self.missing],
            "priority_gaps": [c.to_dict() for c in self.priority_gaps(12)],
            "extra_skills": self.extra_skills,
            "category_breakdown": self.category_breakdown,
            "essential_coverage": self.essential_coverage,
            "advice": self.advice,
            "warnings": self.warnings,
            "stats": {
                "requirements_total": len(self.comparisons),
                "matched": len(self.matched),
                "partial": len(self.partial),
                "missing": len(self.missing),
                "extra_skills": len(self.extra_skills),
            },
            "disclaimer": (
                "This score measures how much of the collected requirement list your CV "
                "names. It is not a prediction of whether you will be shortlisted or "
                "hired, and it cannot see the quality of your experience."
            ),
        }


def readiness_label(percent: float) -> str:
    """Deliberately descriptive, never a verdict on the candidate."""
    if percent >= 85:
        return "Covers nearly all collected requirements"
    if percent >= 70:
        return "Covers most collected requirements"
    if percent >= 50:
        return "Covers about half of the collected requirements"
    if percent >= 30:
        return "Covers some collected requirements"
    return "Covers few of the collected requirements"


# ===========================================================================
# Core comparison
# ===========================================================================


def analyse_gap(
    cv_skills: Sequence[dict[str, Any] | str],
    requirements: Sequence[Any],
    *,
    role_title: str = "",
) -> GapAnalysis:
    """
    Compare CV skills against requirement skills.

    `cv_skills`      dicts from CVProfile.skills, or plain canonical strings
    `requirements`   CombinedSkill objects (or dicts with the same fields)
    """
    analysis = GapAnalysis(role_title=role_title)

    cv_canonical = _canonical_names(cv_skills)
    cv_index = {normalise_key(name): name for name in cv_canonical}
    cv_implications = _implication_map(cv_canonical)

    if not cv_canonical:
        analysis.warnings.append(
            "No skills were extracted from the CV, so every requirement is reported as missing. "
            "Add a clearly headed skills section to the CV and re-upload it."
        )
    if not requirements:
        analysis.warnings.append("No role requirements were available to compare against.")
        return analysis

    for requirement in requirements:
        comparison = _compare_one(requirement, cv_canonical, cv_index, cv_implications)
        analysis.comparisons.append(comparison)

    # ---- scores ----------------------------------------------------------
    total_weight = sum(c.importance for c in analysis.comparisons)
    if total_weight > 0:
        analysis.match_percent = (
            sum(c.importance * c.credit for c in analysis.comparisons) / total_weight * 100
        )
    analysis.unweighted_percent = (
        sum(c.credit for c in analysis.comparisons) / len(analysis.comparisons) * 100
        if analysis.comparisons
        else 0.0
    )

    # ---- severity --------------------------------------------------------
    importances = sorted((c.importance for c in analysis.comparisons), reverse=True)
    high_cut = importances[max(0, len(importances) // 3 - 1)] if importances else 0.0
    for comparison in analysis.comparisons:
        comparison.severity = _severity(comparison, high_cut)

    # ---- extras, categories, essentials ----------------------------------
    analysis.extra_skills = _extra_skills(cv_skills, analysis.comparisons)
    analysis.category_breakdown = _category_breakdown(analysis.comparisons)
    analysis.essential_coverage = _essential_coverage(analysis.comparisons)

    log.info(
        "Gap analysis for %r: %.1f%% weighted (%d matched / %d partial / %d missing)",
        role_title, analysis.match_percent, len(analysis.matched), len(analysis.partial), len(analysis.missing),
    )
    return analysis


def _canonical_names(skills: Sequence[dict[str, Any] | str]) -> list[str]:
    out: list[str] = []
    for skill in skills:
        name = skill.get("canonical", "") if isinstance(skill, dict) else str(skill)
        name = (name or "").strip()
        if name and name not in out:
            out.append(name)
    return out


def _implication_map(cv_canonical: Sequence[str]) -> dict[str, str]:
    """normalised implied-skill key -> the CV skill that implies it."""
    out: dict[str, str] = {}
    for name in cv_canonical:
        for implied in tx.implied_by(name):
            key = normalise_key(implied)
            if key and key not in out:
                out[key] = name
    return out


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _compare_one(
    requirement: Any,
    cv_canonical: Sequence[str],
    cv_index: dict[str, str],
    cv_implications: dict[str, str],
) -> SkillComparison:
    name = str(_field(requirement, "canonical", "") or "")
    comparison = SkillComparison(
        requirement=name,
        category=str(_field(requirement, "category", tx.CATEGORY_OTHER)),
        status=MISSING,
        importance=float(_field(requirement, "importance", 0.5) or 0.5),
        provenance=str(_field(requirement, "provenance", "llm")),
        posting_count=int(_field(requirement, "posting_count", 0) or 0),
        essential=bool(_field(requirement, "essential", False)),
    )

    key = normalise_key(name)

    # ---- 1. exact canonical match ---------------------------------------
    if key in cv_index:
        comparison.status = MATCHED
        comparison.cv_skill = cv_index[key]
        comparison.matched_via = "exact canonical match"
        comparison.confidence = 1.0
        comparison.evidence = f"Your CV lists '{cv_index[key]}'."
        comparison.credit = CREDIT[MATCHED]
        return comparison

    # ---- 2a. a CV skill implies this requirement -------------------------
    if key in cv_implications:
        holder = cv_implications[key]
        comparison.status = PARTIAL
        comparison.cv_skill = holder
        comparison.matched_via = "implied by a related skill on your CV"
        comparison.confidence = 0.7
        comparison.evidence = (
            f"Your CV does not name '{name}', but it lists '{holder}', which normally "
            f"demonstrates it. Name '{name}' explicitly if you have used it."
        )
        comparison.credit = CREDIT[PARTIAL]
        return comparison

    # ---- 2b. requirement builds on something the CV has ------------------
    for foundation in tx.implied_by(name):
        foundation_key = normalise_key(foundation)
        if foundation_key in cv_index:
            comparison.status = PARTIAL
            comparison.cv_skill = cv_index[foundation_key]
            comparison.matched_via = "foundation present, specific technology missing"
            comparison.confidence = 0.55
            comparison.evidence = (
                f"You have '{cv_index[foundation_key]}', which '{name}' builds on, "
                f"so the step up should be quick - but '{name}' itself is not on your CV."
            )
            comparison.credit = CREDIT[PARTIAL]
            return comparison

    # ---- 2c. near-duplicate names ---------------------------------------
    similar, score = _closest_cv_skill(name, cv_canonical)
    if similar and score >= PARTIAL_FUZZY_THRESHOLD:
        comparison.status = PARTIAL if score < FUZZY_ACCEPT else MATCHED
        comparison.cv_skill = similar
        comparison.matched_via = f"name similarity {score:.0f}%"
        comparison.confidence = round(score / 100, 2)
        comparison.evidence = (
            f"Your CV lists '{similar}', which is {score:.0f}% similar to '{name}'. "
            "Check that the two are the same thing."
        )
        comparison.credit = CREDIT[comparison.status]
        return comparison

    # ---- 3. missing ------------------------------------------------------
    comparison.evidence = f"'{name}' does not appear anywhere in your CV."
    comparison.credit = CREDIT[MISSING]
    return comparison


def _closest_cv_skill(requirement: str, cv_canonical: Sequence[str]) -> tuple[str, float]:
    try:
        from rapidfuzz import fuzz  # type: ignore
    except ImportError:  # pragma: no cover
        return "", 0.0

    key = normalise_key(requirement)
    best_name, best_score = "", 0.0
    for name in cv_canonical:
        score = float(max(fuzz.token_set_ratio(key, normalise_key(name)), fuzz.WRatio(key, normalise_key(name)) * 0.95))
        if score > best_score:
            best_name, best_score = name, score
    return best_name, best_score


def _severity(comparison: SkillComparison, high_cut: float) -> str:
    """
    How much this gap matters.

    Essential + absent is critical; anything in the top third of the importance
    distribution is high; a partial match is one band gentler than a full miss.
    """
    if comparison.status == MATCHED:
        return SEVERITY_LOW

    if comparison.status == MISSING:
        if comparison.essential:
            return SEVERITY_CRITICAL
        if comparison.importance >= high_cut or comparison.posting_count >= 3:
            return SEVERITY_HIGH
        if comparison.category in (tx.CATEGORY_SOFT,):
            return SEVERITY_LOW
        return SEVERITY_MEDIUM

    # PARTIAL
    if comparison.essential:
        return SEVERITY_HIGH
    if comparison.importance >= high_cut:
        return SEVERITY_MEDIUM
    return SEVERITY_LOW


def _extra_skills(
    cv_skills: Sequence[dict[str, Any] | str], comparisons: Sequence[SkillComparison]
) -> list[dict[str, Any]]:
    """CV skills the role did not ask for -- useful differentiators, not noise."""
    used = {normalise_key(c.cv_skill) for c in comparisons if c.cv_skill}
    used |= {normalise_key(c.requirement) for c in comparisons}

    out: list[dict[str, Any]] = []
    for skill in cv_skills:
        name = skill.get("canonical", "") if isinstance(skill, dict) else str(skill)
        if not name:
            continue
        if normalise_key(name) in used:
            continue
        category = skill.get("category") if isinstance(skill, dict) else None
        out.append({"canonical": name, "category": category or tx.category_of(name)})
    out.sort(key=lambda s: (s["category"], s["canonical"].lower()))
    return out


def _category_breakdown(comparisons: Sequence[SkillComparison]) -> list[dict[str, Any]]:
    """Per-category coverage, which is what the dashboard radar/bar charts plot."""
    buckets: dict[str, dict[str, Any]] = {}
    for comparison in comparisons:
        bucket = buckets.setdefault(
            comparison.category,
            {"category": comparison.category, "matched": 0, "partial": 0, "missing": 0,
             "total": 0, "weight": 0.0, "earned": 0.0},
        )
        bucket["total"] += 1
        bucket[comparison.status] += 1
        bucket["weight"] += comparison.importance
        bucket["earned"] += comparison.importance * comparison.credit

    out: list[dict[str, Any]] = []
    for bucket in buckets.values():
        coverage = (bucket["earned"] / bucket["weight"] * 100) if bucket["weight"] else 0.0
        out.append(
            {
                "category": bucket["category"],
                "matched": bucket["matched"],
                "partial": bucket["partial"],
                "missing": bucket["missing"],
                "total": bucket["total"],
                "coverage_percent": round(coverage, 1),
            }
        )
    out.sort(key=lambda b: (-b["total"], b["category"]))
    return out


def _essential_coverage(comparisons: Sequence[SkillComparison]) -> dict[str, Any]:
    essentials = [c for c in comparisons if c.essential]
    if not essentials:
        return {"total": 0, "matched": 0, "partial": 0, "missing": 0, "coverage_percent": 0.0,
                "missing_names": []}

    matched = sum(1 for c in essentials if c.status == MATCHED)
    partial = sum(1 for c in essentials if c.status == PARTIAL)
    missing = [c.requirement for c in essentials if c.status == MISSING]
    return {
        "total": len(essentials),
        "matched": matched,
        "partial": partial,
        "missing": len(missing),
        "coverage_percent": round((matched + 0.5 * partial) / len(essentials) * 100, 1),
        "missing_names": missing[:12],
    }


# ===========================================================================
# Reverse lookup helper (used by the interview module)
# ===========================================================================


def skills_in_text(text: str, *, limit: int = 20) -> list[str]:
    """
    Canonical skills mentioned in free text (e.g. a spoken interview answer).

    Used to decide which requirement a candidate has actually demonstrated out
    loud, which drives adaptive follow-up questions.
    """
    probe = f" {''.join(ch if (ch.isalnum() or ch in '+#./&') else ' ' for ch in (text or '').lower())} "
    # Intra-word dots are part of a skill's identity ("node.js"), but a
    # sentence-final one is not: without this, "deployed on AWS." never matches
    # the key "aws", because the probe contains " aws. " rather than " aws ".
    probe = re.sub(r"\.(?=\s|$)", " ", probe)
    probe = f" {' '.join(probe.split())} "

    found: list[str] = []
    for canonical, meta in tx.CANONICAL_SKILLS.items():
        for form in [canonical, *meta["aliases"]]:
            # Conservative key (noise words kept) -- see taxonomy._build_alias_index.
            key = normalise_key(form, strip_noise=False)
            if len(key) >= tx.DOCUMENT_SCAN_MIN_KEY_LENGTH and f" {key} " in probe:
                if canonical not in found:
                    found.append(canonical)
                break
        if len(found) >= limit:
            break
    return found


def candidate_skill_set(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Everything from a CV that can satisfy a role requirement.

    The skills list alone is not enough. A role requirement is often a
    qualification -- "CompTIA Security+", "Bachelor's Degree" -- and a candidate
    who holds it records it under certifications or education, not skills. Before
    this, a CV that explicitly listed "CompTIA Security+ - CompTIA - 2022" was
    still told that CompTIA Security+ was missing, which is plainly wrong and
    visibly wrong to the user.

    Project technologies are included for the same reason: "built with FastAPI
    and PostgreSQL" under a project is evidence of those skills.
    """
    from app.services.skills.normalizer import normalise_skills

    entries: list[dict[str, Any]] = list(profile.get("skills") or [])
    known = {str(e.get("canonical", "")).lower() for e in entries}

    extra: list[str] = []
    for certification in profile.get("certifications") or []:
        name = (certification or {}).get("name", "")
        if name:
            extra.append(name)

    for education in profile.get("education") or []:
        degree = (education or {}).get("degree", "")
        if degree:
            extra.append(degree)

    for project in profile.get("projects") or []:
        extra.extend(project.get("technologies") or [])

    for resolved in normalise_skills(extra):
        if resolved.canonical.lower() not in known:
            entries.append(resolved.to_dict())
            known.add(resolved.canonical.lower())

    return entries


def resolve_many(names: Sequence[str]) -> list[str]:
    """Canonicalise a list of raw names, dropping anything unusable."""
    out: list[str] = []
    for name in names:
        resolved = resolve_skill(name)
        if resolved and resolved.canonical not in out:
            out.append(resolved.canonical)
    return out
