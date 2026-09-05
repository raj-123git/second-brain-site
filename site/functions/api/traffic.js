// site/functions/api/traffic.js — GET /api/traffic?days=7 returns the coarse visit records the
// middleware stored in KV, for the weekly briefing agent on the VPS. Bearer TRAFFIC_KEY only (a Pages
// secret set with `wrangler pages secret put`); nothing here is public or indexable.

const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", "x-robots-tag": "noindex" },
  });

function same(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export async function onRequestGet({ request, env }) {
  const key = env.TRAFFIC_KEY || "";
  const auth = request.headers.get("authorization") || "";
  if (!key || !same(auth, `Bearer ${key}`)) return json({ error: "forbidden" }, 403);
  if (!env.TRAFFIC) return json({ error: "no store" }, 503);
  const want = parseInt(new URL(request.url).searchParams.get("days") || "7", 10);
  const days = Math.min(31, Math.max(1, Number.isFinite(want) ? want : 7));
  const records = [];
  for (let i = 0; i < days; i++) {
    const day = new Date(Date.now() - i * 86400000).toISOString().slice(0, 10);
    let cursor;
    do {
      const page = await env.TRAFFIC.list({ prefix: `v:${day}:`, cursor, limit: 1000 });
      const vals = await Promise.all(page.keys.map(k => env.TRAFFIC.get(k.name)));
      for (const v of vals) {
        if (!v) continue;
        try { records.push(JSON.parse(v)); } catch { /* skip a bad row */ }
      }
      cursor = page.list_complete ? undefined : page.cursor;
    } while (cursor);
  }
  records.sort((a, b) => (a.t < b.t ? -1 : 1));
  return json({ days, count: records.length, records });
}
