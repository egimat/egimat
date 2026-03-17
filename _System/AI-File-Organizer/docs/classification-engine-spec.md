# Classification Engine Specification

## Overview

The classification engine is the core component of the AI File Organizer. It takes a file path as input, extracts metadata and a text snippet, sends them along with the full taxonomy to the Claude API, and returns a structured classification result.

## Components

### classifier.py

The main classification module and CLI entry point.

#### Responsibilities

1. **Metadata extraction**: Read file metadata including name, extension, size (bytes), created date, modified date, and MIME type
2. **Taxonomy loading**: Read and parse `taxonomy.yaml` from disk on every classification call
3. **Snippet integration**: Call `snippet_extractor.py` to get up to 200 words of text content
4. **API interaction**: Send metadata + snippet + full taxonomy to Claude API
5. **Response parsing**: Parse the API response as structured JSON
6. **Escalation logic**: If confidence < 0.70, automatically re-classify with a more capable model

#### Models

- **Default**: Claude Haiku (`claude-haiku-4-5-20251001`) — fast, cost-effective
- **Escalation**: Claude Sonnet (`claude-sonnet-4-5-20241022`) — higher accuracy for ambiguous files

#### Output Schema

```json
{
  "suggested_path": "/Work/Clients/Acme",
  "secondary_paths": ["/Personal/Tax/2025"],
  "confidence": 0.85,
  "rationale": "File contains an invoice from Acme Corp dated 2025-03-15",
  "alternatives": ["/Work/Invoices"],
  "escalate": false
}
```

#### CLI Interface

```bash
# Classify a file
python classifier.py --file <path> --taxonomy <taxonomy_yaml_path>

# Verbose mode: prints the prompt sent to the API
python classifier.py --file <path> --taxonomy <taxonomy_yaml_path> --verbose

# Dry run: extracts metadata + snippet, no API call
python classifier.py --file <path> --taxonomy <taxonomy_yaml_path> --dry-run
```

### snippet_extractor.py

Extracts a text snippet from a file for classification context.

#### Function Signature

```python
def extract_snippet(filepath: str) -> str
```

#### Supported Formats

| Format | Strategy |
|--------|----------|
| `.txt`, `.md` | First 200 words of raw text |
| `.pdf` | First 200 words via `pdfplumber` |
| `.docx` | First 200 words via `python-docx` |
| `.csv` | Column headers + first 5 rows as text |
| `.xlsx` | Column headers + first 5 rows via `openpyxl` |
| Images, binary, unknown | Return empty string `""` |

#### Error Handling

- Must **never crash** on any file type
- Always return a string (empty string for unsupported/binary formats)
- Log warnings for extraction failures but do not raise exceptions

## Prompt Design

### System Prompt

The system prompt must include:

1. The **full taxonomy.yaml content** (verbatim)
2. Instruction to return **ONLY valid JSON** matching the output schema — no markdown fences, no preamble, no explanation outside the JSON
3. Instruction that **`shortcut_target: true`** folders are candidates for `secondary_paths`
4. Instruction that **rules are weighted hints**, not hard filters — the AI should use them as signals alongside `ai_context` and file content
5. Emphasis that **`ai_context` is the highest-signal section** of the taxonomy for determining classification

### User Message

The user message must include:

1. All **file metadata** fields (name, extension, size, created date, modified date, MIME type)
2. **Text snippet** (or `"No text content available"` for binary/unsupported files)

## Escalation Logic

1. Send classification request to Haiku
2. Parse JSON response
3. If `confidence < 0.70` OR `escalate == true`:
   - Re-send the same prompt to Sonnet
   - Return the Sonnet result (regardless of its confidence)
4. If Haiku confidence >= 0.70 and escalate is false:
   - Return the Haiku result

## Configuration

- API key: Read from `ANTHROPIC_API_KEY` environment variable
- Taxonomy path: Passed via CLI `--taxonomy` argument
- No hardcoded paths or API keys

## Dependencies

```
anthropic
pyyaml
pdfplumber
python-docx
openpyxl
```
