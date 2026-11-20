"""
End-to-end evaluation harness.

Drives the running backend over HTTP exactly as the browser does, for three
deliberately different job roles, and records what actually happened. Every
number in `evaluation/results/` comes from this script -- nothing is typed in by
hand.

For each role it:
  1. uploads the matching synthetic CV and parses it
  2. analyses the role (live job postings + LLM generation + fusion)
  3. compares the generated skills against the scraped evidence
  4. runs the skill gap analysis
  5. improves a set of CV bullet points and records what the guard blocked
  6. conducts a full mock interview, answering with scripted candidate replies
  7. scores the interview against the rubric
  8. records per-turn latency

Usage
-----
    # start the backend first:
    #   cd backend && uvicorn app.main:app --port 8000

    python scripts/run_evaluation.py                 # all three roles
    python scripts/run_evaluation.py --roles "Data Analyst"
    python scripts/run_evaluation.py --mode voice    # synthesise spoken answers
    python scripts/run_evaluation.py --trials 2      # repeat for stability

`--mode voice` is the important one for the performance report: it turns each
scripted answer into real audio with the local TTS engine and posts it to the
voice endpoint, so the measured latency includes genuine local speech
recognition rather than skipping it.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

import _console

# Model output contains typographic Unicode that a redirected Windows stdout
# (cp1252) cannot encode.  Install this before anything is printed: an
# unattended run must not die on a curly quote.  See scripts/_console.py.
_console.install()

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "evaluation" / "results"
CV_DIR = ROOT / "evaluation" / "sample_cvs"

BASE_URL = "http://127.0.0.1:8000/api"
TIMEOUT = httpx.Timeout(300.0, connect=10.0)


# ---------------------------------------------------------------------------
# Scripted candidate answers
# ---------------------------------------------------------------------------
# These are written to be *realistic rather than perfect*: a mixture of strong,
# specific answers and deliberately thin ones, so the adaptive follow-up logic
# and the rubric scoring are both genuinely exercised. The interview is adaptive,
# so answers are selected by stage rather than by a fixed script position.

ANSWERS: dict[str, dict[str, list[str]]] = {
    "Software Engineer": {
        "introduction": [
            "Thanks for having me. I'm a backend-focused software engineer with about four "
            "years of experience. Most recently I've been at Northfield Logistics working on "
            "their shipment tracking API, which three internal teams depend on. Before that I "
            "was at Brightline Software doing more full-stack work with React on the front end.",
        ],
        "background": [
            "The piece I'm most proud of is the caching work on the tracking API. The median "
            "response time was about four hundred and twenty milliseconds and the operations "
            "team were complaining the dashboard felt sluggish. I profiled it and found two "
            "problems: we had an N plus one query pattern loading shipment events, and we were "
            "recomputing the same route lookups on every request. I fixed the query with a join "
            "and added Redis caching with a short TTL, and we got it down to about a hundred "
            "and eighty milliseconds.",
            "I personally owned the migration of the shipment service. I wrote the FastAPI "
            "endpoints, defined the Pydantic schemas, and set up the integration tests. The "
            "trickiest part was that the old Django views had a lot of implicit behaviour, so I "
            "ended up writing tests against the old endpoints first to capture what they "
            "actually returned before I changed anything.",
            "I set up the GitHub Actions pipeline. It runs pytest and the linter on every pull "
            "request, and it blocks a merge if coverage on the changed files drops. Getting the "
            "team to accept that gate took longer than building it.",
        ],
        "technical": [
            "For caching I think about three things: how stale the data is allowed to be, how "
            "expensive it is to recompute, and how you invalidate it. For the route lookups the "
            "data changed maybe daily, so a thirty minute TTL was fine and I didn't need "
            "explicit invalidation. For the shipment status I wouldn't cache at all, because a "
            "customer seeing a stale delivery status is a real problem.",
            "An N plus one is when you load a list and then fire one more query per item in "
            "that list. So loading fifty shipments and then fifty separate queries for their "
            "events. You fix it either with a join, or with a select-in style batched load. The "
            "reason it hides is that it looks fine on your dev database with ten rows.",
            "I'd test it at three levels. Unit tests for the pure logic, so the slot assignment "
            "heuristic gets tested on its own with edge cases like a full warehouse. Then "
            "integration tests that hit the real endpoint against a test database. Then one or "
            "two end-to-end checks on the happy path. I try not to write many of the last kind "
            "because they're slow and they break for reasons that aren't bugs.",
            "I'd reach for a message queue when the work doesn't need to happen inside the "
            "request. Sending a notification email, or regenerating a report. The trade-off is "
            "that you've added a component that can fail and a new failure mode where the "
            "message is accepted but never processed, so you need dead letter handling and some "
            "way to see the queue depth.",
            "Honestly I haven't used Kubernetes in production. I've containerised services with "
            "Docker and deployed them with Compose, and I understand roughly what an "
            "orchestrator gives you, but I'd be learning on the job.",
            "For a database index I'd look at what the query actually filters and sorts on. If "
            "we're always querying shipments by customer and then ordering by date, a composite "
            "index on those two columns in that order helps, whereas two separate indexes "
            "mostly don't. The cost is write throughput and storage, so I wouldn't add one "
            "speculatively.",
        ],
        "behavioural": [
            "I disagreed with a colleague about whether to rewrite the billing module or patch "
            "it. He wanted a rewrite; I thought the risk was too high before our busiest month. "
            "We ended up writing down what we each thought would break, and the list made it "
            "fairly obvious that a rewrite in that window was a bad idea. We patched it and did "
            "the rewrite in January.",
            "I deployed a change that broke the tracking page for about twenty minutes. I'd "
            "changed a response field name and missed that the frontend read it. I rolled it "
            "back first, then added a contract test so the frontend and backend schemas get "
            "checked against each other in CI. The lesson was that I'd tested my service in "
            "isolation and not the integration.",
            "When everything is urgent I try to separate what's actually time-sensitive from "
            "what's just been asked loudly. I'll go back to whoever asked and say what I can do "
            "today and what slips, rather than quietly doing it all badly.",
        ],
        "candidate_questions": [
            "Yes, two things. How is the team structured, and how much of the work is new "
            "feature development versus maintaining existing services?",
            "That's helpful, thank you. Nothing else from me.",
        ],
        "closing": ["Thank you for your time, I enjoyed the conversation."],
    },
    "Data Analyst": {
        "introduction": [
            "Thanks for seeing me. I'm a data analyst with about two years at Mercia Retail "
            "Group. I own the weekly sales performance pack that goes to regional managers, and "
            "I built the stock availability dashboard in Power BI. My background is economics, "
            "so I came in strong on statistics and I've been building up the SQL and Python side "
            "since.",
        ],
        "background": [
            "The stock availability dashboard is the work I'd point to. Before it, store "
            "managers were getting a spreadsheet emailed on Monday that was already two days "
            "stale. I rebuilt it in Power BI against the nightly load so it refreshes every "
            "morning, and I added a flag for lines that had been out of stock more than three "
            "days. That flag was the bit people actually used.",
            "I found a discrepancy in the weekly numbers where the total didn't reconcile with "
            "finance. I traced it back to the nightly load, and it turned out a store that had "
            "changed its ID was being counted twice for a four-day window. I wrote a duplicate "
            "check into the load and added a reconciliation query that runs before the pack goes "
            "out.",
            "I do the pack myself every week. It's about forty five minutes now that it's "
            "templated, and the rest of the time goes on whatever the commercial team has asked "
            "about that week.",
        ],
        "technical": [
            "A left join keeps every row from the left table whether or not there's a match on "
            "the right, and fills the right-hand columns with nulls where there isn't one. An "
            "inner join only keeps rows that match on both sides. The reason it matters in "
            "retail reporting is that if you inner join stores to sales, any store with no sales "
            "that week silently disappears, and then your store count changes between reports "
            "and nobody knows why.",
            "For messy data I start by finding out how bad it is before I fix anything. I'll "
            "count nulls per column, look at the distinct values in anything categorical, and "
            "check the ranges on the numerics. On the point-of-sale data the problems were "
            "mostly inconsistent store naming and a few impossible negative quantities that "
            "turned out to be returns coded wrongly.",
            "If a stakeholder asks for the top customers I'd ask what they mean by top, because "
            "revenue, margin and order frequency give you three different lists. I'd also ask "
            "over what period and whether they want it by account or by individual.",
            "I use a bar chart when I'm comparing categories and a line when I'm showing "
            "something over time. I try hard not to use a pie chart with more than about three "
            "slices because you can't compare the angles. And I always start a bar chart's axis "
            "at zero, otherwise you're exaggerating the difference.",
            "I know what a p-value is but I'd be careful claiming significance on our data. "
            "We've got a lot of seasonality and store-level variation, so a week-on-week change "
            "that looks big often isn't once you account for that.",
        ],
        "behavioural": [
            "A regional manager pushed back on my numbers because they didn't match what he had "
            "in his own spreadsheet. Rather than argue I sat down with him and we reconciled the "
            "two line by line. His was including an extra store that had moved region. He was "
            "right that the numbers disagreed and I was right about the cause, and it was much "
            "better to find that out together.",
            "I sent out a pack with a broken filter once, so two regions showed the same figure. "
            "Someone spotted it within the hour. I sent a correction straight away with a note "
            "saying exactly what was wrong, and since then I've had a checklist I run before it "
            "goes out.",
            "I had to learn Power BI fairly quickly with nobody in the team who knew it. I did "
            "the Microsoft learning path in the evenings and rebuilt one of our existing Excel "
            "reports in it as practice before I touched anything that mattered.",
        ],
        "candidate_questions": [
            "I'd like to know what the data stack looks like here, and whether the analysts are "
            "embedded in business teams or sitting centrally.",
            "Thanks, that answers it.",
        ],
        "closing": ["Thanks very much for your time today."],
    },
    "Cybersecurity Analyst": {
        "introduction": [
            "Thanks for having me. I'm a Tier 2 SOC analyst at Sentinel Managed Security, where "
            "I've been for about three years, two of them at Tier 2. I triage escalated Splunk "
            "alerts across twelve client environments, run the monthly Nessus scans, and I've "
            "led a few incident investigations end to end. Before the SOC I was in IT support, "
            "which turned out to be useful background.",
        ],
        "background": [
            "The credential stuffing incident is the one I'd talk about. We saw a spike in "
            "failed authentications across one client's tenant, and the pattern was a lot of "
            "distinct usernames from a small number of ASNs. I confirmed it wasn't a brute force "
            "against single accounts, pulled the source IPs, and found about forty accounts "
            "where a login had actually succeeded. I got those accounts disabled, pushed a "
            "password reset, and wrote the client-facing report.",
            "The detection tuning work had the biggest measurable effect. Our phishing use case "
            "was generating so many false positives that analysts were closing them without "
            "really looking, which is the dangerous state to be in. I pulled three months of "
            "closed alerts, found that most of the noise came from two internal bulk-mail "
            "senders and one marketing platform, and rewrote the rule with those excluded plus a "
            "tighter condition on the header checks. False positives dropped by roughly forty "
            "percent.",
            "I personally did the analysis and wrote the rule. The change went through our "
            "normal review, so my team lead signed it off before it went live.",
        ],
        "technical": [
            "For triage I'm asking three questions in order. Is this real, how far has it got, "
            "and is it still happening. So first I check whether the detection fired on "
            "something explainable, then I look at what the source and destination actually are "
            "and whether there's evidence of success rather than just an attempt, and then I "
            "check whether it's ongoing, because that changes whether I'm containing or "
            "investigating.",
            "The incident response lifecycle I work to is preparation, detection and analysis, "
            "containment, eradication, recovery, and then the post-incident review. The one "
            "people skip is the review, and it's the one that stops you seeing the same incident "
            "again. On the credential stuffing case the review is what produced the MFA "
            "recommendation.",
            "MITRE ATT&CK is useful to me in two ways. It gives a shared vocabulary so when I "
            "write a report and say this was T1110 the client's own team knows exactly what I "
            "mean, and it helps me find gaps, because I can map our detections onto the matrix "
            "and see which techniques we'd miss entirely.",
            "For a vulnerability I don't just go on the CVSS score. A critical on an internal "
            "host with no network path to it matters less than a high on something "
            "internet-facing with a known exploit in the wild. So I look at exposure, whether "
            "there's active exploitation, and what the asset actually does, then I argue for a "
            "priority on that basis.",
            "In Wireshark for suspected exfiltration I'd look at volume and direction first, so "
            "unusually large outbound transfers, then at the destinations and whether they "
            "resolve to anything sensible, and at timing, because scheduled beaconing looks very "
            "regular. DNS is worth a look too since tunnelling over DNS shows up as a lot of "
            "long unusual queries to one domain.",
            "I've not done much malware reverse engineering. I can do basic static triage, "
            "hashes, strings, checking against threat intel, and I know when to hand it to "
            "someone who does that properly rather than guessing.",
        ],
        "behavioural": [
            "I disagreed with a client's IT lead about whether to isolate a host. He didn't want "
            "it taken off the network because it ran a reporting job. I explained what we'd seen "
            "and what the risk was if we waited, and we compromised: we blocked the outbound "
            "connections at the firewall so the job could finish while the command and control "
            "channel was cut, and isolated it properly that evening.",
            "I escalated something as a confirmed incident that turned out to be a penetration "
            "test the client had commissioned and not told us about. It caused an hour of alarm. "
            "I was embarrassed, but the honest lesson was that we had no process for checking "
            "authorised testing windows, and we added one.",
            "On a busy shift I work to severity, and I'm fairly ruthless about it. A possible "
            "active intrusion gets looked at before a policy violation, even if the policy one "
            "came in first and someone is chasing it.",
        ],
        "candidate_questions": [
            "What does the shift pattern look like, and how is the split between Tier 1 and "
            "Tier 2 handled here?",
            "Great, thank you. That's everything.",
        ],
        "closing": ["Thanks for your time, I appreciate it."],
    },
}

GENERIC_ANSWERS = {
    "introduction": ["Thanks for having me. I'd be glad to tell you about my background."],
    "background": ["I've worked on a few relevant projects and I can talk through any of them."],
    "technical": ["I'd approach that by breaking the problem down and checking my assumptions first."],
    "behavioural": ["I had a situation like that recently and we worked through it as a team."],
    "candidate_questions": ["What does success look like in this role in the first six months?"],
    "closing": ["Thank you for your time."],
}

ROLE_TO_CV = {
    "Software Engineer": "synthetic_software_engineer.pdf",
    "Data Analyst": "synthetic_data_analyst.docx",
    "Cybersecurity Analyst": "synthetic_cybersecurity_analyst.pdf",
}

DEFAULT_ROLES = list(ROLE_TO_CV)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def log(message: str, indent: int = 0) -> None:
    # ascii_safe() is for the console only; the recorded results keep whatever
    # the model actually wrote.
    print(f"{'  ' * indent}{_console.ascii_safe(message)}", flush=True)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Harness:
    def __init__(self, base_url: str = BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=TIMEOUT)

    def close(self) -> None:
        self.client.close()

    def get(self, path: str, **params: Any) -> Any:
        response = self.client.get(f"{self.base_url}{path}", params=params or None)
        response.raise_for_status()
        return response.json()

    def post(self, path: str, payload: Any = None) -> Any:
        response = self.client.post(f"{self.base_url}{path}", json=payload)
        response.raise_for_status()
        return response.json()

    def upload(self, path: str, field: str, filename: str, data: bytes, extra: dict | None = None) -> Any:
        files = {field: (filename, data)}
        response = self.client.post(f"{self.base_url}{path}", files=files, data=extra or {})
        response.raise_for_status()
        return response.json()

    def stream(self, path: str, *, payload: Any = None, files: Any = None, extra: Any = None) -> list[dict]:
        """POST and collect every SSE event from the response."""
        events: list[dict] = []
        kwargs: dict[str, Any] = {}
        if files is not None:
            kwargs["files"] = files
            kwargs["data"] = extra or {}
        else:
            kwargs["json"] = payload

        with self.client.stream("POST", f"{self.base_url}{path}", **kwargs) as response:
            response.raise_for_status()
            buffer = ""
            for chunk in response.iter_text():
                buffer += chunk
                while "\n\n" in buffer:
                    frame, buffer = buffer.split("\n\n", 1)
                    data = "".join(
                        line[5:].strip() for line in frame.split("\n") if line.startswith("data:")
                    )
                    if data:
                        try:
                            events.append(json.loads(data))
                        except ValueError:
                            pass
        return events


def pick_answer(role: str, stage: str, used: set[str]) -> str:
    """Next unused scripted answer for this stage, falling back sensibly."""
    pool = ANSWERS.get(role, GENERIC_ANSWERS).get(stage) or GENERIC_ANSWERS.get(stage, [])
    for answer in pool:
        if answer not in used:
            used.add(answer)
            return answer
    return pool[-1] if pool else "I'm not sure I can add much more on that."


# ---------------------------------------------------------------------------
# Per-role evaluation
# ---------------------------------------------------------------------------


def evaluate_role(
    harness: Harness,
    role: str,
    *,
    mode: str,
    trial: int,
    max_turns: int,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "role": role,
        "trial": trial,
        "mode": mode,
        "started_at": utcnow(),
        "issues": [],
    }
    log(f"\n{'=' * 74}")
    log(f"ROLE: {role}   (trial {trial}, {mode} mode)")
    log("=" * 74)

    # ---- 1. CV ------------------------------------------------------------
    cv_file = CV_DIR / ROLE_TO_CV[role]
    log(f"[1/8] Uploading {cv_file.name}", 0)
    started = time.perf_counter()
    cv = harness.upload("/cv/upload", "file", cv_file.name, cv_file.read_bytes())
    cv_ms = (time.perf_counter() - started) * 1000
    profile = cv["profile"]

    record["cv"] = {
        "filename": cv["filename"],
        "cv_id": cv["cv_id"],
        "extractor": cv["extractor"],
        "parse_mode": profile["parse_mode"],
        "char_count": cv["char_count"],
        "parse_ms": round(cv_ms, 1),
        "name_found": bool(profile["full_name"]),
        "email_found": bool(profile["email"]),
        "phone_found": bool(profile["phone"]),
        "skills_extracted": profile["skill_count"],
        "experience_entries": len(profile["experience"]),
        "education_entries": len(profile["education"]),
        "project_entries": len(profile["projects"]),
        "certification_entries": len(profile["certifications"]),
        "bullets_found": len(profile["all_bullets"]),
        "rejected_claims": profile["rejected_claims"],
        "warnings": profile["warnings"],
        "skills": [s["canonical"] for s in profile["skills"]],
    }
    log(f"      parsed in {cv_ms:.0f}ms: {profile['skill_count']} skills, "
        f"{len(profile['experience'])} roles, {len(profile['all_bullets'])} bullets", 0)
    if profile["rejected_claims"]:
        log(f"      grounding filter dropped {len(profile['rejected_claims'])} unsupported claim(s)", 0)

    # ---- 2. Role analysis -------------------------------------------------
    log("[2/8] Analysing role (live postings + LLM)", 0)
    started = time.perf_counter()
    analysis = harness.post("/roles/analyse", {"role_title": role, "use_scraping": True, "use_llm": True})
    role_ms = (time.perf_counter() - started) * 1000
    requirements = analysis["requirements"]
    stats = requirements["stats"]

    record["role_analysis"] = {
        "role_analysis_id": analysis["role_analysis_id"],
        "elapsed_ms": round(role_ms, 1),
        "normalised_title": requirements["normalised_title"],
        "stats": stats,
        "timings": requirements["timings"],
        "warnings": requirements["warnings"],
        "source_reports": requirements["source_reports"],
        "llm_degraded": requirements["llm_degraded"],
        "top_skills": [
            {
                "canonical": s["canonical"],
                "provenance": s["provenance"],
                "importance": s["importance"],
                "posting_count": s["posting_count"],
                "essential": s["essential"],
            }
            for s in requirements["combined_skills"][:25]
        ],
        "merge_evidence": requirements["merge_evidence"][:20],
    }
    log(f"      {role_ms:.0f}ms: {stats['total_skills']} skills from {stats['postings_collected']} postings; "
        f"{stats['confirmed_by_both']} confirmed by both sources "
        f"({stats['agreement_rate'] * 100:.0f}% agreement)", 0)
    log(f"      sources productive: {stats['sources_succeeded']}/{stats['sources_attempted']}", 0)
    if not stats["postings_collected"]:
        record["issues"].append("No live job postings were collected for this role.")

    # ---- 3. Source agreement ---------------------------------------------
    scraped_only = stats["from_scraping_only"]
    llm_only = stats["from_llm_only"]
    both = stats["confirmed_by_both"]
    llm_total = llm_only + both
    record["source_comparison"] = {
        "scraped_only": scraped_only,
        "llm_only": llm_only,
        "both": both,
        "llm_precision_vs_postings": round(both / llm_total, 3) if llm_total else None,
        "posting_recall_by_llm": round(both / (scraped_only + both), 3) if (scraped_only + both) else None,
        "note": "Precision here means: of the skills the LLM proposed, what share were also "
                "asked for by at least one collected advert. It is a measure of agreement, "
                "not of ground truth -- the adverts are themselves an incomplete sample.",
    }
    log(f"[3/8] LLM/posting agreement: {record['source_comparison']['llm_precision_vs_postings']}", 0)

    # ---- 4. Gap analysis --------------------------------------------------
    log("[4/8] Running skill gap analysis", 0)
    started = time.perf_counter()
    gap = harness.post(
        "/gap/analyse",
        {"cv_id": cv["cv_id"], "role_analysis_id": analysis["role_analysis_id"], "with_advice": True},
    )
    gap_ms = (time.perf_counter() - started) * 1000
    result = gap["result"]

    record["gap_analysis"] = {
        "gap_analysis_id": gap["gap_analysis_id"],
        "elapsed_ms": round(gap_ms, 1),
        "match_percent": result["match_percent"],
        "unweighted_percent": result["unweighted_percent"],
        "readiness_label": result["readiness_label"],
        "stats": result["stats"],
        "essential_coverage": result["essential_coverage"],
        "category_breakdown": result["category_breakdown"],
        "top_missing": [
            {"skill": c["requirement"], "severity": c["severity"], "essential": c["essential"]}
            for c in result["priority_gaps"][:12]
        ],
        "advice_available": result["advice"].get("available", False),
        "advice_filtered_out": result["advice"].get("filtered_out", 0),
    }
    log(f"      {gap_ms:.0f}ms: {result['match_percent']:.1f}% weighted coverage "
        f"({result['stats']['matched']} matched / {result['stats']['partial']} partial / "
        f"{result['stats']['missing']} missing)", 0)

    # ---- 5. CV improvement ------------------------------------------------
    log("[5/8] Improving CV bullet points", 0)
    bullets = [b["text"] for b in cv["bullet_ranking"][:6]]
    if bullets:
        started = time.perf_counter()
        improve = harness.post(
            "/improve/bullets", {"bullets": bullets, "role_title": role, "cv_id": cv["cv_id"]}
        )
        improve_ms = (time.perf_counter() - started) * 1000
        record["cv_improvement"] = {
            "elapsed_ms": round(improve_ms, 1),
            "summary": improve["summary"],
            "examples": [
                {
                    "original": r["original"],
                    "improved": r["improved"],
                    "accepted": r["accepted"],
                    "rejection_reason": r["rejection_reason"],
                    "changes": r["changes"],
                    "flags": r["flags"],
                }
                for r in improve["results"]
            ],
        }
        log(f"      {improve_ms:.0f}ms: {improve['summary']['accepted']}/{improve['summary']['requested']} "
            f"accepted, {improve['summary']['rejected']} blocked by the invention guard "
            f"{improve['summary']['rejections_by_reason'] or ''}", 0)
    else:
        record["cv_improvement"] = {"skipped": "no bullet points found in the CV"}
        record["issues"].append("No bullet points available to improve.")

    # ---- 6. Interview -----------------------------------------------------
    log(f"[6/8] Conducting mock interview ({mode})", 0)
    interview = harness.post(
        "/interview/start",
        {
            "role_title": role,
            "difficulty": "medium",
            "mode": mode,
            "cv_id": cv["cv_id"],
            "role_analysis_id": analysis["role_analysis_id"],
        },
    )
    interview_id = interview["interview"]["id"]

    if mode == "voice":
        harness.post("/interview/speech/warmup")

    turns: list[dict[str, Any]] = []
    used_answers: set[str] = set()
    stage = "introduction"
    finished = False

    # Opening turn carries no candidate answer.
    events = harness.stream(f"/interview/{interview_id}/turn", payload={"text": "", "speak": mode == "voice"})
    opening = _summarise_turn(events)
    turns.append({"index": 0, "candidate_answer": None, **opening})
    stage = opening.get("stage") or stage
    log(f"      Q1 [{stage}]: {opening.get('reply', '')[:110]}", 0)

    for index in range(1, max_turns + 1):
        if finished:
            break
        answer = pick_answer(role, stage, used_answers)

        if mode == "voice":
            audio = _synthesise_answer(harness, answer)
            if audio is None:
                record["issues"].append(
                    "Local TTS could not synthesise a scripted answer, so this turn fell back to text."
                )
                events = harness.stream(
                    f"/interview/{interview_id}/turn", payload={"text": answer, "speak": True}
                )
            else:
                events = harness.stream(
                    f"/interview/{interview_id}/voice-turn",
                    files={"audio": ("answer.wav", audio, "audio/wav")},
                    extra={"speak": "true"},
                )
        else:
            events = harness.stream(
                f"/interview/{interview_id}/turn", payload={"text": answer, "speak": False}
            )

        summary = _summarise_turn(events)
        summary["index"] = index
        summary["candidate_answer"] = answer
        turns.append(summary)

        if summary.get("error"):
            record["issues"].append(f"Turn {index} failed: {summary['error']}")
            break

        stage = summary.get("stage") or stage
        finished = bool(summary.get("finished"))
        latency = summary.get("timings", {}).get("e2e_first_audio_ms")
        log(f"      Q{index + 1} [{stage}]"
            + (f" {latency:.0f}ms" if latency else "")
            + (f" follow-up" if summary.get("follow_up") else "")
            + f": {summary.get('reply', '')[:96]}", 0)

    if not finished:
        harness.post(f"/interview/{interview_id}/end")

    record["interview"] = {
        "interview_id": interview_id,
        "plan": interview["interview"]["plan"],
        "turns": turns,
        "completed_naturally": finished,
        "questions_asked": sum(1 for t in turns if t.get("reply")),
        "follow_ups": sum(1 for t in turns if t.get("follow_up")),
        "stages_reached": sorted({t.get("stage") for t in turns if t.get("stage")}),
        "difficulty_adaptations": sorted(
            {t.get("effective_difficulty") for t in turns if t.get("effective_difficulty")}
        ),
        "transcription": [
            {
                "index": t["index"],
                "stt_ms": t.get("stt", {}).get("processing_ms"),
                "confidence": t.get("stt", {}).get("confidence"),
                "audio_seconds": t.get("stt", {}).get("duration_seconds"),
                "reference_text": t.get("candidate_answer"),
                "transcribed_text": t.get("transcript"),
            }
            for t in turns
            if t.get("stt")
        ],
    }

    # ---- 7. Scoring -------------------------------------------------------
    log("[7/8] Scoring the interview against the rubric", 0)
    started = time.perf_counter()
    report = harness.post(f"/interview/{interview_id}/score")
    score_ms = (time.perf_counter() - started) * 1000

    record["scoring"] = {
        "elapsed_ms": round(score_ms, 1),
        "overall_score": report["overall_score"],
        "overall_band": report["overall_band"],
        "categories_scored": report["categories_scored"],
        "categories_not_tested": report["categories_not_tested"],
        "category_scores": [
            {
                "key": c["key"],
                "score": c["score"],
                "weight_percent": c["weight_percent"],
                "justification": c["justification"],
            }
            for c in report["category_scores"]
        ],
        "strengths": report["strengths"],
        "weaknesses": report["weaknesses"],
        "recommended_topics": report["recommended_topics"],
        "transcript_stats": report["transcript_stats"],
        "assessor": report["assessor"],
    }
    log(f"      {score_ms:.0f}ms: {report['overall_score']}/5 ({report['overall_band']}), "
        f"{report['categories_scored']} categories scored", 0)

    # ---- 8. Latency -------------------------------------------------------
    log("[8/8] Collecting latency measurements", 0)
    metrics = harness.get(f"/metrics/interview/{interview_id}")
    record["performance"] = {
        "aggregates": metrics["aggregates"],
        "turns": metrics["turns"],
        "engines": metrics["engines"],
    }
    headline = metrics["aggregates"]["e2e_first_audio_ms"]
    if headline["samples"]:
        log(f"      end of speech to first audio: median {headline['median_ms']:.0f}ms, "
            f"p90 {headline['p90_ms']:.0f}ms over {headline['samples']} turns", 0)
    else:
        log("      no end-to-end audio latency recorded (text mode records generation time only)", 0)

    record["finished_at"] = utcnow()
    return record


def _summarise_turn(events: list[dict]) -> dict[str, Any]:
    """Fold the SSE event list for one turn into a flat record."""
    out: dict[str, Any] = {"reply": "", "audio_chunks": 0}
    text_parts: list[str] = []

    for event in events:
        kind = event.get("type")
        if kind == "text":
            text_parts.append(event.get("delta", ""))
        elif kind == "transcript":
            out["transcript"] = event.get("text", "")
            out["stt"] = event.get("stt", {})
        elif kind == "no_speech":
            out["stt"] = event.get("stt", {})
            out["error"] = event.get("message")
        elif kind == "analysis":
            out["analysis"] = event.get("analysis")
        elif kind == "stage":
            out["stage"] = event.get("stage")
        elif kind == "audio":
            out["audio_chunks"] = out.get("audio_chunks", 0) + 1
            out.setdefault("first_audio_since_speech_end_ms", event.get("since_speech_end_ms"))
        elif kind == "metrics":
            out["timings"] = event.get("timings", {})
        elif kind == "done":
            out["reply"] = event.get("reply") or "".join(text_parts)
            out["stage"] = event.get("stage") or out.get("stage")
            out["finished"] = event.get("finished", False)
            out["follow_up"] = event.get("follow_up", False)
            out["effective_difficulty"] = event.get("effective_difficulty")
            if event.get("timings"):
                out["timings"] = event["timings"]
        elif kind == "error":
            out["error"] = event.get("message")

    if not out["reply"]:
        out["reply"] = "".join(text_parts)
    return out


def _synthesise_answer(harness: Harness, text: str) -> bytes | None:
    """
    Turn a scripted answer into real audio with the LOCAL TTS engine.

    This makes the voice path a genuine measurement: the audio posted to the
    interview endpoint is decoded and transcribed by local Whisper exactly as a
    human recording would be. It is not a human voice, which is a limitation
    recorded honestly in the evaluation write-up.
    """
    try:
        response = harness.client.post(
            f"{harness.base_url}/interview/speak",
            json={"text": text[:2300]},
            timeout=httpx.Timeout(240.0),
        )
        response.raise_for_status()
        return response.content
    except Exception as exc:
        log(f"      ! local TTS failed for a scripted answer: {type(exc).__name__}", 0)
        return None


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def build_summary(records: list[dict[str, Any]], harness: Harness) -> dict[str, Any]:
    def collect(path: list[str]) -> list[float]:
        values: list[float] = []
        for record in records:
            node: Any = record
            for key in path:
                node = (node or {}).get(key) if isinstance(node, dict) else None
            if isinstance(node, (int, float)):
                values.append(float(node))
        return values

    match_percents = collect(["gap_analysis", "match_percent"])
    scores = [
        r["scoring"]["overall_score"]
        for r in records
        if r.get("scoring", {}).get("overall_score") is not None
    ]
    agreements = [
        r["source_comparison"]["llm_precision_vs_postings"]
        for r in records
        if r.get("source_comparison", {}).get("llm_precision_vs_postings") is not None
    ]

    global_metrics = harness.get("/metrics")
    health = harness.get("/system/health")

    return {
        "generated_at": utcnow(),
        "roles_evaluated": sorted({r["role"] for r in records}),
        "runs": len(records),
        "environment": {
            "llm_provider": health["components"]["llm"]["provider"],
            "llm_model": health["components"]["llm"]["model"],
            "llm_degraded": health["components"]["llm"]["degraded"],
            "stt_engine": health["components"]["speech_recognition"].get("engine"),
            "stt_model": health["components"]["speech_recognition"].get("model_size"),
            "tts_engine": health["components"]["text_to_speech"].get("active_engine"),
            "python": health["runtime"]["python"],
            "platform": health["runtime"]["platform"],
            "taxonomy": health["components"]["skill_taxonomy"],
        },
        "cv_parsing": {
            "runs": len(records),
            "all_names_found": all(r["cv"]["name_found"] for r in records),
            "all_emails_found": all(r["cv"]["email_found"] for r in records),
            "mean_skills_extracted": round(
                statistics.mean([r["cv"]["skills_extracted"] for r in records]), 1
            ),
            "total_rejected_claims": sum(len(r["cv"]["rejected_claims"]) for r in records),
            "mean_parse_ms": round(statistics.mean(collect(["cv", "parse_ms"])), 1),
        },
        "role_analysis": {
            "mean_skills": round(
                statistics.mean([r["role_analysis"]["stats"]["total_skills"] for r in records]), 1
            ),
            "mean_postings": round(
                statistics.mean([r["role_analysis"]["stats"]["postings_collected"] for r in records]), 1
            ),
            "mean_agreement_rate": round(
                statistics.mean([r["role_analysis"]["stats"]["agreement_rate"] for r in records]), 3
            ),
            "mean_llm_precision_vs_postings": round(statistics.mean(agreements), 3) if agreements else None,
            "mean_elapsed_ms": round(statistics.mean(collect(["role_analysis", "elapsed_ms"])), 1),
        },
        "gap_analysis": {
            # Keyed by role AND trial: keying by role alone silently discarded
            # the first trial's result, which is exactly the variance the
            # specification asks to be reported.
            "match_percent_by_run": {
                f"{r['role']} (trial {r['trial']})": r["gap_analysis"]["match_percent"]
                for r in records
            },
            "match_percent_by_role": _per_role(records, ["gap_analysis", "match_percent"]),
            "mean_match_percent": round(statistics.mean(match_percents), 1) if match_percents else None,
            "spread_match_percent": round(max(match_percents) - min(match_percents), 1)
            if len(match_percents) > 1
            else 0.0,
        },
        "cv_improvement": {
            "total_requested": sum(
                r.get("cv_improvement", {}).get("summary", {}).get("requested", 0) for r in records
            ),
            "total_accepted": sum(
                r.get("cv_improvement", {}).get("summary", {}).get("accepted", 0) for r in records
            ),
            "total_blocked": sum(
                r.get("cv_improvement", {}).get("summary", {}).get("rejected", 0) for r in records
            ),
            "blocked_by_reason": _merge_counts(
                [r.get("cv_improvement", {}).get("summary", {}).get("rejections_by_reason", {}) for r in records]
            ),
        },
        "interview": {
            "mean_questions": round(
                statistics.mean([r["interview"]["questions_asked"] for r in records]), 1
            ),
            "total_follow_ups": sum(r["interview"]["follow_ups"] for r in records),
            "completed_naturally": sum(1 for r in records if r["interview"]["completed_naturally"]),
            "stages_reached_by_role": {
                r["role"]: r["interview"]["stages_reached"] for r in records
            },
            "difficulty_adaptations_by_role": {
                r["role"]: r["interview"]["difficulty_adaptations"] for r in records
            },
        },
        "scoring": {
            "overall_score_by_run": {
                f"{r['role']} (trial {r['trial']})": r["scoring"]["overall_score"]
                for r in records
            },
            "overall_score_by_role": _per_role(records, ["scoring", "overall_score"]),
            "mean_overall_score": round(statistics.mean(scores), 2) if scores else None,
            "spread_overall_score": round(max(scores) - min(scores), 2) if len(scores) > 1 else 0.0,
        },
        "performance": global_metrics["summary"],
        "issues": {r["role"]: r["issues"] for r in records if r["issues"]},
    }


def _per_role(records: list[dict[str, Any]], path: list[str]) -> dict[str, Any]:
    """
    Group a per-run value by role, keeping every trial.

    Reports the individual values plus their spread, which is what makes
    repeated trials worth running.
    """
    grouped: dict[str, list[float]] = {}
    for record in records:
        node: Any = record
        for key in path:
            node = (node or {}).get(key) if isinstance(node, dict) else None
        if isinstance(node, (int, float)):
            grouped.setdefault(record["role"], []).append(float(node))

    out: dict[str, Any] = {}
    for role, values in grouped.items():
        out[role] = {
            "values": values,
            "trials": len(values),
            "mean": round(statistics.mean(values), 2),
            "spread": round(max(values) - min(values), 2) if len(values) > 1 else 0.0,
        }
    return out


def _merge_counts(dicts: list[dict[str, int]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in dicts:
        for key, value in (item or {}).items():
            out[key] = out.get(key, 0) + int(value)
    return out


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the end-to-end evaluation.")
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--roles", nargs="*", default=DEFAULT_ROLES)
    parser.add_argument("--mode", choices=["text", "voice"], default="voice")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--max-turns", type=int, default=18)
    parser.add_argument("--tag", default="", help="suffix for the output filenames")
    parser.add_argument("--summarise-only", action="store_true",
                        help="rebuild the summary from an existing evaluation_runs.json "
                             "instead of running the interviews again")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    harness = Harness(args.base_url)

    try:
        try:
            health = harness.get("/system/health")
        except Exception as exc:
            log(f"Cannot reach the backend at {args.base_url}: {exc}")
            log("Start it first:  cd backend && uvicorn app.main:app --port 8000")
            return 1

        log("=" * 74)
        log("CAREER INTELLIGENCE PLATFORM - EVALUATION HARNESS")
        log("=" * 74)
        log(f"Backend status : {health['status']}")
        log(f"LLM            : {health['components']['llm']['provider']} / "
            f"{health['components']['llm']['model']}"
            + (" (DEGRADED - offline engine)" if health["components"]["llm"]["degraded"] else ""))
        log(f"Speech in      : {health['components']['speech_recognition'].get('engine')} "
            f"({health['components']['speech_recognition'].get('model_size')})")
        log(f"Speech out     : {health['components']['text_to_speech'].get('active_engine')}")
        log(f"Mode           : {args.mode}")
        log(f"Roles          : {', '.join(args.roles)}")
        log(f"Trials         : {args.trials}")
        if health["degradations"]:
            log("Degradations   :")
            for item in health["degradations"]:
                log(f"  - {item}")

        suffix_early = f"_{args.tag}" if args.tag else ""
        if args.summarise_only:
            runs_path = RESULTS_DIR / f"evaluation_runs{suffix_early}.json"
            if not runs_path.exists():
                log(f"\n{runs_path} does not exist, so there is nothing to summarise.")
                return 1
            records = json.loads(runs_path.read_text(encoding="utf-8"))
            usable = [r for r in records if "fatal_error" not in r]
            summary = build_summary(usable, harness)
            summary_path = RESULTS_DIR / f"evaluation_summary{suffix_early}.json"
            summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
            log(f"\nRebuilt the summary from {len(usable)} saved run(s)")
            log(f"Summary: {summary_path}")
            return 0

        records: list[dict[str, Any]] = []
        for trial in range(1, args.trials + 1):
            for role in args.roles:
                if role not in ROLE_TO_CV:
                    log(f"\nSkipping unknown role {role!r} (no synthetic CV mapped to it)")
                    continue
                try:
                    records.append(
                        evaluate_role(
                            harness, role, mode=args.mode, trial=trial, max_turns=args.max_turns
                        )
                    )
                except Exception as exc:
                    log(f"\n!! {role} (trial {trial}) failed: {type(exc).__name__}: {exc}")
                    records.append(
                        {
                            "role": role,
                            "trial": trial,
                            "mode": args.mode,
                            "fatal_error": f"{type(exc).__name__}: {exc}",
                            "issues": [f"The run aborted: {exc}"],
                        }
                    )

        usable = [r for r in records if "fatal_error" not in r]
        suffix = f"_{args.tag}" if args.tag else ""

        runs_path = RESULTS_DIR / f"evaluation_runs{suffix}.json"
        runs_path.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")

        summary_path = RESULTS_DIR / f"evaluation_summary{suffix}.json"
        if usable:
            summary = build_summary(usable, harness)
            summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        else:
            summary = {"error": "every run failed"}
            summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        log(f"\n{'=' * 74}")
        log("EVALUATION COMPLETE")
        log("=" * 74)
        log(f"Runs completed : {len(usable)}/{len(records)}")
        log(f"Detailed runs  : {runs_path}")
        log(f"Summary        : {summary_path}")

        if usable:
            log("\nHeadline results")
            log("-" * 74)
            for record in usable:
                gap = record["gap_analysis"]["match_percent"]
                score = record["scoring"]["overall_score"]
                headline = record["performance"]["aggregates"]["e2e_first_audio_ms"]
                latency = f"{headline['median_ms']:.0f}ms" if headline["samples"] else "n/a"
                log(f"  {record['role']:26} coverage {gap:5.1f}%   "
                    f"interview {score if score is not None else '-':>4}/5   reply {latency:>8}")

            perf = summary["performance"]["aggregates"]["e2e_first_audio_ms"]
            if perf["samples"]:
                log(f"\n  Overall end-of-speech to first audio: median {perf['median_ms']:.0f}ms, "
                    f"p90 {perf['p90_ms']:.0f}ms, n={perf['samples']}")
            if summary["issues"]:
                log("\n  Issues recorded:")
                for role, issues in summary["issues"].items():
                    for issue in issues:
                        log(f"    [{role}] {issue}")

        return 0
    finally:
        harness.close()


if __name__ == "__main__":
    sys.exit(main())
