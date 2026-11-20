"""
Regression tests for scripts/_console.py.

These exist because a real, paid-for evaluation run died on a single character.
A 16-turn Groq run aborted five turns into the first of three roles with:

    UnicodeEncodeError: 'charmap' codec can't encode character '\u2011'
    in position 58: character maps to <undefined>

U+2011 is a NON-BREAKING HYPHEN. The model wrote it inside "full-stack"; the
harness printed a preview of the question; stdout was redirected to a file, so
Windows gave it the cp1252 ANSI code page, which has no U+2011; `print` raised;
the run ended. The API tokens were already spent.

The important subtlety -- and the reason this went unnoticed through every
earlier run -- is that writing to a real Windows *console* does not fail.
Python 3.6+ uses the wide-character console API, which takes any Unicode
regardless of `chcp`. The bug appears only once output is redirected, which is
precisely what an unattended run does. So these tests do not use the ambient
stdout: they build a cp1252 text stream explicitly, which is what the failing
process actually had.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import _console  # noqa: E402


def cp1252_stream() -> io.TextIOWrapper:
    """A text stream exactly as Windows hands one to a redirected process."""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="")


# The literal string from the log of the run that died, trimmed to the part
# that mattered. Keep the real characters here rather than escapes, so the test
# fails if this file's own encoding is ever mishandled.
KILLER = "Thanks! I\u2011m excited \u2014 \u201cwhat\u2019s next\u201d\u2026 90\u00b0 \u2192 done"


def test_the_exact_character_crashes_an_unguarded_cp1252_stream() -> None:
    """
    Proof the bug is real and not theoretical.

    If this test ever stops failing-to-write, the premise of this whole module
    has changed and the guard can be reconsidered.
    """
    stream = cp1252_stream()
    with pytest.raises(UnicodeEncodeError):
        stream.write("full\u2011stack")
        stream.flush()


def test_ascii_safe_makes_the_killer_line_encodable() -> None:
    folded = _console.ascii_safe(KILLER)
    # The point: it now fits through the code page that could not take it.
    folded.encode("cp1252")
    # ...and it is still readable, not a row of question marks.
    assert "I-m excited -- \"what's next\"..." in folded
    assert "?" not in folded


def test_ascii_safe_does_not_touch_text_that_was_already_fine() -> None:
    plain = "Q5 [technical] 6970ms: walk me through the coverage gate (87% -> 91%)."
    assert _console.ascii_safe(plain) == plain


def test_ascii_safe_folds_every_character_in_its_table_to_cp1252_safe_ascii() -> None:
    for code_point, replacement in _console._FOLD.items():
        folded = _console.ascii_safe(chr(code_point))
        assert folded == replacement
        folded.encode("ascii")  # must be ASCII, not merely cp1252-encodable


def test_install_makes_a_cp1252_stream_lossy_instead_of_fatal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    The safety net. `ascii_safe` only covers characters we anticipated; a model
    can emit a CJK name or an emoji at any time, and that must not end the run
    either.
    """
    stream = cp1252_stream()
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", cp1252_stream())

    _console.install()

    # Nothing we anticipated: a Chinese name and an emoji.
    print("candidate \u4e2d\u6587 \U0001f600 and a hyphen\u2011here")
    sys.stdout.flush()  # the write is where it would have raised

    assert sys.stdout.encoding == "utf-8"
    assert sys.stdout.errors == "replace"


def test_install_is_idempotent_and_safe_on_an_unreconfigurable_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NoReconfigure(io.StringIO):
        reconfigure = None  # type: ignore[assignment]

    monkeypatch.setattr(sys, "stdout", NoReconfigure())
    monkeypatch.setattr(sys, "stderr", NoReconfigure())
    _console.install()
    _console.install()  # must not raise on the second call either


def test_the_harness_log_function_is_actually_guarded() -> None:
    """
    The module being correct is not enough -- the call site has to use it.
    This asserts the wiring that was missing when the run died.
    """
    source = (SCRIPTS_DIR / "run_evaluation.py").read_text(encoding="utf-8")
    assert "_console.install()" in source, "install() must run before any output"
    assert "_console.ascii_safe(message)" in source, "log() must fold model text"

    captures = (SCRIPTS_DIR / "capture_screenshots.py").read_text(encoding="utf-8")
    assert "_console.install()" in captures
    assert "_console.ascii_safe(message)" in captures


def test_recorded_results_keep_the_original_text_not_the_folded_one() -> None:
    """
    The fold is a display concession. If it ever leaked into the stored
    results, the evaluation would be quietly misreporting what the model said.
    """
    source = (SCRIPTS_DIR / "run_evaluation.py").read_text(encoding="utf-8")
    # Every ascii_safe *call* must be inside the printing helper, nowhere
    # else (count calls, not mentions -- comments reference it too).
    assert source.count("_console.ascii_safe(") == 1, (
        "ascii_safe belongs only in log(); recorded data must stay verbatim"
    )
    # And the files that hold the results must be written as UTF-8.
    for marker in ("runs_path.write_text", "summary_path.write_text"):
        assert marker in source
    assert 'encoding="utf-8"' in source
