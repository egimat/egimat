# AI File Organizer

## Project Overview
AI-powered personal file organizer that classifies and routes documents into a user-defined taxonomy. Uses Claude (Haiku for fast classification, Sonnet for ambiguous cases) to read file content and suggest the correct folder placement.

## Key Files
- `_System/AI-File-Organizer/taxonomy/taxonomy.yaml` — The live taxonomy config (folder tree, rules, AI context)
- `_System/AI-File-Organizer/docs/taxonomy-schema-spec.yaml` — Schema specification documenting all supported fields

## Architecture
- **Taxonomy**: YAML-based folder tree with classification hints (keyword_match, file_types)
- **Classification engine**: Reads taxonomy + file content → suggests path, confidence, rationale
- **Automation modes**: suggest_only, suggest_and_confirm, auto_pilot
- **Storage**: SQLite for file metadata, content hashes, classification history

## Conventions
- Folder IDs are 8-char hex, immutable after creation
- Rules are hints, not hard filters — AI weighs them alongside other signals
- Documents have exactly one canonical path and zero or more shortcut paths
- Mixed Italian/English content throughout — both languages appear in every folder
