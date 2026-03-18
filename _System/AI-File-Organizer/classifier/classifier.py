#!/usr/bin/env python3
"""Classification engine: reads file + taxonomy, classifies via Claude Haiku/Sonnet."""

import argparse
import json
import os
import sys

import anthropic
import yaml

from snippet_extractor import extract_snippet

HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-20250514"
CONFIDENCE_THRESHOLD = 0.70


def load_taxonomy(taxonomy_path: str) -> dict:
    with open(taxonomy_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_folder_tree(taxonomy: dict) -> str:
    """Flatten taxonomy into a readable folder list for the prompt."""
    lines = []

    def walk(folders, indent=0):
        for folder in folders:
            prefix = "  " * indent
            desc = folder.get("description", "")
            rules_str = ""
            if folder.get("rules"):
                for rule in folder["rules"]:
                    kw = [str(k) for k in rule.get("keyword_match", [])]
                    ft = [str(t) for t in rule.get("file_types", [])]
                    rules_str += f" [keywords: {', '.join(kw)}; types: {', '.join(ft)}]"
            shortcut = " (shortcut_target)" if folder.get("shortcut_target") else ""
            sensitivity = f" [sensitivity: {folder['sensitivity']}]" if folder.get("sensitivity") else ""
            lines.append(f"{prefix}- {folder['path']}: {desc}{rules_str}{shortcut}{sensitivity}")
            if folder.get("subfolders"):
                walk(folder["subfolders"], indent + 1)

    walk(taxonomy["taxonomy"]["root_folders"])
    return "\n".join(lines)


def build_prompt(filename: str, file_ext: str, snippet: str, taxonomy: dict) -> str:
    folder_tree = build_folder_tree(taxonomy)
    ai_context = taxonomy["taxonomy"].get("ai_context", "")
    snippet_display = snippet if snippet else "(no text content extracted)"

    return f"""You are a file classification engine. Given a file and a folder taxonomy, determine where the file belongs.

USER CONTEXT:
{ai_context}

FOLDER TAXONOMY:
{folder_tree}

FILE TO CLASSIFY:
- Filename: {filename}
- Extension: {file_ext}
- Content snippet: {snippet_display}

INSTRUCTIONS:
1. Analyse the filename, extension, and content snippet against the taxonomy.
2. Consider keyword matches, file type rules, folder descriptions, and user context.
3. Rules are hints, not hard filters — weigh them alongside other signals.
4. If a file could logically sit in two places, the canonical location should be the more specific folder.
5. Only populate secondary_paths if cross-domain relevance is clear and the target folder has shortcut_target: true.

Respond with ONLY valid JSON (no markdown fences, no extra text):
{{
  "suggested_path": "/path/to/folder",
  "secondary_paths": [],
  "confidence": 0.95,
  "rationale": "1-2 sentence explanation",
  "alternatives": ["/other/path1", "/other/path2"]
}}"""


def classify(filepath: str, taxonomy_path: str, verbose: bool = False, dry_run: bool = False) -> dict:
    taxonomy = load_taxonomy(taxonomy_path)
    max_words = taxonomy["taxonomy"].get("global_settings", {}).get("snippet_max_words", 200)

    filename = os.path.basename(filepath)
    file_ext = os.path.splitext(filepath)[1].lower()
    snippet = extract_snippet(filepath, max_words=max_words)

    if verbose:
        print(f"[INFO] File: {filename}", file=sys.stderr)
        print(f"[INFO] Extension: {file_ext}", file=sys.stderr)
        print(f"[INFO] Snippet ({len(snippet.split())} words): {snippet[:100]}...", file=sys.stderr)

    prompt = build_prompt(filename, file_ext, snippet, taxonomy)

    if dry_run:
        result = {
            "suggested_path": "/Inbox",
            "secondary_paths": [],
            "confidence": 0.0,
            "rationale": "Dry run — no API call made.",
            "alternatives": [],
            "escalated": False,
            "model_used": "none (dry-run)",
        }
        if verbose:
            print("[INFO] Dry run mode — skipping API call", file=sys.stderr)
        return result

    client = anthropic.Anthropic()

    # First pass: Haiku
    model_used = HAIKU_MODEL
    if verbose:
        print(f"[INFO] Calling {model_used}...", file=sys.stderr)

    response = client.messages.create(
        model=model_used,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {
            "suggested_path": "/Inbox",
            "secondary_paths": [],
            "confidence": 0.0,
            "rationale": f"Failed to parse model response: {raw[:200]}",
            "alternatives": [],
        }

    # Escalate to Sonnet if confidence < threshold
    escalated = False
    if result.get("confidence", 0) < CONFIDENCE_THRESHOLD:
        escalated = True
        model_used = SONNET_MODEL
        if verbose:
            print(f"[INFO] Confidence {result.get('confidence', 0):.2f} < {CONFIDENCE_THRESHOLD} — escalating to {model_used}", file=sys.stderr)

        response = client.messages.create(
            model=model_used,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = {
                "suggested_path": "/Inbox",
                "secondary_paths": [],
                "confidence": 0.0,
                "rationale": f"Failed to parse Sonnet response: {raw[:200]}",
                "alternatives": [],
            }

    result["escalated"] = escalated
    result["model_used"] = model_used
    return result


def main():
    parser = argparse.ArgumentParser(description="Classify a file using AI and a taxonomy.")
    parser.add_argument("--file", required=True, help="Path to the file to classify.")
    parser.add_argument("--taxonomy", required=True, help="Path to taxonomy.yaml.")
    parser.add_argument("--verbose", action="store_true", help="Print debug info to stderr.")
    parser.add_argument("--dry-run", action="store_true", help="Skip API calls, return placeholder result.")
    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print(json.dumps({"error": f"File not found: {args.file}"}), file=sys.stdout)
        sys.exit(1)

    if not os.path.isfile(args.taxonomy):
        print(json.dumps({"error": f"Taxonomy not found: {args.taxonomy}"}), file=sys.stdout)
        sys.exit(1)

    result = classify(args.file, args.taxonomy, verbose=args.verbose, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
