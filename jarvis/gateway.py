#!/usr/bin/env python3
"""
jarvis/gateway.py — turn a long AI output into a short spoken briefing on the phone.

Runs ON THE VPS. Two entry points over the same pipeline:

  CLI (used by the Claude Code Stop hook over ssh, no open ports):
      echo "<long text>" | /opt/jarvis/venv/bin/python /opt/jarvis/gateway.py --mode brief --title "session"
  HTTP (local only, for future PWA / n8n):
      /opt/jarvis/venv/bin/uvicorn gateway:app --host 127.0.0.1 --port 8787

Pipeline (docs/ARCHITECTURE.md §8):
  text -> summarize (Ollama, local, $0) -> TTS (Kokoro CPU; Piper fallback; text-only fallback)
       -> deliver (Telegram voice note via a DEDICATED bot; never the the platform bot) -> jsonl audit

Modes: brief (~20-60 s spoken), detailed (~2-5 min), full (read the original).
The briefing frame is fixed: what happened / did it work / what matters / needs Raj / next.

Secrets live in /opt/jarvis/.env (mode 600) — JARVIS_TELEGRAM_BOT_TOKEN, JARVIS_TELEGRAM_CHAT_ID —
and are never printed. If they are absent, the brief is still produced and logged; delivery
is skipped with a clear note.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("JARVIS_MODEL", "qwen2.5:3b-instruct")
ENV_FILE = Path("/opt/jarvis/.env")
LOG = Path("/opt/jarvis/briefs.jsonl")
OUT_DIR = Path("/opt/jarvis/out")

FRAME = ("You write spoken briefings for a busy operator who is driving or away from a screen. "
         "Plain spoken English, no markdown, no bullet symbols, no code, no URLs. Answer, in order: "
         "what happened, did it work, what matters, what needs Raj, what is next. "
         "Never invent outcomes; if the text is unclear, say what is unclear.")
LIMITS = {"brief": 110, "detailed": 420}


def _env() -> dict:
    out = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("JARVIS_TELEGRAM_BOT_TOKEN", "JARVIS_TELEGRAM_CHAT_ID"):
        if os.environ.get(k):
            out[k] = os.environ[k]
    return out


# ----------------------------------------------------------------- summarize --
def summarize(text: str, mode: str, title: str = "") -> str:
    if mode == "full":
        return text.strip()
    words = LIMITS.get(mode, LIMITS["brief"])
    prompt = (f"{FRAME}\nHard limit: {words} words.\n\n"
              f"TITLE: {title or 'update'}\n\nTEXT:\n{text[:12000]}\n\nBRIEFING:")
    # keep_alive keeps the 3B model resident between briefs: the first measured run spent
    # most of its 185 s on a cold load under CPU contention. num_ctx bounds RAM.
    r = requests.post(f"{OLLAMA}/api/generate",
                      json={"model": MODEL, "prompt": prompt, "stream": False, "keep_alive": "30m",
                            "options": {"temperature": 0.2, "num_predict": int(words * 1.8), "num_ctx": 8192}},
                      timeout=300)
    r.raise_for_status()
    out = r.json().get("response", "").strip()
    return out or "The update could not be summarised. Read the original."


# ------------------------------------------------------------------------ tts --
def tts(text: str, wav_path: Path) -> str:
    """Return the backend used: kokoro | piper | none."""
    try:
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline
        pipe = KPipeline(lang_code="a")
        audio = None
        for _, _, a in pipe(text, voice=os.environ.get("JARVIS_VOICE", "af_heart")):
            audio = a if audio is None else np.concatenate([audio, a])
        if audio is None:
            raise RuntimeError("kokoro produced no audio")
        sf.write(str(wav_path), audio, 24000)
        return "kokoro"
    except Exception as e:
        print(f"[jarvis] kokoro unavailable ({type(e).__name__}: {e}); trying piper", file=sys.stderr)
    # pip installs the `piper` console script inside the venv, which is not on root's PATH.
    piper = shutil.which("piper") or next((p for p in ("/opt/jarvis/venv/bin/piper",) if Path(p).exists()), None)
    model = os.environ.get("PIPER_MODEL", "/opt/jarvis/piper/en_US-lessac-medium.onnx")
    if piper and Path(model).exists():
        subprocess.run([piper, "--model", model, "--output_file", str(wav_path)],
                       input=text.encode(), check=True, timeout=300)
        return "piper"
    return "none"


def to_opus(wav_path: Path) -> Path | None:
    ff = shutil.which("ffmpeg")
    if not ff:
        return None
    ogg = wav_path.with_suffix(".ogg")
    r = subprocess.run([ff, "-loglevel", "error", "-y", "-i", str(wav_path), "-c:a", "libopus",
                        "-b:a", "32k", "-application", "voip", str(ogg)], timeout=120)
    return ogg if r.returncode == 0 and ogg.exists() else None


# -------------------------------------------------------------------- deliver --
def deliver(env: dict, title: str, brief: str, audio: Path | None) -> str:
    tok, chat = env.get("JARVIS_TELEGRAM_BOT_TOKEN"), env.get("JARVIS_TELEGRAM_CHAT_ID")
    if not tok or not chat:
        return "skipped: JARVIS_TELEGRAM_BOT_TOKEN / CHAT_ID not configured"
    base = f"https://api.telegram.org/bot{tok}"
    caption = (f"🎧 {title}\n\n{brief}")[:1000]
    try:
        if audio and audio.suffix == ".ogg":
            with open(audio, "rb") as f:
                r = requests.post(f"{base}/sendVoice", data={"chat_id": chat, "caption": caption},
                                  files={"voice": ("brief.ogg", f, "audio/ogg")}, timeout=60)
        elif audio:
            with open(audio, "rb") as f:
                r = requests.post(f"{base}/sendAudio", data={"chat_id": chat, "caption": caption, "title": title},
                                  files={"audio": (audio.name, f)}, timeout=60)
        else:
            r = requests.post(f"{base}/sendMessage", json={"chat_id": chat, "text": caption[:4000]}, timeout=30)
        r.raise_for_status()
        return "telegram: ok"
    except Exception as e:
        return f"telegram failed: {type(e).__name__}: {e}"


# ------------------------------------------------------------------- pipeline --
def run(text: str, mode: str = "brief", title: str = "update", source: str = "cli") -> dict:
    t0 = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    brief = summarize(text, mode, title)
    t1 = time.time()
    wav = OUT_DIR / f"{stamp}.wav"
    backend = tts(brief, wav)
    audio = to_opus(wav) if backend != "none" else None
    audio = audio or (wav if backend != "none" else None)
    t2 = time.time()
    status = deliver(_env(), title, brief, audio)
    rec = {"ts": stamp, "source": source, "title": title, "mode": mode, "in_chars": len(text),
           "brief_words": len(brief.split()), "tts": backend, "audio": str(audio) if audio else None,
           "delivery": status, "t_summarize": round(t1 - t0, 1), "t_tts": round(t2 - t1, 1)}
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    # keep the out dir small: last 50 briefs
    for old in sorted(OUT_DIR.glob("*.*"))[:-100]:
        old.unlink(missing_ok=True)
    return {**rec, "brief": brief}


# ----------------------------------------------------------------------- HTTP --
try:
    from fastapi import FastAPI
    from pydantic import BaseModel

    app = FastAPI(title="jarvis")

    class Brief(BaseModel):
        text: str
        mode: str = "brief"
        title: str = "update"
        source: str = "http"

    @app.get("/health")
    def health():
        return {"ok": True, "model": MODEL, "configured": bool(_env().get("JARVIS_TELEGRAM_BOT_TOKEN"))}

    @app.post("/brief")
    def brief(b: Brief):
        return run(b.text, b.mode, b.title, b.source)
except ImportError:      # CLI-only environment
    app = None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="brief", choices=["brief", "detailed", "full"])
    ap.add_argument("--title", default="update")
    ap.add_argument("--source", default="cli")
    ap.add_argument("--file", help="read text from a file instead of stdin")
    a = ap.parse_args()
    text = Path(a.file).read_text(encoding="utf-8") if a.file else sys.stdin.read()
    if not text.strip():
        print("[jarvis] empty input", file=sys.stderr)
        return 2
    rec = run(text, a.mode, a.title, a.source)
    print(json.dumps({k: v for k, v in rec.items() if k != "brief"}))
    print("---\n" + rec["brief"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
