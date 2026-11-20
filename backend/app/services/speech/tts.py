"""
Module 5b - LOCAL text-to-speech.

The assignment requires text-to-speech to run on the machine.  Two local
engines are supported and neither sends text anywhere:

  piper  (primary)   Neural TTS running an ONNX model in this process.  Natural
                     prosody, ~0.05-0.15x real time on CPU, one 63 MB voice file.
  sapi   (fallback)  The operating system's own speech engine through pyttsx3
                     (SAPI5 on Windows, NSSpeechSynthesizer on macOS, espeak on
                     Linux).  Robotic but installed everywhere and needs no
                     model download, so the voice interview still works if the
                     Piper model is missing.

`TTS_ENGINE=auto` prefers Piper and silently degrades to SAPI, recording which
engine actually spoke in the performance metrics -- the report never attributes
SAPI latency to Piper.

Streaming
---------
`synthesise_stream()` splits the interviewer's reply into sentences and yields
one WAV per sentence.  Combined with the streaming LLM this is what lets audio
start before the full reply exists, which is the latency requirement in the
assignment.
"""

from __future__ import annotations

import io
import re
import struct
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from app.core.config import MODELS_DIR, settings
from app.core.errors import SpeechError
from app.core.logging_setup import get_logger

log = get_logger(__name__)

PIPER_DIR = MODELS_DIR / "piper"

_lock = threading.Lock()
_piper_voice: Any = None
_piper_voice_name: str = ""
_piper_error: str = ""
_sapi_error: str = ""
_piper_load_ms: float = 0.0

ENGINE_PIPER = "piper"
ENGINE_SAPI = "sapi"

# Sentence splitter that does not break on "e.g.", "Dr." or decimals.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")
_ABBREVIATIONS = ("e.g.", "i.e.", "etc.", "mr.", "mrs.", "ms.", "dr.", "prof.", "vs.", "no.")


@dataclass
class SynthesisResult:
    audio: bytes
    engine: str
    voice: str
    sample_rate: int
    processing_ms: float
    audio_seconds: float
    text: str
    real_time_factor: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "voice": self.voice,
            "sample_rate": self.sample_rate,
            "processing_ms": round(self.processing_ms, 1),
            "audio_seconds": round(self.audio_seconds, 2),
            "real_time_factor": round(self.real_time_factor, 3),
            "bytes": len(self.audio),
            "chars": len(self.text),
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Availability / description
# ---------------------------------------------------------------------------


def list_piper_voices() -> list[dict[str, Any]]:
    """Voices present on disk (an .onnx with its matching .onnx.json)."""
    out: list[dict[str, Any]] = []
    if not PIPER_DIR.exists():
        return out
    for model in sorted(PIPER_DIR.glob("*.onnx")):
        config = model.with_suffix(".onnx.json")
        out.append(
            {
                "name": model.stem,
                "model_path": str(model),
                "has_config": config.exists(),
                "size_bytes": model.stat().st_size,
                "ready": config.exists(),
            }
        )
    return out


def piper_installed() -> bool:
    try:
        import piper  # type: ignore  # noqa: F401

        return True
    except ImportError:
        return False


def sapi_installed() -> bool:
    try:
        import pyttsx3  # type: ignore  # noqa: F401

        return True
    except ImportError:
        return False


def active_engine() -> str:
    """Which engine will actually be used, given config and what is installed."""
    preference = settings.tts_engine
    piper_ready = piper_installed() and any(v["ready"] for v in list_piper_voices())

    if preference == ENGINE_PIPER:
        return ENGINE_PIPER if piper_ready else ENGINE_SAPI
    if preference == ENGINE_SAPI:
        return ENGINE_SAPI
    return ENGINE_PIPER if piper_ready else ENGINE_SAPI


def describe() -> dict[str, Any]:
    voices = list_piper_voices()
    return {
        "runs_locally": True,
        "enabled": settings.tts_enabled,
        "configured_engine": settings.tts_engine,
        "active_engine": active_engine(),
        "piper": {
            "installed": piper_installed(),
            "voices_on_disk": voices,
            "voice_dir": str(PIPER_DIR),
            "selected_voice": settings.tts_voice,
            "loaded_voice": _piper_voice_name or None,
            "load_ms": round(_piper_load_ms, 1) if _piper_load_ms else None,
            "last_error": _piper_error or None,
            "download_hint": (
                "python scripts/download_speech_models.py  (or see README -> Local speech models)"
            ),
        },
        "sapi": {
            "installed": sapi_installed(),
            "note": "Uses the operating system speech engine; fully offline, lower quality.",
            "last_error": _sapi_error or None,
        },
        "sample_rate": settings.tts_sample_rate,
        "speed": settings.tts_speed,
    }


# ---------------------------------------------------------------------------
# Piper
# ---------------------------------------------------------------------------


def _resolve_piper_model(voice_name: str | None = None) -> Path | None:
    wanted = (voice_name or settings.tts_voice or "").strip()
    if wanted:
        candidate = PIPER_DIR / f"{wanted}.onnx"
        if candidate.exists() and candidate.with_suffix(".onnx.json").exists():
            return candidate
    for voice in list_piper_voices():
        if voice["ready"]:
            return Path(voice["model_path"])
    return None


def _load_piper(voice_name: str | None = None):
    global _piper_voice, _piper_voice_name, _piper_error, _piper_load_ms

    model_path = _resolve_piper_model(voice_name)
    if model_path is None:
        _piper_error = f"No Piper voice found in {PIPER_DIR}"
        return None

    with _lock:
        if _piper_voice is not None and _piper_voice_name == model_path.stem:
            return _piper_voice

        try:
            from piper import PiperVoice  # type: ignore
        except ImportError as exc:
            _piper_error = f"piper-tts is not installed ({exc})"
            return None

        started = time.perf_counter()
        try:
            config_path = model_path.with_suffix(".onnx.json")
            try:
                voice = PiperVoice.load(str(model_path), config_path=str(config_path))
            except TypeError:
                # Older/newer signatures differ; positional form works on both.
                voice = PiperVoice.load(str(model_path), str(config_path))
            _piper_voice = voice
            _piper_voice_name = model_path.stem
            _piper_load_ms = (time.perf_counter() - started) * 1000
            _piper_error = ""
            log.info("Piper voice %r loaded in %.0f ms", _piper_voice_name, _piper_load_ms)
            return _piper_voice
        except Exception as exc:
            _piper_error = str(exc)[:300]
            _piper_voice = None
            log.error("Could not load Piper voice %s: %s", model_path.name, exc)
            return None


def _piper_sample_rate(voice: Any) -> int:
    for path in (
        ("config", "sample_rate"),
        ("config", "audio", "sample_rate"),
        ("sample_rate",),
    ):
        node: Any = voice
        for attribute in path:
            node = getattr(node, attribute, None) if not isinstance(node, dict) else node.get(attribute)
            if node is None:
                break
        if isinstance(node, int) and node > 0:
            return node
    return 22050


def _synthesise_piper(text: str, voice_name: str | None = None) -> SynthesisResult | None:
    voice = _load_piper(voice_name)
    if voice is None:
        return None

    started = time.perf_counter()
    buffer = io.BytesIO()
    sample_rate = _piper_sample_rate(voice)

    try:
        # piper-tts >= 1.3 writes a complete WAV through a wave.Wave_write.
        if hasattr(voice, "synthesize_wav"):
            with wave.open(buffer, "wb") as wav_file:
                voice.synthesize_wav(text, wav_file)
            audio = buffer.getvalue()
        elif hasattr(voice, "synthesize"):
            # Either the same wave-file API, or a chunk generator.
            try:
                with wave.open(buffer, "wb") as wav_file:
                    voice.synthesize(text, wav_file)
                audio = buffer.getvalue()
            except Exception:
                frames = bytearray()
                for chunk in voice.synthesize(text):
                    payload = getattr(chunk, "audio_int16_bytes", None)
                    if payload is None:
                        payload = getattr(chunk, "audio_int16_array", None)
                        payload = payload.tobytes() if payload is not None else None
                    if payload is None and isinstance(chunk, (bytes, bytearray)):
                        payload = bytes(chunk)
                    if payload:
                        frames.extend(payload)
                    rate = getattr(chunk, "sample_rate", None)
                    if isinstance(rate, int) and rate > 0:
                        sample_rate = rate
                audio = _wrap_pcm_as_wav(bytes(frames), sample_rate)
        elif hasattr(voice, "synthesize_stream_raw"):
            frames = bytearray()
            for chunk in voice.synthesize_stream_raw(text):
                frames.extend(chunk)
            audio = _wrap_pcm_as_wav(bytes(frames), sample_rate)
        else:
            _set_piper_error("The installed piper-tts version exposes no known synthesis method.")
            return None
    except Exception as exc:
        _set_piper_error(str(exc)[:300])
        log.error("Piper synthesis failed: %s", exc)
        return None

    processing_ms = (time.perf_counter() - started) * 1000
    duration = _wav_duration(audio)
    if not audio or duration <= 0:
        _set_piper_error("Piper produced no audio for this text.")
        return None

    return SynthesisResult(
        audio=audio,
        engine=ENGINE_PIPER,
        voice=_piper_voice_name,
        sample_rate=sample_rate,
        processing_ms=processing_ms,
        audio_seconds=duration,
        text=text,
        real_time_factor=(processing_ms / 1000 / duration) if duration > 0 else 0.0,
    )


def _set_piper_error(message: str) -> None:
    global _piper_error
    _piper_error = message


# ---------------------------------------------------------------------------
# SAPI / pyttsx3 fallback
# ---------------------------------------------------------------------------


def _synthesise_sapi(text: str) -> SynthesisResult | None:
    """
    Speak through the OS engine, writing to a temporary WAV.

    pyttsx3 drivers are not re-entrant, so a fresh engine is created per call
    and disposed of; that costs ~100 ms but avoids the well-known hang when an
    engine instance is reused from a different thread.
    """
    global _sapi_error

    try:
        import pyttsx3  # type: ignore
    except ImportError as exc:
        _sapi_error = f"pyttsx3 is not installed ({exc})"
        return None

    import os
    import tempfile

    tmp_path = ""
    started = time.perf_counter()
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            tmp_path = handle.name

        engine = pyttsx3.init()
        try:
            base_rate = engine.getProperty("rate") or 200
            engine.setProperty("rate", int(base_rate * max(0.5, min(1.6, settings.tts_speed))))
            engine.save_to_file(text, tmp_path)
            engine.runAndWait()
        finally:
            try:
                engine.stop()
            except Exception:
                pass
            del engine

        audio = Path(tmp_path).read_bytes() if Path(tmp_path).exists() else b""
        if not audio:
            _sapi_error = "The OS speech engine produced an empty file."
            return None

        processing_ms = (time.perf_counter() - started) * 1000
        duration = _wav_duration(audio)
        _sapi_error = ""
        return SynthesisResult(
            audio=audio,
            engine=ENGINE_SAPI,
            voice="os-default",
            sample_rate=_wav_sample_rate(audio) or settings.tts_sample_rate,
            processing_ms=processing_ms,
            audio_seconds=duration,
            text=text,
            real_time_factor=(processing_ms / 1000 / duration) if duration > 0 else 0.0,
            warnings=["Spoken with the operating system voice because the Piper model was unavailable."],
        )
    except Exception as exc:
        _sapi_error = str(exc)[:300]
        log.error("OS speech engine failed: %s", exc)
        return None
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def synthesise(text: str, *, voice: str | None = None, engine: str | None = None) -> SynthesisResult:
    """Speak `text` with the best available LOCAL engine."""
    if not settings.tts_enabled:
        raise SpeechError("Local text-to-speech is switched off in settings (TTS_ENABLED=false).")

    clean = clean_for_speech(text)
    if not clean:
        raise SpeechError("There is nothing to speak in that text.")

    preference = (engine or settings.tts_engine or "auto").lower()

    if preference in (ENGINE_PIPER, "auto"):
        result = _synthesise_piper(clean, voice)
        if result is not None:
            log.info("TTS piper: %d chars -> %.2fs audio in %.0fms (RTF %.3f)",
                     len(clean), result.audio_seconds, result.processing_ms, result.real_time_factor)
            return result
        if preference == ENGINE_PIPER:
            raise SpeechError(
                "The Piper voice could not be used. Download a voice with "
                "'python scripts/download_speech_models.py', or set TTS_ENGINE=auto to allow the "
                f"operating system voice as a fallback. Details: {_piper_error or 'unknown'}"
            )
        log.warning("Piper unavailable (%s); falling back to the OS speech engine", _piper_error)

    result = _synthesise_sapi(clean)
    if result is not None:
        log.info("TTS sapi: %d chars -> %.2fs audio in %.0fms", len(clean), result.audio_seconds, result.processing_ms)
        return result

    raise SpeechError(
        "No local text-to-speech engine is working on this machine. "
        f"Piper: {_piper_error or 'not available'}. OS engine: {_sapi_error or 'not available'}. "
        "The interview still works in text mode."
    )


def synthesise_stream(
    text: str, *, voice: str | None = None, engine: str | None = None
) -> Iterator[SynthesisResult]:
    """
    Yield one SynthesisResult per sentence.

    Sentence-level chunking is the whole point of the streaming design: the
    first clause can be playing while the rest is still being generated.
    """
    for sentence in split_sentences(text):
        if not sentence.strip():
            continue
        try:
            yield synthesise(sentence, voice=voice, engine=engine)
        except SpeechError as exc:
            log.warning("Skipping a sentence that could not be synthesised: %s", exc.message)
            continue


def warm_up() -> dict[str, Any]:
    """Pre-load the voice and verify synthesis works end to end."""
    if not settings.tts_enabled:
        return {"ready": False, "detail": "Text-to-speech is disabled in settings."}
    try:
        result = synthesise("Ready.")
        return {
            "ready": True,
            "engine": result.engine,
            "voice": result.voice,
            "processing_ms": round(result.processing_ms, 1),
            "sample_rate": result.sample_rate,
        }
    except SpeechError as exc:
        return {"ready": False, "detail": exc.message}


# ---------------------------------------------------------------------------
# Text and WAV helpers
# ---------------------------------------------------------------------------


def clean_for_speech(text: str, *, limit: int = 2400) -> str:
    """
    Strip anything that a TTS engine would read out literally.

    The interview prompt forbids markdown, but models slip occasionally, and
    hearing "asterisk asterisk important asterisk asterisk" ruins the illusion.
    """
    if not text:
        return ""

    out = str(text)
    out = re.sub(r"```.*?```", " ", out, flags=re.S)
    out = re.sub(r"`([^`]*)`", r"\1", out)
    out = re.sub(r"\*\*([^*]*)\*\*", r"\1", out)
    out = re.sub(r"(?<!\w)[*_]([^*_]+)[*_](?!\w)", r"\1", out)
    out = re.sub(r"^#{1,6}\s*", "", out, flags=re.M)
    out = re.sub(r"^\s*[-*•]\s+", "", out, flags=re.M)
    out = re.sub(r"^\s*\d+[.)]\s+", "", out, flags=re.M)
    out = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", out)
    out = re.sub(r"https?://\S+", "a link", out)
    out = re.sub(r"^\s*(?:interviewer|candidate)\s*:\s*", "", out, flags=re.I | re.M)
    out = re.sub(r"\((?:pause|laughs?|smiles?|beat)\)", " ", out, flags=re.I)
    out = re.sub(r"[•●▪→←⇒]", " ", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out[:limit]


def split_sentences(text: str, *, min_chars: int = 24, max_chars: int = 240) -> list[str]:
    """
    Split into speakable chunks.

    Very short fragments are merged forward (a two-word chunk sounds clipped)
    and over-long ones are split at a comma, so each WAV stays short enough to
    keep the time-to-first-audio low.
    """
    cleaned = clean_for_speech(text)
    if not cleaned:
        return []

    guarded = cleaned
    for abbreviation in _ABBREVIATIONS:
        guarded = guarded.replace(abbreviation, abbreviation.replace(".", "\u0001"))

    raw = [part.replace("\u0001", ".").strip() for part in _SENTENCE_RE.split(guarded)]
    raw = [part for part in raw if part]

    merged: list[str] = []
    for part in raw:
        if merged and len(merged[-1]) < min_chars:
            merged[-1] = f"{merged[-1]} {part}".strip()
        else:
            merged.append(part)

    out: list[str] = []
    for part in merged:
        if len(part) <= max_chars:
            out.append(part)
            continue
        buffer = ""
        for clause in re.split(r"(?<=,)\s+", part):
            if len(buffer) + len(clause) + 1 <= max_chars:
                buffer = f"{buffer} {clause}".strip()
            else:
                if buffer:
                    out.append(buffer)
                buffer = clause
        if buffer:
            out.append(buffer)
    return out


def _wrap_pcm_as_wav(pcm: bytes, sample_rate: int, *, channels: int = 1, width: int = 2) -> bytes:
    if not pcm:
        return b""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return buffer.getvalue()


def _wav_duration(audio: bytes) -> float:
    try:
        with wave.open(io.BytesIO(audio), "rb") as wav_file:
            rate = wav_file.getframerate() or 1
            return wav_file.getnframes() / rate
    except (wave.Error, EOFError, struct.error):
        return 0.0


def _wav_sample_rate(audio: bytes) -> int:
    try:
        with wave.open(io.BytesIO(audio), "rb") as wav_file:
            return wav_file.getframerate()
    except (wave.Error, EOFError, struct.error):
        return 0


def concat_wavs(parts: list[bytes]) -> bytes:
    """Join several WAVs into one (used to export a whole interviewer reply)."""
    usable = [p for p in parts if p]
    if not usable:
        return b""
    if len(usable) == 1:
        return usable[0]

    try:
        with wave.open(io.BytesIO(usable[0]), "rb") as first:
            params = first.getparams()
            frames = [first.readframes(first.getnframes())]
        for part in usable[1:]:
            with wave.open(io.BytesIO(part), "rb") as wav_file:
                if wav_file.getframerate() != params.framerate or wav_file.getnchannels() != params.nchannels:
                    continue  # mismatched engine output; skip rather than produce noise
                frames.append(wav_file.readframes(wav_file.getnframes()))

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as out:
            out.setnchannels(params.nchannels)
            out.setsampwidth(params.sampwidth)
            out.setframerate(params.framerate)
            out.writeframes(b"".join(frames))
        return buffer.getvalue()
    except (wave.Error, EOFError, struct.error) as exc:
        log.warning("Could not concatenate WAV chunks: %s", exc)
        return usable[0]
