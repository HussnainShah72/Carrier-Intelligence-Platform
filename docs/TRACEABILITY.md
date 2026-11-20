# Requirements Traceability Matrix

Every requirement in the course specification, mapped to where it is
implemented, which test covers it, and how it was verified.

**Status key:** ✅ implemented and verified · ⚠️ implemented with a documented
limitation · ❌ not implemented

Sources of truth: `Project.pdf` (course specification) and the additional
Complex Computing Problem (CCP) requirements for the report.

---

## A. General requirements (specification, page 1)

| # | Requirement | Status | Where | Verified by |
|---|---|---|---|---|
| A1 | LLM APIs allowed | ✅ | `services/llm/client.py` — Anthropic, OpenAI, Gemini, Groq, Ollama | `probe_llm()`; Settings page live check |
| A2 | Speech recognition must be **local** (API not accepted) | ✅ | `services/speech/stt.py` — faster-whisper in-process | `test_speech_and_scraping.py::test_stt_describes_itself_as_local`, `::test_live_round_trip_tts_then_stt` |
| A3 | Text to speech must be **local** | ✅ | `services/speech/tts.py` — Piper ONNX in-process | `::test_tts_describes_itself_as_local`, `::test_live_tts_produces_audio` |
| A4 | Model sizes a laptop can handle; test speed early | ✅ | Whisper `base.en` int8 CPU (145 MB); Piper medium (63 MB); 3B LLMs | Measured RTF: STT 0.086, TTS 0.035 — [EVALUATION.md](../evaluation/EVALUATION.md) |
| A5 | A user interface usable without touching code | ✅ | `frontend/` — 8 pages, React + TypeScript | Screenshots 1–24; `npm run build` succeeds |
| A6 | Not a notebook or a command-line script | ✅ | Web app: React frontend + FastAPI backend | — |
| A7 | Must run on a normal laptop by following the README | ✅ | [README.md](../README.md) | Installed from scratch in a clean venv; 382 tests pass |
| A8 | Must be explainable at a viva; prompts reproducible | ✅ | Every prompt in one file: `services/llm/prompts.py`; [VIVA_PREPARATION.md](VIVA_PREPARATION.md) | — |

---

## B. Module 1 — CV parser (specification, page 3)

> *"Extracts skills, roles, education, and projects from PDF or Word CVs into
> structured data."*

| # | Requirement | Status | Where | Verified by |
|---|---|---|---|---|
| B1 | Upload PDF CVs | ✅ | `cv/extractor.py::_extract_pdf` — pdfplumber, pypdf fallback | `test_cv_parser.py::test_extract_pdf` |
| B2 | Upload Word DOCX CVs | ✅ | `cv/extractor.py::_extract_docx` — incl. tables and headers | `::test_extract_docx`, `test_api.py::test_cv_upload_docx` |
| B3 | Extract text reliably | ✅ | Two PDF engines; fallback on empty text layer | `::test_extract_pdf`, `::test_extract_computes_a_stable_hash` |
| B4 | Extract **skills** | ✅ | `cv/parser.py` skills section + project tech + whole-document fallback | `::test_parse_extracts_skills` |
| B5 | Extract **education** | ✅ | `_parse_education` — degree, field, institution, dates, grade | `::test_parse_extracts_education_with_grade` |
| B6 | Extract **work experience** | ✅ | `_parse_experience` — title, company, dates, bullets | `::test_parse_extracts_experience` |
| B7 | Extract **job roles** | ✅ | `_collect_job_roles` | `::test_parse_collects_job_roles` |
| B8 | Extract **projects** | ✅ | `_parse_projects` — name, description, technologies, link | `::test_parse_extracts_projects_without_splitting_descriptions` |
| B9 | Extract certifications where available | ✅ | `_parse_certifications` | `::test_parse_extracts_certifications` |
| B10 | Convert to structured data | ✅ | `CVProfile` dataclass → JSON | `::test_profile_round_trips_to_a_dict` |
| B11 | Handle malformed files | ✅ | Magic-byte check, corrupt-PDF and corrupt-DOCX paths | `::test_corrupt_pdf_raises_a_readable_error`, `::test_corrupt_docx_raises_a_readable_error` |
| B12 | Handle empty documents | ✅ | `EmptyDocumentError` | `::test_empty_file_is_rejected`, `::test_empty_text_parses_to_an_empty_profile` |
| B13 | Handle unsupported formats | ✅ | `UnsupportedFileError`; extension **and** magic bytes | `::test_unsupported_extension_is_rejected`, `::test_file_claiming_to_be_pdf_is_rejected` |
| B14 | Handle parsing errors | ✅ | Typed errors with user-safe messages | `test_api.py::test_cv_upload_rejections` (4 cases) |
| B15 | Display extracted information | ✅ | `pages/CVAnalysis.tsx` — 6 tabs | Screenshots 3–5 |
| B16 | **Avoid inventing information not in the CV** | ✅ | `enforce_grounding()`; LLM fills blanks only; bullets verbatim only | `::test_prompt_injection_in_a_cv_is_treated_as_text_not_instruction`; `rejected_claims` shown in the UI |

---

## C. Module 2 — job scraper and skills generator (specification, page 3)

> *"Your system must scrape live job postings from job sites **and also** use an
> LLM to generate the skills and expectations of that role. Both are required.
> The final skills list for the role combines the two sources. Similar skill
> names (for example "React", "ReactJS", "React.js") must be treated as one
> skill."*

### C.A — Live job posting collection

| # | Requirement | Status | Where | Verified by |
|---|---|---|---|---|
| CA1 | Scrape **live** job postings from job sites | ✅ | `jobs/sources.py` — 6 sources, one of which parses RSS/XML markup | `::test_live_collection_returns_postings_with_descriptions`; 24 postings collected per role in the evaluation |
| CA2 | Retrieve listings relevant to the entered role | ✅ | `relevance_score()` — title 65% / tags 20% / body 15% | `::test_title_matches_outrank_body_mentions`, `::test_irrelevant_posting_falls_below_the_threshold` |
| CA3 | Extract titles, descriptions, required skills | ✅ | Per-source adapters → `JobPosting`; `_taxonomy_skills` + LLM on the top 4 | `::test_wwr_title_is_split_into_company_and_role`, `::test_html_to_text_keeps_list_structure` |
| CA4 | Handle unavailable pages, network errors, rate limits, malformed data | ✅ | 8 named failure statuses in `jobs/http.py` | `::test_failed_fetch_never_claims_success`, `::test_empty_200_response_is_treated_as_a_failure` |
| CA5 | **Do not pretend scraping succeeded if it did not** | ✅ | `SourceReport` per source, surfaced in the UI | `::test_robots_block_is_reported_as_a_named_failure`; Screenshot 8 |
| CA6 | Respect website terms, robots policies, rate limits | ✅ | `robots.txt` fetched/cached/obeyed; per-host interval; `Crawl-delay`; descriptive UA | `::test_user_agent_identifies_the_project_rather_than_a_browser`, `::test_rate_limiting_is_configured` |
| CA7 | If a source blocks scraping, use a legitimate alternative **or disclose** | ✅ | LinkedIn/Indeed/Glassdoor explicitly excluded and named as such | `test_api.py::test_role_sources_lists_compliance` |

### C.B — LLM role skill generation

| # | Requirement | Status | Where | Verified by |
|---|---|---|---|---|
| CB1 | Use an LLM to generate skills, qualifications, tools, expectations | ✅ | `prompts.py::role_skills_prompt` — 5 tiers | `test_api.py::test_role_analysis_with_offline_engine_still_produces_requirements` |
| CB2 | Combine posting skills **and** LLM skills | ✅ | `collector.py::fuse_skills` | `::test_fusion_marks_provenance_correctly`, `::test_agreement_outranks_a_single_source` |
| CB3 | Normalise similar names (React / ReactJS / React.js) | ✅ | `skills/{taxonomy,text_norm,normalizer}.py` — 4-stage cascade | **15 parametrised cases** in `test_skill_normalisation.py`; `::test_react_variants_collapse_to_a_single_entry`; live demo on Settings |
| CB4 | Show the sources of job requirements where feasible | ✅ | `provenance` on every skill: `scraped` / `llm` / `both`; `example_sources` | `::test_fusion_normalises_variants_across_sources`; Screenshots 6, 9 |
| CB5 | Handle **any** job title (no fixed list) | ✅ | Free-text input; `title_assessment` flags vague titles | `test_api.py::test_role_analysis_handles_an_unusual_title` ("Chief Vibes Officer") |

---

## D. Module 3 — match and gap analysis (specification, page 3)

> *"Compares the CV with the combined skills list, shows the missing skills, and
> ranks which gaps matter most."*

| # | Requirement | Status | Where | Verified by |
|---|---|---|---|---|
| D1 | Compare CV against combined requirements | ✅ | `skills/matcher.py::analyse_gap` | `::test_exact_match_is_matched`, `::test_absent_skill_is_missing` |
| D2 | Display matched skills | ✅ | `GapResult.matched` | `test_api.py::test_gap_analysis_endpoint` |
| D3 | Display missing skills | ✅ | `GapResult.missing` | ditto |
| D4 | Display **partially** matched skills, if supported reliably | ✅ | 3 partial routes: implied-by, foundation-present, name-similarity | `::test_implied_skill_is_a_partial_match`, `::test_foundation_present_is_a_partial_match` |
| D5 | Skill match percentage | ✅ | Importance-weighted; unweighted reported alongside | `::test_score_is_weighted_by_importance` |
| D6 | Gap severity / priority | ✅ | critical / high / medium / low | `::test_severity_escalates_for_missing_essentials` |
| D7 | **Rank which gaps matter most** | ✅ | `priority_gaps()` — severity then importance | `::test_priority_gaps_are_ordered_by_severity_then_importance` |
| D8 | Recommended learning priorities | ✅ | `routes_gap.py::_generate_advice` + validity filter | `test_api.py::test_gap_analysis_endpoint` |
| D9 | Useful, visually understandable dashboard | ✅ | `pages/SkillGap.tsx` — ring, bar, radar, 5 tabs | Screenshots 10–11 |
| D10 | **No misleading claims about suitability** | ✅ | "requirement coverage" wording; descriptive label; disclaimer beside the number | `::test_result_never_claims_employability` |

---

## E. Module 4 — CV improvement (specification, page 3)

> *"Rewrites weak bullet points without inventing experience, and shows the
> original next to the new version."*

| # | Requirement | Status | Where | Verified by |
|---|---|---|---|---|
| E1 | Improve CV bullet points | ✅ | `improve/bullets.py` | `test_api.py::test_improve_bullets_endpoint` |
| E2 | Rewrite weak bullets professionally | ✅ | `BULLET_IMPROVE_SYSTEM` prompt | `::test_improve_end_to_end_with_the_offline_engine` |
| E3 | Improve clarity and action-oriented wording | ✅ | Filler removal, verb strengthening | `::test_weakness_detection_flags_the_usual_suspects` |
| E4 | Improve measurable impact **where genuine metrics exist** | ✅ | `metrics_preserved`; existing metrics kept | `::test_guard_allows_a_metric_that_was_already_there` |
| E5 | Preserve the user's original experience | ✅ | Rejected rewrite returns `improved == original` | `::test_guard_blocks_an_invented_metric` |
| E6 | **NEVER invent metrics** | ✅ | `unsupported_numbers()` → hard reject | `::test_guard_blocks_an_invented_metric` |
| E7 | **NEVER invent achievements or responsibilities** | ✅ | Scope-escalation check | `::test_guard_blocks_escalated_scope` (5 verbs) |
| E8 | **NEVER invent qualifications or skills** | ✅ | `skills_in_text()` → hard reject | `::test_guard_blocks_an_invented_technology` |
| E9 | Show original and improved side by side | ✅ | `pages/Improve.tsx` two-column layout | Screenshot 12 |
| E10 | Allow accept / reject / copy | ✅ | Per-bullet controls; decision persisted | `test_api.py::test_improvement_decision_round_trip` |

---

## F. Module 5 — structured voice interview (specification, page 3)

> *"A spoken interview that follows the stages above, asks follow-up questions
> based on earlier answers, and adapts its difficulty. Speech recognition and
> text to speech must both run locally."*

### F.A — Interview structure

| # | Requirement | Status | Where | Verified by |
|---|---|---|---|---|
| FA1 | Stage 1: Introduction | ✅ | `stages.py::INTRODUCTION` | `::test_stage_order_matches_the_specification` |
| FA2 | Stage 2: Candidate background | ✅ | `BACKGROUND` | ditto |
| FA3 | Stage 3: Technical questions for the role | ✅ | `TECHNICAL` | ditto |
| FA4 | Stage 4: Behavioural questions | ✅ | `BEHAVIOURAL` | ditto |
| FA5 | Stage 5: Candidate's own questions | ✅ | `CANDIDATE_QUESTIONS` | `::test_candidate_questions_stage_ends_when_they_have_none` |
| FA6 | Stage 6: Closing | ✅ | `CLOSING` | `::test_stages_advance_in_order_to_completion` |
| FA7 | All stages actually reached in practice | ✅ | — | Evaluation: all 6 stages reached in **6 of 6** interviews |

### F.B — Adaptation

| # | Requirement | Status | Where | Verified by |
|---|---|---|---|---|
| FB1 | Adapt to the uploaded CV | ✅ | `candidate_context_block()`; `cv_talking_points` in the plan | `test_api.py::test_text_interview_runs_through_every_stage`; transcripts quote CV specifics |
| FB2 | Adapt to the selected job role | ✅ | `role_context_block()`; `technical_topics` | Evaluation transcripts per role |
| FB3 | Adapt to previous answers | ✅ | `answer_analysis.py` + `coverage_note()` | `::test_coverage_note_tells_the_model_what_to_do` |
| FB4 | Adapt to demonstrated knowledge | ✅ | `demonstrated_skills` tracked across turns | `::test_role_relevant_skills_are_weighted_higher` |
| FB5 | Adapt interview difficulty | ✅ | `adapt_difficulty()`, bounded to ±1 band | `::test_difficulty_moves_at_most_one_band` (8 cases) |
| FB6 | **Ask follow-up questions based on earlier responses** | ✅ | `should_follow_up()`, depth-capped at 2 | `::test_follow_up_on_a_substantive_answer`, `::test_follow_up_depth_is_bounded`; **20 follow-ups** across the evaluation |
| FB7 | Feel conversational, not a fixed questionnaire | ✅ | Questions generated per turn from live context | Evaluation transcripts; Screenshot 15 |

### F.C — Mandatory local speech

| # | Requirement | Status | Where | Verified by |
|---|---|---|---|---|
| FC1 | **Speech recognition runs locally** | ✅ | faster-whisper, in-process, nothing written to disk | `::test_live_round_trip_tts_then_stt`; health states `runs_locally: true` |
| FC2 | **Text to speech runs locally** | ✅ | Piper ONNX, in-process | `::test_live_tts_produces_audio` |
| FC3 | **No cloud speech substitution** | ✅ | No cloud speech SDK anywhere in `requirements.txt` | `test_api.py::test_health_states_that_speech_is_local` |
| FC4 | Models suitable for an ordinary laptop | ✅ | 145 MB + 63 MB, CPU only | RTF 0.086 / 0.035 measured |
| FC5 | Microphone input | ✅ | `hooks/useVoice.ts` — MediaRecorder + input meter | Screenshot 15 |
| FC6 | Speech recognition in the pipeline | ✅ | `routes_interview.py::voice_turn` | 45 voice turns measured |
| FC7 | Interview response generation | ✅ | `engine.py::stream_turn` | ditto |
| FC8 | **Streaming text response** | ✅ | `LLMClient.stream()` → SSE `text` events | `llm_ttft_ms` recorded per turn |
| FC9 | Voice playback | ✅ | `useAudioQueue` — strictly ordered | Screenshot 15 |
| FC10 | Interview stage management | ✅ | `stages.py` state machine, persisted | `::test_progress_payload_is_coherent` |
| FC11 | Conversation history | ✅ | `interview_turns` table; last N turns in the prompt | `test_api.py::test_text_interview_runs_through_every_stage` |
| FC12 | Graceful recovery when audio recognition fails | ✅ | `no_speech` event; `fallback: "text"`; typed `SpeechError` | `::test_tiny_recording_returns_no_speech_rather_than_an_error`, `::test_undecodable_audio_is_rejected_with_a_helpful_message` |
| FC13 | Text fallback **in addition to** a real voice interview | ✅ | "Type instead" always available; voice is the default | `test_api.py::test_text_interview_runs_through_every_stage` |
| FC14 | **Start the voice before the full reply is ready** | ✅ | `_take_complete_sentence()` → per-sentence synthesis | `::test_sentence_is_emitted_as_soon_as_it_completes`; `tts_first_ms` median 237 ms vs `llm_total_ms` median 2618 ms |

---

## G. Module 6 — scoring and feedback (specification, page 3)

> *"Scores the interview against a written rubric that you define in advance, and
> explains every score."*

| # | Requirement | Status | Where | Verified by |
|---|---|---|---|---|
| G1 | **Rubric defined in advance** | ✅ | `interview/rubric.py`, fixed in source control, served before the interview | `::test_rubric_is_defined_in_advance`; `GET /api/interview/rubric` |
| G2 | Scoring scale defined before evaluating | ✅ | 1–5 with a written descriptor per level | `::test_scale_covers_one_to_five_with_descriptors` |
| G3 | Weighting defined before evaluating | ✅ | Per-difficulty weights summing to 1.0 | `::test_weights_sum_to_one` (3 difficulties) |
| G4 | Score: technical accuracy | ✅ | `technical_accuracy` | `::test_rubric_covers_the_categories_the_specification_asks_for` |
| G5 | Score: conceptual understanding | ✅ | `conceptual_understanding` | ditto |
| G6 | Score: communication | ✅ | `communication` | ditto |
| G7 | Score: problem solving | ✅ | `problem_solving` | ditto |
| G8 | Score: relevance | ✅ | `relevance` | ditto |
| G9 | Score: behavioural competency | ✅ | `behavioural_competency` | ditto |
| G10 | Overall score | ✅ | Weighted mean **computed in Python**, not by the model | `test_api.py::test_text_interview_runs_through_every_stage` |
| G11 | Category scores | ✅ | One entry per rubric category, always | `scorer.py` fills any the model omitted as "not tested" |
| G12 | **Explanation for every score** | ✅ | `justification` + `evidence_quote` per category | `test_api.py` asserts every category has a justification |
| G13 | Strengths | ✅ | `strengths[]` | ditto |
| G14 | Weaknesses | ✅ | `weaknesses[]` | ditto |
| G15 | Examples of answers that could be improved | ✅ | `answers_to_improve[]` with a stronger-answer outline | Screenshot 18 |
| G16 | Recommended preparation topics | ✅ | `recommended_topics[]` | Screenshot 19 |
| G17 | Personalised improvement plan | ✅ | `improvement_plan[]` — timeframe, focus, actions | Screenshot 19 |
| G18 | Transparent | ✅ | Rubric, weights, justifications and assessor engine all shown | Screenshots 16–17 |
| G19 | **Must not pretend to be an objective hiring decision** | ✅ | `_sanitise()` rewrites hiring language; disclaimer in payload and UI | `::test_hiring_verdicts_are_rewritten` (9 phrasings), `::test_rubric_disclaimer_denies_being_a_hiring_decision` |

---

## H. Module 7 — performance report (specification, page 3)

> *"Measure and report the time from the end of the candidate's speech to the
> start of the interviewer's reply. Test the system on at least three very
> different roles."*

| # | Requirement | Status | Where | Verified by |
|---|---|---|---|---|
| H1 | **Measure end-of-speech → start of reply** | ✅ | `e2e_first_audio_ms`, referenced to `speech_ended_at` | 45 voice turns; median 2794 ms |
| H2 | Speech recognition processing time | ✅ | `stt_ms` | median 960 ms |
| H3 | LLM generation time | ✅ | `llm_total_ms` | median 2618 ms |
| H4 | Time to first generated text | ✅ | `llm_ttft_ms` | median 2137 ms |
| H5 | TTS processing time | ✅ | `tts_first_ms`, `tts_total_ms` | median 237 ms / 865 ms |
| H6 | End-of-speech to first audio latency | ✅ | `e2e_first_audio_ms` — the headline | median 2794 ms |
| H7 | Total response latency | ✅ | `total_ms` | median 3706 ms |
| H8 | **Test on at least THREE very different roles** | ✅ | Software Engineer, Data Analyst, Cybersecurity Analyst | `meets_three_role_requirement: true`; [EVALUATION.md](../evaluation/EVALUATION.md) |
| H9 | **Record genuine results; do not invent numbers** | ✅ | `perf_counter()` in the real request path; `IMPLAUSIBLE_MS` guard | `::test_metrics_summarise_handles_no_samples`, `::test_percentile_is_nearest_rank` |
| H10 | Performance results dashboard | ✅ | `pages/Performance.tsx` | Screenshots 20–21 |
| H11 | Exportable evaluation report | ✅ | JSON + CSV export; `evaluation/results/*.json` | `test_api.py::test_metrics_export_is_self_describing`, `::test_metrics_csv_export` |
| H12 | Repeated trials for reliability | ✅ | `--trials 2` → 6 interviews, 2 per role | [EVALUATION.md](../evaluation/EVALUATION.md) variance section |

---

## I. User interface (project brief, Phase 3)

| # | Requirement | Status | Where |
|---|---|---|---|
| I1 | Dashboard page | ✅ | `pages/Dashboard.tsx` — overview, recent analyses, profile summary, progress, quick actions |
| I2 | CV Analysis page | ✅ | `pages/CVAnalysis.tsx` — upload, progress, profile, skills, education, experience, projects |
| I3 | Job Role Analysis page | ✅ | `pages/RoleAnalysis.tsx` — any title, collection, LLM generation, normalisation, sources |
| I4 | Skill Gap Dashboard | ✅ | `pages/SkillGap.tsx` — matched, missing, priority, charts, recommendations |
| I5 | CV Improvement Studio | ✅ | `pages/Improve.tsx` — original, improved, explanation, accept/reject/copy |
| I6 | Mock Interview page | ✅ | `pages/Interview.tsx` — role, difficulty, spoken interview, stages, transcripts, audio, progress, end |
| I7 | Interview Results page | ✅ | `pages/Results.tsx` — score, rubric, strengths, weaknesses, recommendations, metrics, transcript |
| I8 | Settings page | ✅ | `pages/Settings.tsx` — API config, local models, privacy, storage, health checks |
| I9 | Professional, not a student CRUD app | ✅ | Design tokens, light+dark, 7 chart types, loading/error/empty states throughout |
| I10 | Loading, error and empty states | ✅ | `components/ui.tsx` — `Loading`, `ErrorState`, `EmptyState`, `Skeleton` |
| I11 | Accessible controls | ✅ | ARIA roles/labels, visible focus rings, `prefers-reduced-motion`, keyboard operable |
| I12 | Responsive layout | ✅ | Mobile-first Tailwind; collapsible sidebar |

---

## J. Implementation quality (project brief, Phase 4)

| # | Requirement | Status | Evidence |
|---|---|---|---|
| J1 | Clean, readable code | ✅ | Module docstrings explaining *why*; typed throughout |
| J2 | Sensible file organisation | ✅ | `core` / `api` / `schemas` / `services/<module>` |
| J3 | Modules separated | ✅ | One package per core module |
| J4 | Avoid duplication | ✅ | Shared `skills`, `llm`, `ui.tsx` primitives |
| J5 | Environment variables for secrets | ✅ | `core/config.py` + `.env`; nothing hard-coded |
| J6 | Never commit API keys | ✅ | `.gitignore` excludes `.env`, keeps `.env.example`; verified with `git check-ignore` |
| J7 | Example environment file | ✅ | `backend/.env.example`, fully commented |
| J8 | Validate user input | ✅ | `schemas/models.py` — length caps, character bans, enums |
| J9 | Handle exceptions properly | ✅ | Typed `AppError` hierarchy + three handlers |
| J10 | Never expose internal errors or secrets | ✅ | `test_api.py::test_errors_never_leak_internals`, `::test_settings_never_returns_api_keys` |
| J11 | Appropriate logging | ✅ | `logging_setup.py` — console + rotating file |
| J12 | Dependency files | ✅ | `requirements.txt` (ranges) + `requirements.lock.txt` (exact) + `package.json` |
| J13 | Database initialisation | ✅ | `db.py::init_db()`, idempotent on boot |
| J14 | Testable interfaces | ✅ | 382 tests; services callable without HTTP |
| J15 | Runnable locally | ✅ | Two commands, documented in the README |
| J16 | Reasonable defaults | ✅ | Works with zero `.env` edits |
| J17 | Protect against LLM hallucinations | ✅ | Section 11 of [TECHNICAL.md](TECHNICAL.md); grounding + guards |
| J18 | Protect against invalid JSON | ✅ | `parse_json_payload()` 5-step cascade | 
| J19 | Protect against prompt injection in CVs | ✅ | `wrap_untrusted()` + `strip_injection_lines()` |
| J20 | Protect against malicious file uploads | ✅ | Magic bytes, size cap, zip-bomb guard |
| J21 | Protect against API failures | ✅ | Typed `LLMError`; offline engine; per-source failure reporting |
| J22 | Protect against web scraping failures | ✅ | 8 named statuses; honest UI reporting |
| J23 | Validate AI output before use | ✅ | Every LLM call goes through `json_guard` |
| J24 | Use structured output | ✅ | Explicit JSON schema in every prompt |

---

## K. Submission requirements (specification, pages 5–6)

| # | Requirement | Status | Where |
|---|---|---|---|
| K1 | GitHub repository with full code, documentation and tests | ✅ | This repository |
| K2 | **System architecture diagram** | ✅ | [docs/diagrams/architecture.md](diagrams/architecture.md) — 8 diagrams |
| K3 | README: names and registration numbers | ✅ | [README.md](../README.md) — Hussnain Haider (i230695), Akbar Hussain (i233094); generated from `scripts/report_content.py` and verified by `scripts/verify_submission.py` |
| K4 | README: which project, models, APIs, what runs locally | ✅ | README § "Which project, which models, what runs locally" |
| K5 | README: architecture description with a diagram | ✅ | README § Architecture + linked diagrams |
| K6 | 2–3 minute Loom video with a demo | ❌ | **Must be recorded by the student** — script in [VIVA_PREPARATION.md](VIVA_PREPARATION.md) § Demonstration script |
| K7 | Report: explains the core modules | ✅ | `report/` § 13 Core Modules |
| K8 | Report: setup and technical details | ✅ | `report/` § 14 Technical Implementation |
| K9 | Report: Critical Analysis section | ✅ | `report/` § 18 |

---

## L. Critical Analysis / CCP requirements (specification, page 6)

| # | Requirement | Status | Where |
|---|---|---|---|
| L1 | **Problem Statement** — the real-world gap, and why a standard solution does not solve it | ✅ | Report § 5 and § 18.1 |
| L2 | **Complexity Drivers** — conflicting requirements, no obvious solution, several interacting components | ✅ | Report § 18.2 — 7 drivers with evidence |
| L3 | **Design Justification** — at least two alternatives considered, with a clear reason each was rejected | ✅ | Report § 18.3 — 5 alternatives analysed |
| L4 | **Trade-off Analysis** — the main trade-offs and the choices made, with reasons | ✅ | Report § 18.4 — 8 trade-offs |
| L5 | **Societal and Ethical Impact** — legal, privacy, safety, fairness | ✅ | Report § 21 and § 18.5, separating implemented from proposed mitigation |

---

## Summary

| Category | Requirements | ✅ | ⚠️ | ❌ |
|---|---|---|---|---|
| A. General | 8 | 8 | 0 | 0 |
| B. Module 1 — CV parser | 16 | 16 | 0 | 0 |
| C. Module 2 — scraping + LLM | 12 | 12 | 0 | 0 |
| D. Module 3 — gap analysis | 10 | 10 | 0 | 0 |
| E. Module 4 — CV improvement | 10 | 10 | 0 | 0 |
| F. Module 5 — voice interview | 27 | 27 | 0 | 0 |
| G. Module 6 — scoring | 19 | 19 | 0 | 0 |
| H. Module 7 — performance | 12 | 12 | 0 | 0 |
| I. User interface | 12 | 12 | 0 | 0 |
| J. Implementation quality | 24 | 24 | 0 | 0 |
| K. Submission | 9 | 7 | 1 | 1 |
| L. Critical analysis | 5 | 5 | 0 | 0 |
| **Total** | **164** | **162** | **1** | **1** |

### The one outstanding item

It requires the students, not the code:

1. **K6 ❌ — the 2–3 minute Loom video.** Cannot be produced by the codebase. A
   shot-by-shot script with timings is in
   [VIVA_PREPARATION.md](VIVA_PREPARATION.md) § Demonstration script.

K3 (names and registration numbers) is now satisfied: the two members are
recorded in `scripts/report_content.py`, from which the README table and the
report title page are both generated, and `scripts/verify_submission.py` fails
if either deliverable is missing a name or a number.
