import re
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS features (
  id          INTEGER PRIMARY KEY,
  project     TEXT NOT NULL,
  title       TEXT NOT NULL,
  norm_title  TEXT NOT NULL,
  summary     TEXT,
  status      TEXT NOT NULL DEFAULT 'in_progress',
  source      TEXT NOT NULL DEFAULT 'scanner',
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL,
  UNIQUE(project, norm_title)
);
CREATE TABLE IF NOT EXISTS display (
  id            INTEGER PRIMARY KEY CHECK (id = 1),
  active_board  TEXT NOT NULL DEFAULT 'claude',
  cycle         INTEGER NOT NULL DEFAULT 0,
  interval_sec  INTEGER NOT NULL DEFAULT 10,
  updated_at    TEXT
);
"""

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def normalize_title(title: str) -> str:
    t = title.lower().strip()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t

def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: str) -> sqlite3.Connection:
    conn = connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn

def upsert_feature(conn, project, title, summary, status, source="scanner", now=None) -> str:
    now = now or _now()
    norm = normalize_title(title)
    row = conn.execute(
        "SELECT id, status FROM features WHERE project=? AND norm_title=?",
        (project, norm),
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO features(project,title,norm_title,summary,status,source,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (project, title, norm, summary, status, source, now, now),
        )
        conn.commit()
        return "inserted"
    if source == "manual":
        new_status = status
    elif row["status"] == "done":
        new_status = "done"  # never auto-regress
    else:
        new_status = status
    conn.execute(
        "UPDATE features SET title=?, summary=?, status=?, source=?, updated_at=? WHERE id=?",
        (title, summary, new_status, source, now, row["id"]),
    )
    conn.commit()
    return "updated"

def list_features(conn) -> list[dict]:
    cur = conn.execute(
        "SELECT * FROM features ORDER BY (status='in_progress') DESC, updated_at DESC"
    )
    return [dict(r) for r in cur.fetchall()]

DISPLAY_DEFAULTS = {"active_board": "claude", "cycle": False, "interval_sec": 10}
INTERVAL_FLOOR = 5

def get_display(conn) -> dict:
    row = conn.execute(
        "SELECT active_board, cycle, interval_sec FROM display WHERE id=1"
    ).fetchone()
    if row is None:
        return dict(DISPLAY_DEFAULTS)
    return {
        "active_board": row["active_board"],
        "cycle": bool(row["cycle"]),
        "interval_sec": int(row["interval_sec"]),
    }

def set_display(conn, **fields) -> dict:
    allowed = {"active_board", "cycle", "interval_sec"}
    updates = {k: fields[k] for k in allowed if k in fields}
    if "interval_sec" in updates:
        updates["interval_sec"] = max(INTERVAL_FLOOR, int(updates["interval_sec"]))
    if "cycle" in updates:
        updates["cycle"] = 1 if updates["cycle"] else 0
    # Ensure the single row exists (defaults from the schema), then UPDATE ONLY the
    # provided columns. No Python read-modify-write of untouched columns, so two
    # concurrent partial updates (e.g. rapid menu taps) can't clobber each other.
    conn.execute("INSERT OR IGNORE INTO display(id) VALUES(1)")
    if updates:
        set_clause = ", ".join(f"{k}=:{k}" for k in updates)
        conn.execute(
            f"UPDATE display SET {set_clause}, updated_at=:now WHERE id=1",
            {**updates, "now": _now()},
        )
    conn.commit()
    return get_display(conn)
