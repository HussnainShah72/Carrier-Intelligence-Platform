# API Reference

Base URL: `http://127.0.0.1:8000/api`
Interactive documentation (Swagger): <http://127.0.0.1:8000/docs>
OpenAPI schema: <http://127.0.0.1:8000/openapi.json>

44 endpoints across six routers. All requests and responses are JSON unless
stated otherwise.

---

## Conventions

### Errors

Every error has the same shape. The `message` is written to be shown directly to
a user; internal details (stack traces, SQL, provider payloads, API keys) stay in
the server log and are never returned.

```json
{
  "error": {
    "code": "unsupported_file",
    "message": "'.exe' is not a supported CV format. Please upload one of: .docx, .pdf, .txt.",
    "details": ["optional array of specifics"]
  }
}
```

| HTTP | `code` | Meaning |
|---|---|---|
| 404 | `not_found` | The record does not exist, or storage was cleared |
| 409 | `conflict` | The action conflicts with current state |
| 413 | `file_too_large` | Upload exceeds `MAX_UPLOAD_BYTES` |
| 415 | `unsupported_file` | Wrong extension, or contents do not match the extension |
| 422 | `validation_error` | A field failed validation |
| 422 | `empty_document` | The file is empty, or has no readable text |
| 422 | `extraction_failed` | The document is corrupt or password-protected |
| 502 | `llm_unavailable` | The configured language model could not be reached |
| 502 | `llm_invalid_output` | The model did not return usable structured data |
| 502 | `scrape_failed` | A job source could not be read |
| 503 | `speech_unavailable` | A local speech engine is missing or disabled |
| 500 | `internal_error` | Unexpected — the detail is in the backend log only |

Every response carries `X-Response-Time-Ms`.

### Streaming

The two interview turn endpoints return **Server-Sent Events**
(`text/event-stream`), not JSON. Each frame is `data: {...}` followed by a blank
line. This is what lets audio start playing before the reply has finished
generating. `EventSource` cannot be used because a turn is a POST carrying audio
or text; the frontend reads the stream with `fetch` instead.

---

## Module 1 — CV parsing

### `POST /api/cv/upload`

Upload and parse a CV. `multipart/form-data` with a `file` field.

Accepts `.pdf`, `.docx`, `.txt` up to 5 MB (configurable). Validates the
extension **and** the magic bytes, guards against zip bombs, detects encrypted
and image-only PDFs, and strips prompt-injection lines before anything reads the
document.

<details><summary>Response (abridged)</summary>

```json
{
  "cv_id": "cv_a1b2c3d4e5f6",
  "filename": "cv.pdf",
  "file_type": "pdf",
  "size_bytes": 3649,
  "char_count": 2289,
  "page_count": 1,
  "extractor": "pdfplumber",
  "extraction_warnings": [],
  "profile": {
    "full_name": "Aisha Rahman",
    "email": "aisha.rahman@example.com",
    "phone": "+44 7700 900123",
    "location": "Manchester, United Kingdom",
    "links": ["github.com/example-aisha"],
    "headline": "Backend-focused software engineer with 4 years...",
    "total_years_experience": 4.0,
    "skills": [
      {
        "canonical": "React",
        "category": "Frontend",
        "surface_forms": ["React", "ReactJS"],
        "stage": "exact-alias",
        "confidence": 1.0,
        "in_taxonomy": true,
        "matched_against": "react"
      }
    ],
    "education": [{ "degree": "BSc (Hons) Computer Science", "institution": "University of Manchester", "grade": "2:1" }],
    "experience": [
      {
        "job_title": "Software Engineer",
        "company": "Northfield Logistics Ltd",
        "start": "Mar 2023",
        "end": "Present",
        "bullets": ["Responsible for the shipment tracking API..."]
      }
    ],
    "projects": [{ "name": "Warehouse Slot Optimiser", "technologies": ["Python", "FastAPI"] }],
    "certifications": [{ "name": "AWS Certified Cloud Practitioner", "year": "2024" }],
    "languages": ["English", "Urdu"],
    "job_roles": ["Software Engineer", "Junior Software Developer"],
    "all_bullets": ["..."],
    "sections_found": ["summary", "skills", "experience", "education"],
    "rejected_claims": [
      { "field": "skills", "value": "Kubernetes", "reason": "not found anywhere in the CV text" }
    ],
    "parse_mode": "hybrid (heuristic + LLM, grounded)",
    "warnings": [],
    "skill_count": 26
  },
  "bullet_ranking": [
    { "index": 0, "text": "Responsible for...", "weakness_signals": ["weak opening"], "weakness_score": 2, "word_count": 11 }
  ],
  "llm_usage": { "provider": "ollama", "model": "qwen2.5:3b-instruct-q4_K_M", "total_ms": 8421.3, "degraded": false }
}
```
</details>

`rejected_claims` is the visible output of the grounding filter: things the
language model proposed that the document does not support. An empty array means
the model added nothing unsupported.

### Other CV endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/cv/limits` | Accepted formats, size limits, and the stated caveats (no OCR, etc.) |
| `GET` | `/api/cv?limit=25` | List stored CVs with summary counts |
| `GET` | `/api/cv/{cv_id}` | Full stored profile |
| `GET` | `/api/cv/{cv_id}/text` | The raw extracted text — "show me what you actually read" |
| `DELETE` | `/api/cv/{cv_id}` | Delete the CV and, by cascade, its gap analyses |

---

## Module 2 — job postings and role skills

### `POST /api/roles/analyse`

Collects live job postings **and** generates role requirements with a language
model, then fuses them.

```json
{
  "role_title": "Data Analyst",
  "location": "",
  "seniority": "any",
  "use_scraping": true,
  "use_llm": true,
  "max_postings": 24
}
```

`role_title` is 2–120 characters and rejects `{ } < > | ` ` `, which are prompt
injection vectors rather than parts of a job title. Any title is accepted —
there is no fixed list.

Takes 10–60 seconds: six sources are queried in parallel while the LLM call runs.

<details><summary>Response (abridged)</summary>

```json
{
  "role_analysis_id": "role_9f8e7d6c",
  "requirements": {
    "role_title": "Data Analyst",
    "normalised_title": "Data Analyst",
    "title_assessment": "clear",
    "seniority": "mid",
    "role_summary": "Turns business data into decisions...",
    "responsibilities": ["Write SQL queries to pull and join data..."],
    "interview_focus_areas": ["SQL joins and aggregation"],

    "combined_skills": [
      {
        "canonical": "Python",
        "category": "Programming Language",
        "provenance": "both",
        "importance": 0.927,
        "posting_count": 13,
        "posting_frequency": 0.542,
        "llm_tiers": ["core"],
        "surface_forms": ["Python", "python3"],
        "example_sources": ["Jobicy", "Remotive"],
        "normalisation_stage": "exact-alias",
        "essential": true
      }
    ],

    "postings": [
      {
        "source": "Jobicy",
        "source_type": "json_api",
        "title": "Senior Data Analyst",
        "company": "Welo Global",
        "url": "https://jobicy.com/jobs/...",
        "description": "...",
        "skills": ["SQL", "Python", "Tableau"]
      }
    ],

    "source_reports": [
      { "name": "Jobicy", "source_type": "json_api", "status": "ok",
        "postings_found": 40, "postings_kept": 10, "elapsed_ms": 1151.0,
        "from_cache": false, "detail": "", "attribution": "Job data from Jobicy..." },
      { "name": "Himalayas", "status": "no_relevant_results",
        "postings_found": 20, "postings_kept": 0,
        "detail": "20 postings were returned but none matched 'Data Analyst' closely enough..." }
    ],

    "merge_evidence": [
      { "canonical": "React", "variants": ["React", "ReactJS", "React.js"],
        "stage": "exact-alias", "provenance": "both", "posting_count": 4 }
    ],

    "filtering": {
      "candidates_considered": 227,
      "requirements_kept": 70,
      "dropped_uncorroborated": 157,
      "min_posting_support": 2,
      "max_requirements": 70,
      "dropped_examples": ["AI Strategy", "Ambiguous"],
      "rule": "A skill found only by scraping is kept only if at least 2 independent adverts asked for it..."
    },

    "warnings": [],
    "timings": { "scrape_ms": 1385.9, "llm_role_ms": 13225.0, "fusion_ms": 372.8 },
    "llm_available": true,
    "llm_degraded": false,

    "stats": {
      "total_skills": 70, "from_scraping_only": 54, "from_llm_only": 4,
      "confirmed_by_both": 12, "essential_skills": 19, "postings_collected": 24,
      "sources_attempted": 6, "sources_succeeded": 6,
      "agreement_rate": 0.171, "dropped_uncorroborated": 157
    }
  },
  "llm_usage": { "calls": 1, "total_ms": 13225.0, "degraded": false }
}
```
</details>

**`provenance`** is the key field: `scraped` (live adverts only), `llm` (model
only), or `both` (independently agreed). Nothing is presented as a requirement
without saying where it came from.

**`source_reports`** records every source's outcome, including failures:
`ok`, `no_results`, `no_relevant_results`, `timeout`, `http_error`,
`rate_limited`, `blocked_by_robots`, `network_error`, `unparseable_response`,
`disabled_by_config`, `source_error`. A fetch that failed is never reported as a
success with zero results.

### Other role endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/roles/sources` | Source catalogue, attribution, cache stats, and the compliance measures |
| `GET` | `/api/roles/sources/health` | Live reachability probe of every source (bypasses the cache) |
| `GET` | `/api/roles?limit=25` | List previous analyses |
| `GET` | `/api/roles/{id}` | Full stored analysis, including the raw LLM reply |
| `GET` | `/api/roles/{id}/postings` | The collected postings for that analysis |
| `DELETE` | `/api/roles/cache` | Clear the on-disk response cache |
| `DELETE` | `/api/roles/{id}` | Delete an analysis |

---

## Module 3 — match and gap analysis

### `POST /api/gap/analyse`

```json
{ "cv_id": "cv_a1b2c3d4", "role_analysis_id": "role_9f8e7d6c", "with_advice": true }
```

<details><summary>Response (abridged)</summary>

```json
{
  "gap_analysis_id": "gap_1a2b3c4d",
  "cv_filename": "cv.pdf",
  "role_title": "Data Analyst",
  "result": {
    "match_percent": 38.6,
    "unweighted_percent": 34.1,
    "readiness_label": "Covers some collected requirements",

    "comparisons": [
      {
        "requirement": "JavaScript",
        "category": "Programming Language",
        "status": "partial",
        "importance": 0.72,
        "provenance": "both",
        "posting_count": 8,
        "essential": true,
        "credit": 0.5,
        "severity": "high",
        "evidence": "Your CV does not name 'JavaScript', but it lists 'React', which normally demonstrates it...",
        "matched_via": "implied by a related skill on your CV",
        "cv_skill": "React",
        "confidence": 0.7
      }
    ],

    "matched": [], "partial": [], "missing": [], "priority_gaps": [],
    "extra_skills": [{ "canonical": "Rust", "category": "Programming Language" }],
    "category_breakdown": [
      { "category": "Database", "matched": 3, "partial": 1, "missing": 2, "total": 6, "coverage_percent": 58.3 }
    ],
    "essential_coverage": {
      "total": 19, "matched": 8, "partial": 3, "missing": 8,
      "coverage_percent": 50.0, "missing_names": ["ETL", "Power BI"]
    },

    "advice": {
      "available": true,
      "headline": "Your CV currently covers about 39% of the requirements collected for this role.",
      "priority_gaps": [
        { "skill": "ETL", "why_it_matters": "...", "how_to_close": "...", "estimated_effort": "3-6 weeks of focused practice" }
      ],
      "quick_wins": ["Git"],
      "strengths_to_lead_with": ["SQL", "Excel"],
      "learning_sequence": ["..."],
      "caveat": "This is automated guidance generated from a keyword comparison...",
      "filtered_out": 2
    },

    "warnings": [],
    "stats": { "requirements_total": 70, "matched": 16, "partial": 7, "missing": 47, "extra_skills": 5 },
    "disclaimer": "This score measures how much of the collected requirement list your CV names. It is not a prediction of whether you will be shortlisted or hired..."
  }
}
```
</details>

**Status values.** `matched` (the CV names this exact skill), `partial` (a
related skill implies it, the foundation is present, or the names are
near-duplicates — half credit), `missing` (no evidence).

**`match_percent`** is `Σ(importance × credit) / Σ(importance) × 100`, so missing
one core requirement costs more than missing three optional tools.
`unweighted_percent` is the plain count, for comparison.

**`advice.filtered_out`** counts suggestions discarded because the model proposed
a "gap" the CV already covers.

### Other gap endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/gap?limit=25` | List previous analyses |
| `GET` | `/api/gap/{id}` | Full stored analysis |

---

## Module 4 — CV improvement

### `POST /api/improve/bullets`

```json
{
  "bullets": ["Responsible for the shipment tracking API used by three teams"],
  "role_title": "Software Engineer",
  "cv_id": "cv_a1b2c3d4"
}
```

1–12 bullets, each at most 600 characters.

<details><summary>Response</summary>

```json
{
  "results": [
    {
      "id": "imp_1a2b3c",
      "original": "Responsible for the shipment tracking API used by three teams",
      "improved": "Owned the shipment tracking API used by three internal teams",
      "explanation": "Removed the filler opening and led with a stronger verb.",
      "changes": ["removed filler", "stronger action verb"],
      "flags": [],
      "accepted": true,
      "rejection_reason": "",
      "already_strong": false,
      "metrics_preserved": ["three"],
      "weakness_signals": ["weak opening ('responsible for', 'worked on')"],
      "decision": "pending",
      "word_count_before": 10,
      "word_count_after": 9
    },
    {
      "id": "imp_4d5e6f",
      "original": "Worked on improving the checkout page load time",
      "improved": "Worked on improving the checkout page load time",
      "explanation": "Rejected: the rewrite invented a metric that your original bullet does not contain. Your original text has been kept.",
      "flags": [
        { "type": "invented_metric", "severity": "blocking",
          "detail": "The rewrite introduced 45%, which is not in your original bullet. Invented metrics are rejected automatically." }
      ],
      "accepted": false,
      "rejection_reason": "invented_metric"
    }
  ],
  "summary": {
    "requested": 2, "returned_by_model": 2, "accepted": 1, "rejected": 1,
    "already_strong": 0, "with_warnings": 0,
    "rejections_by_reason": { "invented_metric": 1 },
    "elapsed_ms": 7525.0, "engine": "ollama/qwen2.5:3b-instruct-q4_K_M", "degraded": false,
    "guard_note": "Every rewrite is checked automatically for invented metrics, invented technologies and escalated scope..."
  },
  "llm_usage": { "provider": "ollama", "total_ms": 7520.1, "degraded": false }
}
```
</details>

When `accepted` is `false`, `improved` **equals** `original` — the user's text is
preserved. `rejection_reason` is one of `invented_metric`,
`invented_technology`, `escalated_scope`, `empty_rewrite`, `rewrite_too_long`.

### Other improvement endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/improve/rank` | Rank bullets by weakness — deterministic, instant, no LLM call |
| `POST` | `/api/improve/bullets/{id}/decision` | Record `accepted` / `rejected` / `pending` |
| `GET` | `/api/improve/history?cv_id=&limit=100` | Previous rewrites |

---

## Module 5 — the voice interview

### `GET /api/interview/rubric?difficulty=medium`

The scoring rubric. Available **before** an interview starts, which is the point:
the candidate can read the criteria first.

```json
{
  "version": "1.0",
  "difficulty": "medium",
  "scale": [{ "score": 5, "label": "Strong", "descriptor": "Specific, technically correct..." }],
  "categories": [
    { "key": "technical_accuracy", "name": "Technical Accuracy",
      "description": "Are the technical statements correct?...",
      "what_good_looks_like": "Correct definitions, correct cause and effect...",
      "weight": 0.25, "weight_percent": 25.0 }
  ],
  "overall_bands": [{ "min": 4.5, "label": "Excellent", "summary": "..." }],
  "disclaimer": "This is automated practice feedback... not a hiring decision.",
  "defined_in_advance": true,
  "note": "This rubric is fixed in source control before any interview is conducted..."
}
```

### `GET /api/interview/stages?difficulty=medium`

The six stages, their goals, question budgets, and whether each is scored.

### `GET /api/interview/speech/health`

Whether the local engines are ready.

```json
{
  "stt": { "engine": "faster-whisper (CTranslate2)", "runs_locally": true, "installed": true,
           "enabled": true, "model_size": "base.en", "device": "cpu", "compute_type": "int8",
           "available_sizes": ["tiny.en", "base.en", "small.en"] },
  "tts": { "runs_locally": true, "enabled": true, "active_engine": "piper",
           "piper": { "installed": true, "voices_on_disk": [{ "name": "en_US-amy-medium", "ready": true }] },
           "sapi": { "installed": true, "note": "Uses the operating system speech engine..." } },
  "voice_ready": true,
  "note": "Both speech recognition and speech synthesis run on this machine. No audio is sent to any external service."
}
```

### `POST /api/interview/speech/warmup`

Loads both models into memory. Worth its own endpoint: the first Whisper call
includes model loading (seconds), which would otherwise be charged to the first
measured turn and distort the whole performance report.

### `POST /api/interview/start`

```json
{
  "role_title": "Data Analyst",
  "difficulty": "medium",
  "mode": "voice",
  "cv_id": "cv_a1b2c3d4",
  "role_analysis_id": "role_9f8e7d6c"
}
```

Plans the interview from the CV and the role requirements, then returns the
interview, the rubric, the stages, and the speech engine status.

### `POST /api/interview/{id}/voice-turn` → SSE

`multipart/form-data`: `audio` (the recording) and `speak` (boolean).

The latency clock starts the instant the upload has been read, which is the
server's best observation of the end of the candidate's speech. Every
end-to-end figure is measured from that point.

### `POST /api/interview/{id}/turn` → SSE

`{"text": "...", "speak": true}` — text mode, and the documented fallback when
the microphone or the speech model is unavailable. Send `text: ""` for the
opening turn, where there is no answer yet.

### SSE event types

| `type` | When | Payload |
|---|---|---|
| `transcript` | Local transcription finished | `text`, `stt` (timings, confidence, segments) |
| `no_speech` | The recording held no speech | `message`, `stt` |
| `analysis` | The local answer analysis completed (~1 ms) | `analysis` (quality band, signals, skills) |
| `stage` | The interview advanced a stage | `stage`, `stage_name`, `previous_stage`, `progress` |
| `text` | A token arrived from the model | `delta` |
| `audio` | A sentence was synthesised | `index`, `text`, `audio_base64`, `engine`, `audio_seconds`, `synthesis_ms`, `since_speech_end_ms` |
| `tts_error` | One sentence could not be spoken | `message`, `text` — the turn continues |
| `metrics` | The turn's timings are final | `timings` |
| `done` | The turn finished | `reply`, `stage`, `finished`, `progress`, `timings`, `follow_up`, `effective_difficulty` |
| `error` | The turn failed | `code`, `message`, sometimes `fallback: "text"` |

Audio arrives **interleaved with** `text` events, which is the whole design: the
browser queues and plays each sentence while later ones are still being
generated.

### `POST /api/interview/speak`

`{"text": "...", "voice": ""}` → `audio/wav` bytes. Used for replay and for the
TTS self-test. Headers report `X-TTS-Engine`, `X-TTS-Voice`,
`X-TTS-Processing-Ms`, `X-TTS-Audio-Seconds`.

### `POST /api/interview/transcribe`

Transcribe a recording without advancing the interview — the microphone test.

### Other interview endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/interview?limit=25` | List interviews with scores |
| `GET` | `/api/interview/{id}` | Interview, turns, rubric, and this interview's metrics |
| `POST` | `/api/interview/{id}/end` | End early |
| `GET` | `/api/interview/{id}/transcript` | Turns plus a plain-text rendering |

---

## Module 6 — scoring

### `POST /api/interview/{id}/score`

Scores a finished interview (ending it first if still active).

<details><summary>Response (abridged)</summary>

```json
{
  "interview_id": "int_abc123",
  "role_title": "Data Analyst",
  "difficulty": "medium",
  "rubric": { "...": "the rubric used" },

  "overall_score": 3.49,
  "overall_out_of": 5,
  "overall_percent": 69.8,
  "overall_band": "Competent",
  "overall_band_summary": "Reasonable answers, but often general where detail was needed.",
  "categories_scored": 5,
  "categories_not_tested": ["Behavioural Competency"],

  "category_scores": [
    {
      "key": "technical_accuracy",
      "name": "Technical Accuracy",
      "weight": 0.25, "weight_percent": 25.0,
      "score": 4, "score_label": "Good",
      "justification": "The explanation of inner versus left joins was correct and included the practical consequence...",
      "evidence_quote": "if you inner join stores to sales, any store with no sales that week silently disappears"
    }
  ],

  "strengths": ["Used concrete examples from real work rather than generalities."],
  "weaknesses": ["Statistical claims were hedged without explaining the underlying variation."],
  "answers_to_improve": [
    { "question": "How would you establish significance?",
      "candidate_answer_summary": "...", "why_it_fell_short": "...",
      "stronger_answer_outline": "..." }
  ],
  "recommended_topics": ["Hypothesis testing on seasonal data"],
  "improvement_plan": [{ "timeframe": "This week", "focus": "Answer structure", "actions": ["..."] }],
  "overall_comment": "...",

  "transcript": [],
  "transcript_stats": { "total_turns": 30, "candidate_answers": 15, "candidate_mean_words": 78.4 },
  "stages_completed": ["introduction", "background", "technical", "behavioural", "candidate_questions", "closing"],
  "demonstrated_skills": ["SQL", "Power BI"],
  "answer_quality_series": [0.62, 0.71, 0.58],
  "performance": { "...": "this interview's latency" },
  "assessor": { "engine": "ollama/qwen2.5:3b-instruct-q4_K_M", "degraded": false, "note": "..." },
  "disclaimer": "This is automated practice feedback generated from a transcript...",
  "scoring_ms": 24069.0
}
```
</details>

Guarantees enforced in code, not left to the model:

- `category_scores` always contains exactly the rubric's categories, with its
  exact keys. Unknown keys from the model are dropped.
- `score` is an integer 1–5, or `null` meaning **not tested** — never a guess.
- `overall_score` is computed in Python as a weighted mean over the categories
  that *were* scored, so an untested category neither inflates nor dilutes it.
- Hiring-decision language is rewritten out of all free text.

### `GET /api/interview/{id}/report`

The stored report, or `{"available": false, "message": "..."}`.

---

## Module 7 — performance

### `GET /api/metrics?voice_only=false`

```json
{
  "summary": {
    "total_turns": 90, "total_interviews": 6, "roles_tested": 3,
    "aggregates": {
      "e2e_first_audio_ms": { "samples": 90, "mean_ms": 2812.4, "median_ms": 2703.1,
                              "p90_ms": 4125.8, "min_ms": 874.1, "max_ms": 6120.3 }
    },
    "by_role": [{ "role_title": "Data Analyst", "turns": 30, "interviews": 2, "aggregates": {} }],
    "engines": { "stt": ["faster-whisper:base.en"], "tts": ["piper"],
                 "llm_providers": ["ollama"], "llm_models": ["llama3.2:3b"] },
    "metric_labels": { "e2e_first_audio_ms": "End of speech to first audio (headline)" },
    "headline_metric": "e2e_first_audio_ms",
    "meets_three_role_requirement": true,
    "notes": ["All timings are measured with time.perf_counter() inside the real request path.", "..."]
  },
  "timeline": [],
  "stage_breakdown": [{ "stage": "Speech recognition (local)", "mean_ms": 959.5 }]
}
```

### Metric definitions

| Field | Measured from | Measured to |
|---|---|---|
| `stt_ms` | start of local transcription | transcript ready |
| `llm_ttft_ms` | **end of speech** | first text token of the reply |
| `llm_total_ms` | generation start | generation complete |
| `tts_first_ms` | start of first-sentence synthesis | that WAV ready |
| `tts_total_ms` | — | sum over all sentences |
| `e2e_first_audio_ms` | **end of speech** | **first audio ready** — the headline |
| `total_ms` | **end of speech** | whole turn complete |

Median and p90 are reported alongside the mean because a mean alone hides the
tail that users actually notice. Percentiles use nearest-rank with no
interpolation, which stays honest at small sample sizes. Readings above 180 s are
rejected as broken measurements rather than stored, and the rejection is logged.

### Other metrics endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/metrics/interview/{id}` | Per-turn and aggregate timings for one interview |
| `GET` | `/api/metrics/export` | Self-describing JSON download |
| `GET` | `/api/metrics/export.csv` | Per-turn CSV for the report's tables |
| `DELETE` | `/api/metrics` | Clear all measurements |

---

## System

### `GET /api/system/health?deep=false`

The first endpoint to hit. `deep=true` additionally probes the language model and
every job source over the network — slower, but what you want before a demo.

```json
{
  "status": "ok",
  "uptime_seconds": 412.7,
  "components": {
    "database": { "ok": true, "schema_version": "3", "row_counts": {} },
    "llm": { "provider": "ollama", "model": "qwen2.5:3b-instruct-q4_K_M", "degraded": false, "reachable": true },
    "speech_recognition": { "runs_locally": true, "installed": true },
    "text_to_speech": { "runs_locally": true, "active_engine": "piper" },
    "job_sources": { "checked": false, "configured": 6, "enabled": true },
    "skill_taxonomy": { "canonical_skills": 175, "alias_entries": 849, "categories": 14, "implication_edges": 60 },
    "scrape_cache": { "entries": 18, "size_bytes": 4218880, "ttl_seconds": 21600 }
  },
  "degradations": [],
  "runtime": { "python": "3.12.10", "platform": "Windows 11" },
  "privacy": {
    "cv_storage": "Local SQLite file on this machine only.",
    "audio_storage": "Recordings are transcribed in memory and the temporary file is deleted immediately.",
    "speech_processing": "Fully local (faster-whisper + Piper). No audio leaves the machine.",
    "llm_processing": "Fully local (no external calls).",
    "scraping": "Only public job-board APIs and feeds are queried. No personal data is sent."
  }
}
```

`status` is `degraded` whenever anything is running below full capability, with
`degradations` explaining each in plain language. The offline LLM engine always
counts as degraded — the product never quietly pretends to have a model.

### `POST /api/system/normalise`

The skill-normalisation demonstration.

```json
{ "skills": "React, ReactJS, React.js, Node.js, NodeJS, Postgres, PostgreSQL" }
```

```json
{
  "input_count": 7,
  "output_count": 3,
  "output": [
    { "canonical": "React", "surface_forms": ["React", "ReactJS", "React.js"],
      "stage": "exact-alias", "confidence": 1.0 }
  ],
  "merge_evidence": [],
  "lookup_keys": { "React.js": "react", "ReactJS": "react", "NodeJS": "node" }
}
```

### Other system endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/system/dashboard` | Everything the Dashboard needs, in one round trip |
| `GET` | `/api/system/settings` | Current settings — API keys as present/absent only, never values |
| `PATCH` | `/api/system/settings` | Change a whitelisted setting, persisted to `backend/.env` |
| `GET` | `/api/system/taxonomy` | The full skill taxonomy |
| `GET` | `/api/system/storage` | Database, cache and model-cache sizes |
| `DELETE` | `/api/system/storage` | **Delete all user data** (the privacy control) |
| `GET` | `/api/ping` | Liveness |
| `GET` | `/` | Service banner listing the seven modules |

`PATCH /api/system/settings` accepts only `llm_provider`, `llm_model`,
`llm_fast_model`, `stt_model_size`, `tts_engine`, `tts_voice`, `scrape_enabled`,
`stt_enabled`, `tts_enabled`. Anything else is ignored, so the endpoint cannot be
used to write a secret or an arbitrary variable. Unrecognised fields come back as
`{"updated": {}}`.
