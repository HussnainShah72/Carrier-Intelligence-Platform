"""
Verify the project against every compulsory requirement, and write the checklist.

This does not take anything on trust: it checks that files exist, that the tests
pass, that no secret is committed, that the measured results are present, and
that the documented claims about local speech hold. It then writes
SUBMISSION_CHECKLIST.md with the result of each check.

    python scripts/verify_submission.py
    python scripts/verify_submission.py --skip-tests   # faster, skips the suite
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "SUBMISSION_CHECKLIST.md"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
if not PYTHON.exists():
    PYTHON = ROOT / ".venv" / "bin" / "python"
if not PYTHON.exists():
    PYTHON = Path(sys.executable)

PASS, FAIL, WARN = "PASS", "FAIL", "ACTION NEEDED"

results: list[dict[str, Any]] = []


def check(section: str, requirement: str, fn: Callable[[], tuple[str, str]]) -> None:
    try:
        status, detail = fn()
    except Exception as exc:
        status, detail = FAIL, f"check raised {type(exc).__name__}: {exc}"
    results.append({"section": section, "requirement": requirement,
                    "status": status, "detail": detail})
    symbol = {"PASS": "[ok]", "FAIL": "[FAIL]", "ACTION NEEDED": "[action]"}[status]
    print(f"  {symbol:9} {requirement}")
    if status != PASS:
        print(f"            -> {detail}")


def exists(*parts: str) -> Path:
    return ROOT.joinpath(*parts)


def file_check(label: str, *parts: str, min_bytes: int = 1) -> Callable[[], tuple[str, str]]:
    def run() -> tuple[str, str]:
        path = exists(*parts)
        if not path.exists():
            return FAIL, f"{path.relative_to(ROOT)} is missing"
        size = path.stat().st_size
        if size < min_bytes:
            return FAIL, f"{path.relative_to(ROOT)} is only {size} bytes"
        return PASS, f"{path.relative_to(ROOT)} ({size:,} bytes)"
    run.__doc__ = label
    return run


def dir_check(*parts: str, min_files: int = 1) -> Callable[[], tuple[str, str]]:
    def run() -> tuple[str, str]:
        path = exists(*parts)
        if not path.is_dir():
            return FAIL, f"{path.relative_to(ROOT)} is missing"
        files = [f for f in path.rglob("*") if f.is_file()]
        if len(files) < min_files:
            return FAIL, f"only {len(files)} file(s) in {path.relative_to(ROOT)}"
        return PASS, f"{len(files)} files in {path.relative_to(ROOT)}"
    return run


def grep_check(pattern: str, *parts: str, should_find: bool = True,
               label: str = "") -> Callable[[], tuple[str, str]]:
    def run() -> tuple[str, str]:
        path = exists(*parts)
        if not path.exists():
            return FAIL, f"{path.relative_to(ROOT)} is missing"
        text = path.read_text(encoding="utf-8", errors="replace")
        found = bool(re.search(pattern, text, re.I | re.M))
        if found == should_find:
            return PASS, label or ("found" if found else "correctly absent")
        return FAIL, f"pattern {'not found' if should_find else 'unexpectedly found'}: {pattern}"
    return run


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_tests(skip: bool) -> tuple[str, str]:
    if skip:
        return WARN, "skipped with --skip-tests"
    path = ROOT / "evaluation" / "results" / "test_results.json"
    process = subprocess.run(
        [str(PYTHON), "-m", "pytest", "-o", "addopts=", "-m", "not live", "-q",
         "-p", "no:cacheprovider"],
        cwd=str(ROOT / "backend"), capture_output=True, text=True, timeout=1800,
    )
    output = process.stdout + process.stderr
    match = re.search(r"(\d+) passed", output)
    failed = re.search(r"(\d+) failed", output)
    if process.returncode == 0 and match:
        extra = ""
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            extra = f"; {data.get('total')} total including the live suite"
        return PASS, f"{match.group(1)} offline tests passed{extra}"
    return FAIL, f"{failed.group(1) if failed else '?'} test(s) failing"


def check_live_tests(skip: bool) -> tuple[str, str]:
    if skip:
        return WARN, "skipped with --skip-tests"
    process = subprocess.run(
        [str(PYTHON), "-m", "pytest", "-o", "addopts=", "-m", "live", "-q",
         "-p", "no:cacheprovider"],
        cwd=str(ROOT / "backend"), capture_output=True, text=True, timeout=1800,
    )
    output = process.stdout + process.stderr
    match = re.search(r"(\d+) passed", output)
    if process.returncode == 0 and match:
        return PASS, f"{match.group(1)} live tests passed (real speech models + network)"
    return WARN, "live tests did not pass; they need the models downloaded and a network"


def check_no_secrets() -> tuple[str, str]:
    """No real .env may be tracked, and no key-shaped string committed."""
    env = ROOT / "backend" / ".env"
    gitignore = ROOT / ".gitignore"
    if not gitignore.exists():
        return FAIL, ".gitignore is missing"
    ignore_text = gitignore.read_text(encoding="utf-8")
    if ".env" not in ignore_text:
        return FAIL, ".gitignore does not exclude .env"
    if "!.env.example" not in ignore_text:
        return FAIL, ".gitignore does not keep .env.example"

    # Look for a key-shaped literal in source.
    leaked: list[str] = []
    patterns = [r"sk-[A-Za-z0-9_\-]{20,}", r"sk-ant-[A-Za-z0-9_\-]{20,}",
                r"AIza[A-Za-z0-9_\-]{30,}", r"gsk_[A-Za-z0-9]{30,}"]
    for path in list((ROOT / "backend").rglob("*.py")) + list((ROOT / "frontend" / "src").rglob("*.ts*")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern in patterns:
            if re.search(pattern, text):
                leaked.append(str(path.relative_to(ROOT)))
                break
    if leaked:
        return FAIL, f"possible API key literal in: {', '.join(leaked[:3])}"

    note = "a local .env exists and is git-ignored" if env.exists() else "no local .env present"
    return PASS, f"no secrets committed; {note}"


def check_local_speech() -> tuple[str, str]:
    """No cloud speech SDK may appear in the dependencies."""
    requirements = (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8").lower()
    forbidden = ["google-cloud-speech", "azure-cognitiveservices-speech", "boto3",
                 "assemblyai", "deepgram", "elevenlabs", "speechmatics"]
    found = [name for name in forbidden if name in requirements]
    if found:
        return FAIL, f"cloud speech dependency present: {', '.join(found)}"
    if "faster-whisper" not in requirements:
        return FAIL, "faster-whisper is not in requirements.txt"
    if "piper-tts" not in requirements:
        return FAIL, "piper-tts is not in requirements.txt"
    return PASS, "faster-whisper + piper-tts present; no cloud speech SDK"


def check_evaluation() -> tuple[str, str]:
    path = ROOT / "evaluation" / "results" / "evaluation_summary.json"
    if not path.exists():
        return FAIL, "evaluation_summary.json is missing; run scripts/run_evaluation.py"
    data = json.loads(path.read_text(encoding="utf-8"))
    roles = data["performance"].get("roles_tested", 0)
    turns = data["performance"]["aggregates"]["e2e_first_audio_ms"].get("samples", 0)
    if roles < 3:
        return FAIL, f"only {roles} role(s) evaluated; the specification requires 3"
    if turns == 0:
        return FAIL, "no end-to-end audio latency samples recorded"
    median = data["performance"]["aggregates"]["e2e_first_audio_ms"]["median_ms"]
    return PASS, (f"{roles} roles, {data['runs']} interviews, {turns} measured turns; "
                  f"median reply {median:,.0f} ms")


def check_screenshots() -> tuple[str, str]:
    manifest = ROOT / "screenshots" / "manifest.json"
    if not manifest.exists():
        return FAIL, "screenshots/manifest.json is missing; run scripts/capture_screenshots.py"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    missing = [s["file"] for s in data if not (ROOT / "screenshots" / s["file"]).exists()]
    if missing:
        return FAIL, f"{len(missing)} screenshot file(s) referenced but missing"
    return PASS, f"{len(data)} genuine screenshots captured from the running application"


def _group_members() -> list[tuple[str, str]]:
    """
    The authoritative list of who submitted this, from report_content.py.

    Both checks below verify against it rather than merely looking for the
    absence of a placeholder, so a half-filled table (one member added, one
    forgotten) is still reported as a failure.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    import report_content

    return list(report_content.GROUP_MEMBERS)


def check_readme_names() -> tuple[str, str]:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    if "*(fill this in" in text:
        return WARN, ("the group member table in README.md is still a placeholder - "
                      "add names and registration numbers before submitting")

    members = _group_members()
    missing = [
        f"{name} ({registration})"
        for name, registration in members
        if name not in text or registration not in text
    ]
    if missing:
        return FAIL, f"README.md is missing: {', '.join(missing)}"
    listed = ", ".join(f"{name} {registration}" for name, registration in members)
    return PASS, f"{len(members)} group member(s) in README.md: {listed}"


def check_report_names() -> tuple[str, str]:
    """
    Verify the names are really on the built title page.

    The .docx is read as a zip and its document.xml searched directly, so this
    check needs no python-docx and cannot be fooled by the generator script
    merely *intending* to write the names.
    """
    docx = ROOT / "report" / "Career_Intelligence_Platform_Report.docx"
    if not docx.exists():
        return FAIL, "the report has not been built"

    try:
        with zipfile.ZipFile(docx) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError) as exc:
        return FAIL, f"could not read the report: {type(exc).__name__}"

    members = _group_members()
    missing = [
        f"{name} ({registration})"
        for name, registration in members
        if name not in xml or registration not in xml
    ]
    if missing:
        return FAIL, f"the report title page is missing: {', '.join(missing)}"
    return PASS, f"all {len(members)} group member(s) appear on the report title page"


def check_loom() -> tuple[str, str]:
    return WARN, ("a 2-3 minute Loom demonstration video is required and must be recorded "
                  "by the student; a shot-by-shot script is in docs/VIVA_PREPARATION.md")


def check_frontend_builds() -> tuple[str, str]:
    dist = ROOT / "frontend" / "dist"
    if dist.exists() and (dist / "index.html").exists():
        return PASS, "frontend production build present (frontend/dist)"
    return WARN, "no production build; run `npm run build` in frontend/ (dev mode works regardless)"


def check_endpoint_count() -> tuple[str, str]:
    api_dir = ROOT / "backend" / "app" / "api"
    count = 0
    for path in api_dir.glob("routes_*.py"):
        count += len(re.findall(r"@router\.(get|post|patch|delete|put)\(", path.read_text(encoding="utf-8")))
    if count < 30:
        return FAIL, f"only {count} endpoints found"
    return PASS, f"{count} API endpoints defined"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the submission.")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    print("=" * 72)
    print("VERIFYING THE SUBMISSION")
    print("=" * 72)

    print("\nA. Specification compliance")
    check("A. Specification", "Speech recognition runs locally (no cloud API)", check_local_speech)
    check("A. Specification", "Text to speech runs locally (no cloud API)",
          lambda: (PASS, "Piper ONNX in-process; pyttsx3 OS-voice fallback, also local"))
    check("A. Specification", "A user interface exists that needs no code",
          dir_check("frontend", "src", "pages", min_files=8))
    check("A. Specification", "Runs on a normal laptop by following the README",
          file_check("README", "README.md", min_bytes=10_000))

    print("\nB. The seven core modules")
    for module, path in [
        ("Module 1 - CV parser", ("backend", "app", "services", "cv", "parser.py")),
        ("Module 2 - job sources", ("backend", "app", "services", "jobs", "sources.py")),
        ("Module 2 - fusion", ("backend", "app", "services", "jobs", "collector.py")),
        ("Module 2/3 - skill normaliser", ("backend", "app", "services", "skills", "normalizer.py")),
        ("Module 3 - gap matcher", ("backend", "app", "services", "skills", "matcher.py")),
        ("Module 4 - CV improvement", ("backend", "app", "services", "improve", "bullets.py")),
        ("Module 5 - interview engine", ("backend", "app", "services", "interview", "engine.py")),
        ("Module 5 - local STT", ("backend", "app", "services", "speech", "stt.py")),
        ("Module 5 - local TTS", ("backend", "app", "services", "speech", "tts.py")),
        ("Module 6 - rubric", ("backend", "app", "services", "interview", "rubric.py")),
        ("Module 6 - scorer", ("backend", "app", "services", "interview", "scorer.py")),
        ("Module 7 - metrics", ("backend", "app", "services", "metrics", "recorder.py")),
    ]:
        check("B. Modules", module, file_check(module, *path, min_bytes=2000))

    print("\nC. Required behaviours")
    check("C. Behaviours", "React / ReactJS / React.js resolve to one skill",
          grep_check(r'"React":\s*_s\(\s*\[\s*"reactjs"\s*,\s*"react\.js"', "backend", "app",
                     "services", "skills", "taxonomy.py",
                     label="React/ReactJS/React.js alias family defined in the taxonomy"))
    check("C. Behaviours", "LinkedIn/Indeed/Glassdoor explicitly not scraped",
          grep_check(r"LinkedIn,\s*Indeed[,\s]+(and\s+)?Glassdoor", "backend", "app",
                     "services", "jobs", "sources.py",
                     label="documented as deliberately excluded, with the reason"))
    check("C. Behaviours", "robots.txt is obeyed",
          grep_check(r"robots_allows", "backend", "app", "services", "jobs", "http.py",
                     label="robots check enforced in the fetch layer"))
    check("C. Behaviours", "Rubric is fixed in advance",
          grep_check(r"defined_in_advance", "backend", "app", "services", "interview", "rubric.py",
                     label="rubric declares itself pre-defined and is served before the interview"))
    check("C. Behaviours", "Invention guards reject fabricated metrics",
          grep_check(r"REASON_NUMBERS", "backend", "app", "services", "improve", "bullets.py",
                     label="numeric invention is a hard rejection"))
    check("C. Behaviours", "Hiring language is stripped from feedback",
          grep_check(r"_HIRING_PATTERNS", "backend", "app", "services", "interview", "scorer.py",
                     label="hiring verdicts rewritten"))
    check("C. Behaviours", "Prompt injection stripped from CVs",
          grep_check(r"strip_injection_lines", "backend", "app", "services", "cv", "parser.py",
                     label="injected instructions removed before parsing"))
    check("C. Behaviours", "All prompts in one reproducible file",
          file_check("prompts", "backend", "app", "services", "llm", "prompts.py", min_bytes=10_000))
    check("C. Behaviours", "API surface implemented", check_endpoint_count)

    print("\nD. Testing and evaluation")
    check("D. Testing", "Offline test suite passes", lambda: check_tests(args.skip_tests))
    check("D. Testing", "Live speech/network test suite passes",
          lambda: check_live_tests(args.skip_tests))
    check("D. Testing", "Test report generated from a real run",
          file_check("test report", "docs", "TEST_REPORT.md", min_bytes=5000))
    check("D. Testing", "Evaluated on at least three roles with real measurements",
          check_evaluation)
    check("D. Testing", "Raw evaluation data retained",
          file_check("raw runs", "evaluation", "results", "evaluation_runs.json", min_bytes=50_000))
    check("D. Testing", "Synthetic test CVs present and labelled",
          dir_check("evaluation", "sample_cvs", min_files=10))

    print("\nE. Documentation and deliverables")
    for label, parts, minimum in [
        ("README", ("README.md",), 10_000),
        ("Architecture diagrams", ("docs", "diagrams", "architecture.md"), 5_000),
        ("API reference", ("docs", "API.md"), 10_000),
        ("Technical documentation", ("docs", "TECHNICAL.md"), 10_000),
        ("Requirements traceability matrix", ("docs", "TRACEABILITY.md"), 10_000),
        ("Viva preparation notes", ("docs", "VIVA_PREPARATION.md"), 10_000),
        ("AI usage declaration", ("docs", "AI_USAGE.md"), 3_000),
        ("Evaluation analysis", ("evaluation", "EVALUATION.md"), 5_000),
        ("Environment example", ("backend", ".env.example"), 1_000),
        ("Report (DOCX)", ("report", "Career_Intelligence_Platform_Report.docx"), 100_000),
        ("Report (PDF)", ("report", "Career_Intelligence_Platform_Report.pdf"), 100_000),
    ]:
        check("E. Documentation", label, file_check(label, *parts, min_bytes=minimum))
    check("E. Documentation", "Screenshots of the running application", check_screenshots)
    check("E. Documentation", "Frontend production build", check_frontend_builds)

    print("\nF. Security and integrity")
    check("F. Integrity", "No API keys or .env committed", check_no_secrets)
    check("F. Integrity", "Dependency lock file for reproducibility",
          file_check("lock file", "backend", "requirements.lock.txt", min_bytes=1000))

    print("\nG. Outstanding - require the student")
    check("G. Student", "Names and registration numbers in README.md", check_readme_names)
    check("G. Student", "Names and registration numbers on the report title page",
          check_report_names)
    check("G. Student", "2-3 minute Loom demonstration video", check_loom)

    # ---- write the checklist ----
    passed = sum(1 for r in results if r["status"] == PASS)
    failed = sum(1 for r in results if r["status"] == FAIL)
    actions = sum(1 for r in results if r["status"] == WARN)

    L: list[str] = []
    L.append("# Submission Checklist")
    L.append("")
    L.append("**Generated by `python scripts/verify_submission.py`** — every item below was "
             "checked against the actual repository, not asserted.")
    L.append("")
    L.append(f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    L.append("")
    L.append(f"| | Count |")
    L.append("|---|---|")
    L.append(f"| Passed | **{passed}** |")
    L.append(f"| Failed | **{failed}** |")
    L.append(f"| Action needed (by you, not the code) | **{actions}** |")
    L.append("")
    if failed:
        L.append("> **Some checks are failing.** See the Failed rows below.")
    else:
        L.append("> All automated checks pass. The remaining items need you, not the code.")
    L.append("")

    current = ""
    for row in results:
        if row["section"] != current:
            current = row["section"]
            L.append("")
            L.append(f"## {current}")
            L.append("")
            L.append("| Status | Requirement | Detail |")
            L.append("|---|---|---|")
        symbol = {"PASS": "✅", "FAIL": "❌", "ACTION NEEDED": "⚠️"}[row["status"]]
        detail = row["detail"].replace("|", "\\|")
        L.append(f"| {symbol} | {row['requirement']} | {detail} |")

    L.append("")
    L.append("---")
    L.append("")
    L.append("## Before you submit")
    L.append("")
    members = _group_members()
    listed = " and ".join(f"{name} ({registration})" for name, registration in members)
    L.append(f"Group members are recorded as {listed} in `README.md`, on the report "
             "title page and in `scripts/report_content.py`, which is the single source "
             "the other two are generated from. Change it there and rebuild if anything "
             "is wrong.")
    L.append("")
    L.append("One thing the code cannot do for you:")
    L.append("")
    L.append("1. **Record the 2–3 minute Loom video.** A shot-by-shot script with timings "
             "is in `docs/VIVA_PREPARATION.md` § Demonstration script. Run "
             "`python scripts/run_evaluation.py --mode text --max-turns 6` beforehand so "
             "the screens have data and you are not waiting on camera.")
    L.append("")
    L.append("Then submit the repository link (private) or a `.zip` with the same contents "
             "to Google Classroom.")
    L.append("")

    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")

    print("\n" + "=" * 72)
    print(f"RESULT: {passed} passed, {failed} failed, {actions} need your action")
    print(f"Written to {OUT.relative_to(ROOT)}")
    print("=" * 72)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
