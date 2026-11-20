"""
Low-level text normalisation shared by the skill normaliser and the CV parser.

`normalise_key()` is the function that makes "React", "ReactJS", "React.js",
"React  JS" and "Experience with React (3+ years)" collapse to the same lookup
key.  It is deliberately small, deterministic and unit-tested: every later stage
(alias lookup, fuzzy match, vector match) depends on it behaving predictably.
"""

from __future__ import annotations

import re
import unicodedata

# Phrases recruiters wrap around a skill that carry no identity information.
_NOISE_PHRASES = [
    "hands on experience with",
    "hands-on experience with",
    "demonstrable experience in",
    "demonstrable experience with",
    "proven experience with",
    "proven experience in",
    "proven track record in",
    "practical experience with",
    "working knowledge of",
    "solid understanding of",
    "deep understanding of",
    "strong understanding of",
    "good understanding of",
    "basic understanding of",
    "clear understanding of",
    "an understanding of",
    "understanding of",
    "strong knowledge of",
    "good knowledge of",
    "sound knowledge of",
    "knowledge of",
    "familiarity with",
    "familiar with",
    "experience with",
    "experience in",
    "experience of",
    "experienced in",
    "experienced with",
    "exposure to",
    "proficiency in",
    "proficiency with",
    "proficient in",
    "proficient with",
    "expertise in",
    "expertise with",
    "expert in",
    "competency in",
    "competence in",
    "skilled in",
    "skills in",
    "ability to use",
    "ability to work with",
    "ability to",
    "background in",
    "track record in",
    "comfortable with",
    "confident with",
    "well versed in",
    "well-versed in",
    "versed in",
    "fluency in",
    "fluent in",
    "certified in",
    "certification in",
    "trained in",
    "must have",
    "nice to have",
    "preferred",
    "required",
    "desirable",
    "a plus",
    "bonus",
]

# Single-word intensifiers / qualifiers.
_NOISE_WORDS = {
    "strong",
    "excellent",
    "solid",
    "advanced",
    "intermediate",
    "basic",
    "beginner",
    "expert",
    "deep",
    "good",
    "great",
    "sound",
    "practical",
    "proven",
    "demonstrable",
    "extensive",
    "significant",
    "substantial",
    "relevant",
    "professional",
    "commercial",
    "modern",
    "various",
    "multiple",
    "several",
    "etc",
    "ideally",
    "preferably",
    "plus",
    "bonus",
    "desirable",
    "mandatory",
    "essential",
    "min",
    "minimum",
    "maximum",
    "least",
    "using",
    "use",
    "used",
    "work",
    "working",
    "worked",
    "the",
    "a",
    "an",
    "of",
    "in",
    "with",
    "and",
    "or",
    "to",
    "for",
    "on",
    "at",
    "by",
    "as",
    "is",
    "are",
    "be",
    "skill",
    "skills",
    "knowledge",
    "experience",
    "ability",
    "understanding",
    "proficiency",
    "familiarity",
    "expertise",
    "technologies",
    "technology",
    "tools",
    "tool",
    "stack",
    "frameworks",
    "framework",
    "libraries",
    "library",
    "concepts",
    "concept",
    "principles",
    "fundamentals",
    "best",
    "practices",
}

# "3+ years", "5 yrs", "2-4 years of"
_YEARS_RE = re.compile(r"\b\d+\s*\+?\s*(?:-\s*\d+\s*)?(?:years?|yrs?|y)\b", re.I)
_PAREN_RE = re.compile(r"\(([^)]*)\)")
_BRACKET_RE = re.compile(r"\[[^\]]*\]")
_MULTISPACE_RE = re.compile(r"\s+")
# Bullet glyphs, plus list numbering ONLY in its real form ("1." / "2)").
# A bare leading digit must survive: stripping it turned "5+ years of Java"
# into "+ years of Java", which then defeated the year-removal pattern below.
_BULLET_RE = re.compile(r"^(?:[\s\-•‣●▪·\*–—→>]+|\d{1,2}[.)](?=\s))+")

# Characters that are part of a technology's identity and must survive.
_KEEP_CHARS = set("+#.&/")

_UNICODE_FIXES = {
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "–": "-",
    "—": "-",
    "…": "...",
    " ": " ",
    "​": "",
    "﻿": "",
    "•": " ",
}


def clean_unicode(text: str) -> str:
    """Normalise unicode punctuation that PDF/DOCX extraction leaves behind."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    for bad, good in _UNICODE_FIXES.items():
        text = text.replace(bad, good)
    # Drop control characters except tab/newline.
    return "".join(ch for ch in text if ch in "\t\n" or unicodedata.category(ch)[0] != "C")


def strip_bullet(line: str) -> str:
    """Remove a leading bullet glyph / list numbering from a CV line."""
    return _BULLET_RE.sub("", line or "").strip()


def surface_form(raw: str) -> str:
    """
    Tidy a skill string for *display* without destroying its casing.

    "  experience with  REACT.JS (3+ years) " -> "REACT.JS"
    """
    if not raw:
        return ""
    text = clean_unicode(str(raw))
    text = strip_bullet(text)
    text = _YEARS_RE.sub(" ", text)
    text = _BRACKET_RE.sub(" ", text)
    # Keep a short parenthetical aside ("(AWS)"), drop long ones and anything
    # left empty after the year pattern above has been removed.
    text = _PAREN_RE.sub(
        lambda m: f" ({m.group(1).strip()}) " if 0 < len(m.group(1).strip()) <= 18 else " ",
        text,
    )
    text = text.strip().strip(",;:-–— ").strip()

    lowered = text.lower()
    for phrase in _NOISE_PHRASES:
        if lowered.startswith(phrase + " "):
            text = text[len(phrase) :].strip()
            lowered = text.lower()
    return _MULTISPACE_RE.sub(" ", text).strip(" .,;:-").strip()


def normalise_key(raw: str, *, strip_noise: bool = True) -> str:
    """
    Produce the canonical *lookup key* for a skill string.

    Rules, applied in order:
      1. unicode clean + lowercase
      2. drop "3+ years", bracketed asides, bullet glyphs
      3. remove recruiter noise phrases ("experience with ...")
      4. keep only [a-z0-9] plus the identity characters + # . & /
      5. drop noise words, de-duplicate, sort-stable join
      6. collapse "js"/"dot js" style suffixes so react/reactjs/react.js agree

    `strip_noise=False` skips step 5.  That matters when normalising a
    *taxonomy alias* rather than a user's messy input: stripping noise words
    from the alias "security plus" leaves "security", which would then match
    every job advert containing the word "security".  See `taxonomy` for how
    the two variants are indexed.

    >>> normalise_key("React.js")
    'react'
    >>> normalise_key("Experience with ReactJS (3+ years)")
    'react'
    >>> normalise_key("security plus", strip_noise=False)
    'security plus'
    """
    if not raw:
        return ""

    text = clean_unicode(str(raw)).lower()
    text = strip_bullet(text)
    text = _YEARS_RE.sub(" ", text)
    text = _BRACKET_RE.sub(" ", text)
    text = _PAREN_RE.sub(" ", text)

    for phrase in _NOISE_PHRASES:
        text = text.replace(phrase, " ")

    # Normalise separators but keep identity characters.
    cleaned_chars = []
    for ch in text:
        if ch.isalnum() or ch in _KEEP_CHARS:
            cleaned_chars.append(ch)
        else:
            cleaned_chars.append(" ")
    text = _MULTISPACE_RE.sub(" ", "".join(cleaned_chars)).strip()

    # Token-level clean-up.
    tokens: list[str] = []
    for token in text.split():
        token = token.strip(".,/&")
        if not token:
            continue
        if strip_noise and token in _NOISE_WORDS:
            continue
        if token.isdigit():
            continue
        tokens.append(token)

    if not tokens:
        return ""

    # Collapse framework suffixes: react js / reactjs / react.js -> react
    tokens = _collapse_js_suffix(tokens)

    # De-duplicate while preserving order.
    seen: set[str] = set()
    unique = [t for t in tokens if not (t in seen or seen.add(t))]
    return " ".join(unique)


def _collapse_js_suffix(tokens: list[str]) -> list[str]:
    """
    Treat the JS-ecosystem naming variants as one name.

    react / reactjs / react.js / react js  ->  react
    node / nodejs / node.js                ->  node
    Single-token "js" on its own is preserved (it means JavaScript).
    """
    out: list[str] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]

        # "react" + "js"  (two tokens)
        if i + 1 < len(tokens) and tokens[i + 1] in ("js", "javascript") and len(token) > 2:
            out.append(token.rstrip("."))
            i += 2
            continue

        # "react.js" / "reactjs" (one token)
        if token.endswith(".js") and len(token) > 3:
            out.append(token[:-3])
            i += 1
            continue
        # "ejs" is a real template engine, so only the bare token is protected.
        if token.endswith("js") and len(token) > 4 and token != "ejs":
            stem = token[:-2]
            # Only strip when the stem looks like a real word, not e.g. "axis".
            if stem.isalpha():
                out.append(stem)
                i += 1
                continue

        out.append(token.rstrip("."))
        i += 1
    return out


def char_ngrams(text: str, n: int = 3) -> set[str]:
    """Character n-gram set, used for the cheap Jaccard pre-filter."""
    padded = f"  {text}  "
    return {padded[i : i + n] for i in range(len(padded) - n + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def split_skill_list(text: str) -> list[str]:
    """
    Split a free-text skill line into candidate skills.

    "Python, Java and C++ | SQL; Docker/Kubernetes"
       -> ['Python', 'Java', 'C++', 'SQL', 'Docker', 'Kubernetes']

    '/' is only treated as a separator when both sides look like separate
    technologies, so "CI/CD" and "TCP/IP" survive intact.
    """
    if not text:
        return []

    text = clean_unicode(text)
    parts = re.split(r"[,;|•\n\t]+|\s+/\s+|\s+and\s+|\s+&\s+", text)

    out: list[str] = []
    for part in parts:
        part = part.strip(" .-–—\t")
        if not part:
            continue
        if "/" in part and not _is_protected_slash(part):
            out.extend(p.strip() for p in part.split("/") if p.strip())
        else:
            out.append(part)
    return [p for p in out if p]


_PROTECTED_SLASH_KEYS = {
    "ci/cd",
    "tcp/ip",
    "pl/sql",
    "a/b",
    "and/or",
    "pub/sub",
    "material/ui",
    "i/o",
    "s/w",
    "h/w",
    "24/7",
    "udp/ip",
    "client/server",
    "ui/ux",
}


def _is_protected_slash(part: str) -> bool:
    """True when '/' is part of one term rather than a separator."""
    key = part.strip().lower()
    if key in _PROTECTED_SLASH_KEYS:
        return True
    # Both fragments very short -> almost certainly one abbreviation ("S/W").
    # Only *both*, so "R/Python" and "HTML/CSS" still split correctly.
    left, _, right = key.partition("/")
    return len(left.strip()) <= 2 and len(right.strip()) <= 2
