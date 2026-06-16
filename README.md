# Pi Viz Dashboard

A self-hosted, always-on dashboard for a Raspberry Pi driving a wall-mounted touchscreen.
The first board shows **live Claude usage** alongside an **auto-populated, status-tagged log
of features** you've shipped — extracted from your Claude Code transcripts with **no API key**.
Built as a swipeable multi-board carousel so you can add more boards over time.

![Dashboard](docs/img/dashboard.png)

*Live at 1920×440 (an ultra-wide "strip" panel): Claude usage on the left, a scrollable
feature log on the right. Swipe to switch boards; an auto-dimming menu (lower-left) toggles
auto-cycle. Demo data shown.*

---

## Highlights

- **Live quota** — polls Anthropic's `oauth/usage` endpoint with the Pi's own Claude login and
  auto-refreshes the token. Renders whichever windows your plan exposes (5-hour, 7-day, model
  sub-limits, credits).
- **Auto feature log, no API key** — a job rsyncs your Claude Code transcripts to the Pi, which
  extracts completed/in-progress features locally via `claude -p` (your subscription, not
  pay-as-you-go). Dedupes, infers the project name, and never regresses `done → in_progress`.
- **Multi-board carousel** — swipe (or use a phone) to switch boards; auto-hiding dot indicator;
  optional timed auto-cycle with a countdown bar. Ships with one board; adding another is
  appending a module.
- **Phone control** — a small `/control` page mirrors the on-screen menu (cycle, interval,
  next/prev) and stays in sync with the wall.
- **Touch-friendly** — custom pointer-based drag-to-scroll and drag-to-switch (the cheap strip
  panels often register as a mouse, so native touch scrolling doesn't fire).

## How it works

```
  YOUR MAC (launchd, every 20 min)            THE PI (always on)
  rsync ~/.claude/projects/*.jsonl  ───────▶   ~/claude-projects/      FastAPI :8080
        (dumb file copy, no key)                     │                 ├─ GET/POST /api/features
                                                     ▼                 ├─ GET/POST /api/display
                                          viz-scanner.timer (20 min):  ├─ GET  /api/quota (cached)
                                           read transcripts            ├─ GET  /         (wall page)
                                           → claude -p extract          └─ GET  /control  (phone)
                                           → POST localhost            quota poller → oauth/usage
                                                                        (the Pi's own claude login)
```

The data is *born* on the machine you run Claude Code on, so a tiny sync ships it to the Pi; the
Pi does the rest and is otherwise self-standing.

## Stack

- **Server (Pi):** Python, FastAPI + uvicorn, SQLite. No frontend framework — vanilla JS modules.
- **Extraction:** the locally-installed `claude` CLI in `-p` (print) mode. No `ANTHROPIC_API_KEY`.
- **Kiosk:** Chromium in `--kiosk` under labwc (Wayland) on Raspberry Pi OS.

## Repo layout

| Path | Runs on | Purpose |
|---|---|---|
| `server/` | Pi | FastAPI app, SQLite store, quota fetch/refresh/parse, static board carousel |
| `server/static/` | Pi | carousel + board modules (`boards/`), nav, menu, `/control` page |
| `scanner/` | Pi | transcript reader → `claude -p` extractor → POST (crash-safe offsets) |
| `cli/log-feature` | either | manually log a feature |
| `deploy/` | both | systemd units, kiosk autostart, Mac→Pi sync launchd plist, `deploy-to-pi.sh` |

## Quick start

Prereqs: a Raspberry Pi (tested on Pi 4, Raspberry Pi OS / Debian trixie, labwc) with an HDMI
touchscreen, Node + Claude Code installed and logged in on the Pi (`claude` → `/login`), and a
Mac/Linux box where you run Claude Code.

```bash
# 1. From your dev machine, deploy the server to the Pi (adapt the SSH host first — see below)
./deploy/deploy-to-pi.sh

# 2. On the Pi: enable the kiosk autostart + the feature-scanner timer (see deploy/INSTALL.md)
# 3. On your dev machine: load the transcript-sync launchd job (see deploy/INSTALL.md)
```

Full step-by-step (SSH alias, secret token, systemd units, kiosk, sync job) is in
[`deploy/INSTALL.md`](deploy/INSTALL.md). Paths in `deploy/` use `YOUR_USERNAME`/`monitoring-pi`
placeholders — adapt them to your setup.

## Configuration

| Where | Var | Purpose |
|---|---|---|
| Pi server | `VIZ_DB` | SQLite path |
| Pi server + scanner | `VIZ_TOKEN` | shared secret gating `POST /api/*` writes |
| Pi scanner | `VIZ_PI_URL` | `http://localhost:8080` |
| Pi scanner | `VIZ_PROJECTS_DIR` | where the Mac rsyncs transcripts (e.g. `~/claude-projects`) |

There is **no API key** — extraction uses the Pi's own `claude login` via `claude -p`. The shared
write token lives in a gitignored `.viz-token.local` and is injected into the wall + `/control`
pages at serve time (LAN-only).

## Tests

```bash
python -m pytest server -q     # FastAPI + SQLite (display state, quota parse, endpoints)
python -m pytest scanner -q    # transcript reader, extractor, crash-safe scan orchestration
```

## License

MIT — see [LICENSE](LICENSE).
