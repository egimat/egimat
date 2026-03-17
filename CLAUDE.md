# AI File Organizer — Claude Code Instructions

## Project Structure
All project artifacts belong under `_System/AI-File-Organizer/` with explicit subfolder placement:
- `taxonomy/` — Taxonomy YAML config files
- `docs/` — Specs and schema documentation
- `classifier/` — Classification engine code
- `action-log/` — Logs of classification actions

## Development
- Python 3.10+
- Dependencies listed in `_System/AI-File-Organizer/classifier/requirements.txt`
- API key read from environment variable `ANTHROPIC_API_KEY`, never hardcoded
- Taxonomy YAML is the central config file — read on every classification call

## Classification Behavior
- Classification uses Claude Haiku by default (`claude-haiku-4-5-20251001`)
- Escalates to Sonnet (`claude-sonnet-4-5-20241022`) when confidence < 0.70
- Output is structured JSON with suggested_path, confidence, rationale, etc.

## Running
```bash
cd _System/AI-File-Organizer/classifier
pip install -r requirements.txt
python classifier.py --file <path> --taxonomy ../taxonomy/taxonomy.yaml
python classifier.py --file <path> --taxonomy ../taxonomy/taxonomy.yaml --dry-run
python classifier.py --file <path> --taxonomy ../taxonomy/taxonomy.yaml --verbose
```
