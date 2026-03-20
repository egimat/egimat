"""Entry point — starts watcher, tonight scheduler, and FastAPI dashboard."""

import argparse
import sqlite3
import threading
import time
from datetime import datetime, timezone

import uvicorn

from dashboard import app
from mover import move_file
from watcher import poll_inbox


def init_db(db_path: str):
    """Initialize SQLite database with all required tables."""
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS processed_files (
            content_hash TEXT PRIMARY KEY,
            original_path TEXT NOT NULL,
            processed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pending_files (
            id TEXT PRIMARY KEY,
            file_id TEXT NOT NULL,
            original_name TEXT NOT NULL,
            original_path TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            suggested_path TEXT NOT NULL,
            suggested_name TEXT DEFAULT '',
            secondary_paths TEXT DEFAULT '[]',
            confidence REAL DEFAULT 0.0,
            rationale TEXT DEFAULT '',
            alternatives TEXT DEFAULT '[]',
            model_used TEXT DEFAULT 'haiku',
            status TEXT DEFAULT 'pending',
            final_name TEXT,
            final_path TEXT,
            moved_at TEXT,
            scheduled_time TEXT,
            skip_reason TEXT,
            rename_mode TEXT,
            edited_name TEXT,
            edited_path TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS action_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pending_id TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT DEFAULT '',
            timestamp TEXT NOT NULL
        );
    """
    )
    conn.close()


def tonight_scheduler(db_path: str, root_dir: str, stop_event: threading.Event):
    """Check every 60s for files scheduled for tonight (2 AM). Execute when due."""
    while not stop_event.is_set():
        try:
            now = datetime.now(timezone.utc)
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM pending_files WHERE status = 'scheduled' AND scheduled_time IS NOT NULL"
            ).fetchall()
            conn.close()

            for row in rows:
                scheduled = datetime.fromisoformat(row["scheduled_time"])
                if now >= scheduled:
                    try:
                        move_file(
                            db_path=db_path,
                            pending_id=row["id"],
                            rename_mode=row["rename_mode"] or "accept",
                            edited_name=row["edited_name"],
                            edited_path=row["edited_path"],
                            root_dir=root_dir,
                        )
                    except Exception as e:
                        print(f"[tonight] Error moving {row['id']}: {e}")
        except Exception as e:
            print(f"[tonight] Scheduler error: {e}")

        time.sleep(60)


def main():
    parser = argparse.ArgumentParser(description="AI File Organizer Server")
    parser.add_argument("--inbox", required=True, help="Path to the Inbox folder")
    parser.add_argument(
        "--taxonomy", required=True, help="Path to taxonomy.yaml"
    )
    parser.add_argument("--port", type=int, default=8080, help="Dashboard port")
    args = parser.parse_args()

    db_path = "queue.db"
    init_db(db_path)

    # Share config with dashboard via app state
    app.state.db_path = db_path
    app.state.inbox_path = args.inbox
    app.state.taxonomy_path = args.taxonomy
    app.state.root_dir = "."

    stop_event = threading.Event()

    # Start watcher in background thread
    watcher_thread = threading.Thread(
        target=poll_inbox,
        args=(args.inbox, args.taxonomy, db_path),
        kwargs={"stop_event": stop_event},
        daemon=True,
    )
    watcher_thread.start()

    # Start tonight scheduler in background thread
    scheduler_thread = threading.Thread(
        target=tonight_scheduler,
        args=(db_path, ".", stop_event),
        daemon=True,
    )
    scheduler_thread.start()

    # Start FastAPI
    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
