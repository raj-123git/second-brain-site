#!/bin/bash
# scripts/render-resume.sh — render site/src/resume/resume.html to site/public/Raj_Ranpariya_Resume.pdf
# with headless Chrome (no header/footer, own throwaway profile so a running Chrome never blocks it).
# Run from the repo root after ANY résumé wording change; `npm run build` then gate-scans the PDF text.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHROME="${CHROME:-/c/Program Files/Google/Chrome/Application/chrome.exe}"
SRC="$ROOT/site/src/resume/resume.html"
OUT="$ROOT/site/public/Raj_Ranpariya_Resume.pdf"
PROFILE="${TEMP:-/tmp}/resume-render-profile"
WIN_OUT="$(cygpath -w "$OUT")"; WIN_SRC="file:///$(cygpath -m "$SRC")"
"$CHROME" --headless=new --disable-gpu --no-pdf-header-footer --run-all-compositor-stages-before-draw \
  --virtual-time-budget=4000 --user-data-dir="$(cygpath -w "$PROFILE")" \
  --print-to-pdf="$WIN_OUT" "$WIN_SRC" >/dev/null 2>&1
ls -la "$OUT" | awk '{print "rendered:", $5, "bytes"}'
python "$ROOT/scripts/pdf-text.py" "$OUT" "$PROFILE.txt" >/dev/null && echo "pages/text ok: $(wc -w < "$PROFILE.txt") words"
