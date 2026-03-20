"""Classification engine — reads taxonomy + file content, suggests folder placement."""

import json
import os
import re
from datetime import datetime
from pathlib import Path

import anthropic
import yaml


def load_taxonomy(taxonomy_path: str) -> dict:
    with open(taxonomy_path, "r") as f:
        return yaml.safe_load(f)


def extract_snippet(file_path: str, max_words: int = 200) -> str:
    """Extract text snippet from a file for classification."""
    try:
        with open(file_path, "r", errors="replace") as f:
            text = f.read()
        words = text.split()[:max_words]
        return " ".join(words)
    except Exception:
        return ""


def build_system_prompt(taxonomy: dict) -> str:
    """Build the system prompt for the classification model."""
    tax = taxonomy["taxonomy"]
    folders_desc = _describe_folders(tax.get("root_folders", []))
    ai_context = tax.get("ai_context", "")

    return f"""You are a file classification engine for a personal document organizer.

TAXONOMY (folder tree):
{folders_desc}

USER CONTEXT:
{ai_context}

CLASSIFICATION RULES:
- Rules on folders are HINTS, not hard filters. Weigh them alongside folder name, description, and file content.
- Within a rule block: all conditions are AND. Across blocks: OR.
- A file has exactly ONE canonical path and zero or more shortcut paths.
- shortcut_target folders are candidates for secondary_paths when cross-domain relevance is clear.
- If confidence < 0.70, set escalate: true.

FILE NAMING:
- Suggest a standardized filename using this convention: YYYY-MM — Description — Source.ext
- YYYY-MM is the content date at month precision. Derive it from the document content (e.g. invoice date, statement period, letter date).
- If the content date cannot be determined, fall back to the file's last-modified date.
- If no date is available at all, use "UNDATED" in place of YYYY-MM.
- Description is a short, human-readable summary of the document (2-6 words, title case).
- Source is the issuing entity or author (e.g. "Amazon", "Agenzia Entrate", "Dr Rossi").
- Keep the original file extension.

OUTPUT FORMAT:
Return a single JSON object with these fields:
{{
  "suggested_path": "/path/to/folder",
  "suggested_name": "YYYY-MM — Description — Source.ext",
  "secondary_paths": [],
  "confidence": 0.0,
  "rationale": "1-2 sentences",
  "alternatives": [],
  "escalate": false
}}
Return ONLY the JSON object, no other text."""


def _describe_folders(folders: list, indent: int = 0) -> str:
    """Recursively describe the folder tree for the system prompt."""
    lines = []
    prefix = "  " * indent
    for f in folders:
        line = f"{prefix}- {f['path']}"
        if f.get("description"):
            line += f": {f['description']}"
        extras = []
        if f.get("sensitivity"):
            extras.append(f"sensitivity={f['sensitivity']}")
        if f.get("shortcut_target"):
            extras.append("shortcut_target")
        if f.get("automation_override"):
            extras.append(f"automation={f['automation_override']}")
        if extras:
            line += f" [{', '.join(extras)}]"
        lines.append(line)
        if f.get("rules"):
            for rule in f["rules"]:
                parts = []
                if rule.get("keyword_match"):
                    parts.append(f"keywords: {rule['keyword_match']}")
                if rule.get("file_types"):
                    parts.append(f"types: {rule['file_types']}")
                lines.append(f"{prefix}  rule: {'; '.join(parts)}")
        if f.get("subfolders"):
            lines.append(_describe_folders(f["subfolders"], indent + 1))
    return "\n".join(lines)


def classify_file(
    file_path: str,
    taxonomy: dict,
    file_modified_date: str | None = None,
) -> dict:
    """Classify a file using the Anthropic API.

    Returns a dict with: suggested_path, suggested_name, secondary_paths,
    confidence, rationale, alternatives, escalate.
    """
    client = anthropic.Anthropic()
    snippet = extract_snippet(
        file_path,
        taxonomy["taxonomy"].get("global_settings", {}).get("snippet_max_words", 200),
    )
    filename = os.path.basename(file_path)
    ext = Path(file_path).suffix

    mod_date_str = file_modified_date or ""
    if not mod_date_str:
        try:
            mtime = os.path.getmtime(file_path)
            mod_date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
        except Exception:
            mod_date_str = "unknown"

    user_message = (
        f"Filename: {filename}\n"
        f"Extension: {ext}\n"
        f"File modified date: {mod_date_str}\n"
        f"Content snippet:\n{snippet}"
    )

    system_prompt = build_system_prompt(taxonomy)

    # First try with Haiku
    model = "claude-haiku-4-5-20251001"
    response = client.messages.create(
        model=model,
        max_tokens=512,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    result = _parse_response(response.content[0].text)
    result["model_used"] = "haiku"

    # Escalate to Sonnet if low confidence
    if result.get("escalate", False) or result.get("confidence", 0) < 0.70:
        model = "claude-sonnet-4-6"
        response = client.messages.create(
            model=model,
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        result = _parse_response(response.content[0].text)
        result["model_used"] = "sonnet"

    return result


def _parse_response(text: str) -> dict:
    """Parse the JSON response from the model."""
    text = text.strip()
    # Try to extract JSON from possible markdown code blocks
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = {
            "suggested_path": "/Inbox",
            "suggested_name": "",
            "secondary_paths": [],
            "confidence": 0.0,
            "rationale": "Failed to parse model response",
            "alternatives": [],
            "escalate": True,
        }
    # Ensure all expected keys
    data.setdefault("suggested_path", "/Inbox")
    data.setdefault("suggested_name", "")
    data.setdefault("secondary_paths", [])
    data.setdefault("confidence", 0.0)
    data.setdefault("rationale", "")
    data.setdefault("alternatives", [])
    data.setdefault("escalate", False)
    return data
