"""
Module 5d - measuring an answer, so the interview can adapt in real time.

Why this is deterministic rather than an LLM call
-------------------------------------------------
Adaptation happens between the candidate finishing speaking and the interviewer
starting to reply, which is exactly the latency the project is graded on.  A
second LLM round-trip there would add hundreds of milliseconds to every turn,
so the adaptation signal is computed locally in ~1 ms from measurable features
of the text:

    length            thin answers are the strongest signal of a weak answer
    specificity       "for example", "in my last role", "we migrated"
    structure         "first", "then", "the outcome was"  (STAR-shaped answers)
    hedging           "maybe", "sort of", "I think", "not sure"
    technical density canonical skills from the taxonomy, weighted higher when
                      they are skills this ROLE actually requires
    self-attribution  "I built" vs "we built" -- interviewers care which

The composite 0..1 score drives three decisions: whether to follow up or move
on, whether to step difficulty up or down, and whether to ask for a concrete
example.  The LLM still writes the question; this only tells it what kind of
question to write.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from app.services.skills.matcher import skills_in_text

# --- lexical signals --------------------------------------------------------

# Markers that an answer describes something that actually happened, rather
# than what the candidate "would" do.
#
# The verb list used to be a fixed enumeration, which systematically
# under-scored good answers: "I profiled it", "I traced it back" and "we got it
# down to 180 milliseconds" are all concrete first-person actions and none of
# them were counted. Any past-tense verb after "I"/"we" now counts, which is
# what the signal was always meant to capture.
SPECIFICITY_RE = re.compile(
    r"\b(?:for example|for instance|specifically|in particular|such as|"
    r"in my (?:last|previous|current|first) (?:role|job|project|team|internship)|"
    r"at (?:my|the) (?:last|previous|current) (?:company|employer|job)|"
    r"(?:i|we)\s+(?:[a-z]+ed|built|wrote|ran|led|got|took|found|chose|made|set|"
    r"saw|kept|sent|spent|went|had to|ended up)\b|"
    r"the result was|as a result|which meant|so that|ended up|turned out|"
    r"what happened was|in the end)\b",
    re.I,
)

STRUCTURE_RE = re.compile(
    r"\b(?:first(?:ly)?|second(?:ly)?|then|after that|next|finally|eventually|"
    r"the (?:problem|issue|situation|challenge) was|my (?:approach|role|task) was|"
    r"what i did was|the outcome|in the end|to start with|the context was)\b",
    re.I,
)

HEDGE_RE = re.compile(
    r"\b(?:i think|i guess|maybe|perhaps|probably|possibly|sort of|kind of|kinda|sorta|"
    r"not (?:really )?sure|i'm not sure|im not sure|i don't know|i dont know|"
    r"or something|whatever|stuff like that|things like that|basically|you know)\b",
    re.I,
)

FIRST_PERSON_RE = re.compile(r"\bi\s+(?:[a-z]+ed|built|wrote|made|led|ran|set|took|chose|went|had|was|am)\b", re.I)
TEAM_ONLY_RE = re.compile(r"\bwe\s+(?:[a-z]+ed|built|wrote|made|led|ran|set|took|chose)\b", re.I)
QUESTION_RE = re.compile(r"\?\s*$|^\s*(?:what|how|who|when|where|why|is|are|do|does|can|could|would|will)\b", re.I)
METRIC_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*"
    r"(?:%|percent|ms|milliseconds?|seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|"
    r"months?|years?|users?|customers?|clients?|requests?|rows?|records?|tickets?|alerts?|"
    r"stores?|teams?|people|times|x|k|m|gb|mb|tb)\b",
    re.I,
)

# Reasoning: the candidate explains WHY, compares options, or names a cost.
# A short answer full of reasoning is a good answer; length alone is not.
REASONING_RE = re.compile(
    r"\b(?:because|since|so that|which means|that means|the reason|trade-?offs?|trading|"
    r"instead of|rather than|compared (?:to|with)|depends on|it depends|the downside|"
    r"the upside|at the cost of|in exchange for|pros? and cons?|the risk is|"
    r"to avoid|to prevent|to reduce|to keep|otherwise|first|then|"
    r"so (?:a|an|the|it|we|i|that|they|each|every|any))\b",
    re.I,
)

# Technical vocabulary that is not a "skill" (so the taxonomy misses it) but
# is strong evidence of real understanding in a technical answer.
TECH_TERM_RE = re.compile(
    r"(?:\bo\([^)]{1,12}\)|\b(?:hash ?maps?|hash ?tables?|heaps?|priority queues?|queues?|stacks?|"
    r"trees?|graphs?|index(?:es)?|indices|caching|cache|ttl|latency|throughput|complexity|big o|"
    r"concurren\w*|threads?|locks?|deadlocks?|race conditions?|transactions?|"
    r"idempoten\w*|pagination|sharding|replica\w*|partition\w*|load balanc\w*|"
    r"profil\w*|benchmark\w*|bottlenecks?|memory leaks?|garbage collect\w*|invalidat\w*|"
    r"schemas?|normali[sz]\w*|joins?|quer(?:y|ies)|endpoints?|rate limit\w*|"
    r"retr(?:y|ies|ied)|duplicates?|headers?|consisten\w*|atomic\w*|timeouts?|rollbacks?|rolled back|migrations?|regressions?|unit tests?|"
    r"integration tests?|mocks?|encryption|hashing|authenticat\w*|authori[sz]\w*|"
    r"vulnerabilit\w*|overfitting|regulari[sz]\w*|cross-?validation|postmortem|"
    r"precision|recall|baseline|p-?values?|outliers?|stakeholders?|root cause)\b)",
    re.I,
)

NON_ANSWER_RE = re.compile(
    r"^\s*(?:i (?:don'?t|do not) know|no idea|not sure|pass|skip|next|can we move on|"
    r"i'?m not familiar|never (?:used|done) (?:that|it)|sorry,? (?:what|i)|could you repeat)\b",
    re.I,
)

QUALITY_WEAK = "weak"
QUALITY_ADEQUATE = "adequate"
QUALITY_STRONG = "strong"


@dataclass
class AnswerAnalysis:
    word_count: int = 0
    quality_score: float = 0.0
    quality_band: str = QUALITY_WEAK
    specificity_hits: int = 0
    structure_hits: int = 0
    hedge_hits: int = 0
    metric_hits: int = 0
    reasoning_hits: int = 0
    tech_term_hits: int = 0
    first_person: bool = False
    team_only: bool = False
    is_non_answer: bool = False
    is_question: bool = False
    skills_mentioned: list[str] = field(default_factory=list)
    role_skills_mentioned: list[str] = field(default_factory=list)
    salient_terms: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "word_count": self.word_count,
            "quality_score": round(self.quality_score, 3),
            "quality_band": self.quality_band,
            "specificity_hits": self.specificity_hits,
            "structure_hits": self.structure_hits,
            "hedge_hits": self.hedge_hits,
            "metric_hits": self.metric_hits,
            "reasoning_hits": self.reasoning_hits,
            "tech_term_hits": self.tech_term_hits,
            "first_person": self.first_person,
            "team_only": self.team_only,
            "is_non_answer": self.is_non_answer,
            "is_question": self.is_question,
            "skills_mentioned": self.skills_mentioned,
            "role_skills_mentioned": self.role_skills_mentioned,
            "salient_terms": self.salient_terms,
            "signals": self.signals,
        }


def analyse_answer(text: str, role_skills: Sequence[str] = ()) -> AnswerAnalysis:
    """Extract the adaptation features from one candidate answer."""
    analysis = AnswerAnalysis()
    body = (text or "").strip()
    if not body:
        analysis.signals.append("empty answer")
        return analysis

    words = body.split()
    analysis.word_count = len(words)
    analysis.specificity_hits = len(SPECIFICITY_RE.findall(body))
    analysis.structure_hits = len(STRUCTURE_RE.findall(body))
    analysis.hedge_hits = len(HEDGE_RE.findall(body))
    analysis.metric_hits = len(METRIC_RE.findall(body))
    analysis.reasoning_hits = len(REASONING_RE.findall(body))
    analysis.tech_term_hits = len(TECH_TERM_RE.findall(body))
    analysis.first_person = bool(FIRST_PERSON_RE.search(body))
    analysis.team_only = bool(TEAM_ONLY_RE.search(body)) and not analysis.first_person
    analysis.is_non_answer = bool(NON_ANSWER_RE.match(body)) and analysis.word_count < 25
    analysis.is_question = bool(QUESTION_RE.search(body)) and analysis.word_count < 40

    analysis.skills_mentioned = skills_in_text(body, limit=14)
    role_set = {s.lower() for s in role_skills}
    analysis.role_skills_mentioned = [s for s in analysis.skills_mentioned if s.lower() in role_set]
    analysis.salient_terms = _salient_terms(body, analysis.skills_mentioned)

    # ---- composite score -------------------------------------------------
    # Length saturates early: a 45-word answer with substance is complete in a
    # spoken interview. Weighting length heavily used to rate dense, correct
    # technical answers ("a hash map for O(1) lookups and a heap ...") as weak,
    # which then pushed the difficulty DOWN during a good interview.
    length_component = min(1.0, analysis.word_count / 45)
    specificity_component = min(1.0, analysis.specificity_hits / 2)
    structure_component = min(1.0, analysis.structure_hits / 2)
    technical_component = min(
        1.0,
        (len(analysis.skills_mentioned) + 2 * len(analysis.role_skills_mentioned) + analysis.tech_term_hits) / 4,
    )
    reasoning_component = min(1.0, analysis.reasoning_hits / 2)
    metric_component = min(1.0, float(analysis.metric_hits))

    score = (
        0.16 * length_component
        + 0.20 * specificity_component
        + 0.08 * structure_component
        + 0.26 * technical_component
        + 0.20 * reasoning_component
        + 0.10 * metric_component
    )

    hedge_density = analysis.hedge_hits / max(1, analysis.word_count / 40)
    score -= min(0.22, hedge_density * 0.10)
    if analysis.first_person:
        score += 0.05
    if analysis.team_only:
        score -= 0.05
    if analysis.is_non_answer:
        score = min(score, 0.08)

    analysis.quality_score = max(0.0, min(1.0, score))
    analysis.quality_band = (
        QUALITY_STRONG if analysis.quality_score >= 0.62
        else QUALITY_ADEQUATE if analysis.quality_score >= 0.34
        else QUALITY_WEAK
    )

    # ---- human-readable signals for the UI and the report ----------------
    if analysis.word_count < 18:
        analysis.signals.append(f"very short ({analysis.word_count} words)")
    if analysis.specificity_hits == 0 and analysis.word_count >= 25:
        analysis.signals.append("no concrete example")
    if analysis.hedge_hits >= 3:
        analysis.signals.append(f"hedging x{analysis.hedge_hits}")
    if analysis.team_only:
        analysis.signals.append("describes the team, not their own action")
    if analysis.role_skills_mentioned:
        analysis.signals.append(f"role-relevant: {', '.join(analysis.role_skills_mentioned[:4])}")
    if analysis.metric_hits:
        analysis.signals.append(f"quantified ({analysis.metric_hits})")
    if analysis.is_non_answer:
        analysis.signals.append("declined to answer")
    if analysis.structure_hits >= 2:
        analysis.signals.append("structured answer")
    if analysis.reasoning_hits:
        analysis.signals.append(f"explains reasoning ({analysis.reasoning_hits})")

    return analysis


_STOPWORDS = {
    "that", "this", "with", "from", "have", "been", "were", "they", "them", "then", "than",
    "what", "when", "where", "which", "while", "would", "could", "should", "about", "there",
    "their", "these", "those", "into", "just", "like", "really", "because", "doing", "going",
    "something", "anything", "everything", "basically", "actually", "think", "know", "work",
    "working", "worked", "also", "very", "much", "more", "most", "some", "well", "good",
    "team", "time", "lot", "kind", "sort", "thing", "things", "stuff", "yeah", "okay",
}


def _salient_terms(text: str, skills: Sequence[str], limit: int = 5) -> list[str]:
    """
    Terms worth following up on.

    Canonical skills first (they are genuinely the interesting hooks), then
    capitalised proper nouns, then long content words.
    """
    out: list[str] = list(skills[:3])

    for match in re.finditer(r"\b([A-Z][a-zA-Z0-9+#.]{2,}(?:\s+[A-Z][a-zA-Z0-9+#.]{2,})?)\b", text):
        term = match.group(1).strip()
        if match.start() == 0 or term.lower() in _STOPWORDS:
            continue
        if term not in out:
            out.append(term)
        if len(out) >= limit:
            return out

    for word in re.findall(r"\b([a-z]{6,})\b", text.lower()):
        if word in _STOPWORDS or word in {t.lower() for t in out}:
            continue
        out.append(word)
        if len(out) >= limit:
            break
    return out[:limit]


# ---------------------------------------------------------------------------
# Adaptation decisions
# ---------------------------------------------------------------------------


def adapt_difficulty(base: str, consecutive_strong: int, consecutive_weak: int) -> str:
    """
    Move the effective difficulty, never more than one band from the base.

    Two strong answers in a row earn a harder question; two weak ones earn an
    easier one.  Clamping to +/-1 band stops a single outlier from derailing the
    rest of the interview.
    """
    ladder = ["easy", "medium", "hard"]
    base_index = ladder.index(base) if base in ladder else 1

    offset = 0
    if consecutive_strong >= 2:
        offset = 1
    elif consecutive_weak >= 2:
        offset = -1

    return ladder[max(0, min(len(ladder) - 1, base_index + offset))]


def should_follow_up(analysis: AnswerAnalysis, follow_up_depth: int, *, max_depth: int = 2) -> bool:
    """
    Follow up, or move on?

    Follow up when there is something to dig into (a substantive answer) or
    something to repair (a thin one) -- but never more than `max_depth` times in
    a row, because an interviewer who will not let go is a bad interviewer and a
    frustrating demo.
    """
    if follow_up_depth >= max_depth:
        return False
    if analysis.is_non_answer or analysis.is_question:
        return False
    if analysis.quality_band == QUALITY_STRONG and analysis.salient_terms:
        return True
    if analysis.quality_band == QUALITY_WEAK and analysis.word_count >= 5:
        return True
    return False


def coverage_note(
    analysis: AnswerAnalysis | None,
    *,
    uncovered_topics: Sequence[str],
    follow_up: bool,
    effective_difficulty: str,
) -> str:
    """
    The instruction block handed to the LLM for this turn.

    Deliberately explicit: it tells the model what the local analysis found and
    what kind of question is wanted, so adaptation is traceable in the logs
    rather than an emergent property of the prompt.
    """
    lines: list[str] = [f"Pitch this question at: {effective_difficulty} difficulty."]

    if analysis is None:
        lines.append("This is the first turn; no answer to react to yet.")
        return "\n".join(lines)

    lines.append(
        f"Local analysis of their last answer: {analysis.word_count} words, "
        f"quality {analysis.quality_band} ({analysis.quality_score:.2f}), "
        f"{analysis.specificity_hits} concrete-example marker(s), "
        f"{analysis.hedge_hits} hedge(s)."
    )

    if analysis.is_non_answer:
        lines.append("They declined or could not answer. Acknowledge it without judgement and move to a different topic.")
    elif analysis.is_question:
        lines.append("They asked you something. Answer it briefly, then continue.")
    elif follow_up and analysis.quality_band == QUALITY_STRONG:
        hook = ", ".join(analysis.salient_terms[:3]) or "what they just described"
        lines.append(f"ASK A FOLLOW-UP. Go deeper into: {hook}. Do not change topic.")
    elif follow_up and analysis.quality_band == QUALITY_WEAK:
        lines.append("Their answer was thin. Ask once for a specific example or concrete detail, then move on.")
    else:
        lines.append("Move on to a NEW question in this stage. Do not re-ask what they just answered.")

    if analysis.team_only:
        lines.append("They spoke only about what the team did. Ask what THEY personally did.")

    if uncovered_topics:
        lines.append("Topics still to cover for this role: " + ", ".join(list(uncovered_topics)[:6]) + ".")

    if analysis.role_skills_mentioned:
        lines.append("Role-relevant skills they have now demonstrated: " + ", ".join(analysis.role_skills_mentioned[:6]) + ".")

    return "\n".join(lines)
