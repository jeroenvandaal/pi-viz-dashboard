import importlib
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("VIZ_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("VIZ_TOKEN", "secret")
    monkeypatch.setenv("VIZ_NO_POLLER", "1")  # disable background poll in tests
    from server import app as appmod
    importlib.reload(appmod)
    return TestClient(appmod.app)

def test_post_requires_token(client):
    r = client.post("/api/features", json={"items": []})
    assert r.status_code == 401

def test_post_and_list_features(client):
    payload = {"items": [
        {"project": "webapp", "title": "Email integration", "summary": "PR #4", "status": "in_progress"},
        {"project": "apiservice", "title": "Prod deploy", "summary": "live", "status": "done"},
    ]}
    r = client.post("/api/features", json=payload, headers={"X-Dashboard-Token": "secret"})
    assert r.status_code == 200
    assert r.json() == {"inserted": 2, "updated": 0}
    rows = client.get("/api/features").json()["features"]
    assert [x["title"] for x in rows] == ["Email integration", "Prod deploy"]  # in_progress first

def test_quota_returns_cache_shape(client):
    r = client.get("/api/quota")
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"data", "updated_at", "stale"}

def test_get_display_defaults(client):
    body = client.get("/api/display").json()
    assert body == {"active_board": "claude", "cycle": False, "interval_sec": 10}

def test_post_display_requires_token(client):
    r = client.post("/api/display", json={"cycle": True})
    assert r.status_code == 401

def test_post_display_updates_and_returns_state(client):
    r = client.post("/api/display", json={"cycle": True, "interval_sec": 30},
                    headers={"X-Dashboard-Token": "secret"})
    assert r.status_code == 200
    assert r.json() == {"active_board": "claude", "cycle": True, "interval_sec": 30}
    # persisted across a fresh GET
    assert client.get("/api/display").json()["interval_sec"] == 30

def test_index_injects_write_token(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert '__VIZ_TOKEN__ = "secret"' in r.text   # token injected, placeholder gone
    assert "__TOKEN__" not in r.text

def test_control_page_served_with_token(client):
    r = client.get("/control")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "secret" in r.text          # token injected for client-side writes
    assert "Auto-cycle" in r.text
