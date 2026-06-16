import json
import re
import subprocess

# Extraction runs via the locally-installed, logged-in Claude Code CLI (`claude -p`),
# which uses the machine's subscription — no ANTHROPIC_API_KEY, no per-call billing.
MODEL = "haiku"

SYSTEM = """You extract a structured log of software features from a Claude Code transcript excerpt.
Return ONLY a JSON array. Each element: {"project": short lowercase repo/app name, "title": short feature name, "summary": one line of what was done, "status": "done" or "in_progress"}.
Rules:
- "project": infer the repo/app/project name from the work itself (e.g. "viz-dashboard", "apiservice", "webapp"). Use a short kebab-case slug. Leave "" only if genuinely unclear.
- Include ONLY real work that was actually performed in this excerpt (implemented, fixed, shipped, merged, refactored, deployed) or work explicitly stated as actively underway.
- status "done" only when the excerpt states it was completed/shipped/merged/passing. Otherwise "in_progress".
- DO NOT include plans, intentions, suggestions, or things merely proposed ("I'll...", "we could...", "next we should...").
- If nothing qualifies, return [].
- Keep titles stable and generic enough to match re-mentions across runs."""

VALID_STATUS = {"done", "in_progress"}

def _strip_fences(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else text

def parse_items(raw: str, fallback_project: str) -> list[dict]:
    try:
        data = json.loads(_strip_fences(raw))
    except json.JSONDecodeError:
        return []
    out = []
    for el in data if isinstance(data, list) else []:
        if not isinstance(el, dict):
            continue
        title = (el.get("title") or "").strip()
        if not title:
            continue
        status = el.get("status") if el.get("status") in VALID_STATUS else "in_progress"
        # Prefer the project the model inferred from content; fall back to the dir label.
        proj = re.sub(r"[^a-z0-9._-]+", "-", (el.get("project") or "").strip().lower()).strip("-")
        out.append({
            "project": proj or fallback_project,
            "title": title,
            "summary": (el.get("summary") or "").strip(),
            "status": status,
        })
    return out

def _claude_runner(prompt: str) -> str:
    # Pipe the prompt via stdin (avoids ARG_MAX limits on large transcripts).
    proc = subprocess.run(
        ["claude", "-p", "--model", MODEL],
        input=prompt, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p failed ({proc.returncode}): {proc.stderr[:300]}")
    return proc.stdout

def extract_features(text: str, project: str, runner=None) -> list[dict]:
    if not text.strip():
        return []
    runner = runner or _claude_runner
    prompt = f"{SYSTEM}\n\n<transcript>\n{text[:120_000]}\n</transcript>\n\nReturn ONLY the JSON array."
    return parse_items(runner(prompt), project)
