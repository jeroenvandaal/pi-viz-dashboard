import json
import os
import subprocess
import sys

from scanner.markers import parse_markers, closure_items
from scanner.transcripts import read_new_assistant_text, _assistant_text


def last_assistant_text(path) -> str:
    """Text of the final assistant message in the transcript (for the Stop hook)."""
    last = ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = _assistant_text(evt)
                if t:
                    last = t
    except OSError:
        return ""
    return last


def stop_items(transcript_path) -> list[dict]:
    """Markers in the latest assistant turn — pushed live as Claude emits them."""
    return parse_markers(last_assistant_text(transcript_path))


def session_end_items(transcript_path) -> list[dict]:
    """On session end, soft-close every start with no matching done.
    Best-effort: a missing/unreadable transcript yields no items (never raises)."""
    try:
        text, _ = read_new_assistant_text(transcript_path, 0)
    except OSError:
        return []
    return closure_items(text, ended=True)


def push(items: list[dict]) -> None:
    """Best-effort POST to the Pi over the same SSH path rsync uses. Never raises:
    if the Pi is unreachable the scanner + reaper recover the same state later.
    Set VIZ_HOOK_SSH to the dashboard host; unset means no-op."""
    if not items:
        return
    host = os.environ.get("VIZ_HOOK_SSH")
    if not host:
        return
    payload = json.dumps({"items": items}).encode()
    remote = ('. ~/.config/viz-dashboard.env 2>/dev/null; '
              'curl -s -m 10 -XPOST localhost:8080/api/features '
              '-H "X-Dashboard-Token: $VIZ_TOKEN" --data-binary @-')
    try:
        subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", host, remote],
            input=payload, timeout=20,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def main() -> None:
    try:
        ev = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return
    path = ev.get("transcript_path")
    if not path or not os.path.exists(path):
        return
    if ev.get("hook_event_name") == "SessionEnd":
        push(session_end_items(path))
    else:
        push(stop_items(path))


if __name__ == "__main__":
    main()
