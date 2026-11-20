"""
Shared pytest fixtures.

The whole suite runs against the OFFLINE LLM engine on purpose. A sampling
language model gives different output every run, which would make the tests
either flaky or so loose that they assert nothing. The offline engine is
deterministic, so these tests check the application's own logic -- parsing,
normalisation, matching, guards, state machine, persistence, HTTP contract --
rather than the model's mood.

The tests that genuinely need a model or a network are marked and skipped by
default; see `tests/test_integration_live.py`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Must be set before app.core.config is imported anywhere.
os.environ.setdefault("LLM_PROVIDER", "offline")
os.environ.setdefault("SCRAPE_ENABLED", "false")
os.environ.setdefault("LOG_LEVEL", "WARNING")


@pytest.fixture(scope="session", autouse=True)
def _test_database(tmp_path_factory: pytest.TempPathFactory):
    """Point the app at a throwaway database for the whole session."""
    from app.core import config

    db_path = tmp_path_factory.mktemp("db") / "test.db"
    object.__setattr__(config.settings, "database_path", db_path)

    from app.core.db import init_db

    init_db()
    yield db_path


@pytest.fixture(autouse=True)
def _offline_llm():
    """Guarantee every test sees the deterministic engine."""
    from app.core import config
    from app.services.llm.client import reset_llm

    object.__setattr__(config.settings, "llm_provider", "offline")
    reset_llm()
    yield
    reset_llm()


@pytest.fixture
def client():
    """FastAPI test client."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def clean_db():
    """Empty the database before a test that counts rows."""
    from app.core.db import reset_database

    reset_database()
    yield
    reset_database()


@pytest.fixture(scope="session")
def sample_cv_dir() -> Path:
    directory = BACKEND_DIR.parent / "evaluation" / "sample_cvs"
    if not directory.exists():
        pytest.skip("Synthetic CVs are missing. Run: python scripts/make_sample_cvs.py")
    return directory


@pytest.fixture(scope="session")
def software_engineer_cv_text(sample_cv_dir: Path) -> str:
    path = sample_cv_dir / "synthetic_software_engineer.txt"
    if not path.exists():
        pytest.skip("synthetic_software_engineer.txt is missing")
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def software_engineer_pdf(sample_cv_dir: Path) -> bytes:
    path = sample_cv_dir / "synthetic_software_engineer.pdf"
    if not path.exists():
        pytest.skip("synthetic_software_engineer.pdf is missing")
    return path.read_bytes()


@pytest.fixture(scope="session")
def data_analyst_docx(sample_cv_dir: Path) -> bytes:
    path = sample_cv_dir / "synthetic_data_analyst.docx"
    if not path.exists():
        pytest.skip("synthetic_data_analyst.docx is missing")
    return path.read_bytes()

@pytest.fixture
def cv_and_role(client, software_engineer_pdf: bytes):
    """
    An uploaded CV and an analysed role, the starting point for the gap,
    improvement and interview endpoints. Shared here because several test
    modules need the same pair.
    """
    cv = client.post(
        "/api/cv/upload",
        files={"file": ("cv.pdf", software_engineer_pdf, "application/pdf")},
    ).json()
    role = client.post(
        "/api/roles/analyse",
        json={"role_title": "Software Engineer", "use_scraping": False, "use_llm": True},
    ).json()
    return cv, role
