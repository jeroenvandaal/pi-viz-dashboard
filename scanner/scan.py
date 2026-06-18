import json
import time
from pathlib import Path

from scanner.transcripts import iter_sessions, read_new_assistant_text
from scanner.extract import extract_features
from scanner.post import post_features
from scanner.markers import parse_markers, closure_items

DEFAULT_STATE = Path.home() / ".config" / "viz-scanner-state.json"
QUIET_SECS = 1800  # 30 min; > the 20-min rsync interval, so a live-but-unsynced session isn't mis-judged
MAX_AGE_DAYS = 14  # never mine an untracked session older than this — guards against a lost
                   # state file triggering a full-history `claude -p` grind over old transcripts

def load_state(path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}

def save_state(path, state: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))

def run_scan(projects_dir=None, state_path=DEFAULT_STATE, now=None, quiet_secs=QUIET_SECS,
             max_age_days=MAX_AGE_DAYS) -> None:
    from scanner.transcripts import PROJECTS_DIR
    projects_dir = projects_dir or PROJECTS_DIR
    now = now if now is not None else time.time()
    state = load_state(state_path)
    final = state.setdefault("__final__", {})  # session_key -> True once soft-closed
    for label, sess in iter_sessions(projects_dir):
        key = str(sess)
        untracked = key not in state
        offset = state.get(key, 0)
        if not isinstance(offset, int):  # tolerate any legacy/foreign shape
            offset = 0
        try:
            # Read inside the try: a file can rotate/lock between yield and read.
            info = sess.stat()
            # Guard: never mine an untracked OLD session from scratch. Without this, a
            # lost/empty state file would `claude -p` the entire transcript history (hours
            # of work + quota). Baseline it (mark seen) instead so only recent sessions mine.
            if untracked and (now - info.st_mtime) / 86400.0 > max_age_days:
                state[key] = info.st_size
                final[key] = True
                continue
            quiescent = (now - info.st_mtime) > quiet_secs
            text, new_offset = read_new_assistant_text(sess, offset)
            if quiescent:
                if not final.get(key):
                    full, _ = read_new_assistant_text(sess, 0)
                    items = closure_items(full, ended=True)
                    if items:
                        post_features(items)   # soft-close unclosed starts (+ re-affirm hard dones)
                    final[key] = True
            else:
                final.pop(key, None)           # active again (e.g. resumed) — allow future finalize
                if text.strip():
                    markers = parse_markers(text)
                    if markers:
                        post_features(markers)  # live: starts->in_progress, dones->hard done
            if text.strip():
                post_features(extract_features(text, project=label))  # LLM discovery, unchanged
            state[key] = new_offset             # advance only after POSTs succeed
        except Exception as e:
            print(f"[scan] {key}: {e} — leaving offset at {offset}")
            continue
    save_state(state_path, state)

if __name__ == "__main__":
    run_scan()
