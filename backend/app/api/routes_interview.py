"""
API routes for Module 5 (voice interview) and Module 6 (scoring).

The voice turn is the latency-critical path, so it is a Server-Sent Events
stream rather than a request/response: text deltas and audio chunks reach the
browser as they are produced, and the browser starts playing the first sentence
while the rest of the reply is still being generated.

The clock that matters starts the moment the uploaded audio has been read in
`voice_turn()` -- that is the end of the candidate's speech as far as the server
can observe it, and it is passed down as `speech_ended_at` so every reported
latency is measured from the same, real reference point.
"""

from __future__ import annotations

import json
import time
from typing import Any, Iterator

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import Response, StreamingResponse

from app.core.config import settings
from app.core.db import loads, log_activity, query_one
from app.core.errors import AppError, SpeechError, ValidationError
from app.core.logging_setup import get_logger
from app.schemas.models import InterviewTurnRequest, SpeakRequest, StartInterviewRequest
from app.services.interview import engine, rubric, scorer, stages
from app.services.jobs.collector import requirements_from_dict
from app.services.metrics import recorder as metrics
from app.services.speech import stt, tts

log = get_logger(__name__)
router = APIRouter(prefix="/interview", tags=["Interview"])

MAX_AUDIO_BYTES = 12 * 1024 * 1024  # ~3 minutes of Opus


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # stops any proxy from buffering the stream
}


# ===========================================================================
# Setup / metadata
# ===========================================================================


@router.get("/rubric")
def get_rubric(difficulty: str = "medium") -> dict[str, Any]:
    """The rubric, fixed in advance and shown to the candidate before starting."""
    return rubric.as_dict(difficulty)


@router.get("/stages")
def get_stages(difficulty: str = "medium") -> dict[str, Any]:
    return {"stages": stages.stage_catalogue(difficulty), "difficulty": difficulty}


@router.get("/speech/health")
def speech_health() -> dict[str, Any]:
    """Are the local speech engines ready?  Shown before the voice interview."""
    return {
        "stt": stt.describe(),
        "tts": tts.describe(),
        "voice_ready": stt.is_available() and settings.stt_enabled and settings.tts_enabled,
        "note": "Both speech recognition and speech synthesis run on this machine. "
                "No audio is sent to any external service.",
    }


@router.post("/speech/warmup")
def speech_warmup() -> dict[str, Any]:
    """
    Pre-load both speech models.

    Worth a dedicated endpoint: the first Whisper call includes model load time
    (seconds), which would otherwise pollute the first measured turn.
    """
    return {"stt": stt.warm_up(), "tts": tts.warm_up()}


@router.post("/speak")
def speak(request: SpeakRequest) -> Response:
    """Synthesise arbitrary text locally (used by 'replay' and the TTS test)."""
    result = tts.synthesise(request.text, voice=request.voice or None)
    return Response(
        content=result.audio,
        media_type="audio/wav",
        headers={
            "X-TTS-Engine": result.engine,
            "X-TTS-Voice": result.voice,
            "X-TTS-Processing-Ms": f"{result.processing_ms:.1f}",
            "X-TTS-Audio-Seconds": f"{result.audio_seconds:.2f}",
            "Cache-Control": "no-store",
        },
    )


# ===========================================================================
# Lifecycle
# ===========================================================================


@router.post("/start")
def start(request: StartInterviewRequest) -> dict[str, Any]:
    """Create an interview, planned against the chosen CV and role analysis."""
    cv_profile: dict[str, Any] = {}
    if request.cv_id:
        row = query_one("SELECT profile_json FROM cv_documents WHERE id = ?", (request.cv_id,))
        if row is not None:
            cv_profile = loads(row["profile_json"], {}) or {}

    role_requirements: dict[str, Any] = {}
    if request.role_analysis_id:
        row = query_one("SELECT requirements_json FROM role_analyses WHERE id = ?", (request.role_analysis_id,))
        if row is not None:
            role_requirements = requirements_from_dict(loads(row["requirements_json"], {}) or {}).to_dict()

    interview = engine.create_interview(
        role_title=request.role_title,
        difficulty=request.difficulty,
        mode=request.mode,
        cv_id=request.cv_id,
        cv_profile=cv_profile,
        role_requirements=role_requirements,
    )
    log_activity("interview_start", f"Started interview: {request.role_title}",
                 f"{request.difficulty} difficulty, {request.mode} mode", interview.id)

    return {
        "interview": interview.to_dict(),
        "rubric": rubric.as_dict(interview.difficulty),
        "stages": stages.stage_catalogue(interview.difficulty),
        "has_cv": bool(cv_profile),
        "has_role_requirements": bool(role_requirements),
        "speech": {"stt": stt.describe(), "tts": tts.describe()} if request.mode == "voice" else None,
    }


@router.get("")
def list_all(limit: int = 25) -> dict[str, Any]:
    items = engine.list_interviews(max(1, min(limit, 100)))
    return {"items": items, "count": len(items)}


@router.get("/{interview_id}")
def get_one(interview_id: str) -> dict[str, Any]:
    interview = engine.load_interview(interview_id)
    turns = engine.get_turns(interview_id)
    return {
        "interview": interview.to_dict(),
        "turns": turns,
        "rubric": rubric.as_dict(interview.difficulty),
        "performance": metrics.interview_metrics(interview_id),
        "has_report": engine.get_report(interview_id) is not None,
    }


@router.post("/{interview_id}/end")
def end(interview_id: str) -> dict[str, Any]:
    interview = engine.end_interview(interview_id)
    log_activity("interview_end", f"Ended interview: {interview.role_title}",
                 f"{interview.state.total_questions} questions", interview_id)
    return {"interview": interview.to_dict()}


# ===========================================================================
# Turns
# ===========================================================================


@router.post("/{interview_id}/turn")
def text_turn(interview_id: str, request: InterviewTurnRequest) -> StreamingResponse:
    """
    A text-mode turn (also the documented fallback when the microphone or
    speech recognition is not working).
    """
    speech_ended_at = time.perf_counter()

    def generate() -> Iterator[str]:
        try:
            for event in engine.stream_turn(
                interview_id,
                candidate_text=request.text,
                speak=request.speak,
                speech_ended_at=speech_ended_at,
            ):
                yield _sse(event)
        except AppError as exc:
            yield _sse({"type": "error", "code": exc.code, "message": exc.message})
        except Exception as exc:  # pragma: no cover
            log.exception("Unhandled error in text turn for %s", interview_id)
            yield _sse({"type": "error", "code": "internal_error",
                        "message": "Something went wrong on this turn. Please try again."})
            del exc

    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/{interview_id}/voice-turn")
async def voice_turn(
    interview_id: str,
    audio: UploadFile = File(...),
    speak: bool = Form(True),
) -> StreamingResponse:
    """
    A full spoken turn: local transcription, then the streamed spoken reply.

    Order of operations matters for honest measurement:
      1. read the upload   -> `speech_ended_at` is stamped here
      2. transcribe locally (stt_ms)
      3. emit the transcript so the user sees it immediately
      4. stream the reply text + per-sentence audio
    """
    data = await audio.read()
    speech_ended_at = time.perf_counter()

    if len(data) > MAX_AUDIO_BYTES:
        raise ValidationError(
            f"That recording is too large ({len(data) / 1_048_576:.1f} MB). "
            f"The limit is {MAX_AUDIO_BYTES / 1_048_576:.0f} MB - please answer in shorter turns."
        )

    def generate() -> Iterator[str]:
        try:
            transcription = stt.transcribe_bytes(data, filename_hint=audio.filename or "recording.webm")
        except SpeechError as exc:
            yield _sse({"type": "error", "code": exc.code, "message": exc.message,
                        "fallback": "text", "stage": "speech_recognition"})
            return
        except Exception as exc:  # pragma: no cover
            log.exception("Unhandled transcription error for %s", interview_id)
            yield _sse({"type": "error", "code": "stt_failed",
                        "message": "Speech recognition failed on that recording. "
                                   "Please try again or type your answer.",
                        "fallback": "text"})
            del exc
            return

        yield _sse({
            "type": "transcript",
            "text": transcription.text,
            "stt": transcription.to_dict(),
        })

        if not transcription.has_speech:
            yield _sse({
                "type": "no_speech",
                "message": "No speech was detected in that recording. Press record and try again, "
                           "or type your answer instead.",
                "stt": transcription.to_dict(),
            })
            return

        try:
            for event in engine.stream_turn(
                interview_id,
                candidate_text=transcription.text,
                stt_ms=transcription.processing_ms,
                stt_engine=f"{transcription.engine}:{transcription.model_size}",
                audio_seconds=transcription.duration_seconds,
                speak=speak,
                speech_ended_at=speech_ended_at,
            ):
                yield _sse(event)
        except AppError as exc:
            yield _sse({"type": "error", "code": exc.code, "message": exc.message})
        except Exception as exc:  # pragma: no cover
            log.exception("Unhandled error in voice turn for %s", interview_id)
            yield _sse({"type": "error", "code": "internal_error",
                        "message": "Something went wrong on this turn. Please try again."})
            del exc

    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/transcribe")
async def transcribe_only(audio: UploadFile = File(...)) -> dict[str, Any]:
    """Transcribe a recording without advancing the interview (microphone test)."""
    data = await audio.read()
    if len(data) > MAX_AUDIO_BYTES:
        raise ValidationError("That recording is too large.")
    result = stt.transcribe_bytes(data, filename_hint=audio.filename or "recording.webm")
    return result.to_dict() | {"text": result.text}


# ===========================================================================
# Module 6 - scoring
# ===========================================================================


@router.post("/{interview_id}/score")
def score(interview_id: str) -> dict[str, Any]:
    """Score a finished interview against the pre-defined rubric."""
    interview = engine.load_interview(interview_id)
    if interview.status == engine.STATUS_ACTIVE:
        engine.end_interview(interview_id)

    report = scorer.score_interview(interview_id)
    log_activity(
        "interview_score",
        f"Scored interview: {interview.role_title}",
        f"{report.get('overall_score')}/5 ({report.get('overall_band')})",
        interview_id,
    )
    return report


@router.get("/{interview_id}/report")
def get_report(interview_id: str) -> dict[str, Any]:
    report = engine.get_report(interview_id)
    if report is None:
        return {"available": False,
                "message": "No feedback report has been generated for this interview yet."}
    return {"available": True, "report": report}


@router.get("/{interview_id}/transcript")
def get_transcript(interview_id: str) -> dict[str, Any]:
    interview = engine.load_interview(interview_id)
    turns = engine.get_turns(interview_id)
    return {
        "interview_id": interview_id,
        "role_title": interview.role_title,
        "difficulty": interview.difficulty,
        "turns": turns,
        "plain_text": engine.transcript_text(turns),
    }
