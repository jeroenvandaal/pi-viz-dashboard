import re

# Matches a marker on its own line:  ▶ feature start — <project-slug>: <name>
#                                     ✅ feature done — <project-slug>: <name>
# Project is slug-constrained so a colon inside <name> doesn't mis-split.
_MARKER = re.compile(
    r"^\s*(▶|✅)\s*feature\s+(start|done)\s*—\s*([a-z0-9._-]+)\s*:\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_STATUS = {"start": "in_progress", "done": "done"}

def parse_markers(text: str) -> list[dict]:
    out = []
    for _glyph, verb, project, name in _MARKER.findall(text or ""):
        out.append({
            "project": project.strip().lower(),
            "title": name.strip(),
            "status": _STATUS[verb.lower()],
            "source": "marker",
            "summary": "",
        })
    return out


def _key(item: dict) -> tuple:
    return (item["project"], item["title"].strip().lower())

def closure_items(text: str, ended: bool) -> list[dict]:
    """Marker items to POST for a session.
    ended=False (active): markers as-is — starts→in_progress, dones→done (hard).
    ended=True  (quiescent): explicit dones stay hard; each ▶ start with no matching
    ✅ done becomes a soft close (status 'done', auto_closed True)."""
    items = parse_markers(text)
    if not ended:
        return items
    done_keys = {_key(it) for it in items if it["status"] == "done"}
    out, seen = [], set()
    for it in items:
        k = _key(it)
        if it["status"] == "done":
            out.append(it)
        elif k not in done_keys and k not in seen:
            seen.add(k)
            out.append({**it, "status": "done", "auto_closed": True})
    return out
