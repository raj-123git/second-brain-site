#!/usr/bin/env python3
"""
scripts/publish.py — the ONLY writer of public content (docs/ARCHITECTURE.md §6, Phase 6).

  python scripts/publish.py            # apply every APPROVED queue row
  python scripts/publish.py --dry-run  # show what would change, write nothing

Reads docs/PUBLIC_QUEUE.md. For each row whose State is APPROVED and not yet published:
  1. every ledger row listed under Claims must exist in docs/CLAIMS_LEDGER.md with status
     VERIFIED or RAJ-CONFIRMED — anything else (SOFTEN, DO-NOT-USE, NEVER PUBLIC, PENDING,
     PRIVATE) refuses the whole row;
  2. the Sanitized text is run through scripts/leak-check.sh's patterns;
  3. only then is it written into site/src/data/sections.json at the Target slot
     (a section id, or artifact-<id>), with approved=true and queue_row set;
  4. the queue row is flipped to `published` in place so it cannot apply twice.

Deterministic, no model, no network. A row that fails any step is reported and skipped;
nothing partial is ever written.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "docs" / "PUBLIC_QUEUE.md"
LEDGER = ROOT / "docs" / "CLAIMS_LEDGER.md"
SECTIONS = ROOT / "site" / "src" / "data" / "sections.json"
LEAK = ROOT / "scripts" / "leak-check.sh"
OK_STATUS = ("VERIFIED", "RAJ-CONFIRMED")
BAD_STATUS_WORDS = ("WITHDRAWN", "NEVER", "DO-NOT-USE", "PRIVATE", "PENDING")


def parse_table(md: str, first_header: str) -> list[dict]:
    """Return rows of the first markdown table whose header starts with `first_header`.

    Blank lines inside the table are skipped (a blank line used to end the table silently,
    which made every later row invisible — found by review 2026-09-05). Any `| N |` row that
    still sits outside the parsed table is a hard error, so no row can ever be ignored."""
    lines = md.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("|") and first_header in line:
            header = [h.strip() for h in line.strip().strip("|").split("|")]
            rows = []
            j = i + 2
            while j < len(lines):
                l = lines[j]
                if not l.strip():
                    j += 1
                    continue
                if not l.strip().startswith("|"):
                    break
                cells = [c.strip() for c in l.strip().strip("|").split("|")]
                if len(cells) < len(header):
                    cells += [""] * (len(header) - len(cells))
                rows.append(dict(zip(header, cells)))
                j += 1
            stray = [m.group(1) for l in lines[j:] for m in [re.match(r"^\|\s*(\d+)\s*\|", l)] if m]
            if stray:
                raise SystemExit(
                    f"table {first_header!r}: rows {stray} sit outside the table "
                    "(a non-blank, non-row line ended it) — fix the file, nothing was written")
            return rows
    return []


def ledger_status() -> dict[int, str]:
    out = {}
    for r in parse_table(LEDGER.read_text(encoding="utf-8"), "| # |"):
        try:
            n = int(r.get("#", "").strip())
        except ValueError:
            continue
        raw = r.get("Status", "").strip().upper()
        # The status proper is what comes before the first dash / semicolon / parenthesis;
        # the rest is guidance for the writer ('never an employer name') and must not be read
        # as a status word — the first publish run refused 13 clean rows that way (2026-09-05).
        # The FIRST token decides, exactly: VERIFIED / VERIFIED-DOC / RAJ-CONFIRMED publish;
        # RAJ-CONFIRMED-PENDING, NEVER PUBLIC, DO-NOT-USE, PRIVATE, PENDING do not.
        # WITHDRAWN anywhere in the cell refuses: nobody writes it as guidance.
        head = re.split(r"\s*(?:[—–;(]|\s-\s)", raw, maxsplit=1)[0].strip() if raw else ""
        first = head.split()[0] if head else ""
        if "WITHDRAWN" in raw or any(w in head for w in BAD_STATUS_WORDS):
            status = raw
        elif first in ("VERIFIED", "VERIFIED-DOC"):
            status = "VERIFIED"
        elif first == "RAJ-CONFIRMED":
            status = "RAJ-CONFIRMED"
        else:
            status = raw
        out[n] = status
    return out


def leak_scan(text: str) -> list[str]:
    """Run leak-check.sh's patterns over the text via a temp dir. Returns hit lines."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "candidate.md"
        p.write_text(text, encoding="utf-8")
        body = LEAK.read_text(encoding="utf-8")
        # reuse the PATTERNS array literally: extract each 'label|regex' entry
        pats = re.findall(r"^\s*'([a-z\-]+)\|(.+)'\s*$", body, re.M)
        hits = []
        for label, rx in pats:
            try:
                if re.search(rx, text, re.I):
                    hits.append(label)
            except re.error:
                hits.append(f"{label} (pattern error)")
        return hits


def claims_from(cell: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", cell)]


def apply_row(row: dict, sections: dict, statuses: dict[int, str], dry: bool) -> tuple[bool, str]:
    target = row.get("Target (site section / artifact)", row.get("Target", "")).strip()
    text = row.get("Sanitized", "").strip()
    rows = claims_from(row.get("Claims (ledger rows)", row.get("Claims", "")))
    n = row.get("#", "?")
    if not target or not text:
        return False, f"row {n}: missing Target or Sanitized text"
    if not rows:
        return False, f"row {n}: no ledger rows cited — unverifiable, refused"
    bad = [r for r in rows if statuses.get(r) not in OK_STATUS]
    if bad:
        return False, f"row {n}: ledger row(s) {bad} are not VERIFIED/RAJ-CONFIRMED ({[statuses.get(b) for b in bad]}) — refused"
    hits = leak_scan(text)
    if hits:
        return False, f"row {n}: leak patterns matched {hits} — refused"

    if target == "launch":   # the only way the noindex tag comes off (docs/SEO_PLAN.md technical item 1)
        if dry:
            return True, f"row {n}: WOULD approve launch (noindex removed at the next build)"
        sections["launch"] = {"approved": True, "queue_row": int(n) if str(n).isdigit() else n,
                              "by": row.get("Approved by / date", "").strip(), "note": text}
        return True, f"row {n}: launch approved — noindex removed at the next build"

    slot = None
    if target.startswith("artifact-"):
        aid = target[len("artifact-"):]
        for s in sections["sections"]:
            for a in s.get("artifacts", []):
                if a["id"] == aid:
                    slot = a
    else:
        for s in sections["sections"]:
            if s["id"] == target:
                slot = s
    if slot is None:
        return False, f"row {n}: unknown target {target!r}"
    # sections.json `ledger_rows` is the allow-list of claims a slot may draw on (review 2026-09-05: enforced, not advisory)
    allowed = slot.get("ledger_rows")
    if allowed is not None:
        outside = [r for r in rows if r not in allowed]
        if outside:
            return False, f"row {n}: cites ledger row(s) {outside} outside {target}'s allow-list {allowed} — refused"
    if dry:
        return True, f"row {n}: WOULD publish {len(text)} chars into {target} (claims {rows})"
    slot["content"] = text
    slot["approved"] = True
    slot["queue_row"] = int(n) if str(n).isdigit() else n
    return True, f"row {n}: published {len(text)} chars into {target} (claims {rows})"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    qmd = QUEUE.read_text(encoding="utf-8")
    rows = parse_table(qmd, "| # |")
    statuses = ledger_status()
    sections = json.loads(SECTIONS.read_text(encoding="utf-8"))
    applied, refused = [], []
    for r in rows:
        state = r.get("State", "").strip().upper()
        if state != "APPROVED":
            continue
        ok, msg = apply_row(r, sections, statuses, a.dry_run)
        (applied if ok else refused).append(msg)
        if ok and not a.dry_run:
            # flip this exact row to published so it can never apply twice
            n = r.get("#")
            qmd = re.sub(rf"^(\|\s*{re.escape(n)}\s*\|(?:[^|]*\|){{3}}\s*)APPROVED(\s*\|)", r"\1published\2", qmd, count=1, flags=re.M)
    if not a.dry_run and applied:
        SECTIONS.write_text(json.dumps(sections, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        QUEUE.write_text(qmd, encoding="utf-8")
    for m in applied:
        print("OK   ", m)
    for m in refused:
        print("REFUSED", m)
    if not applied and not refused:
        print("nothing approved in the queue — nothing written")
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
