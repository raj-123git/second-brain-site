#!/usr/bin/env python3
"""
jarvis/agents/seo-audit.py — the SEO agent for rajranpariya.com. Runs ON THE VPS, stdlib only.

  seo-audit.py --daily     06:35 UTC: audit the live site; speak to Jarvis only when a check FAILS
                           or the result set changed since the last run
  seo-audit.py --weekly    Monday 12:00 UTC (08:00 ET): audit + full spoken report, always
  seo-audit.py --print     audit and print, never speak

Deterministic checks against the LIVE site, never the repo: reachability and redirects, title /
description / canonical / robots meta, JSON-LD Person, Open Graph, exactly one H1, internal links,
robots.txt and the sitemap, the résumé PDF's noindex header, security headers, a banned-phrase scan
of the live text, the public assistant's health. Search Console is reported as "not connected"
until /opt/jarvis/gsc-sa.json exists (Raj registers the site; the key is his to add).
Reports: /opt/jarvis/reports/seo-<date>.json + .md. Voice: gateway.py --mode full (verbatim).
Launch flag: /opt/jarvis/seo-launched — before it exists, noindex is by design and a missing
sitemap is only a warning; after it, both are failures.
"""
from __future__ import annotations

import html
import json
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

SITE = "https://rajranpariya.com"
HOST = "rajranpariya.com"
REPORTS = Path("/opt/jarvis/reports")
LAUNCHED = Path("/opt/jarvis/seo-launched").exists()
GSC_KEY = Path("/opt/jarvis/gsc-sa.json")
GATEWAY = ["/opt/jarvis/venv/bin/python", "/opt/jarvis/gateway.py"]
UA = "rajranpariya-seo-agent/1.0 (+https://rajranpariya.com; owner check)"
# Phrases that must never appear on the live page (mirror of the build gate's public-facing subset).
BANNED = [
    ("employer", r"employer-a|employer-b|employer-c|employer-d|employer-e"),
    ("wording", r"\bresidential\b|\bin-?home\b|kitchen table|home.?services? sales|real field project management"),
    ("figures", r"\$3\.34\s*M|3\.34 million|428 opportunit|47\s*% close|\$16\.6\s*K"),
    ("pricing", r"\$[0-9][0-9,]*(\.[0-9]+)?\s*(/\s*mo\b|per\s+month|a\s+month|monthly|/\s*yr\b|per\s+year|annually)"),
    ("phone", r"\(?516\)?[ .-]?336[ .-]?7540|\(?413\)?[ .-]?600[ .-]?0113|\(?413\)?[ .-]?288[ .-]?3767"),
    ("address", r"<street>|<town>|<zip>"),
    ("product", r"the platform"),
    ("internal", r"pending approval \(ledger rows|docs/PUBLIC_QUEUE"),
]

CTX = ssl.create_default_context()


def fetch(url: str, method: str = "GET", timeout: int = 20) -> tuple[int, dict, bytes, float, str]:
    """(status, headers(lowercase), body, seconds, final_url). Redirects are NOT followed."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener(NoRedirect, urllib.request.HTTPSHandler(context=CTX))
    req = urllib.request.Request(url, method=method, headers={"User-Agent": UA, "Accept": "*/*"})
    t0 = time.time()
    try:
        with opener.open(req, timeout=timeout) as r:
            body = r.read() if method == "GET" else b""
            return r.status, {k.lower(): v for k, v in r.headers.items()}, body, time.time() - t0, r.geturl()
    except urllib.error.HTTPError as e:
        body = e.read() if method == "GET" else b""
        return e.code, {k.lower(): v for k, v in e.headers.items()}, body, time.time() - t0, url
    except Exception as e:  # DNS, TLS, timeout
        return 0, {"error": str(e)[:120]}, b"", time.time() - t0, url


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""; self.meta: dict[str, str] = {}; self.canonical = ""; self.ld: list[str] = []
        self.h1 = 0; self.hrefs: list[str] = []; self.lang = ""; self.text: list[str] = []
        self._in = None; self._ld = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html": self.lang = a.get("lang", "")
        if tag == "title": self._in = "title"
        if tag == "meta":
            k = a.get("name") or a.get("property")
            if k: self.meta[k.lower()] = a.get("content", "")
        if tag == "link" and (a.get("rel") or "").lower() == "canonical": self.canonical = a.get("href", "")
        if tag == "script":
            if (a.get("type") or "").lower() == "application/ld+json": self._ld = True; self._in = "ld"
            else: self._in = "skip"
        if tag == "style": self._in = "skip"
        if tag == "h1": self.h1 += 1
        if tag == "a" and a.get("href"): self.hrefs.append(a["href"])

    def handle_endtag(self, tag):
        if tag in ("title", "script", "style"): self._in = None; self._ld = False

    def handle_data(self, data):
        if self._in == "title": self.title += data
        elif self._in == "ld": self.ld.append(data)
        elif self._in is None: self.text.append(data)


class Audit:
    def __init__(self):
        self.rows: list[dict] = []

    def add(self, name: str, level: str, detail: str = ""):
        self.rows.append({"name": name, "level": level, "detail": detail[:200]})

    def ok(self, name, cond, detail="", fail="FAIL"):
        self.add(name, "PASS" if cond else fail, detail)

    def run(self) -> dict:
        st, hd, body, secs, _ = fetch(SITE + "/")
        self.ok("home reachable", st == 200, f"status {st} in {secs:.2f}s, {len(body)} bytes")
        self.ok("home fast", secs < 1.5, f"{secs:.2f}s", fail="WARN")
        p = Page()
        if body:
            p.feed(body.decode("utf-8", "ignore"))
        title = html.unescape(p.title).strip()
        self.ok("title present", bool(title), title)
        self.ok("title length", 0 < len(title) <= 65, f"{len(title)} chars", fail="WARN")
        desc = p.meta.get("description", "")
        self.ok("meta description", bool(desc), f"{len(desc)} chars")
        self.ok("description length", 50 <= len(desc) <= 160, f"{len(desc)} chars", fail="WARN")
        self.ok("canonical", p.canonical.rstrip("/") == SITE, p.canonical or "missing")
        robots = p.meta.get("robots", "")
        if "noindex" in robots.lower():
            self.add("robots meta", "FAIL" if LAUNCHED else "INFO", "noindex is ON" + ("" if LAUNCHED else " (by design until launch)"))
        else:
            self.add("robots meta", "PASS", robots or "indexable")
        ld_ok = False
        for s in p.ld:
            try:
                d = json.loads(s)
                items = d if isinstance(d, list) else [d]
                ld_ok = ld_ok or any(isinstance(i, dict) and i.get("@type") == "Person" for i in items)
            except json.JSONDecodeError:
                self.add("json-ld valid", "FAIL", "unparseable ld+json block")
        self.ok("json-ld Person", ld_ok, f"{len(p.ld)} block(s)", fail="WARN" if not LAUNCHED else "FAIL")
        og = [k for k in ("og:title", "og:description", "og:image", "og:url") if p.meta.get(k)]
        self.ok("open graph", len(og) == 4, f"{len(og)}/4 tags", fail="WARN" if not LAUNCHED else "FAIL")
        self.ok("twitter card", bool(p.meta.get("twitter:card")), p.meta.get("twitter:card", "missing"), fail="WARN")
        self.ok("one h1", p.h1 == 1, f"{p.h1} h1")
        self.ok("html lang", bool(p.lang), p.lang or "missing")
        self.ok("viewport", bool(p.meta.get("viewport")), "", fail="WARN")
        text = " ".join(p.text)
        text = re.sub(r"\s+", " ", text)
        hits = [lab for lab, rx in BANNED if re.search(rx, text, re.I)]
        self.ok("banned phrases absent", not hits, f"hit: {hits}" if hits else f"{len(text)} chars scanned")
        # internal links
        internal = []
        for h in p.hrefs:
            if h.startswith("mailto:") or h.startswith("#") or h.startswith("tel:"): continue
            if h.startswith("/"): internal.append(SITE + h)
            elif h.startswith(SITE): internal.append(h)
        broken = []
        for u in sorted(set(internal))[:25]:
            s2, _, _, _, _ = fetch(u.split("#")[0], "HEAD")
            if s2 in (405, 0): s2, _, _, _, _ = fetch(u.split("#")[0], "GET")
            if s2 != 200: broken.append(f"{u} -> {s2}")
        self.ok("internal links", not broken, "; ".join(broken) if broken else f"{len(set(internal))} checked")
        # redirects
        s3, h3, _, _, _ = fetch("http://" + HOST + "/")
        self.ok("http -> https", s3 in (301, 308) and (h3.get("location", "").startswith("https://")), f"{s3} {h3.get('location', '')}")
        s4, h4, _, _, _ = fetch("https://www." + HOST + "/")
        self.ok("www -> apex", s4 in (301, 308) and HOST in h4.get("location", "") and "www." not in h4.get("location", ""), f"{s4} {h4.get('location', '')}")
        # robots + sitemap
        s5, _, b5, _, _ = fetch(SITE + "/robots.txt")
        self.ok("robots.txt", s5 == 200 and b"Sitemap:" in b5, f"status {s5}")
        s6, _, b6, _, _ = fetch(SITE + "/sitemap-index.xml")
        urls = len(re.findall(rb"<loc>", b6)) if s6 == 200 else 0
        self.ok("sitemap", s6 == 200 and urls > 0, f"status {s6}, {urls} loc", fail="FAIL" if LAUNCHED else "WARN")
        # résumé PDF must be noindex
        s7, h7, _, _, _ = fetch(SITE + "/Raj_Ranpariya_Resume.pdf", "HEAD")
        self.ok("resume pdf served", s7 == 200, f"status {s7}", fail="WARN")
        self.ok("resume pdf noindex", "noindex" in h7.get("x-robots-tag", "").lower(), h7.get("x-robots-tag", "missing"))
        # security headers on the home page
        missing = [k for k in ("x-content-type-options", "referrer-policy", "x-frame-options") if k not in hd]
        self.ok("security headers", not missing, f"missing {missing}" if missing else "all present")
        # the public assistant
        s8, _, b8, _, _ = fetch(SITE + "/api/ask")
        self.ok("assistant alive", s8 == 200 and b'"ok":true' in b8.replace(b" ", b""), f"status {s8}", fail="WARN")
        # search console
        self.add("search console", "PASS" if GSC_KEY.exists() else "INFO",
                 "connected" if GSC_KEY.exists() else "not connected: Raj adds rajranpariya.com in Google Search Console + Bing and drops a service-account key at /opt/jarvis/gsc-sa.json")
        return {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "site": SITE, "launched": LAUNCHED,
                "title": title, "rows": self.rows}


def spoken(rep: dict, weekly: bool) -> str:
    rows = rep["rows"]
    n = {lvl: [r for r in rows if r["level"] == lvl] for lvl in ("PASS", "WARN", "FAIL", "INFO")}
    parts = [f"SEO audit for rajranpariya dot com: {len(n['PASS'])} of {len(rows)} checks passed."]
    if n["FAIL"]:
        parts.append("Attention, " + f"{len(n['FAIL'])} failed: " + "; ".join(f"{r['name']}, {r['detail']}" for r in n["FAIL"][:4]) + ".")
    if n["WARN"]:
        parts.append(f"{len(n['WARN'])} warnings: " + "; ".join(r["name"] for r in n["WARN"][:5]) + ".")
    if not rep["launched"]:
        parts.append("The site is still no-index by design until you approve the launch.")
    info = [r for r in n["INFO"] if r["name"] == "search console"]
    if info and "not connected" in info[0]["detail"]:
        parts.append("Search Console is not connected yet; that is a five-minute task on your side.")
    if weekly and not n["FAIL"]:
        parts.append("Nothing needs you for SEO this week.")
    return " ".join(parts)


def previous() -> dict | None:
    files = sorted(REPORTS.glob("seo-*.json"))
    if not files: return None
    try: return json.loads(files[-1].read_text(encoding="utf-8"))
    except Exception: return None


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--print"
    REPORTS.mkdir(parents=True, exist_ok=True)
    prev = previous()
    rep = Audit().run()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (REPORTS / f"seo-{stamp}.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    md = [f"# SEO audit {rep['ts']} — {SITE}", "", "| check | level | detail |", "|---|---|---|"]
    md += [f"| {r['name']} | {r['level']} | {r['detail']} |" for r in rep["rows"]]
    (REPORTS / f"seo-{stamp}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    for r in rep["rows"]:
        print(f"{r['level']:4} {r['name']:22} {r['detail']}")
    fails = [r for r in rep["rows"] if r["level"] == "FAIL"]
    changed = prev is None or {(r["name"], r["level"]) for r in prev.get("rows", [])} != {(r["name"], r["level"]) for r in rep["rows"]}
    speak = mode == "--weekly" or (mode == "--daily" and (fails or changed))
    text = spoken(rep, weekly=(mode == "--weekly"))
    print("---"); print(text)
    if speak:
        r = subprocess.run(GATEWAY + ["--mode", "full", "--title", "SEO audit", "--source", "seo-agent"],
                           input=text.encode("utf-8"), capture_output=True, timeout=300)
        print("jarvis:", (r.stdout.decode("utf-8", "ignore").strip().splitlines() or ["?"])[-1][:120])
    else:
        print("jarvis: silent (no failure, no change)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
