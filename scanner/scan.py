import json
from pathlib import Path

from scanner.transcripts import iter_sessions, read_new_assistant_text
from scanner.extract import extract_features
from scanner.post import post_features

DEFAULT_STATE = Path.home() / ".config" / "viz-scanner-state.json"

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

def run_scan(projects_dir=None, state_path=DEFAULT_STATE) -> None:
    from scanner.transcripts import PROJECTS_DIR
    projects_dir = projects_dir or PROJECTS_DIR
    state = load_state(state_path)
    for label, sess in iter_sessions(projects_dir):
        key = str(sess)
        offset = state.get(key, 0)
        try:
            # Read is inside the try too: a session file can be rotated/deleted/locked
            # between iter_sessions yielding it and this read. One bad file must not
            # abort the run and discard every sibling's offset progress.
            text, new_offset = read_new_assistant_text(sess, offset)
            if not text.strip():
                state[key] = new_offset  # nothing new (or only non-assistant lines)
                continue
            items = extract_features(text, project=label)
            post_features(items)
            state[key] = new_offset           # advance only after a successful POST
        except Exception as e:
            print(f"[scan] {key}: {e} — leaving offset at {offset}")
            continue
    save_state(state_path, state)

if __name__ == "__main__":
    run_scan()
