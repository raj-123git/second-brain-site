#!/usr/bin/env python3
"""
scripts/build-knowledge.py — what the public /api/ask assistant may know and must refuse.

  python scripts/build-knowledge.py        (runs first inside `npm run build`)

Writes site/functions/_lib/knowledge.js — the APPROVED site text only (sections.json slots with
approved=true, HTML stripped) as one string: the assistant's entire world. Nothing from the private
brain, the ledger, the queue or the résumé is ever included.
Writes site/functions/_lib/blocklist.js — regex sources: PERSONAL (question pre-filter), BUILD
(how-it-was-built / code / repo questions), INJECTION (rule-changing attempts) and LEAK, lifted from
scripts/leak-check.sh so the runtime refuses exactly what the build refuses.
Deterministic, no model, no network.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECTIONS = ROOT / "site" / "src" / "data" / "sections.json"
LEAK = ROOT / "scripts" / "leak-check.sh"
OUT = ROOT / "site" / "functions" / "_lib"

# Personal life: refused before any model sees the question (Raj, 2026-09-05: the site exists for
# professional growth; personal questions get a polite no and the email).
PERSONAL = [
    r"\b(wife|husband|spouse|married|marriage|daughter|son|kids?|children|baby|newborn|family|mother|father|brother|sister|girlfriend|dating)\b",
    r"\b(immigra\w*|visa|green.?card|h-?1b|citizenship|citizen|passport)\b",
    r"\b(salary|salaries|income|earnings?|earn(s|ed)?|compensation|commissions?|net worth|how much (do|does|did) (you|he|raj) (make|earn|get))\b",
    r"\b(your|his|raj'?s) (investments?|portfolio|holdings|returns|trades?|stocks?|crypto|broker|retirement|401k|savings|money|finances?|debt|mortgage|rent)\b",
    r"\b(cholesterol|medical|doctors?|hospital|illness|disease|medications?|diagnos\w*|therapy|mental health|religion|religious|caste|politics|political|vote[sd]?)\b",
    r"\b(phone number|date of birth|birthday|how old|personal life|private life|nationality|ethnicity)\b",
    r"\b(employer|who (do|does) (you|he|raj) work for|which company|current company|clients?|revenue|pricing|prices?|employer-a|employer-b|the platform)\b",
]
# Small talk (Raj, 2026-09-05: "it should at least do hi, hello, casual things; that is not personal").
# Anchored to the WHOLE message, so "hi, where do you live" still reaches the location rule below.
GREET = [
    r"^\s*(hi|hello|hey|hiya|yo|howdy|hi there|hello there|hey there|good (morning|afternoon|evening)|greetings)\b[\s!.,]*(there|raj|jarvis|bot|assistant)?[\s!.,]*(how are you( doing)?|how('s| is) it going|what's up|how do you do|how are things)?[\s!.,?]*$",
    r"^\s*(how are you( doing)?|how('s| is) it going|what's up|how are things|how's your day)[\s!.,?]*$",
    r"^\s*(who are you|what are you|what can you do|what is this|what do you do)[\s!.,?]*$",
]
THANKS = [r"^\s*(thanks|thank you|thx|ty|cheers|appreciate it|great|perfect|awesome|nice|cool)\b[\s!.,]*(a lot|so much|very much|that helps|for the help|raj)?[\s!.,]*$"]
BYE = [r"^\s*(bye|goodbye|see you|see ya|take care|good night|later|ok bye)\b[\s!.,]*$"]
# Location (Raj, 2026-09-05): the only allowed answer is "the Hartford, Connecticut area" — never a
# street, town or zip. Checked BEFORE the personal filter so it gets the canned answer, not a refusal.
LOCATION = [
    r"\b(where (do|does|did) (you|he|raj) (live|stay|reside|work from|operate)|where (is|are) (he|raj|you) (based|located|from)|where is (he|raj) at|based (in|out of)|located in)\b",
    r"\b(home address|street address|address|zip|zip code|postal code|hometown|home town|which (city|town|state|area|region)|what (city|town|state|area|region)|his (city|town|location|neighborhood))\b",
]
# How it was built: what a project does is public; tools, code, prompts, repos and stack are not.
BUILD = [
    r"\b(source.?code|codebase|github|gitlab|bitbucket|repo|repos|repository|repositories|open.?source|code snippets?|snippet)\b",
    r"\b(share|show|send|give|post|paste)( me)?( the| your| his| some)? (code|prompts?|repo|repository|files?|scripts?|config)\b",
    r"\b(system prompt|the prompts?|what prompts?|prompt engineering|tech stack|architecture|infrastructure|which (model|llm|models|framework|library|database|server|cloud|host)|what (model|llm|framework|library|database|server) (do|does|did|is|was))\b",
    r"\b(api keys?|access token|tokens?|password|credentials?)\b",
    r"\b(how (did|do|does) (he|you|raj) (build|make|create|implement|code|train|write|set up|setup|wire|host|deploy)|how (was|is|were|are) (it|this|that|they|these) (built|made|implemented|coded|hosted|deployed|trained)|step.?by.?step|walk me through)\b",
]
# Rule-changing attempts: the visitor's message is a question, never an instruction.
INJECTION = [
    r"\b(ignore|disregard|forget|override|bypass)\b.{0,40}\b(rules?|instructions?|guidelines?|constraints?|restrictions?|system prompt)\b",
    r"\b(you are now|from now on you|pretend (to be|you are)|act as (a|an|if)|role.?play|jailbreak|developer mode|dan mode|no restrictions|without (any )?(rules|restrictions|filters?))\b",
    r"\b(reveal|repeat|print|output|show|display)\b.{0,30}\b(your|the|its) (rules|instructions|prompt|system prompt|hidden text|page text)\b",
]


def strip_html(h: str) -> str:
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)
    t = re.sub(r"</(p|li|h[1-6]|div|tr|section)>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t).strip()


def leak_patterns() -> list[tuple[str, str]]:
    body = LEAK.read_text(encoding="utf-8")
    pats = re.findall(r"^\s*'([a-z\-]+)\|(.+)'\s*$", body, re.M)
    if len(pats) < 8:
        raise SystemExit(f"only {len(pats)} leak patterns parsed from {LEAK} — refusing to build a weak filter")
    return [(l, rx) for l, rx in pats if l != "internal-notes"]   # dev-only wording never reaches an answer


def main() -> int:
    d = json.loads(SECTIONS.read_text(encoding="utf-8"))
    parts: list[str] = []
    email = ""
    for s in d["sections"]:
        if s["id"] == "contact":
            m = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", s.get("content", ""))
            email = m.group(0) if m else ""
        if s["id"] == "ask":
            continue
        if s.get("approved") and s.get("content"):
            title = s["title"] if not str(s["title"]).startswith("{{") else s["eyebrow"]
            head = title if title == s["eyebrow"] else f"{s['eyebrow']}: {title}"
            parts.append(f"## {head}\n{strip_html(s['content'])}")
        for a in s.get("artifacts", []):
            if a.get("approved") and a.get("content"):
                parts.append(f"### Project: {a['title']}\n{strip_html(a['content'])}")
    if not email:
        raise SystemExit("contact slot carries no approved email — the assistant needs one to point to")
    knowledge = "\n\n".join(parts)
    for label, rx in leak_patterns():
        if re.search(rx, knowledge, re.I):
            raise SystemExit(f"approved text trips leak pattern {label!r} — publish.py should have refused it; nothing written")

    OUT.mkdir(parents=True, exist_ok=True)
    header = "// GENERATED by scripts/build-knowledge.py — do not edit; regenerate with `npm run build`.\n"
    (OUT / "knowledge.js").write_text(
        header
        + f"export const EMAIL = {json.dumps(email)};\n"
        + f"export const SLOTS = {len(parts)};\n"
        + f"export const KNOWLEDGE = {json.dumps(knowledge, ensure_ascii=False)};\n",
        encoding="utf-8",
    )

    def arr(name: str, items: list[str]) -> str:
        return f"export const {name} = [\n" + "".join(f"  {json.dumps(x, ensure_ascii=False)},\n" for x in items) + "];\n"

    (OUT / "blocklist.js").write_text(
        header
        + "// Regex SOURCES (compiled case-insensitively by the function). Exempt from the leak gate except `secrets`:\n"
        + "// this file exists to keep these words OUT of answers; it never reaches a browser.\n"
        + arr("GREET", GREET) + arr("THANKS", THANKS) + arr("BYE", BYE)
        + arr("LOCATION", LOCATION) + arr("PERSONAL", PERSONAL) + arr("BUILD", BUILD) + arr("INJECTION", INJECTION)
        + "export const LEAK = [\n" + "".join(f"  [{json.dumps(l)}, {json.dumps(rx, ensure_ascii=False)}],\n" for l, rx in leak_patterns()) + "];\n"
        + "const rx = s => new RegExp(s, \"i\");\n"
        + "export const GREET_RX = GREET.map(rx);\nexport const THANKS_RX = THANKS.map(rx);\nexport const BYE_RX = BYE.map(rx);\n"
        + "export const LOCATION_RX = LOCATION.map(rx);\nexport const PERSONAL_RX = PERSONAL.map(rx);\nexport const BUILD_RX = BUILD.map(rx);\nexport const INJECTION_RX = INJECTION.map(rx);\n"
        + "export const LEAK_RX = LEAK.map(([l, s]) => [l, rx(s)]);\n",
        encoding="utf-8",
    )
    print(f"knowledge.js: {len(parts)} approved slots, {len(knowledge)} chars, email {email}; blocklist.js: "
          f"{len(LOCATION)} location, {len(PERSONAL)} personal, {len(BUILD)} build, {len(INJECTION)} injection, {len(leak_patterns())} leak patterns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
