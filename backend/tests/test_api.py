"""
HTTP API contract tests, plus database and metrics behaviour.

These run against the real FastAPI app with the offline LLM engine and scraping
switched off, so they exercise the full request path (validation, service layer,
SQLite, error shaping) without depending on a model or the network.
"""

from __future__ import annotations

import json

import pytest


# ===========================================================================
# System endpoints
# ===========================================================================


def test_root_lists_the_seven_modules(client) -> None:
    payload = client.get("/").json()
    assert payload["status"] == "running"
    assert len(payload["modules"]) == 7


def test_ping(client) -> None:
    assert client.get("/api/ping").json()["pong"] is True


def test_health_reports_every_component(client) -> None:
    payload = client.get("/api/system/health").json()
    assert payload["status"] in ("ok", "degraded")
    for component in (
        "database",
        "llm",
        "speech_recognition",
        "text_to_speech",
        "job_sources",
        "skill_taxonomy",
    ):
        assert component in payload["components"]
    assert payload["components"]["database"]["ok"] is True
    assert "privacy" in payload


def test_health_declares_the_offline_engine_as_degraded(client) -> None:
    payload = client.get("/api/system/health").json()
    assert payload["components"]["llm"]["degraded"] is True
    assert payload["status"] == "degraded"
    assert any("language model" in d.lower() for d in payload["degradations"])


def test_health_states_that_speech_is_local(client) -> None:
    payload = client.get("/api/system/health").json()
    assert payload["components"]["speech_recognition"]["runs_locally"] is True
    assert payload["components"]["text_to_speech"]["runs_locally"] is True
    assert "local" in payload["privacy"]["speech_processing"].lower()


def test_taxonomy_endpoint(client) -> None:
    payload = client.get("/api/system/taxonomy").json()
    assert payload["stats"]["canonical_skills"] > 150
    assert len(payload["skills"]) == payload["stats"]["canonical_skills"]


def test_normalisation_endpoint_demonstrates_the_react_requirement(client) -> None:
    response = client.post(
        "/api/system/normalise", json={"skills": "React, ReactJS, React.js, React JS"}
    )
    payload = response.json()
    assert payload["input_count"] == 4
    assert payload["output_count"] == 1
    assert payload["output"][0]["canonical"] == "React"


def test_settings_never_returns_api_keys(client) -> None:
    body = client.get("/api/system/settings").text
    payload = json.loads(body)

    assert "keys_present" in payload["llm"]
    assert all(isinstance(v, bool) for v in payload["llm"]["keys_present"].values())
    # No key-shaped string may appear anywhere in the response.
    assert "sk-" not in body
    assert "api_key" not in body.lower().replace("api_keys", "").replace("keys_present", "")


def test_settings_rejects_unknown_fields(client) -> None:
    response = client.patch("/api/system/settings", json={"anthropic_api_key": "sk-leak"})
    assert response.status_code == 200
    assert response.json()["updated"] == {}


def test_dashboard_endpoint(client) -> None:
    payload = client.get("/api/system/dashboard").json()
    for key in ("latest_cv", "recent_gaps", "recent_interviews", "preparation_progress", "performance"):
        assert key in payload
    progress = payload["preparation_progress"]
    assert progress["total"] == len(progress["steps"])


# ===========================================================================
# Module 1 - CV endpoints
# ===========================================================================


def test_cv_limits(client) -> None:
    payload = client.get("/api/cv/limits").json()
    assert ".pdf" in payload["allowed_suffixes"]
    assert ".docx" in payload["allowed_suffixes"]
    assert payload["notes"]


def test_cv_upload_and_fetch(client, software_engineer_pdf: bytes) -> None:
    response = client.post(
        "/api/cv/upload",
        files={"file": ("synthetic_software_engineer.pdf", software_engineer_pdf, "application/pdf")},
    )
    assert response.status_code == 200
    payload = response.json()
    cv_id = payload["cv_id"]

    assert payload["profile"]["full_name"] == "Aisha Rahman"
    assert payload["profile"]["skill_count"] > 10
    assert payload["bullet_ranking"]

    fetched = client.get(f"/api/cv/{cv_id}").json()
    assert fetched["cv_id"] == cv_id
    assert fetched["profile"]["email"] == payload["profile"]["email"]

    text = client.get(f"/api/cv/{cv_id}/text").json()
    assert "Aisha Rahman" in text["text"]

    assert cv_id in [item["cv_id"] for item in client.get("/api/cv").json()["items"]]

    assert client.delete(f"/api/cv/{cv_id}").json()["deleted"] is True
    assert client.get(f"/api/cv/{cv_id}").status_code == 404


def test_cv_upload_docx(client, data_analyst_docx: bytes) -> None:
    response = client.post(
        "/api/cv/upload",
        files={
            "file": (
                "synthetic_data_analyst.docx",
                data_analyst_docx,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 200
    assert response.json()["profile"]["full_name"] == "Daniel Okonkwo"


@pytest.mark.parametrize(
    ("filename", "content", "status", "code"),
    [
        ("cv.exe", b"MZ\x90\x00" + b"\x00" * 400, 415, "unsupported_file"),
        ("cv.pdf", b"", 422, "empty_document"),
        ("cv.pdf", b"MZ not a pdf" + b"\x00" * 400, 415, "unsupported_file"),
        ("cv.docx", b"not a zip" * 40, 415, "unsupported_file"),
    ],
)
def test_cv_upload_rejections(client, filename, content, status, code) -> None:
    response = client.post("/api/cv/upload", files={"file": (filename, content, "application/octet-stream")})
    assert response.status_code == status
    payload = response.json()
    assert payload["error"]["code"] == code
    assert payload["error"]["message"]


def test_cv_404_is_shaped_consistently(client) -> None:
    response = client.get("/api/cv/does_not_exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_errors_never_leak_internals(client) -> None:
    body = client.post(
        "/api/cv/upload", files={"file": ("x.exe", b"MZ" + b"\x00" * 400, "application/octet-stream")}
    ).text
    for leak in ("Traceback", "File \"", "site-packages", "sqlite3", "app/services"):
        assert leak not in body


# ===========================================================================
# Module 2 - role endpoints
# ===========================================================================


def test_role_sources_lists_compliance(client) -> None:
    payload = client.get("/api/roles/sources").json()
    assert len(payload["sources"]) >= 5
    assert any(s["source_type"] == "rss_scrape" for s in payload["sources"])

    compliance = payload["compliance"]
    assert "robots" in " ".join(compliance).lower()
    blob = json.dumps(compliance).lower()
    for excluded in ("linkedin", "indeed", "glassdoor"):
        assert excluded in blob  # named explicitly as NOT scraped


@pytest.mark.parametrize(
    "title",
    ["", "a", "x" * 200, "Engineer{injection}", "Engineer<script>", "role|with|pipes", "role`with`ticks"],
)
def test_role_title_validation(client, title: str) -> None:
    response = client.post("/api/roles/analyse", json={"role_title": title})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_role_analysis_without_scraping_or_llm(client) -> None:
    """Both sources off must warn, not crash."""
    response = client.post(
        "/api/roles/analyse",
        json={"role_title": "Data Analyst", "use_scraping": False, "use_llm": False},
    )
    assert response.status_code == 200
    requirements = response.json()["requirements"]
    assert requirements["warnings"]
    assert requirements["stats"]["postings_collected"] == 0


def test_role_analysis_with_offline_engine_still_produces_requirements(client) -> None:
    response = client.post(
        "/api/roles/analyse",
        json={"role_title": "Data Analyst", "use_scraping": False, "use_llm": True},
    )
    payload = response.json()
    requirements = payload["requirements"]

    assert requirements["combined_skills"]
    assert requirements["llm_degraded"] is True
    names = [s["canonical"] for s in requirements["combined_skills"]]
    assert "SQL" in names

    fetched = client.get(f"/api/roles/{payload['role_analysis_id']}").json()
    assert fetched["role_title"] == "Data Analyst"


def test_role_analysis_handles_an_unusual_title(client) -> None:
    """There is no fixed list of roles, so a nonsense title must still work."""
    response = client.post(
        "/api/roles/analyse",
        json={"role_title": "Chief Vibes Officer", "use_scraping": False, "use_llm": True},
    )
    assert response.status_code == 200
    requirements = response.json()["requirements"]
    assert requirements["normalised_title"]
    assert requirements["title_assessment"]


# ===========================================================================
# Module 3 and 4 endpoints
# ===========================================================================


def test_gap_analysis_endpoint(client, cv_and_role) -> None:
    cv, role = cv_and_role
    response = client.post(
        "/api/gap/analyse",
        json={"cv_id": cv["cv_id"], "role_analysis_id": role["role_analysis_id"], "with_advice": True},
    )
    assert response.status_code == 200
    result = response.json()["result"]

    assert 0 <= result["match_percent"] <= 100
    assert result["stats"]["requirements_total"] == len(result["comparisons"])
    assert (
        result["stats"]["matched"] + result["stats"]["partial"] + result["stats"]["missing"]
        == result["stats"]["requirements_total"]
    )
    assert "not a prediction" in result["disclaimer"].lower()


def test_gap_analysis_rejects_unknown_ids(client) -> None:
    response = client.post(
        "/api/gap/analyse", json={"cv_id": "nope_cv", "role_analysis_id": "nope_role"}
    )
    assert response.status_code == 404
    assert "CV" in response.json()["error"]["message"]


def test_bullet_ranking_endpoint_needs_no_llm(client) -> None:
    response = client.post(
        "/api/improve/rank",
        json={"bullets": ["Responsible for various tasks", "Reduced latency from 420ms to 180ms"]},
    )
    ranking = response.json()["ranking"]
    assert ranking[0]["text"].startswith("Responsible")
    assert ranking[0]["weakness_score"] > ranking[1]["weakness_score"]


def test_improve_bullets_endpoint(client, cv_and_role) -> None:
    cv, _ = cv_and_role
    response = client.post(
        "/api/improve/bullets",
        json={
            "bullets": [
                "Responsible for the shipment tracking API used by three internal teams",
                "Worked on migrating a monolithic application to services",
            ],
            "role_title": "Software Engineer",
            "cv_id": cv["cv_id"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["results"]) == 2
    assert "guard_note" in payload["summary"]

    for result in payload["results"]:
        assert result["original"]
        assert "accepted" in result
        if not result["accepted"]:
            assert result["improved"] == result["original"]


def test_improve_bullets_validation(client) -> None:
    assert client.post("/api/improve/bullets", json={"bullets": []}).status_code == 422
    assert client.post("/api/improve/bullets", json={"bullets": ["ok"] * 40}).status_code == 422
    assert client.post("/api/improve/bullets", json={"bullets": ["x" * 900]}).status_code == 422


def test_improvement_decision_round_trip(client, cv_and_role) -> None:
    cv, _ = cv_and_role
    results = client.post(
        "/api/improve/bullets",
        json={"bullets": ["Responsible for the API"], "cv_id": cv["cv_id"]},
    ).json()["results"]

    improvement_id = results[0]["id"]
    assert (
        client.post(f"/api/improve/bullets/{improvement_id}/decision", json={"decision": "accepted"})
        .json()["decision"]
        == "accepted"
    )
    assert (
        client.post(f"/api/improve/bullets/{improvement_id}/decision", json={"decision": "banana"}).status_code
        == 422
    )
    history = client.get(f"/api/improve/history?cv_id={cv['cv_id']}").json()
    assert history["count"] >= 1


# ===========================================================================
# Module 5 and 6 endpoints
# ===========================================================================


def test_rubric_endpoint_is_available_before_the_interview(client) -> None:
    payload = client.get("/api/interview/rubric?difficulty=hard").json()
    assert payload["defined_in_advance"] is True
    assert payload["difficulty"] == "hard"
    assert len(payload["categories"]) == 6
    assert sum(c["weight"] for c in payload["categories"]) == pytest.approx(1.0)


def test_stages_endpoint(client) -> None:
    payload = client.get("/api/interview/stages").json()
    assert [s["key"] for s in payload["stages"]] == [
        "introduction",
        "background",
        "technical",
        "behavioural",
        "candidate_questions",
        "closing",
    ]


def test_speech_health_endpoint(client) -> None:
    payload = client.get("/api/interview/speech/health").json()
    assert payload["stt"]["runs_locally"] is True
    assert payload["tts"]["runs_locally"] is True
    assert "no audio is sent" in payload["note"].lower()


@pytest.mark.parametrize(
    "body",
    [
        {"role_title": ""},
        {"role_title": "a"},
        {"role_title": "Engineer", "difficulty": "impossible"},
        {"role_title": "Engineer", "mode": "telepathy"},
        {"role_title": "Engineer{inject}"},
    ],
)
def test_interview_start_validation(client, body: dict) -> None:
    assert client.post("/api/interview/start", json=body).status_code == 422


def test_text_interview_runs_through_every_stage(client, cv_and_role) -> None:
    """A full interview, driven in text mode against the deterministic engine."""
    cv, role = cv_and_role
    start = client.post(
        "/api/interview/start",
        json={
            "role_title": "Software Engineer",
            "difficulty": "easy",
            "mode": "text",
            "cv_id": cv["cv_id"],
            "role_analysis_id": role["role_analysis_id"],
        },
    ).json()

    interview_id = start["interview"]["id"]
    assert start["interview"]["status"] == "active"
    assert start["has_cv"] is True
    assert start["rubric"]["defined_in_advance"] is True

    def take_turn(text: str) -> dict:
        with client.stream(
            "POST", f"/api/interview/{interview_id}/turn", json={"text": text, "speak": False}
        ) as response:
            assert response.status_code == 200
            events = []
            buffer = ""
            for chunk in response.iter_text():
                buffer += chunk
                while "\n\n" in buffer:
                    frame, buffer = buffer.split("\n\n", 1)
                    data = "".join(
                        line[5:].strip() for line in frame.split("\n") if line.startswith("data:")
                    )
                    if data:
                        events.append(json.loads(data))
        return {"events": events, "done": next((e for e in events if e["type"] == "done"), None)}

    opening = take_turn("")
    assert opening["done"] is not None
    assert opening["done"]["reply"]
    assert any(e["type"] == "text" for e in opening["events"])

    answer = (
        "In my last role I owned the shipment tracking API. The median response time was "
        "420 milliseconds, so I profiled it, fixed an N plus one query and added Redis "
        "caching. As a result it came down to about 180 milliseconds."
    )

    stages_seen = {opening["done"]["stage"]}
    finished = False
    for _ in range(26):
        turn = take_turn(answer)
        assert turn["done"] is not None, "every turn must end with a done event"
        stages_seen.add(turn["done"]["stage"])
        if turn["done"]["finished"]:
            finished = True
            break

    assert finished, f"interview did not complete; stages reached: {stages_seen}"
    assert {"introduction", "background", "technical", "behavioural"} <= stages_seen

    detail = client.get(f"/api/interview/{interview_id}").json()
    assert detail["interview"]["status"] == "complete"
    assert len(detail["turns"]) >= 8

    candidate_turns = [t for t in detail["turns"] if t["speaker"] == "candidate"]
    assert candidate_turns
    assert "analysis" in candidate_turns[0]["meta"]

    report = client.post(f"/api/interview/{interview_id}/score").json()
    assert report["overall_score"] is not None
    assert 1 <= report["overall_score"] <= 5
    assert len(report["category_scores"]) == 6
    assert "not a hiring decision" in report["disclaimer"].lower()
    for category in report["category_scores"]:
        assert category["key"] in [c["key"] for c in report["rubric"]["categories"]]
        assert category["justification"]

    transcript = client.get(f"/api/interview/{interview_id}/transcript").json()
    assert "Interviewer:" in transcript["plain_text"]

    stored = client.get(f"/api/interview/{interview_id}/report").json()
    assert stored["available"] is True


def test_turn_on_a_finished_interview_is_refused(client) -> None:
    start = client.post(
        "/api/interview/start", json={"role_title": "Data Analyst", "mode": "text"}
    ).json()
    interview_id = start["interview"]["id"]
    client.post(f"/api/interview/{interview_id}/end")

    with client.stream(
        "POST", f"/api/interview/{interview_id}/turn", json={"text": "hello", "speak": False}
    ) as response:
        body = "".join(response.iter_text())
    assert "interview_finished" in body


def test_interview_404(client) -> None:
    assert client.get("/api/interview/nope").status_code == 404
    assert client.post("/api/interview/nope/score").status_code == 404


def test_scoring_an_interview_with_no_answers(client) -> None:
    start = client.post(
        "/api/interview/start", json={"role_title": "Data Analyst", "mode": "text"}
    ).json()
    interview_id = start["interview"]["id"]
    client.post(f"/api/interview/{interview_id}/end")

    report = client.post(f"/api/interview/{interview_id}/score").json()
    assert report["overall_score"] is None
    assert report["overall_band"] == "Not assessed"
    for category in report["category_scores"]:
        assert category["score"] is None


def test_transcribe_rejects_an_oversized_upload(client) -> None:
    response = client.post(
        "/api/interview/transcribe",
        files={"audio": ("huge.webm", b"\x00" * (13 * 1024 * 1024), "audio/webm")},
    )
    assert response.status_code == 422


# ===========================================================================
# Module 7 - metrics
# ===========================================================================


def test_metrics_overview_shape(client) -> None:
    payload = client.get("/api/metrics").json()
    summary = payload["summary"]
    assert "e2e_first_audio_ms" in summary["aggregates"]
    assert summary["headline_metric"] == "e2e_first_audio_ms"
    assert summary["notes"]
    assert "local" in " ".join(summary["notes"]).lower()


def test_metrics_export_is_self_describing(client) -> None:
    payload = client.get("/api/metrics/export").json()
    assert "metric_definitions" in payload
    for definition in payload["metric_definitions"].values():
        assert definition["unit"] == "milliseconds"
        assert definition["measured_from"]


def test_metrics_csv_export(client) -> None:
    response = client.get("/api/metrics/export.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert response.text.splitlines()[0].startswith("index,role_title")


def test_metrics_summarise_handles_no_samples() -> None:
    from app.services.metrics.recorder import summarise

    assert summarise([])["samples"] == 0
    assert summarise([None, None])["samples"] == 0

    result = summarise([100.0, 200.0, 300.0])
    assert result["samples"] == 3
    assert result["median_ms"] == 200.0
    assert result["min_ms"] == 100.0
    assert result["max_ms"] == 300.0


def test_percentile_is_nearest_rank() -> None:
    from app.services.metrics.recorder import _percentile

    values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert _percentile(values, 0.0) == 10
    assert _percentile(values, 1.0) == 100
    assert _percentile([], 0.9) == 0.0


# ===========================================================================
# Database
# ===========================================================================


def test_storage_stats_and_clear(client, clean_db) -> None:
    before = client.get("/api/system/storage").json()
    assert before["row_counts"]["cv_documents"] == 0

    client.post("/api/cv/upload", files={"file": ("cv.txt", b"Jane Doe\njane@example.com\nSKILLS\nPython\n", "text/plain")})
    assert client.get("/api/system/storage").json()["row_counts"]["cv_documents"] == 1

    cleared = client.delete("/api/system/storage").json()
    assert cleared["cleared"] is True
    assert cleared["rows_after"]["cv_documents"] == 0
    assert "speech models were kept" in cleared["note"]


def test_json_columns_round_trip() -> None:
    from app.core.db import dumps, loads

    value = {"a": [1, 2, {"b": "ünïcøde — dash"}], "c": None, "d": True}
    assert loads(dumps(value)) == value
    assert loads("", default={"fallback": 1}) == {"fallback": 1}
    assert loads("{not json", default=[]) == []
    assert loads(None, default=None) is None


def test_activity_log_records_actions(client, clean_db) -> None:
    client.post("/api/cv/upload", files={"file": ("cv.txt", b"Jane Doe\njane@example.com\nSKILLS\nPython\n", "text/plain")})
    activity = client.get("/api/system/dashboard").json()["activity"]
    assert any(entry["kind"] == "cv_upload" for entry in activity)


def test_cascade_delete_removes_dependent_rows(client, clean_db, software_engineer_pdf: bytes) -> None:
    cv = client.post(
        "/api/cv/upload", files={"file": ("cv.pdf", software_engineer_pdf, "application/pdf")}
    ).json()
    role = client.post(
        "/api/roles/analyse",
        json={"role_title": "Software Engineer", "use_scraping": False, "use_llm": True},
    ).json()
    client.post(
        "/api/gap/analyse",
        json={"cv_id": cv["cv_id"], "role_analysis_id": role["role_analysis_id"], "with_advice": False},
    )

    assert client.get("/api/system/storage").json()["row_counts"]["gap_analyses"] == 1
    client.delete(f"/api/cv/{cv['cv_id']}")
    assert client.get("/api/system/storage").json()["row_counts"]["gap_analyses"] == 0


# ===========================================================================
# A throttled turn must explain itself to the user
# ===========================================================================
#
# Groq's free tier is capped at 8,000 tokens per minute. An interview turn
# costs roughly 2,800, so a back-to-back interview is throttled: a measured run
# took 21 HTTP 429s and the retry backoff stretched one first-token time to
# 18 seconds. Once the retry budget is exhausted the turn fails outright.
#
# When that happens the student must be told what to do about it, not shown a
# raw SDK traceback or left with a silently dead turn. The explanatory text
# exists in LLMClient._explain_failure, but text is worthless if it does not
# reach the screen, so this tests the whole chain: the error raised in the LLM
# layer, through the engine's event stream, to the SSE frame the browser
# renders.


def test_a_rate_limited_turn_reaches_the_user_with_advice(client, cv_and_role, monkeypatch) -> None:
    from app.core.errors import LLMError
    from app.services.interview import engine as engine_mod
    from app.services.llm.client import LLMClient

    cv, role = cv_and_role
    start = client.post(
        "/api/interview/start",
        json={
            "role_title": "Software Engineer",
            "difficulty": "easy",
            "mode": "text",
            "cv_id": cv["cv_id"],
            "role_analysis_id": role["role_analysis_id"],
        },
    ).json()
    interview_id = start["interview"]["id"]

    # Reproduce what the provider actually does when the budget is spent: the
    # message is built by the real _explain_failure, so this test fails if that
    # wording ever stops being actionable.
    throttled = RuntimeError("Rate limit reached for model `openai/gpt-oss-20b`")
    setattr(throttled, "status_code", 429)
    explained = LLMClient(provider="groq", model="openai/gpt-oss-20b")._explain_failure(
        throttled, streaming=True
    )

    def refuse_to_stream(self, *args, **kwargs):
        raise LLMError(explained)
        yield  # pragma: no cover - makes this a generator

    monkeypatch.setattr(LLMClient, "stream", refuse_to_stream)

    with client.stream(
        "POST", f"/api/interview/{interview_id}/turn",
        json={"text": "I built the ingestion service.", "speak": False},
    ) as response:
        assert response.status_code == 200, "a throttled turn is a reported error, not a 500"
        body = response.read().decode("utf-8")

    frames = [json.loads(f.removeprefix("data: ")) for f in body.split("\n\n") if f.strip()]
    errors = [f for f in frames if f.get("type") == "error"]

    assert errors, f"the user was told nothing; frames were {[f.get('type') for f in frames]}"
    message = errors[0]["message"]
    assert "rate-limited" in message.lower()
    assert "ollama" in message.lower(), "must name the way out, not just the problem"


def test_the_interview_survives_a_failed_turn(client, cv_and_role, monkeypatch) -> None:
    """
    A throttled turn must be retryable. If the engine advanced the stage or
    closed the interview on failure, a single 429 would cost the student their
    whole session.
    """
    from app.core.errors import LLMError
    from app.services.llm.client import LLMClient

    cv, role = cv_and_role
    start = client.post(
        "/api/interview/start",
        json={
            "role_title": "Software Engineer", "difficulty": "easy", "mode": "text",
            "cv_id": cv["cv_id"], "role_analysis_id": role["role_analysis_id"],
        },
    ).json()
    interview_id = start["interview"]["id"]
    before = client.get(f"/api/interview/{interview_id}").json()["interview"]

    def refuse_to_stream(self, *args, **kwargs):
        raise LLMError("the provider is rate-limited")
        yield  # pragma: no cover

    monkeypatch.setattr(LLMClient, "stream", refuse_to_stream)
    with client.stream(
        "POST", f"/api/interview/{interview_id}/turn",
        json={"text": "I built the ingestion service.", "speak": False},
    ) as response:
        response.read()

    after = client.get(f"/api/interview/{interview_id}").json()["interview"]
    assert after["status"] == "active", "a failed turn must not end the interview"
    assert after["stage"] == before["stage"], "a failed turn must not advance the stage"
    assert after["progress"] == before["progress"], (
        "a failed turn must not consume stage budget -- the student can simply retry"
    )
