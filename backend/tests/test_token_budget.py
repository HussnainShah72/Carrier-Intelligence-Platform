"""
How large is one interview-turn request?

The provider trade-off reported in the project documentation rests on a
quantity: how many tokens one live interview turn costs. Groq's free tier
allows 8,000 tokens per minute (measured from its own
`x-ratelimit-limit-tokens` header), so the turn cost determines whether a
sustained interview fits inside the free tier or is throttled.

This measures the prompt the engine actually builds -- system prompt, role
context, CV context and the replayed conversation history -- at a realistic
history depth, with no API call and no network. It is a measurement, not an
estimate, of the input side; it is reported in characters and converted at the
widely used ~4 characters/token approximation, which is adequate for a
rate-limit argument that turns on thousands of tokens, not tens.
"""

from __future__ import annotations

import json
from pathlib import Path

RESULT_PATH = Path(__file__).resolve().parents[2] / "evaluation" / "results" / "token_budget.json"

#: Average characters per token for English prose on modern BPE vocabularies.
CHARS_PER_TOKEN = 4.0


def test_interview_turn_prompt_size_is_recorded(client, cv_and_role) -> None:
    from app.services.interview import engine as engine_mod
    from app.services.llm.client import LLMClient

    cv, role = cv_and_role
    start = client.post(
        "/api/interview/start",
        json={
            "role_title": "Software Engineer", "difficulty": "medium", "mode": "text",
            "cv_id": cv["cv_id"], "role_analysis_id": role["role_analysis_id"],
        },
    ).json()
    interview_id = start["interview"]["id"]

    captured: list[dict[str, int]] = []
    real_stream = LLMClient.stream

    def measuring_stream(self, prompt, *, system="", **kwargs):
        captured.append({
            "turn": len(captured) + 1,
            "system_chars": len(system),
            "user_chars": len(prompt),
            "total_chars": len(system) + len(prompt),
            "max_tokens_requested": int(kwargs.get("max_tokens") or 0),
        })
        yield from real_stream(self, prompt, system=system, **kwargs)

    LLMClient.stream = measuring_stream  # type: ignore[assignment]
    try:
        answers = [
            "I built the ingestion service that moved about forty thousand records an hour.",
            "I added a Redis cache with a sixty second TTL and watched the p99 drop.",
            "We ran it behind a feature flag for two weeks before turning it on fully.",
            "I profiled it with cProfile and found the serialiser was the bottleneck.",
            "I wrote the integration tests against the legacy Django endpoints first.",
            "We set the coverage gate at eighty five percent and it is enforced in CI.",
        ]
        for answer in answers:
            with client.stream(
                "POST", f"/api/interview/{interview_id}/turn",
                json={"text": answer, "speak": False},
            ) as response:
                response.read()
    finally:
        LLMClient.stream = real_stream  # type: ignore[assignment]

    assert captured, "no turn prompts were observed"

    totals = [c["total_chars"] for c in captured]
    # The history is replayed each turn, so later turns cost more than earlier
    # ones.  That growth is the whole reason the free tier runs out.
    assert totals[-1] > totals[0], "prompt should grow as history accumulates"

    record = {
        "note": (
            "Input prompt sizes for one live interview turn, measured by "
            "instrumenting LLMClient.stream during a real text-mode interview "
            "against the deterministic offline engine. No API calls were made. "
            "Token figures use the ~4 characters/token approximation."
        ),
        "chars_per_token_assumed": CHARS_PER_TOKEN,
        "turns": captured,
        "input_chars": {
            "first_turn": totals[0],
            "last_turn": totals[-1],
            "mean": round(sum(totals) / len(totals), 1),
        },
        "approx_input_tokens": {
            "first_turn": round(totals[0] / CHARS_PER_TOKEN),
            "last_turn": round(totals[-1] / CHARS_PER_TOKEN),
            "mean": round(sum(totals) / len(totals) / CHARS_PER_TOKEN),
        },
        "max_output_tokens_requested": captured[0]["max_tokens_requested"],
        "groq_free_tier_tokens_per_minute": 8000,
    }
    # On Groq the output ceiling is not the 320 the engine asks for. The
    # gpt-oss models emit reasoning tokens before any visible content, and
    # those count against max_tokens, so the client raises the ceiling to
    # MIN_REASONING_MAX_TOKENS. The worst-case per-turn cost uses that.
    groq_output_ceiling = max(
        captured[0]["max_tokens_requested"], LLMClient.MIN_REASONING_MAX_TOKENS
    )
    record["groq_output_ceiling_tokens"] = groq_output_ceiling
    record["groq_output_ceiling_note"] = (
        "Raised from the requested max_tokens because gpt-oss reasoning tokens "
        "count against it; see LLMClient.MIN_REASONING_MAX_TOKENS."
    )

    mean_total = record["approx_input_tokens"]["mean"] + groq_output_ceiling
    record["approx_total_tokens_per_turn"] = mean_total
    turns_per_minute = 8000 / mean_total
    record["sustainable_turns_per_minute_on_groq_free_tier"] = round(turns_per_minute, 2)
    record["seconds_between_turns_to_stay_under_the_cap"] = round(60 / turns_per_minute, 1)
    record["caveat"] = (
        "This is a worst case: max_tokens is a ceiling, not a charge, so a turn "
        "whose reply is short costs less. It is the right figure for deciding "
        "whether a back-to-back run will be throttled, which it was: a measured "
        "16-turn run on the free tier returned 21 HTTP 429s and the retry "
        "backoff stretched one first-token time to 18 seconds."
    )

    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")

    print("\n" + json.dumps({k: record[k] for k in (
        "input_chars", "approx_input_tokens", "max_output_tokens_requested",
        "approx_total_tokens_per_turn", "sustainable_turns_per_minute_on_groq_free_tier",
        "seconds_between_turns_to_stay_under_the_cap")}, indent=2))
