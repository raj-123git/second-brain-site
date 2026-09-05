#!/bin/bash
# jarvis/finish-setup.sh — run ON THE VPS after Raj has stored JARVIS_TELEGRAM_BOT_TOKEN in /opt/jarvis/.env
# and pressed Start on the bot. Discovers the chat id from the bot's own updates, stores it, and sends
# the first spoken briefing. The token is read into a shell variable and never printed or logged.
#   ssh root@<vps-ip> 'bash -s' < jarvis/finish-setup.sh
set -u
ENV=/opt/jarvis/.env
[ -f "$ENV" ] || { echo "no $ENV — run the token command first"; exit 1; }
TOK=$(grep -E '^JARVIS_TELEGRAM_BOT_TOKEN=' "$ENV" | cut -d= -f2- | tr -d '\r"'"'"' ')
[ -n "$TOK" ] || { echo "token line missing in $ENV"; exit 1; }
echo "token present: fp=$(printf %s "$TOK" | sha256sum | cut -c1-12)"
ME=$(curl -s -m 15 "https://api.telegram.org/bot${TOK}/getMe")
echo "getMe ok=$(printf %s "$ME" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("ok"), d.get("result",{}).get("username"))')"
UPD=$(curl -s -m 15 "https://api.telegram.org/bot${TOK}/getUpdates")
CHAT=$(printf %s "$UPD" | python3 -c '
import json,sys
d=json.load(sys.stdin); ids=[]
for u in d.get("result",[]):
    m=u.get("message") or u.get("my_chat_member",{}) or {}
    c=(m.get("chat") or {}).get("id")
    if c: ids.append(c)
print(ids[-1] if ids else "")')
if [ -z "$CHAT" ]; then echo "no chat id yet: open t.me/rajranpariya_jarvis_bot, press Start (or send any message), then re-run"; exit 2; fi
echo "chat id discovered: $CHAT"
grep -q '^JARVIS_TELEGRAM_CHAT_ID=' "$ENV" && sed -i "s/^JARVIS_TELEGRAM_CHAT_ID=.*/JARVIS_TELEGRAM_CHAT_ID=$CHAT/" "$ENV" || printf 'JARVIS_TELEGRAM_CHAT_ID=%s\n' "$CHAT" >> "$ENV"
chmod 600 "$ENV"; echo "stored; $ENV has $(wc -l < "$ENV") lines, mode $(stat -c %a "$ENV")"
echo "=== first briefing (summarize -> Piper TTS -> Telegram voice note) ==="
printf '%s\n' "Jarvis is live. Today the site rajranpariya.com went live on a new domain, the VPS was rebooted into a new kernel with the firewall proven to restore itself, twenty-three content rows were drafted and are waiting for approval, and the Telegram bot you are hearing this through was created this afternoon. Nothing needs you right now except the approvals." \
  | /opt/jarvis/venv/bin/python /opt/jarvis/gateway.py --mode brief --title "Jarvis is live" --source setup 2>&1 | tail -4
echo "=== last audit record ==="; tail -1 /opt/jarvis/briefs.jsonl | python3 -c 'import json,sys; d=json.load(sys.stdin); print({k:d[k] for k in ("ts","tts","delivery","brief_words","t_summarize","t_tts")})'
