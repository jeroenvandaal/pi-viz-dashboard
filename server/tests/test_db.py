import sqlite3
from server import db

def make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    return conn

def test_normalize_title():
    assert db.normalize_title("  Email Integration!! ") == "email integration"
    assert db.normalize_title("Billing  bill-sync   UX") == "billing billsync ux"

def test_insert_then_dedup_updates_not_duplicates():
    conn = make_conn()
    assert db.upsert_feature(conn, "webapp", "Email integration", "v1", "in_progress", now="2026-01-01T00:00:00+00:00") == "inserted"
    assert db.upsert_feature(conn, "webapp", "email  integration", "v2", "in_progress", now="2026-01-02T00:00:00+00:00") == "updated"
    rows = db.list_features(conn)
    assert len(rows) == 1
    assert rows[0]["summary"] == "v2"
    assert rows[0]["updated_at"] == "2026-01-02T00:00:00+00:00"

def test_status_promotes_in_progress_to_done():
    conn = make_conn()
    db.upsert_feature(conn, "p", "Feature A", "s", "in_progress")
    db.upsert_feature(conn, "p", "Feature A", "s", "done")
    assert db.list_features(conn)[0]["status"] == "done"

def test_status_does_not_regress_done_to_in_progress():
    conn = make_conn()
    db.upsert_feature(conn, "p", "Feature A", "s", "done")
    db.upsert_feature(conn, "p", "Feature A", "s", "in_progress")  # scanner re-mention
    assert db.list_features(conn)[0]["status"] == "done"

def test_manual_override_can_set_any_status():
    conn = make_conn()
    db.upsert_feature(conn, "p", "Feature A", "s", "done")
    db.upsert_feature(conn, "p", "Feature A", "s", "in_progress", source="manual")
    assert db.list_features(conn)[0]["status"] == "in_progress"

def test_list_orders_in_progress_first_then_recency():
    conn = make_conn()
    db.upsert_feature(conn, "p", "Old done", "s", "done", now="2026-01-05T00:00:00+00:00")
    db.upsert_feature(conn, "p", "Active", "s", "in_progress", now="2026-01-01T00:00:00+00:00")
    titles = [r["title"] for r in db.list_features(conn)]
    assert titles == ["Active", "Old done"]
