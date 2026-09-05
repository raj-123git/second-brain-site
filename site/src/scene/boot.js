import "./scene.css";

if (typeof window !== "undefined" && typeof document !== "undefined") {
  try {
    const key = Symbol.for("measured.scene");
    if (!window[key]) {
      window[key] = true;
      boot();
    }
  } catch {}
}

function boot() {
  let canvas, scene, fallback, fallbackObserver, idle;
  let disposed = false, generation = 0, started = false;
  let currentTier = "", failed = false, pointerId = null, keyboardId = null, selectedId = null;
  const cleanup = [];
  const projectIds = ["sales-tool", "field-app", "backorder", "voice-to-action", "scheduling-workorders",
    "permit-lifecycle", "post-job-followup", "safety-layer", "evals"].map(id => `artifact-${id}`);
  const lifeIds = ["market-monitor", "life-admin", "health-routine"].map(id => `artifact-${id}`);
  const dark = matchMedia("(prefers-color-scheme: dark)");
  const motion = matchMedia("(prefers-reduced-motion: reduce)");
  const narrow = matchMedia("(max-width: 760px)");
  const tokenNames = [
    "bg", "bg-2", "surface", "surface-2", "line", "line-strong",
    "ink", "ink-2", "ink-3", "accent", "accent-strong", "gate",
    "aurora-1", "aurora-2", "aurora-3", "serif", "sans", "mono"
  ];
  function listen(node, type, fn, options) {
    if (!node?.addEventListener) return;
    const guarded = event => { try { fn(event); } catch { showFallback(); } };
    node.addEventListener(type, guarded, options);
    cleanup.push(() => node.removeEventListener(type, guarded, options));
  }
  function readTokens() {
    const style = getComputedStyle(document.documentElement);
    return Object.fromEntries(tokenNames.map(name => [
      `--${name}`, style.getPropertyValue(`--${name}`).trim()
    ]));
  }
  function tier() {
    if (motion.matches) return "static";
    return narrow.matches || navigator.hardwareConcurrency <= 4 || navigator.connection?.saveData
      ? "lite" : "full";
  }
  function activeId() {
    const y = innerHeight * 0.52;
    let id = "top", distance = Infinity;
    for (const section of document.querySelectorAll("main > section")) {
      const r = section.getBoundingClientRect();
      if (!r.height) continue;
      const d = Math.max(r.top - y, y - r.bottom, 0);
      if (d < distance) { distance = d; id = section.id; }
    }
    return id;
  }
  function fallbackState() {
    if (!fallback || document.hidden) return;
    const id = activeId();
    let nearest = null, distance = Infinity;
    for (const card of document.querySelectorAll("#systems article.card[id], #life article.card[id]")) {
      if (card.closest("main > section")?.id !== id) continue;
      const r = card.getBoundingClientRect();
      if (r.bottom <= innerHeight * 0.28 || r.top >= innerHeight * 0.78) continue;
      const d = Math.abs((r.top + r.bottom) / 2 - innerHeight * 0.52);
      const inspection = card.id === "artifact-safety-layer" || card.id === "artifact-evals";
      if (d < distance || (inspection && Math.abs(d - distance) < 1)) { nearest = card.id; distance = d; }
    }
    const selected = selectedId && document.getElementById(selectedId);
    const bounds = selected?.getBoundingClientRect();
    const card = bounds && bounds.bottom > 0 && bounds.top < innerHeight ? selectedId : nearest;
    const inspection = id === "systems" && (card === "artifact-safety-layer" || card === "artifact-evals");
    const state = inspection ? "inspection" : id === "top" ? "hero" : id;
    if (fallback.dataset.sceneState !== state) fallback.dataset.sceneState = state;
    fallback.dataset.sceneCard = card || "";
    fallback.querySelectorAll("[data-card]").forEach(part => {
      part.classList.toggle("ms-selected", part.dataset.card === card);
    });
    const phone = innerWidth < 1000;
    const copy = state === "hero" && phone ? document.querySelector(".hero-copy")?.getBoundingClientRect() : null;
    const hero = copy && document.getElementById("top");
    const reserve = hero ? parseFloat(getComputedStyle(hero, "::after").height) || innerHeight * 0.5 : 0;
    const fit = copy ? reserve * 0.94 : innerHeight * 0.44;
    fallback.style.setProperty("--still-height", `${phone ? fit : innerHeight * 0.7}px`);
    fallback.style.setProperty("--still-y", `${phone ? copy ? copy.bottom + reserve / 2 : innerHeight * 0.74 : innerHeight * 0.53}px`);
  }
  function showFallback() {
    try {
      if (disposed || !canvas) return;
      failed = true;
      generation++;
      scene?.destroy();
      scene = null;
      canvas.hidden = true;
      if (fallback) { fallbackState(); return; }
      fallback = document.createElement("div");
      fallback.className = "measured-still";
      fallback.setAttribute("aria-hidden", "true");
      const components = ids => ids.map((id, i) => {
        const x = 110 + (i % 3) * 150, y = ids.length === 3 ? 192 : 85 + Math.floor(i / 3) * 110;
        return `<g data-card="${id}" transform="translate(${x} ${y})"><path class="ms-component" d="M-44-25 24-42 50-14-18 4Z M-44-25v38l26 29 68-18v-38 M-18 4v38"/><path fill="none" d="M-30-21 22-34 M-8 1v29 M6-3v28 M20-6v27"/></g>`;
      }).join("");
      fallback.innerHTML = `<svg viewBox="35 0 530 440" focusable="false" aria-hidden="true">
        <g class="ms-assembly">
          <g class="ms-base"><path class="ms-metal" d="M82 270 286 166 497 270 290 382Z"/><path class="ms-shade" d="M82 270v24l208 112 207-112v-24L290 382Z M290 382v24"/></g>
          <g class="ms-middle"><path class="ms-metal" d="M133 226 286 148 447 226 289 310Z"/><path class="ms-shade" d="M133 226v22l156 84 158-84v-22L289 310Z M289 310v22"/><path fill="none" d="M171 219l118 63 121-64 M210 199l79 43 81-43"/></g>
          <g class="ms-top"><path class="ms-metal" fill-rule="evenodd" d="M165 170 286 108 413 170 289 236Z M198 170 287 125 381 171 289 218Z"/><path class="ms-shade" d="M165 170v15l124 66 124-66v-15L289 236Z M289 236v15"/></g>
          <g class="ms-dimensions" fill="none"><path d="M70 306 278 418 M61 318l18-25 M267 430l19-26 M314 414l205-111 M304 404l20 21 M509 294l20 21 M70 295v30 M278 404v30 M519 289v30"/></g>
        </g>
        <g class="ms-leaders" fill="none"><path d="M183 166 85 97H30 M289 108V46h105 M404 167l102-73h62 M442 234l83 16h52 M370 330l130 60h60"/><circle cx="183" cy="166" r="4"/><circle cx="289" cy="108" r="4"/><circle cx="404" cy="167" r="4"/><circle cx="442" cy="234" r="4"/><circle cx="370" cy="330" r="4"/></g>
        <g class="ms-system" fill="none"><path d="M110 85H410V305H110V85 M110 195H410 M260 85V305"/>${components(projectIds)}</g>
        <g class="ms-life" fill="none"><path d="M110 192H410 M110 238v50h300v-50"/>${components(lifeIds)}</g>
        <g class="ms-sheets">
          ${[0, 1, 2, 3, 4].map(i => `<g transform="translate(0 ${-i * 38})"><path class="ms-metal" d="M85 265 305 160 515 265 295 382Z"/><path class="ms-shade" d="M85 265v7l210 117 220-117v-7L295 382Z"/><path fill="none" d="M325 294l95-47 40 20-95 48Z"/></g>`).join("")}
          <path fill="none" stroke="var(--accent, #0b5cad)" d="M324 99c-9-14 9-22 17-15 2-14 22-16 28-5 13-10 28 4 22 14 17 2 19 19 7 24 5 16-15 26-23 17-6 14-24 11-27 0-17 7-27-8-19-18-14-1-17-15-5-17Z"/>
        </g>
        <g class="ms-gate" fill="none">
          <path d="M70 354h460 M300 270v118" stroke-dasharray="6 6"/>
          <path fill="var(--gate, #c0392b)" stroke="var(--gate, #c0392b)" d="M292 260h16v106h-16z"/>
          <path fill="var(--accent, #0b5cad)" d="M262 344h20v20h-20z"/>
        </g>
        <g class="ms-panel" fill="none">
          <path d="M80 120h440v230H80z M80 305h440 M264 120v230 M264 246h256 M458 305v45"/>
          <path d="M300 223v-70h36v32h-36l43 38 M390 223v-70h36v32h-36l43 38"/>
        </g>
      </svg>`;
      canvas.after(fallback);
      fallbackState();
      if (typeof IntersectionObserver !== "undefined") {
        fallbackObserver = new IntersectionObserver(fallbackState, {
          threshold: [0, 0.25, 0.75]
        });
        document.querySelectorAll("main > section, article.card[id]")
          .forEach(element => fallbackObserver.observe(element));
      }
    } catch {
      canvas?.remove();
      fallback?.remove();
    }
  }
  async function mount() {
    if (disposed || !canvas || failed) return;
    const ticket = ++generation;
    try {
      const nextTier = tier();
      scene?.destroy();
      scene = null;
      currentTier = nextTier;
      const context = canvas.getContext("webgl2", {
        alpha: true, antialias: nextTier !== "lite", depth: true,
        premultipliedAlpha: true, powerPreference: "low-power"
      });
      if (!context) { showFallback(); return; }
      const module = await import("./scene.js");
      if (disposed || ticket !== generation) return;
      scene = module.mountScene({
        canvas, tier: nextTier, reduced: motion.matches, tokens: readTokens()
      });
      canvas.dataset.sceneReady = "true";
    } catch { if (ticket === generation) showFallback(); }
  }
  function preference() {
    if (disposed || !canvas) return;
    if (failed) { fallbackState(); return; }
    if (currentTier !== tier()) mount();
    else scene?.setState(activeId(), readTokens());
  }
  function bridge(event) {
    if (!(event.target instanceof Element)) return;
    const card = event.target.closest("article.card[id]");
    if (!card) return;
    if (event.relatedTarget instanceof Node && card.contains(event.relatedTarget)) return;
    const leaving = event.type === "pointerout" || event.type === "focusout";
    const next = leaving ? event.relatedTarget instanceof Element ? event.relatedTarget.closest("article.card[id]") : null : card;
    if (event.type.startsWith("pointer")) pointerId = next?.id || null;
    else keyboardId = next?.id || null;
    document.dispatchEvent(new CustomEvent("sceneFocus", { detail: { id: keyboardId || pointerId } }));
  }
  function start() {
    if (started || disposed) return;
    started = true;
    try {
      canvas = document.createElement("canvas");
      canvas.className = "measured-scene";
      canvas.setAttribute("aria-hidden", "true");
      const stars = document.querySelector(".stars-2");
      if (stars) stars.after(canvas); else document.body.prepend(canvas);
      listen(canvas, "sceneUnavailable", showFallback);
      listen(dark, "change", preference);
      listen(motion, "change", preference);
      listen(narrow, "change", preference);
      listen(navigator.connection, "change", preference);
      listen(document, "sceneFocus", event => {
        const value = event.detail?.id;
        const id = typeof value === "string" ? value.replace(/^#?(artifact-)?/, "") : "";
        const fullId = `artifact-${id}`;
        selectedId = [...projectIds, ...lifeIds].includes(fullId) ? fullId : null;
        fallbackState();
      });
      for (const type of ["pointerover", "pointerout", "focusin", "focusout"]) listen(document, type, bridge);
      listen(window, "resize", fallbackState, { passive: true });
      listen(window, "scroll", fallbackState, { passive: true });
      listen(document, "visibilitychange", fallbackState);
      listen(window, "pageshow", fallbackState);
      mount();
    } catch { showFallback(); }
  }
  function schedule() {
    if (disposed) return;
    try {
      if ("requestIdleCallback" in window) idle = requestIdleCallback(start, { timeout: 1500 });
      else idle = setTimeout(start, 0);
    } catch { start(); }
  }
  listen(window, "pagehide", event => {
    if (event.persisted) return;
    disposed = true;
    generation++;
    if ("cancelIdleCallback" in window) cancelIdleCallback(idle);
    clearTimeout(idle);
    scene?.destroy();
    fallbackObserver?.disconnect();
    cleanup.splice(0).forEach(fn => fn());
    canvas?.remove();
    fallback?.remove();
  });
  if (document.readyState === "complete") schedule();
  else listen(window, "load", schedule, { once: true });
}
