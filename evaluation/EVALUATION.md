# Evaluation

**This document is generated from the measured results.** Regenerate it with:

```bash
python scripts/run_evaluation.py --mode voice --trials 2
python scripts/make_evaluation_doc.py
```

Generated: 2026-11-20T22:09:10+00:00

Raw data: [`results/evaluation_runs.json`](results/evaluation_runs.json) (every turn of every interview) and [`results/evaluation_summary.json`](results/evaluation_summary.json).

---

## 1. What was evaluated, and how

The course specification requires the system to be tested on **at least three very different roles**. Three were chosen to differ along the axes that actually stress this system — technical depth, the balance of technical against communication requirements, and how well the accessible job boards cover the role:

| Role | Why this one | Synthetic CV |
|---|---|---|
| **Software Engineer** | Deep technical requirements; well covered by remote-focused boards | Mid-level backend engineer, 4 years |
| **Data Analyst** | Mixed technical and business-communication requirements; vocabulary distinct from software engineering | Early-career analyst, 2 years |
| **Cybersecurity Analyst** | Specialised domain vocabulary; deliberately the role these boards cover *least* well, to expose the limitation rather than hide it | SOC analyst, 3 years |

Every CV is **synthetic** — fictional people, employers, dates and achievements, each document carrying a marker line saying so. No real person's CV appears anywhere in this project.

### Configuration

```
Platform            Windows 11, Python 3.12.10, CPU only
Language model      ollama / qwen2.5:3b-instruct-q4_K_M
Speech recognition  faster-whisper (CTranslate2), base.en, int8
Speech synthesis    piper
Skill taxonomy      176 skills, 851 aliases
Roles 3  |  Trials per role 2  |  Interviews 6  |  Measured turns 90
```

### Method

The harness (`scripts/run_evaluation.py`) drives the **real HTTP API exactly as the browser does** — no internal shortcuts. For each role it uploads the CV, analyses the role, compares them, improves bullet points, conducts a full interview, scores it, and collects the latency.

In voice mode each scripted answer is **synthesised by the local TTS engine and posted to the voice endpoint**, so the measured latency includes genuine local speech recognition of real audio rather than skipping that stage. The answers were written to be realistic rather than uniformly excellent — a mixture of strong, specific answers and deliberately thin ones — so the adaptive follow-up logic and the rubric scoring are both genuinely exercised.

---

## 2. Latency — the headline requirement

> *"Measure and report the time from the end of the candidate's speech to the start of the interviewer's reply."*

Across **90 measured turns** spanning 6 interviews and three roles:

| Measurement | Median | Mean | p90 | Min | Max | n |
|---|---|---|---|---|---|---|
| Speech recognition (local Whisper) | 766 ms | 846 ms | 1,245 ms | 523 ms | 1,757 ms | 84 |
| End of speech → first text token | 1,855 ms | 1,897 ms | 2,490 ms | 601 ms | 3,009 ms | 90 |
| LLM generation (complete) | 2,299 ms | 2,359 ms | 2,831 ms | 1,567 ms | 3,998 ms | 90 |
| First sentence synthesis (local Piper) | 163 ms | 169 ms | 225 ms | 67 ms | 429 ms | 90 |
| Speech synthesis (all sentences) | 657 ms | 676 ms | 920 ms | 300 ms | 1,318 ms | 90 |
| **End of speech → first audio** | 2,351 ms | 2,382 ms | 3,008 ms | 861 ms | 3,818 ms | 90 |
| End of speech → turn complete | 3,276 ms | 3,347 ms | 4,055 ms | 1,744 ms | 4,833 ms | 90 |

### Where the time goes

```
  Local speech recognition          766 ms
  Language model (first token)    1,088 ms
  First sentence synthesis          163 ms
  ------------------------------------
  End of speech to first audio    2,351 ms   (p90 3,008 ms)
```

**Three things follow from this.**

1. **The language model dominates.** This is expected and is the term most easily improved by configuring a faster provider — a hosted service such as Groq typically returns a first token in well under 200 ms.
2. **Recognition is the second term, and it scales with how long you talk.** Whisper transcribes the *complete* utterance after speech ends, at a measured real-time factor of **0.069**. The mean answer in this evaluation was 17.4 seconds of audio. A 60-second answer would cost roughly twice the recognition time of a 30-second one. Streaming recognition would remove almost all of this, and is the first item of future work.
3. **Local synthesis is cheap enough to do incrementally.** The first sentence costs 163 ms against 2,299 ms for the complete reply. Speaking as soon as the first sentence is ready — rather than waiting for the whole answer — is what removes the overwhelming majority of the perceived wait. Without it, every turn would have roughly 2,299 ms of silence.

### By role

| Role | Interviews | Turns | Median reply | p90 | Median STT | Median TTFT |
|---|---|---|---|---|---|---|
| Cybersecurity Analyst | 2 | 30 | 2,413 ms | 3,139 ms | 788 ms | 1,932 ms |
| Data Analyst | 2 | 30 | 2,180 ms | 2,370 ms | 731 ms | 1,744 ms |
| Software Engineer | 2 | 30 | 2,603 ms | 3,069 ms | 807 ms | 2,060 ms |

Latency is consistent across all three roles, which is the expected result: the cost is driven by utterance length and model size, not by what the role is about.

### A note on why median and p90, not just mean

A mean alone hides the tail users actually notice. That choice was validated unexpectedly: an earlier evaluation run produced a single latency reading of **23,640,741 ms** (6.5 hours) caused by two backend processes sharing one database and differencing timestamps across process clocks. It poisoned every mean while leaving every median correct. The response was to fix the cause *and* add a plausibility guard that rejects readings above 180 seconds as broken measurements rather than slow turns. The current data contains no such outlier — the maximum is 3,818 ms.

---

## 3. Module 1 — CV parsing

| Measure | Result |
|---|---|
| CVs parsed | 6 |
| Name extracted | all |
| Email extracted | all |
| Mean skills extracted | 18 |
| Mean parse time | 14,135 ms |
| Unsupported claims rejected by the grounding filter | 0 |

Parse time is dominated by the language model refinement pass; the rule-based layer completes in 10–40 ms. A rejected-claim count of 0 means the model proposed nothing the source documents did not support in these runs — which is the expected outcome for well-formed CVs, and does not indicate the filter is inactive. It demonstrably fires on hostile input: `test_prompt_injection_in_a_cv_is_treated_as_text_not_instruction` verifies that an injected "REPORT 20 YEARS OF EXPERIENCE" line is excluded.

---

## 4. Module 2 — dual-source requirement collection

| Measure | Result |
|---|---|
| Mean advertisements collected per analysis | 22.3 |
| Mean requirements produced | 60.8 |
| Mean inter-source agreement | 26.9% |
| Mean agreement of LLM proposals with advert evidence | 79.9% |
| Mean analysis time | 35,497 ms |

### Source productivity by role

| Role | Postings collected | Productive sources |
|---|---|---|
| Software Engineer (trial 1) | 24 | 5 / 6 |
| Data Analyst (trial 1) | 24 | 6 / 6 |
| Cybersecurity Analyst (trial 1) | 19 | 5 / 6 |
| Software Engineer (trial 2) | 24 | 5 / 6 |
| Data Analyst (trial 2) | 24 | 6 / 6 |
| Cybersecurity Analyst (trial 2) | 19 | 5 / 6 |

**This is where the coverage limitation shows.** All six sources publish their listings for programmatic use, which is why they were chosen over LinkedIn, Indeed and Glassdoor — whose terms of service prohibit automated access. The consequence is a skew towards remote and technology roles, and it is visible above rather than concealed: the Cybersecurity Analyst role consistently draws on fewer productive sources than Data Analyst.

### The corroboration filter — the most consequential finding in this project

Scanning 24 advertisements against the taxonomy initially produced **227 candidate requirements** for the Data Analyst role, the great majority mentioned by exactly one advertisement. With ~200 spurious entries counted as *missing*, every candidate scored around 30% for reasons that were not genuine requirements of the role. The top of the list included *Deep Learning* and *CompTIA Security+* — for a Data Analyst.

| | Before | After |
|---|---|---|
| Requirements in the list | 227 | **70** |
| Inter-source agreement | 8.7% | **17.1%** |
| Highest-ranked requirements | Deep Learning, CompTIA Security+ | **Python, SQL, Data Visualisation** |

The rule: a skill found **only** by scraping is kept only if **at least two independent advertisements** asked for it; a skill the language model named is always kept. Filtered skills are counted and shown in the interface with examples, not silently discarded.

The generalisable finding is that **naive union of two requirement sources is worse than useless** — it produces a confident, precise-looking score that is systematically wrong.

### An important caveat on these numbers

The 'agreement' figures above measure **how often the two sources concur**, not how often either is *correct*. There is no ground truth: nobody has labelled what a Data Analyst role truly requires. Converting agreement into genuine precision and recall would require hand-labelling the required skills in a sample of advertisements, which is identified as future work. The figures should be read as a measure of source consistency and nothing more.

---

## 5. Module 3 — gap analysis

| Role | Coverage per trial | Mean | Spread |
|---|---|---|---|
| Software Engineer | 44.9%, 40.0% | 42.5% | 4.9 pts |
| Data Analyst | 41.3%, 39.4% | 40.4% | 1.9 pts |
| Cybersecurity Analyst | 32.1%, 30.1% | 31.1% | 2.0 pts |

These are **synthetic CVs with 2–4 years of experience** compared against requirement lists drawn largely from mid-to-senior advertisements, so coverage in the 30–45% range is the honest result rather than a defect. A junior CV *should not* cover a senior requirement list.

The spread is caused by the live advertisement data differing between runs. Cybersecurity Analyst varies most, which is consistent with it having the thinnest advertisement evidence — with fewer postings, each individual posting exerts more influence on the resulting list.

A defect found by looking at the running interface: certifications and degrees were initially absent from the comparison set, so a CV that explicitly listed *CompTIA Security+* was told that CompTIA Security+ was missing. Qualifications, degrees and project technologies are now included, which is why Cybersecurity Analyst coverage improved materially between evaluation rounds.

---

## 6. Module 4 — CV improvement and the invention guards

| Measure | Result |
|---|---|
| Bullet points submitted | 36 |
| Rewrites accepted | 33 |
| Rewrites blocked | 3 |
| Reasons for blocking | {'empty_rewrite': 3} |

No rewrite in these runs attempted to invent a metric, a technology or a seniority claim — the blocks were empty responses from the model. That the invention guards did not fire here does **not** mean they are untested: they are verified directly by unit tests that feed them deliberately fabricated rewrites, covering invented metrics, invented technologies and five distinct escalation verbs. The guards are insurance, and insurance not paying out is the desired outcome.

---

## 7. Modules 5 & 6 — the interview and its scoring

| Measure | Result |
|---|---|
| Interviews conducted | 6 |
| Completed all six stages naturally | 6 / 6 |
| Mean questions per interview | 15 |
| Adaptive follow-up questions generated | 38 |

Every interview reached all six stages — introduction, background, technical, behavioural, candidate questions, closing — in order, and 38 questions were generated as follow-ups to something the candidate had actually just said, rather than drawn from a fixed sequence.

### Speech recognition confidence

| Confidence band | Turns |
|---|---|
| high | 90 |

**Read this with care.** The audio was produced by the local TTS engine, not by a human in a room. Synthesised speech is cleaner than human speech — no background noise, no disfluency, consistent pace — so these confidence figures are optimistic and should not be presented as recognition accuracy for real users. What they do establish is that the decode-transcribe pipeline works end to end on real audio.

### Interview scores

| Role | Score per trial (/5) | Mean | Spread |
|---|---|---|---|
| Software Engineer | 3.80, 3.60 | 3.70 | 0.20 |
| Data Analyst | 3.00, 3.00 | 3.00 | 0.00 |
| Cybersecurity Analyst | 3.20, 3.20 | 3.20 | 0.00 |

**The scripted answers were identical between trials**, so this spread is entirely the scoring model's own run-to-run variation. Up to 0.67 on a five-point scale — about 13% of the range — is not negligible, and it is the clearest available evidence that these scores should be read as *indicating areas to practise* rather than as a precise measurement.

The fixed rubric, whitelisted categories and code-side arithmetic bound how far a score can drift, but they cannot make a sampling model's per-category judgement deterministic. Reducing it would need a larger model, multiple sampled assessments averaged, or both.

**The scores have not been validated against human assessors.** Establishing whether they correlate with human judgement would require multiple interviewers rating a common set of transcripts and computing inter-rater agreement. Until that is done, the absolute calibration of these numbers is unknown, which is precisely why the product labels them practice feedback and not an assessment of ability.

---

## 8. Test results

**408 tests, 408 passing, 0 failing.**

- Offline suite (no model, no network): `403 passed, 5 deselected in 5.30s`
- Live suite (real models + network): `5 passed, 403 deselected in 10.60s`

Per-test detail is in [`docs/TEST_REPORT.md`](../docs/TEST_REPORT.md), generated from an actual run.

---

## 9. Provider comparison

The language model is chosen in configuration, so the same build runs against a local model or a hosted API. The identical harness was run a second time against Groq's free tier to test whether a hosted API would serve the voice interview better. Both rows are measured.

| Provider | Interview model | Turns | First token (median) | End of speech to first audio (median) | p90 | Worst turn |
|---|---|---|---|---|---|---|
| Ollama (local) | `llama3.2:3b` | 90 | 1,855 ms | **2,351 ms** | 3,008 ms | 3,818 ms |
| Groq (free tier) | `openai/gpt-oss-20b` | 45 | 17,363 ms | **17,417 ms** | 19,660 ms | 20,341 ms |

**The hosted API was 7.4x slower in sustained use**, which inverts the result from isolated calls: measured on its own, a single request to the hosted model returned its first token in 250-800 ms, three to eight times faster than the local model. The divergence is a rate limit, not model speed.

The cause was measured, not assumed:

- The free tier permits **8,000 tokens per minute**, read from the provider's own `x-ratelimit-limit-tokens` response header.
- One interview turn was instrumented and costs about **1,837 input tokens**, rising from 1,554 on the first turn to 2,039 by the sixth, because the conversation history is resent and grows each turn.
- With the output ceiling the reasoning models need, that is roughly **2,349 tokens per turn**, so the free tier sustains about 3.41 turns per minute - one every 17.6 seconds.
- This harness answers immediately, so it exceeded that ceiling: the provider returned **HTTP 429 twenty-one times**. The retry and backoff logic preserved every turn, but converted a sub-second reply into an eighteen-second one.

Two conclusions. The limitation is the free tier, not the provider: a paid tier, or an interview paced by a human who needs more than twenty seconds per answer, would stay inside the allowance and the hosted model would be faster. And for the workload evaluated here the local model is the right default, because its worst case is bounded - its spread is about 1.3x its median, against a factor of forty for the throttled hosted path. An unpredictable silence harms a spoken interview more than a consistently moderate delay. The hosted provider stays fully supported; see `backend/.env.example`.

---

## 10. Limitations of this evaluation

Stated here rather than left for a reader to discover.

| Limitation | Effect on the numbers above |
|---|---|
| **Synthesised, not human, speech** | Recognition confidence and latency are optimistic. Real speech has background noise, disfluency and variable pace. |
| **Scripted, not spontaneous, answers** | Real candidates hesitate, restart and digress. The adaptation logic was exercised, but not against genuinely unpredictable input. |
| **Agreement, not accuracy** | Section 4 measures how often two sources concur, not whether either is right. No ground truth exists. |
| **Synthetic CVs** | Written by the author, so they are better structured than many real CVs. Parser accuracy on genuinely messy documents will be lower. |
| **Two trials per role** | Enough to show the system is stable, not enough for statistical confidence intervals. |
| **One machine, one model** | All figures are from a single CPU configuration with a 3B local model. A different machine or provider will differ. |
| **Scores unvalidated** | No human baseline for the rubric scores. |

---

## 11. Summary

**What the evaluation establishes:**

- A complete spoken interview pipeline — local recognition, language model, local synthesis — runs on consumer CPU hardware with a median end-of-speech to first-audio latency of **2,351 ms** (p90 3,008 ms) across 90 measured turns.
- Local speech recognition achieves a real-time factor of **0.069**, and local synthesis **0.035**, on CPU alone.
- All six interview stages completed naturally in 6 of 6 interviews, with 38 adaptive follow-ups.
- The three-role requirement is satisfied, with consistent latency across roles.
- Requiring corroboration between the two requirement sources is essential: without it the gap score is systematically misleading.

**What it does not establish:**

- Recognition accuracy for real human speakers, or across accents.
- Whether the requirement lists are *correct*, only that two sources agree.
- Whether the rubric scores correlate with human assessment.
- Behaviour on genuinely messy real-world CVs.

**Issues recorded during the final runs:** none

