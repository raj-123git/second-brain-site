#!/bin/bash
# scripts/render-og.sh — render site/src/og/og.html to site/public/og.png (1200x630) with headless Chrome.
# Run from the repo root after changing the card; Base.astro points og:image at /og.png.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHROME="${CHROME:-/c/Program Files/Google/Chrome/Application/chrome.exe}"
SRC="$ROOT/site/src/og/og.html"; OUT="$ROOT/site/public/og.png"
PROFILE="${TEMP:-/tmp}/og-render-profile"
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --window-size=1200,630 --force-device-scale-factor=1 \
  --user-data-dir="$(cygpath -w "$PROFILE")" --screenshot="$(cygpath -w "$OUT")" "file:///$(cygpath -m "$SRC")" >/dev/null 2>&1
python - "$OUT" <<'PY'
import struct, sys
b = open(sys.argv[1], 'rb').read(32)
w, h = struct.unpack('>II', b[16:24]); print(f"og.png: {w}x{h}, {len(open(sys.argv[1],'rb').read())} bytes")
PY
