"""Logging configuration: readable console output plus a rotating file log."""

from __future__ import annotations

import logging
import logging.handlers
import sys

from app.core.config import LOG_DIR, settings

_CONFIGURED = False


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    console_fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)-28s | %(message)s", "%H:%M:%S")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(console_fmt)
    root.addHandler(console)

    file_fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "backend.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(file_fmt)
    root.addHandler(file_handler)

    # Third-party chatter we do not need.
    for noisy in ("httpx", "httpcore", "urllib3", "faster_whisper", "multipart", "pdfminer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
