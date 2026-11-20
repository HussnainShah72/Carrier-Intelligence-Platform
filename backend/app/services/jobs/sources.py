"""
Module 2a - live job-posting sources.

Each source is a small adapter: build a URL for the user's role, fetch it
through the polite fetcher, and map the response onto `JobPosting`.

Why these sources
-----------------
The large job boards (LinkedIn, Indeed, Glassdoor) forbid automated access in
their terms of service and block it technically.  Scraping them would be both a
breach of contract and, for this project, dishonest engineering -- it would work
on the demo laptop and fail for a marker.  So the sources below were chosen
because each one *publishes* its listings for programmatic use:

  Remotive        documented public JSON API
  Arbeitnow       documented public job-board API
  Jobicy          documented public JSON API (v2)
  Himalayas       documented public jobs API
  Remote OK       public JSON feed (attribution required -- honoured in the UI)
  WeWorkRemotely  public RSS feed -- parsed as markup, i.e. genuine scraping

The limitation this creates is stated plainly in the README and the report:
these boards skew towards remote and technology roles, so coverage for local,
non-technical or highly regulated roles is thin.  That is a real finding of the
evaluation, not something to paper over.
"""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import quote_plus

from app.core.config import settings
from app.core.logging_setup import get_logger
from app.services.jobs.http import FetchResult, fetcher, html_to_text, parse_rss_items

log = get_logger(__name__)


@dataclass(slots=True)
class JobPosting:
    """One live job advert, normalised across sources."""

    source: str
    source_type: str          # "json_api" | "rss_scrape" | "html_scrape"
    title: str
    company: str = ""
    location: str = ""
    url: str = ""
    posted_at: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_type": self.source_type,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "url": self.url,
            "posted_at": self.posted_at,
            "description": self.description,
            "description_excerpt": self.description[:420],
            "tags": self.tags,
            "skills": self.skills,
        }


@dataclass(slots=True)
class SourceReport:
    """Honest, per-source account of what happened -- shown in the UI."""

    name: str
    source_type: str
    url: str
    status: str
    postings_found: int = 0
    postings_kept: int = 0
    elapsed_ms: float = 0.0
    from_cache: bool = False
    detail: str = ""
    attribution: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source_type": self.source_type,
            "url": self.url,
            "status": self.status,
            "postings_found": self.postings_found,
            "postings_kept": self.postings_kept,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "from_cache": self.from_cache,
            "detail": self.detail[:300],
            "attribution": self.attribution,
        }


# ---------------------------------------------------------------------------
# Relevance filtering
# ---------------------------------------------------------------------------

_ROLE_STOPWORDS = {
    "senior", "junior", "lead", "principal", "staff", "graduate", "entry",
    "level", "mid", "i", "ii", "iii", "intern", "trainee", "remote", "the", "of", "and", "a", "an",
}


def role_tokens(role_title: str) -> list[str]:
    """Significant words of the role title, used for relevance scoring."""
    words = re.findall(r"[a-z0-9+#]+", (role_title or "").lower())
    return [w for w in words if w not in _ROLE_STOPWORDS and len(w) > 1]


def relevance_score(posting: JobPosting, tokens: list[str]) -> float:
    """
    0..1 relevance of a posting to the requested role.

    Title matches weigh far more than description matches, because a posting
    whose body merely mentions "python" is not a Python role.
    """
    if not tokens:
        return 0.5

    title_low = (posting.title or "").lower()
    tags_low = " ".join(posting.tags).lower()
    body_low = (posting.description or "")[:4000].lower()

    title_hits = sum(1 for t in tokens if t in title_low)
    tag_hits = sum(1 for t in tokens if t in tags_low)
    body_hits = sum(1 for t in tokens if t in body_low)

    score = (title_hits / len(tokens)) * 0.65 + (tag_hits / len(tokens)) * 0.2 + (body_hits / len(tokens)) * 0.15
    if title_hits == len(tokens):
        score = min(1.0, score + 0.2)
    return round(min(1.0, score), 3)


MIN_RELEVANCE = 0.22


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class JobSource:
    name: str = "source"
    source_type: str = "json_api"
    attribution: str = ""
    homepage: str = ""

    def build_url(self, role_title: str, location: str = "") -> str:
        raise NotImplementedError

    def parse(self, result: FetchResult) -> list[JobPosting]:
        raise NotImplementedError

    def collect(self, role_title: str, location: str = "", *, limit: int | None = None) -> tuple[list[JobPosting], SourceReport]:
        limit = limit or settings.scrape_per_source_limit
        url = self.build_url(role_title, location)
        accept = "application/rss+xml, application/xml" if self.source_type == "rss_scrape" else "application/json"
        result = fetcher.fetch(url, accept=accept)

        report = SourceReport(
            name=self.name,
            source_type=self.source_type,
            url=url,
            status=result.status,
            elapsed_ms=result.elapsed_ms,
            from_cache=result.from_cache,
            detail=result.detail,
            attribution=self.attribution,
        )
        if not result.ok:
            return [], report

        try:
            postings = self.parse(result)
        except Exception as exc:
            log.warning("%s: could not parse response: %s", self.name, exc)
            report.status = "unparseable_response"
            report.detail = f"The response could not be parsed ({type(exc).__name__})."
            return [], report

        report.postings_found = len(postings)

        tokens = role_tokens(role_title)
        scored = [(relevance_score(p, tokens), p) for p in postings]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        kept = [p for score, p in scored if score >= MIN_RELEVANCE][:limit]

        report.postings_kept = len(kept)
        if postings and not kept:
            report.status = "no_relevant_results"
            report.detail = (
                f"{len(postings)} postings were returned but none matched '{role_title}' "
                f"closely enough (relevance threshold {MIN_RELEVANCE})."
            )
        elif not postings:
            report.status = "no_results"
            report.detail = "The source returned no postings for this query."
        return kept, report


def _clean(text: Any, limit: int = 300) -> str:
    if text is None:
        return ""
    value = html_lib.unescape(str(text))
    return " ".join(value.split())[:limit]


# ---------------------------------------------------------------------------
# JSON API sources
# ---------------------------------------------------------------------------


class RemotiveSource(JobSource):
    name = "Remotive"
    source_type = "json_api"
    homepage = "https://remotive.com"
    attribution = "Job data from Remotive (remotive.com) public API."

    def build_url(self, role_title: str, location: str = "") -> str:
        return f"https://remotive.com/api/remote-jobs?search={quote_plus(role_title)}&limit=40"

    def parse(self, result: FetchResult) -> list[JobPosting]:
        payload = result.json()
        out: list[JobPosting] = []
        for job in payload.get("jobs", []) or []:
            out.append(
                JobPosting(
                    source=self.name,
                    source_type=self.source_type,
                    title=_clean(job.get("title"), 160),
                    company=_clean(job.get("company_name"), 120),
                    location=_clean(job.get("candidate_required_location"), 120),
                    url=_clean(job.get("url"), 400),
                    posted_at=_clean(job.get("publication_date"), 40),
                    description=html_to_text(job.get("description") or ""),
                    tags=[_clean(t, 50) for t in (job.get("tags") or [])][:14],
                )
            )
        return out


class ArbeitnowSource(JobSource):
    name = "Arbeitnow"
    source_type = "json_api"
    homepage = "https://www.arbeitnow.com"
    attribution = "Job data from Arbeitnow (arbeitnow.com) public job-board API."

    def build_url(self, role_title: str, location: str = "") -> str:
        # This API has no server-side search, so filtering happens client side.
        return "https://www.arbeitnow.com/api/job-board-api"

    def parse(self, result: FetchResult) -> list[JobPosting]:
        payload = result.json()
        out: list[JobPosting] = []
        for job in payload.get("data", []) or []:
            out.append(
                JobPosting(
                    source=self.name,
                    source_type=self.source_type,
                    title=_clean(job.get("title"), 160),
                    company=_clean(job.get("company_name"), 120),
                    location=_clean(job.get("location"), 120),
                    url=_clean(job.get("url"), 400),
                    posted_at=_clean(job.get("created_at"), 40),
                    description=html_to_text(job.get("description") or ""),
                    tags=[_clean(t, 50) for t in (job.get("tags") or [])][:14],
                )
            )
        return out


class JobicySource(JobSource):
    name = "Jobicy"
    source_type = "json_api"
    homepage = "https://jobicy.com"
    attribution = "Job data from Jobicy (jobicy.com) public API v2."

    def build_url(self, role_title: str, location: str = "") -> str:
        return f"https://jobicy.com/api/v2/remote-jobs?count=40&tag={quote_plus(role_title)}"

    def parse(self, result: FetchResult) -> list[JobPosting]:
        payload = result.json()
        out: list[JobPosting] = []
        for job in payload.get("jobs", []) or []:
            location = job.get("jobGeo") or ""
            industry = job.get("jobIndustry") or []
            out.append(
                JobPosting(
                    source=self.name,
                    source_type=self.source_type,
                    title=_clean(job.get("jobTitle"), 160),
                    company=_clean(job.get("companyName"), 120),
                    location=_clean(location, 120),
                    url=_clean(job.get("url"), 400),
                    posted_at=_clean(job.get("pubDate"), 40),
                    description=html_to_text(job.get("jobDescription") or job.get("jobExcerpt") or ""),
                    tags=[_clean(t, 50) for t in (industry if isinstance(industry, list) else [industry])][:14],
                )
            )
        return out


class HimalayasSource(JobSource):
    name = "Himalayas"
    source_type = "json_api"
    homepage = "https://himalayas.app"
    attribution = "Job data from Himalayas (himalayas.app) public jobs API."

    def build_url(self, role_title: str, location: str = "") -> str:
        return "https://himalayas.app/jobs/api?limit=50"

    def parse(self, result: FetchResult) -> list[JobPosting]:
        payload = result.json()
        jobs = payload.get("jobs") or payload.get("data") or []
        out: list[JobPosting] = []
        for job in jobs:
            if not isinstance(job, dict):
                continue
            locations = job.get("locationRestrictions") or job.get("locations") or []
            if isinstance(locations, str):
                locations = [locations]
            out.append(
                JobPosting(
                    source=self.name,
                    source_type=self.source_type,
                    title=_clean(job.get("title"), 160),
                    company=_clean(job.get("companyName") or job.get("company"), 120),
                    location=_clean(", ".join(str(l) for l in locations[:3]), 120),
                    url=_clean(job.get("applicationLink") or job.get("guid") or job.get("url"), 400),
                    posted_at=_clean(job.get("pubDate") or job.get("publishedDate"), 40),
                    description=html_to_text(job.get("description") or job.get("excerpt") or ""),
                    tags=[_clean(t, 50) for t in (job.get("categories") or job.get("seniority") or [])][:14],
                )
            )
        return out


class RemoteOKSource(JobSource):
    name = "Remote OK"
    source_type = "json_api"
    homepage = "https://remoteok.com"
    attribution = "Job data from Remote OK (remoteok.com). Remote OK requires attribution and a link back."

    def build_url(self, role_title: str, location: str = "") -> str:
        return "https://remoteok.com/api"

    def parse(self, result: FetchResult) -> list[JobPosting]:
        payload = result.json()
        if not isinstance(payload, list):
            raise ValueError("Remote OK feed was not a JSON array")

        out: list[JobPosting] = []
        for job in payload:
            if not isinstance(job, dict) or "position" not in job:
                continue  # the first element is the legal/attribution notice
            out.append(
                JobPosting(
                    source=self.name,
                    source_type=self.source_type,
                    title=_clean(job.get("position"), 160),
                    company=_clean(job.get("company"), 120),
                    location=_clean(job.get("location"), 120),
                    url=_clean(job.get("url") or job.get("apply_url"), 400),
                    posted_at=_clean(job.get("date"), 40),
                    description=html_to_text(job.get("description") or ""),
                    tags=[_clean(t, 50) for t in (job.get("tags") or [])][:14],
                )
            )
        return out


# ---------------------------------------------------------------------------
# RSS / markup scraping source
# ---------------------------------------------------------------------------


class WeWorkRemotelyRSSSource(JobSource):
    """
    Genuine markup scraping: fetch an RSS feed and parse the XML/HTML.

    WeWorkRemotely publishes category feeds for syndication, so this is a
    permitted, documented access path -- unlike scraping their search pages.
    """

    name = "WeWorkRemotely (RSS)"
    source_type = "rss_scrape"
    homepage = "https://weworkremotely.com"
    attribution = "Job data scraped from WeWorkRemotely public RSS feeds (weworkremotely.com)."

    # Verified live feed slugs.  WeWorkRemotely renames categories from time to
    # time and a retired slug 301-redirects to an empty body, so only slugs
    # confirmed to return content are listed here.
    _CATEGORY_FEEDS = {
        "programming": "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        "fullstack": "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
        "devops": "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
        "design": "https://weworkremotely.com/categories/remote-design-jobs.rss",
        "sales_marketing": "https://weworkremotely.com/categories/remote-sales-and-marketing-jobs.rss",
        "product": "https://weworkremotely.com/categories/remote-product-jobs.rss",
        "support": "https://weworkremotely.com/categories/remote-customer-support-jobs.rss",
        "management_finance": "https://weworkremotely.com/categories/remote-management-and-finance-jobs.rss",
        "all": "https://weworkremotely.com/remote-jobs.rss",
    }

    _CATEGORY_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
        (("devops", "sre", "site reliability", "infrastructure", "platform engineer", "sysadmin",
          "security", "cyber", "soc analyst", "network"), "devops"),
        (("full stack", "fullstack", "full-stack"), "fullstack"),
        (("designer", "design", "ux", "ui ", "graphic"), "design"),
        (("marketing", "seo", "content", "growth", "brand", "sales", "account executive",
          "business development"), "sales_marketing"),
        (("product manager", "product owner", "product"), "product"),
        (("support", "customer success", "helpdesk"), "support"),
        (("finance", "accountant", "hr ", "recruiter", "operations manager", "director",
          "chief", "head of"), "management_finance"),
        (("engineer", "developer", "programmer", "data", "software", "scientist", "qa", "tester",
          "architect", "machine learning", "analyst"), "programming"),
    ]

    def build_url(self, role_title: str, location: str = "") -> str:
        low = (role_title or "").lower()
        for keywords, category in self._CATEGORY_KEYWORDS:
            if any(k in low for k in keywords):
                return self._CATEGORY_FEEDS[category]
        return self._CATEGORY_FEEDS["all"]

    def parse(self, result: FetchResult) -> list[JobPosting]:
        out: list[JobPosting] = []
        for item in parse_rss_items(result.text, limit=60):
            title = item.get("title", "")
            company = ""
            # WWR titles look like "Company: Job Title".
            if ":" in title:
                company, _, remainder = title.partition(":")
                company, title = company.strip(), remainder.strip()
            out.append(
                JobPosting(
                    source=self.name,
                    source_type=self.source_type,
                    title=_clean(title, 160),
                    company=_clean(company, 120),
                    location=_clean(item.get("category"), 120),
                    url=_clean(item.get("link"), 400),
                    posted_at=_clean(item.get("published"), 40),
                    description=html_to_text(item.get("description") or ""),
                    tags=[_clean(item.get("category"), 50)] if item.get("category") else [],
                )
            )
        return out


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALL_SOURCES: list[JobSource] = [
    RemotiveSource(),
    JobicySource(),
    ArbeitnowSource(),
    WeWorkRemotelyRSSSource(),
    HimalayasSource(),
    RemoteOKSource(),
]

SOURCE_BY_NAME: dict[str, JobSource] = {s.name: s for s in ALL_SOURCES}


def describe_sources() -> list[dict[str, Any]]:
    """Source catalogue for the Settings / Job Analysis pages."""
    return [
        {
            "name": s.name,
            "source_type": s.source_type,
            "homepage": s.homepage,
            "attribution": s.attribution,
        }
        for s in ALL_SOURCES
    ]


def check_sources(probe_role: str = "software engineer") -> list[dict[str, Any]]:
    """
    Live reachability check for every source (Settings -> system health).

    Bypasses the cache so the result reflects the network right now.
    """
    out: list[dict[str, Any]] = []
    for source in ALL_SOURCES:
        url = source.build_url(probe_role)
        accept = "application/rss+xml, application/xml" if source.source_type == "rss_scrape" else "application/json"
        allowed, reason = fetcher.robots_allows(url)
        if not allowed:
            out.append(
                {"name": source.name, "source_type": source.source_type, "reachable": False,
                 "status": "blocked_by_robots", "detail": reason, "elapsed_ms": 0.0}
            )
            continue
        result = fetcher.fetch(url, accept=accept, use_cache=False, timeout=12.0)
        out.append(
            {
                "name": source.name,
                "source_type": source.source_type,
                "reachable": result.ok,
                "status": result.status,
                "http_status": result.http_status,
                "detail": result.detail or (f"{len(result.text):,} bytes received" if result.ok else ""),
                "elapsed_ms": round(result.elapsed_ms, 1),
                "robots": reason,
            }
        )
    return out


SourceFactory = Callable[[], JobSource]
