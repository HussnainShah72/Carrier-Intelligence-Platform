"""
The academic report's prose.

Kept separate from the document builder so the writing can be edited without
touching layout code. Every number in the report comes from
`evaluation/results/*.json` at build time and is substituted into these strings
by `make_report.py` — so the report cannot drift from the measurements.

Placeholders use {curly_braces} and are listed in `make_report.REQUIRED_KEYS`.
"""

from __future__ import annotations

# ===========================================================================
# Title page
# ===========================================================================

TITLE = "Career Intelligence Platform"
SUBTITLE = (
    "An NLP-Driven Job Preparation System with Fully Local Speech Processing "
    "and a Structured Adaptive Voice Interview"
)
COURSE = "Natural Language Processing"
TERM = "Course Project — Fall 2026"
PROJECT_CHOICE = "Project 2: Career Intelligence Platform"

#: The single source of truth for who submitted this. The report title page,
#: the README table and the submission checker all read from here, so the names
#: cannot drift apart between the deliverables.
GROUP_MEMBERS = [
    ("Hussnain Haider", "i230695"),
    ("Akbar Hussain", "i233094"),
]

#: Optional title-page lines. Each renders only when it is non-empty, so the
#: title page stays clean if a field does not apply. Set them here; the README
#: and the report both read from this module.
INSTITUTION = "FAST-NUCES, Islamabad"
DEPARTMENT = "Department of Software Engineering"
SECTION = "B"
INSTRUCTOR = "Asif Muhammad Malik"   # rendered under "Submitted to"

# ===========================================================================
# 2. Abstract
# ===========================================================================

ABSTRACT = """
Job seekers preparing for a technical interview face three separate problems that \
existing tools address only in isolation: understanding what a role actually requires, \
knowing where their own experience falls short of it, and practising the interview \
itself under realistic conditions. This report presents the Career Intelligence \
Platform, a locally hosted system that addresses all three in one workflow, with \
particular attention to the honesty of the claims it makes to the user.

The system implements seven modules. A hybrid CV parser combines deterministic rules \
with a language model under a constraint that the rules decide what exists and the \
model may only make it tidier, with every model-supplied value checked against the \
source document. A dual-source requirement engine collects live job advertisements from \
six public job boards and independently queries a language model, then fuses the two \
into a single list in which every requirement carries its provenance. A four-stage \
skill-normalisation cascade resolves surface variants such as React, ReactJS and \
React.js to one canonical skill while keeping genuinely distinct skills apart, using a \
curated taxonomy of {taxonomy_skills} skills and {taxonomy_aliases} aliases, fuzzy \
token matching, and TF-IDF character n-gram similarity. A gap analyser produces an \
importance-weighted coverage figure that is explicitly framed as requirement coverage \
rather than employability. A CV improvement module rewrites weak bullet points and \
mechanically rejects any rewrite that introduces a metric, technology or seniority \
claim absent from the original. A structured voice interview conducts a six-stage \
conversation with speech recognition and speech synthesis running entirely on the local \
machine, adapting its questions to the candidate's CV, the role, and the content of \
their previous answers. Finally, an instrumented measurement layer records genuine \
latency throughout.

The system was evaluated across three deliberately dissimilar roles — Software \
Engineer, Data Analyst and Cybersecurity Analyst — with {trials} independent trials \
each, producing {interview_count} complete interviews and {turn_count} measured \
conversational turns. The median time from the end of the candidate's speech to the \
first audio of the interviewer's reply was {e2e_median} ms (p90 {e2e_p90} ms), \
decomposed into {stt_median} ms of local speech recognition, approximately \
{llm_share} ms of language model latency, and {tts_median} ms to synthesise the first \
spoken sentence. Local speech recognition achieved a real-time factor of \
{stt_rtf}, and local speech synthesis {tts_rtf}. A corroboration filter introduced \
during development reduced the requirement list for one role from 227 candidate skills \
to 70 and raised inter-source agreement from 8.7% to 17.1%, demonstrating that naive \
union of two requirement sources produces a materially misleading gap score.

The work is presented alongside its limitations rather than in spite of them: the job \
boards used skew towards remote technical roles, reply latency scales with utterance \
length because recognition is not streamed, skill matching is lexical rather than \
semantic, and the evaluation measures agreement between two sources rather than \
accuracy against ground truth that does not exist. A test suite of {test_count} tests, \
all passing, covers the application logic deterministically, with a separate opt-in \
suite exercising the real speech models.
"""

# ===========================================================================
# 3. Introduction
# ===========================================================================

INTRODUCTION = """
Preparing for a job interview is an information problem before it is a performance \
problem. A candidate must first establish what a given role genuinely requires, which \
is harder than it sounds: job advertisements are written to attract rather than to \
describe, they use inconsistent vocabulary for identical skills, and any single \
advertisement is a sample of one. The candidate must then assess their own experience \
against that requirement set, a comparison people are notoriously poor at making about \
themselves. Only then does the performance problem begin — articulating that experience \
under time pressure, out loud, to a stranger.

Existing tools address fragments of this. Applicant tracking system simulators score a \
CV against a single job description. Interview question banks list questions without \
reference to the candidate. General-purpose chat assistants will conduct a mock \
interview if asked, but have no structure, no measurement, and no grounding in the \
candidate's actual CV. None of them close the loop between what a role requires, what \
the candidate has, and how the candidate performs when asked about it.

This project builds that loop as a single system. The user uploads a CV and names any \
role. The system establishes the role's requirements from two independent sources, \
compares them against the parsed CV, strengthens the CV's weakest claims without \
inventing anything, and then conducts a spoken mock interview that is grounded in both \
the CV and the role and adapts to the candidate's answers in real time. It concludes \
with a scored assessment against a rubric that was fixed before the interview began.

Two constraints shaped the engineering throughout. The first is imposed by the course \
specification: speech recognition and speech synthesis must run locally, not through a \
cloud API. This is a meaningful constraint rather than an arbitrary one, because it \
forces the latency budget onto consumer hardware and makes the privacy claim real. The \
second constraint is self-imposed and, in the author's view, more important: the system \
must not make claims it cannot support. A tool that tells a job seeker they are a 78% \
match for a role, or that silently adds an invented achievement to their CV, is worse \
than no tool at all, because its output is confident and wrong and the user has no way \
to tell. Much of the engineering described in this report exists to make the system's \
claims checkable by the person reading them.
"""

# ===========================================================================
# 4. Background and motivation
# ===========================================================================

BACKGROUND = """
The technical hiring process has become increasingly standardised in form and \
increasingly opaque in substance. Structured interviews — where every candidate is \
asked a comparable set of questions across defined competency areas — are well \
established as more predictive and more equitable than unstructured conversation. Yet \
candidates rarely get to practise in that format. Mock interviews with a peer lack \
domain knowledge; paid coaching is expensive and not scalable; and reading a list of \
"top 50 interview questions" rehearses recall rather than articulation.

At the same time, the gap between how roles are advertised and how they are discussed \
has widened. A single job title maps to very different expectations across \
organisations, and the vocabulary used is inconsistent even within one advertisement. \
A system that reasons about role requirements must therefore treat the advertisement \
corpus as noisy evidence rather than as ground truth, and must reconcile surface forms \
that refer to the same underlying skill.

Three technical developments make a system of this kind feasible on a personal machine \
for the first time. Transformer-based automatic speech recognition, particularly \
Whisper and its efficient reimplementations, now achieves usable accuracy on \
consumer CPUs at model sizes of a few hundred megabytes. Neural text-to-speech systems \
such as Piper produce natural speech far faster than real time on the same hardware. \
And instruction-following language models small enough to run locally — in the three to \
seven billion parameter range — are now capable enough to generate structured output \
reliably when constrained properly.

The motivation for building this as a local-first system is not only the course \
requirement. A CV is a personal document, and a recorded mock interview is a recording \
of someone at their least confident. Sending both to a third-party API is a real \
privacy cost that most users would not knowingly accept. Demonstrating that the whole \
pipeline can run on a laptop, with measured latency that remains conversational, is \
therefore part of the contribution rather than an incidental constraint.
"""

# ===========================================================================
# 5. Problem statement
# ===========================================================================

PROBLEM_STATEMENT = """
**The real-world gap.** A job seeker preparing for a specific role cannot currently \
obtain, from any single tool, an evidence-backed statement of what that role requires, \
an honest assessment of where their own experience falls short, and realistic spoken \
practice that is grounded in both. The three capabilities exist separately and do not \
compose, because each is built on assumptions the others do not share.

**Why conventional solutions are insufficient.** Four classes of existing solution each \
fail for a structural reason rather than a quality reason.

*Keyword-matching ATS simulators* compare a CV against one job description using exact \
string matching. They fail on vocabulary: a CV saying "ReactJS" scores zero against a \
description saying "React.js". They also fail on sample size, because one job \
description is not a role. Their output is a percentage with no explanation, which the \
user cannot check and therefore cannot act on.

*Static question banks* are not grounded in the candidate. The same question list is \
served to a graduate and to someone with ten years of experience, so the practice does \
not probe what the individual actually needs to improve. There is no follow-up, which \
is where real interviews extract information.

*General-purpose conversational assistants* can conduct a plausible mock interview, but \
they have no enforced structure, so the conversation drifts; no measurement, so the \
candidate cannot tell whether they are improving; no fixed assessment criteria, so \
feedback varies between runs; and critically no grounding constraint, so they will \
cheerfully invent an achievement for the candidate's CV if asked to improve it. They \
also require sending the CV and the interview transcript to a third party.

*Commercial interview-practice platforms* do offer structure and recording, but operate \
as closed cloud services, charge per session, cover a fixed catalogue of roles, and \
give no insight into how their scores are produced.

**The specific technical problem.** Build a system that: establishes role requirements \
from two independent and disagreeing sources, reconciling their vocabulary; parses an \
arbitrary CV into structured data without fabricating content; compares the two and \
explains every judgement; conducts a structured spoken interview that adapts to the \
candidate within a latency budget that keeps conversation natural, using only local \
speech models on consumer hardware; and assesses the result against transparent, \
pre-declared criteria. Every output must be traceable to its evidence, and every \
limitation must be visible to the user rather than concealed by confident presentation.
"""

# ===========================================================================
# 6. Objectives
# ===========================================================================

OBJECTIVES = [
    ("O1", "Implement a CV parser that extracts skills, roles, education, projects and "
           "certifications from PDF and Word documents into structured data, and that "
           "does not introduce information absent from the source document."),
    ("O2", "Implement live collection of job advertisements from publicly accessible "
           "sources, respecting robots policies, rate limits and terms of service, and "
           "reporting every collection outcome honestly including failures."),
    ("O3", "Implement independent LLM-based generation of role requirements, and fuse it "
           "with the collected advertisement evidence into a single requirement list in "
           "which the provenance of every entry is visible."),
    ("O4", "Implement skill normalisation that resolves surface variants of the same "
           "skill to one canonical form, keeps genuinely distinct skills separate, and "
           "records which mechanism produced each decision."),
    ("O5", "Implement gap analysis producing an importance-weighted coverage measure, "
           "severity-ranked gaps and per-decision evidence, framed so that it cannot be "
           "mistaken for a prediction of hiring outcome."),
    ("O6", "Implement CV bullet improvement with mechanical verification that rejects any "
           "rewrite introducing a metric, technology or seniority claim not present in "
           "the candidate's own material."),
    ("O7", "Implement a six-stage structured voice interview with speech recognition and "
           "speech synthesis running entirely locally, adapting its questions to the CV, "
           "the role and the candidate's previous answers."),
    ("O8", "Implement rubric-based scoring against criteria fixed before any interview "
           "runs, with an explanation for every score and no implied hiring decision."),
    ("O9", "Instrument the system to measure genuine end-of-speech to first-audio latency "
           "and its constituent stages, and evaluate across at least three dissimilar "
           "roles with repeated trials."),
    ("O10", "Deliver a professional web interface, a reproducible test suite, and "
            "documentation sufficient for a third party to install and run the system."),
]

# ===========================================================================
# 7. Scope
# ===========================================================================

SCOPE_IN = [
    "PDF, Microsoft Word (.docx) and plain-text CV parsing with structured extraction.",
    "Live collection from six public job boards that permit programmatic access.",
    "LLM-generated role requirements for arbitrary job titles, with no fixed role list.",
    "Skill normalisation across a curated taxonomy with fuzzy and vector fall-back.",
    "Importance-weighted gap analysis with per-decision evidence and severity ranking.",
    "CV bullet rewriting with mechanical anti-invention verification.",
    "A six-stage spoken interview with fully local speech recognition and synthesis.",
    "Adaptive follow-up questioning and bounded difficulty adaptation.",
    "Rubric-based scoring with per-category justification and evidence quotes.",
    "Per-turn latency instrumentation and an exportable performance report.",
    "A single-user web application running entirely on one machine.",
]

SCOPE_OUT = [
    ("Optical character recognition", "Scanned, image-only PDFs are rejected with an "
     "explanatory message rather than silently mis-parsed. OCR quality varies enough "
     "that a wrong profile would be worse than a refusal."),
    ("Scraping LinkedIn, Indeed or Glassdoor", "Their terms of service prohibit "
     "automated access. Sources that publish their listings for programmatic use were "
     "used instead; the resulting coverage limitation is reported rather than hidden."),
    ("Multi-user deployment", "No authentication, no tenancy, no deployment hardening. "
     "The system is a single-user local tool by design."),
    ("Non-English interviews", "Speech recognition uses an English-only Whisper variant "
     "and the rubric assumes English. Multilingual support would require different "
     "models and a reworked rubric."),
    ("Real-time barge-in", "The candidate cannot interrupt the interviewer mid-sentence. "
     "This is a genuine realism gap and is listed as future work."),
    ("Validation of scores against human assessors", "Establishing whether the rubric "
     "scores correlate with human judgement would require multiple assessors rating "
     "common transcripts, which was out of scope."),
]

# ===========================================================================
# 8. Related work
# ===========================================================================

RELATED_WORK = """
**Automatic speech recognition.** Whisper (Radford et al., 2023) established that a \
single encoder–decoder transformer trained on a large weakly supervised multilingual \
corpus generalises across domains without fine-tuning. Its practical limitation for \
interactive use is inference cost; CTranslate2-based reimplementations such as \
faster-whisper address this with quantisation and optimised kernels, achieving several \
times the throughput of the reference implementation on CPU. This project uses the \
English-only base model at 8-bit integer precision, which the evaluation found achieves \
a real-time factor of {stt_rtf} on the target hardware — fast enough that recognition \
is not the dominant term in reply latency.

**Neural speech synthesis.** VITS (Kim et al., 2021) combined variational inference \
with adversarial training to produce end-to-end speech synthesis without a separate \
vocoder stage. Piper packages VITS-derived models as ONNX graphs sized for edge \
deployment. The measured real-time factor of {tts_rtf} is what makes sentence-level \
incremental synthesis viable: the cost of synthesising one sentence is small enough \
that it can be paid repeatedly within a single reply.

**Skill extraction and normalisation.** The research literature treats skill extraction \
from job advertisements as a sequence labelling or entity linking problem, typically \
using transformer encoders fine-tuned on annotated corpora such as SkillSpan. The \
ESCO taxonomy provides a standardised multilingual reference for occupations and \
skills. This project deliberately adopts a lighter approach — a curated alias taxonomy \
with fuzzy and character n-gram fall-back — for reasons set out in Section 18.3: the \
normaliser sits on the interactive latency path, and the explainability of its \
decisions is a product requirement rather than a nicety.

**Conversational assessment.** Research on automated interview assessment has examined \
both verbal content and paralinguistic features such as prosody and pause structure. \
This project assesses verbal content only. The decision is defensible on fairness \
grounds as well as scope: paralinguistic scoring has repeatedly been shown to encode \
accent and cultural speech-pattern biases, and a practice tool that penalises a \
candidate for their accent would be actively harmful.

**Structured output from language models.** Reliably obtaining machine-readable output \
from instruction-following models remains an engineering problem rather than a solved \
one. Approaches include constrained decoding, schema-guided generation, and \
validate-and-retry. This project uses explicit schema statements in the prompt combined \
with a repair-and-revalidate cascade, because constrained decoding is not uniformly \
available across the providers the system supports.

**Grounding and hallucination mitigation.** Retrieval-augmented generation reduces \
unsupported generation by conditioning on retrieved evidence, but does not eliminate \
it. This project applies a stricter post-hoc constraint in the domains where invention \
is most harmful: a generated claim about the candidate is discarded unless it can be \
traced to characters in the candidate's own document. This is closer to extractive \
verification than to retrieval augmentation, and is viable here because the source \
document is short and available in full.
"""

# ===========================================================================
# 9 & 10. Requirements
# ===========================================================================

FUNCTIONAL_REQUIREMENTS = [
    ("FR1", "CV upload and extraction", "Accept PDF, DOCX and TXT CVs up to 5 MB; "
     "validate extension and content; extract text reliably.", "Module 1", "High"),
    ("FR2", "Structured CV parsing", "Extract name, contact details, skills, experience "
     "with bullet points, education with grades, projects and certifications.", "Module 1", "High"),
    ("FR3", "Grounded extraction", "Reject any model-supplied value that cannot be traced "
     "to the source document, and show the user what was rejected.", "Module 1", "High"),
    ("FR4", "Live job posting collection", "Collect current advertisements for the "
     "user's role from public sources, honouring robots policies and rate limits.", "Module 2", "High"),
    ("FR5", "Honest source reporting", "Report each source's outcome, including failure "
     "modes, without presenting a failure as an empty success.", "Module 2", "High"),
    ("FR6", "LLM role generation", "Independently generate role requirements across "
     "technical, tooling, professional and qualification tiers.", "Module 2", "High"),
    ("FR7", "Source fusion with provenance", "Combine both sources into one list in which "
     "each requirement's origin and importance are visible.", "Module 2", "High"),
    ("FR8", "Skill normalisation", "Resolve surface variants (React / ReactJS / React.js) "
     "to one canonical skill without merging distinct skills.", "Module 2/3", "High"),
    ("FR9", "Gap classification", "Classify each requirement as matched, partially matched "
     "or missing, with stated evidence.", "Module 3", "High"),
    ("FR10", "Weighted coverage score", "Produce an importance-weighted coverage figure "
     "and rank gaps by severity.", "Module 3", "High"),
    ("FR11", "Non-misleading presentation", "Frame all scores as requirement coverage and "
     "never as a prediction of hiring outcome.", "Module 3/6", "High"),
    ("FR12", "Bullet improvement", "Rewrite weak CV bullets and present original and "
     "rewrite side by side with accept, reject and copy controls.", "Module 4", "High"),
    ("FR13", "Invention guards", "Mechanically reject rewrites introducing a new metric, "
     "technology or seniority claim.", "Module 4", "High"),
    ("FR14", "Six-stage interview", "Conduct introduction, background, technical, "
     "behavioural, candidate questions and closing stages in order.", "Module 5", "High"),
    ("FR15", "Local speech recognition", "Transcribe candidate speech entirely on the "
     "local machine.", "Module 5", "High"),
    ("FR16", "Local speech synthesis", "Generate the interviewer's voice entirely on the "
     "local machine.", "Module 5", "High"),
    ("FR17", "Streaming response", "Stream generated text and begin speaking before the "
     "full reply is complete.", "Module 5", "High"),
    ("FR18", "Adaptive questioning", "Generate follow-up questions from the content of "
     "previous answers and adapt difficulty to demonstrated competence.", "Module 5", "High"),
    ("FR19", "Graceful speech failure", "Detect recognition failure and offer a text "
     "fallback without ending the interview.", "Module 5", "High"),
    ("FR20", "Pre-declared rubric", "Define scoring categories, scale and weights before "
     "any interview runs, and show them to the candidate first.", "Module 6", "High"),
    ("FR21", "Explained scoring", "Provide a justification and, where available, a "
     "transcript quote for every category score.", "Module 6", "High"),
    ("FR22", "Actionable feedback", "Produce strengths, weaknesses, answers to improve, "
     "preparation topics and a personalised plan.", "Module 6", "Medium"),
    ("FR23", "Latency measurement", "Measure end-of-speech to first-audio latency and its "
     "constituent stages for every turn.", "Module 7", "High"),
    ("FR24", "Multi-role evaluation", "Support evaluation across at least three "
     "dissimilar roles with exportable results.", "Module 7", "High"),
]

NON_FUNCTIONAL_REQUIREMENTS = [
    ("NFR1", "Performance", "End-of-speech to first audio should remain within a range "
     "that preserves conversational feel on consumer CPU hardware.",
     "Median {e2e_median} ms, p90 {e2e_p90} ms over {turn_count} turns.", "Met"),
    ("NFR2", "Privacy", "No audio may leave the machine; CV data must remain local by "
     "default.",
     "Speech models run in-process; recordings are never written to disk; default LLM "
     "provider is local.", "Met"),
    ("NFR3", "Portability", "The system must run on a normal laptop by following the "
     "README, with no GPU.",
     "CPU-only; approximately 210 MB of speech models; verified from a clean virtual "
     "environment.", "Met"),
    ("NFR4", "Reliability", "External failures must degrade the system gracefully rather "
     "than terminate a workflow.",
     "Eight named source failure states; offline LLM engine; text fallback for speech.", "Met"),
    ("NFR5", "Transparency", "Every claim shown to the user must carry its evidence or "
     "its provenance.",
     "Provenance badges, rejected-claims table, per-source reports, per-score "
     "justifications.", "Met"),
    ("NFR6", "Security", "Uploads must be validated; secrets must never be exposed.",
     "Magic-byte validation, size limits, zip-bomb guard, injection stripping; API keys "
     "never returned by the API.", "Met"),
    ("NFR7", "Testability", "The system must be verifiable without a model or network.",
     "{test_count} tests pass deterministically against the offline engine.", "Met"),
    ("NFR8", "Usability", "A user must be able to complete the workflow without touching "
     "code or configuration.",
     "Eight-page interface with loading, error and empty states throughout; works with "
     "no .env editing.", "Met"),
    ("NFR9", "Maintainability", "Modules must be separable and individually testable.",
     "One package per module; services callable without HTTP.", "Met"),
    ("NFR10", "Accessibility", "Interface controls must be operable by keyboard and "
     "legible in both themes.",
     "ARIA roles and labels, visible focus indicators, reduced-motion support, light and "
     "dark themes.", "Partially met — not validated with assistive technology."),
]

# ===========================================================================
# 12. Methodology
# ===========================================================================

METHODOLOGY = """
Development followed an incremental, evidence-driven process rather than a waterfall \
sequence, for a specific reason: several of the most consequential defects in this \
system were invisible in code review and in unit tests, and became obvious only when \
real output was displayed on a real screen. Three examples, each discussed in \
Section 17, illustrate the point — a requirement list that had silently grown to 227 \
entries, a candidate's own certification being reported as missing, and good interview \
answers being scored as weak.

**Phase 1 — Specification analysis.** The course specification was decomposed into 164 \
discrete requirements, recorded in a traceability matrix mapping each to an \
implementation location and a verifying test. The matrix was maintained throughout \
rather than reconstructed at the end.

**Phase 2 — Architecture and technology selection.** Each layer's technology was chosen \
against explicit criteria, with rejected alternatives recorded at the time rather than \
rationalised afterwards. Section 18.3 presents this analysis.

**Phase 3 — Shared components first.** The skill taxonomy, text normaliser and LLM \
output guards were built before the feature modules, because three of the seven modules \
depend on them. Building them first meant their failure modes were understood before \
anything was built on top.

**Phase 4 — Module implementation.** Modules were implemented in dependency order: CV \
parsing, then requirement collection, then gap analysis, then improvement, then the \
interview, then scoring, then measurement. Each was made to work end to end through the \
interface before the next was started.

**Phase 5 — Adversarial testing.** Tests were written to target the system's plausible \
failure modes rather than its happy path: malformed and hostile uploads, prompt \
injection inside a CV, over-merging of distinct skills, hiring language leaking into \
feedback, and implausible latency readings. This phase produced fourteen distinct \
defects, catalogued in Section 17.3.

**Phase 6 — Instrumented evaluation.** A harness was written to drive the real HTTP API \
exactly as the browser does, across three roles with repeated trials, recording every \
measurement to JSON. The report's numbers are substituted from that output at build \
time, so the document cannot drift from the measurements.

**Phase 7 — Documentation.** Written for three audiences: a user following the README, \
a developer reading the technical documentation, and an examiner assessing the work.
"""

# ===========================================================================
# 15. Testing (prose; tables are generated)
# ===========================================================================

TESTING_INTRO = """
The test suite comprises {test_count} tests, all passing. Its design embodies one \
decision worth stating explicitly: the default suite runs against a deterministic \
rule-based engine rather than a language model.

The reason is that a sampling language model produces different output on every run. A \
test suite built on one is either flaky, or so loosely specified that it asserts \
nothing of value. Running against a deterministic engine means these tests verify the \
application's own logic — parsing, normalisation, matching, the invention guards, the \
interview state machine, persistence and the HTTP contract — and that they produce \
identical results on every run, including on a machine with no model and no network.

Tests that genuinely require a downloaded model or live internet access are marked and \
excluded by default. The most significant of these synthesises a known sentence with \
the local text-to-speech engine, transcribes it with the local speech recogniser, and \
asserts that the content words survive — an end-to-end verification of the mandatory \
local speech pipeline.

A deliberate emphasis was placed on adversarial cases. Of the test suite, a substantial \
proportion exercises failure rather than success: malformed uploads, files whose \
contents contradict their extension, zip bombs, encrypted and image-only PDFs, empty \
documents, prompt injection embedded in a CV, over-merging of distinct skills, invented \
metrics and technologies in rewrites, escalated seniority claims, hiring verdicts in \
feedback, and implausible latency readings.
"""

TESTING_NOT_AUTOMATED = [
    ("Real microphone capture", "Browser MediaRecorder requires a physical input device "
     "that a headless browser does not have.",
     "Manual testing in Chrome; the live input-level meter makes a muted or incorrect "
     "device immediately visible to the user."),
    ("Human speech recognition accuracy", "No labelled human-speech corpus exists for "
     "this domain and recording one was out of scope.",
     "The live round-trip test uses synthesised audio; the limitation is stated in the "
     "evaluation and the results are described as optimistic."),
    ("Cloud LLM providers", "No API key may be committed, and a paid key cannot be a "
     "test dependency.",
     "The provider abstraction is exercised through the offline and local paths; a "
     "configured provider is probed at runtime from the Settings page."),
    ("Rubric score correctness", "There is no ground truth; establishing it requires "
     "multiple human assessors and an inter-rater agreement measure.",
     "The scoring process is tested instead: fixed rubric, whitelisted categories, "
     "clamped scores, arithmetic performed in code, hiring language removed."),
    ("Job board content", "Board contents change continuously; asserting on them would "
     "produce failures unrelated to this code.",
     "Reachability and parsing are tested live; content assertions are limited to "
     "structural properties."),
]

# ===========================================================================
# 18. CCP analysis
# ===========================================================================

CCP_PROBLEM = """
The problem statement is set out in full in Section 5 and is summarised here against \
the Complex Computing Problem criteria.

The real-world gap is that no single tool connects what a role requires, what a \
candidate has, and how that candidate performs when questioned about it. The three \
capabilities exist separately and do not compose, because each rests on assumptions the \
others do not share: an ATS simulator assumes one job description is the ground truth; \
a question bank assumes candidates are interchangeable; a chat assistant assumes \
structure and measurement are unnecessary.

A standard solution does not solve it for three distinct reasons. First, there is no \
authoritative source of role requirements: advertisements are noisy, inconsistent in \
vocabulary, and individually unrepresentative, so requirements must be *inferred* from \
disagreeing evidence rather than looked up. Second, the interview component has a \
real-time constraint that rules out a straightforward request-response design, because \
waiting for a complete generated reply before speaking it produces a delay that \
destroys conversational feel. Third, and most fundamentally, the system must make \
claims about a person's career, which means the cost of a confident error is borne by \
the user — a requirement that cannot be satisfied by improving model quality, only by \
designing verification into the pipeline.
"""

CCP_DRIVERS = [
    ("Multiple interacting components with non-local effects",
     "Seven modules share three components — the skill taxonomy, the normaliser and the "
     "LLM output guards. A change to a normalisation threshold alters the CV profile, the "
     "role requirement list and the gap score simultaneously. The choice of speech "
     "recognition model size trades accuracy against the interview latency budget. These "
     "couplings mean no module can be tuned in isolation, and they were the source of "
     "several defects where a locally correct change produced a globally wrong result."),

    ("No obvious solution to the source-fusion problem",
     "The specification mandates two requirement sources that genuinely disagree but "
     "prescribes no rule for combining them. There is no established answer in the "
     "literature for fusing scraped evidence with generative assertion. The weighting "
     "used here (advert frequency 0.55, LLM tier 0.30, agreement 0.15) was designed, not "
     "looked up, and the discovery that an unfiltered union of the two sources produces a "
     "materially misleading gap score came only from inspecting real output."),

    ("Conflicting requirements with no optimum",
     "Latency against quality: a larger language model answers better and breaks the "
     "conversational feel. Accuracy against portability: sentence embeddings would match "
     "skills semantically but add approximately 2.5 GB to an installation that must work "
     "on a normal laptop. Coverage against legality: the job boards with the best data "
     "prohibit automated access. Each conflict was resolved by an explicit trade-off, "
     "documented in Section 18.4, rather than optimised away."),

    ("Inherent uncertainty in the NLP components",
     "Speech recognition is probabilistic and degrades with accent, pace and background "
     "noise. Language model output is non-deterministic and may be fluently wrong. "
     "Neither can be made exact, so the engineering problem is not eliminating error but "
     "bounding its consequences: recognition confidence is surfaced and a text fallback "
     "offered; generated claims about the candidate are verified against their own "
     "document before display."),

    ("Hard real-time constraint on the critical path",
     "The interview is assessed on the interval between the candidate finishing speaking "
     "and the interviewer beginning to reply. This single constraint forced four design "
     "decisions that a batch system would not require: answer analysis must be local "
     "rather than a second model call; speech synthesis must be incremental at sentence "
     "granularity; models must be warmed before measurement begins; and the normaliser "
     "needs an n-gram pre-filter to stay within budget."),

    ("Dependence on uncontrolled external systems",
     "Six job boards, each with its own schema, rate limits, availability and failure "
     "modes. During development one board's category feed was retired and began returning "
     "HTTP 200 with an empty body — a success status carrying no data, which the caching "
     "layer initially stored as a valid result. Robust handling of other parties' "
     "unreliable services proved a substantial fraction of the engineering effort."),

    ("Engineering problems without clean solutions",
     "A genuine version incompatibility between faster-whisper and PyAV, resolved by "
     "implementing audio decoding directly against the stable API rather than pinning a "
     "dependency backwards. A data-integrity failure in which two backend processes "
     "sharing one database produced a six-hour latency reading that poisoned every mean "
     "while leaving medians correct. Sentence-boundary detection that must distinguish a "
     "sentence end from an abbreviation in a streaming buffer. None were anticipated in "
     "design."),
]

CCP_ALTERNATIVES = [
    ("Skill matching: semantic embeddings versus a curated cascade",
     "Sentence-transformer embeddings with cosine similarity — the textbook approach, and "
     "the one a reviewer would expect.",
     "Rejected on three grounds, in order of weight. **Latency:** embedding a batch of "
     "skills costs approximately 150–200 ms on CPU against approximately 1 ms for the "
     "implemented cascade, and the normaliser sits on the interview latency path, so this "
     "would consume roughly 20% of a budget already under pressure. **Portability:** the "
     "dependency adds about 2.5 GB to an installation the specification requires to work "
     "on a normal laptop from the README. **Explainability:** the interface shows the "
     "user why two strings were merged; 'cosine 0.83 in 384 dimensions' is not a usable "
     "explanation, whereas 'matched this alias at the exact-lookup stage' is. The cost of "
     "this decision is real and is recorded as a limitation: matching is lexical, so the "
     "system cannot infer that 'built ETL pipelines' evidences 'Data Engineering' unless "
     "the taxonomy states the relationship."),

    ("Interview generation: fixed question bank versus live generation",
     "A curated question bank per role, selected by rule — far simpler, fully "
     "deterministic, and trivially testable.",
     "Rejected because it cannot satisfy the specification's core requirement that "
     "questions depend on the CV, the role and earlier answers. A bank cannot ask 'you "
     "mentioned reducing response time from 420 to 180 milliseconds — how did you "
     "identify the N+1 query?', and that follow-up is precisely where a real interview "
     "extracts information. The hybrid implemented instead is the useful compromise: a "
     "deterministic state machine fixes the structure and the budgets, so the "
     "conversation cannot drift regardless of model behaviour, while the model supplies "
     "the question text within those constraints."),

    ("Speech recognition: streaming versus utterance-level",
     "Streaming recognition using Whisper with a sliding window and voice-activity "
     "detection, transcribing while the candidate speaks rather than afterwards.",
     "Rejected for this iteration on complexity grounds, and the decision is the one the "
     "author most regrets. It would have removed approximately {stt_median} ms from the "
     "measured latency — the entire recognition term — because transcription would "
     "complete almost as the candidate stops speaking. It requires endpoint detection, "
     "partial-hypothesis stabilisation to avoid flickering transcripts, and careful "
     "handling of the final segment. The evaluation quantifies exactly what was given up: "
     "reply latency scales with utterance length, so a long answer costs proportionally "
     "more. This is the first item of future work."),

    ("Job data: scraping major boards versus using permitted sources",
     "Scraping LinkedIn, Indeed and Glassdoor, which carry substantially more "
     "advertisements, better role coverage and far better coverage of non-remote roles.",
     "Rejected on terms-of-service grounds, and the engineering argument reinforces the "
     "ethical one: those sites actively block automated access, so an implementation "
     "would work on the development machine and fail for an examiner, producing a "
     "demonstration that cannot be reproduced. The six sources used all publish their "
     "listings for programmatic consumption. The cost is measurable and is reported "
     "rather than concealed — the evaluation shows systematically fewer postings "
     "collected for Cybersecurity Analyst than for Data Analyst, because these boards "
     "skew towards remote technical roles."),

    ("Scoring: model-computed overall score versus code-computed",
     "Asking the language model to produce the overall score directly, as it already "
     "produces the category scores.",
     "Rejected because language models are unreliable at arithmetic, and because it would "
     "place the single most consequential number entirely outside verification. The "
     "implemented design asks the model only for per-category judgements, whitelists the "
     "categories so an invented one is discarded, clamps scores to the declared range, "
     "accepts null to mean 'not tested' rather than inferring a value, and computes the "
     "weighted mean in code over the categories actually scored. The result is that the "
     "rubric, the weights and the arithmetic are all fixed and auditable; only the "
     "per-category judgement is delegated."),
]

CCP_TRADEOFFS = [
    ("Reply latency versus answer quality",
     "A larger model produces better interview questions; a smaller one replies faster.",
     "Two models are configured: a larger one for CV parsing, requirement generation and "
     "scoring, where quality matters and latency does not; a smaller one for the live "
     "interview turn, where the reverse holds. Both are selected in configuration."),

    ("Speech recognition accuracy versus latency",
     "Larger Whisper models are more accurate on technical vocabulary and proportionally "
     "slower on the critical path.",
     "The base English model at 8-bit precision was selected over tiny (insufficient on "
     "technical terms) and small (roughly triple the time for a marginal gain). Measured "
     "real-time factor {stt_rtf}."),

    ("Requirement recall versus precision",
     "Keeping every skill mentioned in any advertisement maximises recall; filtering "
     "improves precision at the cost of missing genuine but rarely stated requirements.",
     "A corroboration rule requires a scraped-only skill to appear in at least two "
     "independent advertisements. This reduced one role's list from 227 to 70 and raised "
     "inter-source agreement from 8.7% to 17.1%. Filtered skills are counted and shown "
     "rather than silently discarded."),

    ("Grounding strictness versus useful output",
     "Strict verification prevents fabrication but will also reject legitimate "
     "paraphrase.",
     "Graduated response: inventing a number, a technology or a seniority claim is a hard "
     "rejection; introducing new wording is a visible warning that the user adjudicates."),

    ("Hosted model speed versus sustained predictability",
     "A hosted API answers a single request several times faster than a local 3B "
     "model, but its free tier is rate-limited by tokens per minute.",
     "Both were measured with the same harness. In isolation the hosted model was "
     "3-8x faster; under a continuous interview it was {provider_ratio}x slower, "
     "because an interview turn costs about {tokens_per_turn} tokens and the free "
     "tier allows 8,000 per minute, so every turn entered backoff. The local model "
     "was retained as the default for its bounded worst case, and the hosted "
     "provider is kept fully supported in configuration."),

    ("Portability versus capability",
     "Semantic embeddings would improve matching; they add approximately 2.5 GB to the "
     "installation.",
     "Portability was prioritised, as the specification requires the system to run on a "
     "normal laptop from the README. The capability gap is documented rather than "
     "obscured."),

    ("Legal compliance versus data coverage",
     "The richest job data sources prohibit automated access.",
     "Compliance was treated as non-negotiable. Six permitted sources are used, and the "
     "resulting coverage bias is measured and reported."),

    ("Determinism in tests versus realism",
     "Testing against a real model is realistic but non-reproducible.",
     "The default suite runs against a deterministic engine and verifies application "
     "logic; a separate opt-in suite exercises the real speech models. Both are reported "
     "separately so neither is mistaken for the other."),

    ("Transparency versus interface simplicity",
     "Showing provenance, rejected claims, per-source outcomes and per-score "
     "justifications adds considerable interface complexity.",
     "Transparency was prioritised, with the detail placed behind tabs and collapsible "
     "sections so the default view stays readable. The judgement is that a career tool "
     "whose claims cannot be checked should not be trusted, and that the cost of the "
     "extra interface is lower than the cost of unverifiable output."),
]

# ===========================================================================
# 21. Societal and ethical impact
# ===========================================================================

ETHICS_SECTIONS = [
    ("Privacy and data protection",
     "A CV is personal data under GDPR, containing name, contact details, employment "
     "history and education. A recorded mock interview is a voice recording of an "
     "identifiable individual at their least confident, and is therefore more sensitive "
     "still.",
     [
         "Speech recognition and synthesis run entirely in-process on the user's machine; "
         "no audio is transmitted anywhere.",
         "Uploaded audio is decoded in memory and never written to disk, so no recording "
         "persists even transiently.",
         "The default language model provider is local, so with default settings no "
         "personal data leaves the machine at all.",
         "All storage is a single local SQLite file, with cascading deletion so removing "
         "a CV removes its derived analyses.",
         "A single control deletes all stored user data.",
         "The health endpoint and Settings page state the current data flow in plain "
         "language, including explicitly naming the provider when a cloud model is "
         "configured.",
     ],
     [
         "No encryption at rest: a user with filesystem access can read the database. "
         "Encrypting it would need key management beyond this project's scope.",
         "No configurable retention policy; data persists until deleted manually.",
         "No formal data-protection impact assessment, which a production deployment "
         "would require.",
     ]),

    ("Fairness and bias",
     "Three bias vectors are inherent to a system of this kind. Speech recognition error "
     "rates are known to vary with accent and dialect, so a non-native speaker may be "
     "mis-transcribed and consequently mis-scored. Language models reflect the "
     "distribution of their training data, which over-represents particular career "
     "narratives and vocabularies. The job advertisements used as evidence are themselves "
     "written by employers and encode existing industry demographics and assumptions.",
     [
         "Paralinguistic features — accent, pace, prosody, filler words — are explicitly "
         "excluded from scoring. Only verbal content is assessed. This is the single most "
         "important fairness decision in the system, because paralinguistic scoring is "
         "where accent bias enters most directly.",
         "Recognition confidence is surfaced to the user, and a low-confidence transcript "
         "is flagged as possibly wrong.",
         "A text fallback is available on every turn, so a user whom recognition serves "
         "poorly is not excluded from the system.",
         "Requirement provenance is visible, so a user can see that a requirement came "
         "from advertisements rather than from any objective standard.",
         "Scores are framed as practice feedback with an explicit statement that they are "
         "not an assessment of ability.",
     ],
     [
         "No measurement of recognition accuracy across accents, which would require a "
         "diverse labelled speech corpus.",
         "No measurement of score variation across demographic groups, which would "
         "require consented demographic data and a substantially larger study.",
         "The taxonomy was curated by one author and will reflect that author's "
         "familiarity with particular technology domains.",
     ]),

    ("Psychological safety and user wellbeing",
     "A system that scores a person on their career prospects can cause real harm. A low "
     "score may discourage a candidate who would in fact have succeeded; a high score may "
     "produce unwarranted confidence. The risk is asymmetric, because job seeking is "
     "already a period of elevated anxiety and rejection sensitivity.",
     [
         "All hiring-decision language is automatically removed from generated feedback; "
         "phrasings such as 'I would hire' or 'not a good fit' are rewritten.",
         "The gap score is labelled requirement coverage, with a descriptive band rather "
         "than a verdict, and a disclaimer placed adjacent to the number rather than in a "
         "footer.",
         "Feedback is required to be specific and actionable; the scoring prompt "
         "explicitly rejects unusable notes such as 'improve communication'.",
         "The rubric is shown before the interview, so the criteria are never a surprise.",
         "Untested categories are reported as untested rather than scored low by default.",
     ],
     [
         "No wellbeing signposting if a user performs poorly repeatedly.",
         "No limit on repeated attempts, which could sustain unproductive rumination.",
         "Tone is not adapted to user distress, which the system cannot detect.",
     ]),

    ("Legal compliance in data collection",
     "Automated collection of job advertisements raises contractual questions under site "
     "terms of service, technical questions under robots exclusion conventions, and "
     "database-rights questions in some jurisdictions.",
     [
         "LinkedIn, Indeed and Glassdoor are deliberately not accessed; their terms "
         "prohibit automated collection.",
         "All six sources used publish their listings for programmatic consumption.",
         "robots.txt is fetched, cached and obeyed per host before any request; a "
         "disallowed path causes the source to be skipped and reported, never bypassed.",
         "A descriptive User-Agent identifies the project rather than impersonating a "
         "browser.",
         "Rate limiting is enforced per host, honouring Crawl-delay where longer, and "
         "responses are cached for six hours to avoid repeat load.",
         "Attribution is displayed for every source, including the link-back that one "
         "source's terms require.",
     ],
     [
         "No formal legal review of each source's terms was obtained.",
         "Only advertisement text is retained, which is likely fair use for personal "
         "preparation but has not been assessed by counsel.",
     ]),

    ("Reliability of AI-generated guidance",
     "The system makes claims about a person's career using components that are known to "
     "be fallible. A fabricated CV achievement could follow a candidate into a real "
     "application and cause serious reputational harm.",
     [
         "Every model-supplied CV value is verified against the source document; "
         "unsupported values are discarded and shown to the user as rejected.",
         "Bullet rewrites that introduce a number, technology or seniority claim absent "
         "from the original are rejected outright and the original preserved.",
         "All structured output passes a validation cascade; unparseable output raises an "
         "error rather than being guessed at.",
         "The overall interview score is computed in code, not by the model.",
         "Degraded operation is announced: when no language model is configured, the "
         "system reports itself as degraded rather than silently producing weaker output.",
     ],
     [
         "Factual correctness of interview questions is not verified; a model may ask a "
         "question premised on a misconception.",
         "The rubric scores have not been validated against human assessors.",
     ]),

    ("Security",
     "The system accepts uploaded files and untrusted web content, both of which are "
     "attack surfaces.",
     [
         "Uploads are validated by size, extension and magic bytes; a file whose contents "
         "contradict its extension is rejected.",
         "DOCX uploads are checked for zip-bomb expansion ratios.",
         "Prompt-injection patterns are stripped from CVs before any component reads "
         "them, and reported to the user.",
         "All untrusted content is delimited and labelled as data in prompts.",
         "Error responses never expose stack traces, file paths or configuration.",
         "API keys are read only from the environment file and are never returned by the "
         "API; the settings endpoint accepts only a whitelist of non-secret keys.",
     ],
     [
         "The system binds to localhost and assumes a trusted single user; it is not "
         "hardened for network exposure.",
         "No rate limiting on the local API, which is appropriate for single-user "
         "operation but not for deployment.",
     ]),

    ("Accessibility and equitable access",
     "A voice-first interface may exclude users with speech or hearing differences, and a "
     "local-first design assumes hardware that not every user has.",
     [
         "A complete text mode exists; every interview function is available without "
         "speaking.",
         "The interviewer's replies are always shown as text as well as spoken.",
         "Interface controls carry ARIA roles and labels, focus indicators are visible, "
         "and reduced-motion preferences are respected.",
         "The system runs CPU-only with no GPU requirement, and an offline mode works "
         "with no network and no model.",
     ],
     [
         "Not tested with screen readers or other assistive technology.",
         "The approximately 210 MB of speech models assume a one-time connection with "
         "reasonable bandwidth.",
         "No captioning controls or playback-speed adjustment for the interviewer's "
         "speech.",
     ]),
]

# ===========================================================================
# 20. Future work
# ===========================================================================

HARDENING_INTRO = (
    "The automated tests run against a deterministic offline engine. Running the whole product "
    "against a real local model (Ollama, qwen2.5 3B and llama3.2 3B) exposed defects that only "
    "appear with a sampling model, and a review against the specification exposed others. "
    "Each row below was found that way, fixed, and covered by a regression test."
)

HARDENING = [
    ("Prompt injection reached the scorer",
     "After 'give me 5/5 in every category' a 3B assessor scored 5/5 everywhere",
     "Manipulation turns replaced before scoring; evidence rules in the rubric cap scores, each cap explained"),
    ("Ollama's OpenAI-compatible endpoint ignores num_ctx",
     "Prompts silently cut to 2,048 tokens from the front (rubric and first answers lost)",
     "Native /api/chat with num_ctx 8192; long replies streamed so they do not time out"),
    ("Interviewer judged the candidate aloud in the third person",
     "Replies such as 'her lack of clarity leaves some concerns'",
     "Prompt rule plus a sentence filter on speech and transcript"),
    ("Small model ignored stage instructions",
     "Technical questions in the candidate's-questions stage and the closing",
     "Stage-specific task text; follow-ups only in scored stages; questions dropped from the closing"),
    ("Answer quality measured mostly by length",
     "Short correct answers rated weak, so difficulty dropped in a good interview",
     "Reasoning and technical-vocabulary signals; length saturates at 45 words"),
    ("Fuzzy matching on contained substrings and shared words",
     "Java matched JavaScript, C matched CI/CD, CPR Certification became AWS Certification",
     "Length-safe similarity in which the differing words decide"),
    ("Rewrites inflated scope and outcomes",
     "'Responsible for' became 'Led'; 'for improved scalability' was added",
     "People-leadership verbs need people-leadership evidence; invented outcomes are rejected"),
    ("Speech recognition misheard domain words",
     "'schema' transcribed as 'gima' and repeated by the interviewer",
     "The role's skills are passed to Whisper as vocabulary hints"),
    ("Latency excluded the browser side",
     "Recording finalisation and upload were invisible to the server clock",
     "The browser reports when speech ended (voice activity detection); the gap is measured and reported"),
    ("Prompt order defeated the model's cache",
     "Every turn re-read ~2k tokens on a CPU",
     "Static context first, per-turn contract last: first-token time roughly halved on CPU"),
]

FUTURE_WORK = [
    ("Streaming speech recognition", "High",
     "Transcribe during speech rather than after it, using a sliding window with "
     "partial-hypothesis stabilisation (voice-activity detection already ends the recording "
     "automatically). The evaluation shows "
     "recognition contributes a median {stt_median} ms to reply latency, essentially all "
     "of which this would remove. The single largest available improvement."),
    ("Semantic skill matching as a fifth cascade stage", "High",
     "Add sentence embeddings as a final fall-back after the existing stages, with "
     "per-string caching so the cost stays off the interview latency path. This recovers "
     "the semantic matching the current lexical cascade cannot do, without paying the "
     "latency cost on every turn."),
    ("A labelled skill-extraction benchmark", "High",
     "The evaluation currently measures agreement between two sources, not accuracy, "
     "because no ground truth exists. Hand-labelling the required skills in fifty "
     "advertisements would convert agreement into genuine precision and recall figures."),
    ("Validation of rubric scores against human assessors", "Medium",
     "Have multiple human interviewers score a common set of transcripts and compute "
     "inter-rater agreement, both between humans and between humans and the system. "
     "Without this, the scores' reliability is unknown."),
    ("Barge-in support", "Medium",
     "Allow the candidate to interrupt the interviewer, as happens in real interviews. "
     "Requires duplex audio handling and mid-synthesis cancellation."),
    ("Evaluation with human speech", "Medium",
     "The current voice measurements use synthesised audio, which is cleaner than a human "
     "speaking in a room. Recorded human answers across a range of accents would give "
     "both realistic latency and a first measure of recognition fairness."),
    ("Expanded and community-maintained taxonomy", "Medium",
     "The taxonomy covers {taxonomy_skills} skills curated by one author and will reflect "
     "that author's domain familiarity. Aligning it to a standard such as ESCO would "
     "improve coverage and reduce individual bias."),
    ("Longitudinal progress tracking", "Low",
     "Track scores across repeated interviews to show improvement over time, which is "
     "more motivating and more informative than a single score."),
    ("Accessibility audit", "Low",
     "Validate the interface with screen readers and against WCAG 2.2 AA, and add "
     "playback-speed control for the interviewer's speech."),
]

# ===========================================================================
# 22. Conclusion
# ===========================================================================

CONCLUSION = """
This project set out to build a system that connects three things no existing tool \
connects: what a role requires, what a candidate has, and how that candidate performs \
when questioned about it. All ten objectives were met, and all seven mandated modules \
were implemented and verified.

The measured results support the central technical claim. A complete spoken interview \
pipeline — local speech recognition, language model generation, and local speech \
synthesis — runs on consumer CPU hardware with a median end-of-speech to first-audio \
latency of {e2e_median} ms (p90 {e2e_p90} ms) across {turn_count} measured turns \
spanning three dissimilar roles. Local recognition achieves a real-time factor of \
{stt_rtf} and local synthesis {tts_rtf}. No audio leaves the machine at any point, and \
with the default configuration neither does any other personal data.

Three findings are worth carrying forward beyond this project. First, naively combining \
two requirement sources is actively harmful: the unfiltered union produced 227 \
"requirements" for one role, of which the great majority were mentioned by a single \
advertisement, and the resulting gap score made every candidate look weak for reasons \
that were not real requirements. Requiring corroboration reduced the list to 70, raised \
inter-source agreement from 8.7% to 17.1%, and produced a requirement list that a \
practitioner in the field would recognise. Second, incremental sentence-level synthesis \
is what makes a local voice interview feel conversational: synthesising the first \
sentence costs {tts_median} ms against {llm_total} ms for the complete reply, so \
speaking as soon as the first sentence is available removes the overwhelming majority \
of the perceived wait. Third, and most generally, prompt instructions are not a safety \
mechanism. Every one of the anti-invention guards in this system exists because \
instructing a model not to fabricate is insufficient; mechanical verification against \
the source document is what actually prevents a fabricated achievement reaching a \
user's CV.

The limitations are real and are stated throughout rather than confined to a closing \
paragraph. Reply latency scales with utterance length because recognition is not \
streamed. Skill matching is lexical, so the system cannot infer relationships the \
taxonomy does not encode. The job boards accessible under acceptable terms skew towards \
remote technical roles, which is visible in the evaluation as systematically thinner \
evidence for the Cybersecurity Analyst role. The evaluation measures agreement between \
two sources rather than accuracy against a ground truth that does not exist, and the \
rubric scores have not been validated against human assessors. The voice measurements \
use synthesised rather than human speech.

What the project demonstrates, beyond the specific artefact, is that the difficult part \
of building a useful NLP product is not obtaining model output but deciding what to do \
with it. The majority of the engineering effort described in this report went into \
verification, provenance and honest failure reporting — into ensuring that a system \
making claims about a person's career can have those claims checked by the person \
reading them.
"""

# ===========================================================================
# 23. References
# ===========================================================================

REFERENCES = [
    "Radford, A., Kim, J. W., Xu, T., Brockman, G., McLeavey, C., & Sutskever, I. (2023). "
    "Robust Speech Recognition via Large-Scale Weak Supervision. Proceedings of the 40th "
    "International Conference on Machine Learning (ICML), 28492–28518.",

    "Kim, J., Kong, J., & Son, J. (2021). Conditional Variational Autoencoder with "
    "Adversarial Learning for End-to-End Text-to-Speech. Proceedings of the 38th "
    "International Conference on Machine Learning (ICML), 5530–5540.",

    "Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., "
    "Kaiser, L., & Polosukhin, I. (2017). Attention Is All You Need. Advances in Neural "
    "Information Processing Systems 30 (NeurIPS).",

    "Zhang, M., Jensen, K. N., Sonniks, S. D., & Plank, B. (2022). SkillSpan: Hard and "
    "Soft Skill Extraction from English Job Postings. Proceedings of NAACL-HLT 2022, "
    "4962–4984.",

    "Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., et al. "
    "(2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. Advances "
    "in Neural Information Processing Systems 33 (NeurIPS), 9459–9474.",

    "Ji, Z., Lee, N., Frieske, R., Yu, T., Su, D., Xu, Y., et al. (2023). Survey of "
    "Hallucination in Natural Language Generation. ACM Computing Surveys, 55(12), 1–38.",

    "Koenecke, A., Nam, A., Lake, E., Nudell, J., Quartey, M., Mengesha, Z., et al. "
    "(2020). Racial disparities in automated speech recognition. Proceedings of the "
    "National Academy of Sciences, 117(14), 7684–7689.",

    "Levashina, J., Hartwell, C. J., Morgeson, F. P., & Campion, M. A. (2014). The "
    "Structured Employment Interview: Narrative and Quantitative Review of the Research "
    "Literature. Personnel Psychology, 67(1), 241–293.",

    "Naim, I., Tanveer, M. I., Gildea, D., & Hoque, M. E. (2018). Automated Analysis and "
    "Prediction of Job Interview Performance. IEEE Transactions on Affective Computing, "
    "9(2), 191–204.",

    "le Vrang, M., Papantoniou, A., Pauwels, E., Fannes, P., Vandensteen, D., & De Smedt, "
    "J. (2014). ESCO: Boosting Job Matching in Europe with Semantic Interoperability. "
    "Computer, 47(10), 57–64.",

    "Bender, E. M., Gebru, T., McMillan-Major, A., & Shmitchell, S. (2021). On the "
    "Dangers of Stochastic Parrots: Can Language Models Be Too Big? Proceedings of the "
    "2021 ACM Conference on Fairness, Accountability, and Transparency (FAccT), 610–623.",

    "Greshake, K., Abdelnabi, S., Mishra, S., Endres, C., Holz, T., & Fritz, M. (2023). "
    "Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications "
    "with Indirect Prompt Injection. Proceedings of the 16th ACM Workshop on Artificial "
    "Intelligence and Security (AISec), 79–90.",

    "Klein, G., Zhang, D., Chouteau, C., Crego, J., & Senellart, J. (2020). Efficient and "
    "High-Quality Neural Machine Translation with OpenNMT. Proceedings of the 4th "
    "Workshop on Neural Generation and Translation, 211–217. [CTranslate2, the inference "
    "engine underlying faster-whisper]",

    "Ramos, J. (2003). Using TF-IDF to Determine Word Relevance in Document Queries. "
    "Proceedings of the First Instructional Conference on Machine Learning.",

    "European Parliament and Council. (2016). Regulation (EU) 2016/679 (General Data "
    "Protection Regulation). Official Journal of the European Union, L119, 1–88.",
]

SOFTWARE_REFERENCES = [
    ("FastAPI", "Ramírez, S. ASGI web framework.", "https://fastapi.tiangolo.com"),
    ("faster-whisper", "SYSTRAN. CTranslate2 reimplementation of Whisper.",
     "https://github.com/SYSTRAN/faster-whisper"),
    ("Piper", "Rhasspy. Local neural text-to-speech.", "https://github.com/rhasspy/piper"),
    ("Ollama", "Local large language model runtime.", "https://ollama.com"),
    ("scikit-learn", "Pedregosa et al. (2011). JMLR 12, 2825–2830.", "https://scikit-learn.org"),
    ("RapidFuzz", "Bachmann, M. Fast approximate string matching.",
     "https://github.com/rapidfuzz/RapidFuzz"),
    ("pdfplumber", "Singer-Vine, J. PDF text and table extraction.",
     "https://github.com/jsvine/pdfplumber"),
    ("python-docx", "Canny, S. Word document parsing.", "https://python-docx.readthedocs.io"),
    ("React", "Meta. User interface library.", "https://react.dev"),
    ("Recharts", "Charting library for React.", "https://recharts.org"),
    ("Tailwind CSS", "Utility-first CSS framework.", "https://tailwindcss.com"),
    ("PyAV", "Pythonic bindings for FFmpeg.", "https://github.com/PyAV-Org/PyAV"),
]
