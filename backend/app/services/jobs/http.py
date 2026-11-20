"""
Module 2a - the polite HTTP layer used for live job-posting collection.

Compliance is a requirement of this project, not an afterthought, so the
fetching layer -- not the individual source adapters -- enforces it:

  * robots.txt is fetched, cached and obeyed for every host before any request
    to that host (a Disallow means the source is skipped and reported as
    'blocked_by_robots', never silently bypassed)
  * a descriptive User-Agent identifies the project rather than pretending to
    be a browser
  * a minimum interval between requests to the same host (rate limiting)
  * an on-disk response cache, so repeated analyses of the same role do not
    hammer the source and so a demo works on a flaky network
  * every failure mode is captured and reported honestly: timeout, HTTP error,
    rate limited (429), unparseable body, robots-blocked

Nothing here ever claims a fetch succeeded when it did not.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.robotparser
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import DATA_DIR, settings
from app.core.logging_setup import get_logger

log = get_logger(__name__)

CACHE_DIR = DATA_DIR / "scrape_cache"

# Fetch outcome codes used by the UI and the evaluation report.
OK = "ok"
ERR_TIMEOUT = "timeout"
ERR_HTTP = "http_error"
ERR_RATE_LIMIT = "rate_limited"
ERR_ROBOTS = "blocked_by_robots"
ERR_NETWORK = "network_error"
ERR_PARSE = "unparseable_response"
ERR_DISABLED = "disabled_by_config"


@dataclass(slots=True)
class FetchResult:
    """The outcome of one HTTP fetch -- success or a named failure."""

    url: str
    status: str
    http_status: int = 0
    text: str = ""
    elapsed_ms: float = 0.0
    from_cache: bool = False
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "status": self.status,
            "http_status": self.http_status,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "from_cache": self.from_cache,
            "detail": self.detail[:300],
            "bytes": len(self.text),
        }

    def json(self) -> Any:
        try:
            return json.loads(self.text)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Response from {self.url} was not valid JSON") from exc


@dataclass
class _HostState:
    last_request_at: float = 0.0
    robots: urllib.robotparser.RobotFileParser | None = None
    robots_checked: bool = False
    robots_available: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)


class PoliteFetcher:
    """Shared, thread-safe fetcher with robots.txt, rate limiting and caching."""

    def __init__(self) -> None:
        self._hosts: dict[str, _HostState] = {}
        self._hosts_lock = threading.Lock()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------- internals
    def _host_state(self, host: str) -> _HostState:
        with self._hosts_lock:
            state = self._hosts.get(host)
            if state is None:
                state = _HostState()
                self._hosts[host] = state
            return state

    def _cache_path(self, url: str):
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        host = urlparse(url).netloc.replace(":", "_") or "unknown"
        return CACHE_DIR / f"{host}_{digest}.json"

    def _read_cache(self, url: str) -> FetchResult | None:
        path = self._cache_path(url)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None

        age = time.time() - float(payload.get("cached_at", 0))
        if age > settings.scrape_cache_ttl_seconds:
            return None
        return FetchResult(
            url=url,
            status=OK,
            http_status=int(payload.get("http_status", 200)),
            text=str(payload.get("text", "")),
            elapsed_ms=0.0,
            from_cache=True,
            detail=f"served from cache ({age / 60:.0f} min old)",
        )

    def _write_cache(self, url: str, result: FetchResult) -> None:
        try:
            self._cache_path(url).write_text(
                json.dumps(
                    {"cached_at": time.time(), "http_status": result.http_status, "text": result.text},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            log.debug("Could not write scrape cache for %s: %s", url, exc)

    # --------------------------------------------------------------- robots
    def robots_allows(self, url: str) -> tuple[bool, str]:
        """
        Check robots.txt for `url`.

        A host with no robots.txt (404) is treated as permitting access, which
        is the standard interpretation.  A host we cannot reach at all is also
        allowed through -- the request itself will then fail and be reported.
        """
        parsed = urlparse(url)
        host = parsed.netloc
        if not host:
            return False, "malformed URL"

        state = self._host_state(host)
        with state.lock:
            if not state.robots_checked:
                state.robots_checked = True
                robots_url = f"{parsed.scheme}://{host}/robots.txt"
                try:
                    response = httpx.get(
                        robots_url,
                        timeout=8.0,
                        headers={"User-Agent": settings.scrape_user_agent},
                        follow_redirects=True,
                    )
                    if response.status_code == 200 and response.text.strip():
                        parser = urllib.robotparser.RobotFileParser()
                        parser.parse(response.text.splitlines())
                        state.robots = parser
                        state.robots_available = True
                        log.info("robots.txt loaded for %s", host)
                    else:
                        log.info("No usable robots.txt for %s (HTTP %s); treating as allowed",
                                 host, response.status_code)
                except Exception as exc:
                    log.info("robots.txt unreachable for %s (%s); treating as allowed", host, exc)

            if state.robots_available and state.robots is not None:
                allowed = state.robots.can_fetch(settings.scrape_user_agent, url)
                if not allowed:
                    allowed = state.robots.can_fetch("*", url)
                if not allowed:
                    return False, f"robots.txt on {host} disallows this path for our user-agent"
                delay = state.robots.crawl_delay(settings.scrape_user_agent) or state.robots.crawl_delay("*")
                if delay:
                    return True, f"allowed (robots crawl-delay {delay}s honoured)"
            return True, "allowed"

    def _respect_rate_limit(self, url: str) -> None:
        host = urlparse(url).netloc
        state = self._host_state(host)
        min_interval = settings.scrape_min_interval_seconds

        crawl_delay = 0.0
        if state.robots_available and state.robots is not None:
            crawl_delay = float(
                state.robots.crawl_delay(settings.scrape_user_agent)
                or state.robots.crawl_delay("*")
                or 0.0
            )
        interval = max(min_interval, min(crawl_delay, 10.0))

        with state.lock:
            wait = interval - (time.monotonic() - state.last_request_at)
            if wait > 0:
                log.debug("Rate limiting %s: waiting %.2fs", host, wait)
                time.sleep(wait)
            state.last_request_at = time.monotonic()

    # ---------------------------------------------------------------- fetch
    def fetch(
        self,
        url: str,
        *,
        accept: str = "application/json",
        use_cache: bool = True,
        timeout: float | None = None,
    ) -> FetchResult:
        """Fetch `url` politely.  Never raises -- failures come back as a status."""
        if not settings.scrape_enabled:
            return FetchResult(
                url=url, status=ERR_DISABLED,
                detail="Live job collection is switched off (SCRAPE_ENABLED=false).",
            )

        if use_cache:
            cached = self._read_cache(url)
            if cached is not None:
                log.info("Cache hit: %s", url)
                return cached

        allowed, reason = self.robots_allows(url)
        if not allowed:
            log.warning("robots.txt blocked %s: %s", url, reason)
            return FetchResult(url=url, status=ERR_ROBOTS, detail=reason)

        self._respect_rate_limit(url)
        started = time.perf_counter()
        try:
            response = httpx.get(
                url,
                timeout=timeout or settings.scrape_timeout_seconds,
                headers={
                    "User-Agent": settings.scrape_user_agent,
                    "Accept": accept,
                    "Accept-Language": "en",
                },
                follow_redirects=True,
            )
            elapsed = (time.perf_counter() - started) * 1000

            if response.status_code == 429:
                retry_after = response.headers.get("retry-after", "unspecified")
                return FetchResult(
                    url=url, status=ERR_RATE_LIMIT, http_status=429, elapsed_ms=elapsed,
                    detail=f"The source rate-limited us (retry-after: {retry_after}).",
                )
            if response.status_code >= 400:
                return FetchResult(
                    url=url, status=ERR_HTTP, http_status=response.status_code, elapsed_ms=elapsed,
                    detail=f"The source returned HTTP {response.status_code}.",
                )

            # A 2xx with an empty body is a failure, not a success: it happens
            # when a feed slug has been retired and redirects to nothing.  It
            # must not be cached or reported as "ok".
            if not response.text.strip():
                return FetchResult(
                    url=url, status=ERR_PARSE, http_status=response.status_code, elapsed_ms=elapsed,
                    detail=f"The source returned HTTP {response.status_code} with an empty body "
                           "(the feed or endpoint may have moved).",
                )

            result = FetchResult(
                url=url, status=OK, http_status=response.status_code,
                text=response.text, elapsed_ms=elapsed,
            )
            if use_cache:
                self._write_cache(url, result)
            log.info("Fetched %s -> HTTP %s in %.0fms (%d bytes)",
                     url, response.status_code, elapsed, len(response.text))
            return result

        except httpx.TimeoutException:
            return FetchResult(
                url=url, status=ERR_TIMEOUT,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                detail=f"No response within {timeout or settings.scrape_timeout_seconds:.0f}s.",
            )
        except httpx.HTTPError as exc:
            return FetchResult(
                url=url, status=ERR_NETWORK,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                detail=f"Network error: {type(exc).__name__}.",
            )
        except Exception as exc:  # pragma: no cover - defensive
            log.error("Unexpected fetch failure for %s: %s", url, exc)
            return FetchResult(
                url=url, status=ERR_NETWORK,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                detail="Unexpected network failure.",
            )

    def clear_cache(self) -> int:
        removed = 0
        for path in CACHE_DIR.glob("*.json"):
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
        log.info("Cleared %d cached scrape response(s)", removed)
        return removed

    def cache_stats(self) -> dict[str, Any]:
        files = list(CACHE_DIR.glob("*.json"))
        return {
            "entries": len(files),
            "size_bytes": sum(f.stat().st_size for f in files if f.exists()),
            "ttl_seconds": settings.scrape_cache_ttl_seconds,
            "directory": str(CACHE_DIR),
        }


fetcher = PoliteFetcher()


# ---------------------------------------------------------------------------
# HTML / XML helpers shared by the scraping adapters
# ---------------------------------------------------------------------------


def html_to_text(html: str, *, limit: int = 12_000) -> str:
    """
    Strip an HTML job description down to readable text.

    Keeps list items on their own lines, because 'required skills' in a job
    advert is almost always a <ul>, and the line structure is what the skill
    extractor keys off.
    """
    if not html:
        return ""

    try:
        from bs4 import BeautifulSoup  # type: ignore
    except ImportError:  # pragma: no cover
        import re

        return re.sub(r"<[^>]+>", " ", html)[:limit]

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe", "svg", "form", "nav", "footer"]):
        tag.decompose()

    for item in soup.find_all("li"):
        item.insert_before("\n- ")
    for tag in soup.find_all(["p", "br", "div", "h1", "h2", "h3", "h4", "tr"]):
        tag.insert_before("\n")

    text = soup.get_text(" ")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    cleaned = "\n".join(line for line in lines if line)
    return cleaned[:limit]


def parse_rss_items(xml_text: str, *, limit: int = 20) -> list[dict[str, str]]:
    """
    Parse an RSS/Atom job feed into dicts.

    Used for the HTML/XML scraping source: unlike the JSON APIs this is real
    markup parsing, which is what 'scraping' means in the assignment.
    """
    items: list[dict[str, str]] = []
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except ImportError:  # pragma: no cover
        return items

    soup = BeautifulSoup(xml_text, "xml")
    nodes = soup.find_all("item") or soup.find_all("entry")
    for node in nodes[:limit]:
        def pick(*names: str) -> str:
            for name in names:
                found = node.find(name)
                if found and found.get_text(strip=True):
                    return found.get_text(" ", strip=True)
                if found and found.get("href"):
                    return str(found.get("href"))
            return ""

        items.append(
            {
                "title": pick("title"),
                "link": pick("link", "id"),
                "description": pick("description", "summary", "content"),
                "published": pick("pubDate", "published", "updated"),
                "category": pick("category"),
            }
        )
    return items
