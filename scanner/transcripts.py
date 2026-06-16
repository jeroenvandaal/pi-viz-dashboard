import json
import os
from pathlib import Path

# On the Pi, the transcripts are rsynced from the Mac into VIZ_PROJECTS_DIR.
# Falls back to the local Claude Code projects dir when unset (e.g. running on the Mac).
PROJECTS_DIR = Path(os.environ.get("VIZ_PROJECTS_DIR", str(Path.home() / ".claude" / "projects")))

def project_label(encoded_dir: str) -> str:
    # "-Users-dev-Documents-AI-Projects-myapp" -> "myapp"
    return encoded_dir.rstrip("-").split("-")[-1] or encoded_dir

def _assistant_text(event: dict) -> str:
    if event.get("type") != "assistant":
        return ""
    content = event.get("message", {}).get("content", "")
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts)

def read_new_assistant_text(path: Path, offset: int) -> tuple[str, int]:
    path = Path(path)
    size = path.stat().st_size
    if offset >= size:
        return "", offset
    chunks = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        fh.seek(offset)
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
                chunks.append(t)
    return "\n".join(chunks), size

def iter_sessions(projects_dir: Path = PROJECTS_DIR):
    projects_dir = Path(projects_dir)
    if not projects_dir.exists():
        return
    for proj_dir in projects_dir.iterdir():
        if not proj_dir.is_dir():
            continue
        label = project_label(proj_dir.name)
        for jsonl in proj_dir.glob("*.jsonl"):
            yield label, jsonl
