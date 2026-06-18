import re
import sqlite3
from datetime import datetime, timedelta, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS features (
  id          INTEGER PRIMARY KEY,
  project     TEXT NOT NULL,
  title       TEXT NOT NULL,
  norm_title  TEXT NOT NULL,
  summary     TEXT,
  status      TEXT NOT NULL DEFAULT 'in_progress',
  source      TEXT NOT NULL DEFAULT 'scanner',
  auto_closed INTEGER NOT NULL DEFAULT 0,
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

# De-dup tuning: a scanner/LLM title is considered the "same feature" as a marker
# title when they share >=2 meaningful tokens AND the overlap coefficient is high.
# Plain Jaccard>=0.5 was rejected: it misses "metrics board implementation plan"
# vs "metrics board spec" (0.4). Overlap-coefficient on the smaller set catches
# fragment-style re-phrasings without over-matching 2-word titles on one shared word.
_DEDUP_OVERLAP = 0.6
_STOPWORDS = {"the", "a", "an", "of", "to", "for", "and", "with"}

def _tokens(norm: str) -> set:
    return {w for w in norm.split() if len(w) >= 3 and w not in _STOPWORDS}

def _titles_match(a_norm: str, b_norm: str) -> bool:
    A, B = _tokens(a_norm), _tokens(b_norm)
    if len(A) < 2 or len(B) < 2:
        return a_norm == b_norm
    inter = A & B
    if len(inter) < 2:
        return False
    return len(inter) / min(len(A), len(B)) >= _DEDUP_OVERLAP

def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: str) -> sqlite3.Connection:
    conn = connect(db_path)
    conn.executescript(SCHEMA)
    # Idempotent migration for DBs created before auto_closed existed.
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(features)")}
    if "auto_closed" not in cols:
        conn.execute("ALTER TABLE features ADD COLUMN auto_closed INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    return conn

def upsert_feature(conn, project, title, summary, status, source="scanner", auto_closed=False, now=None) -> str:
    now = now or _now()
    norm = normalize_title(title)
    # LLM/auto-discovery items must not twin a marker-managed feature.
    if source == "scanner":
        for r in conn.execute(
            "SELECT norm_title FROM features WHERE project=? AND source='marker'", (project,)
        ).fetchall():
            if _titles_match(norm, r["norm_title"]):
                return "suppressed"
    exact = conn.execute(
        "SELECT id, status, summary, auto_closed FROM features WHERE project=? AND norm_title=?",
        (project, norm),
    ).fetchone()
    row, keep_title = exact, False
    if row is None and source == "marker":
        for r in conn.execute(
            "SELECT id, status, summary, norm_title, auto_closed FROM features WHERE project=?"
            " ORDER BY (status='in_progress') DESC, updated_at DESC",
            (project,),
        ).fetchall():
            if _titles_match(norm, r["norm_title"]):
                row, keep_title = r, True
                break
    if row is None:
        ac = 1 if (auto_closed and status == "done") else 0
        conn.execute(
            "INSERT INTO features(project,title,norm_title,summary,status,source,auto_closed,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (project, title, norm, summary, status, source, ac, now, now),
        )
        conn.commit()
        return "inserted"
    new_summary = summary if (summary and summary.strip()) else row["summary"]
    row_done = (row["status"] == "done")
    row_auto = bool(row["auto_closed"])
    if source == "manual":
        new_status, new_auto = status, 0          # manual is a declaration
    elif status == "done":
        new_status = "done"
        # A hard close (auto_closed False) is sticky and must never be downgraded to a
        # soft close. A soft close stays soft unless the row is already a hard close.
        new_auto = 0 if (not auto_closed or (row_done and not row_auto)) else 1
    else:  # incoming in_progress
        if row_done and not row_auto:
            new_status, new_auto = "done", 0       # declared done: never regress
        else:
            new_status, new_auto = "in_progress", 0  # open, or reopen an assumed-done row
    if keep_title:
        conn.execute(
            "UPDATE features SET summary=?, status=?, source=?, auto_closed=?, updated_at=? WHERE id=?",
            (new_summary, new_status, source, new_auto, now, row["id"]),
        )
    else:
        conn.execute(
            "UPDATE features SET title=?, summary=?, status=?, source=?, auto_closed=?, updated_at=? WHERE id=?",
            (title, new_summary, new_status, source, new_auto, now, row["id"]),
        )
    conn.commit()
    return "updated"

def reap_idle_features(conn, idle_hours=48, now=None) -> int:
    """Soft-close any in-progress feature with no activity for `idle_hours`.
    Reversible (auto_closed=1) and does NOT bump updated_at, so the board keeps
    showing the real last-activity time and the sweep stays idempotent."""
    now = now or _now()
    cutoff = (datetime.fromisoformat(now) - timedelta(hours=idle_hours)).isoformat()
    cur = conn.execute(
        "UPDATE features SET status='done', auto_closed=1"
        " WHERE status='in_progress' AND updated_at < ?",
        (cutoff,),
    )
    conn.commit()
    return cur.rowcount

def prune_features(conn, keep_days=14, now=None) -> int:
    """Delete features with no activity (updated_at) within keep_days, bounding board
    size. Features are cheap/regenerable from transcripts, so deletion is safe."""
    now = now or _now()
    cutoff = (datetime.fromisoformat(now) - timedelta(days=keep_days)).isoformat()
    cur = conn.execute("DELETE FROM features WHERE updated_at < ?", (cutoff,))
    conn.commit()
    return cur.rowcount

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
