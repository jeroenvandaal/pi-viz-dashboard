import json
import os
import tempfile
import time
from pathlib import Path

import httpx

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
REFRESH_URL = "https://platform.claude.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
CREDS_PATH = Path.home() / ".claude" / ".credentials.json"

USAGE_HEADERS = {
    "anthropic-beta": "oauth-2025-04-20",
    "User-Agent": "viz-dashboard/1.0",
}

# Subscription windows we surface, in display order, with friendly labels.
_WINDOW_LABELS = {
    "five_hour": "5-hour",
    "seven_day": "7-day",
    "seven_day_opus": "7-day Opus",
    "seven_day_sonnet": "7-day Sonnet",
}

def _oauth_key(data: dict) -> str:
    # The creds file can hold several *auth* objects (e.g. claudeAiOauth AND
    # mcpOAuth after `claude login`). Only the chat OAuth object carries the
    # usage-API token fields — select by content, not by name substring.
    for k, v in data.items():
        if isinstance(v, dict) and "accessToken" in v and "expiresAt" in v:
            return k
    for name in ("claudeAiOauth", "oauth"):  # fallback to known names
        if name in data:
            return name
    raise KeyError("no usable oauth object in credentials")

def read_credentials(path=CREDS_PATH) -> dict:
    data = json.loads(Path(path).read_text())
    return data[_oauth_key(data)]

def write_credentials(path, oauth: dict) -> None:
    # Atomic write: this is the SAME file Claude Code reads/refreshes. A truncating
    # write that's interrupted (power loss, kill) would corrupt credentials machine-wide.
    p = Path(path)
    data = json.loads(p.read_text())
    data[_oauth_key(data)] = oauth
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".credentials.", suffix=".tmp")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(data))
        os.replace(tmp, p)  # atomic rename
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise

def is_expired(oauth: dict, now_ms=None, buffer_ms=60_000) -> bool:
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    return now_ms >= int(oauth["expiresAt"]) - buffer_ms

def refresh(refresh_token: str, client: httpx.Client) -> dict:
    resp = client.post(REFRESH_URL, json={
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()

def fetch_usage(access_token: str, client: httpx.Client) -> dict:
    resp = client.get(USAGE_URL, headers={"Authorization": f"Bearer {access_token}", **USAGE_HEADERS}, timeout=15)
    resp.raise_for_status()
    return resp.json()

def _window(obj, label) -> dict | None:
    if not obj or obj.get("utilization") is None:
        return None
    pct = round(float(obj["utilization"]), 1)   # already a 0..100 percentage
    return {"pct": max(0.0, min(100.0, pct)), "resets_at": obj.get("resets_at"),
            "detail": None, "label": label}

def parse_usage(data: dict) -> dict:
    out = {}
    for key, label in _WINDOW_LABELS.items():
        w = _window(data.get(key), label)
        if w:
            out[key] = w
    eu = data.get("extra_usage") or {}
    if eu.get("is_enabled") and eu.get("utilization") is not None:
        pct = round(float(eu["utilization"]), 1)
        detail = None
        if eu.get("used_credits") is not None and eu.get("monthly_limit") is not None:
            detail = f"{eu['used_credits']} / {eu['monthly_limit']} {eu.get('currency') or ''}".strip()
        out["credits"] = {"pct": max(0.0, min(100.0, pct)), "resets_at": None,
                          "detail": detail, "label": "Credits"}
    return out

def get_snapshot(creds_path=CREDS_PATH, client: httpx.Client | None = None) -> dict:
    own = client is None
    client = client or httpx.Client()
    try:
        oauth = read_credentials(creds_path)
        if is_expired(oauth):
            r = refresh(oauth["refreshToken"], client)
            oauth["accessToken"] = r["access_token"]
            if r.get("refresh_token"):
                oauth["refreshToken"] = r["refresh_token"]
            oauth["expiresAt"] = int(time.time() * 1000) + int(r["expires_in"]) * 1000
            write_credentials(creds_path, oauth)
        return parse_usage(fetch_usage(oauth["accessToken"], client))
    finally:
        if own:
            client.close()
