"""
Deterministic, rule-based stand-in for the LLM.

Purpose
-------
1. The product must still demonstrate every screen if no API key / model server
   is available on the demo machine.
2. The automated test suite must be reproducible, which a sampling LLM is not.

What it is NOT
--------------
It is not pretending to be an LLM and the application never claims it is: the
provider is reported as "offline" and marked `degraded: true` in the health
endpoint, the UI shows a banner, and the evaluation report records which engine
produced each number.  Quality is visibly lower -- the question bank is
template-driven and the role profiles come from a small built-in knowledge base.

Everything here is honest rule-based NLP: taxonomy keyword matching over real
text, filler-phrase rewriting, and evidence-counting heuristics for scoring.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.core.logging_setup import get_logger
from app.services.skills import taxonomy as tx
from app.services.skills.text_norm import normalise_key

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Built-in role knowledge base (used only in offline mode)
# ---------------------------------------------------------------------------

_ROLE_LIBRARY: dict[str, dict[str, Any]] = {
    "software engineer": {
        "role_summary": "Designs, builds, tests and maintains software systems, working "
        "from requirements through to deployment and support in a team setting.",
        "core": ["Python", "JavaScript", "Git", "REST API", "SQL", "Data Structures & Algorithms",
                 "Object-Oriented Programming", "Unit Testing", "Debugging", "System Design"],
        "desirable": ["Docker", "CI/CD", "TypeScript", "AWS", "Microservices", "React"],
        "tools": ["Git", "Docker", "Jira", "VS Code", "Postman", "CI/CD"],
        "soft": ["Communication", "Teamwork", "Problem Solving", "Code Review", "Time Management"],
        "quals": ["Bachelor's Degree"],
        "responsibilities": [
            "Write and review application code against agreed requirements",
            "Design APIs and data models for new features",
            "Write automated tests and fix defects found in review or production",
            "Participate in sprint planning and estimation",
            "Deploy changes through a CI/CD pipeline and monitor the result",
        ],
        "focus": ["Language fundamentals", "Data structures and complexity", "API and system design",
                  "Testing and debugging approach", "Version control workflow"],
    },
    "data analyst": {
        "role_summary": "Turns raw business data into decisions: extracts and cleans data, "
        "analyses it for patterns, and communicates findings to non-technical stakeholders.",
        "core": ["SQL", "Excel", "Data Visualisation", "Statistics", "Data Cleaning",
                 "Python", "Business Intelligence", "Database Design"],
        "desirable": ["Power BI", "Tableau", "Pandas", "A/B Testing", "ETL", "Data Warehousing"],
        "tools": ["Excel", "Power BI", "Tableau", "SQL", "Jupyter", "Google Analytics"],
        "soft": ["Communication", "Attention to Detail", "Stakeholder Management",
                 "Presentation Skills", "Problem Solving"],
        "quals": ["Bachelor's Degree"],
        "responsibilities": [
            "Write SQL queries to pull and join data from multiple sources",
            "Clean and validate datasets before analysis",
            "Build and maintain dashboards and recurring reports",
            "Present findings and recommendations to business stakeholders",
            "Define and track key performance indicators",
        ],
        "focus": ["SQL joins and aggregation", "Handling messy or missing data",
                  "Choosing the right chart", "Explaining results to non-technical people",
                  "Basic statistics and significance"],
    },
    "cybersecurity analyst": {
        "role_summary": "Defends an organisation's systems: monitors for intrusions, "
        "investigates alerts, assesses vulnerabilities and responds to incidents.",
        "core": ["Networking", "Network Security", "SIEM", "Incident Response",
                 "Vulnerability Management", "Linux", "Packet Analysis", "Threat Intelligence"],
        "desirable": ["Penetration Testing", "Python", "Cloud Security", "Digital Forensics",
                      "Malware Analysis", "Endpoint Security"],
        "tools": ["SIEM", "Packet Analysis", "Vulnerability Management", "Endpoint Security", "Linux"],
        "soft": ["Attention to Detail", "Communication", "Problem Solving", "Time Management"],
        "quals": ["Bachelor's Degree", "CompTIA Security+"],
        "responsibilities": [
            "Monitor SIEM alerts and triage security events",
            "Investigate suspected intrusions and document findings",
            "Run vulnerability scans and track remediation",
            "Maintain detection rules and security tooling",
            "Support incident response and post-incident review",
        ],
        "focus": ["TCP/IP and common protocols", "Alert triage and prioritisation",
                  "The incident response lifecycle", "MITRE ATT&CK and threat models",
                  "Vulnerability severity and patch decisions"],
    },
    "frontend developer": {
        "role_summary": "Builds the user-facing part of web applications, translating "
        "designs into accessible, responsive and performant interfaces.",
        "core": ["JavaScript", "HTML", "CSS", "React", "TypeScript", "Responsive Web Design",
                 "REST API", "Git", "Web Accessibility"],
        "desirable": ["Next.js", "Tailwind CSS", "Unit Testing", "Redux", "Performance Optimisation"],
        "tools": ["Git", "Vite", "Figma", "VS Code", "Postman"],
        "soft": ["Communication", "Teamwork", "Attention to Detail", "Customer Focus"],
        "quals": ["Bachelor's Degree"],
        "responsibilities": [
            "Build reusable interface components from designs",
            "Integrate the frontend with backend REST or GraphQL APIs",
            "Ensure pages are responsive and accessible",
            "Write component and end-to-end tests",
            "Profile and improve page load and interaction performance",
        ],
        "focus": ["JavaScript fundamentals and the event loop", "Component state management",
                  "CSS layout", "Accessibility", "Frontend performance"],
    },
    "machine learning engineer": {
        "role_summary": "Takes machine learning models from experiment to production: "
        "builds data and training pipelines, deploys models and monitors them.",
        "core": ["Python", "Machine Learning", "scikit-learn", "Model Evaluation",
                 "Feature Engineering", "SQL", "Deep Learning", "MLOps", "Statistics"],
        "desirable": ["PyTorch", "TensorFlow", "Docker", "AWS", "Big Data", "Large Language Models"],
        "tools": ["Jupyter", "Git", "Docker", "MLOps", "Pandas"],
        "soft": ["Problem Solving", "Communication", "Teamwork", "Documentation"],
        "quals": ["Bachelor's Degree", "Master's Degree"],
        "responsibilities": [
            "Build and validate training and inference pipelines",
            "Select features and evaluate model performance honestly",
            "Deploy models behind an API and monitor drift",
            "Work with analysts and engineers to define the problem",
            "Document experiments so results are reproducible",
        ],
        "focus": ["Bias/variance and overfitting", "Evaluation metric choice",
                  "Feature engineering decisions", "Getting a model into production",
                  "Monitoring a live model"],
    },
    "devops engineer": {
        "role_summary": "Owns the path from code to running system: build pipelines, "
        "infrastructure, deployment automation, monitoring and reliability.",
        "core": ["Linux", "Docker", "Kubernetes", "CI/CD", "Terraform", "AWS",
                 "Bash", "Monitoring & Observability", "Networking"],
        "desirable": ["Python", "Ansible", "Microservices", "Cloud Security", "Nginx"],
        "tools": ["Docker", "Kubernetes", "Terraform", "Git", "CI/CD", "Monitoring & Observability"],
        "soft": ["Problem Solving", "Communication", "Teamwork", "Time Management"],
        "quals": ["Bachelor's Degree"],
        "responsibilities": [
            "Build and maintain CI/CD pipelines",
            "Define infrastructure as code",
            "Containerise services and run them on an orchestrator",
            "Set up monitoring, alerting and on-call runbooks",
            "Investigate and resolve production incidents",
        ],
        "focus": ["Container and orchestration fundamentals", "Pipeline design",
                  "Infrastructure as code", "Observability", "Incident handling"],
    },
    "product manager": {
        "role_summary": "Decides what gets built and why: gathers evidence, defines "
        "requirements, prioritises a roadmap and coordinates delivery.",
        "core": ["Product Management", "Stakeholder Management", "Agile", "Data Visualisation",
                 "Business Acumen", "UX Research", "Communication"],
        "desirable": ["SQL", "A/B Testing", "Google Analytics", "Project Management"],
        "tools": ["Jira", "Figma", "Excel", "Google Analytics"],
        "soft": ["Communication", "Leadership", "Presentation Skills", "Problem Solving",
                 "Time Management", "Customer Focus"],
        "quals": ["Bachelor's Degree"],
        "responsibilities": [
            "Translate user and business needs into prioritised requirements",
            "Write user stories and acceptance criteria",
            "Run discovery research and validate assumptions",
            "Align engineering, design and business stakeholders",
            "Measure whether shipped work achieved its goal",
        ],
        "focus": ["Prioritisation frameworks", "Defining success metrics",
                  "Handling stakeholder conflict", "Discovery and validation",
                  "Saying no with evidence"],
    },
}

_ROLE_ALIASES = {
    "software developer": "software engineer",
    "backend developer": "software engineer",
    "back end developer": "software engineer",
    "full stack developer": "software engineer",
    "fullstack developer": "software engineer",
    "programmer": "software engineer",
    "sde": "software engineer",
    "web developer": "frontend developer",
    "front end developer": "frontend developer",
    "ui developer": "frontend developer",
    "react developer": "frontend developer",
    "data scientist": "machine learning engineer",
    "ml engineer": "machine learning engineer",
    "ai engineer": "machine learning engineer",
    "business analyst": "data analyst",
    "bi analyst": "data analyst",
    "business intelligence analyst": "data analyst",
    "reporting analyst": "data analyst",
    "security analyst": "cybersecurity analyst",
    "soc analyst": "cybersecurity analyst",
    "information security analyst": "cybersecurity analyst",
    "cyber security analyst": "cybersecurity analyst",
    "site reliability engineer": "devops engineer",
    "sre": "devops engineer",
    "platform engineer": "devops engineer",
    "cloud engineer": "devops engineer",
    "product owner": "product manager",
}

_GENERIC_ROLE: dict[str, Any] = {
    "role_summary": "A professional role. The offline engine has no specific profile for "
    "this title, so the requirements below are generic and should be treated as a "
    "starting point only.",
    "core": ["Communication", "Problem Solving", "Teamwork", "Documentation",
             "Time Management", "Attention to Detail"],
    "desirable": ["Project Management", "Stakeholder Management", "Business Acumen"],
    "tools": ["Excel", "Jira"],
    "soft": ["Communication", "Teamwork", "Adaptability", "Problem Solving"],
    "quals": ["Bachelor's Degree"],
    "responsibilities": [
        "Deliver the core duties of the role to an agreed standard",
        "Work with colleagues and stakeholders across the organisation",
        "Document work so that others can pick it up",
        "Identify and escalate problems early",
    ],
    "focus": ["Relevant experience", "Working with others", "Handling problems",
              "Motivation for this role"],
}


def _lookup_role(role_title: str) -> tuple[str, dict[str, Any]]:
    key = re.sub(r"[^a-z ]", " ", (role_title or "").lower())
    key = re.sub(r"\s+", " ", key).strip()
    key = re.sub(r"\b(senior|junior|lead|principal|staff|graduate|entry level|mid level|i{1,3}|intern)\b", "", key).strip()
    key = re.sub(r"\s+", " ", key)

    if key in _ROLE_LIBRARY:
        return key, _ROLE_LIBRARY[key]
    if key in _ROLE_ALIASES:
        resolved = _ROLE_ALIASES[key]
        return resolved, _ROLE_LIBRARY[resolved]

    # Partial containment, longest alias first so "data analyst" beats "analyst".
    for alias in sorted(_ROLE_ALIASES, key=len, reverse=True):
        if alias in key:
            resolved = _ROLE_ALIASES[alias]
            return resolved, _ROLE_LIBRARY[resolved]
    for name in sorted(_ROLE_LIBRARY, key=len, reverse=True):
        if name in key or all(word in key for word in name.split()):
            return name, _ROLE_LIBRARY[name]

    return "generic", _GENERIC_ROLE


def _detect_seniority(text: str) -> str:
    low = (text or "").lower()
    for word, level in (
        ("principal", "lead"), ("staff", "lead"), ("lead", "lead"), ("head of", "lead"),
        ("senior", "senior"), ("sr.", "senior"), ("mid", "mid"),
        ("junior", "junior"), ("jr.", "junior"),
        ("graduate", "entry"), ("intern", "entry"), ("entry", "entry"), ("trainee", "entry"),
    ):
        if word in low:
            return level
    return "unspecified"


# ---------------------------------------------------------------------------
# Task dispatch
# ---------------------------------------------------------------------------


def offline_complete(*, task: str, prompt: str, system: str = "") -> str:
    """Return the deterministic response for `task`, as a JSON or text string."""
    handler = {
        "role_skills": _role_skills,
        "posting_skills": _posting_skills,
        "gap_advice": _gap_advice,
        "bullet_improve": _bullet_improve,
        "interview_plan": _interview_plan,
        "interview_turn": _interview_turn,
        "scoring": _scoring,
        "cv_parse": _cv_parse,
        "probe": lambda _p: "OK",
    }.get(task)

    if handler is None:
        log.debug("Offline engine has no handler for task=%s; returning empty object", task)
        return "{}"
    try:
        return handler(prompt)
    except Exception as exc:  # pragma: no cover - must never crash the request
        log.error("Offline engine failed on task=%s: %s", task, exc)
        return "{}"


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _extract_block(prompt: str, tag: str) -> str:
    match = re.search(rf"<<<BEGIN_{tag}>>>\s*(.*?)\s*<<<END_{tag}>>>", prompt, re.S)
    return match.group(1).strip() if match else ""


def _extract_field(prompt: str, label: str) -> str:
    match = re.search(rf"^{re.escape(label)}\s*:?\s*(.+)$", prompt, re.M)
    return match.group(1).strip() if match else ""


def _stable_choice(options: list[str], seed: str) -> str:
    """Deterministic pseudo-random pick, so output varies by input but repeats."""
    if not options:
        return ""
    digest = hashlib.sha256(seed.encode("utf-8", "ignore")).hexdigest()
    return options[int(digest[:8], 16) % len(options)]


# --------------------------------------------------------------- CV parsing --


def _cv_parse(_prompt: str) -> str:
    """
    Offline mode does no LLM CV parsing.

    The heuristic parser in services/cv/parser.py always runs and owns the
    result; returning an empty object here means "the LLM contributed nothing",
    which the parser handles explicitly rather than treating as a failure.
    """
    return "{}"


# ------------------------------------------------------------- role skills --


def _role_skills(prompt: str) -> str:
    role_title = _extract_block(prompt, "JOB_TITLE") or _extract_field(prompt, "Job title entered by the user")
    role_title = role_title.strip() or "Unspecified Role"
    name, profile = _lookup_role(role_title)
    seniority = _detect_seniority(role_title)

    assessment = (
        "clear"
        if name != "generic"
        else "The offline engine has no profile for this exact title, so these requirements are generic."
    )
    normalised = role_title.strip().title() if name == "generic" else name.title()

    return _dumps(
        {
            "normalised_title": normalised,
            "title_assessment": assessment,
            "seniority": seniority,
            "role_summary": profile["role_summary"],
            "core_technical_skills": profile["core"],
            "desirable_technical_skills": profile["desirable"],
            "tools_and_platforms": profile["tools"],
            "soft_skills": profile["soft"],
            "qualifications": profile["quals"],
            "responsibilities": profile["responsibilities"],
            "interview_focus_areas": profile["focus"],
        }
    )


# ---------------------------------------------------------- posting skills --


def _posting_skills(prompt: str) -> str:
    """
    Extract skills from an advert by matching the curated taxonomy against the
    advert text.  This is genuine (if shallow) keyword NLP, not a guess.
    """
    advert = _extract_block(prompt, "JOB_ADVERT")
    low = f" {re.sub(r'[^a-z0-9+#./ ]', ' ', advert.lower())} "
    low = re.sub(r"\s+", " ", low)

    required: list[str] = []
    for canonical, meta in tx.CANONICAL_SKILLS.items():
        for form in [canonical, *meta["aliases"]]:
            probe = normalise_key(form, strip_noise=False)
            if len(probe) < tx.DOCUMENT_SCAN_MIN_KEY_LENGTH:
                continue
            if f" {probe} " in low:
                required.append(canonical)
                break

    # Split required vs preferred using the advert's own section wording.
    preferred_zone = ""
    for marker in ("nice to have", "nice-to-have", "desirable", "bonus", "preferred qualifications", "a plus"):
        idx = advert.lower().find(marker)
        if idx >= 0:
            preferred_zone += " " + advert[idx : idx + 900].lower()

    preferred = [s for s in required if normalise_key(s) and normalise_key(s) in preferred_zone]
    required = [s for s in required if s not in preferred]

    responsibilities: list[str] = []
    for line in advert.splitlines():
        stripped = line.strip(" -•\t*")
        if 35 <= len(stripped) <= 180 and re.match(r"^[A-Z]?[a-z]+(ing|e|s)?\b", stripped):
            responsibilities.append(stripped)
        if len(responsibilities) >= 6:
            break

    return _dumps(
        {
            "required_skills": required[:40],
            "preferred_skills": preferred[:15],
            "responsibilities": responsibilities,
            "seniority_signal": _detect_seniority(advert[:400]),
        }
    )


# -------------------------------------------------------------- gap advice --


def _gap_advice(prompt: str) -> str:
    def parse_list(label: str) -> list[str]:
        match = re.search(rf"{label}\s*\(\d+\)\s*:\s*(\[.*?\])", prompt, re.S)
        if not match:
            return []
        try:
            value = json.loads(match.group(1))
            return [str(v) for v in value if isinstance(v, str)]
        except ValueError:
            return []

    matched = parse_list("matched_skills")
    missing = parse_list("missing_skills")
    partial = parse_list("partially_matched_skills")

    score_match = re.search(r"Computed match score:\s*([\d.]+)", prompt)
    percent = float(score_match.group(1)) if score_match else 0.0
    role = _extract_field(prompt, "Target role") or "this role"

    how_to = {
        tx.CATEGORY_LANGUAGE: "Work through a structured tutorial, then rewrite one of your existing projects in it.",
        tx.CATEGORY_FRONTEND: "Build one small interface end to end and deploy it somewhere public.",
        tx.CATEGORY_BACKEND: "Build a small service with three or four endpoints, including validation and error handling.",
        tx.CATEGORY_DATABASE: "Load a public dataset and practise joins, grouping and indexing against it.",
        tx.CATEGORY_CLOUD: "Deploy one container to a free tier and add a build pipeline to it.",
        tx.CATEGORY_DATA: "Take one messy public dataset through clean, analyse and present.",
        tx.CATEGORY_ML: "Reproduce one well-documented model end to end and report its metrics honestly.",
        tx.CATEGORY_SECURITY: "Set up a home lab or use a free range, and write up one investigation.",
        tx.CATEGORY_TOOL: "Use it daily on your current work until it is habit.",
        tx.CATEGORY_PRACTICE: "Apply it to your next project and have someone review the result.",
        tx.CATEGORY_SOFT: "Prepare two concrete STAR examples you can tell in under ninety seconds.",
        tx.CATEGORY_QUALIFICATION: "Check the syllabus and book a date; the deadline is what makes it happen.",
    }

    priority: list[dict[str, str]] = []
    for skill in missing[:6]:
        category = tx.category_of(skill)
        priority.append(
            {
                "skill": skill,
                "why_it_matters": f"{skill} appears in the combined requirements for {role} "
                f"and is currently absent from your CV.",
                "how_to_close": how_to.get(category, "Find one small, finishable project that forces you to use it."),
                "estimated_effort": "1-2 weeks of focused practice"
                if category in (tx.CATEGORY_TOOL, tx.CATEGORY_SOFT, tx.CATEGORY_PRACTICE)
                else "3-6 weeks of focused practice",
            }
        )

    quick_wins = [
        s for s in missing
        if tx.category_of(s) in (tx.CATEGORY_TOOL, tx.CATEGORY_SOFT, tx.CATEGORY_PRACTICE)
    ][:5]

    return _dumps(
        {
            "headline": f"Your CV currently covers about {percent:.0f}% of the combined requirements "
            f"collected for {role}.",
            "priority_gaps": priority,
            "quick_wins": quick_wins,
            "strengths_to_lead_with": matched[:8],
            "learning_sequence": [f"Step {i + 1}: {s}" for i, s in enumerate(missing[:5])]
            or ["No missing skills were identified from the requirements collected."],
            "caveat": "This is automated practice guidance generated from a keyword comparison, "
            "not an assessment of your suitability for any job.",
        }
    )


# --------------------------------------------------------- bullet rewriting --

_FILLER_PATTERNS: list[tuple[str, str]] = [
    (r"^\s*(?:i\s+was\s+)?responsible\s+for\s+", ""),
    (r"^\s*(?:i\s+)?was\s+tasked\s+with\s+", ""),
    (r"^\s*(?:i\s+)?(?:also\s+)?helped\s+(?:to\s+|with\s+)?", "Contributed to "),
    (r"^\s*(?:i\s+)?assisted\s+(?:in\s+|with\s+)?", "Supported "),
    (r"^\s*(?:i\s+)?worked\s+on\s+", "Developed "),
    (r"^\s*(?:i\s+)?worked\s+with\s+", "Used "),
    (r"^\s*(?:i\s+)?did\s+", "Performed "),
    (r"^\s*(?:i\s+)?made\s+", "Built "),
    (r"^\s*(?:i\s+)?involved\s+in\s+", "Contributed to "),
    (r"^\s*(?:i\s+)?participated\s+in\s+", "Contributed to "),
    (r"^\s*(?:my\s+)?duties\s+included\s+", ""),
    (r"^\s*tasks\s+included\s+", ""),
    (r"\s+in\s+order\s+to\s+", " to "),
    (r"\s+various\s+", " "),
    (r"\s+a\s+lot\s+of\s+", " "),
    (r"\s+utili[sz]ed?\s+", " used "),
    (r"\s+leverag(?:ed|ing)\s+", " used "),
]

_WEAK_TO_STRONG = {
    "made": "Built", "did": "Delivered", "got": "Achieved", "put": "Deployed",
    "used": "Applied", "handled": "Managed", "dealt": "Resolved",
    "created": "Developed", "wrote": "Authored", "fixed": "Resolved",
    "checked": "Validated", "looked": "Investigated", "set": "Configured",
    "ran": "Operated", "gave": "Delivered", "took": "Led",
}


def _bullet_improve(prompt: str) -> str:
    block = _extract_block(prompt, "ORIGINAL_BULLETS")
    results: list[dict[str, Any]] = []

    for line in block.splitlines():
        match = re.match(r"^\s*\[(\d+)\]\s*(.+)$", line)
        if not match:
            continue
        index, original = int(match.group(1)), match.group(2).strip()
        improved, changes = _rewrite_bullet(original)
        metrics = re.findall(r"\d+(?:[.,]\d+)?\s*%?|\b\d+[kKmM]\b", original)
        results.append(
            {
                "index": index,
                "improved": improved,
                "explanation": (
                    "Rule-based rewrite: " + ", ".join(changes) + "."
                    if changes
                    else "The bullet already opens with a strong action verb and contains no filler, "
                    "so it was left close to the original."
                ),
                "changes": changes or ["already concise"],
                "metrics_preserved": [m.strip() for m in metrics],
                "already_strong": not changes,
            }
        )

    return _dumps({"results": results})


def _rewrite_bullet(original: str) -> tuple[str, list[str]]:
    """
    Deterministically strengthen a bullet.

    Invents nothing: it only deletes filler, upgrades a weak verb to a stronger
    synonym, and fixes capitalisation/tense surface issues.
    """
    text = original.strip()
    changes: list[str] = []

    for pattern, replacement in _FILLER_PATTERNS:
        new_text = re.sub(pattern, replacement, text, flags=re.I)
        if new_text != text:
            text = new_text
            if "removed filler" not in changes:
                changes.append("removed filler")

    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return original, []

    words = text.split()
    first = words[0].lower().strip(".,")
    if first in _WEAK_TO_STRONG:
        words[0] = _WEAK_TO_STRONG[first]
        changes.append("stronger verb")
    elif first.endswith("ing") and len(first) > 5:
        words[0] = first[:-3].capitalize() + "ed" if not first[:-3].endswith("e") else first[:-3].capitalize() + "d"
        changes.append("past-tense action verb")

    text = " ".join(words)
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
        if "capitalisation" not in changes:
            changes.append("capitalisation")

    text = text.rstrip(" .;,")
    if len(text.split()) > 34:
        changes.append("tightened to one sentence")
        text = " ".join(text.split()[:32])

    return text, changes


# ------------------------------------------------------------- interviewing --


def _interview_plan(prompt: str) -> str:
    role = _extract_field(prompt, "Role") or "the role"
    profile_text = _extract_block(prompt, "CANDIDATE_PROFILE")
    _, profile = _lookup_role(role)

    talking_points: list[str] = []
    for line in profile_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Project:"):
            talking_points.append(f"Their project: {stripped[8:].strip()[:90]}")
        elif stripped.startswith("Experience:"):
            talking_points.append(f"Their role: {stripped[11:].strip()[:90]}")
        elif stripped.startswith("  - ") and len(stripped) > 30:
            talking_points.append(f"CV claim: {stripped[4:].strip()[:90]}")
        if len(talking_points) >= 5:
            break

    cv_skill_match = re.search(r"Skills on CV \(\d+\): (.+)", profile_text)
    cv_skills = {s.strip().lower() for s in (cv_skill_match.group(1).split(",") if cv_skill_match else [])}
    gap_probes = [s for s in profile["core"] if s.lower() not in cv_skills][:4]

    return _dumps(
        {
            "interviewer_name": _stable_choice(
                ["Sarah Ahmed", "David Chen", "Priya Nair", "Omar Farooq", "Elena Rossi", "Michael Obi"],
                role,
            ),
            "interviewer_persona": "Hiring manager; practical, asks for concrete examples and follow-ups.",
            "opening_line_hint": "Greet the candidate, introduce yourself and the role, and invite a brief self-introduction.",
            "cv_talking_points": talking_points or ["No CV detail was available to probe."],
            "technical_topics": profile["focus"] + profile["core"][:4],
            "behavioural_themes": [
                "Working with others under pressure",
                "Handling a mistake or failure",
                "Prioritising when everything is urgent",
                "Learning something unfamiliar quickly",
            ],
            "gap_probes": gap_probes,
            "red_flag_checks": ["Unexplained gaps between roles", "Claims with no specifics behind them"],
        }
    )


_STAGE_QUESTIONS: dict[str, list[str]] = {
    "introduction": [
        "Thanks for joining me today. To get us started, could you walk me through your background in your own words?",
        "Good to meet you. Before we get into the detail, tell me a little about yourself and what brought you to this role.",
    ],
    "background": [
        "Tell me about the piece of work on your CV you are most proud of, and what your specific contribution was.",
        "Which of the roles on your CV stretched you the most, and in what way?",
        "Walk me through a project on your CV from start to finish. What was your part in it?",
    ],
    "technical": [
        "Let's talk technically. How would you explain {topic} to someone joining your team next week?",
        "Tell me about a time {topic} caused you a problem. What did you actually do about it?",
        "How do you decide when to use {topic}, and when it would be the wrong choice?",
        "If you had to check whether your work on {topic} was correct, how would you go about it?",
    ],
    "behavioural": [
        "Tell me about a time you disagreed with a colleague about how to do something. How did that play out?",
        "Describe a time you got something wrong. How did you find out, and what did you do next?",
        "Tell me about a week when everything was urgent. How did you decide what to drop?",
        "Give me an example of something you had to learn quickly with nobody to ask.",
    ],
    "candidate_questions": [
        "That covers what I wanted to ask. What questions do you have for me, about the role or the team?",
        "We have time for your questions now. What would you like to know?",
    ],
    "closing": [
        "Thank you, that is everything from my side. We will be in touch about next steps. Best of luck.",
        "That brings us to the end. Thanks for your time today, and we will follow up shortly.",
    ],
}

_FOLLOW_UPS = [
    "You mentioned {term} just now. Can you take me a level deeper into that?",
    "Let's stay with {term} for a moment. What was the hardest part of it?",
    "When you say {term}, what did that involve in practice day to day?",
    "You touched on {term}. What would you do differently if you did it again?",
]

_PROBES = [
    "Could you give me a specific example of that, with what you personally did?",
    "That is quite general. Can you ground it in one real situation you were part of?",
    "Help me picture it. What did you actually do, step by step?",
]

_VAGUE_MARKERS = re.compile(
    r"\b(?:i think|maybe|probably|sort of|kind of|not sure|i guess|basically|stuff|things|whatever)\b", re.I
)


def _interview_turn(prompt: str) -> str:
    stage = (_extract_field(prompt, "COVERAGE NOTE") or "").lower()
    stage_match = re.search(r"stage[_ ]?(?:is|:)?\s*([a-z_]+)", prompt, re.I)
    stage_name = "introduction"
    for candidate in _STAGE_QUESTIONS:
        if candidate in stage or (stage_match and candidate in stage_match.group(1).lower()):
            stage_name = candidate
            break

    last_answer = _extract_block(prompt, "CANDIDATE_LAST_ANSWER")
    asked_block = re.search(r"QUESTIONS YOU HAVE ALREADY ASKED.*?\n((?:- .*\n?)*)", prompt)
    asked = [line[2:].strip() for line in (asked_block.group(1).splitlines() if asked_block else []) if line.startswith("- ")]

    # Opening turn.
    if not last_answer.strip():
        return _stable_choice(_STAGE_QUESTIONS["introduction"], prompt[:200])

    words = last_answer.split()
    seed = last_answer[:160]

    # Thin or vague answer -> ask for a specific example (but not twice running).
    recent_probe = any(q in _PROBES for q in asked[-2:])
    if (len(words) < 18 or _VAGUE_MARKERS.search(last_answer)) and not recent_probe:
        return _stable_choice(_PROBES, seed)

    # Substantive answer -> follow up on a salient technical term they used.
    term = _salient_term(last_answer)
    if term and stage_name in ("background", "technical") and len(words) >= 18:
        template = _stable_choice(_FOLLOW_UPS, seed)
        question = template.format(term=term)
        if question not in asked:
            return question

    pool = [q for q in _STAGE_QUESTIONS.get(stage_name, _STAGE_QUESTIONS["background"]) if q not in asked]
    pool = pool or _STAGE_QUESTIONS.get(stage_name, _STAGE_QUESTIONS["background"])
    question = _stable_choice(pool, seed)

    if "{topic}" in question:
        topics = re.findall(r"Interview focus areas: (.+)", prompt)
        options = [t.strip() for t in topics[0].split(",")] if topics else ["the main tools you use"]
        question = question.replace("{topic}", _stable_choice(options, seed) or "your core tooling")
    return question


def _salient_term(text: str) -> str:
    """Pick a technology mentioned in the answer, for an adaptive follow-up."""
    low = f" {re.sub(r'[^a-zA-Z0-9+#./ ]', ' ', text.lower())} "
    low = re.sub(r"\s+", " ", low)
    best = ""
    for canonical, meta in tx.CANONICAL_SKILLS.items():
        if tx.category_of(canonical) in (tx.CATEGORY_SOFT, tx.CATEGORY_QUALIFICATION):
            continue
        for form in [canonical, *meta["aliases"]]:
            probe = normalise_key(form, strip_noise=False)
            if (
                len(probe) >= tx.DOCUMENT_SCAN_MIN_KEY_LENGTH
                and f" {probe} " in low
                and len(canonical) > len(best)
            ):
                best = canonical
                break
    return best


# ------------------------------------------------------------------ scoring --

_SPECIFIC_MARKERS = re.compile(
    r"\b(?:for example|for instance|specifically|in my (?:last|previous|current) (?:role|job|project)|"
    r"we (?:used|built|decided|migrated)|i (?:built|wrote|designed|led|implemented|debugged|measured)|"
    r"because|which meant|the result was|as a result|so that)\b",
    re.I,
)
_STRUCTURE_MARKERS = re.compile(r"\b(?:first|then|after that|finally|the problem was|my approach|the outcome)\b", re.I)


def _scoring(prompt: str) -> str:
    transcript = _extract_block(prompt, "INTERVIEW_TRANSCRIPT")
    role = _extract_field(prompt, "Role interviewed for") or "the role"

    keys = re.findall(r"^\s*-?\s*([a-z_]{4,30})\s*\(weight", prompt, re.M) or re.findall(
        r"key:\s*([a-z_]+)", prompt
    )
    if not keys:
        keys = ["technical_accuracy", "conceptual_understanding", "communication",
                "problem_solving", "relevance", "behavioural_competency"]

    answers = re.findall(r"Candidate:\s*(.+?)(?=\n(?:Interviewer|Candidate):|\Z)", transcript, re.S)
    answers = [a.strip() for a in answers if a.strip()]

    if not answers:
        return _dumps(
            {
                "category_scores": [
                    {"key": k, "score": None,
                     "justification": "The candidate gave no answers, so this category could not be assessed.",
                     "evidence_quote": ""}
                    for k in keys
                ],
                "strengths": [],
                "weaknesses": ["No answers were recorded in this interview."],
                "answers_to_improve": [],
                "recommended_topics": [],
                "improvement_plan": [],
                "overall_comment": "This interview contains no candidate answers, so no assessment is possible.",
            }
        )

    total_words = sum(len(a.split()) for a in answers)
    avg_words = total_words / len(answers)
    specific_hits = sum(len(_SPECIFIC_MARKERS.findall(a)) for a in answers)
    structure_hits = sum(len(_STRUCTURE_MARKERS.findall(a)) for a in answers)
    vague_hits = sum(len(_VAGUE_MARKERS.findall(a)) for a in answers)
    blob = " ".join(answers).lower()
    tech_hits = sum(
        1
        for canonical in tx.CANONICAL_SKILLS
        if tx.category_of(canonical) not in (tx.CATEGORY_SOFT, tx.CATEGORY_QUALIFICATION)
        and len(normalise_key(canonical, strip_noise=False)) >= tx.DOCUMENT_SCAN_MIN_KEY_LENGTH
        and normalise_key(canonical, strip_noise=False) in blob
    )

    def band(value: float, thresholds: tuple[float, float, float, float]) -> int:
        return 1 + sum(1 for t in thresholds if value >= t)

    scores = {
        "technical_accuracy": band(tech_hits, (1, 3, 6, 10)),
        "conceptual_understanding": band(specific_hits + tech_hits / 2, (1, 3, 6, 10)),
        "communication": max(1, band(avg_words, (18, 35, 60, 95)) - (1 if vague_hits > 3 else 0)),
        "problem_solving": band(structure_hits, (1, 2, 4, 7)),
        "relevance": band(specific_hits, (1, 2, 4, 7)),
        "behavioural_competency": band(structure_hits + specific_hits / 2, (1, 3, 5, 8)),
    }

    # Each category states the evidence that drove ITS score, and quotes the
    # answer that best shows it -- the rubric requires every score explained,
    # and one shared sentence for all six categories did not do that.
    reasons = {
        "technical_accuracy": f"{tech_hits} distinct technical terms from the taxonomy were used across the answers",
        "conceptual_understanding": (
            f"{specific_hits} concrete-example markers and {tech_hits} technical terms suggest how far "
            "explanations went beyond definitions"
        ),
        "communication": (
            f"answers averaged {avg_words:.0f} words with {vague_hits} hedging phrases"
            + (" (hedging lowered this score)" if vague_hits > 3 else "")
        ),
        "problem_solving": f"{structure_hits} structuring phrases (first/then/the outcome) showed a stepwise approach",
        "relevance": f"{specific_hits} references to concrete, real situations rather than generalities",
        "behavioural_competency": (
            f"{structure_hits} structuring phrases and {specific_hits} concrete-example markers indicate "
            "how STAR-shaped the behavioural answers were"
        ),
    }
    pickers = {
        "technical_accuracy": lambda a: sum(1 for c in tx.CANONICAL_SKILLS if len(c) >= 4 and c.lower() in a.lower()),
        "conceptual_understanding": lambda a: len(_SPECIFIC_MARKERS.findall(a)),
        "communication": lambda a: -abs(len(a.split()) - 60),
        "problem_solving": lambda a: len(_STRUCTURE_MARKERS.findall(a)),
        "relevance": lambda a: len(_SPECIFIC_MARKERS.findall(a)),
        "behavioural_competency": lambda a: len(_STRUCTURE_MARKERS.findall(a)) + len(_SPECIFIC_MARKERS.findall(a)),
    }

    category_scores = []
    for key in keys:
        score = int(min(5, max(1, scores.get(key, band(avg_words, (18, 35, 60, 95))))))
        best = max(answers, key=pickers.get(key, lambda a: len(a)))
        category_scores.append(
            {
                "key": key,
                "score": score,
                "justification": (
                    f"Scored {score}/5 because {reasons.get(key, f'answers averaged {avg_words:.0f} words')} "
                    f"(over {len(answers)} answers). No language model was available, so this rule-based "
                    "score counts evidence rather than judging whether the content was correct."
                ),
                "evidence_quote": best[:160] + ("..." if len(best) > 160 else ""),
            }
        )

    strengths: list[str] = []
    if avg_words >= 45:
        strengths.append("Answers were developed rather than one-liners.")
    if specific_hits >= 3:
        strengths.append("Used concrete examples from real work rather than generalities.")
    if tech_hits >= 5:
        strengths.append(f"Brought relevant technical vocabulary into the conversation ({tech_hits} distinct terms).")
    if structure_hits >= 3:
        strengths.append("Answers had a recognisable structure (situation, action, outcome).")

    weaknesses: list[str] = []
    if avg_words < 30:
        weaknesses.append(f"Answers were short (average {avg_words:.0f} words); interviewers read brevity as thin knowledge.")
    if specific_hits < 2:
        weaknesses.append("Few concrete examples - answers stayed at the level of what one 'would' do.")
    if vague_hits > 3:
        weaknesses.append(f"Frequent hedging ({vague_hits} instances of 'maybe', 'sort of', 'I think').")
    if tech_hits < 3:
        weaknesses.append("Little role-specific technical vocabulary appeared in the answers.")

    shortest = min(answers, key=lambda a: len(a.split()))
    return _dumps(
        {
            "category_scores": category_scores,
            "strengths": strengths or ["The candidate completed the interview."],
            "weaknesses": weaknesses or ["No significant weakness was detected by the rule-based checks."],
            "answers_to_improve": [
                {
                    "question": "(shortest answer in the interview)",
                    "candidate_answer_summary": shortest[:200],
                    "why_it_fell_short": f"At {len(shortest.split())} words this answer gave the interviewer "
                    "little to follow up on.",
                    "stronger_answer_outline": "Name the situation, state what you personally did, then say what "
                    "the result was and what you learned - roughly sixty to ninety seconds of speech.",
                }
            ],
            "recommended_topics": [f"Core fundamentals for {role}", "Telling a project story in 90 seconds",
                                   "Having two STAR examples ready", "Quantifying your own impact honestly"],
            "improvement_plan": [
                {
                    "timeframe": "This week",
                    "focus": "Answer structure",
                    "actions": ["Write out three STAR stories from your CV",
                                "Record yourself answering each in 90 seconds"],
                },
                {
                    "timeframe": "Next two weeks",
                    "focus": f"Technical depth for {role}",
                    "actions": ["Pick the two weakest topics from the gap analysis and build something small with each",
                                "Practise explaining each one out loud without notes"],
                },
            ],
            "overall_comment": (
                f"This feedback was produced by the offline rule-based engine, which counts evidence "
                f"(answer length, concrete-example markers, technical vocabulary, structuring phrases) "
                f"rather than understanding the content. Across {len(answers)} answers the transcript shows "
                f"an average of {avg_words:.0f} words with {specific_hits} concrete-example markers. "
                "Configure a language model for substantive feedback. This is practice feedback, not a hiring decision."
            ),
        }
    )
