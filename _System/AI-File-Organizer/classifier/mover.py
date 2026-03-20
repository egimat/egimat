"""File mover — renames and moves files from Inbox to their destination."""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def move_file(
    db_path: str,
    pending_id: str,
    rename_mode: str,
    edited_name: str | None = None,
    edited_path: str | None = None,
    root_dir: str = ".",
):
    """Move a file from Inbox to its classified destination.

    Args:
        db_path: Path to the SQLite database.
        pending_id: ID of the pending_files row.
        rename_mode: One of "accept", "edit", "keep_original".
        edited_name: User-edited filename (used when rename_mode is "edit").
        edited_path: User-edited destination path (overrides suggested_path).
        root_dir: Root directory for the file tree.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM pending_files WHERE id = ?", (pending_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Pending file not found: {pending_id}")

        original_path = row["original_path"]
        if not os.path.exists(original_path):
            raise FileNotFoundError(f"Source file missing: {original_path}")

        # Determine final name
        if rename_mode == "edit" and edited_name:
            final_name = edited_name
        elif rename_mode == "accept" and row["suggested_name"]:
            final_name = row["suggested_name"]
        else:
            final_name = row["original_name"]

        # Determine destination folder
        dest_folder_rel = edited_path if edited_path else row["suggested_path"]
        dest_folder = os.path.join(root_dir, dest_folder_rel.lstrip("/"))

        # Create destination folder recursively
        os.makedirs(dest_folder, exist_ok=True)

        # Handle name collisions
        dest_path = _resolve_collision(dest_folder, final_name)

        # Move the file
        os.rename(original_path, dest_path)

        # Update pending_files status
        conn.execute(
            """UPDATE pending_files
            SET status = 'moved', final_name = ?, final_path = ?, moved_at = ?
            WHERE id = ?""",
            (
                os.path.basename(dest_path),
                dest_path,
                datetime.now(timezone.utc).isoformat(),
                pending_id,
            ),
        )

        # Log the action
        conn.execute(
            """INSERT INTO action_log (pending_id, action, detail, timestamp)
            VALUES (?, ?, ?, ?)""",
            (
                pending_id,
                "moved",
                json.dumps(
                    {
                        "from": original_path,
                        "to": dest_path,
                        "rename_mode": rename_mode,
                    }
                ),
                datetime.now(timezone.utc).isoformat(),
            ),
        )

        # Log shortcut targets as deferred
        secondary_paths = json.loads(row["secondary_paths"] or "[]")
        for sp in secondary_paths:
            conn.execute(
                """INSERT INTO action_log (pending_id, action, detail, timestamp)
                VALUES (?, ?, ?, ?)""",
                (
                    pending_id,
                    "shortcut_deferred",
                    json.dumps({"shortcut_path": sp, "canonical": dest_path}),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

        conn.commit()
        return dest_path

    finally:
        conn.close()


def _resolve_collision(dest_folder: str, filename: str) -> str:
    """Resolve name collisions by appending _1, _2, etc."""
    dest = os.path.join(dest_folder, filename)
    if not os.path.exists(dest):
        return dest

    stem = Path(filename).stem
    ext = Path(filename).suffix
    counter = 1
    while True:
        new_name = f"{stem}_{counter}{ext}"
        dest = os.path.join(dest_folder, new_name)
        if not os.path.exists(dest):
            return dest
        counter += 1
