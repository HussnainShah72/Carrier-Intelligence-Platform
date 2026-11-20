"""API routes for Module 7 - the performance report."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from app.core.logging_setup import get_logger
from app.services.metrics import recorder as metrics

log = get_logger(__name__)
router = APIRouter(prefix="/metrics", tags=["Performance"])


@router.get("")
def overview(voice_only: bool = False) -> dict[str, Any]:
    """Aggregate latency across every interview, overall and per role."""
    return {
        "summary": metrics.global_metrics(voice_only=voice_only),
        "timeline": metrics.latency_timeline(),
        "stage_breakdown": metrics.stage_breakdown(),
    }


@router.get("/interview/{interview_id}")
def for_interview(interview_id: str) -> dict[str, Any]:
    return metrics.interview_metrics(interview_id)


@router.get("/export")
def export() -> Response:
    """Download the full, self-describing metrics export as JSON."""
    payload = metrics.export_payload()
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="performance_metrics.json"'},
    )


@router.get("/export.csv")
def export_csv() -> Response:
    """Download per-turn timings as CSV, for the report's evaluation tables."""
    payload = metrics.export_payload()
    events = payload["summary"]
    rows = metrics.latency_timeline(limit=10_000)

    columns = ["index", "role_title", "stt_ms", "llm_ttft_ms", "tts_first_ms",
               "e2e_first_audio_ms", "total_ms", "created_at"]
    lines = [",".join(columns)]
    for row in rows:
        values = []
        for column in columns:
            value = row.get(column)
            if value is None:
                values.append("")
            elif isinstance(value, str):
                values.append('"' + value.replace('"', '""') + '"')
            else:
                values.append(str(value))
        lines.append(",".join(values))

    del events
    return Response(
        content="\n".join(lines) + "\n",
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="performance_metrics.csv"'},
    )


@router.delete("")
def clear() -> dict[str, Any]:
    return {"cleared": metrics.clear_metrics()}
