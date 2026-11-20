# Use of Generative AI in this Project

The course permits generative AI tools, with two conditions: generate the
minimal amount of code needed, and be able to explain the code and reproduce the
prompts at the viva. This document covers both.

There are **two separate things** called "prompts" in this project, and they
should not be confused:

| | What it is | Where |
|---|---|---|
| **Application prompts** | What the product sends to a language model at runtime | [`backend/app/services/llm/prompts.py`](../backend/app/services/llm/prompts.py) — all of them, in one file |
| **Development prompts** | What was asked of an AI assistant while building the project | This document |

---

## Part 1 — Application prompts (runtime)

Every prompt the running application sends is in a single module,
`backend/app/services/llm/prompts.py`, which exists precisely so they can be
produced on request. Nothing is constructed ad-hoc elsewhere in the codebase.

### The eight prompts

| Task | Function | Used by | Output |
|---|---|---|---|
| CV parsing | `cv_parse_prompt()` | Module 1 | JSON profile |
| Role requirements | `role_skills_prompt()` | Module 2B | JSON, 5 skill tiers |
| Advert skill extraction | `posting_skills_prompt()` | Module 2A | JSON skill lists |
| Gap learning plan | `gap_advice_prompt()` | Module 3 | JSON advice |
| Bullet rewriting | `bullet_improve_prompt()` | Module 4 | JSON rewrites |
| Interview planning | `interview_plan_prompt()` | Module 5 | JSON plan |
| Interview turn | `interview_turn_prompt()` + `INTERVIEW_SYSTEM_TEMPLATE` | Module 5 | spoken text |
| Scoring | `scoring_prompt()` | Module 6 | JSON assessment |

### Conventions applied to all of them

1. **The system prompt states the role AND the hard prohibitions.** The CV
   parser is told four times, in different words, not to infer anything.
2. **Untrusted content is fenced.** `wrap_untrusted()` wraps every piece of
   user- or web-supplied text in delimited blocks preceded by an explicit
   warning that it is data and must not be followed as instructions.
3. **Schemas are stated literally.** Each JSON task embeds the exact expected
   object and ends with "JSON only".
4. **Anti-invention rules are repeated per task, in that task's own words.**
   Generic instructions do not survive contact with a model that wants to sound
   impressive.

### The two most important ones

**Bullet rewriting** — the prohibitions are the first thing in the system
prompt, numbered, and phrased as consequences:

> ABSOLUTE PROHIBITIONS — breaking any of these makes the output useless and
> potentially harmful to the candidate:
> 1. NEVER invent a number, percentage, timescale, team size, revenue figure or
>    any other metric. If the original has no metric, the rewrite has no metric.
> 2. NEVER add a technology, tool, framework, responsibility, qualification or
>    achievement that is not in the original bullet.
> 3. NEVER escalate scope or seniority ('helped with' must not become 'led').
> 4. NEVER state or imply an outcome the original does not state.

**Scoring** — the model is told it is not making a hiring decision, and told to
use the whole scale:

> 2. Use the whole scale. A thin, generic answer is not a 4 out of 5.
> 3. If a category was never genuinely tested, score it null and say why — do
>    not guess.
> 4. You are producing practice feedback, NOT a hiring decision.

### Prompting is not the defence

The important design point: **none of these instructions are trusted**. Every
response passes through `json_guard.py` for structural validation, and
module-specific guards verify the content against the source document. The
prompts reduce the failure rate; the code catches what gets through. See
[TECHNICAL.md § 11](TECHNICAL.md#11-defending-against-the-llm).

---

## Part 2 — Development prompts

An AI assistant was used throughout development. What follows is an honest
account of where it helped, where it was wrong, and what was decided by hand.

### How it was used

The assistant was given the course specification and asked to implement the
project. Work proceeded module by module, with the running application and the
test suite as the source of truth — not the assistant's description of what it
had written.

Representative prompts, by phase:

**Architecture**
> "Design a backend architecture for a career platform with seven modules: CV
> parsing, live job scraping plus LLM skill generation, gap analysis, CV
> improvement, a voice interview with local STT and TTS, rubric scoring, and
> latency measurement. It must run on a normal laptop. Justify each technology
> choice and say what you rejected."

**Module 2 — the fusion problem**
> "I have two sources of role requirements that disagree: scraped job adverts
> and an LLM. Design a fusion rule that weights them, and make the provenance of
> every requirement visible to the user."

**Skill normalisation**
> "React, ReactJS and React.js must resolve to one skill, but React and Redux
> must not merge — they are closer as strings. Design a matching cascade that
> handles both, without a 2.5 GB PyTorch dependency, and make each decision
> explainable."

**The latency problem**
> "The interview is graded on the time from the end of the candidate's speech to
> the start of the interviewer's reply. Design the turn so audio starts before
> generation finishes, and instrument it so every figure is measured rather than
> estimated."

**Anti-hallucination**
> "Prompt instructions alone will not stop a model adding an invented metric to
> a CV bullet. Design mechanical checks that verify every rewrite against the
> original and reject it if it invents anything."

**Testing**
> "Write tests that would catch the project's real failure modes, not just the
> happy path: malformed uploads, prompt injection in a CV, over-merging of
> distinct skills, hiring language leaking into feedback, implausible latency
> readings."

### Where the assistant was wrong, and tests caught it

This is the part worth reading, because it is the evidence that the code was
verified rather than accepted.

| Bug | How it surfaced | Fix |
|---|---|---|
| Alias noise-stripping made `"security plus"` → `"security"`, so *CompTIA Security+* appeared as a Data Analyst requirement | Inspecting real output | Alias index keyed on a conservative form |
| `strip_bullet` ate the leading digit of `"5+ years of Java"`, defeating the year-removal pattern | A parametrised normalisation test | List numbering only stripped in its real form |
| `"Node.js"` and `"NodeJS"` normalised differently | A manual spot-check | Corrected the `ejs` guard |
| Wrapped PDF description lines became separate "projects" | Comparing output against the source CV | Project headers capped at 9 words |
| Duplicate education entries after the LLM merge | Same | Token-overlap entity matching |
| UK grade `"2:1"` never extracted | A CV parser test | Grade pattern extended |
| `"milliseconds"` not counted as a metric | An answer-analysis test | Unit list widened |
| Sentence-final period broke skill matching: `"on AWS."` | A matcher test | Strip only dots followed by whitespace |
| Prompt injection in a CV was read by the **regex** layer, not the model, and reported as fact | A deliberately hostile test | `strip_injection_lines()` before all parsing |
| 227 "requirements" per role made the gap score meaningless | Reading the evaluation output | Corroboration filter (227 → 70) |
| A retired RSS slug returned HTTP 200 with an empty body, cached as success | Source report showing 0 results for a working feed | Empty 2xx treated as failure |
| `faster-whisper` incompatible with PyAV 19 | Runtime `TypeError` | Wrote `audio_decode.py` |
| A 6.5-hour latency reading poisoned every mean | Reading the evaluation summary | Process hygiene **and** an `IMPLAUSIBLE_MS` guard |
| Specificity regex missed "I profiled it", "we got it down" — good answers scored "weak" and difficulty wrongly adapted down | Reading a screenshot of a real interview | Generalised to any past-tense verb after I/we |
| Certifications never reached the gap comparison, so a CV listing *CompTIA Security+* was told it was missing | Reading a screenshot of a real gap analysis | `candidate_skill_set()` includes certifications, degrees and project technologies |

Every one of those is a case where the first implementation looked correct and
was not. Several were found only by looking at real output on a real screen,
which is the argument for building the UI early rather than last.

### Decisions made by hand, not by the assistant

- **Which job boards to use**, and the decision not to scrape LinkedIn, Indeed
  or Glassdoor on terms-of-service grounds.
- **The fusion weights** (0.55 / 0.30 / 0.15) and the corroboration threshold,
  both tuned against real collected data.
- **The rubric**: six categories, the 1–5 descriptors, and weights that shift
  with difficulty.
- **Rejecting sentence-transformers**, with latency, install size and
  explainability as the stated reasons.
- **Reporting median and p90 rather than the mean alone** — which turned out to
  matter when the mean was poisoned and the median was not.
- **The honesty posture throughout**: provenance badges, visible rejected
  claims, per-source failure reporting, "requirement coverage" rather than
  employability, and the degraded-mode banner.

### What is genuinely original

The specification defines *what* to build. These were the open problems:

1. How to fuse two disagreeing requirement sources — and the discovery that an
   unfiltered union is worse than useless.
2. How to normalise skills explainably without a heavyweight embedding model.
3. How to make a spoken interview feel responsive on CPU — sentence-level
   synthesis, local answer analysis, and warming the models before the clock
   starts.
4. How to make an LLM's output safe to show a person about their own career.

---

## Part 3 — Declaration

- All application code in `backend/` and `frontend/` was written for this
  project, with AI assistance as the course permits.
- The author can explain any part of the codebase; see
  [VIVA_PREPARATION.md](VIVA_PREPARATION.md).
- All runtime prompts are reproducible from
  [`prompts.py`](../backend/app/services/llm/prompts.py).
- Every CV in `evaluation/sample_cvs/` is synthetic and marked as such.
- Every number in the evaluation and the report was produced by
  `scripts/run_evaluation.py` on this machine. Nothing is estimated or invented;
  where something could not be measured, it says so.
- The screenshots are genuine captures of the running application, produced by
  `scripts/capture_screenshots.py`. None is edited or mocked up.
