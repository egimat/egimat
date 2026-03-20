"""Inbox watcher — polls for new files and queues them for classification."""

import hashlib
import json
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from classifier import classify_file, load_taxonomy


def sha256_hash(file_path: str) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def poll_inbox(
    inbox_path: str,
    taxonomy_path: str,
    db_path: str,
    poll_interval: int = 10,
    stop_event: threading.Event | None = None,
):
    """Poll the inbox folder for new files and classify them.

    Files must be stable (size unchanged over 2 consecutive polls) before
    processing. Already-processed files (by content hash) are skipped.
    """
    taxonomy = load_taxonomy(taxonomy_path)
    file_sizes: dict[str, int] = {}  # path -> size from previous poll

    while True:
        if stop_event and stop_event.is_set():
            break

        try:
            _poll_once(inbox_path, taxonomy, taxonomy_path, db_path, file_sizes)
        except Exception as e:
            print(f"[watcher] Error during poll: {e}")

        time.sleep(poll_interval)


def _poll_once(
    inbox_path: str,
    taxonomy: dict,
    taxonomy_path: str,
    db_path: str,
    file_sizes: dict[str, int],
):
    """Single poll iteration."""
    inbox = Path(inbox_path)
    if not inbox.exists():
        return

    current_files: set[str] = set()

    for entry in inbox.iterdir():
        if not entry.is_file():
            continue
        fp = str(entry)
        current_files.add(fp)

        try:
            size = entry.stat().st_size
        except OSError:
            continue

        prev_size = file_sizes.get(fp)
        file_sizes[fp] = size

        # Require stability: size must be unchanged from previous poll
        if prev_size is None or prev_size != size:
            continue

        # Check if already processed
        content_hash = sha256_hash(fp)
        if _is_processed(db_path, content_hash):
            continue

        # Classify the file
        try:
            result = classify_file(fp, taxonomy)
        except Exception as e:
            print(f"[watcher] Classification error for {fp}: {e}")
            continue

        # Insert into pending_files
        _insert_pending(db_path, fp, content_hash, result, taxonomy)

        # Mark as processed
        _mark_processed(db_path, content_hash, fp)

    # Clean up sizes for files that no longer exist
    gone = set(file_sizes.keys()) - current_files
    for g in gone:
        del file_sizes[g]


def _is_processed(db_path: str, content_hash: str) -> bool:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM processed_files WHERE content_hash = ?", (content_hash,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _mark_processed(db_path: str, content_hash: str, file_path: str):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO processed_files (content_hash, original_path, processed_at) VALUES (?, ?, ?)",
            (content_hash, file_path, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_pending(
    db_path: str,
    file_path: str,
    content_hash: str,
    result: dict,
    taxonomy: dict,
):
    file_id = uuid.uuid4().hex[:16]
    original_name = os.path.basename(file_path)
    now = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO pending_files
            (id, file_id, original_name, original_path, content_hash,
             suggested_path, suggested_name, secondary_paths, confidence,
             rationale, alternatives, model_used, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                uuid.uuid4().hex,
                file_id,
                original_name,
                file_path,
                content_hash,
                result.get("suggested_path", "/Inbox"),
                result.get("suggested_name", ""),
                json.dumps(result.get("secondary_paths", [])),
                result.get("confidence", 0.0),
                result.get("rationale", ""),
                json.dumps(result.get("alternatives", [])),
                result.get("model_used", "haiku"),
                "pending",
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
