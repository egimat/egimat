"""CLI classifier: reads a file, extracts metadata and content, and classifies it via Claude."""

import argparse
import json
import mimetypes
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import yaml

from snippet_extractor import extract_snippet

HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-20250514"
CONFIDENCE_THRESHOLD = 0.70


def load_taxonomy(taxonomy_path: str) -> dict:
    """Load taxonomy YAML from disk."""
    with open(taxonomy_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_file_metadata(filepath: str) -> dict:
    """Gather file metadata: name, extension, size, dates, MIME type."""
    path = Path(filepath)
    stat = path.stat()
    mime_type, _ = mimetypes.guess_type(str(path))
    return {
        "filename": path.name,
        "extension": path.suffix.lower(),
        "size_bytes": stat.st_size,
        "created": datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat(),
        "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "mime_type": mime_type or "application/octet-stream",
    }


def build_system_prompt(taxonomy: dict) -> str:
    """Build the system prompt with full taxonomy and JSON output instruction."""
    taxonomy_yaml = yaml.dump(taxonomy, default_flow_style=False, allow_unicode=True)
    return f"""You are a file classification engine. Given a file's metadata and content snippet, classify it into the most appropriate folder in the taxonomy below.

TAXONOMY:
{taxonomy_yaml}

You MUST respond with ONLY valid JSON in this exact schema:
{{
  "suggested_path": "<primary folder path>",
  "secondary_paths": ["<shortcut paths if applicable>"],
  "confidence": <float 0.0-1.0>,
  "rationale": "<brief explanation>",
  "alternatives": [
    {{"path": "<alt path>", "confidence": <float>}}
  ],
  "escalate": <true if ambiguous and needs human review, false otherwise>
}}

Do not include any text outside the JSON object."""


def classify_file(
    filepath: str,
    taxonomy_path: str,
    verbose: bool = False,
    dry_run: bool = False,
) -> dict:
    """Classify a file using Claude API with escalation logic."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    metadata = get_file_metadata(filepath)
    snippet = extract_snippet(filepath)
    taxonomy = load_taxonomy(taxonomy_path)

    system_prompt = build_system_prompt(taxonomy)
    user_message = (
        f"File metadata:\n{json.dumps(metadata, indent=2)}\n\n"
        f"Content snippet:\n{snippet if snippet else '(no text content extracted)'}"
    )

    if verbose:
        print(f"Metadata: {json.dumps(metadata, indent=2)}", file=sys.stderr)
        print(f"Snippet length: {len(snippet)} chars", file=sys.stderr)

    if dry_run:
        return {
            "suggested_path": "(dry run)",
            "secondary_paths": [],
            "confidence": 0.0,
            "rationale": "Dry run — no API call made.",
            "alternatives": [],
            "escalate": False,
            "model_used": "none",
            "metadata": metadata,
            "snippet_preview": snippet[:200] if snippet else "",
        }

    client = anthropic.Anthropic(api_key=api_key)

    # First pass with Haiku
    if verbose:
        print(f"Calling {HAIKU_MODEL}...", file=sys.stderr)

    result = _call_claude(client, HAIKU_MODEL, system_prompt, user_message)
    model_used = HAIKU_MODEL

    # Escalate to Sonnet if confidence is below threshold
    if result.get("confidence", 0) < CONFIDENCE_THRESHOLD:
        if verbose:
            print(
                f"Confidence {result.get('confidence', 0):.2f} < {CONFIDENCE_THRESHOLD}, "
                f"escalating to {SONNET_MODEL}...",
                file=sys.stderr,
            )
        result = _call_claude(client, SONNET_MODEL, system_prompt, user_message)
        model_used = SONNET_MODEL

    result["model_used"] = model_used
    return result


def _call_claude(
    client: anthropic.Anthropic,
    model: str,
    system_prompt: str,
    user_message: str,
) -> dict:
    """Send a classification request to Claude and parse the JSON response."""
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    text = response.content[0].text.strip()
    return json.loads(text)


def main():
    parser = argparse.ArgumentParser(
        description="Classify a file into the taxonomy using Claude."
    )
    parser.add_argument("--file", required=True, help="Path to the file to classify.")
    parser.add_argument(
        "--taxonomy",
        required=True,
        help="Path to taxonomy.yaml.",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print debug info to stderr."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Gather metadata and snippet without calling the API.",
    )
    args = parser.parse_args()

    filepath = args.file
    if not Path(filepath).is_file():
        print(f"Error: file not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    result = classify_file(
        filepath=filepath,
        taxonomy_path=args.taxonomy,
        verbose=args.verbose,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
