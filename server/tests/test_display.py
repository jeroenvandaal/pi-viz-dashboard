import sqlite3
from server import db

def make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    return conn

def test_get_display_returns_defaults_on_fresh_db():
    conn = make_conn()
    d = db.get_display(conn)
    assert d == {"active_board": "claude", "cycle": False, "interval_sec": 10}

def test_set_display_partial_update_persists():
    conn = make_conn()
    db.set_display(conn, cycle=True, interval_sec=30)
    d = db.get_display(conn)
    assert d["cycle"] is True
    assert d["interval_sec"] == 30
    assert d["active_board"] == "claude"  # untouched field keeps default

def test_set_display_active_board_roundtrip():
    conn = make_conn()
    db.set_display(conn, active_board="infra")
    assert db.get_display(conn)["active_board"] == "infra"

def test_set_display_only_touches_provided_columns():
    # A partial update must not rewrite untouched columns (no read-modify-write
    # clobber): set cycle, then set interval — cycle must survive.
    conn = make_conn()
    db.set_display(conn, cycle=True)
    db.set_display(conn, interval_sec=45)
    d = db.get_display(conn)
    assert d["cycle"] is True          # not clobbered by the interval-only update
    assert d["interval_sec"] == 45

def test_set_display_clamps_interval_floor():
    conn = make_conn()
    db.set_display(conn, interval_sec=1)
    assert db.get_display(conn)["interval_sec"] == 5  # floor is 5s

def test_set_display_ignores_unknown_fields():
    conn = make_conn()
    db.set_display(conn, bogus="x", cycle=True)  # must not raise
    assert db.get_display(conn)["cycle"] is True
