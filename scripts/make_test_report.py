"""
Generate docs/TEST_REPORT.md from real pytest results.

The report has to state, per test case, the expected result, the actual result
and pass/fail. Writing that by hand invites drift between the document and the
suite, so it is generated from an actual run:

    python scripts/make_test_report.py

It runs pytest itself (offline suite, then the `live` suite), parses the
machine-readable outcome of every test, and writes the document. The expected
result for each test is taken from its docstring where one exists, and
otherwise derived from its name — which is why the tests are named as
sentences.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
TESTS = BACKEND / "tests"
OUT = ROOT / "docs" / "TEST_REPORT.md"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
if not PYTHON.exists():
    PYTHON = ROOT / ".venv" / "bin" / "python"
if not PYTHON.exists():
    PYTHON = Path(sys.executable)

# Which requirement area each test file covers.
FILE_AREAS: dict[str, tuple[str, str]] = {
    "test_cv_parser.py": ("Module 1", "CV extraction and structured parsing"),
    "test_skill_normalisation.py": ("Module 2B / 3", "Skill normalisation and the taxonomy"),
    "test_matching_and_guards.py": ("Modules 2–4", "Fusion, gap matching, invention guards, LLM output defences"),
    "test_interview.py": ("Modules 5–6", "Interview stage machine, adaptation, streaming, rubric"),
    "test_speech_and_scraping.py": ("Modules 2 / 5", "Local speech engines and scraping compliance"),
    "test_api.py": ("All", "HTTP API contract, database, metrics"),
}


def run_pytest(marker: str, label: str) -> tuple[list[dict], str]:
    """Run pytest and return (results, summary line)."""
    print(f"Running the {label} suite…", flush=True)
    process = subprocess.run(
        # `-o addopts=` clears pytest.ini's own flags, which include -q.
        # Without that, -q and -v cancel out and no per-test line is printed.
        [
            str(PYTHON), "-m", "pytest",
            "-o", "addopts=",
            "-m", marker,
            "-v", "--tb=line", "-p", "no:cacheprovider",
        ],
        cwd=str(BACKEND),
        capture_output=True,
        text=True,
        timeout=1800,
    )
    output = process.stdout + process.stderr

    results: list[dict] = []
    pattern = re.compile(r"^(tests[/\\][\w_]+\.py)::(\w+)(?:\[(.*?)\])?\s+(PASSED|FAILED|ERROR|SKIPPED|XFAIL)")
    for line in output.splitlines():
        match = pattern.match(line.strip())
        if match:
            results.append(
                {
                    "file": Path(match.group(1)).name,
                    "test": match.group(2),
                    "param": match.group(3) or "",
                    "outcome": match.group(4),
                }
            )

    summary = ""
    for line in output.splitlines():
        if re.search(r"\d+ (passed|failed|error)", line) and "=" in line:
            summary = line.strip().strip("=").strip()
    return results, summary


def docstrings_for(path: Path) -> dict[str, str]:
    """Map test function name -> first line of its docstring."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        return {}

    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            doc = ast.get_docstring(node)
            if doc:
                first = " ".join(doc.strip().split("\n\n")[0].split())
                out[node.name] = first
    return out


def humanise(name: str) -> str:
    """`test_empty_file_is_rejected` -> `Empty file is rejected`."""
    text = name.removeprefix("test_").replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else name


def main() -> int:
    offline, offline_summary = run_pytest("not live", "offline")
    live, live_summary = run_pytest("live", "live")

    docs: dict[str, dict[str, str]] = {}
    for path in sorted(TESTS.glob("test_*.py")):
        docs[path.name] = docstrings_for(path)

    def group(results: list[dict]) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = {}
        for item in results:
            grouped.setdefault(item["file"], []).append(item)
        return grouped

    offline_by_file = group(offline)
    live_by_file = group(live)

    total = len(offline) + len(live)
    passed = sum(1 for r in offline + live if r["outcome"] == "PASSED")
    failed = sum(1 for r in offline + live if r["outcome"] in ("FAILED", "ERROR"))
    skipped = sum(1 for r in offline + live if r["outcome"] == "SKIPPED")

    lines: list[str] = []
    add = lines.append

    add("# Test Report")
    add("")
    add("**This document is generated from an actual test run.** Regenerate it with:")
    add("")
    add("```bash")
    add("python scripts/make_test_report.py")
    add("```")
    add("")
    add(f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    add("")
    add("---")
    add("")
    add("## Summary")
    add("")
    add("| | Count |")
    add("|---|---|")
    add(f"| **Total tests** | **{total}** |")
    add(f"| Passed | {passed} |")
    add(f"| Failed | {failed} |")
    add(f"| Skipped | {skipped} |")
    add(f"| Offline suite (no model, no network) | {len(offline)} |")
    add(f"| Live suite (real models + network) | {len(live)} |")
    add("")
    add(f"- Offline run: `{offline_summary}`")
    add(f"- Live run: `{live_summary}`")
    add("")

    if failed:
        add("> **Some tests are failing.** Each failure is listed in its section below.")
    else:
        add("> All tests pass.")
    add("")

    add("## How the suite is designed")
    add("")
    add("The default suite runs against the **deterministic offline engine**")
    add("(`LLM_PROVIDER=offline`) with scraping disabled. That is deliberate: a sampling")
    add("language model gives different output every run, which would make the tests")
    add("either flaky or so loose that they assert nothing. These tests therefore check")
    add("*the application's own logic* — parsing, normalisation, matching, the guards, the")
    add("state machine, persistence, the HTTP contract — rather than the model's mood, and")
    add("they pass identically on every run.")
    add("")
    add("Tests that genuinely need a downloaded model or live internet are marked `live`")
    add("and skipped by default:")
    add("")
    add("```bash")
    add('pytest -m "not live"   # the default')
    add("pytest -m live         # needs Whisper + Piper downloaded, and network")
    add("pytest                 # everything")
    add("```")
    add("")
    add("The headline live test synthesises a sentence with local TTS, transcribes it with")
    add("local STT, and asserts the content words survive — a genuine end-to-end check of")
    add("the mandatory local speech requirement.")
    add("")
    add("---")
    add("")

    def section(title: str, grouped: dict[str, list[dict]], note: str) -> None:
        add(f"## {title}")
        add("")
        add(note)
        add("")
        for filename in sorted(grouped):
            area, description = FILE_AREAS.get(filename, ("—", ""))
            items = grouped[filename]
            file_passed = sum(1 for i in items if i["outcome"] == "PASSED")

            add(f"### `{filename}` — {description}")
            add("")
            add(f"*Covers: {area}. {file_passed}/{len(items)} passed.*")
            add("")
            add("| # | Test case | Expected result | Actual | Status |")
            add("|---|---|---|---|---|")

            # Collapse parametrised variants into one row with a count.
            seen: dict[str, dict] = {}
            for item in items:
                key = item["test"]
                if key not in seen:
                    seen[key] = {"item": item, "variants": 0, "failed": 0}
                seen[key]["variants"] += 1
                if item["outcome"] in ("FAILED", "ERROR"):
                    seen[key]["failed"] += 1

            for index, (name, info) in enumerate(seen.items(), start=1):
                # The test name IS the expectation (tests are named as
                # sentences), so the code reference goes in the first column
                # and the sentence, or its docstring, in the second.
                docstring = docs.get(filename, {}).get(name)
                expected = docstring or f"{humanise(name)}."
                if len(expected) > 160:
                    expected = expected[:157] + "…"

                label = f"`{name}`"
                if info["variants"] > 1:
                    label += f"<br/>*{info['variants']} cases*"

                ok = info["failed"] == 0
                actual = (
                    f"Passed ({info['variants']} cases)"
                    if ok and info["variants"] > 1
                    else "Passed"
                    if ok
                    else f"{info['failed']} of {info['variants']} FAILED"
                )
                status = "✅" if ok else "❌"
                expected = expected.replace("|", "\\|")
                add(f"| {index} | {label} | {expected} | {actual} | {status} |")
            add("")

    section(
        "Offline test suite",
        offline_by_file,
        "No language model and no network access. Fully reproducible.",
    )
    section(
        "Live test suite",
        live_by_file,
        "Requires the downloaded Whisper and Piper models and live internet access. "
        "Run with `pytest -m live`.",
    )

    add("---")
    add("")
    add("## What could not be tested automatically, and why")
    add("")
    add("Stated here rather than left as a silent gap.")
    add("")
    add("| Area | Why not automated | How it was verified instead |")
    add("|---|---|---|")
    add("| **Real microphone capture** | `MediaRecorder` needs a browser and a physical "
        "input device; a headless browser has neither | Manual testing in Chrome; the input-level "
        "meter makes a muted or wrong device visible to the user |")
    add("| **Human speech recognition accuracy** | No labelled human-speech corpus for this "
        "domain, and recording one was out of scope | The live round-trip test uses local TTS "
        "audio; the limitation is stated in the evaluation |")
    add("| **Cloud LLM providers** | No API key is committed, and a paid key cannot be a test "
        "dependency | The provider abstraction is covered via the offline and Ollama paths; "
        "`probe_llm()` checks a configured provider at runtime from the Settings page |")
    add("| **Audio playback in the browser** | Cannot assert that a sound was heard | The audio "
        "queue's ordering logic is unit-tested; playback was verified manually |")
    add("| **Rubric score correctness** | There is no ground truth — that needs multiple human "
        "assessors and an inter-rater agreement figure | The *process* is tested: fixed rubric, "
        "whitelisted categories, clamped scores, Python-side arithmetic, hiring language stripped |")
    add("| **Job board content** | The boards' contents change hourly; asserting on them would "
        "make the suite fail for reasons unrelated to this code | Reachability and parsing are "
        "tested live; content assertions are limited to structure |")
    add("")
    add("---")
    add("")
    add("## Reproducing this report")
    add("")
    add("```bash")
    add("# 1. install")
    add("python -m venv .venv && .venv\\Scripts\\activate")
    add("pip install -r backend/requirements.txt")
    add("")
    add("# 2. generate the synthetic test CVs the suite needs")
    add("python scripts/make_sample_cvs.py")
    add("")
    add("# 3. for the live tests only, download the speech models")
    add("python scripts/download_speech_models.py --warm-whisper")
    add("")
    add("# 4. regenerate this document")
    add("python scripts/make_test_report.py")
    add("```")
    add("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nWrote {OUT}")
    print(f"  {total} tests: {passed} passed, {failed} failed, {skipped} skipped")

    machine = ROOT / "evaluation" / "results" / "test_results.json"
    machine.parent.mkdir(parents=True, exist_ok=True)
    machine.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "total": total,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "offline_summary": offline_summary,
                "live_summary": live_summary,
                "results": offline + live,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"  machine-readable: {machine}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
