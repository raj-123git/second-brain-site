# Jarvis — spoken briefings instead of walls of text

Goal (pack §I, §16–18): Claude can stay verbose internally; Raj hears a 20–60 second
briefing on his phone that answers *what happened / did it work / what matters / what
needs me / what is next*. Driving mode is audio-first.

## Stack — all $0, all on the existing VPS

| Step | Component | Where | Why |
|---|---|---|---|
| Trigger | Claude Code `Stop` hook → `hooks/claude-stop-hook.py` | laptop | fires when a turn ends; ships the final message over **ssh stdin** — no ports opened |
| Summarize | Ollama `qwen2.5:3b-instruct` (already pulled) | VPS | local, deterministic frame, $0 |
| Speak | **Kokoro-82M** on CPU; Piper fallback; text-only fallback | VPS | quality/speed measured on this box (see PROJECT_STATUS); no cloud TTS |
| Deliver | **Telegram voice note via a DEDICATED bot** | phone | already in Raj's pocket; voice notes play with one tap and work in the car |
| Audit | `/opt/jarvis/briefs.jsonl` | VPS | every brief: timing, backend, delivery result |

### Why Telegram and not self-hosted ntfy (for now)
ntfy needs a public hostname for the phone app to reach it. The only domain that exists
today is the platform's, and the privacy firewall forbids sharing it. A dedicated Telegram
bot costs nothing, needs no domain, and Raj already lives in Telegram. ntfy/PWA can be
added the day a personal domain is approved (unknown U3).

**Never reuse the the platform Telegram bot** — a shared secret is a shared identity.

## Modes
`brief` ≈110 words (~45 s) · `detailed` ≈420 words (~3 min) · `full` reads the original.

## Setup (one-time)

1. **Raj creates the bot** — Telegram → @BotFather → `/newbot` → name it anything private
   (e.g. "Jarvis RR") → copy the token. Then message the bot once and get the chat id:
   `https://api.telegram.org/bot<TOKEN>/getUpdates` → `chat.id`.
2. **Store the secrets on the VPS without echoing them** (paste when prompted):
   ```bash
   ssh -t root@<vps-ip> 'read -rsp "Bot token: " T; echo; read -rp "Chat id: " C; umask 077; printf "JARVIS_TELEGRAM_BOT_TOKEN=%s\nJARVIS_TELEGRAM_CHAT_ID=%s\n" "$T" "$C" > /opt/jarvis/.env; echo "saved fp=$(printf %s "$T" | sha256sum | cut -c1-12)"'
   ```
3. **Register the hook on the laptop** — add to `~/.claude/settings.json`:
   ```json
   "hooks": {
     "Stop": [ { "hooks": [ { "type": "command", "timeout": 30,
       "command": "python C:/Users/rajra/OneDrive/Desktop/raj-second-brain/jarvis/hooks/claude-stop-hook.py" } ] } ]
   }
   ```
   Knobs: `JARVIS_MODE=brief|detailed|full`, `JARVIS_MIN_CHARS=400`, `JARVIS_MIN_GAP=600` (seconds between voice notes; the hook returns at once and the ssh child finishes in the background), `JARVIS_DISABLE=1`.

## Test
```bash
echo "Long text here..." | ssh root@<vps-ip> '/opt/jarvis/venv/bin/python /opt/jarvis/gateway.py --mode brief --title test'
```
Prints the audit record and the brief; sends the voice note if the bot is configured.

## Optional HTTP (local only)
`/opt/jarvis/venv/bin/uvicorn gateway:app --host 127.0.0.1 --port 8787` → `POST /brief {text, mode, title}`.
Not exposed publicly; a future PWA would go through nginx with auth on an approved domain.

## NEED FROM RAJ
- Create the dedicated Telegram bot and run the secret-store command above (2 minutes).
- Confirm the phone OS (unknown U13) — irrelevant for Telegram, relevant for a later ntfy/PWA.
