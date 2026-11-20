"""
Module 5 (interview stage machine and adaptation) and Module 6 (rubric scoring).

The interview is the main component of this project, so these tests pin down the
things that must hold whatever the language model says: the six stages run in
order, follow-ups are bounded, difficulty moves by at most one band, the rubric
cannot be altered by the model, and the feedback never becomes a hiring verdict.
"""

from __future__ import annotations

import pytest

from app.services.interview import rubric, stages
from app.services.interview.answer_analysis import (
    adapt_difficulty,
    analyse_answer,
    coverage_note,
    should_follow_up,
)
from app.services.interview.engine import _take_complete_sentence, _strip_speaker_label
from app.services.interview.scorer import _sanitise
from app.services.speech.tts import clean_for_speech, split_sentences


# ===========================================================================
# The stage machine
# ===========================================================================


def test_stage_order_matches_the_specification() -> None:
    """Introduction, background, technical, behavioural, their questions, closing."""
    assert stages.STAGE_ORDER == [
        "introduction",
        "background",
        "technical",
        "behavioural",
        "candidate_questions",
        "closing",
    ]


def test_every_stage_has_a_spec_and_a_budget() -> None:
    for key in stages.STAGE_ORDER:
        spec = stages.spec_for(key)
        assert spec.name and spec.goal and spec.instructions
        for difficulty in rubric.DIFFICULTIES:
            assert spec.budget(difficulty) >= 1


def test_stages_advance_in_order_to_completion() -> None:
    seen = []
    current = stages.INTRODUCTION
    for _ in range(len(stages.STAGE_ORDER) + 2):
        if current == stages.COMPLETE:
            break
        seen.append(current)
        current = stages.next_stage(current)
    assert seen == stages.STAGE_ORDER
    assert current == stages.COMPLETE


def test_stage_advances_once_its_budget_is_spent() -> None:
    state = stages.StageState(stage=stages.TECHNICAL)
    budget = stages.spec_for(stages.TECHNICAL).budget("medium")

    state.stage_question_count = budget - 1
    assert stages.should_advance(state, "medium") is False

    state.stage_question_count = budget
    assert stages.should_advance(state, "medium") is True


def test_harder_interviews_spend_longer_on_technical_questions() -> None:
    technical = stages.spec_for(stages.TECHNICAL)
    assert technical.budget("hard") >= technical.budget("medium") >= technical.budget("easy")


@pytest.mark.parametrize(
    "reply",
    ["No questions, thanks", "Nothing from me", "No thank you", "That's all", "I'm good"],
)
def test_candidate_questions_stage_ends_when_they_have_none(reply: str) -> None:
    state = stages.StageState(stage=stages.CANDIDATE_QUESTIONS, stage_question_count=0)
    assert stages.should_advance(state, "medium", reply) is True


def test_candidate_questions_stage_continues_when_they_do_ask() -> None:
    state = stages.StageState(stage=stages.CANDIDATE_QUESTIONS, stage_question_count=0)
    reply = "Yes, I would like to know how the team is structured and what the on-call rota looks like."
    assert stages.should_advance(state, "medium", reply) is False


def test_progress_payload_is_coherent() -> None:
    state = stages.StageState(stage=stages.TECHNICAL, stage_question_count=2, total_questions=6)
    progress = stages.progress(state, "medium")

    assert progress["stage"] == stages.TECHNICAL
    assert progress["stage_index"] == 2
    assert progress["stage_total"] == 6
    assert 0 <= progress["percent"] <= 100
    assert len(progress["stages"]) == 6

    statuses = [s["status"] for s in progress["stages"]]
    assert statuses[:2] == ["done", "done"]
    assert statuses[2] == "active"
    assert statuses[3:] == ["pending", "pending", "pending"]


def test_stage_state_round_trips() -> None:
    state = stages.StageState(
        stage=stages.BEHAVIOURAL,
        stage_question_count=2,
        total_questions=9,
        asked_questions=["q1", "q2"],
        demonstrated_skills=["Python"],
        answer_scores=[0.4, 0.8],
        consecutive_strong=1,
        effective_difficulty="hard",
        follow_up_depth=1,
    )
    restored = stages.StageState.from_dict(state.to_dict())
    assert restored.to_dict() == state.to_dict()


def test_introduction_and_closing_are_not_scored() -> None:
    """Greetings carry no assessable content, so they must not dilute the score."""
    assert stages.spec_for(stages.INTRODUCTION).scored is False
    assert stages.spec_for(stages.CLOSING).scored is False
    assert stages.spec_for(stages.CANDIDATE_QUESTIONS).scored is False
    assert stages.spec_for(stages.TECHNICAL).scored is True


# ===========================================================================
# Answer analysis and adaptation
# ===========================================================================

STRONG_ANSWER = (
    "In my last role I owned the shipment tracking API. The problem was that the median "
    "response time was about 420 milliseconds, so I profiled it and found an N plus one "
    "query pattern. First I fixed the query with a join, then I added Redis caching with a "
    "short TTL. As a result we got it down to roughly 180 milliseconds, and the operations "
    "team stopped complaining about the dashboard."
)
WEAK_ANSWER = "I think I probably used some stuff like that, sort of."
NON_ANSWER = "I don't know."


def test_strong_answer_is_recognised() -> None:
    analysis = analyse_answer(STRONG_ANSWER, ["Redis", "Python"])
    assert analysis.quality_band == "strong"
    assert analysis.quality_score > 0.6
    assert analysis.specificity_hits >= 2
    assert analysis.structure_hits >= 2
    assert analysis.metric_hits >= 1
    assert analysis.first_person is True
    assert "Redis" in analysis.skills_mentioned


def test_weak_answer_is_recognised() -> None:
    analysis = analyse_answer(WEAK_ANSWER)
    assert analysis.quality_band == "weak"
    assert analysis.hedge_hits >= 2
    assert "hedging" in " ".join(analysis.signals)


def test_non_answer_is_recognised() -> None:
    analysis = analyse_answer(NON_ANSWER)
    assert analysis.is_non_answer is True
    assert analysis.quality_score < 0.15


def test_team_only_answer_is_flagged() -> None:
    analysis = analyse_answer(
        "We built the service together and we deployed it and we monitored it afterwards."
    )
    assert analysis.team_only is True
    assert "team" in " ".join(analysis.signals).lower()


def test_empty_answer_is_handled() -> None:
    analysis = analyse_answer("")
    assert analysis.word_count == 0
    assert analysis.quality_score == 0.0


def test_role_relevant_skills_are_weighted_higher() -> None:
    answer = "I used Python and PostgreSQL to build the pipeline."
    relevant = analyse_answer(answer, ["Python", "PostgreSQL"])
    irrelevant = analyse_answer(answer, ["Photoshop", "Figma"])
    assert relevant.quality_score > irrelevant.quality_score
    assert relevant.role_skills_mentioned == ["Python", "PostgreSQL"]
    assert irrelevant.role_skills_mentioned == []


def test_salient_terms_give_the_follow_up_something_to_grip() -> None:
    analysis = analyse_answer(STRONG_ANSWER, ["Redis"])
    assert analysis.salient_terms
    assert any("redis" in term.lower() for term in analysis.salient_terms)


@pytest.mark.parametrize(
    ("base", "strong", "weak", "expected"),
    [
        ("medium", 0, 0, "medium"),
        ("medium", 2, 0, "hard"),
        ("medium", 5, 0, "hard"),
        ("medium", 0, 2, "easy"),
        ("easy", 0, 5, "easy"),     # cannot go below the floor
        ("hard", 5, 0, "hard"),     # cannot go above the ceiling
        ("easy", 2, 0, "medium"),
        ("hard", 0, 2, "medium"),
    ],
)
def test_difficulty_moves_at_most_one_band(base: str, strong: int, weak: int, expected: str) -> None:
    assert adapt_difficulty(base, strong, weak) == expected


def test_follow_up_on_a_substantive_answer() -> None:
    analysis = analyse_answer(STRONG_ANSWER, ["Redis"])
    assert should_follow_up(analysis, follow_up_depth=0) is True


def test_follow_up_on_a_thin_answer_asks_for_specifics() -> None:
    analysis = analyse_answer(WEAK_ANSWER)
    assert should_follow_up(analysis, follow_up_depth=0) is True


def test_follow_up_depth_is_bounded() -> None:
    """An interviewer who will not let go is a bad interviewer."""
    analysis = analyse_answer(STRONG_ANSWER, ["Redis"])
    assert should_follow_up(analysis, follow_up_depth=2) is False
    assert should_follow_up(analysis, follow_up_depth=5) is False


def test_no_follow_up_on_a_non_answer() -> None:
    analysis = analyse_answer(NON_ANSWER)
    assert should_follow_up(analysis, follow_up_depth=0) is False


def test_coverage_note_tells_the_model_what_to_do() -> None:
    strong = coverage_note(
        analyse_answer(STRONG_ANSWER, ["Redis"]),
        uncovered_topics=["system design"],
        follow_up=True,
        effective_difficulty="hard",
    )
    assert "FOLLOW-UP" in strong
    assert "hard" in strong
    assert "system design" in strong

    weak = coverage_note(
        analyse_answer(WEAK_ANSWER),
        uncovered_topics=[],
        follow_up=True,
        effective_difficulty="easy",
    )
    assert "specific example" in weak or "concrete detail" in weak

    first = coverage_note(None, uncovered_topics=[], follow_up=False, effective_difficulty="medium")
    assert "first turn" in first


# ===========================================================================
# Streaming sentence splitting (what makes audio start early)
# ===========================================================================


def test_sentence_is_emitted_as_soon_as_it_completes() -> None:
    sentence, rest = _take_complete_sentence("Thanks for joining me today. Now tell me")
    assert sentence == "Thanks for joining me today."
    assert rest.strip() == "Now tell me"


def test_incomplete_buffer_is_held_back() -> None:
    sentence, rest = _take_complete_sentence("Thanks for joining me toda")
    assert sentence == ""
    assert rest == "Thanks for joining me toda"


def test_abbreviation_does_not_split_a_sentence() -> None:
    sentence, _ = _take_complete_sentence("Tell me about your work, e.g. the API project. Then we")
    assert "e.g." in sentence
    assert sentence.endswith("project.")


def test_long_run_on_flushes_at_a_comma_so_audio_still_starts() -> None:
    buffer = (
        "so I want to understand how you approached that particular problem, "
        "and what the constraints were at the time, and whether you would do it differently now "
        "given what you know"
    )
    sentence, rest = _take_complete_sentence(buffer)
    assert sentence
    assert sentence.endswith(",")
    assert rest


def test_short_buffer_is_not_split() -> None:
    sentence, rest = _take_complete_sentence("Hi.")
    assert sentence == ""
    assert rest == "Hi."


@pytest.mark.parametrize(
    "prefix", ["Interviewer: ", "interviewer:", "You: ", "Assistant: ", "**", "  Interviewer:  "]
)
def test_speaker_labels_are_stripped(prefix: str) -> None:
    assert _strip_speaker_label(f"{prefix}Tell me about yourself.") == "Tell me about yourself."


def test_quotes_around_the_whole_reply_are_stripped() -> None:
    assert _strip_speaker_label('"Tell me about yourself."') == "Tell me about yourself."


# ===========================================================================
# Text-to-speech preparation
# ===========================================================================


@pytest.mark.parametrize(
    ("raw", "forbidden"),
    [
        ("**Important** question", "*"),
        ("## Heading\nThen a question", "#"),
        ("- First point\n- Second point", "- "),
        ("Use `pytest` for this", "`"),
        ("See [the docs](https://example.com)", "]("),
        ("Visit https://example.com/page now", "https://"),
        ("1. First\n2. Second", "1."),
    ],
)
def test_markdown_never_reaches_the_speech_engine(raw: str, forbidden: str) -> None:
    assert forbidden not in clean_for_speech(raw)


def test_stage_directions_are_removed() -> None:
    assert "pause" not in clean_for_speech("Tell me more. (pause) Then continue.").lower()


def test_clean_for_speech_keeps_the_actual_words() -> None:
    assert clean_for_speech("**Tell me** about `Python`") == "Tell me about Python"


def test_split_sentences_merges_fragments_and_caps_length() -> None:
    parts = split_sentences(
        "Right. Good. Now, tell me about the single most difficult technical problem you "
        "have had to solve in your career so far, including what made it difficult, what you "
        "tried first, and how you eventually got to an answer that worked."
    )
    assert parts
    assert all(len(part) <= 240 for part in parts)
    assert len(parts[0]) >= 10  # "Right." alone would sound clipped


def test_split_sentences_on_empty_input() -> None:
    assert split_sentences("") == []
    assert split_sentences("   ") == []


# ===========================================================================
# Module 6 - the rubric
# ===========================================================================


def test_rubric_is_defined_in_advance() -> None:
    payload = rubric.as_dict("medium")
    assert payload["defined_in_advance"] is True
    assert payload["version"] == rubric.RUBRIC_VERSION
    assert "rubric.py" in payload["note"]


def test_rubric_covers_the_categories_the_specification_asks_for() -> None:
    keys = set(rubric.CATEGORY_KEYS)
    assert {
        "technical_accuracy",
        "conceptual_understanding",
        "communication",
        "problem_solving",
        "relevance",
        "behavioural_competency",
    } <= keys


@pytest.mark.parametrize("difficulty", list(rubric.DIFFICULTIES))
def test_weights_sum_to_one(difficulty: str) -> None:
    weights = rubric.weights_for(difficulty)
    assert sum(weights.values()) == pytest.approx(1.0)
    assert set(weights) == set(rubric.CATEGORY_KEYS)
    assert all(w > 0 for w in weights.values())


def test_weights_differ_by_difficulty_in_the_expected_direction() -> None:
    easy = rubric.weights_for("easy")
    hard = rubric.weights_for("hard")
    # A senior interview tests depth more and presentation less.
    assert hard["technical_accuracy"] > easy["technical_accuracy"]
    assert hard["conceptual_understanding"] > easy["conceptual_understanding"]
    assert easy["communication"] > hard["communication"]


def test_unknown_difficulty_falls_back_to_medium() -> None:
    assert rubric.weights_for("banana") == rubric.weights_for("medium")


def test_scale_covers_one_to_five_with_descriptors() -> None:
    assert [entry["score"] for entry in rubric.SCALE] == [5, 4, 3, 2, 1]
    for entry in rubric.SCALE:
        assert entry["label"] and len(entry["descriptor"]) > 30


def test_overall_bands_cover_the_whole_range() -> None:
    for score in (0.0, 1.0, 2.5, 3.5, 4.0, 4.9, 5.0):
        band = rubric.overall_band(score)
        assert band["label"] and band["summary"]


def test_rubric_prompt_text_names_the_exact_keys() -> None:
    text = rubric.as_prompt_text("medium")
    for key in rubric.CATEGORY_KEYS:
        assert key in text
    assert "1 to 5" in text
    assert "null" in text


def test_rubric_disclaimer_denies_being_a_hiring_decision() -> None:
    assert "not a hiring decision" in rubric.DISCLAIMER.lower()
    assert "practice" in rubric.DISCLAIMER.lower()


# ===========================================================================
# Hiring-language sanitisation
# ===========================================================================


@pytest.mark.parametrize(
    "verdict",
    [
        "I would hire this candidate.",
        "I would not hire this candidate.",
        "They should be hired for this role.",
        "They should not be hired.",
        "This is a good fit for the role.",
        "This is not a good fit for the position.",
        "The candidate passed the interview.",
        "The candidate failed the interview.",
        "We would recommend hiring them.",
    ],
)
def test_hiring_verdicts_are_rewritten(verdict: str) -> None:
    cleaned = _sanitise(verdict).lower()
    for forbidden in ("would hire", "should be hired", "good fit for", "passed the interview", "failed the interview"):
        assert forbidden not in cleaned


def test_sanitisation_leaves_legitimate_feedback_alone() -> None:
    feedback = (
        "Answers were specific and well structured, though the explanation of caching "
        "trade-offs stayed at a high level."
    )
    assert _sanitise(feedback) == feedback


def test_sanitisation_handles_empty_input() -> None:
    assert _sanitise("") == ""
