# Test Report

**This document is generated from an actual test run.** Regenerate it with:

```bash
python scripts/make_test_report.py
```

Generated: 2026-11-20T21:45:31+00:00

---

## Summary

| | Count |
|---|---|
| **Total tests** | **408** |
| Passed | 408 |
| Failed | 0 |
| Skipped | 0 |
| Offline suite (no model, no network) | 403 |
| Live suite (real models + network) | 5 |

- Offline run: `403 passed, 5 deselected in 5.30s`
- Live run: `5 passed, 403 deselected in 10.60s`

> All tests pass.

## How the suite is designed

The default suite runs against the **deterministic offline engine**
(`LLM_PROVIDER=offline`) with scraping disabled. That is deliberate: a sampling
language model gives different output every run, which would make the tests
either flaky or so loose that they assert nothing. These tests therefore check
*the application's own logic* — parsing, normalisation, matching, the guards, the
state machine, persistence, the HTTP contract — rather than the model's mood, and
they pass identically on every run.

Tests that genuinely need a downloaded model or live internet are marked `live`
and skipped by default:

```bash
pytest -m "not live"   # the default
pytest -m live         # needs Whisper + Piper downloaded, and network
pytest                 # everything
```

The headline live test synthesises a sentence with local TTS, transcribes it with
local STT, and asserts the content words survive — a genuine end-to-end check of
the mandatory local speech requirement.

---

## Offline test suite

No language model and no network access. Fully reproducible.

### `test_api.py` — HTTP API contract, database, metrics

*Covers: All. 60/60 passed.*

| # | Test case | Expected result | Actual | Status |
|---|---|---|---|---|
| 1 | `test_root_lists_the_seven_modules` | Root lists the seven modules. | Passed | ✅ |
| 2 | `test_ping` | Ping. | Passed | ✅ |
| 3 | `test_health_reports_every_component` | Health reports every component. | Passed | ✅ |
| 4 | `test_health_declares_the_offline_engine_as_degraded` | Health declares the offline engine as degraded. | Passed | ✅ |
| 5 | `test_health_states_that_speech_is_local` | Health states that speech is local. | Passed | ✅ |
| 6 | `test_taxonomy_endpoint` | Taxonomy endpoint. | Passed | ✅ |
| 7 | `test_normalisation_endpoint_demonstrates_the_react_requirement` | Normalisation endpoint demonstrates the react requirement. | Passed | ✅ |
| 8 | `test_settings_never_returns_api_keys` | Settings never returns api keys. | Passed | ✅ |
| 9 | `test_settings_rejects_unknown_fields` | Settings rejects unknown fields. | Passed | ✅ |
| 10 | `test_dashboard_endpoint` | Dashboard endpoint. | Passed | ✅ |
| 11 | `test_cv_limits` | Cv limits. | Passed | ✅ |
| 12 | `test_cv_upload_and_fetch` | Cv upload and fetch. | Passed | ✅ |
| 13 | `test_cv_upload_docx` | Cv upload docx. | Passed | ✅ |
| 14 | `test_cv_upload_rejections`<br/>*4 cases* | Cv upload rejections. | Passed (4 cases) | ✅ |
| 15 | `test_cv_404_is_shaped_consistently` | Cv 404 is shaped consistently. | Passed | ✅ |
| 16 | `test_errors_never_leak_internals` | Errors never leak internals. | Passed | ✅ |
| 17 | `test_role_sources_lists_compliance` | Role sources lists compliance. | Passed | ✅ |
| 18 | `test_role_title_validation`<br/>*7 cases* | Role title validation. | Passed (7 cases) | ✅ |
| 19 | `test_role_analysis_without_scraping_or_llm` | Both sources off must warn, not crash. | Passed | ✅ |
| 20 | `test_role_analysis_with_offline_engine_still_produces_requirements` | Role analysis with offline engine still produces requirements. | Passed | ✅ |
| 21 | `test_role_analysis_handles_an_unusual_title` | There is no fixed list of roles, so a nonsense title must still work. | Passed | ✅ |
| 22 | `test_gap_analysis_endpoint` | Gap analysis endpoint. | Passed | ✅ |
| 23 | `test_gap_analysis_rejects_unknown_ids` | Gap analysis rejects unknown ids. | Passed | ✅ |
| 24 | `test_bullet_ranking_endpoint_needs_no_llm` | Bullet ranking endpoint needs no llm. | Passed | ✅ |
| 25 | `test_improve_bullets_endpoint` | Improve bullets endpoint. | Passed | ✅ |
| 26 | `test_improve_bullets_validation` | Improve bullets validation. | Passed | ✅ |
| 27 | `test_improvement_decision_round_trip` | Improvement decision round trip. | Passed | ✅ |
| 28 | `test_rubric_endpoint_is_available_before_the_interview` | Rubric endpoint is available before the interview. | Passed | ✅ |
| 29 | `test_stages_endpoint` | Stages endpoint. | Passed | ✅ |
| 30 | `test_speech_health_endpoint` | Speech health endpoint. | Passed | ✅ |
| 31 | `test_interview_start_validation`<br/>*5 cases* | Interview start validation. | Passed (5 cases) | ✅ |
| 32 | `test_text_interview_runs_through_every_stage` | A full interview, driven in text mode against the deterministic engine. | Passed | ✅ |
| 33 | `test_turn_on_a_finished_interview_is_refused` | Turn on a finished interview is refused. | Passed | ✅ |
| 34 | `test_interview_404` | Interview 404. | Passed | ✅ |
| 35 | `test_scoring_an_interview_with_no_answers` | Scoring an interview with no answers. | Passed | ✅ |
| 36 | `test_transcribe_rejects_an_oversized_upload` | Transcribe rejects an oversized upload. | Passed | ✅ |
| 37 | `test_metrics_overview_shape` | Metrics overview shape. | Passed | ✅ |
| 38 | `test_metrics_export_is_self_describing` | Metrics export is self describing. | Passed | ✅ |
| 39 | `test_metrics_csv_export` | Metrics csv export. | Passed | ✅ |
| 40 | `test_metrics_summarise_handles_no_samples` | Metrics summarise handles no samples. | Passed | ✅ |
| 41 | `test_percentile_is_nearest_rank` | Percentile is nearest rank. | Passed | ✅ |
| 42 | `test_storage_stats_and_clear` | Storage stats and clear. | Passed | ✅ |
| 43 | `test_json_columns_round_trip` | Json columns round trip. | Passed | ✅ |
| 44 | `test_activity_log_records_actions` | Activity log records actions. | Passed | ✅ |
| 45 | `test_cascade_delete_removes_dependent_rows` | Cascade delete removes dependent rows. | Passed | ✅ |
| 46 | `test_a_rate_limited_turn_reaches_the_user_with_advice` | A rate limited turn reaches the user with advice. | Passed | ✅ |
| 47 | `test_the_interview_survives_a_failed_turn` | A throttled turn must be retryable. If the engine advanced the stage or closed the interview on failure, a single 429 would cost the student their whole sess… | Passed | ✅ |

### `test_console_encoding.py` — 

*Covers: —. 8/8 passed.*

| # | Test case | Expected result | Actual | Status |
|---|---|---|---|---|
| 1 | `test_the_exact_character_crashes_an_unguarded_cp1252_stream` | Proof the bug is real and not theoretical. | Passed | ✅ |
| 2 | `test_ascii_safe_makes_the_killer_line_encodable` | Ascii safe makes the killer line encodable. | Passed | ✅ |
| 3 | `test_ascii_safe_does_not_touch_text_that_was_already_fine` | Ascii safe does not touch text that was already fine. | Passed | ✅ |
| 4 | `test_ascii_safe_folds_every_character_in_its_table_to_cp1252_safe_ascii` | Ascii safe folds every character in its table to cp1252 safe ascii. | Passed | ✅ |
| 5 | `test_install_makes_a_cp1252_stream_lossy_instead_of_fatal` | The safety net. `ascii_safe` only covers characters we anticipated; a model can emit a CJK name or an emoji at any time, and that must not end the run either. | Passed | ✅ |
| 6 | `test_install_is_idempotent_and_safe_on_an_unreconfigurable_stream` | Install is idempotent and safe on an unreconfigurable stream. | Passed | ✅ |
| 7 | `test_the_harness_log_function_is_actually_guarded` | The module being correct is not enough -- the call site has to use it. This asserts the wiring that was missing when the run died. | Passed | ✅ |
| 8 | `test_recorded_results_keep_the_original_text_not_the_folded_one` | The fold is a display concession. If it ever leaked into the stored results, the evaluation would be quietly misreporting what the model said. | Passed | ✅ |

### `test_cv_parser.py` — CV extraction and structured parsing

*Covers: Module 1. 52/52 passed.*

| # | Test case | Expected result | Actual | Status |
|---|---|---|---|---|
| 1 | `test_extract_pdf` | Extract pdf. | Passed | ✅ |
| 2 | `test_extract_docx` | Extract docx. | Passed | ✅ |
| 3 | `test_extract_txt` | Extract txt. | Passed | ✅ |
| 4 | `test_extract_computes_a_stable_hash` | Extract computes a stable hash. | Passed | ✅ |
| 5 | `test_empty_file_is_rejected` | Empty file is rejected. | Passed | ✅ |
| 6 | `test_unsupported_extension_is_rejected` | Unsupported extension is rejected. | Passed | ✅ |
| 7 | `test_other_unsupported_extensions`<br/>*7 cases* | Other unsupported extensions. | Passed (7 cases) | ✅ |
| 8 | `test_file_claiming_to_be_pdf_is_rejected` | Extension and magic bytes must agree. | Passed | ✅ |
| 9 | `test_file_claiming_to_be_docx_is_rejected` | File claiming to be docx is rejected. | Passed | ✅ |
| 10 | `test_oversized_file_is_rejected` | Oversized file is rejected. | Passed | ✅ |
| 11 | `test_corrupt_pdf_raises_a_readable_error` | Corrupt pdf raises a readable error. | Passed | ✅ |
| 12 | `test_image_only_pdf_is_identified_as_scanned` | A valid PDF with no text layer must say so, not return an empty profile. | Passed | ✅ |
| 13 | `test_corrupt_docx_raises_a_readable_error` | Corrupt docx raises a readable error. | Passed | ✅ |
| 14 | `test_very_short_cv_produces_a_warning` | Very short cv produces a warning. | Passed | ✅ |
| 15 | `test_long_document_is_truncated_with_a_warning` | Long document is truncated with a warning. | Passed | ✅ |
| 16 | `test_sections_are_detected` | Sections are detected. | Passed | ✅ |
| 17 | `test_heading_variants_map_to_the_right_section`<br/>*12 cases* | Heading variants map to the right section. | Passed (12 cases) | ✅ |
| 18 | `test_a_sentence_is_not_mistaken_for_a_heading` | 'Skills were applied to...' must not start a skills section. | Passed | ✅ |
| 19 | `test_parse_extracts_contact_details` | Parse extracts contact details. | Passed | ✅ |
| 20 | `test_parse_extracts_skills` | Parse extracts skills. | Passed | ✅ |
| 21 | `test_parse_extracts_experience` | Parse extracts experience. | Passed | ✅ |
| 22 | `test_parse_extracts_education_with_grade` | Parse extracts education with grade. | Passed | ✅ |
| 23 | `test_parse_extracts_projects_without_splitting_descriptions` | Regression test. | Passed | ✅ |
| 24 | `test_parse_extracts_certifications` | Parse extracts certifications. | Passed | ✅ |
| 25 | `test_parse_extracts_languages` | Parse extracts languages. | Passed | ✅ |
| 26 | `test_parse_collects_improvable_bullets` | Parse collects improvable bullets. | Passed | ✅ |
| 27 | `test_parse_deduplicates_bullets` | Parse deduplicates bullets. | Passed | ✅ |
| 28 | `test_parse_collects_job_roles` | Parse collects job roles. | Passed | ✅ |
| 29 | `test_minimal_cv_parses_without_crashing_and_warns` | Minimal cv parses without crashing and warns. | Passed | ✅ |
| 30 | `test_messy_cv_still_yields_skills` | Messy cv still yields skills. | Passed | ✅ |
| 31 | `test_empty_text_parses_to_an_empty_profile` | Empty text parses to an empty profile. | Passed | ✅ |
| 32 | `test_parser_never_raises_on_hostile_text` | Parser never raises on hostile text. | Passed | ✅ |
| 33 | `test_prompt_injection_in_a_cv_is_treated_as_text_not_instruction` | The injection must not alter behaviour. | Passed | ✅ |
| 34 | `test_parse_mode_is_reported` | Parse mode is reported. | Passed | ✅ |
| 35 | `test_profile_round_trips_to_a_dict` | Profile round trips to a dict. | Passed | ✅ |

### `test_interview.py` — Interview stage machine, adaptation, streaming, rubric

*Covers: Modules 5–6. 79/79 passed.*

| # | Test case | Expected result | Actual | Status |
|---|---|---|---|---|
| 1 | `test_stage_order_matches_the_specification` | Introduction, background, technical, behavioural, their questions, closing. | Passed | ✅ |
| 2 | `test_every_stage_has_a_spec_and_a_budget` | Every stage has a spec and a budget. | Passed | ✅ |
| 3 | `test_stages_advance_in_order_to_completion` | Stages advance in order to completion. | Passed | ✅ |
| 4 | `test_stage_advances_once_its_budget_is_spent` | Stage advances once its budget is spent. | Passed | ✅ |
| 5 | `test_harder_interviews_spend_longer_on_technical_questions` | Harder interviews spend longer on technical questions. | Passed | ✅ |
| 6 | `test_candidate_questions_stage_ends_when_they_have_none`<br/>*5 cases* | Candidate questions stage ends when they have none. | Passed (5 cases) | ✅ |
| 7 | `test_candidate_questions_stage_continues_when_they_do_ask` | Candidate questions stage continues when they do ask. | Passed | ✅ |
| 8 | `test_progress_payload_is_coherent` | Progress payload is coherent. | Passed | ✅ |
| 9 | `test_stage_state_round_trips` | Stage state round trips. | Passed | ✅ |
| 10 | `test_introduction_and_closing_are_not_scored` | Greetings carry no assessable content, so they must not dilute the score. | Passed | ✅ |
| 11 | `test_strong_answer_is_recognised` | Strong answer is recognised. | Passed | ✅ |
| 12 | `test_weak_answer_is_recognised` | Weak answer is recognised. | Passed | ✅ |
| 13 | `test_non_answer_is_recognised` | Non answer is recognised. | Passed | ✅ |
| 14 | `test_team_only_answer_is_flagged` | Team only answer is flagged. | Passed | ✅ |
| 15 | `test_empty_answer_is_handled` | Empty answer is handled. | Passed | ✅ |
| 16 | `test_role_relevant_skills_are_weighted_higher` | Role relevant skills are weighted higher. | Passed | ✅ |
| 17 | `test_salient_terms_give_the_follow_up_something_to_grip` | Salient terms give the follow up something to grip. | Passed | ✅ |
| 18 | `test_difficulty_moves_at_most_one_band`<br/>*8 cases* | Difficulty moves at most one band. | Passed (8 cases) | ✅ |
| 19 | `test_follow_up_on_a_substantive_answer` | Follow up on a substantive answer. | Passed | ✅ |
| 20 | `test_follow_up_on_a_thin_answer_asks_for_specifics` | Follow up on a thin answer asks for specifics. | Passed | ✅ |
| 21 | `test_follow_up_depth_is_bounded` | An interviewer who will not let go is a bad interviewer. | Passed | ✅ |
| 22 | `test_no_follow_up_on_a_non_answer` | No follow up on a non answer. | Passed | ✅ |
| 23 | `test_coverage_note_tells_the_model_what_to_do` | Coverage note tells the model what to do. | Passed | ✅ |
| 24 | `test_sentence_is_emitted_as_soon_as_it_completes` | Sentence is emitted as soon as it completes. | Passed | ✅ |
| 25 | `test_incomplete_buffer_is_held_back` | Incomplete buffer is held back. | Passed | ✅ |
| 26 | `test_abbreviation_does_not_split_a_sentence` | Abbreviation does not split a sentence. | Passed | ✅ |
| 27 | `test_long_run_on_flushes_at_a_comma_so_audio_still_starts` | Long run on flushes at a comma so audio still starts. | Passed | ✅ |
| 28 | `test_short_buffer_is_not_split` | Short buffer is not split. | Passed | ✅ |
| 29 | `test_speaker_labels_are_stripped`<br/>*6 cases* | Speaker labels are stripped. | Passed (6 cases) | ✅ |
| 30 | `test_quotes_around_the_whole_reply_are_stripped` | Quotes around the whole reply are stripped. | Passed | ✅ |
| 31 | `test_markdown_never_reaches_the_speech_engine`<br/>*7 cases* | Markdown never reaches the speech engine. | Passed (7 cases) | ✅ |
| 32 | `test_stage_directions_are_removed` | Stage directions are removed. | Passed | ✅ |
| 33 | `test_clean_for_speech_keeps_the_actual_words` | Clean for speech keeps the actual words. | Passed | ✅ |
| 34 | `test_split_sentences_merges_fragments_and_caps_length` | Split sentences merges fragments and caps length. | Passed | ✅ |
| 35 | `test_split_sentences_on_empty_input` | Split sentences on empty input. | Passed | ✅ |
| 36 | `test_rubric_is_defined_in_advance` | Rubric is defined in advance. | Passed | ✅ |
| 37 | `test_rubric_covers_the_categories_the_specification_asks_for` | Rubric covers the categories the specification asks for. | Passed | ✅ |
| 38 | `test_weights_sum_to_one`<br/>*3 cases* | Weights sum to one. | Passed (3 cases) | ✅ |
| 39 | `test_weights_differ_by_difficulty_in_the_expected_direction` | Weights differ by difficulty in the expected direction. | Passed | ✅ |
| 40 | `test_unknown_difficulty_falls_back_to_medium` | Unknown difficulty falls back to medium. | Passed | ✅ |
| 41 | `test_scale_covers_one_to_five_with_descriptors` | Scale covers one to five with descriptors. | Passed | ✅ |
| 42 | `test_overall_bands_cover_the_whole_range` | Overall bands cover the whole range. | Passed | ✅ |
| 43 | `test_rubric_prompt_text_names_the_exact_keys` | Rubric prompt text names the exact keys. | Passed | ✅ |
| 44 | `test_rubric_disclaimer_denies_being_a_hiring_decision` | Rubric disclaimer denies being a hiring decision. | Passed | ✅ |
| 45 | `test_hiring_verdicts_are_rewritten`<br/>*9 cases* | Hiring verdicts are rewritten. | Passed (9 cases) | ✅ |
| 46 | `test_sanitisation_leaves_legitimate_feedback_alone` | Sanitisation leaves legitimate feedback alone. | Passed | ✅ |
| 47 | `test_sanitisation_handles_empty_input` | Sanitisation handles empty input. | Passed | ✅ |

### `test_matching_and_guards.py` — Fusion, gap matching, invention guards, LLM output defences

*Covers: Modules 2–4. 88/88 passed.*

| # | Test case | Expected result | Actual | Status |
|---|---|---|---|---|
| 1 | `test_exact_match_is_matched` | Exact match is matched. | Passed | ✅ |
| 2 | `test_absent_skill_is_missing` | Absent skill is missing. | Passed | ✅ |
| 3 | `test_variant_spelling_on_the_cv_counts_as_a_match` | The CV says ReactJS; the role wants React. | Passed | ✅ |
| 4 | `test_implied_skill_is_a_partial_match` | Holding React partially evidences JavaScript. | Passed | ✅ |
| 5 | `test_foundation_present_is_a_partial_match` | The CV has JavaScript; the role wants React, which builds on it. | Passed | ✅ |
| 6 | `test_every_comparison_carries_evidence` | Every comparison carries evidence. | Passed | ✅ |
| 7 | `test_score_is_weighted_by_importance` | Missing one core requirement must hurt more than missing a minor one. | Passed | ✅ |
| 8 | `test_severity_escalates_for_missing_essentials` | Severity escalates for missing essentials. | Passed | ✅ |
| 9 | `test_priority_gaps_are_ordered_by_severity_then_importance` | Priority gaps are ordered by severity then importance. | Passed | ✅ |
| 10 | `test_extra_cv_skills_are_reported` | Extra cv skills are reported. | Passed | ✅ |
| 11 | `test_category_breakdown_sums_correctly` | Category breakdown sums correctly. | Passed | ✅ |
| 12 | `test_essential_coverage_is_computed` | Essential coverage is computed. | Passed | ✅ |
| 13 | `test_empty_cv_produces_a_warning_not_a_crash` | Empty cv produces a warning not a crash. | Passed | ✅ |
| 14 | `test_no_requirements_produces_a_warning` | No requirements produces a warning. | Passed | ✅ |
| 15 | `test_result_never_claims_employability` | Result never claims employability. | Passed | ✅ |
| 16 | `test_skills_in_text_finds_canonical_skills` | Skills in text finds canonical skills. | Passed | ✅ |
| 17 | `test_skills_in_text_ignores_short_ambiguous_words` | 'go' as an English word must not register the Go language. | Passed | ✅ |
| 18 | `test_fusion_marks_provenance_correctly` | Fusion marks provenance correctly. | Passed | ✅ |
| 19 | `test_fusion_keeps_a_skill_corroborated_by_two_adverts` | Fusion keeps a skill corroborated by two adverts. | Passed | ✅ |
| 20 | `test_fusion_drops_the_uncorroborated_long_tail` | Regression test. | Passed | ✅ |
| 21 | `test_fusion_caps_the_requirement_list` | Fusion caps the requirement list. | Passed | ✅ |
| 22 | `test_agreement_outranks_a_single_source` | Agreement outranks a single source. | Passed | ✅ |
| 23 | `test_fusion_normalises_variants_across_sources` | Adverts say ReactJS, the LLM says React.js -- one requirement. | Passed | ✅ |
| 24 | `test_essential_flag_requires_evidence` | Essential flag requires evidence. | Passed | ✅ |
| 25 | `test_guard_blocks_an_invented_metric` | Guard blocks an invented metric. | Passed | ✅ |
| 26 | `test_guard_allows_a_metric_that_was_already_there` | Guard allows a metric that was already there. | Passed | ✅ |
| 27 | `test_guard_blocks_an_invented_technology` | Guard blocks an invented technology. | Passed | ✅ |
| 28 | `test_guard_allows_a_technology_present_elsewhere_in_the_cv` | Guard allows a technology present elsewhere in the cv. | Passed | ✅ |
| 29 | `test_guard_blocks_escalated_scope`<br/>*5 cases* | Guard blocks escalated scope. | Passed (5 cases) | ✅ |
| 30 | `test_guard_allows_leadership_language_when_the_original_supports_it` | Guard allows leadership language when the original supports it. | Passed | ✅ |
| 31 | `test_guard_rejects_an_empty_rewrite` | Guard rejects an empty rewrite. | Passed | ✅ |
| 32 | `test_guard_rejects_an_absurdly_long_rewrite` | Guard rejects an absurdly long rewrite. | Passed | ✅ |
| 33 | `test_new_wording_is_a_warning_not_a_rejection` | New wording is a warning not a rejection. | Passed | ✅ |
| 34 | `test_weakness_detection_flags_the_usual_suspects` | Weakness detection flags the usual suspects. | Passed | ✅ |
| 35 | `test_weakness_detection_is_quiet_on_a_strong_bullet` | Weakness detection is quiet on a strong bullet. | Passed | ✅ |
| 36 | `test_bullets_are_ranked_worst_first` | Bullets are ranked worst first. | Passed | ✅ |
| 37 | `test_improve_rejects_an_empty_request` | Improve rejects an empty request. | Passed | ✅ |
| 38 | `test_improve_rejects_too_many_bullets` | Improve rejects too many bullets. | Passed | ✅ |
| 39 | `test_improve_end_to_end_with_the_offline_engine` | Improve end to end with the offline engine. | Passed | ✅ |
| 40 | `test_json_repair_cascade`<br/>*9 cases* | Json repair cascade. | Passed (9 cases) | ✅ |
| 41 | `test_json_guard_handles_raw_newlines_in_strings` | Json guard handles raw newlines in strings. | Passed | ✅ |
| 42 | `test_json_guard_handles_smart_quotes` | Json guard handles smart quotes. | Passed | ✅ |
| 43 | `test_json_guard_handles_nested_braces_in_strings` | Json guard handles nested braces in strings. | Passed | ✅ |
| 44 | `test_json_guard_raises_on_unusable_output`<br/>*5 cases* | Json guard raises on unusable output. | Passed (5 cases) | ✅ |
| 45 | `test_as_str_list_coerces_everything`<br/>*8 cases* | As str list coerces everything. | Passed (8 cases) | ✅ |
| 46 | `test_as_float_clamps_and_defaults` | As float clamps and defaults. | Passed | ✅ |
| 47 | `test_as_choice_falls_back_to_the_default` | As choice falls back to the default. | Passed | ✅ |
| 48 | `test_unsupported_numbers_detects_invention` | Unsupported numbers detects invention. | Passed | ✅ |
| 49 | `test_grounding_filter_splits_supported_from_invented` | Grounding filter splits supported from invented. | Passed | ✅ |
| 50 | `test_grounding_filter_accepts_an_acronym_backed_by_its_expansion` | Grounding filter accepts an acronym backed by its expansion. | Passed | ✅ |
| 51 | `test_certifications_and_degrees_count_as_skills` | Regression test. | Passed | ✅ |
| 52 | `test_a_held_certification_is_not_reported_as_missing` | A held certification is not reported as missing. | Passed | ✅ |
| 53 | `test_candidate_skill_set_does_not_duplicate` | Candidate skill set does not duplicate. | Passed | ✅ |
| 54 | `test_anthropic_request_omits_the_removed_sampling_parameters` | Regression test. | Passed | ✅ |
| 55 | `test_latency_critical_task_requests_low_effort` | The interview turn sits on the measured reply-latency path. | Passed | ✅ |
| 56 | `test_unsupported_output_config_is_dropped_and_retried` | An older model string in .env must not break every request. | Passed | ✅ |
| 57 | `test_unrelated_errors_are_not_swallowed` | Unrelated errors are not swallowed. | Passed | ✅ |
| 58 | `test_groq_reasoning_model_gets_effort_and_token_headroom` | Regression test. | Passed | ✅ |
| 59 | `test_non_reasoning_models_are_left_alone` | Ollama and plain OpenAI models must not receive reasoning_effort. | Passed | ✅ |
| 60 | `test_reasoning_effort_is_dropped_if_rejected` | Reasoning effort is dropped if rejected. | Passed | ✅ |
| 61 | `test_provider_failures_explain_themselves`<br/>*3 cases* | A free-tier user must be told what to do, not shown a raw SDK error. | Passed (3 cases) | ✅ |
| 62 | `test_rate_limit_message_names_a_way_out` | Rate limit message names a way out. | Passed | ✅ |
| 63 | `test_retries_are_configured_for_free_tiers` | Retries are configured for free tiers. | Passed | ✅ |

### `test_skill_normalisation.py` — Skill normalisation and the taxonomy

*Covers: Module 2B / 3. 76/76 passed.*

| # | Test case | Expected result | Actual | Status |
|---|---|---|---|---|
| 1 | `test_every_react_spelling_resolves_to_one_skill`<br/>*14 cases* | Every react spelling resolves to one skill. | Passed (14 cases) | ✅ |
| 2 | `test_react_variants_collapse_to_a_single_entry` | React variants collapse to a single entry. | Passed | ✅ |
| 3 | `test_known_alias_families_collapse`<br/>*12 cases* | Known alias families collapse. | Passed (12 cases) | ✅ |
| 4 | `test_mixed_list_deduplicates_across_families` | Mixed list deduplicates across families. | Passed | ✅ |
| 5 | `test_distinct_skills_are_not_merged`<br/>*8 cases* | Distinct skills are not merged. | Passed (8 cases) | ✅ |
| 6 | `test_generic_words_do_not_match_specific_certifications` | Regression test. | Passed | ✅ |
| 7 | `test_document_scan_minimum_key_length_excludes_ambiguous_acronyms` | One and two character skills must not be matched inside prose. | Passed | ✅ |
| 8 | `test_normalise_key`<br/>*12 cases* | Normalise key. | Passed (12 cases) | ✅ |
| 9 | `test_normalise_key_can_keep_noise_words` | Normalise key can keep noise words. | Passed | ✅ |
| 10 | `test_split_skill_list`<br/>*5 cases* | Split skill list. | Passed (5 cases) | ✅ |
| 11 | `test_split_preserves_terms_containing_a_slash`<br/>*4 cases* | Split preserves terms containing a slash. | Passed (4 cases) | ✅ |
| 12 | `test_surface_form_tidies_without_destroying_casing` | Surface form tidies without destroying casing. | Passed | ✅ |
| 13 | `test_strip_bullet_handles_every_glyph` | Strip bullet handles every glyph. | Passed | ✅ |
| 14 | `test_unknown_skill_is_kept_rather_than_discarded` | Unknown skill is kept rather than discarded. | Passed | ✅ |
| 15 | `test_unknown_near_duplicates_cluster_together` | A brand-new technology must still de-duplicate across sources. | Passed | ✅ |
| 16 | `test_junk_input_is_rejected` | Junk input is rejected. | Passed | ✅ |
| 17 | `test_sentence_is_not_treated_as_a_skill` | Sentence is not treated as a skill. | Passed | ✅ |
| 18 | `test_normalisation_records_which_stage_decided` | Normalisation records which stage decided. | Passed | ✅ |
| 19 | `test_common_typos_still_resolve`<br/>*4 cases* | Common typos still resolve. | Passed (4 cases) | ✅ |
| 20 | `test_an_unrecoverable_typo_is_kept_verbatim_not_misassigned` | The fuzzy and vector stages have a documented limit. | Passed | ✅ |
| 21 | `test_taxonomy_is_internally_consistent` | Taxonomy is internally consistent. | Passed | ✅ |
| 22 | `test_no_alias_maps_to_two_different_skills` | An ambiguous alias would make normalisation order-dependent. | Passed | ✅ |
| 23 | `test_implication_graph_has_no_self_loops` | Implication graph has no self loops. | Passed | ✅ |
| 24 | `test_normalisation_is_deterministic` | Normalisation is deterministic. | Passed | ✅ |

### `test_speech_and_scraping.py` — Local speech engines and scraping compliance

*Covers: Modules 2 / 5. 39/39 passed.*

| # | Test case | Expected result | Actual | Status |
|---|---|---|---|---|
| 1 | `test_wav_decodes_to_16k_mono` | Wav decodes to 16k mono. | Passed | ✅ |
| 2 | `test_stereo_wav_is_downmixed` | Stereo wav is downmixed. | Passed | ✅ |
| 3 | `test_any_sample_rate_is_resampled`<br/>*5 cases* | Any sample rate is resampled. | Passed (5 cases) | ✅ |
| 4 | `test_empty_audio_is_rejected` | Empty audio is rejected. | Passed | ✅ |
| 5 | `test_undecodable_audio_is_rejected_with_a_helpful_message` | Undecodable audio is rejected with a helpful message. | Passed | ✅ |
| 6 | `test_stt_describes_itself_as_local` | Stt describes itself as local. | Passed | ✅ |
| 7 | `test_tiny_recording_returns_no_speech_rather_than_an_error` | Tiny recording returns no speech rather than an error. | Passed | ✅ |
| 8 | `test_confidence_banding`<br/>*5 cases* | Confidence banding. | Passed (5 cases) | ✅ |
| 9 | `test_tts_describes_itself_as_local` | Tts describes itself as local. | Passed | ✅ |
| 10 | `test_wav_helpers` | Wav helpers. | Passed | ✅ |
| 11 | `test_pcm_is_wrapped_into_a_valid_wav` | Pcm is wrapped into a valid wav. | Passed | ✅ |
| 12 | `test_wavs_concatenate` | Wavs concatenate. | Passed | ✅ |
| 13 | `test_mismatched_sample_rates_are_skipped_not_mangled` | Mismatched sample rates are skipped not mangled. | Passed | ✅ |
| 14 | `test_every_source_is_declared_with_attribution` | Every source is declared with attribution. | Passed | ✅ |
| 15 | `test_at_least_one_source_is_genuine_markup_scraping` | The specification asks for scraping, not only JSON APIs. | Passed | ✅ |
| 16 | `test_sources_build_valid_urls` | Sources build valid urls. | Passed | ✅ |
| 17 | `test_user_agent_identifies_the_project_rather_than_a_browser` | User agent identifies the project rather than a browser. | Passed | ✅ |
| 18 | `test_rate_limiting_is_configured` | Rate limiting is configured. | Passed | ✅ |
| 19 | `test_scraping_disabled_is_reported_not_faked` | Scraping disabled is reported not faked. | Passed | ✅ |
| 20 | `test_robots_block_is_reported_as_a_named_failure` | Robots block is reported as a named failure. | Passed | ✅ |
| 21 | `test_failed_fetch_never_claims_success` | Failed fetch never claims success. | Passed | ✅ |
| 22 | `test_empty_200_response_is_treated_as_a_failure` | Regression test. | Passed | ✅ |
| 23 | `test_html_to_text_keeps_list_structure` | Html to text keeps list structure. | Passed | ✅ |
| 24 | `test_html_to_text_handles_junk` | Html to text handles junk. | Passed | ✅ |
| 25 | `test_rss_items_are_parsed` | Rss items are parsed. | Passed | ✅ |
| 26 | `test_rss_parsing_of_junk_returns_nothing` | Rss parsing of junk returns nothing. | Passed | ✅ |
| 27 | `test_wwr_title_is_split_into_company_and_role` | Wwr title is split into company and role. | Passed | ✅ |
| 28 | `test_role_tokens_drop_seniority_noise` | Role tokens drop seniority noise. | Passed | ✅ |
| 29 | `test_title_matches_outrank_body_mentions` | Title matches outrank body mentions. | Passed | ✅ |
| 30 | `test_irrelevant_posting_falls_below_the_threshold` | Irrelevant posting falls below the threshold. | Passed | ✅ |
| 31 | `test_relevance_of_an_empty_query_is_neutral` | Relevance of an empty query is neutral. | Passed | ✅ |

### `test_token_budget.py` — 

*Covers: —. 1/1 passed.*

| # | Test case | Expected result | Actual | Status |
|---|---|---|---|---|
| 1 | `test_interview_turn_prompt_size_is_recorded` | Interview turn prompt size is recorded. | Passed | ✅ |

## Live test suite

Requires the downloaded Whisper and Piper models and live internet access. Run with `pytest -m live`.

### `test_speech_and_scraping.py` — Local speech engines and scraping compliance

*Covers: Modules 2 / 5. 5/5 passed.*

| # | Test case | Expected result | Actual | Status |
|---|---|---|---|---|
| 1 | `test_live_tts_produces_audio` | Live tts produces audio. | Passed | ✅ |
| 2 | `test_live_tts_streams_sentence_by_sentence` | Live tts streams sentence by sentence. | Passed | ✅ |
| 3 | `test_live_round_trip_tts_then_stt` | The honest end-to-end speech test. | Passed | ✅ |
| 4 | `test_live_sources_are_reachable` | Live sources are reachable. | Passed | ✅ |
| 5 | `test_live_collection_returns_postings_with_descriptions` | Live collection returns postings with descriptions. | Passed | ✅ |

---

## What could not be tested automatically, and why

Stated here rather than left as a silent gap.

| Area | Why not automated | How it was verified instead |
|---|---|---|
| **Real microphone capture** | `MediaRecorder` needs a browser and a physical input device; a headless browser has neither | Manual testing in Chrome; the input-level meter makes a muted or wrong device visible to the user |
| **Human speech recognition accuracy** | No labelled human-speech corpus for this domain, and recording one was out of scope | The live round-trip test uses local TTS audio; the limitation is stated in the evaluation |
| **Cloud LLM providers** | No API key is committed, and a paid key cannot be a test dependency | The provider abstraction is covered via the offline and Ollama paths; `probe_llm()` checks a configured provider at runtime from the Settings page |
| **Audio playback in the browser** | Cannot assert that a sound was heard | The audio queue's ordering logic is unit-tested; playback was verified manually |
| **Rubric score correctness** | There is no ground truth — that needs multiple human assessors and an inter-rater agreement figure | The *process* is tested: fixed rubric, whitelisted categories, clamped scores, Python-side arithmetic, hiring language stripped |
| **Job board content** | The boards' contents change hourly; asserting on them would make the suite fail for reasons unrelated to this code | Reachability and parsing are tested live; content assertions are limited to structure |

---

## Reproducing this report

```bash
# 1. install
python -m venv .venv && .venv\Scripts\activate
pip install -r backend/requirements.txt

# 2. generate the synthetic test CVs the suite needs
python scripts/make_sample_cvs.py

# 3. for the live tests only, download the speech models
python scripts/download_speech_models.py --warm-whisper

# 4. regenerate this document
python scripts/make_test_report.py
```

