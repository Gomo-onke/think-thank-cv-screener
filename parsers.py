"""CV text extraction from PDF / DOCX / TXT. Identical in Build 1 and Build 2."""
from __future__ import annotations

import io
import os

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def extract_text(filename: str, data: bytes) -> str:
    """Return plain text from an uploaded CV. Raises ValueError with a
    user-presentable message if the file can't be read."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type '{ext or 'unknown'}'. Upload a PDF, DOCX or TXT file.")
    if not data:
        raise ValueError("The uploaded file is empty.")

    try:
        if ext == ".pdf":
            import pdfplumber
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                text = "\n".join((page.extract_text() or "") for page in pdf.pages)
        elif ext == ".docx":
            import docx
            document = docx.Document(io.BytesIO(data))
            parts = [p.text for p in document.paragraphs]
            for table in document.tables:  # CVs often put skills/jobs in tables
                for row in table.rows:
                    parts.extend(cell.text for cell in row.cells)
            text = "\n".join(parts)
        else:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = data.decode("latin-1")
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Could not read {ext.upper().lstrip('.')} file: {exc}") from exc

    text = text.strip()
    if not text:
        raise ValueError(
            "No text could be extracted from the file (it may be a scanned image). "
            "Paste the CV text instead, or upload a text-based PDF."
        )
    return text
