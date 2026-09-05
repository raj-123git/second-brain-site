#!/usr/bin/env python3
"""
jarvis/agents/traffic-report.py — the weekly traffic agent for rajranpariya.com. Runs ON THE VPS.

  traffic-report.py --days 7        Monday 12:10 UTC: fetch the week's coarse visit records from
                                    /api/traffic (bearer TRAFFIC_KEY from /opt/jarvis/.env),
                                    aggregate, write /opt/jarvis/reports/traffic-<date>.md and
                                    speak the summary through Jarvis (gateway.py --mode full)
  traffic-report.py --days 7 --print   same, never speak

The records carry no IP and no cookie: country, region, city, network name, a user-agent family,
path, status, time (see site/functions/_middleware.js). "People" are distinct (city, region,
country, browser/OS) combinations among human page views, so one person reloading counts once and
two Bay Area visitors on different devices count twice — an honest approximation, stated as such.
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ENV = Path("/opt/jarvis/.env")
REPORTS = Path("/opt/jarvis/reports")
GATEWAY = ["/opt/jarvis/venv/bin/python", "/opt/jarvis/gateway.py"]

METRO = {
    "the Bay Area": {"San Francisco", "San Jose", "Oakland", "Palo Alto", "Mountain View", "Sunnyvale", "Menlo Park",
                     "Redwood City", "Berkeley", "Fremont", "Santa Clara", "Cupertino", "San Mateo", "Daly City", "South San Francisco"},
    "New York City": {"New York", "Brooklyn", "Queens", "Bronx", "Staten Island", "Jersey City", "Hoboken", "Manhattan"},
    "the Hartford area": {"Hartford", "West Hartford", "East Hartford", "South Windsor", "Manchester", "Glastonbury", "Windsor",
                          "Wethersfield", "Newington", "Bloomfield", "<town>", "Enfield", "Vernon", "Farmington", "Rocky Hill"},
    "the Boston area": {"Boston", "Cambridge", "Somerville", "Newton", "Quincy", "Waltham", "Brookline", "Medford"},
    "the Seattle area": {"Seattle", "Bellevue", "Redmond", "Kirkland", "Tacoma"},
    "the Los Angeles area": {"Los Angeles", "Santa Monica", "Pasadena", "Long Beach", "Irvine", "Burbank", "Glendale"},
    "the Austin area": {"Austin", "Round Rock", "Cedar Park"},
    "the Houston area": {"Houston", "Sugar Land", "Katy", "The Woodlands"},
}
AI_NAMES = {
    "gptbot": "OpenAI's GPTBot", "chatgpt-user": "ChatGPT browsing", "oai-searchbot": "OpenAI's search bot",
    "claudebot": "Anthropic's ClaudeBot", "claude-web": "Claude web", "claude-searchbot": "Claude search", "anthropic-ai": "Anthropic",
    "perplexitybot": "Perplexity", "perplexity-user": "Perplexity browsing", "google-extended": "Google's AI crawler",
    "googleother": "Google Other", "ccbot": "Common Crawl", "bytespider": "ByteDance's Bytespider", "amazonbot": "Amazon's bot",
    "applebot-extended": "Apple's AI crawler", "cohere-ai": "Cohere", "meta-externalagent": "Meta's AI crawler",
    "meta-externalfetcher": "Meta fetcher", "diffbot": "Diffbot", "youbot": "You dot com", "duckassistbot": "DuckDuckGo's assistant",
    "petalbot": "Huawei's PetalBot", "ai2bot": "AI2", "mistralai": "Mistral", "deepseekbot": "DeepSeek", "grokbot": "xAI's Grok",
}
SEARCH_NAMES = {"googlebot": "Googlebot", "bingbot": "Bingbot", "duckduckbot": "DuckDuckGo", "yandexbot": "Yandex", "yandex": "Yandex",
                "baiduspider": "Baidu", "applebot": "Applebot", "seznambot": "Seznam", "qwantbot": "Qwant", "archive.org_bot": "the Internet Archive",
                "ia_archiver": "the Internet Archive", "msnbot": "MSN", "adsbot-google": "Google Ads bot", "mediapartners-google": "Google Mediapartners"}


def env() -> dict[str, str]:
    out = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1); out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def where(r: dict) -> str:
    city, region, country = r.get("city", ""), r.get("region", ""), r.get("country", "")
    for metro, cities in METRO.items():
        if city in cities: return metro
    if country == "US":
        return f"{city}, {region}" if city else (region or "the US")
    if country == "IN" and city: return f"{city}, India"
    return f"{city}, {country}" if city else (country or "an unknown place")


def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def main() -> int:
    days = 7
    speak = True
    a = sys.argv[1:]
    if "--days" in a: days = int(a[a.index("--days") + 1])
    if "--print" in a: speak = False
    e = env()
    site = e.get("SITE", "https://rajranpariya.com").rstrip("/")
    key = e.get("TRAFFIC_KEY", "")
    if not key:
        print("TRAFFIC_KEY missing in /opt/jarvis/.env"); return 1
    req = urllib.request.Request(f"{site}/api/traffic?days={days}", headers={"Authorization": f"Bearer {key}", "User-Agent": "rajranpariya-traffic-agent/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
    except urllib.error.HTTPError as ex:
        print(f"traffic endpoint {ex.code}"); return 1
    recs = data.get("records", [])
    end = datetime.now(timezone.utc).date(); start = end - timedelta(days=days - 1)
    span = f"{start.strftime('%B %-d')} to {end.strftime('%B %-d')}"

    humans_home = [r for r in recs if r.get("who") == "human" and r.get("kind") == "view" and r.get("path") in ("/", "/index.html")]
    people = Counter(where(r) for r in {(r.get("city"), r.get("region"), r.get("country"), r.get("name")): r for r in humans_home}.values())
    resume = sum(1 for r in recs if r.get("who") == "human" and r.get("path") == "/Raj_Ranpariya_Resume.pdf" and r.get("status") == 200)
    asks = sum(1 for r in recs if r.get("kind") == "ask")
    ai = Counter(AI_NAMES.get(r.get("name", ""), r.get("name", "an AI crawler")) for r in recs if r.get("who") == "ai")
    search = Counter(SEARCH_NAMES.get(r.get("name", ""), r.get("name", "a search crawler")) for r in recs if r.get("who") == "search")
    bots = sum(1 for r in recs if r.get("who") in ("bot", "unknown"))
    refs = Counter(r.get("ref") for r in humans_home if r.get("ref"))

    parts = [f"Weekly traffic for rajranpariya dot com, {span}."]
    if people:
        n = sum(people.values())
        detail = ", ".join(f"{plural(c, 'person', 'people')} from {w}" for w, c in people.most_common(6))
        parts.append(f"{plural(n, 'person', 'people')} visited: {detail}, across {plural(len(humans_home), 'page view')}.")
    else:
        parts.append("No human visitors this week.")
    if resume: parts.append(f"The résumé was downloaded {plural(resume, 'time')}.")
    if asks: parts.append(f"The assistant answered {plural(asks, 'question')}.")
    if ai:
        parts.append(f"{plural(sum(ai.values()), 'visit')} from {plural(len(ai), 'AI crawler')}: " + ", ".join(f"{k} {plural(v, 'time')}" for k, v in ai.most_common(6)) + ".")
    else:
        parts.append("No AI crawlers came by.")
    if search:
        parts.append("Search engines: " + ", ".join(f"{k} {plural(v, 'visit')}" for k, v in search.most_common(5)) + ".")
    if bots: parts.append(f"{plural(bots, 'other automated hit')}.")
    if refs: parts.append("Referrers: " + ", ".join(f"{k} ({v})" for k, v in refs.most_common(3)) + ".")
    text = " ".join(parts)

    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = end.strftime("%Y-%m-%d")
    md = [f"# Traffic {span} ({days} days, {len(recs)} records)", "", text, "", "| when (UTC) | kind | who | name | where | network | path | status | ref |", "|---|---|---|---|---|---|---|---|---|"]
    md += [f"| {r.get('t','')[:16]} | {r.get('kind')} | {r.get('who')} | {r.get('name','')} | {where(r)} | {r.get('org','')} | {r.get('path')} | {r.get('status')} | {r.get('ref','')} |" for r in recs[-300:]]
    (REPORTS / f"traffic-{stamp}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(text)
    if speak:
        r = subprocess.run(GATEWAY + ["--mode", "full", "--title", "Weekly traffic", "--source", "traffic-agent"],
                           input=text.encode("utf-8"), capture_output=True, timeout=300)
        print("jarvis:", (r.stdout.decode("utf-8", "ignore").strip().splitlines() or ["?"])[-1][:120])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
