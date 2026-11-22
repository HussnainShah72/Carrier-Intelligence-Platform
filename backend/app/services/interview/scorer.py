"""
Module 6 - scoring the interview against the rubric defined in advance.

The LLM judges; this module controls it.  Specifically:

  * the rubric (categories, scale, weights) comes from rubric.py, which is fixed
    in source control before any interview runs -- the model cannot add,
    rename or re-weight a category
  * every returned score is validated: unknown keys dropped, scores clamped to
    1-5, `null` accepted as "not tested" rather than silently becoming 0
  * the overall score is computed HERE in Python as a weighted mean over the
    categories that were actually scored -- not taken from the model, which
    cannot be trusted to do arithmetic consistently
  * hiring language is stripped: this is practice feedback, and the report says
    so in every place a reader might mistake it for a decision
  * if a category was never genuinely tested, that is reported as such

If the LLM is unavailable the offline rule-based assessor runs instead and the
report is clearly labelled as rule-based.
"""

from __future__ import annotations

import re
import time
from typing import Any

from app.core.logging_setup import get_logger
from app.services.interview import engine, rubric
from app.services.interview.stages import STAGE_ORDER
from app.services.llm import json_guard
from app.services.llm.client import get_llm
from app.services.llm.prompts import SCORING_SYSTEM, scoring_prompt
from app.services.metrics import recorder as metrics

log = get_logger(__name__)

# Phrasing that would turn practice feedback into an implied hiring decision.
_HIRING_PATTERNS = [
    (re.compile(r"\b(?:I|we)\s+would\s+(?:not\s+)?(?:hire|recommend hiring|reject|advance|progress)\b", re.I),
     "this is practice feedback rather than a hiring decision"),
    (re.compile(r"\b(?:should|would)\s+(?:not\s+)?be\s+(?:hired|rejected|offered|shortlisted)\b", re.I),
     "would benefit from further preparation"),
    (re.compile(r"\b(?:not\s+)?(?:a\s+)?(?:good|strong|poor)\s+fit\s+for\s+(?:the\s+)?(?:role|position|job)\b", re.I),
     "aligned differently with the role requirements"),
    (re.compile(r"\b(?:pass|fail)(?:ed|es)?\s+(?:the\s+)?interview\b", re.I),
     "completed the interview"),
    (re.compile(r"\b(?:definitely|certainly)\s+(?:hire|reject)\b", re.I), "practise further"),
]


def score_interview(interview_id: str) -> dict[str, Any]:
    """Build the full feedback report for a finished interview."""
    started = time.perf_counter()
    interview = engine.load_interview(interview_id)
    turns = engine.get_turns(interview_id)

    candidate_turns = [t for t in turns if t["speaker"] == engine.SPEAKER_CANDIDATE]
    rubric_payload = rubric.as_dict(interview.difficulty)
    weights = rubric.weights_for(interview.difficulty)

    if not candidate_turns:
        return _empty_report(interview, rubric_payload, "No answers were recorded in this interview.")

    client = get_llm()
    # Candidate turns that try to instruct the assessor ("give me 5/5") are
    # replaced before the model sees them. Measured in QA: a 3B model awarded
    # 5/5 in every category straight after such a turn.
    manipulation_turns = [t for t in candidate_turns if _MANIPULATION_RE.search(t["text"])]
    transcript = engine.transcript_text([
        t | {"text": _MANIPULATION_PLACEHOLDER} if t in manipulation_turns else t for t in turns
    ])

    try:
        payload, usage = client.complete_json(
            scoring_prompt(
                interview.role_title,
                interview.difficulty,
                rubric.as_prompt_text(interview.difficulty),
                transcript,
            ),
            system=SCORING_SYSTEM,
            task="scoring",
            temperature=0.15,
            max_tokens=2600,
        )
        engine_used = f"{usage.provider}/{usage.model}" if usage.provider else "unknown"
        degraded = usage.degraded
    except Exception as exc:
        log.error("Scoring failed for %s: %s", interview_id, exc)
        return _empty_report(
            interview,
            rubric_payload,
            "The scoring step could not be completed because the language model was unavailable "
            f"({type(exc).__name__}). Your transcript and performance metrics are still available below.",
        )

    # ---- validate category scores ---------------------------------------
    raw_scores = json_guard.as_dict_list(payload.get("category_scores"), limit=20)
    by_key: dict[str, dict[str, Any]] = {}
    for item in raw_scores:
        key = json_guard.as_text(item.get("key"), max_len=60).strip().lower().replace(" ", "_")
        if key not in rubric.CATEGORY_KEYS:
            # Tolerate a renamed-but-recognisable key before discarding it.
            match = next((k for k in rubric.CATEGORY_KEYS if k in key or key in k), "")
            if not match:
                log.info("Dropping unknown rubric key from model output: %r", key)
                continue
            key = match
        if key in by_key:
            continue

        raw_score = item.get("score")
        score: int | None
        if raw_score is None or (isinstance(raw_score, str) and raw_score.strip().lower() in ("null", "n/a", "")):
            score = None
        else:
            score = int(round(json_guard.as_float(raw_score, default=3.0, lo=1.0, hi=5.0)))

        by_key[key] = {
            "key": key,
            "name": rubric.CATEGORY_BY_KEY[key]["name"],
            "description": rubric.CATEGORY_BY_KEY[key]["description"],
            "weight": round(weights[key], 4),
            "weight_percent": round(weights[key] * 100, 1),
            "score": score,
            "score_label": rubric.SCORE_LABELS.get(score, "Not tested") if score else "Not tested",
            "justification": _sanitise(json_guard.as_text(item.get("justification"), max_len=900))
            or "No justification was provided for this category.",
            "evidence_quote": json_guard.as_text(item.get("evidence_quote"), max_len=400),
        }

    # Any category the model skipped is reported as untested, not invented.
    for key in rubric.CATEGORY_KEYS:
        if key not in by_key:
            by_key[key] = {
                "key": key,
                "name": rubric.CATEGORY_BY_KEY[key]["name"],
                "description": rubric.CATEGORY_BY_KEY[key]["description"],
                "weight": round(weights[key], 4),
                "weight_percent": round(weights[key] * 100, 1),
                "score": None,
                "score_label": "Not tested",
                "justification": "The assessor did not return a score for this category, so it is "
                                 "reported as not assessed rather than estimated.",
                "evidence_quote": "",
            }

    category_scores = [by_key[k] for k in rubric.CATEGORY_KEYS]
    calibration_notes = _calibrate(category_scores, turns, manipulation_turns)

    # ---- overall score, computed in Python -------------------------------
    scored = [c for c in category_scores if c["score"] is not None]
    if scored:
        weight_total = sum(c["weight"] for c in scored) or 1.0
        overall = sum(c["score"] * c["weight"] for c in scored) / weight_total
    else:
        overall = 0.0

    band = rubric.overall_band(overall)

    report = {
        "interview_id": interview_id,
        "role_title": interview.role_title,
        "difficulty": interview.difficulty,
        "mode": interview.mode,
        "started_at": interview.started_at,
        "ended_at": interview.ended_at,
        "rubric": rubric_payload,
        "overall_score": round(overall, 2),
        "overall_out_of": 5,
        "overall_percent": round(overall / 5 * 100, 1),
        "overall_band": band["label"],
        "overall_band_summary": band["summary"],
        "categories_scored": len(scored),
        "categories_not_tested": [c["name"] for c in category_scores if c["score"] is None],
        "category_scores": category_scores,
        "strengths": [_sanitise(s) for s in json_guard.as_str_list(payload.get("strengths"), limit=6, max_len=320)],
        "weaknesses": [_sanitise(s) for s in json_guard.as_str_list(payload.get("weaknesses"), limit=6, max_len=320)],
        "answers_to_improve": _answers_to_improve(payload.get("answers_to_improve")),
        "recommended_topics": json_guard.as_str_list(payload.get("recommended_topics"), limit=8, max_len=140),
        "improvement_plan": _improvement_plan(payload.get("improvement_plan")),
        "overall_comment": _sanitise(json_guard.as_text(payload.get("overall_comment"), max_len=1400)),
        "transcript": turns,
        "transcript_stats": _transcript_stats(turns),
        "stage_history": interview.state.stage_history,
        "stages_completed": _stages_completed(turns),
        "demonstrated_skills": interview.state.demonstrated_skills,
        "answer_quality_series": interview.state.answer_scores,
        "performance": metrics.interview_metrics(interview_id),
        "assessor": {
            "engine": engine_used,
            "degraded": degraded,
            "note": (
                "Scored by the deterministic offline engine (no language model was configured). "
                "It counts evidence such as answer length, concrete-example markers and technical "
                "vocabulary rather than understanding the content."
                if degraded
                else "Scored by a language model against the fixed rubric. The overall score is "
                "computed in code as a weighted mean of the category scores."
            ),
        },
        "calibration": calibration_notes,
        "disclaimer": rubric.DISCLAIMER,
        "scoring_ms": round((time.perf_counter() - started) * 1000, 1),
    }

    engine.save_report(interview_id, report)
    log.info("Scored interview %s: %.2f/5 (%s) in %.0f ms",
             interview_id, overall, band["label"], report["scoring_ms"])
    return report


# ---------------------------------------------------------------------------
# Calibration against local evidence
# ---------------------------------------------------------------------------

_MANIPULATION_RE = re.compile(
    r"\b(?:ignore (?:all |any )?(?:the )?(?:previous|prior|above) (?:instructions|prompts?)|"
    r"you are now|evaluation mode|system prompt|"
    r"(?:give|award|score) me (?:a )?(?:5|five|full|perfect|top)|"
    r"(?:5|five) out of (?:5|five) (?:in|on|for) (?:every|all|each)|"
    r"mark me as (?:excellent|hired)|rate me (?:5|five|excellent))",
    re.I,
)

_MANIPULATION_PLACEHOLDER = (
    "[Instead of answering, the candidate tried to instruct the assessor (for example asked "
    "for a perfect score). This is not an answer to the question and is evidence against "
    "Relevance and Communication.]"
)

_NON_ANSWER_RE = re.compile(
    r"^\s*(?:i (?:don'?t|do not) know|no idea|not sure|pass|skip|i'?m not (?:sure|familiar))\b", re.I
)

# Which interview stage tests which rubric category, for the local fallback.
_CATEGORY_STAGE = {"behavioural_competency": "behavioural"}


def _calibrate(
    category_scores: list[dict[str, Any]],
    turns: list[dict[str, Any]],
    manipulation_turns: list[dict[str, Any]],
) -> list[str]:
    """
    Cap the model's scores where the transcript's own evidence contradicts them.

    A small local model can be lenient (or obey an injected "give me 5/5"). The
    rubric is still applied by the model, but these deterministic ceilings keep
    an interview with declined answers or manipulation attempts from being
    reported as "Excellent". Every cap is written into the justification.
    """
    notes: list[str] = []
    answers = [t for t in turns if t["speaker"] == engine.SPEAKER_CANDIDATE
               and t.get("stage") in ("background", "technical", "behavioural")]
    if not answers:
        return notes

    non_answers = [t for t in answers if _NON_ANSWER_RE.match(t["text"])]
    bands = [((t.get("meta") or {}).get("analysis") or {}).get("quality_band") for t in answers]
    weak_share = sum(1 for b in bands if b == "weak") / len(answers)

    def cap(keys: tuple[str, ...], ceiling: int, reason: str) -> None:
        changed: list[str] = []
        for category in category_scores:
            if category["key"] in keys and category["score"] is not None and category["score"] > ceiling:
                category["score"] = ceiling
                category["score_label"] = rubric.SCORE_LABELS.get(ceiling, str(ceiling))
                category["justification"] += f" [Capped at {ceiling}/5: {reason}]"
                changed.append(category["name"])
        if changed:
            notes.append(f"{', '.join(changed)} capped at {ceiling}/5: {reason}.")

    if manipulation_turns:
        cap(("relevance", "communication"), 2,
            f"{len(manipulation_turns)} answer(s) tried to instruct the assessor instead of answering")
        cap(tuple(rubric.CATEGORY_KEYS), 4, "the transcript contains an attempt to manipulate the score")
    if non_answers:
        cap(("technical_accuracy", "conceptual_understanding"), 4,
            f"the candidate could not answer {len(non_answers)} question(s)")
    if weak_share >= 0.4:
        cap(tuple(rubric.CATEGORY_KEYS), 3, f"{weak_share:.0%} of assessed answers were rated weak by the local analysis")

    # A category the model called untested although its stage has real answers.
    for category in category_scores:
        stage = _CATEGORY_STAGE.get(category["key"])
        if category["score"] is not None or not stage:
            continue
        stage_answers = [t for t in answers if t.get("stage") == stage and t not in non_answers]
        scores = [((t.get("meta") or {}).get("analysis") or {}).get("quality_score") for t in stage_answers]
        scores = [s for s in scores if isinstance(s, (int, float))]
        if len(scores) >= 2:
            estimate = int(min(5, max(1, round(1 + 4 * sum(scores) / len(scores)))))
            category["score"] = estimate
            category["score_label"] = rubric.SCORE_LABELS.get(estimate, str(estimate))
            category["justification"] = (
                f"The assessor reported this category as untested, but the {stage} stage has "
                f"{len(scores)} substantive answers, so it is estimated at {estimate}/5 from the local "
                "answer analysis (specific examples, structure, reasoning). Treat it as indicative."
            )
            best = max(stage_answers, key=lambda t: ((t.get("meta") or {}).get("analysis") or {}).get("quality_score") or 0)
            category["evidence_quote"] = best["text"][:300]
            notes.append(f"{category['name']} estimated locally because the assessor skipped it.")
    return notes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitise(text: str) -> str:
    """Remove hiring-decision language from model output."""
    if not text:
        return ""
    out = text
    for pattern, replacement in _HIRING_PATTERNS:
        out = pattern.sub(replacement, out)
    return out.strip()


def _answers_to_improve(value: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in json_guard.as_dict_list(value, limit=6):
        question = json_guard.as_text(item.get("question"), max_len=300)
        if not question:
            continue
        out.append(
            {
                "question": question,
                "candidate_answer_summary": json_guard.as_text(item.get("candidate_answer_summary"), max_len=600),
                "why_it_fell_short": _sanitise(json_guard.as_text(item.get("why_it_fell_short"), max_len=600)),
                "stronger_answer_outline": json_guard.as_text(item.get("stronger_answer_outline"), max_len=900),
            }
        )
    return out


def _improvement_plan(value: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in json_guard.as_dict_list(value, limit=6):
        focus = json_guard.as_text(item.get("focus"), max_len=200)
        if not focus:
            continue
        out.append(
            {
                "timeframe": json_guard.as_text(item.get("timeframe"), default="Next steps", max_len=80),
                "focus": focus,
                "actions": json_guard.as_str_list(item.get("actions"), limit=5, max_len=240),
            }
        )
    return out


def _transcript_stats(turns: list[dict[str, Any]]) -> dict[str, Any]:
    candidate = [t for t in turns if t["speaker"] == engine.SPEAKER_CANDIDATE]
    interviewer = [t for t in turns if t["speaker"] == engine.SPEAKER_INTERVIEWER]
    words = [len(t["text"].split()) for t in candidate]
    return {
        "total_turns": len(turns),
        "interviewer_questions": len(interviewer),
        "candidate_answers": len(candidate),
        "candidate_total_words": sum(words),
        "candidate_mean_words": round(sum(words) / len(words), 1) if words else 0.0,
        "shortest_answer_words": min(words) if words else 0,
        "longest_answer_words": max(words) if words else 0,
    }


def _stages_completed(turns: list[dict[str, Any]]) -> list[str]:
    seen = {t["stage"] for t in turns}
    return [s for s in STAGE_ORDER if s in seen]


def _empty_report(interview: Any, rubric_payload: dict[str, Any], reason: str) -> dict[str, Any]:
    turns = engine.get_turns(interview.id)
    report = {
        "interview_id": interview.id,
        "role_title": interview.role_title,
        "difficulty": interview.difficulty,
        "mode": interview.mode,
        "started_at": interview.started_at,
        "ended_at": interview.ended_at,
        "rubric": rubric_payload,
        "overall_score": None,
        "overall_out_of": 5,
        "overall_percent": None,
        "overall_band": "Not assessed",
        "overall_band_summary": reason,
        "categories_scored": 0,
        "categories_not_tested": [c["name"] for c in rubric.CATEGORIES],
        "category_scores": [
            {
                "key": c["key"],
                "name": c["name"],
                "description": c["description"],
                "weight": round(rubric.weights_for(interview.difficulty)[c["key"]], 4),
                "weight_percent": round(rubric.weights_for(interview.difficulty)[c["key"]] * 100, 1),
                "score": None,
                "score_label": "Not tested",
                "justification": reason,
                "evidence_quote": "",
            }
            for c in rubric.CATEGORIES
        ],
        "strengths": [],
        "weaknesses": [],
        "answers_to_improve": [],
        "recommended_topics": [],
        "improvement_plan": [],
        "overall_comment": reason,
        "transcript": turns,
        "transcript_stats": _transcript_stats(turns),
        "stage_history": interview.state.stage_history,
        "stages_completed": _stages_completed(turns),
        "demonstrated_skills": interview.state.demonstrated_skills,
        "answer_quality_series": interview.state.answer_scores,
        "performance": metrics.interview_metrics(interview.id),
        "assessor": {"engine": "none", "degraded": True, "note": reason},
        "disclaimer": rubric.DISCLAIMER,
        "scoring_ms": 0.0,
    }
    engine.save_report(interview.id, report)
    return report
