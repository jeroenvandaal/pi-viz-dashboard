import json
from scanner import scan

def test_run_scan_isolates_read_errors_and_still_saves(tmp_path, monkeypatch):
    proj = tmp_path / "projects" / "-x-webapp"; proj.mkdir(parents=True)
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
    proj = tmp_path / "projects" / "-x-webapp"; proj.mkdir(parents=True)
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
    proj = tmp_path / "projects" / "-x-webapp"; proj.mkdir(parents=True)
    sess = proj / "s.jsonl"
    sess.write_text(json.dumps({"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Done X"}]}}) + "\n")
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(scan, "extract_features", lambda *a, **k: [{"project":"webapp","title":"X","summary":"","status":"done"}])
    def boom(items): raise RuntimeError("pi down")
    monkeypatch.setattr(scan, "post_features", boom)
    scan.run_scan(projects_dir=proj.parent, state_path=state_path)
    assert scan.load_state(state_path).get(str(sess), 0) == 0  # not advanced
