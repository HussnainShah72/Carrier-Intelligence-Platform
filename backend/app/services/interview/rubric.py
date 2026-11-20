"""
Module 6a - the interview scoring rubric.

The assignment requires a rubric "that you define in advance".  This file IS
that definition: it is data, fixed before any interview runs, versioned, and
served to the frontend so the candidate can read the criteria *before* starting.
Nothing in the scoring path may invent a category or a weight.

Scale
-----
1-5 per category, with a written descriptor for every level so a score is
defensible rather than a vibe:

  5  Strong      specific, correct, well-structured, goes beyond what was asked
  4  Good        correct and specific, minor gaps
  3  Adequate    broadly correct but general, or correct with prompting
  2  Weak        vague, partially incorrect, or avoids the question
  1  Poor        incorrect, or no usable content
  null Not tested   the interview never genuinely probed this category

Weighting
---------
Weights sum to 1.0 and differ by difficulty, because what a junior interview is
really testing is not what a senior interview is testing.  The weights are
applied as a weighted mean over the categories that were actually scored, so a
category marked "not tested" dilutes nothing and inflates nothing.
"""

from __future__ import annotations

from typing import Any

RUBRIC_VERSION = "1.0"

SCALE: list[dict[str, Any]] = [
    {"score": 5, "label": "Strong",
     "descriptor": "Specific, technically correct and well-structured. Supports claims with concrete "
                   "detail from real work and addresses trade-offs without being asked."},
    {"score": 4, "label": "Good",
     "descriptor": "Correct and specific with real examples. Minor gaps or occasional vagueness, but "
                   "an interviewer would be satisfied."},
    {"score": 3, "label": "Adequate",
     "descriptor": "Broadly correct but general, textbook-like, or needed a prompt before the "
                   "substance arrived."},
    {"score": 2, "label": "Weak",
     "descriptor": "Vague, partly incorrect, or talks around the question without answering it. "
                   "Little evidence of first-hand experience."},
    {"score": 1, "label": "Poor",
     "descriptor": "Incorrect, contradictory, or contains no usable content."},
]

SCORE_LABELS = {entry["score"]: entry["label"] for entry in SCALE}

CATEGORIES: list[dict[str, Any]] = [
    {
        "key": "technical_accuracy",
        "name": "Technical Accuracy",
        "description": "Are the technical statements correct? Are terms used in their proper meaning?",
        "what_good_looks_like": "Correct definitions, correct cause and effect, no confidently wrong claims.",
        "weights": {"easy": 0.20, "medium": 0.25, "hard": 0.28},
    },
    {
        "key": "conceptual_understanding",
        "name": "Conceptual Understanding",
        "description": "Does the candidate understand WHY, not only HOW? Can they reason about "
                       "alternatives and consequences?",
        "what_good_looks_like": "Explains the reason behind a choice and what would change the decision.",
        "weights": {"easy": 0.18, "medium": 0.20, "hard": 0.24},
    },
    {
        "key": "communication",
        "name": "Communication",
        "description": "Is the answer clear, appropriately concise and well-ordered for a listener?",
        "what_good_looks_like": "States the point first, then the detail. No rambling, no one-word answers.",
        "weights": {"easy": 0.22, "medium": 0.18, "hard": 0.14},
    },
    {
        "key": "problem_solving",
        "name": "Problem Solving",
        "description": "When faced with an unfamiliar or open problem, is there a visible method?",
        "what_good_looks_like": "Clarifies the problem, states assumptions, works through options, checks the result.",
        "weights": {"easy": 0.15, "medium": 0.17, "hard": 0.18},
    },
    {
        "key": "relevance",
        "name": "Relevance to the Role",
        "description": "Do the examples and experience connect to what this specific role requires?",
        "what_good_looks_like": "Examples map onto the role's actual requirements rather than generic work stories.",
        "weights": {"easy": 0.13, "medium": 0.12, "hard": 0.10},
    },
    {
        "key": "behavioural_competency",
        "name": "Behavioural Competency",
        "description": "Evidence of collaboration, ownership, handling conflict, failure and pressure.",
        "what_good_looks_like": "Concrete situation, the candidate's own action, the outcome, and what they learned.",
        "weights": {"easy": 0.12, "medium": 0.08, "hard": 0.06},
    },
]

CATEGORY_KEYS = [c["key"] for c in CATEGORIES]
CATEGORY_BY_KEY = {c["key"]: c for c in CATEGORIES}

DIFFICULTIES = ("easy", "medium", "hard")

OVERALL_BANDS: list[dict[str, Any]] = [
    {"min": 4.5, "label": "Excellent", "summary": "Consistently specific, correct and well-structured answers."},
    {"min": 3.8, "label": "Strong", "summary": "Solid answers with real examples; a few areas to tighten."},
    {"min": 3.0, "label": "Competent", "summary": "Reasonable answers, but often general where detail was needed."},
    {"min": 2.2, "label": "Developing", "summary": "Some relevant knowledge, undermined by vagueness or gaps."},
    {"min": 0.0, "label": "Needs preparation", "summary": "Answers lacked the specifics an interviewer needs."},
]

DISCLAIMER = (
    "This is automated practice feedback generated from a transcript by a language model "
    "against a fixed rubric. It is not an assessment of your ability and not a hiring "
    "decision. Scores can be wrong, especially where speech recognition mis-transcribed "
    "an answer. Use it to find areas to practise, not as a verdict on yourself."
)


def weights_for(difficulty: str) -> dict[str, float]:
    """Category weights for a difficulty, normalised to sum to exactly 1.0."""
    level = difficulty if difficulty in DIFFICULTIES else "medium"
    raw = {c["key"]: float(c["weights"][level]) for c in CATEGORIES}
    total = sum(raw.values()) or 1.0
    return {key: value / total for key, value in raw.items()}


def overall_band(score: float) -> dict[str, Any]:
    for band in OVERALL_BANDS:
        if score >= band["min"]:
            return {"label": band["label"], "summary": band["summary"]}
    return {"label": OVERALL_BANDS[-1]["label"], "summary": OVERALL_BANDS[-1]["summary"]}


def as_dict(difficulty: str = "medium") -> dict[str, Any]:
    """The whole rubric, for the API and the Interview Results page."""
    weights = weights_for(difficulty)
    return {
        "version": RUBRIC_VERSION,
        "difficulty": difficulty if difficulty in DIFFICULTIES else "medium",
        "scale": SCALE,
        "categories": [
            {
                "key": c["key"],
                "name": c["name"],
                "description": c["description"],
                "what_good_looks_like": c["what_good_looks_like"],
                "weight": round(weights[c["key"]], 4),
                "weight_percent": round(weights[c["key"]] * 100, 1),
            }
            for c in CATEGORIES
        ],
        "overall_bands": OVERALL_BANDS,
        "disclaimer": DISCLAIMER,
        "defined_in_advance": True,
        "note": "This rubric is fixed in source control before any interview is conducted "
                "(backend/app/services/interview/rubric.py) and is shown to the candidate "
                "before the interview starts.",
    }


def as_prompt_text(difficulty: str = "medium") -> str:
    """The rubric rendered for the scoring prompt, with the exact keys to use."""
    weights = weights_for(difficulty)
    lines = [
        f"Rubric version {RUBRIC_VERSION}. Difficulty: {difficulty}.",
        "Score each category from 1 to 5, or null if the interview never genuinely tested it.",
        "",
        "SCALE:",
    ]
    for entry in SCALE:
        lines.append(f"  {entry['score']} = {entry['label']}: {entry['descriptor']}")
    lines.append("")
    lines.append("CATEGORIES (use these exact keys):")
    for category in CATEGORIES:
        lines.append(
            f"  - {category['key']} (weight {weights[category['key']]:.2f}) — {category['name']}: "
            f"{category['description']} Good looks like: {category['what_good_looks_like']}"
        )
    return "\n".join(lines)
