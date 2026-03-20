"""FastAPI dashboard — routes for pending files review and actions."""

import json
import sqlite3
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from mover import move_file

app = FastAPI(title="AI File Organizer Dashboard")
templates = Jinja2Templates(directory="templates")


class ApproveBody(BaseModel):
    rename_mode: str = "accept"
    edited_name: str | None = None
    edited_path: str | None = None


class TonightBody(BaseModel):
    rename_mode: str = "accept"
    edited_name: str | None = None
    edited_path: str | None = None


class SkipBody(BaseModel):
    reason: str = ""


def _get_db(request: Request) -> str:
    return request.app.state.db_path


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/pending")
async def get_pending(request: Request):
    db_path = _get_db(request)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM pending_files WHERE status = 'pending' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/stats")
async def get_stats(request: Request):
    db_path = _get_db(request)
    conn = sqlite3.connect(db_path)
    pending = conn.execute(
        "SELECT COUNT(*) FROM pending_files WHERE status = 'pending'"
    ).fetchone()[0]
    moved = conn.execute(
        "SELECT COUNT(*) FROM pending_files WHERE status = 'moved'"
    ).fetchone()[0]
    skipped = conn.execute(
        "SELECT COUNT(*) FROM pending_files WHERE status = 'skipped'"
    ).fetchone()[0]
    scheduled = conn.execute(
        "SELECT COUNT(*) FROM pending_files WHERE status = 'scheduled'"
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM pending_files").fetchone()[0]

    # Trust level: ratio of auto-accepted (moved without edits) to total processed
    auto_accepted = conn.execute(
        "SELECT COUNT(*) FROM pending_files WHERE status = 'moved' AND (rename_mode = 'accept' OR rename_mode IS NULL)"
    ).fetchone()[0]
    processed = moved + skipped
    trust_level = (auto_accepted / processed) if processed > 0 else 0.0
    conn.close()

    return {
        "pending": pending,
        "moved": moved,
        "skipped": skipped,
        "scheduled": scheduled,
        "total": total,
        "trust_level": round(trust_level, 2),
    }


@app.post("/api/approve/{pending_id}")
async def approve(pending_id: str, body: ApproveBody, request: Request):
    db_path = _get_db(request)
    root_dir = request.app.state.root_dir

    # Store rename preferences before moving
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE pending_files SET rename_mode = ?, edited_name = ?, edited_path = ? WHERE id = ?",
        (body.rename_mode, body.edited_name, body.edited_path, pending_id),
    )
    conn.commit()
    conn.close()

    try:
        dest = move_file(
            db_path=db_path,
            pending_id=pending_id,
            rename_mode=body.rename_mode,
            edited_name=body.edited_name,
            edited_path=body.edited_path,
            root_dir=root_dir,
        )
        return {"status": "moved", "destination": dest}
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/tonight/{pending_id}")
async def tonight(pending_id: str, body: TonightBody, request: Request):
    db_path = _get_db(request)
    conn = sqlite3.connect(db_path)

    row = conn.execute(
        "SELECT id FROM pending_files WHERE id = ?", (pending_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Pending file not found")

    # Schedule for today at 2 AM UTC
    now = datetime.now(timezone.utc)
    scheduled_time = now.replace(hour=2, minute=0, second=0, microsecond=0)
    if now.hour >= 2:
        # If already past 2 AM, schedule for tomorrow 2 AM
        from datetime import timedelta

        scheduled_time += timedelta(days=1)

    conn.execute(
        """UPDATE pending_files
        SET status = 'scheduled', scheduled_time = ?,
            rename_mode = ?, edited_name = ?, edited_path = ?
        WHERE id = ?""",
        (
            scheduled_time.isoformat(),
            body.rename_mode,
            body.edited_name,
            body.edited_path,
            pending_id,
        ),
    )
    conn.commit()
    conn.close()

    return {"status": "scheduled", "scheduled_time": scheduled_time.isoformat()}


@app.post("/api/skip/{pending_id}")
async def skip(pending_id: str, body: SkipBody, request: Request):
    db_path = _get_db(request)
    conn = sqlite3.connect(db_path)

    row = conn.execute(
        "SELECT id FROM pending_files WHERE id = ?", (pending_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Pending file not found")

    conn.execute(
        """UPDATE pending_files
        SET status = 'skipped', skip_reason = ?
        WHERE id = ?""",
        (body.reason, pending_id),
    )
    conn.commit()
    conn.close()

    return {"status": "skipped"}
