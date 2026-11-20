"""
Module 5a - LOCAL speech recognition.

The assignment requires speech recognition to run on the machine, not through a
cloud API, so this module wraps faster-whisper (CTranslate2 Whisper).  No audio
ever leaves the laptop: the browser posts the recording to our own backend, the
model runs in this process, and the file is deleted immediately afterwards.

Model choice
------------
`base.en` int8 on CPU is the default: roughly 0.3-0.5x real time on a normal
laptop, which keeps the end-of-speech-to-reply budget workable, with clearly
better accuracy than `tiny.en` on technical vocabulary.  All of
tiny.en/base.en/small.en are selectable from Settings, and the first use of a
size downloads its weights once into backend/data/models.

Failure handling is first-class, because a mock interview that dies on a bad
recording is useless:
  * model missing / download failed  -> SpeechError with instructions
  * audio too short or silent        -> a "no speech detected" result, not an error
  * unsupported container           -> reported, with the text fallback suggested
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.config import MODELS_DIR, settings
from app.core.errors import SpeechError
from app.core.logging_setup import get_logger
from app.services.speech.audio_decode import decode_to_mono16k

log = get_logger(__name__)

_model_lock = threading.Lock()
_model: Any = None
_model_size_loaded: str = ""
_load_error: str = ""
_load_ms: float = 0.0

MIN_AUDIO_BYTES = 1200
VALID_SIZES = ("tiny.en", "tiny", "base.en", "base", "small.en", "small", "medium.en", "distil-small.en")


@dataclass
class TranscriptionResult:
    text: str
    language: str = "en"
    duration_seconds: float = 0.0
    processing_ms: float = 0.0
    real_time_factor: float = 0.0
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0
    confidence: str = "unknown"
    segments: list[dict[str, Any]] = field(default_factory=list)
    engine: str = ""
    model_size: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def has_speech(self) -> bool:
        return bool(self.text.strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "language": self.language,
            "duration_seconds": round(self.duration_seconds, 2),
            "processing_ms": round(self.processing_ms, 1),
            "real_time_factor": round(self.real_time_factor, 3),
            "avg_logprob": round(self.avg_logprob, 3),
            "no_speech_prob": round(self.no_speech_prob, 3),
            "confidence": self.confidence,
            "segment_count": len(self.segments),
            "engine": self.engine,
            "model_size": self.model_size,
            "warnings": self.warnings,
            "has_speech": self.has_speech,
        }


# ---------------------------------------------------------------------------
# Model lifecycle
# ---------------------------------------------------------------------------


def is_available() -> bool:
    try:
        import faster_whisper  # type: ignore  # noqa: F401

        return True
    except ImportError:
        return False


def get_model(size: str | None = None):
    """Load (once) and return the Whisper model.  Thread-safe."""
    global _model, _model_size_loaded, _load_error, _load_ms

    wanted = (size or settings.stt_model_size).strip()
    if wanted not in VALID_SIZES:
        log.warning("Unknown STT model size %r; falling back to base.en", wanted)
        wanted = "base.en"

    with _model_lock:
        if _model is not None and _model_size_loaded == wanted:
            return _model

        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError as exc:
            _load_error = (
                "faster-whisper is not installed. Run: pip install -r backend/requirements.txt"
            )
            raise SpeechError(
                "Local speech recognition is unavailable because faster-whisper is not installed. "
                "Install the backend requirements, or use the text fallback in the interview."
            ) from exc

        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        try:
            log.info("Loading local Whisper model %r (%s/%s). First run downloads the weights.",
                     wanted, settings.stt_device, settings.stt_compute_type)
            _model = WhisperModel(
                wanted,
                device=settings.stt_device,
                compute_type=settings.stt_compute_type,
                download_root=str(MODELS_DIR),
                num_workers=1,
            )
            _model_size_loaded = wanted
            _load_ms = (time.perf_counter() - started) * 1000
            _load_error = ""
            log.info("Whisper %r ready in %.0f ms", wanted, _load_ms)
            return _model
        except Exception as exc:
            _load_error = str(exc)[:400]
            _model = None
            log.error("Could not load Whisper model %r: %s", wanted, exc)
            raise SpeechError(
                "The local speech recognition model could not be loaded. "
                "The first run needs an internet connection to download the model once "
                "(about 150 MB for base.en). You can use the text fallback meanwhile."
            ) from exc


def warm_up() -> dict[str, Any]:
    """Pre-load the model so the first interview turn is not slowed by loading."""
    if not settings.stt_enabled:
        return {"loaded": False, "detail": "Speech recognition is disabled in settings."}
    try:
        get_model()
        return {"loaded": True, "model_size": _model_size_loaded, "load_ms": round(_load_ms, 1)}
    except SpeechError as exc:
        return {"loaded": False, "detail": exc.message}


def describe() -> dict[str, Any]:
    return {
        "engine": "faster-whisper (CTranslate2)",
        "runs_locally": True,
        "installed": is_available(),
        "enabled": settings.stt_enabled,
        "model_size": settings.stt_model_size,
        "loaded_model": _model_size_loaded or None,
        "device": settings.stt_device,
        "compute_type": settings.stt_compute_type,
        "beam_size": settings.stt_beam_size,
        "model_cache": str(MODELS_DIR),
        "load_ms": round(_load_ms, 1) if _load_ms else None,
        "last_error": _load_error or None,
        "available_sizes": list(VALID_SIZES),
    }


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------


def transcribe_bytes(
    audio: bytes,
    *,
    filename_hint: str = "recording.webm",
    language: str | None = None,
    model_size: str | None = None,
) -> TranscriptionResult:
    """
    Transcribe an in-memory recording from the browser.

    The audio is decoded to 16 kHz mono float32 by `audio_decode` and handed to
    the model as an array -- nothing is written to disk, so no recording is ever
    persisted, and the pipeline does not depend on faster-whisper's internal
    decoder (see audio_decode.py for why that matters).
    """
    if not settings.stt_enabled:
        raise SpeechError("Local speech recognition is switched off in settings (STT_ENABLED=false).")

    if not audio or len(audio) < MIN_AUDIO_BYTES:
        return TranscriptionResult(
            text="",
            engine="faster-whisper",
            model_size=model_size or settings.stt_model_size,
            confidence="none",
            warnings=[
                f"The recording was only {len(audio)} bytes. Nothing was transcribed - "
                "hold the record button a little longer and speak clearly."
            ],
        )

    model = get_model(model_size)

    started = time.perf_counter()
    samples, decoded_duration = decode_to_mono16k(audio, filename_hint=filename_hint)

    if decoded_duration > settings.stt_max_audio_seconds:
        raise SpeechError(
            f"That recording is {decoded_duration:.0f} seconds long. The limit is "
            f"{settings.stt_max_audio_seconds:.0f} seconds - please answer in shorter turns."
        )

    try:
        segments_iter, info = model.transcribe(
            samples,
            language=language or settings.stt_language,
            beam_size=max(1, settings.stt_beam_size),
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 420},
            condition_on_previous_text=False,
            temperature=0.0,
            no_speech_threshold=0.62,
        )
        segments = list(segments_iter)
    except SpeechError:
        raise
    except Exception as exc:
        log.error("Transcription failed for %s: %s", filename_hint, exc)
        raise SpeechError(
            "Speech recognition failed on this recording. Please try again, or type your "
            "answer using the text fallback."
        ) from exc

    processing_ms = (time.perf_counter() - started) * 1000
    text = " ".join(s.text.strip() for s in segments if s.text and s.text.strip()).strip()
    duration = float(getattr(info, "duration", 0.0) or 0.0) or decoded_duration

    logprobs = [float(getattr(s, "avg_logprob", 0.0) or 0.0) for s in segments]
    no_speech = [float(getattr(s, "no_speech_prob", 0.0) or 0.0) for s in segments]
    avg_logprob = sum(logprobs) / len(logprobs) if logprobs else 0.0
    avg_no_speech = sum(no_speech) / len(no_speech) if no_speech else 0.0

    result = TranscriptionResult(
        text=text,
        language=str(getattr(info, "language", language or settings.stt_language) or "en"),
        duration_seconds=duration,
        processing_ms=processing_ms,
        real_time_factor=(processing_ms / 1000 / duration) if duration > 0.05 else 0.0,
        avg_logprob=avg_logprob,
        no_speech_prob=avg_no_speech,
        confidence=_confidence_band(avg_logprob, avg_no_speech, text),
        segments=[
            {
                "start": round(float(getattr(s, "start", 0.0) or 0.0), 2),
                "end": round(float(getattr(s, "end", 0.0) or 0.0), 2),
                "text": s.text.strip(),
            }
            for s in segments
        ],
        engine="faster-whisper",
        model_size=_model_size_loaded,
    )

    if not text:
        result.warnings.append(
            "No speech was detected in that recording. Check that the right microphone is "
            "selected and that your browser has permission to use it."
        )
    elif result.confidence == "low":
        result.warnings.append(
            "The recognition confidence for this answer was low, so the transcript may contain "
            "errors. Correct it in the text box if it came out wrong."
        )

    log.info(
        "STT: %.1fs audio -> %d chars in %.0fms (RTF %.2f, confidence %s)",
        duration, len(text), processing_ms, result.real_time_factor, result.confidence,
    )
    return result


def _confidence_band(avg_logprob: float, no_speech_prob: float, text: str) -> str:
    """
    Turn Whisper's internals into something a user can act on.

    The thresholds follow the Whisper decoder's own heuristics: an average token
    log-probability below about -1.0 is where transcripts start degrading badly,
    and a no-speech probability above 0.6 usually means silence or noise.
    """
    if not text.strip():
        return "none"
    if no_speech_prob > 0.6 or avg_logprob < -1.0:
        return "low"
    if avg_logprob < -0.62:
        return "medium"
    return "high"
