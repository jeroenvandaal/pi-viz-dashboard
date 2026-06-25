import json
import os
from scanner import scan

def test_run_scan_isolates_read_errors_and_still_saves(tmp_path, monkeypatch):
    proj = tmp_path / "projects" / "-x-vector"; proj.mkdir(parents=True)
    (proj / "s.jsonl").write_text(
        '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"x"}]}}\n')
    state_path = tmp_path / "state.json"
    def boom(path, offset): raise FileNotFoundError("rotated away mid-run")
    monkeypatch.setattr(scan, "read_new_assistant_text", boom)
    monkeypatch.setattr(scan, "extract_features", lambda *a, **k: [])
    monkeypatch.setattr(scan, "post_features", lambda items: {"inserted": 0, "updated": 0})
    scan.run_scan(projects_dir=proj.parent, state_path=state_path)  # must not raise
    assert state_path.exists()  # save_state still ran despite the read error

def test_state_roundtrip(tmp_path):
    p = tmp_path / "state.json"
    scan.save_state(p, {"/a.jsonl": 10})
    assert scan.load_state(p) == {"/a.jsonl": 10}
    assert scan.load_state(tmp_path / "missing.json") == {}

def test_run_scan_advances_offsets_only_on_success(tmp_path, monkeypatch):
    # one session file
    proj = tmp_path / "projects" / "-x-vector"; proj.mkdir(parents=True)
    sess = proj / "s.jsonl"
    sess.write_text(json.dumps({"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Done — shipped X"}]}}) + "\n")
    state_path = tmp_path / "state.json"

    posted = []
    def fake_extract(text, project, client=None): return [{"project": project, "title": "X", "summary": "shipped X", "status": "done"}]
    def fake_post(items): posted.append(items); return {"inserted": len(items), "updated": 0}

    monkeypatch.setattr(scan, "extract_features", fake_extract)
    monkeypatch.setattr(scan, "post_features", fake_post)

    scan.run_scan(projects_dir=proj.parent, state_path=state_path)
    assert posted and posted[0][0]["title"] == "X"
    assert scan.load_state(state_path)[str(sess)] == sess.stat().st_size

    # second run: no new content -> no post, offset unchanged
    posted.clear()
    scan.run_scan(projects_dir=proj.parent, state_path=state_path)
    assert posted == []

def test_run_scan_keeps_offset_when_post_fails(tmp_path, monkeypatch):
    proj = tmp_path / "projects" / "-x-vector"; proj.mkdir(parents=True)
    sess = proj / "s.jsonl"
    sess.write_text(json.dumps({"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Done X"}]}}) + "\n")
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(scan, "extract_features", lambda *a, **k: [{"project":"vector","title":"X","summary":"","status":"done"}])
    def boom(items): raise RuntimeError("pi down")
    monkeypatch.setattr(scan, "post_features", boom)
    scan.run_scan(projects_dir=proj.parent, state_path=state_path)
    assert scan.load_state(state_path).get(str(sess), 0) == 0  # not advanced

def test_run_scan_posts_marker_items_before_llm(tmp_path, monkeypatch):
    proj = tmp_path / "projects" / "-x-pi-dashboard"; proj.mkdir(parents=True)
    sess = proj / "s.jsonl"
    sess.write_text(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "✅ feature done — pi-dashboard: Marker feature"}]}}) + "\n")
    state_path = tmp_path / "state.json"
    posted = []
    monkeypatch.setattr(scan, "extract_features", lambda *a, **k: [{"project": "pi-dashboard", "title": "LLM feature", "summary": "", "status": "in_progress"}])
    monkeypatch.setattr(scan, "post_features", lambda items: posted.append(items) or {"inserted": len(items), "updated": 0, "suppressed": 0})
    scan.run_scan(projects_dir=proj.parent, state_path=state_path)
    assert posted[0] == [{"project": "pi-dashboard", "title": "Marker feature", "status": "done", "source": "marker", "summary": ""}]
    assert posted[1][0]["title"] == "LLM feature"
    assert scan.load_state(state_path)[str(sess)] == sess.stat().st_size

def test_run_scan_soft_closes_unclosed_start_when_quiescent(tmp_path, monkeypatch):
    proj = tmp_path / "projects" / "-x-pi-dashboard"; proj.mkdir(parents=True)
    sess = proj / "s.jsonl"
    sess.write_text(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "▶ feature start — pi-dashboard: Solo feature"}]}}) + "\n")
    os.utime(sess, (1000, 1000))  # old mtime
    state_path = tmp_path / "state.json"
    posted = []
    monkeypatch.setattr(scan, "extract_features", lambda *a, **k: [])
    monkeypatch.setattr(scan, "post_features", lambda items: posted.append(items) or {})
    scan.run_scan(projects_dir=proj.parent, state_path=state_path, now=1000 + 4000)  # > QUIET past mtime
    assert posted[0] == [{"project": "pi-dashboard", "title": "Solo feature", "status": "done",
                          "source": "marker", "summary": "", "auto_closed": True}]
    # finalized: a later scan posts nothing new
    posted.clear()
    scan.run_scan(projects_dir=proj.parent, state_path=state_path, now=1000 + 8000)
    assert posted == []

def test_run_scan_active_session_keeps_start_in_progress(tmp_path, monkeypatch):
    proj = tmp_path / "projects" / "-x-pi-dashboard"; proj.mkdir(parents=True)
    sess = proj / "s.jsonl"
    sess.write_text(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "▶ feature start — pi-dashboard: Live feature"}]}}) + "\n")
    state_path = tmp_path / "state.json"
    posted = []
    monkeypatch.setattr(scan, "extract_features", lambda *a, **k: [])
    monkeypatch.setattr(scan, "post_features", lambda items: posted.append(items) or {})
    scan.run_scan(projects_dir=proj.parent, state_path=state_path, now=sess.stat().st_mtime)  # fresh → active
    assert posted[0][0]["status"] == "in_progress" and "auto_closed" not in posted[0][0]

def test_run_scan_resumed_session_unsets_finalization(tmp_path, monkeypatch):
    proj = tmp_path / "projects" / "-x-pi-dashboard"; proj.mkdir(parents=True)
    sess = proj / "s.jsonl"
    sess.write_text(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "▶ feature start — pi-dashboard: Resumed feature"}]}}) + "\n")
    os.utime(sess, (1000, 1000))  # old mtime → quiescent
    state_path = tmp_path / "state.json"
    posted = []
    monkeypatch.setattr(scan, "extract_features", lambda *a, **k: [])
    monkeypatch.setattr(scan, "post_features", lambda items: posted.append(items) or {})

    # First scan: quiescent → finalized
    scan.run_scan(projects_dir=proj.parent, state_path=state_path, now=1000 + 4000)
    assert posted  # soft-close posted
    state = scan.load_state(state_path)
    assert state["__final__"].get(str(sess)) is True

    # Resume: bump mtime so the session is active again
    os.utime(sess, (5200, 5200))
    posted.clear()
    scan.run_scan(projects_dir=proj.parent, state_path=state_path, now=5200)  # now == mtime → active
    state = scan.load_state(state_path)
    assert str(sess) not in state.get("__final__", {})  # un-finalized

def test_run_scan_skips_and_baselines_old_untracked_session(tmp_path, monkeypatch):
    # A lost/empty state must NOT trigger a full-history claude -p grind: an untracked
    # session older than max_age_days is baselined (marked seen), never mined.
    proj = tmp_path / "projects" / "-x-pi-dashboard"; proj.mkdir(parents=True)
    sess = proj / "old.jsonl"
    sess.write_text(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "old work that must not be mined"}]}}) + "\n")
    os.utime(sess, (1000, 1000))  # ancient mtime
    state_path = tmp_path / "state.json"
    extracted, posted = [], []
    monkeypatch.setattr(scan, "extract_features", lambda *a, **k: extracted.append(1) or [])
    monkeypatch.setattr(scan, "post_features", lambda items: posted.append(items) or {})
    scan.run_scan(projects_dir=proj.parent, state_path=state_path,
                  now=1000 + 30 * 86400, max_age_days=14)  # 30 days old > 14
    assert extracted == []   # never invoked claude -p extraction
    assert posted == []      # nothing posted
    st = scan.load_state(state_path)
    assert st[str(sess)] == sess.stat().st_size        # baselined to current size
    assert st["__final__"].get(str(sess)) is True      # marked finalized (history)
