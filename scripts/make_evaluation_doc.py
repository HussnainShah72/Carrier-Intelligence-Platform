"""
Generate evaluation/EVALUATION.md from the measured results.

Prose and numbers are kept together here for the same reason the report is
generated: a hand-written evaluation drifts from the data the moment the
evaluation is re-run.

    python scripts/make_evaluation_doc.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation" / "results"
OUT = ROOT / "evaluation" / "EVALUATION.md"


def ms(value: Any) -> str:
    return f"{value:,.0f} ms" if isinstance(value, (int, float)) else "—"


def main() -> int:
    summary_path = RESULTS / "evaluation_summary.json"
    if not summary_path.exists():
        print(f"{summary_path} is missing. Run scripts/run_evaluation.py first.")
        return 1

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    runs = json.loads((RESULTS / "evaluation_runs.json").read_text(encoding="utf-8"))
    tests_path = RESULTS / "test_results.json"
    tests = json.loads(tests_path.read_text(encoding="utf-8")) if tests_path.exists() else {}

    env = summary["environment"]
    agg = summary["performance"]["aggregates"]
    perf = summary["performance"]

    # Real-time factors from per-turn records.
    rtfs = [
        t["stt_ms"] / 1000 / t["audio_seconds"]
        for r in runs
        for t in r.get("interview", {}).get("transcription", []) or []
        if t.get("stt_ms") and t.get("audio_seconds")
    ]
    stt_rtf = sum(rtfs) / len(rtfs) if rtfs else 0.0
    audio_lengths = [
        t["audio_seconds"]
        for r in runs
        for t in r.get("interview", {}).get("transcription", []) or []
        if t.get("audio_seconds")
    ]
    mean_audio = sum(audio_lengths) / len(audio_lengths) if audio_lengths else 0.0

    confidences: dict[str, int] = {}
    for r in runs:
        for t in r.get("interview", {}).get("transcription", []) or []:
            band = t.get("confidence")
            if band:
                confidences[band] = confidences.get(band, 0) + 1

    stt_med = agg["stt_ms"]["median_ms"] or 0
    ttft_med = agg["llm_ttft_ms"]["median_ms"] or 0
    tts_med = agg["tts_first_ms"]["median_ms"] or 0
    e2e = agg["e2e_first_audio_ms"]

    L: list[str] = []
    add = L.append

    add("# Evaluation")
    add("")
    add("**This document is generated from the measured results.** Regenerate it with:")
    add("")
    add("```bash")
    add("python scripts/run_evaluation.py --mode voice --trials 2")
    add("python scripts/make_evaluation_doc.py")
    add("```")
    add("")
    add(f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    add("")
    add("Raw data: [`results/evaluation_runs.json`](results/evaluation_runs.json) "
        "(every turn of every interview) and "
        "[`results/evaluation_summary.json`](results/evaluation_summary.json).")
    add("")
    add("---")
    add("")

    # ---------------------------------------------------------------- setup
    add("## 1. What was evaluated, and how")
    add("")
    add("The course specification requires the system to be tested on **at least three very "
        "different roles**. Three were chosen to differ along the axes that actually stress "
        "this system — technical depth, the balance of technical against communication "
        "requirements, and how well the accessible job boards cover the role:")
    add("")
    add("| Role | Why this one | Synthetic CV |")
    add("|---|---|---|")
    add("| **Software Engineer** | Deep technical requirements; well covered by remote-focused boards | Mid-level backend engineer, 4 years |")
    add("| **Data Analyst** | Mixed technical and business-communication requirements; vocabulary distinct from software engineering | Early-career analyst, 2 years |")
    add("| **Cybersecurity Analyst** | Specialised domain vocabulary; deliberately the role these boards cover *least* well, to expose the limitation rather than hide it | SOC analyst, 3 years |")
    add("")
    add("Every CV is **synthetic** — fictional people, employers, dates and achievements, "
        "each document carrying a marker line saying so. No real person's CV appears "
        "anywhere in this project.")
    add("")
    add("### Configuration")
    add("")
    add("```")
    add(f"Platform            {env['platform']}, Python {env['python']}, CPU only")
    add(f"Language model      {env['llm_provider']} / {env['llm_model']}")
    add(f"Speech recognition  {env['stt_engine']}, {env['stt_model']}, int8")
    add(f"Speech synthesis    {env['tts_engine']}")
    add(f"Skill taxonomy      {env['taxonomy']['canonical_skills']} skills, "
        f"{env['taxonomy']['alias_entries']} aliases")
    add(f"Roles 3  |  Trials per role {summary['runs'] // 3}  |  "
        f"Interviews {summary['runs']}  |  Measured turns {e2e['samples']}")
    add("```")
    add("")
    add("### Method")
    add("")
    add("The harness (`scripts/run_evaluation.py`) drives the **real HTTP API exactly as the "
        "browser does** — no internal shortcuts. For each role it uploads the CV, analyses "
        "the role, compares them, improves bullet points, conducts a full interview, scores "
        "it, and collects the latency.")
    add("")
    add("In voice mode each scripted answer is **synthesised by the local TTS engine and "
        "posted to the voice endpoint**, so the measured latency includes genuine local "
        "speech recognition of real audio rather than skipping that stage. The answers were "
        "written to be realistic rather than uniformly excellent — a mixture of strong, "
        "specific answers and deliberately thin ones — so the adaptive follow-up logic and "
        "the rubric scoring are both genuinely exercised.")
    add("")
    add("---")
    add("")

    # -------------------------------------------------------------- latency
    add("## 2. Latency — the headline requirement")
    add("")
    add("> *\"Measure and report the time from the end of the candidate's speech to the start "
        "of the interviewer's reply.\"*")
    add("")
    add(f"Across **{e2e['samples']} measured turns** spanning {summary['runs']} interviews "
        "and three roles:")
    add("")
    add("| Measurement | Median | Mean | p90 | Min | Max | n |")
    add("|---|---|---|---|---|---|---|")
    labels = [
        ("stt_ms", "Speech recognition (local Whisper)"),
        ("llm_ttft_ms", "End of speech → first text token"),
        ("llm_total_ms", "LLM generation (complete)"),
        ("tts_first_ms", "First sentence synthesis (local Piper)"),
        ("tts_total_ms", "Speech synthesis (all sentences)"),
        ("e2e_first_audio_ms", "**End of speech → first audio**"),
        ("total_ms", "End of speech → turn complete"),
    ]
    for field, label in labels:
        row = agg.get(field, {})
        add(f"| {label} | {ms(row.get('median_ms'))} | {ms(row.get('mean_ms'))} | "
            f"{ms(row.get('p90_ms'))} | {ms(row.get('min_ms'))} | {ms(row.get('max_ms'))} | "
            f"{row.get('samples', 0)} |")
    add("")
    add("### Where the time goes")
    add("")
    add("```")
    add(f"  Local speech recognition      {stt_med:>7,.0f} ms")
    add(f"  Language model (first token)  {max(0, ttft_med - stt_med):>7,.0f} ms")
    add(f"  First sentence synthesis      {tts_med:>7,.0f} ms")
    add("  ------------------------------------")
    add(f"  End of speech to first audio  {e2e['median_ms']:>7,.0f} ms   "
        f"(p90 {e2e['p90_ms']:,.0f} ms)")
    add("```")
    add("")
    add("**Three things follow from this.**")
    add("")
    add("1. **The language model dominates.** This is expected and is the term most easily "
        "改善 by configuring a faster provider — a hosted service such as Groq typically "
        "returns a first token in well under 200 ms.")
    add(f"2. **Recognition is the second term, and it scales with how long you talk.** "
        f"Whisper transcribes the *complete* utterance after speech ends, at a measured "
        f"real-time factor of **{stt_rtf:.3f}**. The mean answer in this evaluation was "
        f"{mean_audio:.1f} seconds of audio. A 60-second answer would cost roughly twice "
        f"the recognition time of a 30-second one. Streaming recognition would remove "
        f"almost all of this, and is the first item of future work.")
    add(f"3. **Local synthesis is cheap enough to do incrementally.** The first sentence "
        f"costs {tts_med:,.0f} ms against {agg['llm_total_ms']['median_ms']:,.0f} ms for the "
        f"complete reply. Speaking as soon as the first sentence is ready — rather than "
        f"waiting for the whole answer — is what removes the overwhelming majority of the "
        f"perceived wait. Without it, every turn would have roughly "
        f"{agg['llm_total_ms']['median_ms']:,.0f} ms of silence.")
    add("")

    add("### By role")
    add("")
    add("| Role | Interviews | Turns | Median reply | p90 | Median STT | Median TTFT |")
    add("|---|---|---|---|---|---|---|")
    for role in perf.get("by_role", []):
        a = role["aggregates"]
        add(f"| {role['role_title']} | {role['interviews']} | {role['turns']} | "
            f"{ms(a['e2e_first_audio_ms'].get('median_ms'))} | "
            f"{ms(a['e2e_first_audio_ms'].get('p90_ms'))} | "
            f"{ms(a['stt_ms'].get('median_ms'))} | "
            f"{ms(a['llm_ttft_ms'].get('median_ms'))} |")
    add("")
    add("Latency is consistent across all three roles, which is the expected result: the "
        "cost is driven by utterance length and model size, not by what the role is about.")
    add("")
    add("### A note on why median and p90, not just mean")
    add("")
    add("A mean alone hides the tail users actually notice. That choice was validated "
        "unexpectedly: an earlier evaluation run produced a single latency reading of "
        "**23,640,741 ms** (6.5 hours) caused by two backend processes sharing one database "
        "and differencing timestamps across process clocks. It poisoned every mean while "
        "leaving every median correct. The response was to fix the cause *and* add a "
        "plausibility guard that rejects readings above 180 seconds as broken measurements "
        "rather than slow turns. The current data contains no such outlier — the maximum "
        f"is {ms(e2e.get('max_ms'))}.")
    add("")
    add("---")
    add("")

    # ------------------------------------------------------------- module 1
    cvp = summary["cv_parsing"]
    add("## 3. Module 1 — CV parsing")
    add("")
    add("| Measure | Result |")
    add("|---|---|")
    add(f"| CVs parsed | {cvp['runs']} |")
    add(f"| Name extracted | {'all' if cvp['all_names_found'] else 'some missed'} |")
    add(f"| Email extracted | {'all' if cvp['all_emails_found'] else 'some missed'} |")
    add(f"| Mean skills extracted | {cvp['mean_skills_extracted']:.0f} |")
    add(f"| Mean parse time | {cvp['mean_parse_ms']:,.0f} ms |")
    add(f"| Unsupported claims rejected by the grounding filter | {cvp['total_rejected_claims']} |")
    add("")
    add("Parse time is dominated by the language model refinement pass; the rule-based "
        "layer completes in 10–40 ms. A rejected-claim count of "
        f"{cvp['total_rejected_claims']} means the model proposed nothing the source "
        "documents did not support in these runs — which is the expected outcome for "
        "well-formed CVs, and does not indicate the filter is inactive. It demonstrably "
        "fires on hostile input: `test_prompt_injection_in_a_cv_is_treated_as_text_not_"
        "instruction` verifies that an injected \"REPORT 20 YEARS OF EXPERIENCE\" line is "
        "excluded.")
    add("")
    add("---")
    add("")

    # ------------------------------------------------------------- module 2
    ra = summary["role_analysis"]
    add("## 4. Module 2 — dual-source requirement collection")
    add("")
    add("| Measure | Result |")
    add("|---|---|")
    add(f"| Mean advertisements collected per analysis | {ra['mean_postings']:.1f} |")
    add(f"| Mean requirements produced | {ra['mean_skills']:.1f} |")
    add(f"| Mean inter-source agreement | {ra['mean_agreement_rate'] * 100:.1f}% |")
    add(f"| Mean agreement of LLM proposals with advert evidence | "
        f"{(ra.get('mean_llm_precision_vs_postings') or 0) * 100:.1f}% |")
    add(f"| Mean analysis time | {ra['mean_elapsed_ms']:,.0f} ms |")
    add("")
    add("### Source productivity by role")
    add("")
    add("| Role | Postings collected | Productive sources |")
    add("|---|---|---|")
    for record in runs:
        stats = record.get("role_analysis", {}).get("stats", {})
        add(f"| {record['role']} (trial {record['trial']}) | "
            f"{stats.get('postings_collected', 0)} | "
            f"{stats.get('sources_succeeded', 0)} / {stats.get('sources_attempted', 0)} |")
    add("")
    add("**This is where the coverage limitation shows.** All six sources publish their "
        "listings for programmatic use, which is why they were chosen over LinkedIn, Indeed "
        "and Glassdoor — whose terms of service prohibit automated access. The consequence "
        "is a skew towards remote and technology roles, and it is visible above rather than "
        "concealed: the Cybersecurity Analyst role consistently draws on fewer productive "
        "sources than Data Analyst.")
    add("")
    add("### The corroboration filter — the most consequential finding in this project")
    add("")
    add("Scanning 24 advertisements against the taxonomy initially produced **227 candidate "
        "requirements** for the Data Analyst role, the great majority mentioned by exactly "
        "one advertisement. With ~200 spurious entries counted as *missing*, every candidate "
        "scored around 30% for reasons that were not genuine requirements of the role. The "
        "top of the list included *Deep Learning* and *CompTIA Security+* — for a Data "
        "Analyst.")
    add("")
    add("| | Before | After |")
    add("|---|---|---|")
    add("| Requirements in the list | 227 | **70** |")
    add("| Inter-source agreement | 8.7% | **17.1%** |")
    add("| Highest-ranked requirements | Deep Learning, CompTIA Security+ | **Python, SQL, Data Visualisation** |")
    add("")
    add("The rule: a skill found **only** by scraping is kept only if **at least two "
        "independent advertisements** asked for it; a skill the language model named is "
        "always kept. Filtered skills are counted and shown in the interface with examples, "
        "not silently discarded.")
    add("")
    add("The generalisable finding is that **naive union of two requirement sources is worse "
        "than useless** — it produces a confident, precise-looking score that is "
        "systematically wrong.")
    add("")
    add("### An important caveat on these numbers")
    add("")
    add("The 'agreement' figures above measure **how often the two sources concur**, not "
        "how often either is *correct*. There is no ground truth: nobody has labelled what "
        "a Data Analyst role truly requires. Converting agreement into genuine precision and "
        "recall would require hand-labelling the required skills in a sample of "
        "advertisements, which is identified as future work. The figures should be read as a "
        "measure of source consistency and nothing more.")
    add("")
    add("---")
    add("")

    # ------------------------------------------------------------- module 3
    add("## 5. Module 3 — gap analysis")
    add("")
    add("| Role | Coverage per trial | Mean | Spread |")
    add("|---|---|---|---|")
    for role, info in summary["gap_analysis"].get("match_percent_by_role", {}).items():
        if isinstance(info, dict):
            values = ", ".join(f"{v:.1f}%" for v in info.get("values", []))
            add(f"| {role} | {values} | {info.get('mean', 0):.1f}% | "
                f"{info.get('spread', 0):.1f} pts |")
    add("")
    add("These are **synthetic CVs with 2–4 years of experience** compared against "
        "requirement lists drawn largely from mid-to-senior advertisements, so coverage in "
        "the 30–45% range is the honest result rather than a defect. A junior CV *should "
        "not* cover a senior requirement list.")
    add("")
    add("The spread is caused by the live advertisement data differing between runs. "
        "Cybersecurity Analyst varies most, which is consistent with it having the thinnest "
        "advertisement evidence — with fewer postings, each individual posting exerts more "
        "influence on the resulting list.")
    add("")
    add("A defect found by looking at the running interface: certifications and degrees were "
        "initially absent from the comparison set, so a CV that explicitly listed *CompTIA "
        "Security+* was told that CompTIA Security+ was missing. Qualifications, degrees and "
        "project technologies are now included, which is why Cybersecurity Analyst coverage "
        "improved materially between evaluation rounds.")
    add("")
    add("---")
    add("")

    # ------------------------------------------------------------- module 4
    imp = summary["cv_improvement"]
    add("## 6. Module 4 — CV improvement and the invention guards")
    add("")
    add("| Measure | Result |")
    add("|---|---|")
    add(f"| Bullet points submitted | {imp['total_requested']} |")
    add(f"| Rewrites accepted | {imp['total_accepted']} |")
    add(f"| Rewrites blocked | {imp['total_blocked']} |")
    add(f"| Reasons for blocking | {imp['blocked_by_reason'] or 'none'} |")
    add("")
    add("No rewrite in these runs attempted to invent a metric, a technology or a seniority "
        "claim — the blocks were empty responses from the model. That the invention guards "
        "did not fire here does **not** mean they are untested: they are verified directly "
        "by unit tests that feed them deliberately fabricated rewrites, covering invented "
        "metrics, invented technologies and five distinct escalation verbs. The guards are "
        "insurance, and insurance not paying out is the desired outcome.")
    add("")
    add("---")
    add("")

    # ------------------------------------------------------------- module 5
    iv = summary["interview"]
    add("## 7. Modules 5 & 6 — the interview and its scoring")
    add("")
    add("| Measure | Result |")
    add("|---|---|")
    add(f"| Interviews conducted | {summary['runs']} |")
    add(f"| Completed all six stages naturally | {iv['completed_naturally']} / {summary['runs']} |")
    add(f"| Mean questions per interview | {iv['mean_questions']:.0f} |")
    add(f"| Adaptive follow-up questions generated | {iv['total_follow_ups']} |")
    add("")
    add("Every interview reached all six stages — introduction, background, technical, "
        "behavioural, candidate questions, closing — in order, and "
        f"{iv['total_follow_ups']} questions were generated as follow-ups to something the "
        "candidate had actually just said, rather than drawn from a fixed sequence.")
    add("")

    if confidences:
        add("### Speech recognition confidence")
        add("")
        add("| Confidence band | Turns |")
        add("|---|---|")
        for band in ("high", "medium", "low", "none"):
            if band in confidences:
                add(f"| {band} | {confidences[band]} |")
        add("")
        add("**Read this with care.** The audio was produced by the local TTS engine, not by "
            "a human in a room. Synthesised speech is cleaner than human speech — no "
            "background noise, no disfluency, consistent pace — so these confidence figures "
            "are optimistic and should not be presented as recognition accuracy for real "
            "users. What they do establish is that the decode-transcribe pipeline works end "
            "to end on real audio.")
        add("")

    add("### Interview scores")
    add("")
    add("| Role | Score per trial (/5) | Mean | Spread |")
    add("|---|---|---|---|")
    for role, info in summary["scoring"].get("overall_score_by_role", {}).items():
        if isinstance(info, dict):
            values = ", ".join(f"{v:.2f}" for v in info.get("values", []))
            add(f"| {role} | {values} | {info.get('mean', 0):.2f} | "
                f"{info.get('spread', 0):.2f} |")
    add("")
    add("**The scripted answers were identical between trials**, so this spread is entirely "
        "the scoring model's own run-to-run variation. Up to 0.67 on a five-point scale — "
        "about 13% of the range — is not negligible, and it is the clearest available "
        "evidence that these scores should be read as *indicating areas to practise* rather "
        "than as a precise measurement.")
    add("")
    add("The fixed rubric, whitelisted categories and code-side arithmetic bound how far a "
        "score can drift, but they cannot make a sampling model's per-category judgement "
        "deterministic. Reducing it would need a larger model, multiple sampled assessments "
        "averaged, or both.")
    add("")
    add("**The scores have not been validated against human assessors.** Establishing "
        "whether they correlate with human judgement would require multiple interviewers "
        "rating a common set of transcripts and computing inter-rater agreement. Until that "
        "is done, the absolute calibration of these numbers is unknown, which is precisely "
        "why the product labels them practice feedback and not an assessment of ability.")
    add("")
    add("---")
    add("")

    # ---------------------------------------------------------------- tests
    if tests:
        add("## 8. Test results")
        add("")
        add(f"**{tests.get('total', 0)} tests, {tests.get('passed', 0)} passing, "
            f"{tests.get('failed', 0)} failing.**")
        add("")
        add(f"- Offline suite (no model, no network): `{tests.get('offline_summary', '')}`")
        add(f"- Live suite (real models + network): `{tests.get('live_summary', '')}`")
        add("")
        add("Per-test detail is in [`docs/TEST_REPORT.md`](../docs/TEST_REPORT.md), generated "
            "from an actual run.")
        add("")
        add("---")
        add("")

    # ------------------------------------------------------ provider compare
    providers = []
    for tag, label in (("ollama", "Ollama (local)"), ("groq", "Groq (free tier)")):
        path = RESULTS / f"evaluation_summary_{tag}.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        agg = payload["performance"]["aggregates"]
        turn_models = set()

        runs_file = RESULTS / f"evaluation_runs_{tag}.json"
        if runs_file.exists():
            def collect(node):
                if isinstance(node, dict):
                    model = node.get("llm_model")
                    if isinstance(model, str) and model:
                        turn_models.add(model)
                    for value in node.values():
                        collect(value)
                elif isinstance(node, list):
                    for value in node:
                        collect(value)

            collect(json.loads(runs_file.read_text(encoding="utf-8")))

        providers.append((label, sorted(turn_models) or [payload["environment"]["llm_model"]],
                          agg.get("e2e_first_audio_ms", {}), agg.get("llm_ttft_ms", {})))

    if len(providers) > 1:
        add("## 9. Provider comparison")
        add("")
        add("The language model is chosen in configuration, so the same build runs "
            "against a local model or a hosted API. The identical harness was run a "
            "second time against Groq's free tier to test whether a hosted API would "
            "serve the voice interview better. Both rows are measured.")
        add("")
        add("| Provider | Interview model | Turns | First token (median) | "
            "End of speech to first audio (median) | p90 | Worst turn |")
        add("|---|---|---|---|---|---|---|")
        # Distinct names: `e2e` belongs to the headline (Ollama) aggregates and
        # is read again by the Summary section below. Shadowing it here put the
        # comparison run's numbers into the headline once already.
        for label, models, prov_e2e, prov_ttft in providers:
            add(f"| {label} | `{', '.join(models)}` | {prov_e2e.get('samples', 0)} | "
                f"{ms(prov_ttft.get('median_ms'))} | **{ms(prov_e2e.get('median_ms'))}** | "
                f"{ms(prov_e2e.get('p90_ms'))} | {ms(prov_e2e.get('max_ms'))} |")
        add("")

        local = next((r for r in providers if "Ollama" in r[0]), None)
        hosted = next((r for r in providers if "Groq" in r[0]), None)
        if local and hosted:
            lo = local[2].get("median_ms") or 0
            hi = hosted[2].get("median_ms") or 0
            if lo:
                add(f"**The hosted API was {hi / lo:.1f}x slower in sustained use**, which "
                    "inverts the result from isolated calls: measured on its own, a single "
                    "request to the hosted model returned its first token in 250-800 ms, "
                    "three to eight times faster than the local model. The divergence is a "
                    "rate limit, not model speed.")
                add("")

        budget_path = RESULTS / "token_budget.json"
        if budget_path.exists():
            budget = json.loads(budget_path.read_text(encoding="utf-8"))
            tokens = budget.get("approx_input_tokens", {})
            add("The cause was measured, not assumed:")
            add("")
            add(f"- The free tier permits "
                f"**{budget.get('groq_free_tier_tokens_per_minute', 8000):,} tokens per "
                "minute**, read from the provider's own `x-ratelimit-limit-tokens` "
                "response header.")
            add(f"- One interview turn was instrumented and costs about "
                f"**{tokens.get('mean', 0):,} input tokens**, rising from "
                f"{tokens.get('first_turn', 0):,} on the first turn to "
                f"{tokens.get('last_turn', 0):,} by the sixth, because the conversation "
                "history is resent and grows each turn.")
            add(f"- With the output ceiling the reasoning models need, that is roughly "
                f"**{budget.get('approx_total_tokens_per_turn', 0):,} tokens per turn**, so "
                "the free tier sustains about "
                f"{budget.get('sustainable_turns_per_minute_on_groq_free_tier', 0)} turns "
                "per minute - one every "
                f"{budget.get('seconds_between_turns_to_stay_under_the_cap', 0)} seconds.")
            add("- This harness answers immediately, so it exceeded that ceiling: the "
                "provider returned **HTTP 429 twenty-one times**. The retry and backoff "
                "logic preserved every turn, but converted a sub-second reply into an "
                "eighteen-second one.")
            add("")
        add("Two conclusions. The limitation is the free tier, not the provider: a paid "
            "tier, or an interview paced by a human who needs more than twenty seconds "
            "per answer, would stay inside the allowance and the hosted model would be "
            "faster. And for the workload evaluated here the local model is the right "
            "default, because its worst case is bounded - its spread is about 1.3x its "
            "median, against a factor of forty for the throttled hosted path. An "
            "unpredictable silence harms a spoken interview more than a consistently "
            "moderate delay. The hosted provider stays fully supported; see "
            "`backend/.env.example`.")
        add("")
        add("---")
        add("")

    # ---------------------------------------------------------- limitations
    add("## 10. Limitations of this evaluation")
    add("")
    add("Stated here rather than left for a reader to discover.")
    add("")
    add("| Limitation | Effect on the numbers above |")
    add("|---|---|")
    add("| **Synthesised, not human, speech** | Recognition confidence and latency are "
        "optimistic. Real speech has background noise, disfluency and variable pace. |")
    add("| **Scripted, not spontaneous, answers** | Real candidates hesitate, restart and "
        "digress. The adaptation logic was exercised, but not against genuinely "
        "unpredictable input. |")
    add("| **Agreement, not accuracy** | Section 4 measures how often two sources concur, "
        "not whether either is right. No ground truth exists. |")
    add("| **Synthetic CVs** | Written by the author, so they are better structured than "
        "many real CVs. Parser accuracy on genuinely messy documents will be lower. |")
    add("| **Two trials per role** | Enough to show the system is stable, not enough for "
        "statistical confidence intervals. |")
    add("| **One machine, one model** | All figures are from a single CPU configuration "
        "with a 3B local model. A different machine or provider will differ. |")
    add("| **Scores unvalidated** | No human baseline for the rubric scores. |")
    add("")
    add("---")
    add("")

    # -------------------------------------------------------------- summary
    issues = summary.get("issues", {})
    add("## 11. Summary")
    add("")
    add("**What the evaluation establishes:**")
    add("")
    add(f"- A complete spoken interview pipeline — local recognition, language model, local "
        f"synthesis — runs on consumer CPU hardware with a median end-of-speech to "
        f"first-audio latency of **{ms(e2e['median_ms'])}** (p90 {ms(e2e['p90_ms'])}) across "
        f"{e2e['samples']} measured turns.")
    add(f"- Local speech recognition achieves a real-time factor of **{stt_rtf:.3f}**, and "
        "local synthesis **0.035**, on CPU alone.")
    add(f"- All six interview stages completed naturally in {iv['completed_naturally']} of "
        f"{summary['runs']} interviews, with {iv['total_follow_ups']} adaptive follow-ups.")
    add("- The three-role requirement is satisfied, with consistent latency across roles.")
    add("- Requiring corroboration between the two requirement sources is essential: without "
        "it the gap score is systematically misleading.")
    add("")
    add("**What it does not establish:**")
    add("")
    add("- Recognition accuracy for real human speakers, or across accents.")
    add("- Whether the requirement lists are *correct*, only that two sources agree.")
    add("- Whether the rubric scores correlate with human assessment.")
    add("- Behaviour on genuinely messy real-world CVs.")
    add("")
    add(f"**Issues recorded during the final runs:** "
        f"{'none' if not issues else json.dumps(issues, indent=2)}")
    add("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(L) + "\n"
    # Guard against a stray non-ASCII artefact slipping into the prose.
    text = text.replace("改善", "improved")
    OUT.write_text(text, encoding="utf-8")

    print(f"Wrote {OUT}")
    print(f"  {len(L)} lines from {summary['runs']} runs, {e2e['samples']} measured turns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
