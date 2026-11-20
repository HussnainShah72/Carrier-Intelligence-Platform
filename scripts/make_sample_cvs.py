"""
Generate the synthetic test CVs used by the test suite and the evaluation.

Every CV produced here is FICTIONAL. Names, employers, dates and achievements
were written for this project; they describe no real person. Each file carries a
"SYNTHETIC TEST CV" marker in its header so it can never be mistaken for a real
candidate's document, and the filenames say `synthetic` too.

Three profiles are generated, deliberately matched to the three very different
roles the evaluation covers (the project specification asks for at least three):

    software_engineer   mid-level backend/full-stack
    data_analyst        early-career analyst, business-facing
    cybersecurity       SOC analyst, defensive security

Plus three fixtures that exercise the parser's failure handling:

    minimal     almost no content
    messy       table layout, odd headings, inconsistent dates
    empty       zero bytes

Run:
    python scripts/make_sample_cvs.py
Outputs to:
    evaluation/sample_cvs/
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "evaluation" / "sample_cvs"

MARKER = "SYNTHETIC TEST CV - FICTIONAL PERSON - CREATED FOR NLP COURSE PROJECT TESTING"


# ---------------------------------------------------------------------------
# CV content
# ---------------------------------------------------------------------------

SOFTWARE_ENGINEER = f"""{MARKER}

Aisha Rahman
Software Engineer
aisha.rahman@example.com | +44 7700 900123 | Manchester, United Kingdom
github.com/example-aisha | linkedin.com/in/example-aisha

PROFESSIONAL SUMMARY
Backend-focused software engineer with 4 years of experience building and maintaining
REST APIs and internal tooling for logistics platforms. Comfortable owning a service
from design through to production support.

TECHNICAL SKILLS
Languages: Python, JavaScript, TypeScript, SQL, Bash
Backend: FastAPI, Django, Node.js, Express, REST APIs, PostgreSQL, Redis
Frontend: React, HTML, CSS, Tailwind CSS
Tooling: Git, Docker, GitHub Actions, pytest, Postman, Linux
Practices: Unit testing, code review, Agile, object-oriented programming

WORK EXPERIENCE

Software Engineer | Northfield Logistics Ltd | Manchester | Mar 2023 - Present
- Responsible for the shipment tracking API used by three internal teams
- Worked on migrating a monolithic Django application to a set of FastAPI services
- Reduced median API response time from 420ms to 180ms by adding Redis caching and fixing N+1 queries
- Helped to set up GitHub Actions pipelines that run pytest and linting on every pull request
- Reviewed pull requests from two junior engineers and ran their onboarding

Junior Software Developer | Brightline Software | Leeds | Sep 2021 - Feb 2023
- Built internal admin screens in React consumed by the operations team
- Wrote unit tests for the billing module, raising its coverage from 34% to 81%
- Fixed defects reported by QA against the customer portal
- Participated in sprint planning and estimation with the product owner

PROJECTS

Warehouse Slot Optimiser | Python, PostgreSQL, FastAPI
Built a service that assigns inbound pallets to warehouse slots using a greedy
heuristic. Exposed as a REST endpoint and used in a pilot at one depot.

Open Source Contribution - httpx
Submitted a documentation fix and a small bug fix for timeout handling.
github.com/example-aisha/httpx-contrib

EDUCATION

BSc (Hons) Computer Science | University of Manchester | 2018 - 2021
Grade: 2:1

CERTIFICATIONS
AWS Certified Cloud Practitioner - Amazon Web Services - 2024
Professional Scrum Master I - Scrum.org - 2023

LANGUAGES
English (native), Urdu (fluent)
"""

DATA_ANALYST = f"""{MARKER}

Daniel Okonkwo
Data Analyst
daniel.okonkwo@example.com | +44 7700 900456 | Birmingham, United Kingdom
linkedin.com/in/example-daniel

PROFILE
Data analyst with 2 years of experience turning operational data into reporting that
non-technical managers actually use. Strong SQL and Excel, currently building out
Python skills.

SKILLS
SQL, Microsoft Excel, Power BI, Tableau, Python, Pandas, Data Visualisation,
Data Cleaning, Statistics, Google Analytics, Stakeholder Management, Presentation Skills

EXPERIENCE

Data Analyst | Mercia Retail Group | Birmingham | Jan 2024 - Present
- Responsible for the weekly sales performance pack circulated to regional managers
- Worked on cleaning and consolidating point-of-sale data from 48 stores
- Built a Power BI dashboard tracking stock availability that replaced a manual spreadsheet process
- Investigated a reporting discrepancy and traced it to duplicated records in the nightly load
- Presented monthly findings to the commercial team

Junior Reporting Analyst | Mercia Retail Group | Birmingham | Jul 2023 - Dec 2023
- Produced ad-hoc SQL extracts for the finance and marketing teams
- Maintained the existing Excel reporting suite
- Documented the definitions behind each KPI so the numbers could be reproduced

PROJECTS

Customer Churn Exploration | Python, Pandas, scikit-learn
Analysed a public telecoms churn dataset, compared logistic regression with a decision
tree, and wrote up which features mattered most. Reported accuracy of 79% on a held-out
test set.

Football Attendance Dashboard | Tableau
Built a public dashboard exploring attendance trends across four seasons.

EDUCATION

BSc Economics | University of Birmingham | 2020 - 2023
Grade: First Class Honours
Relevant modules: Econometrics, Statistics for Economists, Data Analysis

CERTIFICATIONS
Google Data Analytics Professional Certificate - Coursera - 2023

LANGUAGES
English (native)
"""

CYBERSECURITY = f"""{MARKER}

Priya Deshmukh
Cybersecurity Analyst
priya.deshmukh@example.com | +44 7700 900789 | Reading, United Kingdom
linkedin.com/in/example-priya

SUMMARY
SOC analyst with 3 years of experience in alert triage, incident response and
vulnerability management for a managed security services provider.

TECHNICAL SKILLS
Security: Incident Response, SIEM, Threat Intelligence, Vulnerability Management,
Endpoint Security, Network Security, Packet Analysis, MITRE ATT&CK
Tools: Splunk, Wireshark, Nessus, CrowdStrike, Microsoft Sentinel
Systems: Linux, Windows Server, Active Directory
Networking: TCP/IP, DNS, DHCP, firewalls, VPN
Scripting: Python, PowerShell, Bash

PROFESSIONAL EXPERIENCE

Security Analyst (Tier 2) | Sentinel Managed Security | Reading | Jun 2023 - Present
- Responsible for triaging escalated Splunk alerts across 12 client environments
- Worked on tuning detection rules, which cut false positives on the phishing use case by roughly 40%
- Led the investigation of a credential stuffing incident and produced the client-facing report
- Ran monthly Nessus vulnerability scans and tracked remediation with system owners
- Mentored one Tier 1 analyst through their first three months

SOC Analyst (Tier 1) | Sentinel Managed Security | Reading | Aug 2022 - May 2023
- Monitored SIEM dashboards on a rotating shift pattern
- Performed initial triage and escalated genuine incidents according to the playbook
- Maintained the on-call handover log

IT Support Technician | Reading Borough Council | Reading | Sep 2021 - Jul 2022
- Handled first-line support tickets for roughly 300 users
- Managed Active Directory accounts and group membership
- Assisted with the rollout of multi-factor authentication

PROJECTS

Home Detection Lab | Linux, Splunk, Sysmon
Built a small lab with a Windows host and a Kali attacker, generated attack telemetry,
and wrote Splunk detections for three MITRE ATT&CK techniques.

EDUCATION

BSc (Hons) Cyber Security | University of Reading | 2018 - 2021
Grade: 2:1

CERTIFICATIONS
CompTIA Security+ - CompTIA - 2022
CompTIA Network+ - CompTIA - 2021
Microsoft SC-200 Security Operations Analyst - Microsoft - 2024

LANGUAGES
English (fluent), Marathi (native), Hindi (fluent)
"""

MINIMAL = f"""{MARKER}

John Smith
john.smith@example.com

Looking for work.
"""

# Deliberately awkward: pipe-separated contact block, non-standard headings,
# inconsistent date formats, skills buried mid-sentence.
MESSY = f"""{MARKER}

MARIA  SANTOS   ||   maria.santos@example.com   ||   07700900999

WHAT I DO
I am a developer. I have been doing web work since 2019 and I mostly use react and
node these days, plus a bit of mongo.

WHERE I HAVE WORKED
Acme Web Studio -- developer -- 2019 to now
   * built websites for clients
   * did some API work
Freelance | 2018-2019
   * various small jobs

SCHOOL
Diploma in Software Development, Lisbon Technical College, finished 2018

OTHER
react, reactjs, React.js, node.js, nodejs, mongodb, mongo db, git, GIT
"""


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def write_txt(name: str, content: str) -> Path:
    path = OUT_DIR / f"{name}.txt"
    path.write_text(content, encoding="utf-8")
    return path


def write_docx(name: str, content: str) -> Path | None:
    try:
        import docx  # type: ignore
    except ImportError:
        print("  ! python-docx not installed; skipping DOCX output")
        return None

    document = docx.Document()
    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped:
            document.add_paragraph("")
        elif stripped.isupper() and len(stripped) < 60:
            document.add_heading(stripped, level=2)
        elif stripped.startswith(("-", "*")):
            document.add_paragraph(stripped.lstrip("-* ").strip(), style="List Bullet")
        else:
            document.add_paragraph(stripped)

    path = OUT_DIR / f"{name}.docx"
    document.save(str(path))
    return path


def write_pdf(name: str, content: str) -> Path | None:
    """Build a text-layer PDF with reportlab (not a scan, so it is parseable)."""
    try:
        from reportlab.lib.pagesizes import A4  # type: ignore
        from reportlab.lib.units import mm  # type: ignore
        from reportlab.pdfgen import canvas  # type: ignore
    except ImportError:
        print("  ! reportlab not installed; skipping PDF output")
        return None

    path = OUT_DIR / f"{name}.pdf"
    page = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    left = 18 * mm
    top = height - 18 * mm
    bottom = 18 * mm
    leading = 4.6 * mm
    y = top

    for raw_line in content.split("\n"):
        line = raw_line.rstrip()
        if y < bottom:
            page.showPage()
            y = top

        if not line:
            y -= leading * 0.6
            continue

        is_heading = line.isupper() and len(line) < 60 and not line.startswith(MARKER[:12])
        page.setFont("Helvetica-Bold" if is_heading else "Helvetica", 10.5 if is_heading else 9.5)

        # Wrap long lines so nothing runs off the page.
        max_chars = 108
        chunks: list[str] = []
        remaining = line
        while len(remaining) > max_chars:
            cut = remaining.rfind(" ", 0, max_chars)
            if cut <= 0:
                cut = max_chars
            chunks.append(remaining[:cut])
            remaining = "    " + remaining[cut:].lstrip()
        chunks.append(remaining)

        for chunk in chunks:
            if y < bottom:
                page.showPage()
                y = top
                page.setFont("Helvetica-Bold" if is_heading else "Helvetica", 10.5 if is_heading else 9.5)
            page.drawString(left, y, chunk)
            y -= leading

    page.save()
    return path


def write_empty() -> Path:
    path = OUT_DIR / "synthetic_empty.pdf"
    path.write_bytes(b"")
    return path


def write_fake_pdf() -> Path:
    """A file claiming to be a PDF that is not one - tests the magic-byte check."""
    path = OUT_DIR / "synthetic_not_really_a_pdf.pdf"
    path.write_bytes(b"MZ\x90\x00\x03This is not a PDF at all." + b"\x00" * 400)
    return path


def write_scanned_lookalike() -> Path | None:
    """A PDF with no text layer - tests the 'scanned CV' path."""
    try:
        from reportlab.lib.pagesizes import A4  # type: ignore
        from reportlab.pdfgen import canvas  # type: ignore
    except ImportError:
        return None

    path = OUT_DIR / "synthetic_image_only.pdf"
    page = canvas.Canvas(str(path), pagesize=A4)
    # Draw shapes only: a valid PDF that contains no extractable characters.
    page.setFillColorRGB(0.85, 0.85, 0.85)
    for row in range(14):
        page.rect(60, 760 - row * 46, 460, 22, fill=1, stroke=0)
    page.save()
    return path


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing synthetic test CVs to {OUT_DIR}")

    profiles = {
        "synthetic_software_engineer": SOFTWARE_ENGINEER,
        "synthetic_data_analyst": DATA_ANALYST,
        "synthetic_cybersecurity_analyst": CYBERSECURITY,
    }

    written: list[Path] = []
    for name, content in profiles.items():
        written.append(write_txt(name, content))
        for writer in (write_pdf, write_docx):
            path = writer(name, content)
            if path:
                written.append(path)

    # Edge cases for the parser tests.
    written.append(write_txt("synthetic_minimal", MINIMAL))
    for writer in (write_pdf, write_docx):
        path = writer("synthetic_messy", MESSY)
        if path:
            written.append(path)
    written.append(write_txt("synthetic_messy", MESSY))
    written.append(write_empty())
    written.append(write_fake_pdf())
    scanned = write_scanned_lookalike()
    if scanned:
        written.append(scanned)

    readme = OUT_DIR / "README.md"
    readme.write_text(
        "# Synthetic test CVs\n\n"
        "**Every file in this folder is synthetic.** The people, employers, dates and\n"
        "achievements are fictional and were written for testing this project. No real\n"
        "candidate's CV is included anywhere in this repository.\n\n"
        "Each document carries the marker line:\n\n"
        f"> `{MARKER}`\n\n"
        "## Realistic profiles (used for the evaluation)\n\n"
        "| File | Profile | Used to evaluate |\n"
        "|---|---|---|\n"
        "| `synthetic_software_engineer.*` | Mid-level backend engineer, 4 years | Software Engineer role |\n"
        "| `synthetic_data_analyst.*` | Early-career analyst, 2 years | Data Analyst role |\n"
        "| `synthetic_cybersecurity_analyst.*` | SOC analyst, 3 years | Cybersecurity Analyst role |\n\n"
        "Each is generated as `.txt`, `.pdf` (with a real text layer) and `.docx`.\n\n"
        "## Edge-case fixtures (used for the parser tests)\n\n"
        "| File | What it tests |\n"
        "|---|---|\n"
        "| `synthetic_minimal.txt` | A CV with almost no content |\n"
        "| `synthetic_messy.*` | Odd headings, pipe-separated contacts, inconsistent dates, duplicate skill spellings |\n"
        "| `synthetic_empty.pdf` | A zero-byte upload |\n"
        "| `synthetic_not_really_a_pdf.pdf` | A non-PDF file with a `.pdf` extension (magic-byte check) |\n"
        "| `synthetic_image_only.pdf` | A valid PDF with no text layer (the 'scanned CV' path) |\n\n"
        "Regenerate everything with:\n\n"
        "```bash\n"
        "python scripts/make_sample_cvs.py\n"
        "```\n",
        encoding="utf-8",
    )
    written.append(readme)

    print(f"\nWrote {len(written)} file(s):")
    for path in written:
        size = path.stat().st_size if path.exists() else 0
        print(f"  {path.name:44} {size:>9,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
