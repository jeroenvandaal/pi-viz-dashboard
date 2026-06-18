import io
import json
from hooks import feature_hook


def _write(path, *texts):
    lines = [json.dumps({"type": "assistant", "message": {"role": "assistant",
             "content": [{"type": "text", "text": t}]}}) for t in texts]
    path.write_text("\n".join(lines) + "\n")


def test_last_assistant_text_returns_final_message(tmp_path):
    p = tmp_path / "s.jsonl"; _write(p, "first", "second", "third")
    assert feature_hook.last_assistant_text(p) == "third"


def test_stop_items_reads_only_last_message(tmp_path):
    p = tmp_path / "s.jsonl"
    _write(p, "▶ feature start — proj: Early one", "✅ feature done — proj: Late one")
    items = feature_hook.stop_items(p)
    assert items == [{"project": "proj", "title": "Late one", "status": "done",
                      "source": "marker", "summary": ""}]


def test_session_end_items_soft_closes_unclosed(tmp_path):
    p = tmp_path / "s.jsonl"
    _write(p, "▶ feature start — proj: Unfinished", "✅ feature done — proj: Finished")
    by = {i["title"]: i for i in feature_hook.session_end_items(p)}
    assert by["Unfinished"]["status"] == "done" and by["Unfinished"]["auto_closed"] is True
    assert "auto_closed" not in by["Finished"]


def test_session_end_items_missing_file_returns_empty(tmp_path):
    assert feature_hook.session_end_items(tmp_path / "nope.jsonl") == []


def test_last_assistant_text_missing_file_returns_empty(tmp_path):
    assert feature_hook.last_assistant_text(tmp_path / "nope.jsonl") == ""


def test_push_sends_payload_over_ssh(monkeypatch):
    monkeypatch.setenv("VIZ_HOOK_SSH", "testhost")
    calls = {}
    def fake_run(cmd, input=None, **kw):
        calls["cmd"], calls["input"], calls["timeout"] = cmd, input, kw.get("timeout")
        class R: returncode = 0
        return R()
    monkeypatch.setattr(feature_hook.subprocess, "run", fake_run)
    feature_hook.push([{"project": "p", "title": "X", "status": "done", "auto_closed": True}])
    assert calls["cmd"][0] == "ssh"
    assert json.loads(calls["input"].decode())["items"][0]["title"] == "X"
    assert calls.get("timeout") == 20


def test_push_noop_on_empty(monkeypatch):
    called = []
    monkeypatch.setattr(feature_hook.subprocess, "run", lambda *a, **k: called.append(1))
    feature_hook.push([])
    assert called == []


def test_push_never_raises(monkeypatch):
    monkeypatch.setenv("VIZ_HOOK_SSH", "testhost")
    def boom(*a, **k): raise OSError("ssh missing")
    monkeypatch.setattr(feature_hook.subprocess, "run", boom)
    feature_hook.push([{"project": "p", "title": "X", "status": "done"}])  # must not raise


def test_push_noop_without_host(monkeypatch):
    monkeypatch.delenv("VIZ_HOOK_SSH", raising=False)
    called = []
    monkeypatch.setattr(feature_hook.subprocess, "run", lambda *a, **k: called.append(1))
    feature_hook.push([{"project": "p", "title": "X", "status": "done"}])
    assert called == []


def test_main_dispatches_session_end(tmp_path, monkeypatch):
    p = tmp_path / "s.jsonl"; _write(p, "▶ feature start — proj: Unfinished")
    captured = []
    monkeypatch.setattr(feature_hook, "push", lambda items: captured.append(items))
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(
        {"hook_event_name": "SessionEnd", "transcript_path": str(p)})))
    feature_hook.main()
    assert captured[0][0]["title"] == "Unfinished" and captured[0][0]["auto_closed"] is True


def test_main_dispatches_stop(tmp_path, monkeypatch):
    p = tmp_path / "s.jsonl"
    _write(p, "✅ feature done — proj: Finished")
    captured = []
    monkeypatch.setattr(feature_hook, "push", lambda items: captured.append(items))
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(
        {"hook_event_name": "Stop", "transcript_path": str(p)})))
    feature_hook.main()
    assert captured[0][0]["title"] == "Finished" and captured[0][0]["status"] == "done"
