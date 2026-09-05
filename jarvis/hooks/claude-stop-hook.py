#!/usr/bin/env python3
"""
jarvis/hooks/claude-stop-hook.py — Claude Code "Stop" hook (runs on the LAPTOP).

When a Claude Code turn ends, this reads the hook payload on stdin, pulls the final
assistant message out of the session transcript, and ships it to the VPS gateway over
ssh stdin. No ports are opened anywhere; the gateway summarises, speaks, and delivers a
Telegram voice note. Failure here must NEVER block or slow Claude Code, so everything is
best-effort with short timeouts and a local log.

Register in ~/.claude/settings.json (see jarvis/README.md):
  "hooks": { "Stop": [ { "hooks": [ { "type": "command",
      "command": "python C:/Users/rajra/OneDrive/Desktop/raj-second-brain/jarvis/hooks/claude-stop-hook.py" } ] } ] }

Env knobs: JARVIS_MODE=brief|detailed|full (default brief), JARVIS_MIN_CHARS (default 400 —
shorter answers are not worth a voice note), JARVIS_MIN_GAP (default 600 s — at most one voice
note per ten minutes, so a busy session does not flood the phone), JARVIS_DISABLE=1 to switch off.

The ship is fire-and-forget: the gateway needs 30–150 s to summarise and speak, and a Stop hook
blocks the turn until it returns, so the ssh child is detached and its output lands in the log.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

VPS = os.environ.get("JARVIS_VPS", "root@<vps-ip>")
REMOTE = "/opt/jarvis/venv/bin/python /opt/jarvis/gateway.py"
LOG = Path.home() / ".claude" / "jarvis-hook.log"
MIN_CHARS = int(os.environ.get("JARVIS_MIN_CHARS", "400"))


def log(msg: str) -> None:
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")
    except OSError:
        pass


def last_assistant_text(transcript: Path) -> str:
    """Transcript is JSONL; find the last assistant message and join its text blocks."""
    last = ""
    try:
        with open(transcript, encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = rec.get("message") or rec
                if (rec.get("type") == "assistant" or msg.get("role") == "assistant"):
                    content = msg.get("content")
                    if isinstance(content, str):
                        last = content
                    elif isinstance(content, list):
                        parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
                        if parts:
                            last = "\n".join(parts)
    except OSError as e:
        log(f"transcript unreadable: {e}")
    return last.strip()


def main() -> int:
    if os.environ.get("JARVIS_DISABLE") == "1":
        return 0
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    if payload.get("stop_hook_active"):          # we are already inside a stop-hook cycle
        return 0
    tp = payload.get("transcript_path")
    if not tp:
        log("no transcript_path in payload")
        return 0
    text = last_assistant_text(Path(tp))
    if len(text) < MIN_CHARS:
        log(f"skipped: {len(text)} chars < {MIN_CHARS}")
        return 0
    title = f"Claude Code · {Path(payload.get('cwd', '')).name or 'session'}"
    mode = os.environ.get("JARVIS_MODE", "brief")
    gap = int(os.environ.get("JARVIS_MIN_GAP", "600"))
    stamp = LOG.with_name("jarvis-hook.last")
    try:
        if gap and stamp.exists():
            age = int(time.time() - stamp.stat().st_mtime)
            if age < gap:
                log(f"skipped: last brief {age}s ago < JARVIS_MIN_GAP={gap}")
                return 0
    except OSError:
        pass
    try:
        outbox = LOG.with_name("jarvis-outbox")
        outbox.mkdir(exist_ok=True)
        for old in outbox.glob("*.txt"):                       # keep the outbox to one day
            if time.time() - old.stat().st_mtime > 86400:
                old.unlink(missing_ok=True)
        body = outbox / f"{datetime.now():%Y%m%dT%H%M%S}.txt"
        body.write_text(text, encoding="utf-8")
        cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", VPS,
               f"{REMOTE} --mode {mode} --source claude-code --title {json.dumps(title)}"]
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        with open(body, "rb") as fin, open(LOG, "ab") as fout:
            subprocess.Popen(cmd, stdin=fin, stdout=fout, stderr=subprocess.STDOUT, creationflags=flags)
        stamp.touch()
        log(f"shipped {len(text)} chars mode={mode} title={title!r} (detached; gateway output follows in this log)")
    except Exception as e:
        log(f"ship failed: {type(e).__name__}: {e}")
    return 0     # never fail the hook


if __name__ == "__main__":
    raise SystemExit(main())
