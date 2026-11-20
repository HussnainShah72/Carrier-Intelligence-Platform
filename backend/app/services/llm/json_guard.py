"""
Defences against the two ways LLM output breaks an application:
invalid JSON, and valid JSON that says things the model made up.

`parse_json_payload()` handles the syntax problem with a repair cascade.
`enforce_grounding()` handles the honesty problem by checking that every claim
the model returns can be traced back to text the user actually supplied.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Sequence

from app.core.errors import LLMOutputError
from app.core.logging_setup import get_logger

log = get_logger(__name__)

_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)\s*```", re.S)
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")
_SMART_QUOTES = {"“": '"', "”": '"', "‘": "'", "’": "'"}
_NUMBER_WORDS = re.compile(r"\b(NaN|Infinity|-Infinity)\b")


def parse_json_payload(text: str, *, expect: type = dict) -> Any:
    """
    Pull a JSON value out of whatever the model actually produced.

    Repair cascade (each step is attempted in order):
      1. straight json.loads
      2. strip ``` fences / leading prose
      3. slice from the first { or [ to its matching close brace
      4. fix smart quotes, trailing commas, NaN/Infinity literals
      5. escape raw newlines that appear inside string literals

    Raises LLMOutputError if nothing yields the expected type -- callers treat
    that as "the model failed", not as data.
    """
    if text is None:
        raise LLMOutputError("The language model returned an empty response.")

    raw = str(text).strip()
    if not raw:
        raise LLMOutputError("The language model returned an empty response.")

    candidates: list[str] = [raw]

    fenced = _FENCE_RE.search(raw)
    if fenced:
        candidates.append(fenced.group(1).strip())

    sliced = _slice_balanced(raw)
    if sliced:
        candidates.append(sliced)

    for candidate in list(candidates):
        candidates.append(_repair(candidate))

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            value = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(value, expect):
            return value
        # A single-element list wrapping the object we wanted is common.
        if expect is dict and isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
            return value[0]

    preview = raw[:220].replace("\n", " ")
    log.warning("Unparseable model output (expected %s): %s", expect.__name__, preview)
    raise LLMOutputError(
        "The language model did not return valid structured data. Please try again.",
        details={"preview": preview},
    )


def _slice_balanced(text: str) -> str:
    """Return the first balanced {...} or [...] block, ignoring braces in strings."""
    start = -1
    opener = ""
    for i, ch in enumerate(text):
        if ch in "{[":
            start, opener = i, ch
            break
    if start < 0:
        return ""

    closer = "}" if opener == "{" else "]"
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def _repair(text: str) -> str:
    if not text:
        return text
    out = text
    for bad, good in _SMART_QUOTES.items():
        out = out.replace(bad, good)
    out = _TRAILING_COMMA_RE.sub(r"\1", out)
    out = _NUMBER_WORDS.sub("null", out)
    return _escape_newlines_in_strings(out)


def _escape_newlines_in_strings(text: str) -> str:
    """Models often emit literal newlines inside a JSON string value."""
    out: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
                out.append(ch)
                continue
            if ch == "\\":
                escaped = True
                out.append(ch)
                continue
            if ch == '"':
                in_string = False
                out.append(ch)
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                continue
            if ch == "\t":
                out.append("\\t")
                continue
            out.append(ch)
            continue
        if ch == '"':
            in_string = True
        out.append(ch)
    return "".join(out)


# ---------------------------------------------------------------------------
# Shape coercion
# ---------------------------------------------------------------------------


def as_str_list(value: Any, *, limit: int = 60, max_len: int = 120) -> list[str]:
    """
    Coerce 'whatever the model sent' into a clean list of short strings.

    Accepts a list, a comma-separated string, or a list of {name: ...} objects,
    because all three show up in practice from the same prompt.
    """
    items: list[str] = []
    if value is None:
        return items

    if isinstance(value, str):
        parts = [p.strip() for p in re.split(r"[,;\n]+", value)]
        items = [p for p in parts if p]
    elif isinstance(value, dict):
        items = [str(v).strip() for v in value.values() if isinstance(v, (str, int, float))]
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            if isinstance(item, str):
                items.append(item.strip())
            elif isinstance(item, (int, float)):
                items.append(str(item))
            elif isinstance(item, dict):
                for key in ("name", "skill", "title", "value", "text", "label"):
                    if isinstance(item.get(key), str):
                        items.append(item[key].strip())
                        break
    else:
        items = [str(value).strip()]

    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        item = item.strip(" .;,-")
        if not item or len(item) > max_len:
            continue
        low = item.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def as_text(value: Any, *, default: str = "", max_len: int = 4000) -> str:
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        value = " ".join(str(v) for v in value)
    text = str(value).strip()
    return text[:max_len] if text else default


def as_float(value: Any, *, default: float = 0.0, lo: float | None = None, hi: float | None = None) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if out != out:  # NaN
        return default
    if lo is not None:
        out = max(lo, out)
    if hi is not None:
        out = min(hi, out)
    return out


def as_choice(value: Any, allowed: Sequence[str], *, default: str) -> str:
    if isinstance(value, str):
        low = value.strip().lower()
        for option in allowed:
            if low == option.lower():
                return option
        for option in allowed:  # tolerate "high priority" -> "high"
            if option.lower() in low:
                return option
    return default


def as_dict_list(value: Any, *, limit: int = 40) -> list[dict]:
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, dict)][:limit]


# ---------------------------------------------------------------------------
# Grounding / anti-hallucination
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "by", "at", "as",
    "is", "are", "was", "were", "be", "been", "being", "from", "that", "this", "these",
    "those", "it", "its", "my", "our", "their", "i", "we", "they", "he", "she", "you",
}

_NUMBER_IN_TEXT = re.compile(r"\d+(?:[.,]\d+)?\s*%?|\b\d+[kKmM]\b")


def numbers_in(text: str) -> set[str]:
    """Normalised numeric tokens, used to detect invented metrics."""
    out: set[str] = set()
    for match in _NUMBER_IN_TEXT.findall(text or ""):
        token = match.strip().lower().replace(" ", "").replace(",", "")
        if token:
            out.add(token)
            out.add(token.rstrip("%"))
    return out


def content_words(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9+#./-]{2,}", (text or "").lower())
    return {w for w in words if w not in _STOPWORDS}


def unsupported_numbers(candidate: str, sources: Sequence[str]) -> list[str]:
    """
    Numbers that appear in `candidate` but in none of the `sources`.

    This is the check that stops the CV-improvement module from fabricating
    "improved performance by 40%" when the original bullet had no metric.
    """
    source_numbers: set[str] = set()
    for src in sources:
        source_numbers |= numbers_in(src)
    found = numbers_in(candidate)
    return sorted(n for n in found if n not in source_numbers and n.rstrip("%") not in source_numbers)


def unsupported_terms(
    candidate: str,
    sources: Sequence[str],
    *,
    allowlist: Sequence[str] = (),
    min_length: int = 4,
) -> list[str]:
    """Content words in the output that no source text supports."""
    source_words: set[str] = set()
    for src in sources:
        source_words |= content_words(src)
    allowed = {a.lower() for a in allowlist}

    out: list[str] = []
    for word in sorted(content_words(candidate)):
        if len(word) < min_length or word in source_words or word in allowed:
            continue
        # Simple morphological back-off: "optimised" vs "optimise".
        if any(word.startswith(sw[:4]) and abs(len(word) - len(sw)) <= 4 for sw in source_words if len(sw) >= 4):
            continue
        out.append(word)
    return out


def enforce_grounding(
    items: Sequence[str],
    sources: Sequence[str],
    *,
    resolver: Callable[[str], str | None] | None = None,
) -> tuple[list[str], list[str]]:
    """
    Split `items` into (grounded, rejected) against the source texts.

    Used for CV skill extraction: a skill the model "found" that appears nowhere
    in the CV text is dropped rather than shown to the user as fact.
    """
    source_words: set[str] = set()
    source_blob = " ".join(sources).lower()
    for src in sources:
        source_words |= content_words(src)

    grounded: list[str] = []
    rejected: list[str] = []
    for item in items:
        probe = (resolver(item) if resolver else item) or item
        low = probe.lower().strip()
        if not low:
            continue
        if low in source_blob:
            grounded.append(item)
            continue
        tokens = content_words(low)
        if tokens and tokens <= source_words:
            grounded.append(item)
            continue
        # Acronym support: "NLP" grounded by "natural language processing".
        if len(low) <= 5 and low.replace(".", "") in source_blob.replace(".", ""):
            grounded.append(item)
            continue
        rejected.append(item)

    if rejected:
        log.info("Grounding filter dropped %d unsupported item(s): %s", len(rejected), rejected[:8])
    return grounded, rejected
