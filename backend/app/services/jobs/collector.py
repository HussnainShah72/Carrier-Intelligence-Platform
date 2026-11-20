"""
Module 2 - combining live job postings with LLM-generated role requirements.

The assignment requires BOTH sources and one combined list.  The interesting
engineering question is how to combine them, because they disagree and they
fail differently:

  scraped postings   real, current, evidence-backed -- but noisy, remote/tech
                     skewed, and sometimes zero results for a niche title
  LLM generation     broad, well-structured, works for any title -- but
                     unverifiable and prone to listing an idealised wish list

Fusion rule implemented here
----------------------------
Every skill carries provenance (`scraped`, `llm`, or `both`) and an importance
score built from three signals:

    importance = 0.55 * posting_frequency      (how many adverts asked for it)
              + 0.30 * llm_tier_weight         (core > desirable > tool > soft)
              + 0.15 * agreement_bonus         (both sources independently said it)

A skill confirmed by both sources outranks one asserted by either alone, which
is exactly the behaviour you want: the LLM supplies breadth, the postings supply
evidence, and agreement supplies confidence.  The UI shows the provenance badge
for every skill so no requirement is presented as fact without its source.
"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Sequence

from app.core.logging_setup import get_logger
from app.services.jobs.sources import ALL_SOURCES, JobPosting, SourceReport
from app.services.llm import json_guard
from app.services.llm.client import LLMUsage, get_llm
from app.services.llm.prompts import (
    POSTING_SKILLS_SYSTEM,
    ROLE_SKILLS_SYSTEM,
    posting_skills_prompt,
    role_skills_prompt,
)
from app.services.skills import taxonomy as tx
from app.services.skills.normalizer import NormalisedSkill, normalise_skills, resolve_skill
from app.services.skills.text_norm import normalise_key, split_skill_list

log = get_logger(__name__)

# Importance weights (documented above and in the report).
W_FREQUENCY = 0.55
W_LLM_TIER = 0.30
W_AGREEMENT = 0.15

LLM_TIER_WEIGHTS = {
    "core": 1.0,
    "qualification": 0.75,
    "tool": 0.65,
    "desirable": 0.55,
    "soft": 0.5,
}

# --- noise control -----------------------------------------------------------
# Scanning 24 adverts for every skill in the taxonomy finds a long tail of
# things mentioned in passing by exactly one posting: a Data Analyst search
# turns up "Deep Learning" because one advert happened to say it. Carrying that
# tail into the requirement list is actively harmful -- it inflates the
# denominator of the gap score, so every candidate looks weak for reasons that
# are not really requirements of the role.
#
# A scraped-only skill therefore needs corroboration: either a second,
# independent advert asked for it, or the LLM independently named it. Skills the
# LLM named are always kept, because that is the other half of the required
# two-source design. Dropped skills are counted and reported, never hidden.
MIN_POSTING_SUPPORT = 2
MAX_REQUIREMENTS = 70

PROV_SCRAPED = "scraped"
PROV_LLM = "llm"
PROV_BOTH = "both"


@dataclass
class CombinedSkill:
    canonical: str
    category: str
    provenance: str
    importance: float = 0.0
    posting_count: int = 0
    posting_frequency: float = 0.0
    llm_tiers: list[str] = field(default_factory=list)
    surface_forms: list[str] = field(default_factory=list)
    example_sources: list[str] = field(default_factory=list)
    normalisation_stage: str = ""
    essential: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical": self.canonical,
            "category": self.category,
            "provenance": self.provenance,
            "importance": round(self.importance, 3),
            "posting_count": self.posting_count,
            "posting_frequency": round(self.posting_frequency, 3),
            "llm_tiers": self.llm_tiers,
            "surface_forms": self.surface_forms[:8],
            "example_sources": self.example_sources[:5],
            "normalisation_stage": self.normalisation_stage,
            "essential": self.essential,
        }


@dataclass
class RoleRequirements:
    """The combined requirement profile for one role."""

    role_title: str
    normalised_title: str = ""
    title_assessment: str = ""
    seniority: str = "unspecified"
    role_summary: str = ""
    responsibilities: list[str] = field(default_factory=list)
    interview_focus_areas: list[str] = field(default_factory=list)
    combined_skills: list[CombinedSkill] = field(default_factory=list)
    postings: list[JobPosting] = field(default_factory=list)
    source_reports: list[SourceReport] = field(default_factory=list)
    llm_raw: dict[str, Any] = field(default_factory=dict)
    merge_evidence: list[dict[str, Any]] = field(default_factory=list)
    filtering: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    llm_available: bool = True
    llm_degraded: bool = False

    # ------------------------------------------------------------- accessors
    @property
    def skill_names(self) -> list[str]:
        return [s.canonical for s in self.combined_skills]

    def essential_skills(self) -> list[CombinedSkill]:
        return [s for s in self.combined_skills if s.essential]

    def to_dict(self) -> dict[str, Any]:
        scraped = sum(1 for s in self.combined_skills if s.provenance == PROV_SCRAPED)
        llm_only = sum(1 for s in self.combined_skills if s.provenance == PROV_LLM)
        both = sum(1 for s in self.combined_skills if s.provenance == PROV_BOTH)
        return {
            "role_title": self.role_title,
            "normalised_title": self.normalised_title,
            "title_assessment": self.title_assessment,
            "seniority": self.seniority,
            "role_summary": self.role_summary,
            "responsibilities": self.responsibilities,
            "interview_focus_areas": self.interview_focus_areas,
            "combined_skills": [s.to_dict() for s in self.combined_skills],
            "postings": [p.to_dict() for p in self.postings],
            "source_reports": [r.to_dict() for r in self.source_reports],
            "merge_evidence": self.merge_evidence,
            "filtering": self.filtering,
            "warnings": self.warnings,
            "timings": {k: round(v, 1) for k, v in self.timings.items()},
            "llm_available": self.llm_available,
            "llm_degraded": self.llm_degraded,
            "stats": {
                "total_skills": len(self.combined_skills),
                "from_scraping_only": scraped,
                "from_llm_only": llm_only,
                "confirmed_by_both": both,
                "essential_skills": sum(1 for s in self.combined_skills if s.essential),
                "postings_collected": len(self.postings),
                "sources_attempted": len(self.source_reports),
                "sources_succeeded": sum(1 for r in self.source_reports if r.postings_kept > 0),
                "agreement_rate": round(both / len(self.combined_skills), 3) if self.combined_skills else 0.0,
                "dropped_uncorroborated": int(self.filtering.get("dropped_uncorroborated", 0)),
            },
            # Role profile in the shape the interview prompts expect.
            "core_technical_skills": [s.canonical for s in self.combined_skills if s.essential][:16],
            "desirable_technical_skills": [
                s.canonical for s in self.combined_skills
                if not s.essential and s.category not in (tx.CATEGORY_SOFT, tx.CATEGORY_QUALIFICATION)
            ][:12],
            "soft_skills": [s.canonical for s in self.combined_skills if s.category == tx.CATEGORY_SOFT][:10],
            "qualifications": [
                s.canonical for s in self.combined_skills if s.category == tx.CATEGORY_QUALIFICATION
            ][:8],
            "tools_and_platforms": [
                s.canonical for s in self.combined_skills if s.category in (tx.CATEGORY_TOOL, tx.CATEGORY_CLOUD)
            ][:12],
        }


# ===========================================================================
# Public entry point
# ===========================================================================


def analyse_role(
    role_title: str,
    *,
    location: str = "",
    seniority: str = "any",
    use_scraping: bool = True,
    use_llm: bool = True,
    max_postings: int | None = None,
    extract_skills_with_llm: bool = True,
) -> tuple[RoleRequirements, list[LLMUsage]]:
    """Collect live postings, generate role skills with an LLM, and fuse them."""
    requirements = RoleRequirements(role_title=role_title.strip())
    usages: list[LLMUsage] = []
    client = get_llm()
    requirements.llm_degraded = client.is_offline

    # ---------------------------------------------- A: live job postings ----
    postings: list[JobPosting] = []
    if use_scraping:
        started = time.perf_counter()
        postings, reports = collect_postings(role_title, location, max_postings=max_postings)
        requirements.postings = postings
        requirements.source_reports = reports
        requirements.timings["scrape_ms"] = (time.perf_counter() - started) * 1000

        if not postings:
            blocked = [r for r in reports if r.status == "blocked_by_robots"]
            failed = [r for r in reports if r.status not in ("ok", "no_results", "no_relevant_results")]
            detail = "; ".join(f"{r.name}: {r.status}" for r in (blocked + failed)[:4])
            requirements.warnings.append(
                "No live job postings could be collected for this role. "
                + (f"Source outcomes: {detail}. " if detail else "")
                + "The requirement list below therefore rests on the language model alone, "
                "and is not backed by current advert evidence."
            )
    else:
        requirements.warnings.append("Live posting collection was switched off for this analysis.")

    # ------------------------------------- A2: skills out of each posting ---
    if postings:
        started = time.perf_counter()
        posting_usages = extract_posting_skills(
            postings, use_llm=extract_skills_with_llm and use_llm and not client.is_offline
        )
        usages.extend(posting_usages)
        requirements.timings["posting_skill_extraction_ms"] = (time.perf_counter() - started) * 1000

    # ------------------------------------------- B: LLM role generation -----
    llm_payload: dict[str, Any] = {}
    if use_llm:
        started = time.perf_counter()
        try:
            llm_payload, usage = client.complete_json(
                role_skills_prompt(role_title, location=location, seniority=seniority),
                system=ROLE_SKILLS_SYSTEM,
                task="role_skills",
                temperature=0.2,
                max_tokens=1800,
            )
            usages.append(usage)
            requirements.llm_raw = llm_payload
        except Exception as exc:
            log.error("LLM role generation failed for %r: %s", role_title, exc)
            requirements.llm_available = False
            requirements.warnings.append(
                "The language model could not generate role requirements "
                f"({type(exc).__name__}). The list below comes from scraped postings only."
            )
        requirements.timings["llm_role_ms"] = (time.perf_counter() - started) * 1000
    else:
        requirements.llm_available = False
        requirements.warnings.append("LLM role generation was switched off for this analysis.")

    if llm_payload:
        requirements.normalised_title = json_guard.as_text(llm_payload.get("normalised_title"), max_len=120)
        requirements.title_assessment = json_guard.as_text(llm_payload.get("title_assessment"), max_len=400)
        requirements.seniority = json_guard.as_choice(
            llm_payload.get("seniority"),
            ["entry", "junior", "mid", "senior", "lead", "unspecified"],
            default="unspecified",
        )
        requirements.role_summary = json_guard.as_text(llm_payload.get("role_summary"), max_len=900)
        requirements.responsibilities = json_guard.as_str_list(
            llm_payload.get("responsibilities"), limit=10, max_len=220
        )
        requirements.interview_focus_areas = json_guard.as_str_list(
            llm_payload.get("interview_focus_areas"), limit=8, max_len=120
        )

    if not requirements.normalised_title:
        requirements.normalised_title = role_title.strip().title()

    # ------------------------------------------------------- C: fusion ------
    started = time.perf_counter()
    requirements.combined_skills, requirements.merge_evidence, requirements.filtering = fuse_skills(
        postings, llm_payload
    )
    requirements.timings["fusion_ms"] = (time.perf_counter() - started) * 1000

    if not requirements.combined_skills:
        requirements.warnings.append(
            "No skills could be determined for this role from either source. "
            "Check the job title spelling, or try a more conventional title."
        )

    # Fill responsibilities from postings when the LLM gave none.
    if not requirements.responsibilities and postings:
        for posting in postings[:4]:
            for line in posting.description.split("\n"):
                stripped = line.strip(" -•")
                if 40 <= len(stripped) <= 200:
                    requirements.responsibilities.append(stripped)
                if len(requirements.responsibilities) >= 6:
                    break
            if len(requirements.responsibilities) >= 6:
                break

    log.info(
        "Role analysis complete for %r: %d skills (%d both, %d scraped-only, %d llm-only), %d postings",
        role_title,
        len(requirements.combined_skills),
        sum(1 for s in requirements.combined_skills if s.provenance == PROV_BOTH),
        sum(1 for s in requirements.combined_skills if s.provenance == PROV_SCRAPED),
        sum(1 for s in requirements.combined_skills if s.provenance == PROV_LLM),
        len(postings),
    )
    return requirements, usages


# ===========================================================================
# Step A - posting collection
# ===========================================================================


def collect_postings(
    role_title: str, location: str = "", *, max_postings: int | None = None
) -> tuple[list[JobPosting], list[SourceReport]]:
    """
    Query every source concurrently.

    Concurrency is per-source: the polite fetcher still serialises requests to
    the same host, so parallelism never translates into hammering one site.
    """
    from app.core.config import settings

    limit = max_postings or settings.scrape_max_postings
    postings: list[JobPosting] = []
    reports: list[SourceReport] = []

    with ThreadPoolExecutor(max_workers=min(6, len(ALL_SOURCES))) as pool:
        futures = {pool.submit(source.collect, role_title, location): source for source in ALL_SOURCES}
        for future in as_completed(futures):
            source = futures[future]
            try:
                found, report = future.result()
            except Exception as exc:
                log.error("Source %s raised: %s", source.name, exc)
                reports.append(
                    SourceReport(
                        name=source.name, source_type=source.source_type, url=source.homepage,
                        status="source_error", detail=f"{type(exc).__name__} while collecting.",
                        attribution=source.attribution,
                    )
                )
                continue
            reports.append(report)
            postings.extend(found)

    reports.sort(key=lambda r: (-r.postings_kept, r.name))
    deduped = _dedupe_postings(postings)[:limit]
    log.info("Collected %d posting(s) from %d source(s) (deduped from %d)",
             len(deduped), len(reports), len(postings))
    return deduped, reports


def _dedupe_postings(postings: Sequence[JobPosting]) -> list[JobPosting]:
    """Drop repeats of the same advert syndicated across several boards."""
    seen: set[str] = set()
    out: list[JobPosting] = []
    for posting in postings:
        key = normalise_key(f"{posting.title} {posting.company}")[:90]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(posting)
    return out


# ===========================================================================
# Step A2 - skills from each posting
# ===========================================================================


def extract_posting_skills(postings: list[JobPosting], *, use_llm: bool = True) -> list[LLMUsage]:
    """
    Fill `posting.skills` for every posting.

    The taxonomy pass always runs (fast, deterministic, no cost).  The LLM pass
    runs on the few most substantial adverts only -- running it on 24 postings
    would dominate the page's response time for very little extra recall.
    """
    usages: list[LLMUsage] = []

    for posting in postings:
        posting.skills = sorted(
            {s.canonical for s in normalise_skills(_taxonomy_skills(posting) + posting.tags)}
        )

    if not use_llm:
        return usages

    client = get_llm()
    candidates = sorted(postings, key=lambda p: len(p.description), reverse=True)[:4]
    for posting in candidates:
        if len(posting.description) < 300:
            continue
        try:
            payload, usage = client.complete_json(
                posting_skills_prompt(posting.title, posting.company, posting.description),
                system=POSTING_SKILLS_SYSTEM,
                task="posting_skills",
                temperature=0.0,
                max_tokens=900,
            )
            usages.append(usage)
            extra = json_guard.as_str_list(payload.get("required_skills"), limit=40) + json_guard.as_str_list(
                payload.get("preferred_skills"), limit=20
            )
            # Only keep what the advert text actually contains.
            grounded, _ = json_guard.enforce_grounding(extra, [posting.description, posting.title])
            merged = {s.canonical for s in normalise_skills(posting.skills + grounded)}
            posting.skills = sorted(merged)
        except Exception as exc:
            log.debug("LLM skill extraction skipped for %r: %s", posting.title[:40], exc)

    return usages


def _taxonomy_skills(posting: JobPosting) -> list[str]:
    """
    Deterministic skill spotting inside an advert.

    Matches every canonical name and alias in the taxonomy against the normalised
    advert text, plus any explicit "requirements" bullet lines.
    """
    blob = f"{posting.title}\n{posting.description}"
    probe = f" {normalise_key_preserve_words(blob)} "

    found: list[str] = []
    for canonical, meta in tx.CANONICAL_SKILLS.items():
        for form in [canonical, *meta["aliases"]]:
            # Conservative key: the alias as written, so "security plus" is not
            # reduced to "security" and matched against every security advert.
            key = normalise_key(form, strip_noise=False)
            if len(key) < tx.DOCUMENT_SCAN_MIN_KEY_LENGTH:
                continue
            if f" {key} " in probe:
                found.append(canonical)
                break

    # Requirement bullets often name skills the taxonomy does not hold yet
    # ("Bun", "HTMX", a niche internal tool).  Harvesting them is worthwhile,
    # but a bullet is prose, so each candidate is screened before it is kept.
    for line in posting.description.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("-") or len(stripped) > 140:
            continue
        body = stripped.lstrip("- ").strip()
        if not re.search(r"\b(experience|knowledge|proficien|familiar|skills?|understanding)\b", body, re.I):
            continue
        for candidate in split_skill_list(body)[:6]:
            if _looks_like_a_skill_name(candidate):
                found.append(candidate)

    return found


# Phrases that mark a fragment as a requirement *sentence* rather than a skill.
_NOT_A_SKILL_RE = re.compile(
    r"\b(?:years?\s+of|yrs?\s+of|ability\s+to|willing(?:ness)?\s+to|able\s+to|"
    r"track\s+record|degree\s+in|equivalent|or\s+similar|a\s+plus|nice\s+to\s+have|"
    r"such\s+as|including|etc|preferred|required|minimum|at\s+least)\b",
    re.I,
)


def _looks_like_a_skill_name(candidate: str) -> bool:
    """
    Screen a fragment harvested from advert prose.

    Real skill names are short noun phrases.  Anything that reads like a clause
    from a requirements list ("5+ years of experience in a related field") is
    rejected here rather than being carried into the requirement list, where it
    would appear to the user as a skill they are missing.
    """
    text = (candidate or "").strip()
    if not (2 <= len(text) <= 48):
        return False
    words = text.split()
    if len(words) > 5:
        return False
    if text[0] in "+0123456789" or text.startswith(("•", "*")):
        return False
    if _NOT_A_SKILL_RE.search(text):
        return False
    # Needs at least one real word; "C++"/"C#" are covered by the taxonomy path.
    return any(len(w) >= 2 and any(c.isalpha() for c in w) for w in words)


def normalise_key_preserve_words(text: str) -> str:
    """
    Like `normalise_key` but for long documents: keeps word order and all words.

    `normalise_key` strips noise words, which is right for a short skill string
    and wrong for an advert body where we need to find phrases inside it.
    """
    lowered = (text or "").lower()
    cleaned = "".join(ch if (ch.isalnum() or ch in "+#./&") else " " for ch in lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


# ===========================================================================
# Step C - fusion
# ===========================================================================


def fuse_skills(
    postings: Sequence[JobPosting], llm_payload: dict[str, Any]
) -> tuple[list[CombinedSkill], list[dict[str, Any]], dict[str, Any]]:
    """
    Merge scraped and LLM skills into one normalised, scored, attributed list.

    Returns (requirements, merge_evidence, filtering_report).
    """
    posting_total = max(1, len(postings))

    # ---- scraped side ----------------------------------------------------
    posting_counts: dict[str, int] = {}
    posting_sources: dict[str, set[str]] = {}
    scraped_forms: dict[str, set[str]] = {}

    for posting in postings:
        for raw in posting.skills:
            resolved = resolve_skill(raw)
            if resolved is None:
                continue
            canonical = resolved.canonical
            posting_counts[canonical] = posting_counts.get(canonical, 0) + 1
            posting_sources.setdefault(canonical, set()).add(posting.source)
            scraped_forms.setdefault(canonical, set()).update(resolved.surface_forms)

    # ---- LLM side --------------------------------------------------------
    llm_tiers: dict[str, set[str]] = {}
    llm_forms: dict[str, set[str]] = {}

    tier_keys = [
        ("core_technical_skills", "core"),
        ("desirable_technical_skills", "desirable"),
        ("tools_and_platforms", "tool"),
        ("soft_skills", "soft"),
        ("qualifications", "qualification"),
    ]
    for key, tier in tier_keys:
        for raw in json_guard.as_str_list(llm_payload.get(key), limit=40, max_len=70):
            resolved = resolve_skill(raw)
            if resolved is None:
                continue
            llm_tiers.setdefault(resolved.canonical, set()).add(tier)
            llm_forms.setdefault(resolved.canonical, set()).update(resolved.surface_forms)

    # ---- combine ---------------------------------------------------------
    combined: dict[str, CombinedSkill] = {}
    for canonical in set(posting_counts) | set(llm_tiers):
        count = posting_counts.get(canonical, 0)
        tiers = sorted(llm_tiers.get(canonical, set()))
        from_scrape = count > 0
        from_llm = bool(tiers)

        provenance = PROV_BOTH if (from_scrape and from_llm) else (PROV_SCRAPED if from_scrape else PROV_LLM)
        frequency = count / posting_total
        tier_weight = max((LLM_TIER_WEIGHTS.get(t, 0.5) for t in tiers), default=0.0)

        importance = (
            W_FREQUENCY * min(1.0, frequency * 1.6)
            + W_LLM_TIER * tier_weight
            + W_AGREEMENT * (1.0 if provenance == PROV_BOTH else 0.0)
        )

        forms = sorted(scraped_forms.get(canonical, set()) | llm_forms.get(canonical, set()))
        resolved = resolve_skill(canonical)

        combined[canonical] = CombinedSkill(
            canonical=canonical,
            category=tx.category_of(canonical),
            provenance=provenance,
            importance=round(importance, 4),
            posting_count=count,
            posting_frequency=round(frequency, 4),
            llm_tiers=tiers,
            surface_forms=forms or [canonical],
            example_sources=sorted(posting_sources.get(canonical, set())),
            normalisation_stage=resolved.stage if resolved else "",
        )

    # ---- essential flag --------------------------------------------------
    # "Essential" = the LLM called it core, OR a quarter of the collected
    # adverts asked for it.  Both routes are evidence-based rather than a
    # hand-tuned cut-off on the blended score.
    for skill in combined.values():
        skill.essential = ("core" in skill.llm_tiers) or (skill.posting_frequency >= 0.25)

    # ---- drop the uncorroborated long tail ------------------------------
    kept: list[CombinedSkill] = []
    dropped: list[CombinedSkill] = []
    for skill in combined.values():
        corroborated = bool(skill.llm_tiers) or skill.posting_count >= MIN_POSTING_SUPPORT
        (kept if corroborated else dropped).append(skill)

    ordered = sorted(kept, key=lambda s: (-s.importance, -s.posting_count, s.canonical.lower()))
    if len(ordered) > MAX_REQUIREMENTS:
        dropped.extend(ordered[MAX_REQUIREMENTS:])
        ordered = ordered[:MAX_REQUIREMENTS]

    if dropped:
        log.info(
            "Fusion dropped %d uncorroborated skill(s) (single-advert mentions, no LLM support): %s",
            len(dropped),
            [s.canonical for s in dropped[:10]],
        )

    evidence = [
        {
            "canonical": s.canonical,
            "variants": s.surface_forms[:6],
            "stage": s.normalisation_stage,
            "provenance": s.provenance,
            "posting_count": s.posting_count,
        }
        for s in ordered
        if len(s.surface_forms) > 1
    ][:40]

    filtering = {
        "candidates_considered": len(combined),
        "requirements_kept": len(ordered),
        "dropped_uncorroborated": len(dropped),
        "min_posting_support": MIN_POSTING_SUPPORT,
        "max_requirements": MAX_REQUIREMENTS,
        "dropped_examples": sorted(s.canonical for s in dropped)[:15],
        "rule": (
            f"A skill found only by scraping is kept only if at least "
            f"{MIN_POSTING_SUPPORT} independent adverts asked for it. Skills the language "
            f"model named are always kept. The list is then capped at the "
            f"{MAX_REQUIREMENTS} most important."
        ),
    }
    return ordered, evidence, filtering


def requirements_from_dict(payload: dict[str, Any]) -> RoleRequirements:
    """Rebuild a RoleRequirements from a stored row (used by the gap + interview modules)."""
    requirements = RoleRequirements(role_title=payload.get("role_title", ""))
    requirements.normalised_title = payload.get("normalised_title", "")
    requirements.title_assessment = payload.get("title_assessment", "")
    requirements.seniority = payload.get("seniority", "unspecified")
    requirements.role_summary = payload.get("role_summary", "")
    requirements.responsibilities = list(payload.get("responsibilities") or [])
    requirements.interview_focus_areas = list(payload.get("interview_focus_areas") or [])
    requirements.warnings = list(payload.get("warnings") or [])
    requirements.filtering = dict(payload.get("filtering") or {})
    requirements.llm_available = bool(payload.get("llm_available", True))
    requirements.llm_degraded = bool(payload.get("llm_degraded", False))

    for item in payload.get("combined_skills") or []:
        if not isinstance(item, dict):
            continue
        requirements.combined_skills.append(
            CombinedSkill(
                canonical=item.get("canonical", ""),
                category=item.get("category", tx.CATEGORY_OTHER),
                provenance=item.get("provenance", PROV_LLM),
                importance=float(item.get("importance", 0.0) or 0.0),
                posting_count=int(item.get("posting_count", 0) or 0),
                posting_frequency=float(item.get("posting_frequency", 0.0) or 0.0),
                llm_tiers=list(item.get("llm_tiers") or []),
                surface_forms=list(item.get("surface_forms") or []),
                example_sources=list(item.get("example_sources") or []),
                normalisation_stage=item.get("normalisation_stage", ""),
                essential=bool(item.get("essential", False)),
            )
        )

    for item in payload.get("postings") or []:
        if not isinstance(item, dict):
            continue
        requirements.postings.append(
            JobPosting(
                source=item.get("source", ""),
                source_type=item.get("source_type", "json_api"),
                title=item.get("title", ""),
                company=item.get("company", ""),
                location=item.get("location", ""),
                url=item.get("url", ""),
                posted_at=item.get("posted_at", ""),
                description=item.get("description", "") or item.get("description_excerpt", ""),
                tags=list(item.get("tags") or []),
                skills=list(item.get("skills") or []),
            )
        )
    return requirements


def normalised_requirement_skills(requirements: RoleRequirements) -> list[NormalisedSkill]:
    """Requirement skills as NormalisedSkill objects (for the matcher)."""
    return normalise_skills([s.canonical for s in requirements.combined_skills], cluster_unknowns=False)
