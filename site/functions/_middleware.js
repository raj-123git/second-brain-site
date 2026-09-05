// site/functions/_middleware.js — one coarse record per page view or assistant question into KV
// (TRAFFIC binding) for the weekly traffic briefing. No IP address, no cookie, no fingerprint: the
// country, region, city and network name Cloudflare already attaches to the request, a user-agent
// family, the path, the status and the time. Records expire after 45 days. public/_routes.json limits
// this middleware to "/", "/api/*" and the résumé PDF, so every other asset stays purely static.

const AI = /gptbot|chatgpt-user|oai-searchbot|claudebot|claude-web|claude-searchbot|anthropic-ai|perplexitybot|perplexity-user|google-extended|googleother|ccbot|bytespider|amazonbot|applebot-extended|cohere-ai|meta-externalagent|meta-externalfetcher|diffbot|youbot|duckassistbot|petalbot|ai2bot|omgili|imagesiftbot|timpibot|mistralai|deepseekbot|grokbot|xai-grok|iaskbot|panscient|velenpublicwebcrawler/i;
const SEARCH = /googlebot|bingbot|duckduckbot|yandex(bot)?|baiduspider|applebot|yahoo! slurp|seznambot|qwantbot|sogou|naver|archive\.org_bot|ia_archiver|msnbot|adsbot-google|mediapartners-google/i;
const TOOL = /curl|wget|python-requests|python-urllib|httpx|aiohttp|go-http-client|java\/|okhttp|libwww|scrapy|node-fetch|undici|axios|postman|insomnia|headlesschrome|puppeteer|playwright|lighthouse|pagespeed|gtmetrix|ahrefsbot|semrushbot|mj12bot|dotbot|screaming frog|uptimerobot|pingdom|statuscake|site24x7|facebookexternalhit|twitterbot|linkedinbot|slackbot|telegrambot|whatsapp|discordbot|embedly|pinterestbot|crawler|spider|\bbot\b/i;

function family(ua) {
  const os = /iphone|ipad/i.test(ua) ? "iOS" : /android/i.test(ua) ? "Android" : /windows/i.test(ua) ? "Windows"
    : /mac os/i.test(ua) ? "macOS" : /cros/i.test(ua) ? "ChromeOS" : /linux/i.test(ua) ? "Linux" : "other";
  const br = /edg\//i.test(ua) ? "Edge" : /opr\//i.test(ua) ? "Opera" : /firefox/i.test(ua) ? "Firefox"
    : /chrome/i.test(ua) ? "Chrome" : /safari/i.test(ua) ? "Safari" : "browser";
  return `${br}/${os}`;
}

function classify(ua) {
  if (!ua) return ["unknown", ""];
  let m;
  if ((m = ua.match(AI))) return ["ai", m[0].toLowerCase()];
  if ((m = ua.match(SEARCH))) return ["search", m[0].toLowerCase()];
  if ((m = ua.match(TOOL))) return ["bot", m[0].toLowerCase()];
  if (/mozilla|safari|chrome|firefox|edg\/|opr\//i.test(ua)) return ["human", family(ua)];
  return ["unknown", ""];
}

function refHost(r) {
  try { return r ? new URL(r).host.slice(0, 60) : ""; } catch { return ""; }
}

export async function onRequest(context) {
  const { request, env, next } = context;
  const res = await next();
  try {
    if (!env.TRAFFIC) return res;
    const p = new URL(request.url).pathname;
    const view = request.method === "GET" && (p === "/" || p === "/index.html" || p === "/Raj_Ranpariya_Resume.pdf");
    const ask = request.method === "POST" && p === "/api/ask";
    if (!view && !ask) return res;
    const cf = request.cf || {};
    const ua = request.headers.get("user-agent") || "";
    const [who, name] = classify(ua);
    const t = new Date().toISOString();
    const rec = {
      t, kind: ask ? "ask" : "view", path: p, status: res.status, who, name,
      country: cf.country || "", region: cf.region || "", city: cf.city || "",
      org: String(cf.asOrganization || "").slice(0, 60), ref: refHost(request.headers.get("referer")),
    };
    const key = `v:${t.slice(0, 10)}:${t.slice(11, 19)}:${Math.random().toString(36).slice(2, 8)}`;
    context.waitUntil(env.TRAFFIC.put(key, JSON.stringify(rec), { expirationTtl: 45 * 86400 }));
  } catch {
    // never let bookkeeping break a page
  }
  return res;
}
