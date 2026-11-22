# Career Intelligence Platform

A job-preparation platform that reads your CV, works out what a role actually
requires, shows you the gaps, strengthens your CV bullet points, and then runs a
**spoken mock interview** with fully local speech recognition and speech
synthesis — followed by scored feedback against a rubric published before the
interview starts.

Built for the **Natural Language Processing** course project (Fall 2026),
**Project 2: Career Intelligence Platform**.

---

## Group members

| Name | Registration number |
|---|---|
| **Hussnain Haider** | i230695 |
| **Akbar Hussain** | i233094 |

| | |
|---|---|
| **University** | FAST-NUCES, Islamabad |
| **Department** | Software Engineering |
| **Course** | Natural Language Processing — Fall 2026 |
| **Section** | B |
| **Instructor** | Asif Muhammad Malik |

---

## Which project, which models, what runs locally

| | |
|---|---|
| **Project built** | Project 2 — Career Intelligence Platform |
| **Speech recognition** | **LOCAL** — `faster-whisper` (CTranslate2 Whisper), `base.en`, int8 on CPU |
| **Text to speech** | **LOCAL** — `Piper` neural TTS, `en_US-amy-medium` ONNX voice |
| **Language model** | Configurable. Default is **Ollama on localhost** (`qwen2.5:3b-instruct-q4_K_M` for analysis, `llama3.2:3b` for live interview turns). Anthropic / OpenAI / Gemini / Groq APIs are also supported, as is a no-LLM offline mode. |
| **Job postings** | Six public job boards, fetched live (Remotive, Jobicy, Arbeitnow, WeWorkRemotely RSS, Himalayas, Remote OK) |
| **Database** | SQLite, one local file |
| **Frontend** | React 18 + TypeScript + Vite + Tailwind CSS + Recharts |
| **Backend** | Python 3.12 + FastAPI + Uvicorn |

**No audio ever leaves your machine.** The browser records your answer, posts it
to your own backend, Whisper transcribes it in-process, and the temporary file is
deleted immediately. Piper speaks the replies locally too. With
`LLM_PROVIDER=ollama` or `offline`, *nothing at all* is sent to any external
service except the job-board requests.

---

## Architecture

Full diagrams: **[docs/diagrams/architecture.md](docs/diagrams/architecture.md)**
(component architecture, the voice-turn sequence, Module 2 fusion, the
normalisation cascade, the interview stage machine, the anti-hallucination
defences, and the data model).

```
┌──────────────────────────────────────────────────────────────────────────┐
│ BROWSER  React + TypeScript + Vite + Tailwind                            │
│  8 pages · MediaRecorder (+ live input meter) · ordered audio queue       │
│  Server-Sent Events reader for streamed text and audio                   │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │  /api/*   (Vite proxies to :8000)
┌───────────────────────────────▼──────────────────────────────────────────┐
│ BACKEND  FastAPI on 127.0.0.1:8000   (44 endpoints)                      │
│                                                                          │
│  ① CV parser          PDF/DOCX → structured profile, grounding-filtered  │
│  ② Job collection     6 live sources  +  LLM generation  →  fused list   │
│  ③ Match & gap        weighted coverage, severity-ranked gaps            │
│  ④ CV improvement     rewrite bullets, invention guards reject inventions│
│  ⑤ Voice interview    6 stages, adaptive, streamed text + sentence audio │
│  ⑥ Rubric scoring     fixed rubric, every score justified                │
│  ⑦ Performance        real end-of-speech → first-audio latency           │
│                                                                          │
│  Shared: skill taxonomy (176 skills / 851 aliases) · 4-stage normaliser  │
│          json_guard (JSON repair + grounding) · all prompts in one file  │
│                                                                          │
│  LOCAL MODELS ─ faster-whisper (STT) · Piper (TTS) · PyAV decode         │
│  STORAGE ────── SQLite (9 tables) · scrape cache (6 h TTL)               │
└───────────────┬──────────────────────────────────┬───────────────────────┘
                │                                  │
      ┌─────────▼─────────┐              ┌─────────▼──────────┐
      │ Ollama (localhost)│   or cloud   │ Public job boards  │
      │ or an LLM API     │              │ robots.txt obeyed  │
      └───────────────────┘              └────────────────────┘
```

---

## Features

### ① CV parser
Upload a PDF, Word (`.docx`) or plain-text CV. Extracts name, contact details,
skills, work experience with bullet points, education with grades, projects,
certifications, languages and job titles.

A **hybrid** design: deterministic rules decide what *exists*, and the language
model may only make it *tidier*. Every value the model supplies is checked
against the document, and anything unsupported is dropped and shown to you in a
"claims rejected by the grounding filter" table. It handles malformed files,
empty uploads, wrong extensions, encrypted PDFs, zip bombs, image-only (scanned)
PDFs and prompt injection hidden inside a CV.

### ② Job posting collection + LLM skill generation
Enter **any** job title. The platform does both halves the specification
requires:

- **Live collection** from six job boards that publish their listings for
  programmatic use. `robots.txt` is fetched, cached and obeyed per host; requests
  are rate-limited; responses are cached for 6 hours; every source's outcome
  (including failures) is reported honestly.
- **LLM generation** of the skills, tools, qualifications and expectations for
  the role, independently of the adverts.

The two are then **fused** into one normalised list where every requirement
carries its provenance (*job adverts only* / *LLM only* / *both agree*) and an
importance score. Uncorroborated single-advert mentions are filtered out and
counted, because carrying that long tail would make the gap score meaningless.

**"React", "ReactJS" and "React.js" become one skill**, via a four-stage
cascade: curated alias index → fuzzy token matching → TF-IDF character n-gram
cosine → clustering of unknown terms. Every merge records which stage decided it.
There is a live playground for this on the Settings page.

### ③ Match and gap analysis
Classifies every requirement as **matched**, **partially matched** (a related
skill on your CV implies it, or the foundation is there but the specific
technology is not) or **missing**, with the evidence for each decision. Gaps are
ranked critical → low. The score is a *weighted* coverage figure, so missing one
core requirement hurts more than missing three optional tools — and it is
labelled "requirement coverage", never a prediction of being hired.

### ④ CV improvement studio
Rewrites weak bullet points, shown side by side with the original, with
accept / reject / copy per bullet. Four automatic checks run **before you see
the rewrite**:

| Check | Rule | On failure |
|---|---|---|
| Numbers | every number in the rewrite must be in your original | rewrite **rejected** |
| Technologies | every technology must appear in your bullet or CV | rewrite **rejected** |
| Scope | "led"/"owned"/"architected" need matching evidence | rewrite **rejected** |
| New wording | unexplained new content words are counted | warning shown |

A rejected rewrite is displayed as rejected with the reason — the guard working
is a feature, not something to hide.

### ⑤ Structured voice mock interview
A spoken interview following the six stages of a real one: **introduction →
background → technical → behavioural → your questions → closing**.

- Questions are grounded in *your* CV and *this* role — never generic.
- Follow-up questions dig into what you actually just said.
- Difficulty adapts up or down one band based on how you are answering.
- The interviewer's reply is **streamed**, and each finished sentence is spoken
  immediately, so audio starts before the full reply exists.
- A live microphone meter shows that recording is really working.
- Text fallback is always one click away if the microphone or model fails.

### ⑥ Scoring and feedback
Scored against a rubric **fixed in source control before any interview runs**
([`rubric.py`](backend/app/services/interview/rubric.py)) and shown to you
before you start: six categories, 1–5 scale with written descriptors, and
weights that change with difficulty. Every score carries a justification and,
where available, a quote. The overall score is computed in Python as a weighted
mean — not asked of the model. Untested categories are reported as untested, not
guessed. Hiring-decision language is stripped from the output.

### ⑦ Performance report
Measures, per turn, with a high-resolution timer in the real request path:
speech-recognition time, end-of-speech to first text token, first-sentence
synthesis time, **end of speech to first audio** (the headline), and total turn
time. Reported as median, mean and p90 — a mean alone hides the tail. Broken
down per job role, exportable as JSON and CSV.

---

## Prerequisites

| | Minimum | Notes |
|---|---|---|
| **Python** | 3.11+ | 3.12 recommended. `python --version` |
| **Node.js** | 18+ | 20/22 recommended. `node --version` |
| **RAM** | 8 GB | 16 GB if you run a local LLM |
| **Disk** | ~2 GB free | ~1 GB of Python packages, ~210 MB of speech models |
| **Microphone** | any | Only for the voice interview; text mode needs none |
| **OS** | Windows / macOS / Linux | Developed and measured on Windows 11 |

No GPU is required. Everything in this project runs on CPU.

> **Browser note:** use a recent Chrome, Edge or Firefox, and open the app at
> `http://localhost:5173`. Microphone access requires `localhost` — it will not
> work from a `file://` page.

---

## Installation

### 1. Get the code

```bash
git clone https://github.com/HussnainShah72/Carrier-Intelligence-Platform.git
cd Carrier-Intelligence-Platform
```

### 2. Backend

```bash
# from the project root
python -m venv .venv

# activate it
.venv\Scripts\activate        # Windows (cmd)
.venv\Scripts\Activate.ps1    # Windows (PowerShell)
source .venv/bin/activate     # macOS / Linux

pip install --upgrade pip
pip install -r backend/requirements.txt
# faster alternative if you have uv:  uv pip install -r backend/requirements.txt
```

This installs about 95 packages (~1 GB), including `faster-whisper` and
`piper-tts` with their native runtimes. It takes a few minutes.

`backend/requirements.lock.txt` records the exact versions the submitted test and
evaluation runs were produced with, if you need to reproduce them precisely.

### 3. Configuration

```bash
cd backend
cp .env.example .env          # Windows cmd:        copy .env.example .env
                              # Windows PowerShell: Copy-Item .env.example .env
cd ..
```

**The defaults need no editing, but they expect Ollama to be running** with the
two models below pulled (see *API configuration*). If you do not want to install
Ollama, set `LLM_PROVIDER=offline` (no model, lower quality) or a cloud provider.
The backend checks Ollama at start-up and the Settings page shows what is missing.

### 4. Local speech models

```bash
python scripts/download_speech_models.py
```

Downloads the Piper voice (~63 MB) into `backend/data/models/piper/`. The
Whisper model (~145 MB for `base.en`) downloads itself on first use into
`backend/data/models/`.

Both are one-time downloads. After that the speech pipeline is fully offline.

### 5. Frontend

```bash
cd frontend
npm install
cd ..
```

---

## API configuration (choosing a language model)

Edit `LLM_PROVIDER` in `backend/.env`. Pick **one**:

### Option A — local model via Ollama (the default, no API key)

Nothing leaves your machine. Install [Ollama](https://ollama.com), then:

```bash
ollama pull qwen2.5:3b-instruct-q4_K_M   # analysis, scoring  (~1.8 GB)
ollama pull llama3.2:3b                  # live interview turns (~1.9 GB)
```

```ini
LLM_PROVIDER=ollama
```

Two models is a deliberate trade-off: the larger one follows the JSON schemas
more reliably, the smaller one keeps the interview responsive.

### Option B — a cloud API (better quality, needs a key)

```ini
LLM_PROVIDER=anthropic        # or openai / gemini / groq
ANTHROPIC_API_KEY=sk-ant-...  # only the key matching your provider
```

Note what this means for privacy: your CV text, role titles and interview
answers are sent to that provider for analysis. Speech still stays local.

### Option C — no language model at all

```ini
LLM_PROVIDER=offline
```

A deterministic rule-based engine runs instead, so every screen still works and
the test suite is reproducible. Quality is visibly lower and the app says so
with a banner. This is what the automated tests use.

> **Never commit your `.env`.** It is already in `.gitignore`. Only
> `.env.example` belongs in version control.

---

## Running the application

Two terminals, both from the project root.

**Terminal 1 — backend**

```bash
.venv\Scripts\activate          # or: source .venv/bin/activate
cd backend
uvicorn app.main:app --reload --port 8000
```

Wait for:

```
Starting Career Intelligence Platform
Database ready at ...
LLM provider: ollama (model: qwen2.5:3b-instruct-q4_K_M, fast: llama3.2:3b)
Speech recognition: faster-whisper installed=True enabled=True model=base.en
Text-to-speech: active engine=piper piper_voices=1
API ready on /api (docs at /docs)
```

**Terminal 2 — frontend**

```bash
cd frontend
npm run dev
```

Then open **<http://localhost:5173>**.

| URL | What it is |
|---|---|
| <http://localhost:5173> | The application |
| <http://127.0.0.1:8000/docs> | Interactive API documentation (Swagger) |
| <http://127.0.0.1:8000/api/system/health> | Machine-readable health of every component |

---

## How to use the application

The sidebar is ordered as the workflow, and the Dashboard tracks your progress
through it.

### 1. Upload your CV — *CV Analysis*
Drop in a PDF or `.docx`. You will see the extracted profile, which sections
were recognised, any parsing warnings, and anything the grounding filter
rejected. "Extracted text" shows exactly what the parser read — if something is
missing from your profile it is usually missing there too, which points at the
document rather than the parser.

### 2. Analyse a target role — *Job Role Analysis*
Type any job title and press **Analyse role**. Takes 10–60 seconds (six boards
queried in parallel, plus the LLM). Then explore:

- **Requirements** — the fused list; filter by *essential*, *both agree*,
  *adverts only*, *LLM only*
- **Job postings** — the actual live adverts collected, with links
- **Source report** — exactly what each source returned, failures included
- **Normalisation** — which spellings were merged, and what was dropped as
  uncorroborated

### 3. See your gaps — *Skill Gap*
Pick your CV and the role, press **Run gap analysis**. You get a weighted
coverage score, per-category charts, severity-ranked gaps with the evidence for
each decision, your extra skills, and a learning plan.

### 4. Strengthen your CV — *CV Improvement*
Your bullet points are ranked weakest-first. Select up to 12 and press
**Improve**. Compare side by side, accept or reject each one, and export the
result.

### 5. Sit the interview — *Mock Interview*

1. Enter the role, pick difficulty, choose your CV and role analysis.
2. Keep **Spoken interview** selected.
3. Press **Start**. The speech models load first (a few seconds) — deliberately
   before the clock starts, so model loading does not distort the measured
   latency.
4. Press the microphone, speak your answer, press it again to send.
5. Watch the input meter while you speak: if it does not move, your microphone
   is muted or the wrong device is selected.
6. The interviewer's reply streams in as text and starts speaking after the
   first sentence.
7. Continue through all six stages, or press **End interview** at any point.

**Use headphones** — otherwise your microphone picks up the interviewer's voice.
If recognition mishears you, press **Type instead** for that turn and carry on.

### 6. Read your feedback — *Interview Results*
Rubric breakdown with a justification and quote per category, strengths and
weaknesses, answers worth rehearsing with the shape of a stronger answer, a
preparation plan, the full transcript, and this interview's measured latency.

### 7. Check the numbers — *Performance*
Aggregate latency across every interview, per pipeline stage and per job role,
exportable as JSON or CSV.

### 8. Configure and verify — *Settings*
Switch model provider, change the Whisper size or Piper voice, see which API
keys are present (never their values), run a **system check** that probes the
LLM and every job source live, use the **skill normalisation playground**, and
**delete all your data**.

---

## Testing

```bash
cd backend

pytest -m "not live"      # 403 tests, no model or network needed  (~90 s)
pytest -m live            # 5 tests that need the real models + network
pytest                    # everything
pytest -v                 # verbose
pytest --cov=app          # with coverage (needs: pip install pytest-cov)
```

The default suite runs against the **offline deterministic engine**, so it tests
the application's logic rather than a sampling model's mood, and it passes
identically on every run. The `live` tests are opt-in because they need the
downloaded Whisper and Piper models and live internet access; the headline one
synthesises a sentence with local TTS, transcribes it with local STT, and checks
the content words survive.

Full test documentation, including every test case with its expected and actual
result: **[docs/TEST_REPORT.md](docs/TEST_REPORT.md)**

### End-to-end evaluation

```bash
# with the backend running on port 8000, from the project root
python scripts/run_evaluation.py --mode voice            # three roles, voice
python scripts/run_evaluation.py --mode text             # faster, no speech
python scripts/run_evaluation.py --roles "Data Analyst"  # one role
python scripts/run_evaluation.py --trials 2              # repeat for stability
```

Drives the real HTTP API exactly as the browser does, across three deliberately
different roles, and writes `evaluation/results/evaluation_runs.json` and
`evaluation_summary.json`. In `--mode voice` the scripted answers are turned into
real audio by the local TTS engine and posted to the voice endpoint, so the
measured latency includes genuine local speech recognition.

Results and discussion: **[evaluation/EVALUATION.md](evaluation/EVALUATION.md)**

### Regenerating the synthetic test CVs

```bash
python scripts/make_sample_cvs.py
```

Every CV in `evaluation/sample_cvs/` is **synthetic** — fictional people written
for testing, each marked as such in its own text. No real CV is in this
repository.

---

## Project structure

```
Carrier-Intelligence-Platform/
├── README.md                        this file
├── Project.pdf                      the course specification
│
├── backend/
│   ├── .env.example                 configuration template (copy to .env)
│   ├── requirements.txt             dependencies
│   ├── requirements.lock.txt        exact versions used for the submitted runs
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py                  FastAPI app, error handling, routing
│   │   ├── core/
│   │   │   ├── config.py            every setting, all overridable from .env
│   │   │   ├── db.py                SQLite schema + helpers
│   │   │   ├── errors.py            typed errors with user-safe messages
│   │   │   └── logging_setup.py
│   │   ├── schemas/models.py        request validation
│   │   ├── api/                     routes_cv · routes_jobs · routes_gap
│   │   │                            routes_interview · routes_metrics · routes_system
│   │   └── services/
│   │       ├── cv/                  ① extractor.py · parser.py
│   │       ├── jobs/                ② http.py · sources.py · collector.py
│   │       ├── skills/              ②③ taxonomy · text_norm · normalizer · matcher
│   │       ├── improve/             ④ bullets.py  (invention guards)
│   │       ├── interview/           ⑤⑥ stages · answer_analysis · engine
│   │       │                             rubric · scorer
│   │       ├── speech/              ⑤ stt.py · tts.py · audio_decode.py  (LOCAL)
│   │       ├── metrics/             ⑦ recorder.py
│   │       └── llm/                 client · prompts · json_guard · offline_engine
│   ├── tests/                       408 tests
│   └── data/                        created at runtime — database, models, logs
│
├── frontend/
│   ├── src/
│   │   ├── main.tsx                 routing
│   │   ├── index.css                design tokens (light + dark)
│   │   ├── components/              Layout.tsx · ui.tsx
│   │   ├── hooks/                   useAsync.ts · useVoice.ts
│   │   ├── lib/                     api.ts · types.ts · format.ts · store.tsx
│   │   └── pages/                   the 8 pages
│   └── package.json
│
├── docs/
│   ├── diagrams/architecture.md     all system diagrams
│   ├── API.md                       endpoint reference
│   ├── TECHNICAL.md                 design decisions and algorithms
│   ├── TEST_REPORT.md               every test case + result
│   ├── TRACEABILITY.md              requirement → implementation → test
│   └── VIVA_PREPARATION.md          how to explain and demonstrate this project
│
├── evaluation/
│   ├── EVALUATION.md                results, limitations, failures
│   ├── sample_cvs/                  synthetic test CVs (all clearly marked)
│   └── results/                     raw JSON from the evaluation runs
│
├── report/                          the academic report (DOCX + PDF)
├── screenshots/                      screenshots of the running application
└── scripts/
    ├── make_sample_cvs.py
    ├── download_speech_models.py
    ├── run_evaluation.py
    └── capture_screenshots.py
```

---

## Troubleshooting

### "Could not reach the backend"
The frontend is running but the backend is not. Check Terminal 1. The sidebar
shows the exact command.

### Port 8000 or 5173 already in use
```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <pid> /F

# macOS / Linux
lsof -ti:8000 | xargs kill -9
```
Or use another port: `uvicorn app.main:app --port 8001` (then update
`CORS_ORIGINS` in `.env` and the proxy target in `frontend/vite.config.ts`).

### The microphone does not work
1. Open the app at `http://localhost:5173`, not a `file://` path.
2. Allow microphone access via the icon in the browser's address bar.
3. Watch the input meter while speaking — no movement means a muted or wrong
   device.
4. Check **Settings → system check**.
5. Use **Type instead** to continue; the interview works fully in text mode.

### "The local speech recognition model could not be loaded"
The first run downloads Whisper (~145 MB) and needs internet access once. If it
failed, check your connection and restart the backend, or set a smaller model:
`STT_MODEL_SIZE=tiny.en`.

### The interviewer's voice sounds robotic
That is the operating-system fallback voice, meaning the Piper model was not
found. Run `python scripts/download_speech_models.py` and check
**Settings → Local speech engines**.

### Replies are slow
- First turn is always slowest (models load into RAM). The app warms them up
  before the interview starts, so use **Start interview** rather than measuring
  a cold first turn.
- Use a smaller LLM for the interview: `LLM_FAST_MODEL=llama3.2:3b`.
- Use a smaller Whisper model: `STT_MODEL_SIZE=tiny.en`.
- Shorter answers transcribe faster — latency scales with how long you speak.
- A cloud provider with `LLM_PROVIDER=groq` is usually the fastest option.
- **Old or low-power CPUs are too slow for a local 3B model.** Measured on a
  2-core 2016 laptop (i7-6600U, no GPU): ~23 prompt tokens/s and ~5 output
  tokens/s, i.e. about a minute per interview reply and several minutes per role
  analysis. On such a machine use `LLM_PROVIDER=groq` for the live demo; speech
  recognition and TTS stay local either way.

### The LLM stops responding mid-session
If you started Ollama from its desktop app and the app is closed or restarts for
an update, the Ollama server stops with it. Run `ollama serve` in a terminal
instead for a long session or a demo. The Settings page and
`/api/system/health` report "Ollama is not reachable" when this happens.

### "No live job postings could be collected"
Check **Settings → system check** for per-source reachability. Causes: no
internet, a firewall, a source being temporarily down, or a genuinely unusual
job title. The analysis still completes using the LLM alone, and says so.

### Role analysis is slow
Normal: six boards plus an LLM call. Repeat analyses are faster (6-hour cache).
Clear the cache from Settings if you want fresh data.

### "The language model could not be reached"
- **Ollama:** is it running? `ollama list`. Have you pulled the model?
- **Cloud:** is the key in `backend/.env`, and is `LLM_PROVIDER` set to that
  provider? Restart the backend after editing `.env`.
- Set `LLM_PROVIDER=offline` to keep working without a model.

### A scanned PDF is rejected
Deliberate. The platform does not run OCR, so a PDF with no text layer cannot be
parsed. Export a text-based PDF or upload the `.docx`.

### Tests fail with "Synthetic CVs are missing"
```bash
python scripts/make_sample_cvs.py
```

### `npm install` fails
Node 18 or newer is required (`node --version`). Then:
```bash
rm -rf node_modules package-lock.json   # Windows: rmdir /s /q node_modules
npm install
```

---

## Privacy

| What | Where it goes |
|---|---|
| **Your CV** | Stored only in the local SQLite file. Never uploaded anywhere by this project. |
| **Your voice** | Transcribed in-process by local Whisper. The temporary file is deleted immediately. No recording is kept. |
| **Interviewer's voice** | Generated locally by Piper. |
| **Interview transcripts** | Local SQLite only. |
| **CV text and answers** | Sent to your chosen LLM provider for analysis — **unless** you use `ollama` or `offline`, in which case nothing is sent. |
| **Job boards** | Only the job title you typed is sent, as a search query. No personal data. |

**Delete everything:** Settings → Storage → *Delete all my data*. This removes
every CV, analysis, transcript, rewrite and measurement from the database.
Downloaded speech models are kept — they contain no personal data.

The health endpoint states the current privacy posture in plain language:
<http://127.0.0.1:8000/api/system/health>

---

## Known limitations

Stated here rather than discovered by a marker. Measured evidence for each is in
[evaluation/EVALUATION.md](evaluation/EVALUATION.md).

1. **The job boards skew remote and technical.** All six publish their listings
   for programmatic use, which is why they were chosen over LinkedIn, Indeed and
   Glassdoor, whose terms of service prohibit automated access. Coverage for
   local, non-technical or highly regulated roles is therefore thinner — visible
   in the evaluation as fewer postings for Cybersecurity Analyst than for Data
   Analyst.
2. **Reply latency scales with answer length.** Whisper transcribes the whole
   utterance after speech ends, so a 60-second answer costs roughly twice the
   recognition time of a 30-second one. Streaming (chunked) recognition would fix
   this and is not implemented.
3. **No OCR.** Scanned, image-only PDFs are rejected rather than mis-parsed.
4. **The rubric score is model-dependent.** A small local model scores more
   coarsely than a large cloud one. The rubric, weights and arithmetic are fixed
   in code, but the judgement is not.
5. **Skill matching is lexical, not semantic.** It does not know that "built
   ETL pipelines" evidences "Data Engineering" unless the taxonomy says so.
6. **Evaluation answers are scripted and synthesised, not human.** The voice
   measurements use real local STT on real audio, but that audio is TTS output,
   which is cleaner than human speech in a real room.
7. **Single-user, local-only.** No authentication, no multi-user support, no
   deployment hardening. It is a course project, not a product.

---

## Academic integrity

- All application code in `backend/` and `frontend/` was written for this
  project.
- Generative AI tools were used during development, as the course permits. The
  prompts the *application itself* sends are all in
  [`backend/app/services/llm/prompts.py`](backend/app/services/llm/prompts.py),
  and the development prompts are in
  [docs/AI_USAGE.md](docs/AI_USAGE.md).
- Every CV in `evaluation/sample_cvs/` is synthetic and marked as such. No real
  person's CV is included.
- Every number in the evaluation and the report was produced by
  `scripts/run_evaluation.py` on this machine. Nothing is estimated or invented.
  Where something could not be measured, it says so.
- Job postings are collected from sources that permit it, with `robots.txt`
  obeyed and attribution given. LinkedIn, Indeed and Glassdoor are deliberately
  **not** scraped.

---

## Attribution for job data

Job postings are collected from, and attributed to:
[Remotive](https://remotive.com) · [Jobicy](https://jobicy.com) ·
[Arbeitnow](https://www.arbeitnow.com) ·
[WeWorkRemotely](https://weworkremotely.com) ·
[Himalayas](https://himalayas.app) · [Remote OK](https://remoteok.com)

Remote OK asks for a link back, which the Job Role Analysis page provides for
every posting it supplies.
