#!/usr/bin/env bash
# scripts/leak-check.sh — the last gate before anything public ships.
#
# Runs after `astro build` (wired into site/package.json) and can be run alone:
#   bash scripts/leak-check.sh            # scans site/src and site/dist
#   bash scripts/leak-check.sh --self-test # proves the gate catches planted leaks
#
# Any hit = exit 1 = the build fails. Patterns come from docs/PUBLIC_PROFILE.md
# "Must never appear on the site" and docs/CLAIMS_LEDGER.md rows 24, 28, 29.
# This is deterministic on purpose: a model can be talked out of a rule; grep cannot.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGETS=("$ROOT/site/src" "$ROOT/site/dist" "$ROOT/site/functions")

# Each line: <label>|<extended regex, case-insensitive>
PATTERNS=(
  'employer-name|\bemployer-a\b|\bsila\b|employer-b|employer-b'
  'employer-portfolio|brand-x.example plumbing|central cooling|n\.e\.t\.r|brand-x.example air|brand-x.example'
  'the platform-link|the platform\.cloud|cmd\.the platform|postiz\.the platform'
  'the platform-as-mine|my company the platform|founder of the platform|the platform, my|i founded the platform'
  'pricing|\$[0-9][0-9,]*(\.[0-9]+)?[kKmM]?\s*(/\s*mo\b|per\s+month|a\s+month|each\s+month|monthly|/\s*yr\b|per\s+year|annually|/\s*user|per\s+seat|per\s+user)|\b[0-9]{2,4}\s*/\s*mo\b|\b(front\s*office|full\s*crew|rate\s*card)\b'
  'phone|\(?516\)?[ .-]?336[ .-]?7540|\(?413\)?[ .-]?600[ .-]?0113|\(?413\)?[ .-]?288[ .-]?3767|<phone-2>'
  'personal-email|<old-email>|<handle-1>|rajemployer-a'
  'home-address|<street>|<town>|<zip>'
  'title-overclaim|forward deployed engineer at|\bceo\b|\bfounder\b|co-founder'
  'private-topics|immigration|green card|insurance claim|medical record|\btax return'
  'secrets|api[_-]?key\s*[:=]|sk-ant-|ghp_[A-Za-z0-9]{20,}|BEGIN (RSA|OPENSSH) PRIVATE KEY'
  # Raj, 2026-09-05: the word "residential" and the 2025 sales figures stay off the public site and the public résumé.
  'raj-wording|\bresidential\b|\$3\.34\s*M|3\.34 million|428 opportunit|47\s*% close|\$16\.6\s*K'
  # Raj, 2026-09-05 (second set): he sells to homes AND commercial sites and hates these phrases.
  'raj-wording-2|\bin-?home\b|kitchen table|home.?services? sales|real field project management'
  # Raj, 2026-09-05 (reaffirmed): real employers may be named on the public résumé PDF ONLY — never on a site page.
  'employer-prior|employer-c|employer-d|employer-e'
  # Raj, 2026-09-05: he does not hand-write code — no programming language or coding claim on the site or the résumé.
  'raj-skills|\bpython\b|\bjavascript\b|\btypescript\b|\bprisma\b|hand-typ|wrote (the |most of the )?code|\bprogrammer\b|software (developer|engineer)'
  # A built site must never carry the dev-only review notes (they exist only under `astro dev`).
  'internal-notes|pending approval \(ledger rows|placeholder internal|docs/PUBLIC_QUEUE\.md'
)

scan() {
  local hits=0
  # PDFs (the public résumé) are scanned through their extracted text; a PDF that cannot be read is a hit.
  local pdftmp; pdftmp="$(mktemp -d)"
  for t in "${TARGETS[@]}"; do
    [ -d "$t" ] || continue
    while IFS= read -r pdf; do
      [ -z "$pdf" ] && continue
      if ! python "$ROOT/scripts/pdf-text.py" "$pdf" "$pdftmp/$(basename "$pdf").txt"; then
        echo "LEAK [pdf-unreadable] $pdf"; hits=$((hits+1))
      fi
    done < <(find "$t" -type f -iname '*.pdf' 2>/dev/null)
  done
  TARGETS+=("$pdftmp")
  for t in "${TARGETS[@]}"; do
    [ -d "$t" ] || continue
    for entry in "${PATTERNS[@]}"; do
      label="${entry%%|*}"; rx="${entry#*|}"
      # The résumé (site/src/resume/** and the generated PDF) is the only place employer names may appear.
      # internal-notes guards the BUILT output only: the source template legitimately carries the dev-only wording.
      exempt=''; case "$label" in employer-*) exempt='/resume/|Raj_Ranpariya_Resume\.pdf' ;; internal-notes) exempt='/site/src/' ;; raj-skills) exempt='_middleware\.js' ;; esac   # the bot-UA list names python-requests
      # functions/_lib/blocklist.js is GENERATED from this very pattern list (scripts/build-knowledge.py) so the
      # runtime refuses what the build refuses; it never reaches a browser and is exempt from every label.
      exempt="${exempt:+$exempt|}_lib/blocklist\.js"
      while IFS= read -r line; do
        [ -z "$line" ] && continue
        echo "LEAK [$label] $line"
        hits=$((hits+1))
      done < <(grep -rniE --include='*.astro' --include='*.md' --include='*.mdx' --include='*.html' --include='*.ts' --include='*.tsx' --include='*.js' --include='*.json' --include='*.txt' --include='*.svg' -e "$rx" "$t" 2>/dev/null | { if [ -n "$exempt" ]; then grep -vE "$exempt"; else cat; fi; } | cut -c1-200)
    done
  done
  rm -rf "$pdftmp"
  return $(( hits > 0 ))   # boolean: a plain count wraps at 256 and reads as clean
}

if [ "${1:-}" = "--self-test" ]; then
  tmp="$(mktemp -d)"; TARGETS=("$tmp")
  printf 'Plans from $299/mo. Call <phone-1>. I was Forward Deployed Engineer at X. Contact me at rajranpariya22@gmail.com. employer-b is great.\n' > "$tmp/planted.md"
  if scan >/dev/null; then echo "SELF-TEST FAILED: planted leaks were not detected"; rm -rf "$tmp"; exit 1; fi
  n=$(scan | wc -l); rm -rf "$tmp"
  echo "self-test: $n planted leak(s) detected — gate works"; exit 0
fi

if scan; then
  echo "leak-check: clean (site/src + site/dist)"; exit 0
else
  echo "leak-check: FAILED — fix the lines above; the site does not ship"; exit 1
fi
