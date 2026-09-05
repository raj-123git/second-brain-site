#!/usr/bin/env python3
"""
scripts/test_publish.py — Phase 6 acceptance: a private fact cannot reach site/ without an
approval row, and an approved row still cannot ship an unverified claim or a leak.

  python scripts/test_publish.py

stdlib unittest. Every test works on TEMP COPIES of the queue, ledger and sections.json,
so the real files are never touched.
"""
from __future__ import annotations

import importlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
publish = importlib.import_module("publish")

LEDGER_MD = """# CLAIMS LEDGER
| # | Claim (public wording) | Evidence | Strength | Status |
|---|---|---|---|---|
| 1 | MS Mechanical Engineering, NYIT, 2018 | facts | Strong | VERIFIED |
| 2 | BE Aeronautical Engineering, 2016 | facts | Strong | VERIFIED |
| 3 | ~6.5 years customer-facing technical work | chronology | Strong | VERIFIED — say "years", never an employer name |
| 5 | A claim withdrawn after the fact | — | — | VERIFIED — WITHDRAWN by Raj 2026-09-06, do not reuse |
| 4 | $3.34M 2025 HVAC sales | dashboard | Strong | WITHDRAWN by Raj 2026-09-05 — was VERIFIED; never on the site |
| 17 | Signature-verified webhooks | evidence matrix | Moderate | VERIFIED-DOC (re-spot-check before publishing) |
| 25 | Forward-Deployed AI Product & Solutions Operator | pack | Raj-stated | RAJ-CONFIRMED as a **descriptor**; NEVER as a held title |
| 26 | income in strong commission years | Raj-stated | Raj-stated | DO-NOT-USE |
| 28 | Pricing of any plan | — | — | NEVER PUBLIC |
| 46 | A work tool, description pending Raj | — | Raj-stated | RAJ-CONFIRMED-PENDING — Raj to correct details |
"""

SECTIONS = {"sections": [
    {"id": "hero", "eyebrow": "x", "title": "x", "ledger_rows": [1, 3, 25], "approved": False, "queue_row": None, "content": ""},
    {"id": "systems", "eyebrow": "x", "title": "x", "ledger_rows": [], "approved": False, "queue_row": None, "content": "",
     "artifacts": [{"id": "evals", "title": "Evals", "ledger_rows": [1], "approved": False, "content": ""}]},
]}

QUEUE_HEAD = """# PUBLIC QUEUE
| # | Target (site section / artifact) | DB candidate id | Claims (ledger rows) | State | Approved by / date | Sanitized |
|---|---|---|---|---|---|---|
"""


def queue(rows: list[str]) -> str:
    return QUEUE_HEAD + "\n".join(rows) + "\n"


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="publish-test-"))
        (self.tmp / "docs").mkdir()
        (self.tmp / "site" / "src" / "data").mkdir(parents=True)
        (self.tmp / "scripts").mkdir()
        shutil.copy(ROOT / "scripts" / "leak-check.sh", self.tmp / "scripts" / "leak-check.sh")
        (self.tmp / "docs" / "CLAIMS_LEDGER.md").write_text(LEDGER_MD, encoding="utf-8")
        (self.tmp / "site" / "src" / "data" / "sections.json").write_text(json.dumps(SECTIONS), encoding="utf-8")
        publish.ROOT = self.tmp
        publish.QUEUE = self.tmp / "docs" / "PUBLIC_QUEUE.md"
        publish.LEDGER = self.tmp / "docs" / "CLAIMS_LEDGER.md"
        publish.SECTIONS = self.tmp / "site" / "src" / "data" / "sections.json"
        publish.LEAK = self.tmp / "scripts" / "leak-check.sh"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_publish(self, rows, dry=False) -> tuple[int, dict, str]:
        publish.QUEUE.write_text(queue(rows), encoding="utf-8")
        sys.argv = ["publish.py"] + (["--dry-run"] if dry else [])
        rc = publish.main()
        return rc, json.loads(publish.SECTIONS.read_text(encoding="utf-8")), publish.QUEUE.read_text(encoding="utf-8")

    def hero(self, sections):
        return next(s for s in sections["sections"] if s["id"] == "hero")

    # --- the one that matters: no approval, no write -------------------------
    def test_unapproved_row_writes_nothing(self):
        rc, s, _ = self.run_publish(["| 1 | hero | 7 | 1, 25 | verified | — | I hold an MS in mechanical engineering. |"])
        self.assertFalse(self.hero(s)["approved"])
        self.assertEqual(self.hero(s)["content"], "")
        self.assertEqual(rc, 0)

    def test_approved_clean_row_is_written_and_flipped(self):
        rc, s, q = self.run_publish(["| 1 | hero | 7 | 1, 25 | APPROVED | raj 2026-09-04 | I hold an MS in mechanical engineering. |"])
        self.assertEqual(rc, 0)
        self.assertTrue(self.hero(s)["approved"])
        self.assertIn("mechanical engineering", self.hero(s)["content"])
        self.assertEqual(self.hero(s)["queue_row"], 1)
        self.assertIn("| published |", q, "queue row must flip so it cannot apply twice")

    def test_approved_but_do_not_use_claim_is_refused(self):
        rc, s, _ = self.run_publish(["| 1 | hero | 7 | 1, 26 | APPROVED | raj | In good years I earned a lot. |"])
        self.assertEqual(rc, 1)
        self.assertFalse(self.hero(s)["approved"])

    def test_approved_but_never_public_claim_is_refused(self):
        rc, s, _ = self.run_publish(["| 1 | hero | 7 | 28 | APPROVED | raj | Our plans are affordable. |"])
        self.assertEqual(rc, 1)
        self.assertFalse(self.hero(s)["approved"])

    def test_approved_with_planted_leak_is_refused(self):
        rc, s, _ = self.run_publish(["| 1 | hero | 7 | 1 | APPROVED | raj | I hold an MS. Plans from $299/mo. |"])
        self.assertEqual(rc, 1)
        self.assertFalse(self.hero(s)["approved"])

    def test_approved_with_employer_name_is_refused(self):
        rc, s, _ = self.run_publish(["| 1 | hero | 7 | 1 | APPROVED | raj | I hold an MS and work at employer-a. |"])
        self.assertEqual(rc, 1)
        self.assertFalse(self.hero(s)["approved"])

    def test_no_cited_claims_is_refused(self):
        rc, s, _ = self.run_publish(["| 1 | hero | 7 |  | APPROVED | raj | A sentence with no evidence. |"])
        self.assertEqual(rc, 1)
        self.assertFalse(self.hero(s)["approved"])

    def test_unknown_target_is_refused(self):
        rc, s, _ = self.run_publish(["| 1 | nowhere | 7 | 1 | APPROVED | raj | Fine text. |"])
        self.assertEqual(rc, 1)

    def test_artifact_target_is_supported(self):
        rc, s, _ = self.run_publish(["| 1 | artifact-evals | 7 | 1 | APPROVED | raj | Evals text. |"])
        self.assertEqual(rc, 0)
        art = next(a for a in s["sections"][1]["artifacts"] if a["id"] == "evals")
        self.assertTrue(art["approved"])

    def test_dry_run_writes_nothing(self):
        rc, s, q = self.run_publish(["| 1 | hero | 7 | 1 | APPROVED | raj | I hold an MS. |"], dry=True)
        self.assertEqual(rc, 0)
        self.assertFalse(self.hero(s)["approved"])
        self.assertIn("| APPROVED |", q)

    def test_a_row_cannot_publish_twice(self):
        self.run_publish(["| 1 | hero | 7 | 1 | APPROVED | raj | First. |"])
        q = publish.QUEUE.read_text(encoding="utf-8")
        self.assertIn("published", q)
        # re-running on the flipped file must be a no-op
        sys.argv = ["publish.py"]
        rc = publish.main()
        self.assertEqual(rc, 0)

    # --- review 2026-09-05: the table parser must never lose a row --------------
    def test_blank_line_inside_table_does_not_hide_later_rows(self):
        rc, s, _ = self.run_publish([
            "| 1 | hero | 7 | 1 | verified | — | Not approved. |",
            "",
            "| 2 | artifact-evals | 7 | 1 | APPROVED | raj | Evals text. |",
        ])
        self.assertEqual(rc, 0)
        art = next(a for a in s["sections"][1]["artifacts"] if a["id"] == "evals")
        self.assertTrue(art["approved"], "a blank line inside the table used to end it silently")

    def test_row_outside_the_table_is_a_loud_failure(self):
        with self.assertRaises(SystemExit):
            self.run_publish([
                "| 1 | hero | 7 | 1 | APPROVED | raj | Fine. |",
                "## a heading ends the table",
                "| 2 | artifact-evals | 7 | 1 | APPROVED | raj | This row would have been ignored. |",
            ])

    # --- review 2026-09-05: statuses ---------------------------------------------
    def test_withdrawn_claim_is_refused_even_if_it_was_verified(self):
        rc, s, _ = self.run_publish(["| 1 | hero | 7 | 1, 4 | APPROVED | raj | I closed a lot of sales in 2025. |"])
        self.assertEqual(rc, 1)
        self.assertFalse(self.hero(s)["approved"])

    def test_raj_confirmed_pending_is_refused(self):
        rc, s, _ = self.run_publish(["| 1 | artifact-evals | 7 | 46 | APPROVED | raj | A tool I built at work. |"])
        self.assertEqual(rc, 1)

    def test_verified_doc_is_accepted(self):
        statuses = publish.ledger_status()
        self.assertEqual(statuses[17], "VERIFIED")
        self.assertEqual(statuses[1], "VERIFIED")
        self.assertEqual(statuses[25], "RAJ-CONFIRMED", "guidance after ';' must not poison the status")
        self.assertNotIn(statuses[4], publish.OK_STATUS)
        self.assertNotIn(statuses[46], publish.OK_STATUS)

    # --- 2026-09-05 second pass: writer guidance in the status cell is not a status word ------
    def test_guidance_after_the_dash_is_not_a_status_word(self):
        statuses = publish.ledger_status()
        self.assertEqual(statuses[3], "VERIFIED", "'never an employer name' is guidance, not a refusal")
        rc, s, _ = self.run_publish(["| 1 | hero | 7 | 1, 3 | APPROVED | raj | Years of customer-facing work. |"])
        self.assertEqual(rc, 0)
        self.assertTrue(self.hero(s)["approved"])

    def test_withdrawn_anywhere_in_the_cell_still_refuses(self):
        statuses = publish.ledger_status()
        self.assertNotIn(statuses[5], publish.OK_STATUS)
        rc, s, _ = self.run_publish(["| 1 | hero | 7 | 1, 5 | APPROVED | raj | A withdrawn claim. |"])
        self.assertEqual(rc, 1)
        self.assertFalse(self.hero(s)["approved"])

    # --- launch flag: the only way noindex comes off ---------------------------------
    def test_launch_row_sets_the_flag_only_when_approved(self):
        rc, s, _ = self.run_publish(["| 1 | launch | — | 1 | verified | | Remove the noindex tag. |"])
        self.assertNotIn("launch", s)
        rc, s, q = self.run_publish(["| 1 | launch | — | 1 | APPROVED | raj | Remove the noindex tag. |"])
        self.assertEqual(rc, 0)
        self.assertTrue(s["launch"]["approved"])
        self.assertIn("| published |", q)

    # --- review 2026-09-05: the slot allow-list is enforced ---------------------
    def test_claim_outside_slot_allow_list_is_refused(self):
        # hero allows [1, 25]; row 2 is VERIFIED but not allowed on the hero
        rc, s, _ = self.run_publish(["| 1 | hero | 7 | 1, 2 | APPROVED | raj | Two degrees. |"])
        self.assertEqual(rc, 1)
        self.assertFalse(self.hero(s)["approved"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
