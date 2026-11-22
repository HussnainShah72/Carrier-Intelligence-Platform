"""
Module 5c - the interview stage machine.

The assignment fixes the shape of the interview: introduction, candidate
background, technical questions, behavioural questions, candidate's own
questions, closing.  This module holds that structure as data and the rules for
moving through it, separately from the LLM prompting -- so the conversation
cannot wander off the required structure however the model behaves.

Stage advance rule
------------------
A stage ends when EITHER its question budget is spent, OR its exit condition is
met (for example: the candidate asked their questions and they were answered).
Budgets scale with difficulty, because a hard interview spends longer on
technical depth and less on warm-up.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

INTRODUCTION = "introduction"
BACKGROUND = "background"
TECHNICAL = "technical"
BEHAVIOURAL = "behavioural"
CANDIDATE_QUESTIONS = "candidate_questions"
CLOSING = "closing"
COMPLETE = "complete"

STAGE_ORDER = [INTRODUCTION, BACKGROUND, TECHNICAL, BEHAVIOURAL, CANDIDATE_QUESTIONS, CLOSING]


@dataclass(frozen=True)
class StageSpec:
    key: str
    name: str
    goal: str
    instructions: str
    budgets: dict[str, int]          # questions per difficulty
    scored: bool = True

    def budget(self, difficulty: str) -> int:
        return self.budgets.get(difficulty, self.budgets.get("medium", 2))


STAGE_SPECS: dict[str, StageSpec] = {
    INTRODUCTION: StageSpec(
        key=INTRODUCTION,
        name="Introduction",
        goal="Greet the candidate, introduce yourself and the role, and settle them in.",
        instructions=(
            "STAGE INSTRUCTIONS (introduction)\n"
            "- Greet the candidate by name if you know it, introduce yourself and the role.\n"
            "- Invite them to introduce themselves briefly.\n"
            "- Keep this short and warm. Do not start assessing yet.\n"
            "- Do not ask a technical question in this stage."
        ),
        budgets={"easy": 1, "medium": 1, "hard": 1},
        scored=False,
    ),
    BACKGROUND: StageSpec(
        key=BACKGROUND,
        name="Candidate Background",
        goal="Understand their actual experience and verify what the CV claims.",
        instructions=(
            "STAGE INSTRUCTIONS (background)\n"
            "- Probe the specific projects, roles and claims on their CV.\n"
            "- Establish what THEY did, not what their team did.\n"
            "- Follow up on anything impressive or anything vague.\n"
            "- Stay on experience; save deep technical questioning for the next stage."
        ),
        budgets={"easy": 2, "medium": 3, "hard": 3},
    ),
    TECHNICAL: StageSpec(
        key=TECHNICAL,
        name="Technical Questions",
        goal="Test the role's core technical requirements against their real understanding.",
        instructions=(
            "STAGE INSTRUCTIONS (technical)\n"
            "- Ask about the role's core technical requirements, grounded in their experience.\n"
            "- Move from 'can you explain' towards 'how would you decide' as they succeed.\n"
            "- If an answer is wrong, do not correct it at length - probe once, then move on.\n"
            "- Prefer questions about judgement and trade-offs over definition recall.\n"
            "- One question at a time. No multi-part questions."
        ),
        budgets={"easy": 3, "medium": 5, "hard": 6},
    ),
    BEHAVIOURAL: StageSpec(
        key=BEHAVIOURAL,
        name="Behavioural Questions",
        goal="Test collaboration, ownership, conflict, failure and working under pressure.",
        instructions=(
            "STAGE INSTRUCTIONS (behavioural)\n"
            "- Ask for real situations, not hypotheticals ('tell me about a time...').\n"
            "- Push gently for the candidate's own action and the outcome if they omit either.\n"
            "- Cover a different theme each question; do not ask two teamwork questions."
        ),
        budgets={"easy": 2, "medium": 3, "hard": 3},
    ),
    CANDIDATE_QUESTIONS: StageSpec(
        key=CANDIDATE_QUESTIONS,
        name="Candidate's Questions",
        goal="Give the candidate the floor and answer what they ask.",
        instructions=(
            "STAGE INSTRUCTIONS (candidate questions)\n"
            "- Invite their questions, then answer them briefly and plausibly as the interviewer.\n"
            "- You may describe the team and role in general terms; never promise an outcome, "
            "a salary, or a decision.\n"
            "- If they have no questions, acknowledge that and move to closing.\n"
            "- Do not turn this into more assessment."
        ),
        budgets={"easy": 2, "medium": 2, "hard": 2},
        scored=False,
    ),
    CLOSING: StageSpec(
        key=CLOSING,
        name="Closing",
        goal="Thank the candidate, explain next steps in general terms, and end.",
        instructions=(
            "STAGE INSTRUCTIONS (closing)\n"
            "- Thank them for their time and say next steps will follow.\n"
            "- Two or three sentences. Do not ask another question.\n"
            "- Never state or imply whether they passed."
        ),
        budgets={"easy": 1, "medium": 1, "hard": 1},
        scored=False,
    ),
}

# Phrases that mean "I have nothing to ask" in the candidate-questions stage.
_NO_QUESTIONS_MARKERS = (
    "no questions", "nothing else", "nothing from me", "nothing to ask", "no thanks", "no thank you", "i'm good", "im good",
    "that's all", "thats all", "all good", "no i don't", "no i dont", "not really",
    "you've covered", "youve covered", "covered everything", "i think that's it",
)


@dataclass
class StageState:
    """Where the interview is, and what has happened so far."""

    stage: str = INTRODUCTION
    stage_question_count: int = 0
    total_questions: int = 0
    asked_questions: list[str] = field(default_factory=list)
    covered_topics: list[str] = field(default_factory=list)
    demonstrated_skills: list[str] = field(default_factory=list)
    answer_scores: list[float] = field(default_factory=list)
    consecutive_weak: int = 0
    consecutive_strong: int = 0
    effective_difficulty: str = "medium"
    stage_history: list[dict[str, Any]] = field(default_factory=list)
    follow_up_depth: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "stage_question_count": self.stage_question_count,
            "total_questions": self.total_questions,
            "asked_questions": self.asked_questions,
            "covered_topics": self.covered_topics,
            "demonstrated_skills": self.demonstrated_skills,
            "answer_scores": self.answer_scores,
            "consecutive_weak": self.consecutive_weak,
            "consecutive_strong": self.consecutive_strong,
            "effective_difficulty": self.effective_difficulty,
            "stage_history": self.stage_history,
            "follow_up_depth": self.follow_up_depth,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> StageState:
        payload = payload or {}
        return cls(
            stage=payload.get("stage", INTRODUCTION),
            stage_question_count=int(payload.get("stage_question_count", 0) or 0),
            total_questions=int(payload.get("total_questions", 0) or 0),
            asked_questions=list(payload.get("asked_questions") or []),
            covered_topics=list(payload.get("covered_topics") or []),
            demonstrated_skills=list(payload.get("demonstrated_skills") or []),
            answer_scores=[float(s) for s in (payload.get("answer_scores") or [])],
            consecutive_weak=int(payload.get("consecutive_weak", 0) or 0),
            consecutive_strong=int(payload.get("consecutive_strong", 0) or 0),
            effective_difficulty=payload.get("effective_difficulty", "medium"),
            stage_history=list(payload.get("stage_history") or []),
            follow_up_depth=int(payload.get("follow_up_depth", 0) or 0),
        )


def spec_for(stage: str) -> StageSpec:
    return STAGE_SPECS.get(stage, STAGE_SPECS[BACKGROUND])


def next_stage(stage: str) -> str:
    try:
        index = STAGE_ORDER.index(stage)
    except ValueError:
        return COMPLETE
    return STAGE_ORDER[index + 1] if index + 1 < len(STAGE_ORDER) else COMPLETE


_QUESTION_OPENERS = (
    "what", "how", "why", "when", "where", "who", "which", "can", "could", "would",
    "is", "are", "do", "does", "will", "should", "tell me",
)


def _contains_question(text: str) -> bool:
    """Does the candidate actually ask something ("Nothing much, but what...?")"""
    if "?" in text:
        return True
    words = text.replace(",", " ").split()
    # "nothing much, but how big is the team" - a question without the "?"
    # that speech recognition often drops.
    for index, word in enumerate(words):
        if word in ("but", "although", "though", "actually") and index + 1 < len(words):
            if any(" ".join(words[index + 1:]).startswith(o + " ") for o in _QUESTION_OPENERS):
                return True
    return False


def should_advance(state: StageState, difficulty: str, last_answer: str = "") -> bool:
    """Has the current stage finished?"""
    spec = spec_for(state.stage)
    budget = spec.budget(difficulty)

    if state.stage == CANDIDATE_QUESTIONS and last_answer:
        probe = last_answer.strip().lower()
        if probe.strip(" .!,") in ("no", "nope", "none", "nothing", "nothing much", "no thank you"):
            return True
        if (
            len(probe) < 90
            and not _contains_question(probe)
            and any(marker in probe for marker in _NO_QUESTIONS_MARKERS)
        ):
            return True

    return state.stage_question_count >= budget


def progress(state: StageState, difficulty: str) -> dict[str, Any]:
    """Progress payload for the interview page's stage tracker."""
    total_budget = sum(spec_for(s).budget(difficulty) for s in STAGE_ORDER)
    done_budget = 0
    for stage in STAGE_ORDER:
        if stage == state.stage:
            done_budget += min(state.stage_question_count, spec_for(stage).budget(difficulty))
            break
        done_budget += spec_for(stage).budget(difficulty)

    stage_index = STAGE_ORDER.index(state.stage) if state.stage in STAGE_ORDER else len(STAGE_ORDER)
    return {
        "stage": state.stage,
        "stage_name": spec_for(state.stage).name if state.stage in STAGE_SPECS else "Complete",
        "stage_index": stage_index,
        "stage_total": len(STAGE_ORDER),
        "stage_question_count": state.stage_question_count,
        "stage_budget": spec_for(state.stage).budget(difficulty) if state.stage in STAGE_SPECS else 0,
        "total_questions": state.total_questions,
        "percent": round(min(100.0, done_budget / max(1, total_budget) * 100), 1),
        "effective_difficulty": state.effective_difficulty,
        "stages": [
            {
                "key": s,
                "name": STAGE_SPECS[s].name,
                "goal": STAGE_SPECS[s].goal,
                "budget": STAGE_SPECS[s].budget(difficulty),
                "scored": STAGE_SPECS[s].scored,
                "status": (
                    "done" if STAGE_ORDER.index(s) < stage_index
                    else "active" if s == state.stage
                    else "pending"
                ),
            }
            for s in STAGE_ORDER
        ],
    }


def stage_catalogue(difficulty: str = "medium") -> list[dict[str, Any]]:
    """Static stage description, shown before the interview starts."""
    return [
        {
            "key": s,
            "name": STAGE_SPECS[s].name,
            "goal": STAGE_SPECS[s].goal,
            "questions": STAGE_SPECS[s].budget(difficulty),
            # Same name as in progress(); the setup page reads "budget".
            "budget": STAGE_SPECS[s].budget(difficulty),
            "scored": STAGE_SPECS[s].scored,
        }
        for s in STAGE_ORDER
    ]
