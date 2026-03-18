# Classification Engine — Build Spec
## For use as context in Claude Code

### What to build
A standalone Python script (`classifier.py`) that classifies a file into the user's folder taxonomy using the Claude API. Must be testable from the command line against real files before any UI or watcher exists.

### Interface

**Input:**
- File metadata: name, extension, size_bytes, created_date, modified_date, mime_type
- Text snippet: up to 200 words, extracted locally from the file
- taxonomy.yaml: full document (loaded from disk)

**Output (JSON):**
```json
{
  "suggested_path": "/Work/Clients/Acme",
  "secondary_paths": ["/Personal/Tax/2025"],
  "confidence": 0.85,
  "rationale": "Invoice from Acme Corp, dated March 2025. Primary location by client, shortcut in tax folder for fiscal year retrieval.",
  "alternatives": ["/Work/Invoices", "/Finance"],
  "escalate": false
}
```

### Key rules
- `secondary_paths`: optional. Only populated when cross-domain relevance is clear. AI draws candidates from folders where `shortcut_target: true` in the taxonomy.
- `escalate`: true if confidence < 0.70. Caller will re-run with Sonnet instead of Haiku.
- `alternatives`: up to 2 other plausible paths. Empty list if confidence > 0.95.
- `rationale`: 1-2 sentences. Must reference specific taxonomy signals (folder name, rule match, ai_context).

### Model strategy
- Default: `claude-haiku-4-5-20251001` (cheap, fast).
- Escalation: `claude-sonnet-4-20250514` (only when confidence < 0.70 on first pass).
- The script handles escalation internally: classify with Haiku first, if escalate=true, re-classify with Sonnet automatically.

### Prompt design guidance
The system prompt to Claude should include:
1. The full taxonomy.yaml content.
2. Instruction to return ONLY valid JSON matching the output schema.
3. Instruction to use `shortcut_target: true` folders when considering secondary_paths.
4. Instruction that rules are weighted hints, not hard filters.
5. The ai_context field should be emphasised as the highest-signal section.

The user message should contain:
1. File metadata (all fields).
2. Text snippet (if available; some files like images will have none).

### Snippet extraction
Build a helper function `extract_snippet(filepath) -> str` that handles:
- `.txt`, `.md`: first 200 words.
- `.pdf`: first 200 words via `PyPDF2` or `pdfplumber`.
- `.docx`: first 200 words via `python-docx`.
- `.csv`, `.xlsx`: column headers + first 5 rows as text.
- Images (`.jpg`, `.png`): return empty string (classify from metadata only).
- Unknown/binary: return empty string.

### CLI usage
```bash
# Classify a single file
python classifier.py --file /path/to/invoice.pdf --taxonomy /path/to/taxonomy.yaml

# Classify with verbose output (shows prompt sent to API)
python classifier.py --file /path/to/invoice.pdf --taxonomy /path/to/taxonomy.yaml --verbose

# Dry run (no API call, just shows extracted metadata + snippet)
python classifier.py --file /path/to/invoice.pdf --taxonomy /path/to/taxonomy.yaml --dry-run
```

### Project structure
```
_System/AI-File-Organizer/
  classifier/
    classifier.py          # main script
    snippet_extractor.py   # extract_snippet helper
    requirements.txt       # dependencies
    test_files/            # sample files for manual testing
  taxonomy/
    taxonomy.yaml          # the live taxonomy (already exists)
  docs/
    taxonomy-schema-spec.yaml    # schema reference (already exists)
    classification-engine-spec.md  # this document
```

### Dependencies (requirements.txt)
```
anthropic
pyyaml
pdfplumber
python-docx
openpyxl
```

### Environment
- Anthropic API key must be set as env var: `ANTHROPIC_API_KEY`
- Python 3.10+

### What "done" looks like
1. Script runs from CLI against a real file and returns valid JSON output.
2. Snippet extraction works for pdf, docx, txt, csv, xlsx.
3. Haiku classification returns plausible results on 5+ test files.
4. Escalation to Sonnet triggers correctly when confidence < 0.70.
5. --dry-run and --verbose flags work.
