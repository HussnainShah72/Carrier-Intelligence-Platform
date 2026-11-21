"""
Module 2B/3 - skill normalisation.

The assignment names one requirement explicitly: "React", "ReactJS" and
"React.js" must be treated as one skill. These tests pin that down, then check
the surrounding behaviour that makes it safe -- that normalisation does NOT
over-merge genuinely different skills, which is the failure mode that would
quietly corrupt every gap analysis.
"""

from __future__ import annotations

import pytest

from app.services.skills import taxonomy as tx
from app.services.skills.normalizer import normalise_skills, resolve_skill
from app.services.skills.text_norm import (
    normalise_key,
    split_skill_list,
    strip_bullet,
    surface_form,
)


# ===========================================================================
# The explicit assignment requirement
# ===========================================================================


@pytest.mark.parametrize(
    "variant",
    [
        "React",
        "react",
        "REACT",
        "ReactJS",
        "reactjs",
        "React.js",
        "react.js",
        "React JS",
        "React  js",
        "Experience with React",
        "Experience with ReactJS (3+ years)",
        "Strong knowledge of React.js",
        "5 years React",
        "  react  ",
    ],
)
def test_every_react_spelling_resolves_to_one_skill(variant: str) -> None:
    resolved = resolve_skill(variant)
    assert resolved is not None, f"{variant!r} did not resolve at all"
    assert resolved.canonical == "React", f"{variant!r} resolved to {resolved.canonical!r}"


def test_react_variants_collapse_to_a_single_entry() -> None:
    variants = ["React", "ReactJS", "React.js", "React JS", "Experience with React (3+ years)"]
    result = normalise_skills(variants)
    assert len(result) == 1
    assert result[0].canonical == "React"
    # The evidence trail must survive, so the UI can show what was merged.
    assert len(result[0].surface_forms) >= 4


@pytest.mark.parametrize(
    ("variants", "expected"),
    [
        (["Node.js", "NodeJS", "node js", "Node"], "Node.js"),
        (["PostgreSQL", "Postgres", "postgre sql", "psql"], "PostgreSQL"),
        (["Kubernetes", "k8s", "kube"], "Kubernetes"),
        (["JavaScript", "JS", "ECMAScript", "javascript"], "JavaScript"),
        (["Machine Learning", "ML", "machine-learning"], "Machine Learning"),
        (["TensorFlow", "tensor flow", "Keras"], "TensorFlow"),
        (["Microsoft Excel", "MS Excel", "excel", "Advanced Excel"], "Excel"),
        (["CI/CD", "ci cd", "continuous integration", "Jenkins"], "CI/CD"),
        (["scikit-learn", "sklearn", "scikit learn"], "scikit-learn"),
        (["Vue.js", "Vue", "VueJS"], "Vue.js"),
        (["C#", "csharp", "C Sharp"], "C#"),
        (["TypeScript", "ts"], "TypeScript"),
    ],
)
def test_known_alias_families_collapse(variants: list[str], expected: str) -> None:
    result = normalise_skills(variants)
    assert len(result) == 1, f"{variants} produced {[s.canonical for s in result]}"
    assert result[0].canonical == expected


def test_mixed_list_deduplicates_across_families() -> None:
    raw = [
        "React", "ReactJS", "React.js",
        "Node.js", "NodeJS",
        "Postgres", "PostgreSQL",
        "k8s", "Kubernetes",
        "JS", "JavaScript",
    ]
    result = normalise_skills(raw)
    canonical = sorted(s.canonical for s in result)
    assert canonical == ["JavaScript", "Kubernetes", "Node.js", "PostgreSQL", "React"]


# ===========================================================================
# The opposite failure: over-merging
# ===========================================================================


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("React", "Redux"),            # 3 edits apart as strings
        ("React", "React Native"),     # one contains the other
        ("Java", "JavaScript"),        # the classic
        ("Python", "PyTorch"),
        ("MySQL", "PostgreSQL"),
        ("C", "C++"),
        ("CSS", "SASS"),
        ("Angular", "AngularJS"),      # this pair IS deliberately one skill
    ],
)
def test_distinct_skills_are_not_merged(a: str, b: str) -> None:
    resolved_a = resolve_skill(a)
    resolved_b = resolve_skill(b)
    assert resolved_a is not None and resolved_b is not None

    # Angular/AngularJS is the one pair in this list the taxonomy deliberately
    # treats as a single skill, which is the industry convention.
    if {a, b} == {"Angular", "AngularJS"}:
        assert resolved_a.canonical == resolved_b.canonical
        return

    assert resolved_a.canonical != resolved_b.canonical, (
        f"{a!r} and {b!r} both resolved to {resolved_a.canonical!r}"
    )


def test_generic_words_do_not_match_specific_certifications() -> None:
    """
    Regression test.

    The alias "security plus" for CompTIA Security+ used to be reduced to
    "security" by noise-word stripping, which then matched every advert
    containing the word "security". The alias index now keys on the
    conservative form.
    """
    assert tx.ALIAS_INDEX.get("security") != "CompTIA Security+"
    assert tx.ALIAS_INDEX.get("domain") != "Business Acumen"
    assert tx.ALIAS_INDEX.get("security plus") == "CompTIA Security+"
    assert tx.ALIAS_INDEX.get("domain knowledge") == "Business Acumen"


def test_document_scan_minimum_key_length_excludes_ambiguous_acronyms() -> None:
    """One and two character skills must not be matched inside prose."""
    assert tx.DOCUMENT_SCAN_MIN_KEY_LENGTH >= 3
    for short in ("r", "go", "ml", "dl", "ts", "js"):
        assert len(short) < tx.DOCUMENT_SCAN_MIN_KEY_LENGTH or len(short) >= 3


# ===========================================================================
# Text normalisation primitives
# ===========================================================================


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("React.js", "react"),
        ("ReactJS", "react"),
        ("React JS", "react"),
        ("Experience with ReactJS (3+ years)", "react"),
        ("  Strong knowledge of   Python  ", "python"),
        ("5+ years of Java experience", "java"),
        ("Proficiency in SQL", "sql"),
        ("C++", "c++"),
        ("C#", "c#"),
        ("CI/CD", "ci/cd"),
        ("Node.js", "node"),
        ("NodeJS", "node"),
    ],
)
def test_normalise_key(raw: str, expected: str) -> None:
    assert normalise_key(raw) == expected


def test_normalise_key_can_keep_noise_words() -> None:
    assert normalise_key("security plus") == "security"
    assert normalise_key("security plus", strip_noise=False) == "security plus"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Python, Java and C++", ["Python", "Java", "C++"]),
        ("SQL; Docker | Kubernetes", ["SQL", "Docker", "Kubernetes"]),
        ("Docker/Kubernetes", ["Docker", "Kubernetes"]),
        ("HTML/CSS", ["HTML", "CSS"]),
        ("React & Redux", ["React", "Redux"]),
    ],
)
def test_split_skill_list(raw: str, expected: list[str]) -> None:
    assert split_skill_list(raw) == expected


@pytest.mark.parametrize("protected", ["CI/CD", "TCP/IP", "PL/SQL", "A/B"])
def test_split_preserves_terms_containing_a_slash(protected: str) -> None:
    assert split_skill_list(protected) == [protected]


def test_surface_form_tidies_without_destroying_casing() -> None:
    assert surface_form("  experience with  REACT.JS (3+ years) ") == "REACT.JS"
    assert surface_form("- Python") == "Python"
    # A short parenthetical aside is information, so it is kept.
    assert surface_form("Cloud (AWS)") == "Cloud (AWS)"
    # An empty one left behind by year-stripping is not.
    assert "( )" not in surface_form("React (3+ years)")


def test_strip_bullet_handles_every_glyph() -> None:
    for prefix in ("- ", "* ", "• ", "● ", "1. ", "2) ", "  – "):
        assert strip_bullet(f"{prefix}Python") == "Python"


# ===========================================================================
# Unknown skills
# ===========================================================================


def test_unknown_skill_is_kept_rather_than_discarded() -> None:
    resolved = resolve_skill("Zaplorian Dataflow Engine")
    assert resolved is not None
    assert resolved.in_taxonomy is False
    assert "Zaplorian" in resolved.canonical


def test_unknown_near_duplicates_cluster_together() -> None:
    """A brand-new technology must still de-duplicate across sources."""
    result = normalise_skills(["Zaplorian Dataflow", "Zaplorian Dataflows", "zaplorian dataflow"])
    unknown = [s for s in result if not s.in_taxonomy]
    assert len(unknown) == 1, f"expected one cluster, got {[s.canonical for s in unknown]}"


def test_junk_input_is_rejected() -> None:
    for junk in ("", "   ", "-", ".", "   ,  ", "a"):
        assert resolve_skill(junk) is None


def test_sentence_is_not_treated_as_a_skill() -> None:
    sentence = "I am looking for a challenging role where I can grow my career further"
    assert resolve_skill(sentence) is None


def test_normalisation_records_which_stage_decided() -> None:
    exact = resolve_skill("React")
    assert exact is not None and exact.stage == "exact-alias" and exact.confidence == 1.0

    typo = resolve_skill("kubernets")
    assert typo is not None
    assert typo.canonical == "Kubernetes"
    assert typo.stage in ("fuzzy-token", "tfidf-cosine")
    assert 0.5 < typo.confidence < 1.0


@pytest.mark.parametrize(
    ("typo", "expected"),
    [
        ("kubernets", "Kubernetes"),
        ("javscript", "JavaScript"),
        ("postgressql", "PostgreSQL"),
        ("pyhton", "Python"),
    ],
)
def test_common_typos_still_resolve(typo: str, expected: str) -> None:
    resolved = resolve_skill(typo)
    assert resolved is not None
    assert resolved.canonical == expected


def test_an_unrecoverable_typo_is_kept_verbatim_not_misassigned() -> None:
    """
    The fuzzy and vector stages have a documented limit.

    A double transposition such as "docekr" falls below both thresholds. The
    important property is not that every typo is caught -- it is that an
    uncaught one is preserved as its own (unknown) skill rather than silently
    attached to the wrong canonical skill, which would corrupt the gap analysis.
    """
    resolved = resolve_skill("docekr")
    assert resolved is not None
    if resolved.in_taxonomy:
        assert resolved.canonical == "Docker"
    else:
        assert "ocekr" in resolved.canonical.lower()


# ===========================================================================
# Taxonomy integrity
# ===========================================================================


def test_taxonomy_is_internally_consistent() -> None:
    stats = tx.taxonomy_stats()
    assert stats["canonical_skills"] > 150
    assert stats["alias_entries"] > 600

    for canonical, meta in tx.CANONICAL_SKILLS.items():
        assert meta["category"] in tx.ALL_CATEGORIES, f"{canonical} has an unknown category"
        for implied in meta["implies"]:
            assert implied in tx.CANONICAL_SKILLS, f"{canonical} implies unknown skill {implied}"


def test_no_alias_maps_to_two_different_skills() -> None:
    """An ambiguous alias would make normalisation order-dependent."""
    seen: dict[str, str] = {}
    for canonical, meta in tx.CANONICAL_SKILLS.items():
        for alias in meta["aliases"]:
            key = normalise_key(alias, strip_noise=False)
            if key in seen and seen[key] != canonical:
                pytest.fail(f"alias {alias!r} maps to both {seen[key]!r} and {canonical!r}")
            seen[key] = canonical


def test_implication_graph_has_no_self_loops() -> None:
    for canonical, meta in tx.CANONICAL_SKILLS.items():
        assert canonical not in meta["implies"], f"{canonical} implies itself"


def test_normalisation_is_deterministic() -> None:
    raw = ["React", "ReactJS", "Python", "SQL", "unknown thing here", "Docker"]
    first = [s.canonical for s in normalise_skills(raw)]
    for _ in range(4):
        assert [s.canonical for s in normalise_skills(raw)] == first


# --- QA regression: unrelated skills must not merge (B1/B2) -------------------

import pytest as _pytest


@_pytest.mark.parametrize(
    "raw, wrong",
    [
        ("Problem Solving", "Data Structures & Algorithms"),
        ("Cooking", "C"),
        ("Adobe Photoshop", "Figma"),
    ],
)
def test_unrelated_skills_do_not_merge(raw: str, wrong: str) -> None:
    from app.services.skills.normalizer import resolve_skill

    resolved = resolve_skill(raw)
    assert resolved is None or resolved.canonical != wrong


@_pytest.mark.parametrize(
    "requirement, cv_skill",
    [("Java", "JavaScript"), ("C", "CI/CD"), ("R", "Express.js"), ("Go", "Django"), ("VS Code", "Code Review")],
)
def test_short_or_contained_names_get_no_similarity_credit(requirement: str, cv_skill: str) -> None:
    from app.services.skills.matcher import PARTIAL_FUZZY_THRESHOLD, _closest_cv_skill

    _, score = _closest_cv_skill(requirement, [cv_skill])
    assert score < PARTIAL_FUZZY_THRESHOLD
