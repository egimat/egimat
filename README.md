# AI File Organizer

AI-powered local-first file organizer that classifies files into a user-defined taxonomy using the Claude API.

## Status

Design phase complete. Classification engine in progress.

## How It Works

1. Point the classifier at any file on your local machine
2. It extracts metadata (name, extension, size, dates, MIME type) and a text snippet (first 200 words)
3. Sends the file info + your full taxonomy to Claude API
4. Returns a structured classification with suggested folder path, confidence score, and rationale
5. Low-confidence results automatically escalate from Haiku to Sonnet for better accuracy

## Quick Start

```bash
cd _System/AI-File-Organizer/classifier
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your-key-here
python classifier.py --file /path/to/file.pdf --taxonomy ../taxonomy/taxonomy.yaml
```

## Project Structure

```
_System/AI-File-Organizer/
  taxonomy/        # Taxonomy YAML config
  docs/            # Specs and schema docs
  classifier/      # Classification engine
  action-log/      # Classification action logs
```

Private project by Matteo.
