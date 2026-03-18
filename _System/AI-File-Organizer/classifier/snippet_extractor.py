"""Extract text snippets from various file types for classification."""

import csv
import io
from pathlib import Path


def extract_snippet(filepath: str) -> str:
    """Extract a text snippet from a file for AI classification.

    Supports .txt, .md, .pdf, .docx, .csv, .xlsx.
    Returns empty string for binary/unknown types.
    Never raises exceptions.
    """
    try:
        path = Path(filepath)
        ext = path.suffix.lower()

        if ext in (".txt", ".md"):
            return _extract_text(path)
        elif ext == ".pdf":
            return _extract_pdf(path)
        elif ext == ".docx":
            return _extract_docx(path)
        elif ext == ".csv":
            return _extract_csv(path)
        elif ext == ".xlsx":
            return _extract_xlsx(path)
        else:
            return ""
    except Exception:
        return ""


def _extract_text(path: Path) -> str:
    """Read plain text and return first 200 words."""
    text = path.read_text(encoding="utf-8", errors="replace")
    words = text.split()
    return " ".join(words[:200])


def _extract_pdf(path: Path) -> str:
    """Extract text from PDF using pdfplumber, first 200 words."""
    import pdfplumber

    text_parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
            words_so_far = " ".join(text_parts).split()
            if len(words_so_far) >= 200:
                break
    words = " ".join(text_parts).split()
    return " ".join(words[:200])


def _extract_docx(path: Path) -> str:
    """Extract text from .docx using python-docx, first 200 words."""
    import docx

    doc = docx.Document(str(path))
    text_parts = []
    for para in doc.paragraphs:
        if para.text.strip():
            text_parts.append(para.text)
        words_so_far = " ".join(text_parts).split()
        if len(words_so_far) >= 200:
            break
    words = " ".join(text_parts).split()
    return " ".join(words[:200])


def _extract_csv(path: Path) -> str:
    """Extract headers + first 5 rows from CSV as text."""
    text = path.read_text(encoding="utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    lines = []
    for i, row in enumerate(reader):
        if i > 5:
            break
        lines.append(", ".join(row))
    return "\n".join(lines)


def _extract_xlsx(path: Path) -> str:
    """Extract headers + first 5 rows from .xlsx using openpyxl."""
    import openpyxl

    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    sheet = wb.active
    lines = []
    for i, row in enumerate(sheet.iter_rows(max_row=6, values_only=True)):
        cells = [str(c) if c is not None else "" for c in row]
        lines.append(", ".join(cells))
    wb.close()
    return "\n".join(lines)
