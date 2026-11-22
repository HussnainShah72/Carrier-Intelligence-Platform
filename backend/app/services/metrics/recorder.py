"""
Module 7 - performance measurement and reporting.

The assignment asks specifically for "the time from the end of the candidate's
speech to the start of the interviewer's reply", plus per-stage timings.  Every
number here comes from `time.perf_counter()` readings taken in the real request
path -- nothing is estimated, modelled or back-filled.

What each metric means (the same wording is used in the UI and the report)
-------------------------------------------------------------------------
stt_ms                local Whisper transcription time for that answer
llm_ttft_ms           end of speech -> first text token of the reply
llm_total_ms          full LLM generation time for the reply
tts_first_ms          Piper synthesis time for the FIRST sentence only
tts_total_ms          Piper synthesis time summed over all sentences
e2e_first_audio_ms    END OF SPEECH -> FIRST AUDIO BYTE READY  <-- headline
total_ms              end of speech -> whole turn complete
speech_end_to_server_ms  browser-detected end of speech -> audio received by the server
                      (recording finalisation + upload; same machine, same clock)
e2e_from_speech_end_ms   browser-detected end of speech -> first audio byte ready
                      (= speech_end_to_server_ms + e2e_first_audio_ms)
audio_seconds         duration of the candidate's recording

Aggregates report the median and p90 as well as the mean, because a mean alone
hides the tail that users actually notice.
"""

from __future__ import annotations

from statistics import mean, median
from typing import Any, Sequence

from app.core.db import execute, new_id, query_all, utcnow
from app.core.logging_setup import get_logger

log = get_logger(__name__)

METRIC_FIELDS = (
    "stt_ms",
    "llm_ttft_ms",
    "llm_total_ms",
    "tts_first_ms",
    "tts_total_ms",
    "e2e_first_audio_ms",
    "total_ms",
    "speech_end_to_server_ms",
    "e2e_from_speech_end_ms",
)

METRIC_LABELS = {
    "stt_ms": "Speech recognition (local Whisper)",
    "llm_ttft_ms": "End of speech to first text token",
    "llm_total_ms": "LLM generation time (from LLM start)",
    "tts_first_ms": "First sentence synthesis (local Piper)",
    "tts_total_ms": "Speech synthesis (total)",
    "e2e_first_audio_ms": "End of speech to first audio (headline)",
    "total_ms": "End of speech to turn complete",
    "speech_end_to_server_ms": "Browser end of speech to server receipt (upload)",
    "e2e_from_speech_end_ms": "Browser end of speech to first audio",
}

HEADLINE_METRIC = "e2e_first_audio_ms"

# A single interview turn cannot legitimately take longer than this: the LLM
# timeout is 90 s and every stage runs inside one request. A larger value is not
# a slow turn, it is a broken measurement -- for example a reference timestamp
# that did not come from this process. Storing it would silently corrupt every
# mean in the performance report, so such values are dropped and counted.
IMPLAUSIBLE_MS = 180_000.0

_rejected_samples = 0


def _sane(value: Any) -> float | None:
    """Return a plausible millisecond reading, or None."""
    global _rejected_samples
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number < 0 or number > IMPLAUSIBLE_MS:
        if number == number and (number < 0 or number > IMPLAUSIBLE_MS):
            _rejected_samples += 1
            log.warning(
                "Discarding an implausible latency reading of %.0f ms (limit %.0f ms). "
                "This usually means the reference timestamp did not come from this process.",
                number, IMPLAUSIBLE_MS,
            )
        return None
    return number


def rejected_sample_count() -> int:
    return _rejected_samples


def record_turn(
    *,
    interview_id: str,
    turn_index: int,
    role_title: str,
    timings: Any,
    mode: str = "voice",
) -> None:
    """Persist one turn's timings.  Never raises into the request path."""
    payload = timings.to_dict() if hasattr(timings, "to_dict") else dict(timings or {})
    try:
        execute(
            "INSERT INTO latency_events(id, interview_id, turn_index, role_title, stt_ms, llm_total_ms, "
            "llm_ttft_ms, tts_first_ms, tts_total_ms, e2e_first_audio_ms, total_ms, audio_seconds, "
            "chars_out, stt_engine, tts_engine, llm_provider, llm_model, mode, created_at, "
            "speech_end_to_server_ms, e2e_from_speech_end_ms) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                new_id("lat"), interview_id, turn_index, role_title,
                _sane(payload.get("stt_ms")), _sane(payload.get("llm_total_ms")),
                _sane(payload.get("llm_ttft_ms")),
                _sane(payload.get("tts_first_ms")), _sane(payload.get("tts_total_ms")),
                _sane(payload.get("e2e_first_audio_ms")), _sane(payload.get("total_ms")),
                payload.get("audio_seconds"), payload.get("chars_out") or 0,
                payload.get("stt_engine") or "", payload.get("tts_engine") or "",
                payload.get("llm_provider") or "", payload.get("llm_model") or "",
                mode, utcnow(),
                _sane(payload.get("speech_end_to_server_ms")), _sane(payload.get("e2e_from_speech_end_ms")),
            ),
        )
    except Exception as exc:  # pragma: no cover - metrics must never break a turn
        log.error("Could not record latency metrics for %s turn %s: %s", interview_id, turn_index, exc)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _percentile(values: Sequence[float], fraction: float) -> float:
    """Nearest-rank percentile (no interpolation, so small n stays honest)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1)))))
    return float(ordered[index])


def summarise(values: Sequence[float | None]) -> dict[str, Any]:
    # Filter again on read, so any implausible row stored before the guard
    # existed cannot distort a published mean.
    clean = [v for v in (_sane(value) for value in values) if v is not None]
    if not clean:
        return {"samples": 0, "mean_ms": None, "median_ms": None, "p90_ms": None,
                "min_ms": None, "max_ms": None}
    return {
        "samples": len(clean),
        "mean_ms": round(mean(clean), 1),
        "median_ms": round(median(clean), 1),
        "p90_ms": round(_percentile(clean, 0.90), 1),
        "min_ms": round(min(clean), 1),
        "max_ms": round(max(clean), 1),
    }


def _rows(where: str = "", params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    sql = "SELECT * FROM latency_events"
    if where:
        sql += f" WHERE {where}"
    sql += " ORDER BY created_at DESC"
    return [dict(r) for r in query_all(sql, params)]


def interview_metrics(interview_id: str) -> dict[str, Any]:
    """Per-turn and aggregate timings for one interview (Results page)."""
    rows = _rows("interview_id = ?", (interview_id,))
    rows.sort(key=lambda r: r["turn_index"])

    return {
        "interview_id": interview_id,
        "turns": [
            {
                "turn_index": r["turn_index"],
                **{field: r[field] for field in METRIC_FIELDS},
                "audio_seconds": r["audio_seconds"],
                "chars_out": r["chars_out"],
                "stt_engine": r["stt_engine"],
                "tts_engine": r["tts_engine"],
                "llm_provider": r["llm_provider"],
                "llm_model": r["llm_model"],
                "mode": r["mode"],
            }
            for r in rows
        ],
        "aggregates": {field: summarise([r[field] for r in rows]) for field in METRIC_FIELDS},
        "engines": _engines_used(rows),
        "metric_labels": METRIC_LABELS,
        "headline_metric": HEADLINE_METRIC,
        "voice_turns": sum(1 for r in rows if r["mode"] == "voice"),
        "text_turns": sum(1 for r in rows if r["mode"] != "voice"),
    }


def global_metrics(*, voice_only: bool = False) -> dict[str, Any]:
    """Everything measured so far, overall and broken down by role."""
    rows = _rows("mode = 'voice'" if voice_only else "")

    by_role: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_role.setdefault(row["role_title"] or "(unspecified)", []).append(row)

    roles = []
    for role, role_rows in sorted(by_role.items(), key=lambda kv: -len(kv[1])):
        interviews = {r["interview_id"] for r in role_rows}
        roles.append(
            {
                "role_title": role,
                "turns": len(role_rows),
                "interviews": len(interviews),
                "aggregates": {field: summarise([r[field] for r in role_rows]) for field in METRIC_FIELDS},
            }
        )

    return {
        "total_turns": len(rows),
        "total_interviews": len({r["interview_id"] for r in rows}),
        "roles_tested": len(by_role),
        "aggregates": {field: summarise([r[field] for r in rows]) for field in METRIC_FIELDS},
        "by_role": roles,
        "engines": _engines_used(rows),
        "metric_labels": METRIC_LABELS,
        "headline_metric": HEADLINE_METRIC,
        "meets_three_role_requirement": len(by_role) >= 3,
        "notes": [
            "All timings are measured with time.perf_counter() inside the real request path.",
            "The reference point for every end-to-end figure is the moment the candidate's audio "
            "reached the server, i.e. the end of their speech.",
            "Speech recognition and speech synthesis both run locally on this machine; no audio "
            "is sent to any external service.",
        ],
    }


def _engines_used(rows: Sequence[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "stt": sorted({r["stt_engine"] for r in rows if r["stt_engine"]}),
        "tts": sorted({r["tts_engine"] for r in rows if r["tts_engine"]}),
        "llm_providers": sorted({r["llm_provider"] for r in rows if r["llm_provider"]}),
        "llm_models": sorted({r["llm_model"] for r in rows if r["llm_model"]}),
    }


def latency_timeline(limit: int = 60) -> list[dict[str, Any]]:
    """Chronological series for the performance dashboard chart."""
    rows = _rows()[:limit]
    rows.reverse()
    return [
        {
            "index": i + 1,
            "role_title": r["role_title"],
            "e2e_first_audio_ms": r["e2e_first_audio_ms"],
            "llm_ttft_ms": r["llm_ttft_ms"],
            "stt_ms": r["stt_ms"],
            "tts_first_ms": r["tts_first_ms"],
            "total_ms": r["total_ms"],
            "created_at": r["created_at"],
        }
        for i, r in enumerate(rows)
    ]


def stage_breakdown() -> list[dict[str, Any]]:
    """Mean contribution of each pipeline stage -- the stacked bar in the UI."""
    rows = _rows()
    if not rows:
        return []

    def avg(field: str) -> float:
        values = [float(r[field]) for r in rows if r[field] is not None]
        return round(mean(values), 1) if values else 0.0

    stt = avg("stt_ms")
    ttft = avg("llm_ttft_ms")
    tts_first = avg("tts_first_ms")

    # llm_ttft is measured from end of speech, so the LLM's own share is
    # whatever is left after transcription.
    llm_share = max(0.0, round(ttft - stt, 1))
    return [
        {"stage": "Speech recognition (local)", "mean_ms": stt},
        {"stage": "LLM first token", "mean_ms": llm_share},
        {"stage": "First sentence TTS (local)", "mean_ms": tts_first},
    ]


def export_payload() -> dict[str, Any]:
    """Full, self-describing metrics export (downloaded as JSON from the UI)."""
    rows = _rows()
    return {
        "generated_at": utcnow(),
        "metric_definitions": {
            field: {
                "label": METRIC_LABELS[field],
                "unit": "milliseconds",
                "measured_from": "end of candidate speech (server receipt of audio)"
                if field in ("llm_ttft_ms", "e2e_first_audio_ms", "total_ms")
                else "end of candidate speech as detected in the browser"
                if field in ("speech_end_to_server_ms", "e2e_from_speech_end_ms")
                else "start of that pipeline stage",
            }
            for field in METRIC_FIELDS
        },
        "summary": global_metrics(),
        "events": rows,
    }


def clear_metrics() -> int:
    cursor = execute("DELETE FROM latency_events")
    count = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
    log.info("Cleared %d latency event(s)", count)
    return count
