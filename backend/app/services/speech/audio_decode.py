"""
Audio decoding for the local speech-recognition path.

Why we decode the audio ourselves instead of letting faster-whisper do it
-------------------------------------------------------------------------
faster-whisper's bundled decoder calls `av.open(..., metadata_errors="ignore")`,
a keyword PyAV removed in version 14.  With PyAV 19 installed, handing a file
path to `model.transcribe()` raises

    TypeError: open() got an unexpected keyword argument 'metadata_errors'

Pinning PyAV backwards would fix it today and break again later.  Decoding here
instead means:

  * the pipeline works across PyAV versions, because we only use the stable API
  * the browser's WebM/Opus recording, a WAV, an MP3 or an M4A all take the
    same path
  * resampling to the 16 kHz mono float32 that Whisper actually wants is
    explicit and testable, rather than a side effect of someone else's helper
  * a pure-stdlib `wave` fast path handles WAV with no PyAV involvement at all

`model.transcribe()` accepts a numpy float32 array, which is what this returns.
"""

from __future__ import annotations

import io
import wave
from typing import Any

from app.core.errors import SpeechError
from app.core.logging_setup import get_logger

log = get_logger(__name__)

TARGET_RATE = 16_000
MAX_SAMPLES = TARGET_RATE * 60 * 10  # 10 minutes, a hard guard on memory


def decode_to_mono16k(data: bytes, *, filename_hint: str = "") -> tuple[Any, float]:
    """
    Decode arbitrary audio bytes to (float32 numpy array, duration_seconds).

    Samples are mono, 16 kHz, in the range [-1.0, 1.0].
    """
    if not data:
        raise SpeechError("The recording was empty.")

    import numpy as np

    samples = _try_wave(data)
    source = "wave (stdlib)"
    if samples is None:
        samples = _try_pyav(data, filename_hint)
        source = "PyAV"

    if samples is None or samples.size == 0:
        raise SpeechError(
            "That audio could not be decoded. Please record again, or type your answer using "
            "the text fallback."
        )

    if samples.size > MAX_SAMPLES:
        log.warning("Truncating a %.1fs recording to 10 minutes", samples.size / TARGET_RATE)
        samples = samples[:MAX_SAMPLES]

    duration = float(samples.size) / TARGET_RATE
    log.debug("Decoded %d bytes via %s -> %.2fs @ %d Hz mono", len(data), source, duration, TARGET_RATE)
    return samples.astype(np.float32, copy=False), duration


def _try_wave(data: bytes):
    """Fast path: a real WAV needs nothing but the standard library."""
    import numpy as np

    try:
        with wave.open(io.BytesIO(data), "rb") as wav_file:
            channels = wav_file.getnchannels()
            width = wav_file.getsampwidth()
            rate = wav_file.getframerate()
            frames = wav_file.readframes(wav_file.getnframes())
    except (wave.Error, EOFError, ValueError):
        return None

    if not frames:
        return None

    dtype = {1: np.uint8, 2: np.int16, 4: np.int32}.get(width)
    if dtype is None:
        return None  # 24-bit or float WAV: let PyAV handle it

    audio = np.frombuffer(frames, dtype=dtype).astype(np.float32)
    if width == 1:
        audio = (audio - 128.0) / 128.0
    elif width == 2:
        audio /= 32768.0
    else:
        audio /= 2147483648.0

    if channels > 1:
        usable = (audio.size // channels) * channels
        audio = audio[:usable].reshape(-1, channels).mean(axis=1)

    return _resample(audio, rate, TARGET_RATE)


def _try_pyav(data: bytes, filename_hint: str):
    """General path: WebM/Opus from the browser, MP3, M4A, FLAC, odd WAVs."""
    import numpy as np

    try:
        import av  # type: ignore
    except ImportError as exc:
        raise SpeechError(
            "The audio decoder (PyAV) is not installed, so recordings cannot be read. "
            "Run: pip install -r backend/requirements.txt"
        ) from exc

    buffer = io.BytesIO(data)
    try:
        container = av.open(buffer)
    except Exception as exc:
        log.info("PyAV could not open %r: %s", filename_hint or "recording", exc)
        return None

    try:
        if not container.streams.audio:
            log.info("No audio stream found in %r", filename_hint or "recording")
            return None
        stream = container.streams.audio[0]

        # Ask PyAV for exactly what Whisper wants, so we do no DSP ourselves.
        resampler = av.AudioResampler(format="s16", layout="mono", rate=TARGET_RATE)

        chunks: list[Any] = []
        for frame in container.decode(stream):
            for resampled in _resample_frame(resampler, frame):
                chunks.append(resampled.to_ndarray().reshape(-1))

        # Flush whatever the resampler is still holding.
        try:
            for resampled in _resample_frame(resampler, None):
                chunks.append(resampled.to_ndarray().reshape(-1))
        except Exception:
            pass

        if not chunks:
            return None

        audio = np.concatenate(chunks).astype(np.float32) / 32768.0
        return audio
    except Exception as exc:
        log.warning("PyAV decode failed for %r: %s", filename_hint or "recording", exc)
        return None
    finally:
        try:
            container.close()
        except Exception:
            pass


def _resample_frame(resampler: Any, frame: Any) -> list[Any]:
    """
    Call the resampler across PyAV API generations.

    Older PyAV returns a single frame (or None); newer returns a list.
    """
    result = resampler.resample(frame)
    if result is None:
        return []
    if isinstance(result, list):
        return [f for f in result if f is not None]
    return [result]


def _resample(audio: Any, source_rate: int, target_rate: int):
    """
    Linear resampling, used only on the stdlib WAV path.

    Linear interpolation is adequate here: the input is already speech at
    16-48 kHz, and Whisper's own front end is a mel spectrogram that is
    insensitive to the small amount of aliasing this introduces.  The PyAV path
    uses libswresample, which is better, for everything else.
    """
    import numpy as np

    if source_rate == target_rate or audio.size == 0:
        return audio

    duration = audio.size / float(source_rate)
    target_count = max(1, int(round(duration * target_rate)))
    source_positions = np.linspace(0.0, audio.size - 1, num=audio.size, dtype=np.float64)
    target_positions = np.linspace(0.0, audio.size - 1, num=target_count, dtype=np.float64)
    return np.interp(target_positions, source_positions, audio).astype(np.float32)


def probe(data: bytes) -> dict[str, Any]:
    """Container/codec details, used by the Settings page audio diagnostics."""
    try:
        import av  # type: ignore

        with av.open(io.BytesIO(data)) as container:
            audio_streams = container.streams.audio
            stream = audio_streams[0] if audio_streams else None
            return {
                "decodable": bool(stream),
                "format": getattr(container.format, "name", ""),
                "codec": getattr(getattr(stream, "codec_context", None), "name", "") if stream else "",
                "sample_rate": getattr(stream, "rate", 0) if stream else 0,
                "channels": getattr(stream, "channels", 0) if stream else 0,
                "duration_seconds": round(float(container.duration or 0) / 1_000_000, 2),
            }
    except Exception as exc:
        return {"decodable": False, "detail": str(exc)[:200]}
