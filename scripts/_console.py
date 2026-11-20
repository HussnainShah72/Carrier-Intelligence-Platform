"""
Console output that survives a legacy Windows code page.

Why this module exists
----------------------
Language models write typographic Unicode: curly quotes, en dashes, ellipses,
and -- the one that actually broke a run -- U+2011 NON-BREAKING HYPHEN, as in
"full-stack" with a hyphen that will not line-break. Windows redirects a
process's stdout to a file using the ANSI code page (cp1252 on this machine),
and cp1252 has no U+2011. Printing a progress line that quotes the model then
raises:

    UnicodeEncodeError: 'charmap' codec can't encode character '\u2011'
    in position 58: character maps to <undefined>

That is not a cosmetic problem. It is raised by the `print` itself, so it
propagates out of whatever was logging progress and aborts the work. It cost a
real 16-turn evaluation run, which died five turns into the first of three
roles -- after the API calls had already been spent -- while printing a preview
of an interview question. The characters are not in our control: they come from
the model, so any provider swap can reintroduce them at any time.

Note that the console itself is usually fine. Python 3.6+ writes to a Windows
*console* through the wide-character API, which handles Unicode whatever `chcp`
says. The failure appears only once output is redirected -- which is exactly
what long unattended runs do, and exactly when nobody is watching to notice.

Two layers, because neither is sufficient alone
-----------------------------------------------
`install()` makes the streams lossy instead of fatal. It is the safety net: it
covers every `print` in the process, including ones in libraries and ones added
later by someone who has never heard of this module.

`ascii_safe()` folds the common typographic characters to ASCII so that output
stays *readable* rather than merely non-fatal -- `install()` alone would turn a
quoted question into "I?m excited" or mojibake. It is for display only. The
recorded results and reports keep the original text, because the original is
what the model actually said.
"""

from __future__ import annotations

import sys

#: Typographic characters -> ASCII. Deliberately conservative: it covers what
#: models and job postings emit in English prose, and leaves everything else
#: (accented names, CJK, emoji) to `install()`, which will not crash on them.
#: Keys are code points so the table can be handed straight to `str.translate`.
_FOLD: dict[int, str] = {
    # dashes and hyphens
    0x2010: "-",    # hyphen
    0x2011: "-",    # non-breaking hyphen  <- the one that broke the run
    0x2012: "-",    # figure dash
    0x2013: "-",    # en dash
    0x2014: "--",   # em dash
    0x2015: "--",   # horizontal bar
    0x2212: "-",    # minus sign
    # quotes
    0x2018: "'", 0x2019: "'", 0x201A: "'", 0x201B: "'",
    0x201C: '"', 0x201D: '"', 0x201E: '"', 0x201F: '"',
    0x2032: "'", 0x2033: '"',
    0x00AB: '"', 0x00BB: '"',
    # spaces that are not a plain space
    0x00A0: " ",    # no-break space
    0x2002: " ", 0x2003: " ", 0x2007: " ", 0x2008: " ",
    0x2009: " ", 0x200A: " ", 0x202F: " ", 0x205F: " ", 0x3000: " ",
    # zero-width: drop entirely, they only confuse a terminal
    0x200B: "", 0x200C: "", 0x200D: "", 0x2060: "", 0xFEFF: "",
    # miscellaneous prose furniture
    0x2026: "...",  # ellipsis
    0x2022: "*",    # bullet
    0x00B7: "*",    # middle dot
    0x2122: "(tm)",
    0x00AE: "(R)",
    0x00A9: "(c)",
    0x2190: "<-", 0x2192: "->", 0x21D2: "=>",
    0x2264: "<=", 0x2265: ">=", 0x2248: "~=", 0x00D7: "x",
}


def ascii_safe(text: str) -> str:
    """
    Fold typographic Unicode in `text` down to ASCII equivalents.

    For console display only -- never for stored results. Characters outside
    the fold table are returned unchanged; `install()` is what keeps those from
    raising.
    """
    return text.translate(_FOLD)


def install() -> None:
    """
    Make `sys.stdout` / `sys.stderr` incapable of raising UnicodeEncodeError.

    Prefers UTF-8, which is the correct encoding when output is redirected to a
    file and is what every reader of these logs expects. `errors="replace"` is
    the part that actually guarantees no crash, and is kept even if the
    encoding change is refused.

    Safe to call more than once, and a no-op on a stream that cannot be
    reconfigured (one already replaced by a test harness, a pytest capture
    object, or a plain file object).
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError, AttributeError):
            # The stream would not take a new encoding (already detached, or
            # not a TextIOWrapper). Settle for not crashing.
            try:
                reconfigure(errors="replace")
            except Exception:
                pass
