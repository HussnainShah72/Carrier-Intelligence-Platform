"""
Module 1a - getting text out of an uploaded CV safely.

Handles PDF, DOCX and plain text, and treats every upload as hostile until
proven otherwise:

  * size limit enforced before anything is parsed
  * extension AND magic-byte check (a .pdf that is really a .exe is rejected)
  * zip-bomb guard on DOCX (declared uncompressed size is checked)
  * encrypted PDFs detected and reported, not crashed on
  * a second extraction engine is tried when the first yields nothing
  * image-only (scanned) PDFs are identified and explained to the user, rather
    than silently returning an empty profile
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.core.errors import (
    EmptyDocumentError,
    ExtractionError,
    FileTooLargeError,
    UnsupportedFileError,
)
from app.core.logging_setup import get_logger
from app.services.skills.text_norm import clean_unicode

log = get_logger(__name__)

# Magic bytes we accept.
_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")  # DOCX is a zip
_DOCX_MAX_UNCOMPRESSED = 60 * 1024 * 1024  # zip-bomb guard
_MIN_USEFUL_CHARS = 120


@dataclass(slots=True)
class ExtractedDocument:
    text: str
    file_type: str
    extractor: str
    size_bytes: int
    sha256: str
    page_count: int = 0
    warnings: list[str] | None = None

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []

    @property
    def char_count(self) -> int:
        return len(self.text)


def extract_document(filename: str, data: bytes) -> ExtractedDocument:
    """
    Validate an upload and return its text.

    Raises UnsupportedFileError / FileTooLargeError / ExtractionError /
    EmptyDocumentError -- all of which carry a message safe to show the user.
    """
    if not data:
        raise EmptyDocumentError("The uploaded file is empty (0 bytes).")

    size = len(data)
    if size > settings.max_upload_bytes:
        raise FileTooLargeError(
            f"That file is {size / 1_048_576:.1f} MB. The limit is "
            f"{settings.max_upload_bytes / 1_048_576:.0f} MB."
        )

    suffix = Path(filename or "").suffix.lower()
    if suffix not in settings.allowed_suffixes:
        allowed = ", ".join(sorted(settings.allowed_suffixes))
        raise UnsupportedFileError(
            f"'{suffix or 'no extension'}' is not a supported CV format. Please upload one of: {allowed}."
        )

    digest = hashlib.sha256(data).hexdigest()
    warnings: list[str] = []

    if suffix == ".pdf":
        _assert_magic(data, (_PDF_MAGIC,), "PDF")
        text, extractor, pages, extra = _extract_pdf(data)
    elif suffix == ".docx":
        _assert_magic(data, _ZIP_MAGIC, "Word (.docx)")
        _guard_zip_bomb(data)
        text, extractor, pages, extra = _extract_docx(data)
    else:  # .txt
        text, extractor, pages, extra = _extract_txt(data)

    warnings.extend(extra)
    text = _tidy(text)

    if not text.strip():
        raise EmptyDocumentError(
            "No text could be read from this file. If it is a scanned CV (an image inside a PDF), "
            "please upload a text-based PDF or a Word document instead - this tool does not run OCR."
        )

    if len(text) < _MIN_USEFUL_CHARS:
        warnings.append(
            f"Only {len(text)} characters of text were found. The extracted profile will be very limited."
        )

    if len(text) > settings.max_cv_characters:
        warnings.append(
            f"The document is long ({len(text):,} characters); only the first "
            f"{settings.max_cv_characters:,} characters were analysed."
        )
        text = text[: settings.max_cv_characters]

    log.info(
        "Extracted %s via %s: %d chars, %d page(s), %d warning(s)",
        suffix, extractor, len(text), pages, len(warnings),
    )
    return ExtractedDocument(
        text=text,
        file_type=suffix.lstrip("."),
        extractor=extractor,
        size_bytes=size,
        sha256=digest,
        page_count=pages,
        warnings=warnings,
    )


def _assert_magic(data: bytes, magics: tuple[bytes, ...], label: str) -> None:
    head = data[:8]
    if not any(head.startswith(m) for m in magics):
        raise UnsupportedFileError(
            f"This file does not look like a real {label} document. Its contents do not match its extension."
        )


def _guard_zip_bomb(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            total = sum(info.file_size for info in archive.infolist())
            if total > _DOCX_MAX_UNCOMPRESSED:
                raise UnsupportedFileError(
                    "This Word file expands to an unreasonable size and was rejected as unsafe."
                )
            if not any(info.filename == "word/document.xml" for info in archive.infolist()):
                raise UnsupportedFileError(
                    "This .docx file has no document body. It may be corrupt or not really a Word file."
                )
    except zipfile.BadZipFile as exc:
        raise ExtractionError("This Word file appears to be corrupt and could not be opened.") from exc


# ------------------------------------------------------------------ PDF ----


def _extract_pdf(data: bytes) -> tuple[str, str, int, list[str]]:
    warnings: list[str] = []

    # Primary: pdfplumber (best layout fidelity for CV columns).
    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = len(pdf.pages)
            chunks: list[str] = []
            for page in pdf.pages:
                chunks.append(page.extract_text(x_tolerance=1.6, y_tolerance=2.4) or "")
                for table in page.extract_tables() or []:
                    for row in table:
                        cells = [c.strip() for c in row if c and c.strip()]
                        if cells:
                            chunks.append(" | ".join(cells))
            text = "\n".join(c for c in chunks if c)
        if text.strip():
            return text, "pdfplumber", pages, warnings
        warnings.append("pdfplumber found no text layer; retried with pypdf.")
    except Exception as exc:
        message = str(exc).lower()
        if "password" in message or "encrypt" in message:
            raise ExtractionError(
                "This PDF is password-protected. Please remove the password and upload it again."
            ) from exc
        log.warning("pdfplumber failed: %s", exc)
        warnings.append("The primary PDF reader failed; a fallback reader was used.")

    # Fallback: pypdf.
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(io.BytesIO(data))
        if getattr(reader, "is_encrypted", False):
            try:
                reader.decrypt("")  # many CVs are encrypted with an empty owner password
            except Exception as exc:
                raise ExtractionError(
                    "This PDF is password-protected. Please remove the password and upload it again."
                ) from exc
        pages = len(reader.pages)
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        if text.strip():
            return text, "pypdf", pages, warnings
        warnings.append(
            "Neither PDF reader found a text layer. This is almost certainly a scanned/image-only PDF."
        )
        return "", "pypdf", pages, warnings
    except ExtractionError:
        raise
    except Exception as exc:
        log.error("Both PDF extractors failed: %s", exc)
        raise ExtractionError(
            "This PDF could not be read. It may be corrupt. Try re-exporting it, or upload a Word version."
        ) from exc


# ----------------------------------------------------------------- DOCX ----


def _extract_docx(data: bytes) -> tuple[str, str, int, list[str]]:
    warnings: list[str] = []
    try:
        import docx  # type: ignore

        document = docx.Document(io.BytesIO(data))
        lines: list[str] = [p.text for p in document.paragraphs]

        # CV layouts very often hide the real content inside tables.
        for table in document.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text and c.text.strip()]
                if cells:
                    lines.append(" | ".join(dict.fromkeys(cells)))

        # Headers/footers sometimes hold the contact block.
        for section in document.sections:
            for container in (section.header, section.footer):
                for paragraph in container.paragraphs:
                    if paragraph.text.strip():
                        lines.append(paragraph.text.strip())

        text = "\n".join(line for line in lines if line is not None)
        if not text.strip():
            warnings.append("The Word document contains no readable paragraphs or tables.")
        return text, "python-docx", 0, warnings
    except Exception as exc:
        log.error("DOCX extraction failed: %s", exc)
        raise ExtractionError(
            "This Word document could not be read. If it is an old .doc file, please save it as .docx first."
        ) from exc


# ------------------------------------------------------------------ TXT ----


def _extract_txt(data: bytes) -> tuple[str, str, int, list[str]]:
    warnings: list[str] = []
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding), f"text/{encoding}", 0, warnings
        except UnicodeDecodeError:
            continue
    warnings.append("The text file had an unrecognised encoding; undecodable characters were replaced.")
    return data.decode("utf-8", errors="replace"), "text/replace", 0, warnings


# ---------------------------------------------------------------- tidying ---


def _tidy(text: str) -> str:
    """Normalise whitespace while preserving the line structure the parser needs."""
    text = clean_unicode(text or "")
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]

    out: list[str] = []
    blanks = 0
    for line in lines:
        # Collapse runs of spaces inside a line, but keep leading indentation.
        stripped = line.strip()
        if not stripped:
            blanks += 1
            if blanks <= 1:
                out.append("")
            continue
        blanks = 0
        out.append(" ".join(stripped.split()))
    return "\n".join(out).strip()
