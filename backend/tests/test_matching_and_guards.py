"""
Module 3 (match and gap analysis), Module 4 (CV improvement guards) and the
LLM output defences in json_guard.

The guard tests are the most important in the suite: they are what stops the
product telling a user it improved their CV when it actually invented a
qualification for them.
"""

from __future__ import annotations

import pytest

from app.core.errors import LLMOutputError, ValidationError
from app.services.improve import bullets as improve
from app.services.jobs.collector import CombinedSkill, fuse_skills
from app.services.jobs.sources import JobPosting
from app.services.llm import json_guard
from app.services.skills import taxonomy as tx
from app.services.skills.matcher import MATCHED, MISSING, PARTIAL, analyse_gap, skills_in_text


def requirement(
    canonical: str,
    *,
    importance: float = 0.6,
    essential: bool = False,
    posting_count: int = 3,
    provenance: str = "both",
) -> CombinedSkill:
    return CombinedSkill(
        canonical=canonical,
        category=tx.category_of(canonical),
        provenance=provenance,
        importance=importance,
        posting_count=posting_count,
        essential=essential,
    )


# ===========================================================================
# Module 3 - matching
# ===========================================================================


def test_exact_match_is_matched() -> None:
    analysis = analyse_gap(["Python", "SQL"], [requirement("Python")], role_title="Test")
    assert analysis.comparisons[0].status == MATCHED
    assert analysis.comparisons[0].confidence == 1.0
    assert analysis.match_percent == pytest.approx(100.0)


def test_absent_skill_is_missing() -> None:
    analysis = analyse_gap(["Python"], [requirement("Kubernetes")], role_title="Test")
    assert analysis.comparisons[0].status == MISSING
    assert analysis.match_percent == pytest.approx(0.0)


def test_variant_spelling_on_the_cv_counts_as_a_match() -> None:
    """The CV says ReactJS; the role wants React."""
    from app.services.skills.normalizer import normalise_skills

    cv_skills = [s.to_dict() for s in normalise_skills(["ReactJS"])]
    analysis = analyse_gap(cv_skills, [requirement("React")], role_title="Test")
    assert analysis.comparisons[0].status == MATCHED


def test_implied_skill_is_a_partial_match() -> None:
    """Holding React partially evidences JavaScript."""
    analysis = analyse_gap(["React"], [requirement("JavaScript")], role_title="Test")
    comparison = analysis.comparisons[0]
    assert comparison.status == PARTIAL
    assert comparison.cv_skill == "React"
    assert "implied" in comparison.matched_via
    assert comparison.credit == 0.5


def test_foundation_present_is_a_partial_match() -> None:
    """The CV has JavaScript; the role wants React, which builds on it."""
    analysis = analyse_gap(["JavaScript"], [requirement("React")], role_title="Test")
    comparison = analysis.comparisons[0]
    assert comparison.status == PARTIAL
    assert comparison.cv_skill == "JavaScript"
    assert "foundation" in comparison.matched_via


def test_every_comparison_carries_evidence() -> None:
    analysis = analyse_gap(
        ["Python", "React"],
        [requirement("Python"), requirement("JavaScript"), requirement("Kubernetes")],
        role_title="Test",
    )
    for comparison in analysis.comparisons:
        assert comparison.evidence, f"{comparison.requirement} has no evidence string"


def test_score_is_weighted_by_importance() -> None:
    """
    Missing one core requirement must hurt more than missing a minor one.
    """
    requirements = [
        requirement("Python", importance=1.0, essential=True),
        requirement("Figma", importance=0.1),
    ]
    has_core = analyse_gap(["Python"], requirements, role_title="Test")
    has_minor = analyse_gap(["Figma"], requirements, role_title="Test")

    assert has_core.match_percent > has_minor.match_percent
    assert has_core.match_percent == pytest.approx(100 * 1.0 / 1.1, abs=0.1)


def test_severity_escalates_for_missing_essentials() -> None:
    analysis = analyse_gap(
        [],
        [
            requirement("Python", importance=1.0, essential=True),
            requirement("Figma", importance=0.1, posting_count=1),
        ],
        role_title="Test",
    )
    by_name = {c.requirement: c for c in analysis.comparisons}
    assert by_name["Python"].severity == "critical"
    assert by_name["Figma"].severity in ("medium", "low")


def test_priority_gaps_are_ordered_by_severity_then_importance() -> None:
    analysis = analyse_gap(
        [],
        [
            requirement("Figma", importance=0.2, posting_count=1),
            requirement("Python", importance=1.0, essential=True),
            requirement("Docker", importance=0.7),
        ],
        role_title="Test",
    )
    order = [c.requirement for c in analysis.priority_gaps()]
    assert order[0] == "Python"


def test_extra_cv_skills_are_reported() -> None:
    analysis = analyse_gap(
        [
            {"canonical": "Python", "category": "Programming Language"},
            {"canonical": "Rust", "category": "Programming Language"},
        ],
        [requirement("Python")],
        role_title="Test",
    )
    assert [s["canonical"] for s in analysis.extra_skills] == ["Rust"]


def test_category_breakdown_sums_correctly() -> None:
    analysis = analyse_gap(
        ["Python"],
        [requirement("Python"), requirement("SQL"), requirement("Docker")],
        role_title="Test",
    )
    total = sum(row["total"] for row in analysis.category_breakdown)
    assert total == 3
    for row in analysis.category_breakdown:
        assert row["matched"] + row["partial"] + row["missing"] == row["total"]
        assert 0 <= row["coverage_percent"] <= 100


def test_essential_coverage_is_computed() -> None:
    analysis = analyse_gap(
        ["Python"],
        [
            requirement("Python", essential=True),
            requirement("SQL", essential=True),
            requirement("Figma"),
        ],
        role_title="Test",
    )
    coverage = analysis.essential_coverage
    assert coverage["total"] == 2
    assert coverage["matched"] == 1
    assert coverage["missing"] == 1
    assert "SQL" in coverage["missing_names"]


def test_empty_cv_produces_a_warning_not_a_crash() -> None:
    analysis = analyse_gap([], [requirement("Python")], role_title="Test")
    assert analysis.match_percent == 0.0
    assert analysis.warnings


def test_no_requirements_produces_a_warning() -> None:
    analysis = analyse_gap(["Python"], [], role_title="Test")
    assert analysis.warnings
    assert analysis.comparisons == []


def test_result_never_claims_employability() -> None:
    analysis = analyse_gap(["Python"], [requirement("Python")], role_title="Test")
    payload = analysis.to_dict()
    blob = f"{payload['readiness_label']} {payload['disclaimer']}".lower()
    for forbidden in ("you will get", "guaranteed", "you are qualified", "will be hired", "should be hired"):
        assert forbidden not in blob
    assert "not a prediction" in payload["disclaimer"].lower()


def test_skills_in_text_finds_canonical_skills() -> None:
    found = skills_in_text(
        "I built a REST API with FastAPI and PostgreSQL, deployed with Docker on AWS."
    )
    for expected in ("FastAPI", "PostgreSQL", "Docker", "AWS"):
        assert expected in found


def test_skills_in_text_ignores_short_ambiguous_words() -> None:
    """'go' as an English word must not register the Go language."""
    found = skills_in_text("I will go to the office and see how things are.")
    assert "Go" not in found
    assert "R" not in found


# ===========================================================================
# Module 2 - fusion
# ===========================================================================


def posting(skills: list[str], source: str = "TestBoard") -> JobPosting:
    return JobPosting(
        source=source,
        source_type="json_api",
        title="Test Engineer",
        description="A test advert.",
        skills=skills,
    )


def test_fusion_marks_provenance_correctly() -> None:
    postings = [posting(["Python", "Docker"]), posting(["Python"])]
    llm = {"core_technical_skills": ["Python", "Kubernetes"]}

    skills, _, _ = fuse_skills(postings, llm)
    by_name = {s.canonical: s for s in skills}

    assert by_name["Python"].provenance == "both"
    assert by_name["Kubernetes"].provenance == "llm"
    assert "Docker" not in by_name  # only one advert, no LLM support -> dropped


def test_fusion_keeps_a_skill_corroborated_by_two_adverts() -> None:
    postings = [posting(["Docker"]), posting(["Docker"])]
    skills, _, _ = fuse_skills(postings, {})
    assert [s.canonical for s in skills] == ["Docker"]
    assert skills[0].provenance == "scraped"


def test_fusion_drops_the_uncorroborated_long_tail() -> None:
    """
    Regression test.

    Scanning 24 adverts used to produce 200+ 'requirements', most mentioned by
    a single advert, which made the gap score meaningless.
    """
    postings = [posting([f"Niche Tool {i}"]) for i in range(40)]
    skills, _, filtering = fuse_skills(postings, {})
    assert skills == []
    assert filtering["dropped_uncorroborated"] == 40
    assert filtering["min_posting_support"] >= 2
    assert "independent adverts" in filtering["rule"]


def test_fusion_caps_the_requirement_list() -> None:
    from app.services.jobs.collector import MAX_REQUIREMENTS

    llm = {"core_technical_skills": [f"Skill Number {i}" for i in range(MAX_REQUIREMENTS + 25)]}
    skills, _, filtering = fuse_skills([], llm)
    assert len(skills) <= MAX_REQUIREMENTS
    assert filtering["requirements_kept"] == len(skills)


def test_agreement_outranks_a_single_source() -> None:
    postings = [posting(["Python"]), posting(["Python"]), posting(["Docker"]), posting(["Docker"])]
    llm = {"core_technical_skills": ["Python"]}

    skills, _, _ = fuse_skills(postings, llm)
    by_name = {s.canonical: s for s in skills}
    assert by_name["Python"].importance > by_name["Docker"].importance


def test_fusion_normalises_variants_across_sources() -> None:
    """Adverts say ReactJS, the LLM says React.js -- one requirement."""
    postings = [posting(["ReactJS"]), posting(["react js"])]
    llm = {"core_technical_skills": ["React.js"]}

    skills, evidence, _ = fuse_skills(postings, llm)
    assert [s.canonical for s in skills] == ["React"]
    assert skills[0].provenance == "both"
    assert any(row["canonical"] == "React" and len(row["variants"]) > 1 for row in evidence)


def test_essential_flag_requires_evidence() -> None:
    frequent = [posting(["Python"]) for _ in range(10)]
    skills, _, _ = fuse_skills(frequent, {"desirable_technical_skills": ["Python"]})
    assert skills[0].essential is True  # 100% of adverts asked for it

    rare = [posting(["Figma"]), posting(["Figma"])] + [posting(["Python"]) for _ in range(20)]
    skills, _, _ = fuse_skills(rare, {"desirable_technical_skills": ["Figma"]})
    figma = next(s for s in skills if s.canonical == "Figma")
    assert figma.essential is False  # 2/22 adverts, and only "desirable"


# ===========================================================================
# Module 4 - the invention guards
# ===========================================================================


def test_guard_blocks_an_invented_metric() -> None:
    original = "Worked on improving the checkout page load time"
    result = improve._verify_one(
        original=original,
        item={"improved": "Reduced checkout page load time by 45%, improving conversion", "index": 0},
        cv_skills=[],
        cv_text=original,
        role_title="",
    )
    assert result.accepted is False
    assert result.rejection_reason == improve.REASON_NUMBERS
    assert result.improved == original  # the original is preserved
    assert any(f["type"] == improve.REASON_NUMBERS and f["severity"] == "blocking" for f in result.flags)


def test_guard_allows_a_metric_that_was_already_there() -> None:
    original = "Worked on reducing page load time by 45% on the checkout page"
    result = improve._verify_one(
        original=original,
        item={"improved": "Reduced checkout page load time by 45%", "index": 0},
        cv_skills=[],
        cv_text=original,
        role_title="",
    )
    assert result.accepted is True
    assert "45%" in result.improved


def test_guard_blocks_an_invented_technology() -> None:
    original = "Built internal reporting tools for the operations team"
    result = improve._verify_one(
        original=original,
        item={"improved": "Built internal reporting tools using Kubernetes and Kafka", "index": 0},
        cv_skills=["Python", "SQL"],
        cv_text=original,
        role_title="",
    )
    assert result.accepted is False
    assert result.rejection_reason == improve.REASON_TECH


def test_guard_allows_a_technology_present_elsewhere_in_the_cv() -> None:
    original = "Built internal reporting tools for the operations team"
    result = improve._verify_one(
        original=original,
        item={"improved": "Built internal reporting tools in Python for the operations team", "index": 0},
        cv_skills=["Python", "SQL"],
        cv_text=f"{original}\nSKILLS: Python, SQL",
        role_title="",
    )
    assert result.accepted is True


@pytest.mark.parametrize("verb", ["Led", "Managed", "Owned", "Architected", "Spearheaded"])
def test_guard_blocks_escalated_scope(verb: str) -> None:
    original = "Helped with the migration of the billing service"
    result = improve._verify_one(
        original=original,
        item={"improved": f"{verb} the migration of the billing service", "index": 0},
        cv_skills=[],
        cv_text=original,
        role_title="",
    )
    assert result.accepted is False
    assert result.rejection_reason == improve.REASON_SCOPE


def test_guard_allows_leadership_language_when_the_original_supports_it() -> None:
    original = "Led the migration of the billing service as technical lead"
    result = improve._verify_one(
        original=original,
        item={"improved": "Led the billing service migration as technical lead", "index": 0},
        cv_skills=[],
        cv_text=original,
        role_title="",
    )
    assert result.accepted is True


def test_guard_rejects_an_empty_rewrite() -> None:
    original = "Worked on the API"
    result = improve._verify_one(
        original=original, item={"improved": "", "index": 0}, cv_skills=[], cv_text=original, role_title=""
    )
    assert result.accepted is False
    assert result.rejection_reason == improve.REASON_EMPTY
    assert result.improved == original


def test_guard_rejects_an_absurdly_long_rewrite() -> None:
    original = "Worked on the API"
    result = improve._verify_one(
        original=original,
        item={"improved": "Worked on the API " * 40, "index": 0},
        cv_skills=[],
        cv_text=original,
        role_title="",
    )
    assert result.accepted is False
    assert result.rejection_reason == improve.REASON_TOO_LONG


def test_new_wording_is_a_warning_not_a_rejection() -> None:
    original = "Worked on the shipment tracking API"
    result = improve._verify_one(
        original=original,
        item={
            "improved": "Engineered and delivered a resilient shipment tracking API endpoint",
            "index": 0,
        },
        cv_skills=[],
        cv_text=original,
        role_title="",
    )
    assert result.accepted is True
    assert any(f["severity"] == "warning" for f in result.flags)


def test_weakness_detection_flags_the_usual_suspects() -> None:
    signals = improve.detect_weakness("Responsible for various tasks")
    joined = " ".join(signals)
    assert "weak opening" in joined
    assert "vague quantifiers" in joined
    assert "no measurable detail" in joined


def test_weakness_detection_is_quiet_on_a_strong_bullet() -> None:
    strong = (
        "Reduced median API response time from 420ms to 180ms by adding Redis caching "
        "and eliminating N+1 queries"
    )
    assert len(improve.detect_weakness(strong)) <= 1


def test_bullets_are_ranked_worst_first() -> None:
    ranked = improve.rank_bullets(
        [
            "Reduced API latency from 420ms to 180ms using Redis caching in Python",
            "Responsible for various things",
        ]
    )
    assert ranked[0]["text"].startswith("Responsible for")
    assert ranked[0]["weakness_score"] > ranked[1]["weakness_score"]


def test_improve_rejects_an_empty_request() -> None:
    with pytest.raises(ValidationError):
        improve.improve_bullets([], persist=False)


def test_improve_rejects_too_many_bullets() -> None:
    with pytest.raises(ValidationError) as caught:
        improve.improve_bullets(["bullet point text here"] * 40, persist=False)
    assert "at most" in str(caught.value)


def test_improve_end_to_end_with_the_offline_engine() -> None:
    results, usage, summary = improve.improve_bullets(
        [
            "Responsible for the shipment tracking API used by three teams",
            "Worked on migrating a monolith to services",
        ],
        role_title="Software Engineer",
        persist=False,
    )
    assert len(results) == 2
    assert summary["requested"] == 2
    assert usage is not None
    for result in results:
        # Whatever happens, no rewrite may introduce a number.
        assert not json_guard.unsupported_numbers(result.improved, [result.original])


# ===========================================================================
# json_guard
# ===========================================================================


@pytest.mark.parametrize(
    "payload",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        '```\n{"a": 1}\n```',
        'Here is the JSON you asked for:\n{"a": 1}',
        '{"a": 1,}',
        "{'a': 1}".replace("'", '"'),
        '{\n  "a": 1\n}\nHope that helps!',
        '{"a": 1} trailing commentary',
        '[{"a": 1}]',
    ],
)
def test_json_repair_cascade(payload: str) -> None:
    assert json_guard.parse_json_payload(payload) == {"a": 1}


def test_json_guard_handles_raw_newlines_in_strings() -> None:
    result = json_guard.parse_json_payload('{"text": "line one\nline two"}')
    assert "line one" in result["text"]


def test_json_guard_handles_smart_quotes() -> None:
    result = json_guard.parse_json_payload('{“key”: “value”}')
    assert result == {"key": "value"}


def test_json_guard_handles_nested_braces_in_strings() -> None:
    result = json_guard.parse_json_payload('{"code": "if (x) { y(); }", "n": 2}')
    assert result["n"] == 2


@pytest.mark.parametrize("payload", ["", "   ", "not json at all", "{broken", "null"])
def test_json_guard_raises_on_unusable_output(payload: str) -> None:
    with pytest.raises(LLMOutputError):
        json_guard.parse_json_payload(payload)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (["a", "b"], ["a", "b"]),
        ("a, b", ["a", "b"]),
        ("a; b\nc", ["a", "b", "c"]),
        ([{"name": "a"}, {"skill": "b"}], ["a", "b"]),
        (["a", "a", "A"], ["a"]),
        (None, []),
        ([], []),
        (["", "  ", "a"], ["a"]),
    ],
)
def test_as_str_list_coerces_everything(value: object, expected: list[str]) -> None:
    assert json_guard.as_str_list(value) == expected


def test_as_float_clamps_and_defaults() -> None:
    assert json_guard.as_float("3.5", lo=1, hi=5) == 3.5
    assert json_guard.as_float(99, lo=1, hi=5) == 5
    assert json_guard.as_float(-99, lo=1, hi=5) == 1
    assert json_guard.as_float("not a number", default=2.0) == 2.0
    assert json_guard.as_float(None, default=2.0) == 2.0


def test_as_choice_falls_back_to_the_default() -> None:
    options = ["low", "medium", "high"]
    assert json_guard.as_choice("HIGH", options, default="medium") == "high"
    assert json_guard.as_choice("high priority", options, default="medium") == "high"
    assert json_guard.as_choice("banana", options, default="medium") == "medium"
    assert json_guard.as_choice(None, options, default="medium") == "medium"


def test_unsupported_numbers_detects_invention() -> None:
    assert json_guard.unsupported_numbers("improved by 40%", ["improved the process"]) == ["40", "40%"]
    assert json_guard.unsupported_numbers("improved by 40%", ["improved by 40% last year"]) == []


def test_grounding_filter_splits_supported_from_invented() -> None:
    source = "I used Python and PostgreSQL to build an internal API."
    grounded, rejected = json_guard.enforce_grounding(
        ["Python", "PostgreSQL", "Kubernetes", "Rust"], [source]
    )
    assert set(grounded) == {"Python", "PostgreSQL"}
    assert set(rejected) == {"Kubernetes", "Rust"}


def test_grounding_filter_accepts_an_acronym_backed_by_its_expansion() -> None:
    grounded, _ = json_guard.enforce_grounding(
        ["NLP"], ["Worked on natural language processing and NLP pipelines"]
    )
    assert "NLP" in grounded


# ===========================================================================
# What counts as a candidate's skill
# ===========================================================================


def test_certifications_and_degrees_count_as_skills() -> None:
    """
    Regression test.

    A role requirement is often a qualification. A candidate who holds it
    records it under certifications, not skills -- so a CV that explicitly
    listed "CompTIA Security+" was still being told it was missing.
    """
    from app.services.skills.matcher import candidate_skill_set

    profile = {
        "skills": [{"canonical": "SIEM", "category": tx.CATEGORY_SECURITY}],
        "certifications": [{"name": "CompTIA Security+", "issuer": "CompTIA", "year": "2022"}],
        "education": [{"degree": "BSc (Hons) Cyber Security", "institution": "University of Reading"}],
        "projects": [{"name": "Home lab", "technologies": ["Linux"]}],
    }
    names = {s["canonical"] for s in candidate_skill_set(profile)}

    assert "SIEM" in names
    assert "CompTIA Security+" in names, "a listed certification must satisfy that requirement"
    assert "Bachelor's Degree" in names, "a listed degree must satisfy a degree requirement"
    assert "Linux" in names, "a project technology is evidence of that skill"


def test_a_held_certification_is_not_reported_as_missing() -> None:
    from app.services.skills.matcher import candidate_skill_set

    profile = {
        "skills": [],
        "certifications": [{"name": "CompTIA Security+", "issuer": "CompTIA", "year": "2022"}],
    }
    analysis = analyse_gap(
        candidate_skill_set(profile),
        [requirement("CompTIA Security+", essential=True)],
        role_title="Cybersecurity Analyst",
    )
    assert analysis.comparisons[0].status == MATCHED


def test_candidate_skill_set_does_not_duplicate() -> None:
    from app.services.skills.matcher import candidate_skill_set

    profile = {
        "skills": [{"canonical": "Linux", "category": tx.CATEGORY_CLOUD}],
        "projects": [{"name": "Lab", "technologies": ["Linux", "linux"]}],
    }
    names = [s["canonical"] for s in candidate_skill_set(profile)]
    assert names.count("Linux") == 1


# ===========================================================================
# Anthropic API compatibility
# ===========================================================================


def test_anthropic_request_omits_the_removed_sampling_parameters() -> None:
    """
    Regression test.

    The current Claude API (anthropic-version 2026-10-21, which the installed
    SDK sends by default) rejects `temperature`, `top_p` and `top_k` with a 400
    on every model. Sending one would have broken every request the moment a
    user switched LLM_PROVIDER to anthropic.
    """
    from app.services.llm.client import LLMClient

    client = LLMClient(provider="anthropic", model="claude-sonnet-5-5")
    client._current_task = "scoring"
    kwargs = client._anthropic_kwargs("hello", system="sys", max_tokens=100, temperature=0.65)

    for removed in ("temperature", "top_p", "top_k"):
        assert removed not in kwargs, f"{removed} must not be sent to the Claude API"
    assert kwargs["model"] == "claude-sonnet-5-5"
    assert kwargs["messages"][0]["content"] == "hello"
    assert kwargs["output_config"]["effort"] in ("low", "medium", "high")


def test_latency_critical_task_requests_low_effort() -> None:
    """The interview turn sits on the measured reply-latency path."""
    from app.services.llm.client import LLMClient

    client = LLMClient(provider="anthropic", model="claude-haiku-5-5")
    client._current_task = "interview_turn"
    kwargs = client._anthropic_kwargs("q", system="s", max_tokens=200, temperature=0.65)
    assert kwargs["output_config"]["effort"] == "low"

    client._current_task = "scoring"
    kwargs = client._anthropic_kwargs("q", system="s", max_tokens=200, temperature=0.15)
    assert kwargs["output_config"]["effort"] == "medium"


def test_unsupported_output_config_is_dropped_and_retried() -> None:
    """An older model string in .env must not break every request."""
    from app.services.llm.client import LLMClient

    client = LLMClient(provider="anthropic", model="some-older-model")
    attempts: list[dict] = []

    def fake(**kwargs):
        attempts.append(kwargs)
        if "output_config" in kwargs:
            raise RuntimeError("400 unexpected parameter: output_config")
        return "ok"

    assert client._anthropic_call(fake, {"output_config": {"effort": "low"}, "model": "m"}) == "ok"
    assert len(attempts) == 2
    assert "output_config" not in attempts[1]


def test_unrelated_errors_are_not_swallowed() -> None:
    from app.services.llm.client import LLMClient

    client = LLMClient(provider="anthropic", model="claude-sonnet-5-5")

    def fake(**kwargs):
        raise RuntimeError("401 authentication_error: invalid x-api-key")

    with pytest.raises(RuntimeError, match="authentication_error"):
        client._anthropic_call(fake, {"output_config": {"effort": "low"}})


# ===========================================================================
# Reasoning models on OpenAI-compatible providers (Groq)
# ===========================================================================


def test_groq_reasoning_model_gets_effort_and_token_headroom() -> None:
    """
    Regression test.

    Groq's gpt-oss models emit reasoning tokens BEFORE any visible content, and
    those tokens count against max_tokens. Measured against the live API, a
    request with max_tokens=12 returned finish_reason="length" and empty
    content. The interview turn requests only 320 tokens, so without a floor it
    could return a truncated question or nothing at all.
    """
    from app.services.llm.client import LLMClient

    client = LLMClient(provider="groq", model="openai/gpt-oss-20b")
    client._current_task = "interview_turn"
    kwargs = client._openai_kwargs("q", system="s", temperature=0.65, max_tokens=320)

    assert kwargs["reasoning_effort"] == "low", "the latency path must minimise reasoning"
    assert kwargs["max_tokens"] >= LLMClient.MIN_REASONING_MAX_TOKENS
    assert kwargs["model"] == "openai/gpt-oss-20b"


def test_non_reasoning_models_are_left_alone() -> None:
    """Ollama and plain OpenAI models must not receive reasoning_effort."""
    from app.services.llm.client import LLMClient

    for provider, model in (("ollama", "llama3.2:3b"), ("openai", "gpt-4o-mini")):
        client = LLMClient(provider=provider, model=model)
        client._current_task = "interview_turn"
        kwargs = client._openai_kwargs("q", system="s", temperature=0.65, max_tokens=320)
        assert "reasoning_effort" not in kwargs, f"{provider}/{model} should not get it"
        assert kwargs["max_tokens"] == 320, "max_tokens must not be inflated needlessly"


def test_reasoning_effort_is_dropped_if_rejected() -> None:
    from app.services.llm.client import LLMClient

    client = LLMClient(provider="groq", model="openai/gpt-oss-20b")
    attempts: list[dict] = []

    def fake(**kwargs):
        attempts.append(kwargs)
        if "reasoning_effort" in kwargs:
            raise RuntimeError("400 unrecognized request argument: reasoning_effort")
        return "ok"

    assert client._openai_call(fake, {"reasoning_effort": "low", "model": "m"}) == "ok"
    assert len(attempts) == 2
    assert "reasoning_effort" not in attempts[1]


@pytest.mark.parametrize(
    ("status", "needle"),
    [
        (429, "rate-limited"),
        (401, "rejected the API key"),
        (404, "not available on"),
    ],
)
def test_provider_failures_explain_themselves(status: int, needle: str) -> None:
    """A free-tier user must be told what to do, not shown a raw SDK error."""
    from app.services.llm.client import LLMClient

    client = LLMClient(provider="groq", model="openai/gpt-oss-120b")
    exc = RuntimeError("provider said no")
    setattr(exc, "status_code", status)
    assert needle in client._explain_failure(exc)


def test_rate_limit_message_names_a_way_out() -> None:
    from app.services.llm.client import LLMClient

    client = LLMClient(provider="groq", model="openai/gpt-oss-120b")
    exc = RuntimeError("Rate limit reached for model")
    message = client._explain_failure(exc)
    assert "ollama" in message.lower(), "should offer the unlimited local fallback"


def test_retries_are_configured_for_free_tiers() -> None:
    from app.core.config import settings

    assert settings.llm_max_retries >= 4, (
        "a free tier capped at 8,000 tokens per minute needs more than the SDK default of 2"
    )


# --- QA regression (found with a real local LLM) ------------------------------

import pytest as _pytest


@_pytest.mark.parametrize(
    "original, rewrite, rejected",
    [
        ("Responsible for the shipment tracking API used by three internal teams",
         "Led the shipment tracking API, used by three internal teams", True),
        ("Responsible for the shipment tracking API used by three internal teams",
         "Owned the shipment tracking API used by three internal teams", False),
        ("Worked on reducing overhead in the build", "Headed an effort to reduce build overhead", True),
        ("Team lead for a team of 4", "Led a team of four engineers", False),
        ("Mentored two junior engineers", "Mentored two junior engineers through onboarding", False),
    ],
)
def test_people_leadership_verbs_need_people_leadership_evidence(original, rewrite, rejected) -> None:
    from app.services.improve.bullets import _escalated_scope

    assert bool(_escalated_scope(original, rewrite)) is rejected


@_pytest.mark.parametrize(
    "requirement, cv_skill",
    [("AWS Certification", "Scrum Certification"), ("Google Analytics", "Google Cloud"),
     ("Unit Testing", "Integration Testing")],
)
def test_a_shared_generic_word_does_not_make_skills_similar(requirement, cv_skill) -> None:
    from app.services.skills.matcher import PARTIAL_FUZZY_THRESHOLD, _closest_cv_skill

    _, score = _closest_cv_skill(requirement, [cv_skill])
    assert score < PARTIAL_FUZZY_THRESHOLD


@_pytest.mark.parametrize(
    "original, rewrite, invented",
    [
        ("Worked on migrating a monolithic Django application to a set of FastAPI services",
         "Transformed a monolithic Django application into FastAPI services for improved scalability.", True),
        ("Fixed defects reported by QA against the customer portal",
         "Ensured the customer portal's reliability by resolving defects reported by QA.", True),
        ("Fixed defects reported by QA against the customer portal",
         "Resolved QA-reported defects in the customer portal", False),
        ("Helped speed up the API with Redis caching", "Reduced API response time with Redis caching", False),
    ],
)
def test_rewrites_may_not_invent_outcomes(original, rewrite, invented) -> None:
    from app.services.improve.bullets import _invented_outcomes

    cv = "Reduced median API response time from 420ms to 180ms by adding Redis caching"
    assert bool(_invented_outcomes(original, rewrite, cv)) is invented
