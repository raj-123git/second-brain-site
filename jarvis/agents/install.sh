#!/bin/bash
# jarvis/agents/install.sh — run from the LAPTOP (repo root). Installs the two site agents on the VPS
# and wires the traffic key without ever printing it:
#   1. copies seo-audit.py + traffic-report.py to /opt/jarvis/agents/
#   2. generates TRAFFIC_KEY on the VPS (openssl, appended to /opt/jarvis/.env, mode 600) if absent
#   3. pipes that key from the VPS straight into `wrangler pages secret put` (production + preview)
#   4. installs the crons: SEO daily 06:35 UTC (silent unless a failure or a change), SEO weekly
#      Monday 12:00 UTC (08:00 ET), traffic weekly Monday 12:10 UTC
set -euo pipefail
VPS=${JARVIS_VPS:-root@<vps-ip>}
HERE="$(cd "$(dirname "$0")/.." && pwd)"      # jarvis/
SITE_DIR="$HERE/../site"

echo "== 1. agents -> $VPS:/opt/jarvis/agents/"
ssh -o BatchMode=yes "$VPS" 'mkdir -p /opt/jarvis/agents /opt/jarvis/reports'
scp -q "$HERE/agents/seo-audit.py" "$HERE/agents/traffic-report.py" "$VPS:/opt/jarvis/agents/"
ssh -o BatchMode=yes "$VPS" 'chmod 700 /opt/jarvis/agents/*.py; python3 -m py_compile /opt/jarvis/agents/seo-audit.py /opt/jarvis/agents/traffic-report.py && echo "   compiled ok"'

echo "== 2. TRAFFIC_KEY on the VPS (generated there, never shown)"
ssh -o BatchMode=yes "$VPS" 'E=/opt/jarvis/.env; touch "$E"; chmod 600 "$E"
grep -q "^SITE=" "$E" || echo "SITE=https://rajranpariya.com" >> "$E"
if ! grep -q "^TRAFFIC_KEY=" "$E"; then echo "TRAFFIC_KEY=$(openssl rand -hex 24)" >> "$E"; echo "   generated"; else echo "   already present"; fi
echo "   fp=$(grep "^TRAFFIC_KEY=" "$E" | cut -d= -f2 | tr -d "\r\n" | sha256sum | cut -c1-12) len=$(grep "^TRAFFIC_KEY=" "$E" | cut -d= -f2 | tr -d "\r\n" | wc -c)"'

echo "== 3. same key into the Pages project (production + preview) via stdin"
for envname in production preview; do
  ssh -o BatchMode=yes "$VPS" 'grep "^TRAFFIC_KEY=" /opt/jarvis/.env | cut -d= -f2 | tr -d "\r\n"' \
    | (cd "$SITE_DIR" && npx wrangler pages secret put TRAFFIC_KEY --project-name rajranpariya --env "$envname" 2>&1 | grep -iE "success|error|✨" || true)
done

echo "== 4. crons"
ssh -o BatchMode=yes "$VPS" 'C=$(crontab -l 2>/dev/null | grep -v "# site-agent" || true)
printf "%s\n" "$C" \
"35 6 * * * /opt/jarvis/venv/bin/python /opt/jarvis/agents/seo-audit.py --daily >> /opt/jarvis/reports/seo-agent.log 2>&1 # site-agent" \
"0 12 * * 1 /opt/jarvis/venv/bin/python /opt/jarvis/agents/seo-audit.py --weekly >> /opt/jarvis/reports/seo-agent.log 2>&1 # site-agent" \
"10 12 * * 1 /opt/jarvis/venv/bin/python /opt/jarvis/agents/traffic-report.py --days 7 >> /opt/jarvis/reports/traffic-agent.log 2>&1 # site-agent" \
| sed "/^$/d" | crontab -
crontab -l | grep -c "# site-agent" | sed "s/^/   crons installed: /"'
echo "done"
