"""
Download the local speech models.

Run once after installing the Python dependencies:

    python scripts/download_speech_models.py

What it fetches
---------------
Piper voice   en_US-amy-medium  (~63 MB)  -> backend/data/models/piper/
              A second voice (ryan) is optional, with --all-voices.

The Whisper model is NOT downloaded here: faster-whisper fetches it itself on
first use, into backend/data/models/. Use --warm-whisper to trigger that now
rather than during your first interview.

Everything downloaded here runs on your machine. No audio is ever sent anywhere.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPER_DIR = ROOT / "backend" / "data" / "models" / "piper"

HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US"

VOICES: dict[str, dict[str, str]] = {
    "en_US-amy-medium": {
        "url": f"{HF_BASE}/amy/medium",
        "description": "Female, US English, medium quality (the default)",
        "size": "63 MB",
    },
    "en_US-ryan-medium": {
        "url": f"{HF_BASE}/ryan/medium",
        "description": "Male, US English, medium quality",
        "size": "63 MB",
    },
    "en_US-lessac-medium": {
        "url": f"{HF_BASE}/lessac/medium",
        "description": "Neutral, US English, medium quality",
        "size": "63 MB",
    },
}

DEFAULT_VOICE = "en_US-amy-medium"


def human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def download(url: str, destination: Path, *, label: str) -> bool:
    """Stream a file to disk, showing progress.  Returns True on success."""
    try:
        import httpx
    except ImportError:
        print("  ! httpx is not installed. Run: pip install -r backend/requirements.txt")
        return False

    temporary = destination.with_suffix(destination.suffix + ".part")
    started = time.perf_counter()

    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=120.0) as response:
            if response.status_code != 200:
                print(f"  ! {label}: HTTP {response.status_code}")
                return False

            total = int(response.headers.get("content-length", 0))
            written = 0
            with temporary.open("wb") as handle:
                for chunk in response.iter_bytes(chunk_size=256 * 1024):
                    handle.write(chunk)
                    written += len(chunk)
                    if total:
                        percent = written / total * 100
                        bar = "#" * int(percent / 2.5)
                        print(f"\r  {label}: [{bar:<40}] {percent:5.1f}%  {human(written)}",
                              end="", flush=True)
                    else:
                        print(f"\r  {label}: {human(written)}", end="", flush=True)

        temporary.replace(destination)
        elapsed = time.perf_counter() - started
        print(f"\r  {label}: done — {human(written)} in {elapsed:.1f}s" + " " * 20)
        return True

    except Exception as exc:
        print(f"\r  ! {label} failed: {type(exc).__name__}: {exc}" + " " * 20)
        if temporary.exists():
            temporary.unlink(missing_ok=True)
        return False


def fetch_voice(name: str, *, force: bool = False) -> bool:
    meta = VOICES[name]
    PIPER_DIR.mkdir(parents=True, exist_ok=True)

    model = PIPER_DIR / f"{name}.onnx"
    config = PIPER_DIR / f"{name}.onnx.json"

    if model.exists() and config.exists() and not force:
        print(f"  {name}: already present ({human(model.stat().st_size)}) - skipping")
        return True

    print(f"\n{name}  ({meta['size']})")
    print(f"  {meta['description']}")

    ok_model = download(f"{meta['url']}/{name}.onnx", model, label="model ")
    ok_config = download(f"{meta['url']}/{name}.onnx.json", config, label="config")

    if ok_model and ok_config:
        # A truncated download is worse than none: it fails at synthesis time
        # with a confusing ONNX error instead of here.
        if model.stat().st_size < 10_000_000:
            print(f"  ! {name}: the model file is implausibly small - deleting it")
            model.unlink(missing_ok=True)
            config.unlink(missing_ok=True)
            return False
        return True

    model.unlink(missing_ok=True)
    config.unlink(missing_ok=True)
    return False


def warm_whisper(size: str) -> bool:
    """Trigger the one-off Whisper download by loading the model."""
    print(f"\nWhisper {size}")
    print("  The first load downloads the weights. This can take a few minutes.")

    sys.path.insert(0, str(ROOT / "backend"))
    try:
        from app.services.speech import stt
    except ImportError as exc:
        print(f"  ! could not import the backend: {exc}")
        print("    Did you install the requirements and activate the virtual environment?")
        return False

    started = time.perf_counter()
    try:
        stt.get_model(size)
        print(f"  ready in {time.perf_counter() - started:.1f}s")
        return True
    except Exception as exc:
        print(f"  ! failed: {exc}")
        return False


def verify() -> bool:
    """Load the voice and synthesise one phrase, so a problem shows up now."""
    print("\nVerifying local text-to-speech")
    sys.path.insert(0, str(ROOT / "backend"))
    try:
        from app.services.speech import tts
    except ImportError as exc:
        print(f"  ! could not import the backend: {exc}")
        return False

    try:
        result = tts.synthesise("Local speech synthesis is working.")
    except Exception as exc:
        print(f"  ! synthesis failed: {exc}")
        return False

    print(f"  engine : {result.engine}")
    print(f"  voice  : {result.voice}")
    print(f"  output : {human(len(result.audio))}, {result.audio_seconds:.2f}s of audio")
    print(f"  time   : {result.processing_ms:.0f}ms (real-time factor {result.real_time_factor:.3f})")

    if result.engine != "piper":
        print("\n  ! Piper was not used, so the voice will sound robotic.")
        print("    Check the messages above and the Settings page in the app.")
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the local speech models.")
    parser.add_argument("--voice", default=DEFAULT_VOICE, choices=sorted(VOICES),
                        help="which Piper voice to download")
    parser.add_argument("--all-voices", action="store_true", help="download every listed voice")
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    parser.add_argument("--warm-whisper", action="store_true",
                        help="also download the Whisper model now")
    parser.add_argument("--whisper-size", default="base.en",
                        help="Whisper model size to warm (default: base.en)")
    parser.add_argument("--no-verify", action="store_true", help="skip the synthesis check")
    args = parser.parse_args()

    print("=" * 70)
    print("LOCAL SPEECH MODELS")
    print("=" * 70)
    print(f"Destination: {PIPER_DIR}")
    print("These models run on this machine. No audio is sent to any service.")

    wanted = sorted(VOICES) if args.all_voices else [args.voice]
    results = {name: fetch_voice(name, force=args.force) for name in wanted}

    whisper_ok = True
    if args.warm_whisper:
        whisper_ok = warm_whisper(args.whisper_size)

    verified = True
    if not args.no_verify and any(results.values()):
        verified = verify()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for name, ok in results.items():
        print(f"  {'OK  ' if ok else 'FAIL'}  {name}")
    if args.warm_whisper:
        print(f"  {'OK  ' if whisper_ok else 'FAIL'}  whisper {args.whisper_size}")
    if not args.no_verify:
        print(f"  {'OK  ' if verified else 'WARN'}  synthesis check")

    if all(results.values()) and whisper_ok and verified:
        print("\nAll set. Start the app and the voice interview will work.")
        return 0

    print("\nSomething did not complete. The app still runs:")
    print("  - the interview works fully in text mode")
    print("  - without a Piper voice it falls back to the operating-system voice")
    print("  - see Settings in the app for live diagnostics")
    return 1


if __name__ == "__main__":
    sys.exit(main())
