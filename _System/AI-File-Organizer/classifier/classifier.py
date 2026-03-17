"""Classification engine for the AI File Organizer.

Classifies files into a user-defined taxonomy using the Claude API.
Uses Haiku by default, escalates to Sonnet when confidence < 0.70.
"""

import argparse
import json
import mimetypes
import os
import sys
from datetime import datetime

import yaml

from snippet_extractor import extract_snippet

HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-5-20241022"
CONFIDENCE_THRESHOLD = 0.70

OUTPUT_SCHEMA = {
    "suggested_path": "string — primary taxonomy path for the file",
    "secondary_paths": "list[string] — additional paths (shortcut_target folders)",
    "confidence": "float — 0.0 to 1.0",
    "rationale": "string — brief explanation of the classification",
    "alternatives": "list[string] — other plausible paths considered",
    "escalate": "boolean — true if confidence < 0.70",
}


def get_file_metadata(filepath: str) -> dict:
    """Extract file metadata for classification."""
    stat = os.stat(filepath)
    mime_type, _ = mimetypes.guess_type(filepath)

    return {
        "filename": os.path.basename(filepath),
        "extension": os.path.splitext(filepath)[1].lower(),
        "size_bytes": stat.st_size,
        "created_date": datetime.fromtimestamp(stat.st_ctime).isoformat(),
        "modified_date": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "mime_type": mime_type or "unknown",
    }


def load_taxonomy(taxonomy_path: str) -> str:
    """Load taxonomy YAML file and return its raw content."""
    with open(taxonomy_path, "r") as f:
        content = f.read()
    # Validate it parses as YAML
    yaml.safe_load(content)
    return content


def build_system_prompt(taxonomy_content: str) -> str:
    """Build the system prompt with taxonomy and instructions."""
    return f"""You are a file classification engine. Your job is to classify a file into the most appropriate folder in the user's taxonomy.

## Taxonomy

{taxonomy_content}

## Instructions

1. Analyze the file metadata and text snippet provided by the user.
2. Determine the best matching folder path from the taxonomy above.
3. The `ai_context` field on each taxonomy node is the HIGHEST-SIGNAL indicator of what belongs in that folder. Prioritize it above all other signals.
4. The `rules` on taxonomy nodes are WEIGHTED HINTS, not hard filters. Use them as additional signals alongside `ai_context` and actual file content analysis. A file can match a folder even without matching any rule pattern.
5. Folders with `shortcut_target: true` are candidates for the `secondary_paths` field. If a file logically belongs in multiple places, list shortcut_target folders as secondary paths.
6. Set `confidence` between 0.0 and 1.0 based on how certain you are about the classification.
7. Set `escalate` to true if your confidence is below 0.70.

## Output Format

Return ONLY valid JSON matching this exact schema. No markdown fences, no preamble, no explanation outside the JSON object.

{{
  "suggested_path": "/path/to/folder",
  "secondary_paths": ["/other/path"],
  "confidence": 0.85,
  "rationale": "Brief explanation of why this classification was chosen",
  "alternatives": ["/alternative/path"],
  "escalate": false
}}"""


def build_user_message(metadata: dict, snippet: str) -> str:
    """Build the user message with file metadata and snippet."""
    lines = ["Classify this file:\n", "## File Metadata"]
    for key, value in metadata.items():
        lines.append(f"- {key}: {value}")

    lines.append("\n## Text Content")
    if snippet.strip():
        lines.append(snippet)
    else:
        lines.append("No text content available")

    return "\n".join(lines)


def classify_with_model(
    system_prompt: str, user_message: str, model: str, verbose: bool = False
) -> dict:
    """Send classification request to Claude API and parse response."""
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    if verbose:
        print("\n--- SYSTEM PROMPT ---")
        print(system_prompt)
        print("\n--- USER MESSAGE ---")
        print(user_message)
        print("--- END ---\n")

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    raw_text = response.content[0].text.strip()

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        print(f"Error: Failed to parse API response as JSON:\n{raw_text}", file=sys.stderr)
        sys.exit(1)

    return result


def classify_file(
    filepath: str, taxonomy_path: str, verbose: bool = False
) -> dict:
    """Classify a file using the taxonomy. Escalates from Haiku to Sonnet if needed."""
    metadata = get_file_metadata(filepath)
    snippet = extract_snippet(filepath)
    taxonomy_content = load_taxonomy(taxonomy_path)

    system_prompt = build_system_prompt(taxonomy_content)
    user_message = build_user_message(metadata, snippet)

    # First attempt with Haiku
    if verbose:
        print(f"Classifying with {HAIKU_MODEL}...")

    result = classify_with_model(system_prompt, user_message, HAIKU_MODEL, verbose)

    # Escalation check
    confidence = result.get("confidence", 0)
    escalate = result.get("escalate", False)

    if confidence < CONFIDENCE_THRESHOLD or escalate:
        if verbose:
            print(
                f"\nEscalating to {SONNET_MODEL} "
                f"(confidence={confidence}, escalate={escalate})..."
            )
        result = classify_with_model(system_prompt, user_message, SONNET_MODEL, verbose)

    return result


def dry_run(filepath: str, taxonomy_path: str) -> None:
    """Extract metadata and snippet without making an API call."""
    metadata = get_file_metadata(filepath)
    snippet = extract_snippet(filepath)

    # Validate taxonomy loads
    load_taxonomy(taxonomy_path)

    print("=== DRY RUN ===\n")
    print("File Metadata:")
    for key, value in metadata.items():
        print(f"  {key}: {value}")

    print(f"\nText Snippet ({len(snippet.split())} words):")
    if snippet.strip():
        print(f"  {snippet[:500]}{'...' if len(snippet) > 500 else ''}")
    else:
        print("  No text content available")

    print(f"\nTaxonomy: loaded successfully")
    print("\n=== No API call made ===")


def main():
    parser = argparse.ArgumentParser(
        description="AI File Organizer — Classification Engine"
    )
    parser.add_argument(
        "--file", required=True, help="Path to the file to classify"
    )
    parser.add_argument(
        "--taxonomy", required=True, help="Path to taxonomy.yaml"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print the prompt sent to the API"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract metadata and snippet without calling the API",
    )

    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(args.taxonomy):
        print(f"Error: Taxonomy file not found: {args.taxonomy}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        dry_run(args.file, args.taxonomy)
    else:
        result = classify_file(args.file, args.taxonomy, verbose=args.verbose)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
