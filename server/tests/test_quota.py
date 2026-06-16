import json, os, stat, pathlib
from server import quota

FIX = pathlib.Path(__file__).parent / "fixtures"

def test_write_credentials_atomic_roundtrip(tmp_path):
    p = tmp_path / ".credentials.json"
    p.write_text(json.dumps({"claudeAiOauth": {"accessToken": "old", "refreshToken": "r", "expiresAt": 1}}))
    quota.write_credentials(p, {"accessToken": "new", "refreshToken": "r2", "expiresAt": 2})
    data = json.loads(p.read_text())
    assert data["claudeAiOauth"]["accessToken"] == "new"
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600
    assert list(tmp_path.glob(".credentials.*.tmp")) == []  # no leftover temp files

def test_read_credentials_handles_either_top_key(tmp_path):
    p = tmp_path / "creds.json"
    p.write_text(json.dumps({"oauth": {"accessToken": "a", "refreshToken": "r", "expiresAt": 123}}))
    oauth = quota.read_credentials(p)
    assert oauth["accessToken"] == "a"

def test_read_credentials_picks_object_with_token_fields(tmp_path):
    # Mirrors a real post-`claude login` creds file: mcpOAuth (no token fields)
    # listed before claudeAiOauth. Must pick the one with accessToken+expiresAt.
    p = tmp_path / "creds.json"
    p.write_text(json.dumps({
        "mcpOAuth": {"serverName": {"foo": "bar"}},
        "claudeAiOauth": {"accessToken": "a", "refreshToken": "r", "expiresAt": 123},
    }))
    oauth = quota.read_credentials(p)
    assert oauth["accessToken"] == "a"
    assert oauth["expiresAt"] == 123

def test_is_expired_uses_buffer():
    assert quota.is_expired({"expiresAt": 1000}, now_ms=1000, buffer_ms=0) is True
    assert quota.is_expired({"expiresAt": 10_000}, now_ms=1000, buffer_ms=0) is False

def test_parse_usage_against_real_fixture():
    data = json.loads((FIX / "usage_sample.json").read_text())
    snap = quota.parse_usage(data)
    # five_hour + seven_day are always present for a subscription; each has 0..100 pct + label
    assert "five_hour" in snap and "seven_day" in snap
    for w in snap.values():
        assert 0 <= w["pct"] <= 100
        assert "label" in w

def test_window_uses_utilization_as_percent():
    snap = quota.parse_usage({
        "five_hour": {"utilization": 6.0, "resets_at": "x"},
        "seven_day": {"utilization": 36.0, "resets_at": "y"},
    })
    assert snap["five_hour"]["pct"] == 6.0
    assert snap["five_hour"]["label"] == "5-hour"

def test_null_windows_are_skipped():
    snap = quota.parse_usage({
        "five_hour": {"utilization": 1.0},
        "seven_day": {"utilization": 1.0},
        "seven_day_opus": None,
        "seven_day_sonnet": {"utilization": 9.0},
    })
    assert "seven_day_opus" not in snap
    assert snap["seven_day_sonnet"]["pct"] == 9.0

def test_credits_included_only_when_extra_usage_enabled():
    base = {"five_hour": {"utilization": 1.0}, "seven_day": {"utilization": 1.0}}
    off = quota.parse_usage({**base, "extra_usage": {"is_enabled": False, "utilization": None}})
    assert "credits" not in off
    on = quota.parse_usage({**base, "extra_usage": {
        "is_enabled": True, "utilization": 50.0, "used_credits": 70, "monthly_limit": 140, "currency": "USD"}})
    assert on["credits"]["pct"] == 50.0
    assert "70" in on["credits"]["detail"]
