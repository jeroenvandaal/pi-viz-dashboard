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

def test_titles_match_catches_real_near_dups():
    from server.db import normalize_title as n, _titles_match
    assert _titles_match(n("metrics board implementation plan"), n("metrics board spec"))
    assert _titles_match(n("metrics board implementation plan"), n("metrics board ui"))
    assert _titles_match(n("Metrics Core Web Vitals parser"), n("Metrics traffic parser"))

def test_titles_match_rejects_unrelated():
    from server.db import normalize_title as n, _titles_match
    assert not _titles_match(n("Login page"), n("Login rate limiting"))   # only 1 shared token
    assert not _titles_match(n("Dashboard wall-strip mockups"), n("metrics board ui"))
    assert not _titles_match(n("Email integration"), n("metrics board"))

def test_titles_match_short_titles_need_exact():
    from server.db import normalize_title as n, _titles_match
    assert _titles_match(n("Auth"), n("auth"))          # <2 tokens → exact norm
    assert not _titles_match(n("Auth"), n("Authz"))

def test_marker_is_authoritative_and_sets_source(tmp_path):
    from server import db
    p = str(tmp_path / "t.db"); db.init_db(p); conn = db.connect(p)
    db.upsert_feature(conn, "pi-dashboard", "Website board", "", "in_progress", source="scanner")
    assert db.upsert_feature(conn, "pi-dashboard", "Website board", "", "done", source="marker") == "updated"
    row = conn.execute("SELECT status, source FROM features").fetchone()
    assert row["status"] == "done" and row["source"] == "marker"

def test_scanner_item_matching_marker_is_suppressed(tmp_path):
    from server import db
    p = str(tmp_path / "t.db"); db.init_db(p); conn = db.connect(p)
    db.upsert_feature(conn, "pi-dashboard", "Metrics board spec", "", "done", source="marker")
    res = db.upsert_feature(conn, "pi-dashboard", "metrics board implementation plan", "", "in_progress", source="scanner")
    assert res == "suppressed"
    rows = conn.execute("SELECT status, source FROM features").fetchall()
    assert len(rows) == 1 and rows[0]["status"] == "done" and rows[0]["source"] == "marker"

def test_scanner_item_not_matching_marker_inserts(tmp_path):
    from server import db
    p = str(tmp_path / "t.db"); db.init_db(p); conn = db.connect(p)
    db.upsert_feature(conn, "pi-dashboard", "Metrics board spec", "", "done", source="marker")
    res = db.upsert_feature(conn, "pi-dashboard", "Email integration", "", "in_progress", source="scanner")
    assert res == "inserted"
    assert conn.execute("SELECT COUNT(*) c FROM features").fetchone()["c"] == 2

def test_suppression_is_per_project(tmp_path):
    from server import db
    p = str(tmp_path / "t.db"); db.init_db(p); conn = db.connect(p)
    db.upsert_feature(conn, "proj-a", "Metrics board spec", "", "done", source="marker")
    assert db.upsert_feature(conn, "proj-b", "metrics board implementation plan", "", "in_progress", source="scanner") == "inserted"

def test_marker_update_preserves_existing_summary(tmp_path):
    from server import db
    p = str(tmp_path / "t.db"); db.init_db(p); conn = db.connect(p)
    db.upsert_feature(conn, "pi-dashboard", "Cool thing", "Implemented the cool thing", "in_progress", source="scanner")
    db.upsert_feature(conn, "pi-dashboard", "Cool thing", "", "done", source="marker")
    row = conn.execute("SELECT status, summary FROM features").fetchone()
    assert row["status"] == "done"
    assert row["summary"] == "Implemented the cool thing"   # not blanked by the empty marker summary

def test_marker_done_fuzzy_closes_open_marker_with_drifted_title(tmp_path):
    from server import db
    p = str(tmp_path / "t.db"); db.init_db(p); conn = db.connect(p)
    db.upsert_feature(conn, "pi-dashboard", "Feature markers", "", "in_progress", source="marker")
    res = db.upsert_feature(conn, "pi-dashboard", "Feature lifecycle markers", "", "done", source="marker")
    assert res == "updated"
    rows = conn.execute("SELECT title, status, source FROM features").fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "done" and rows[0]["source"] == "marker"
    assert rows[0]["title"] == "Feature markers"   # kept the start's title, no twin

def test_marker_done_fuzzy_retires_stale_llm_row(tmp_path):
    from server import db
    p = str(tmp_path / "t.db"); db.init_db(p); conn = db.connect(p)
    db.upsert_feature(conn, "pi-dashboard", "Metrics traffic parser", "did parser", "in_progress", source="scanner")
    res = db.upsert_feature(conn, "pi-dashboard", "Metrics Core Web Vitals parser", "", "done", source="marker")
    assert res == "updated"
    rows = conn.execute("SELECT status, source, summary FROM features").fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "done" and rows[0]["source"] == "marker"
    assert rows[0]["summary"] == "did parser"   # preserved (marker carried none)

def test_marker_no_fuzzy_match_inserts(tmp_path):
    from server import db
    p = str(tmp_path / "t.db"); db.init_db(p); conn = db.connect(p)
    db.upsert_feature(conn, "pi-dashboard", "Email integration", "", "in_progress", source="marker")
    res = db.upsert_feature(conn, "pi-dashboard", "Metrics world map", "", "done", source="marker")
    assert res == "inserted"
    assert conn.execute("SELECT COUNT(*) c FROM features").fetchone()["c"] == 2

def test_marker_fuzzy_prefers_open_row(tmp_path):
    from server import db
    p = str(tmp_path / "t.db"); db.init_db(p); conn = db.connect(p)
    db.upsert_feature(conn, "pi-dashboard", "Metrics parser shipped", "", "done", source="marker")     # already done
    db.upsert_feature(conn, "pi-dashboard", "Metrics parser", "", "in_progress", source="marker")       # open
    db.upsert_feature(conn, "pi-dashboard", "Metrics parser module", "", "done", source="marker")        # done marker, drifted name
    open_rows = conn.execute("SELECT COUNT(*) c FROM features WHERE status='in_progress'").fetchone()["c"]
    assert open_rows == 0   # the open 'Metrics parser' got closed, not a finished row or a twin

def test_init_db_adds_auto_closed_to_legacy_table(tmp_path):
    import sqlite3
    p = str(tmp_path / "legacy.db")
    c = sqlite3.connect(p)
    c.execute(
        "CREATE TABLE features (id INTEGER PRIMARY KEY, project TEXT NOT NULL,"
        " title TEXT NOT NULL, norm_title TEXT NOT NULL, summary TEXT,"
        " status TEXT NOT NULL DEFAULT 'in_progress', source TEXT NOT NULL DEFAULT 'scanner',"
        " created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(project, norm_title))"
    )
    c.execute(
        "INSERT INTO features(project,title,norm_title,summary,status,source,created_at,updated_at)"
        " VALUES('p','T','t','','in_progress','scanner','2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00')"
    )
    c.commit(); c.close()
    conn = db.init_db(p)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(features)")}
    assert "auto_closed" in cols
    assert conn.execute("SELECT auto_closed FROM features").fetchone()["auto_closed"] == 0

def test_soft_close_sets_auto_closed_and_is_reversible():
    conn = make_conn()
    db.upsert_feature(conn, "p", "Feature A", "s", "in_progress", source="marker")
    # session-end / reaper style soft close
    db.upsert_feature(conn, "p", "Feature A", "", "done", source="marker", auto_closed=True)
    row = conn.execute("SELECT status, auto_closed FROM features").fetchone()
    assert row["status"] == "done" and row["auto_closed"] == 1
    # resumed work reopens it
    db.upsert_feature(conn, "p", "Feature A", "", "in_progress", source="marker")
    row = conn.execute("SELECT status, auto_closed FROM features").fetchone()
    assert row["status"] == "in_progress" and row["auto_closed"] == 0

def test_declared_done_is_sticky():
    conn = make_conn()
    db.upsert_feature(conn, "p", "Feature A", "s", "done", source="marker")  # explicit done, auto_closed False
    assert conn.execute("SELECT auto_closed FROM features").fetchone()["auto_closed"] == 0
    db.upsert_feature(conn, "p", "Feature A", "", "in_progress", source="marker")
    assert conn.execute("SELECT status FROM features").fetchone()["status"] == "done"  # never regresses

def test_hard_close_not_downgraded_by_later_soft_close():
    conn = make_conn()
    db.upsert_feature(conn, "p", "Feature A", "s", "done", source="marker")              # hard
    db.upsert_feature(conn, "p", "Feature A", "", "done", source="marker", auto_closed=True)  # soft attempt
    assert conn.execute("SELECT auto_closed FROM features").fetchone()["auto_closed"] == 0

def test_soft_close_upgraded_to_hard_by_explicit_done():
    conn = make_conn()
    db.upsert_feature(conn, "p", "Feature A", "s", "in_progress", source="marker")
    db.upsert_feature(conn, "p", "Feature A", "", "done", source="marker", auto_closed=True)
    assert conn.execute("SELECT auto_closed FROM features").fetchone()["auto_closed"] == 1
    # explicit done arrives — must upgrade to hard/sticky
    db.upsert_feature(conn, "p", "Feature A", "", "done", source="marker", auto_closed=False)
    row = conn.execute("SELECT status, auto_closed FROM features").fetchone()
    assert row["status"] == "done" and row["auto_closed"] == 0
    # and it must now be sticky (won't reopen)
    db.upsert_feature(conn, "p", "Feature A", "", "in_progress", source="marker")
    assert conn.execute("SELECT status FROM features").fetchone()["status"] == "done"

def test_reaper_closes_only_stale_in_progress():
    conn = make_conn()
    db.upsert_feature(conn, "p", "Old", "s", "in_progress", now="2026-01-01T00:00:00+00:00")
    db.upsert_feature(conn, "p", "Fresh", "s", "in_progress", now="2026-01-10T00:00:00+00:00")
    db.upsert_feature(conn, "p", "DoneAlready", "s", "done", now="2026-01-01T00:00:00+00:00")
    n = db.reap_idle_features(conn, idle_hours=48, now="2026-01-10T01:00:00+00:00")
    assert n == 1
    rows = {r["title"]: r for r in db.list_features(conn)}
    assert rows["Old"]["status"] == "done" and rows["Old"]["auto_closed"] == 1
    assert rows["Old"]["updated_at"] == "2026-01-01T00:00:00+00:00"   # not bumped
    assert rows["Fresh"]["status"] == "in_progress"
    # idempotent
    assert db.reap_idle_features(conn, idle_hours=48, now="2026-01-10T01:00:00+00:00") == 0

def test_prune_features_deletes_only_old():
    conn = make_conn()
    db.upsert_feature(conn, "p", "Old", "s", "done", now="2026-01-01T00:00:00+00:00")
    db.upsert_feature(conn, "p", "Recent", "s", "done", now="2026-01-20T00:00:00+00:00")
    n = db.prune_features(conn, keep_days=14, now="2026-01-25T00:00:00+00:00")
    assert n == 1
    assert [r["title"] for r in db.list_features(conn)] == ["Recent"]
    # idempotent
    assert db.prune_features(conn, keep_days=14, now="2026-01-25T00:00:00+00:00") == 0
