"""
Module 5 speech engines and Module 2 scraping compliance.

Tests that need a downloaded model or live network access are marked `live` and
skipped unless you opt in:

    pytest -m live          # run them
    pytest -m "not live"    # the default

Everything unmarked here runs offline: it checks the plumbing (audio decoding,
WAV handling, robots.txt logic, relevance scoring, failure reporting) rather
than the models themselves.
"""

from __future__ import annotations

import io
import wave

import pytest

from app.services.jobs import sources as job_sources
from app.services.jobs.http import ERR_ROBOTS, FetchResult, fetcher, html_to_text, parse_rss_items
from app.services.speech import stt, tts
from app.services.speech.audio_decode import TARGET_RATE, decode_to_mono16k


# ===========================================================================
# Helpers
# ===========================================================================


def make_wav(seconds: float = 0.5, rate: int = 22050, channels: int = 1) -> bytes:
    """A silent but structurally valid WAV."""
    frames = int(seconds * rate)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * frames * channels)
    return buffer.getvalue()


# ===========================================================================
# Audio decoding
# ===========================================================================


def test_wav_decodes_to_16k_mono() -> None:
    samples, duration = decode_to_mono16k(make_wav(1.0, rate=22050))
    assert duration == pytest.approx(1.0, abs=0.05)
    assert samples.shape[0] == pytest.approx(TARGET_RATE, abs=TARGET_RATE * 0.05)
    assert str(samples.dtype) == "float32"
    assert abs(float(samples.max())) <= 1.0


def test_stereo_wav_is_downmixed() -> None:
    samples, duration = decode_to_mono16k(make_wav(0.5, rate=16000, channels=2))
    assert samples.ndim == 1
    assert duration == pytest.approx(0.5, abs=0.05)


@pytest.mark.parametrize("rate", [8000, 16000, 22050, 44100, 48000])
def test_any_sample_rate_is_resampled(rate: int) -> None:
    samples, duration = decode_to_mono16k(make_wav(0.5, rate=rate))
    assert duration == pytest.approx(0.5, abs=0.06)
    assert samples.shape[0] > 0


def test_empty_audio_is_rejected() -> None:
    from app.core.errors import SpeechError

    with pytest.raises(SpeechError):
        decode_to_mono16k(b"")


def test_undecodable_audio_is_rejected_with_a_helpful_message() -> None:
    from app.core.errors import SpeechError

    with pytest.raises(SpeechError) as caught:
        decode_to_mono16k(b"this is definitely not audio data" * 50, filename_hint="x.webm")
    assert "text fallback" in str(caught.value)


# ===========================================================================
# STT wiring (no model needed)
# ===========================================================================


def test_stt_describes_itself_as_local() -> None:
    described = stt.describe()
    assert described["runs_locally"] is True
    assert described["engine"].startswith("faster-whisper")
    assert "tiny.en" in described["available_sizes"]
    assert "base.en" in described["available_sizes"]


def test_tiny_recording_returns_no_speech_rather_than_an_error() -> None:
    result = stt.transcribe_bytes(b"\x00" * 40, filename_hint="x.webm")
    assert result.has_speech is False
    assert result.text == ""
    assert result.warnings
    assert "longer" in result.warnings[0]


@pytest.mark.parametrize(
    ("logprob", "no_speech", "text", "expected"),
    [
        (-0.2, 0.05, "hello there", "high"),
        (-0.8, 0.10, "hello there", "medium"),
        (-1.5, 0.10, "hello there", "low"),
        (-0.2, 0.90, "hello there", "low"),
        (-0.2, 0.05, "", "none"),
    ],
)
def test_confidence_banding(logprob, no_speech, text, expected) -> None:
    assert stt._confidence_band(logprob, no_speech, text) == expected


# ===========================================================================
# TTS wiring
# ===========================================================================


def test_tts_describes_itself_as_local() -> None:
    described = tts.describe()
    assert described["runs_locally"] is True
    assert described["active_engine"] in ("piper", "sapi")
    assert "piper" in described
    assert "sapi" in described


def test_wav_helpers() -> None:
    audio = make_wav(0.5, rate=22050)
    assert tts._wav_duration(audio) == pytest.approx(0.5, abs=0.02)
    assert tts._wav_sample_rate(audio) == 22050
    assert tts._wav_duration(b"not a wav") == 0.0
    assert tts._wav_sample_rate(b"not a wav") == 0


def test_pcm_is_wrapped_into_a_valid_wav() -> None:
    pcm = b"\x00\x01" * 8000
    audio = tts._wrap_pcm_as_wav(pcm, 16000)
    assert audio.startswith(b"RIFF")
    assert tts._wav_sample_rate(audio) == 16000
    assert tts._wrap_pcm_as_wav(b"", 16000) == b""


def test_wavs_concatenate() -> None:
    joined = tts.concat_wavs([make_wav(0.3), make_wav(0.3)])
    assert tts._wav_duration(joined) == pytest.approx(0.6, abs=0.05)
    assert tts.concat_wavs([]) == b""

    single = make_wav(0.3)
    assert tts.concat_wavs([single]) == single


def test_mismatched_sample_rates_are_skipped_not_mangled() -> None:
    joined = tts.concat_wavs([make_wav(0.3, rate=22050), make_wav(0.3, rate=16000)])
    assert tts._wav_duration(joined) == pytest.approx(0.3, abs=0.05)


# ===========================================================================
# Live speech tests (opt in)
# ===========================================================================


@pytest.mark.live
def test_live_tts_produces_audio() -> None:
    result = tts.synthesise("This is a local text to speech test.")
    assert result.audio.startswith(b"RIFF")
    assert result.audio_seconds > 0.5
    assert result.engine in ("piper", "sapi")
    assert result.processing_ms > 0


@pytest.mark.live
def test_live_tts_streams_sentence_by_sentence() -> None:
    chunks = list(
        tts.synthesise_stream("First sentence here. Second sentence here. Third sentence here.")
    )
    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.audio.startswith(b"RIFF")


@pytest.mark.live
def test_live_round_trip_tts_then_stt() -> None:
    """
    The honest end-to-end speech test.

    Synthesise a known sentence locally, transcribe it locally, and check the
    content words survive. An exact match is not expected -- Whisper normalises
    casing and punctuation, and synthetic speech is not identical to human
    speech, which is a limitation recorded in the evaluation.
    """
    sentence = "I built a rest api with python and postgres for the logistics team"
    audio = tts.synthesise(sentence).audio

    result = stt.transcribe_bytes(audio, filename_hint="test.wav")
    assert result.has_speech
    assert result.processing_ms > 0
    assert result.real_time_factor > 0

    transcribed = result.text.lower()
    hits = sum(1 for word in ("built", "api", "python", "logistics") if word in transcribed)
    assert hits >= 3, f"only {hits}/4 keywords survived: {result.text!r}"


# ===========================================================================
# Scraping compliance
# ===========================================================================


def test_every_source_is_declared_with_attribution() -> None:
    described = job_sources.describe_sources()
    assert len(described) >= 5
    for source in described:
        assert source["name"]
        assert source["homepage"].startswith("https://")
        assert source["attribution"], f"{source['name']} has no attribution"


def test_at_least_one_source_is_genuine_markup_scraping() -> None:
    """The specification asks for scraping, not only JSON APIs."""
    assert any(s["source_type"] == "rss_scrape" for s in job_sources.describe_sources())


def test_sources_build_valid_urls() -> None:
    for source in job_sources.ALL_SOURCES:
        url = source.build_url("data analyst", "")
        assert url.startswith("https://")
        assert " " not in url


def test_user_agent_identifies_the_project_rather_than_a_browser() -> None:
    from app.core.config import settings

    agent = settings.scrape_user_agent
    assert "CareerIntelligencePlatform" in agent
    for browser in ("Mozilla", "Chrome", "Safari", "AppleWebKit"):
        assert browser not in agent


def test_rate_limiting_is_configured() -> None:
    from app.core.config import settings

    assert settings.scrape_min_interval_seconds > 0
    assert settings.scrape_cache_ttl_seconds > 0


def test_scraping_disabled_is_reported_not_faked() -> None:
    result = fetcher.fetch("https://example.com/jobs")
    assert result.ok is False
    assert result.status == "disabled_by_config"
    assert "switched off" in result.detail


def test_robots_block_is_reported_as_a_named_failure() -> None:
    report = job_sources.SourceReport(
        name="Blocked Board",
        source_type="json_api",
        url="https://blocked.example.com/api",
        status=ERR_ROBOTS,
        detail="robots.txt disallows this path",
    )
    payload = report.to_dict()
    assert payload["status"] == "blocked_by_robots"
    assert payload["postings_kept"] == 0


def test_failed_fetch_never_claims_success() -> None:
    for status in ("timeout", "http_error", "rate_limited", "network_error", "blocked_by_robots"):
        result = FetchResult(url="https://example.com", status=status)
        assert result.ok is False
        assert result.text == ""


def test_empty_200_response_is_treated_as_a_failure() -> None:
    """
    Regression test.

    A retired RSS category slug returns 200 with an empty body. That used to be
    cached and reported as a successful fetch with zero postings.
    """
    from app.services.jobs.http import ERR_PARSE

    result = FetchResult(url="https://example.com/feed.rss", status=ERR_PARSE, http_status=200)
    assert result.ok is False


# ===========================================================================
# Parsing scraped content
# ===========================================================================


def test_html_to_text_keeps_list_structure() -> None:
    html = """
    <html><body>
      <script>var x = 1;</script>
      <style>.a { color: red }</style>
      <h2>Requirements</h2>
      <ul><li>3 years of Python</li><li>Experience with Docker</li></ul>
      <p>Nice to have: Kubernetes</p>
    </body></html>
    """
    text = html_to_text(html)
    assert "var x" not in text
    assert "color: red" not in text
    assert "3 years of Python" in text
    assert "Experience with Docker" in text
    assert "- " in text  # list items survived as lines


def test_html_to_text_handles_junk() -> None:
    assert html_to_text("") == ""
    assert "hello" in html_to_text("<p>hello")


def test_rss_items_are_parsed() -> None:
    xml = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <title>Acme Corp: Senior Python Engineer</title>
        <link>https://example.com/job/1</link>
        <description>&lt;p&gt;We need Python and Django.&lt;/p&gt;</description>
        <pubDate>Mon, 01 Jan 2026 00:00:00 +0000</pubDate>
        <category>Programming</category>
      </item>
    </channel></rss>
    """
    items = parse_rss_items(xml)
    assert len(items) == 1
    assert items[0]["title"] == "Acme Corp: Senior Python Engineer"
    assert items[0]["link"] == "https://example.com/job/1"


def test_rss_parsing_of_junk_returns_nothing() -> None:
    assert parse_rss_items("") == []
    assert parse_rss_items("not xml at all") == []


def test_wwr_title_is_split_into_company_and_role() -> None:
    xml = """<?xml version="1.0"?>
    <rss version="2.0"><channel><item>
      <title>Acme Corp: Senior Python Engineer</title>
      <link>https://example.com/1</link>
      <description>Python work</description>
    </item></channel></rss>
    """
    source = job_sources.WeWorkRemotelyRSSSource()
    postings = source.parse(FetchResult(url="x", status="ok", text=xml))
    assert postings[0].company == "Acme Corp"
    assert postings[0].title == "Senior Python Engineer"


# ===========================================================================
# Relevance filtering
# ===========================================================================


def test_role_tokens_drop_seniority_noise() -> None:
    assert job_sources.role_tokens("Senior Data Analyst II") == ["data", "analyst"]
    assert job_sources.role_tokens("Junior Software Engineer") == ["software", "engineer"]


def test_title_matches_outrank_body_mentions() -> None:
    tokens = job_sources.role_tokens("Data Analyst")

    exact = job_sources.JobPosting(
        source="x", source_type="json_api", title="Data Analyst", description="Reporting work."
    )
    incidental = job_sources.JobPosting(
        source="x",
        source_type="json_api",
        title="Warehouse Operative",
        description="You will work with the data analyst team occasionally.",
    )
    assert job_sources.relevance_score(exact, tokens) > job_sources.relevance_score(incidental, tokens)
    assert job_sources.relevance_score(exact, tokens) >= 0.8


def test_irrelevant_posting_falls_below_the_threshold() -> None:
    tokens = job_sources.role_tokens("Cybersecurity Analyst")
    posting = job_sources.JobPosting(
        source="x", source_type="json_api", title="Pastry Chef", description="Baking bread daily."
    )
    assert job_sources.relevance_score(posting, tokens) < job_sources.MIN_RELEVANCE


def test_relevance_of_an_empty_query_is_neutral() -> None:
    posting = job_sources.JobPosting(source="x", source_type="json_api", title="Anything")
    assert job_sources.relevance_score(posting, []) == 0.5


# ===========================================================================
# Live scraping (opt in)
# ===========================================================================


@pytest.mark.live
def test_live_sources_are_reachable() -> None:
    from app.core import config

    object.__setattr__(config.settings, "scrape_enabled", True)
    try:
        results = job_sources.check_sources("software engineer")
        reachable = [r for r in results if r.get("reachable")]
        assert len(reachable) >= 3, f"only {len(reachable)}/{len(results)} sources reachable"
        for result in results:
            assert "status" in result
    finally:
        object.__setattr__(config.settings, "scrape_enabled", False)


@pytest.mark.live
def test_live_collection_returns_postings_with_descriptions() -> None:
    from app.core import config
    from app.services.jobs.collector import collect_postings

    object.__setattr__(config.settings, "scrape_enabled", True)
    try:
        postings, reports = collect_postings("Software Engineer")
        assert reports
        assert postings, "no postings collected from any source"
        assert any(len(p.description) > 200 for p in postings)
        for posting in postings:
            assert posting.title
            assert posting.source
    finally:
        object.__setattr__(config.settings, "scrape_enabled", False)


# --- QA regression: posting relevance (B7) ------------------------------------

import pytest as _pytest


@_pytest.mark.parametrize(
    "role, title, body, kept",
    [
        ("Chef", "Chef d'équipe logistique (H/F)", "", False),
        ("Chef", "Head Chef", "kitchen team", True),
        ("Software Engineer", "Civil Engineer", "bridges and roads", False),
        ("Software Engineer", "Senior Full Stack Software Engineer", "", True),
        ("Java Developer", "JavaScript Developer", "react", False),
    ],
)
def test_posting_relevance_uses_whole_words_and_the_full_title(role, title, body, kept) -> None:
    from app.services.jobs.sources import MIN_RELEVANCE, JobPosting, relevance_score, role_tokens

    score = relevance_score(JobPosting(source="t", source_type="api", title=title, description=body), role_tokens(role))
    assert (score >= MIN_RELEVANCE) is kept
