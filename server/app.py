import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles

from server import db, quota

DB_PATH = os.environ.get("VIZ_DB", "dashboard.db")
TOKEN = os.environ.get("VIZ_TOKEN", "")
STATIC_DIR = Path(__file__).parent / "static"

_quota_cache = {"data": None, "updated_at": None, "stale": True}

# oauth/usage is rate-limited (429) if polled too often — it's not meant for
# high-frequency polling. The 5h/7d windows change slowly, so poll every 5 min.
# On error (e.g. a transient 429), keep the last-known data and back off harder.
POLL_OK_INTERVAL = 300
POLL_ERR_INTERVAL = 600

# Eagerly init DB so the table exists whether or not lifespan runs (e.g. in tests).
db.init_db(DB_PATH)

async def _poll_quota():
    while True:
        try:
            snap = await asyncio.to_thread(quota.get_snapshot)
            _quota_cache.update(data=snap, updated_at=datetime.now(timezone.utc).isoformat(), stale=False)
            delay = POLL_OK_INTERVAL
        except Exception:
            _quota_cache["stale"] = True
            delay = POLL_ERR_INTERVAL
        await asyncio.sleep(delay)

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db(DB_PATH)
    task = None
    if not os.environ.get("VIZ_NO_POLLER"):
        task = asyncio.create_task(_poll_quota())
    yield
    if task:
        task.cancel()

app = FastAPI(lifespan=lifespan)

def require_token(x_dashboard_token: str = Header(default="")):
    if not TOKEN or x_dashboard_token != TOKEN:
        raise HTTPException(status_code=401, detail="bad token")

@app.get("/api/quota")
def get_quota():
    return _quota_cache

@app.get("/api/features")
def get_features():
    conn = db.connect(DB_PATH)
    try:
        return {"features": db.list_features(conn)}
    finally:
        conn.close()

@app.post("/api/features", dependencies=[Depends(require_token)])
def post_features(payload: dict):
    conn = db.connect(DB_PATH)
    inserted = updated = 0
    try:
        for item in payload.get("items", []):
            result = db.upsert_feature(
                conn,
                project=item["project"],
                title=item["title"],
                summary=item.get("summary"),
                status=item.get("status", "in_progress"),
                source=item.get("source", "scanner"),
            )
            if result == "inserted":
                inserted += 1
            else:
                updated += 1
        return {"inserted": inserted, "updated": updated}
    finally:
        conn.close()

@app.get("/api/display")
def get_display():
    conn = db.connect(DB_PATH)
    try:
        return db.get_display(conn)
    finally:
        conn.close()

BOARD_ORDER = ["claude"]  # keep in sync with server/static/boards.js order

@app.post("/api/display", dependencies=[Depends(require_token)])
def post_display(payload: dict):
    conn = db.connect(DB_PATH)
    try:
        fields = {k: payload[k] for k in ("active_board", "cycle", "interval_sec") if k in payload}
        if "nudge" in payload and BOARD_ORDER:
            cur = db.get_display(conn)["active_board"]
            i = BOARD_ORDER.index(cur) if cur in BOARD_ORDER else 0
            fields["active_board"] = BOARD_ORDER[(i + int(payload["nudge"])) % len(BOARD_ORDER)]
        return db.set_display(conn, **fields)
    finally:
        conn.close()

@app.get("/control")
def control_page():
    from fastapi.responses import HTMLResponse
    html = (STATIC_DIR / "control.html").read_text().replace("__TOKEN__", TOKEN)
    return HTMLResponse(html)

@app.get("/")
def index_page():
    # Serve the wall page with the write token injected so its on-screen menu can
    # persist display state. Same token-injection pattern as /control.
    from fastapi.responses import HTMLResponse
    html = (STATIC_DIR / "index.html").read_text().replace("__TOKEN__", TOKEN)
    return HTMLResponse(html)

# Static assets (js/css) at "/*" (mounted last so /api/* and explicit routes win)
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
