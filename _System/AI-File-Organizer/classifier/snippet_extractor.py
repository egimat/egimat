"""Snippet extractor for the AI File Organizer classification engine.

Extracts up to 200 words of text content from various file formats
to provide context for AI-based classification.
"""

import os
import csv
import io


def extract_snippet(filepath: str) -> str:
    """Extract a text snippet (up to 200 words) from a file.

    Supported formats:
        .txt, .md  — first 200 words of raw text
        .pdf       — first 200 words via pdfplumber
        .docx      — first 200 words via python-docx
        .csv       — column headers + first 5 rows
        .xlsx      — column headers + first 5 rows via openpyxl

    Returns empty string for images, binary, and unknown formats.
    Never raises exceptions.
    """
    try:
        ext = os.path.splitext(filepath)[1].lower()

        if ext in (".txt", ".md"):
            return _extract_text(filepath)
        elif ext == ".pdf":
            return _extract_pdf(filepath)
        elif ext == ".docx":
            return _extract_docx(filepath)
        elif ext == ".csv":
            return _extract_csv(filepath)
        elif ext == ".xlsx":
            return _extract_xlsx(filepath)
        else:
            return ""
    except Exception:
        return ""


def _truncate_words(text: str, max_words: int = 200) -> str:
    words = text.split()
    return " ".join(words[:max_words])


def _extract_text(filepath: str) -> str:
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return _truncate_words(content)
    except Exception:
        return ""


def _extract_pdf(filepath: str) -> str:
    try:
        import pdfplumber

        text_parts = []
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
                if len(" ".join(text_parts).split()) >= 200:
                    break
        return _truncate_words(" ".join(text_parts))
    except Exception:
        return ""


def _extract_docx(filepath: str) -> str:
    try:
        from docx import Document

        doc = Document(filepath)
        text_parts = []
        for para in doc.paragraphs:
            if para.text.strip():
                text_parts.append(para.text)
            if len(" ".join(text_parts).split()) >= 200:
                break
        return _truncate_words(" ".join(text_parts))
    except Exception:
        return ""


def _extract_csv(filepath: str) -> str:
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            rows = []
            for i, row in enumerate(reader):
                rows.append(row)
                if i >= 5:  # header + 5 data rows
                    break

        if not rows:
            return ""

        lines = []
        lines.append("Columns: " + ", ".join(rows[0]))
        for row in rows[1:]:
            lines.append(" | ".join(row))
        return _truncate_words("\n".join(lines))
    except Exception:
        return ""


def _extract_xlsx(filepath: str) -> str:
    try:
        from openpyxl import load_workbook

        wb = load_workbook(filepath, read_only=True, data_only=True)
        ws = wb.active

        rows = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            rows.append([str(cell) if cell is not None else "" for cell in row])
            if i >= 5:
                break
        wb.close()

        if not rows:
            return ""

        lines = []
        lines.append("Columns: " + ", ".join(rows[0]))
        for row in rows[1:]:
            lines.append(" | ".join(row))
        return _truncate_words("\n".join(lines))
    except Exception:
        return ""
