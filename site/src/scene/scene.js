import * as THREE from "three";

export function mountScene({ canvas, tier, reduced, tokens }) {
  const still = reduced || tier === "static";
  const lite = tier === "lite";
  const gl = canvas.getContext("webgl2", {
    alpha: true, antialias: !lite, depth: true,
    premultipliedAlpha: true, powerPreference: "low-power"
  });
  if (!gl) throw new Error("Scene unavailable");
  const cleanups = [], buffers = [], shaders = [];
  let program, dead = false, raf = 0, inside = false;
  let onScreen = true, suspended = false, dirty = true, last = 0;
  let width = 1, height = 1, dpr = 1, sectionId = "top", progress = 0;
  let mode = "", elapsed = 0, duration = 0, heroSeen = false;
  let focusId = null, viewId = null, colors, pose, colorKey = "", redraw = true;
  const sections = [...document.querySelectorAll("main > section")];
  const projectIds = ["sales-tool", "field-app", "backorder", "voice-to-action",
    "scheduling-workorders", "permit-lifecycle", "post-job-followup", "safety-layer", "evals"];
  const lifeIds = ["market-monitor", "life-admin", "health-routine"];
  const modes = ["about", "combination", "skills", "systems", "operator", "how", "life", "os", "hobbies", "contact"];
  const cards = [...document.querySelectorAll("article.card[id^='artifact-']")];
  const validCards = new Set([...projectIds, ...lifeIds].map(id => `artifact-${id}`));
  let activeCard = null, framing = null, manual = false;
  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const ease = v => { v = clamp(v); return v * v * (3 - 2 * v); };
  const mix = (a, b, t) => a + (b - a) * t;
  const listen = (node, type, fn, options) => {
    node.addEventListener(type, fn, options);
    cleanups.push(() => node.removeEventListener(type, fn, options));
  };
  const camera = new THREE.OrthographicCamera(0, 1, 1, 0, 0.1, 2000);
  camera.position.z = 1000;
  const root = new THREE.Matrix4(), model = new THREE.Matrix4();
  const local = new THREE.Matrix4(), projection = new THREE.Matrix4();
  const normal = new THREE.Matrix3(), angles = new THREE.Euler();
  const scale = new THREE.Vector3();
  let uniforms, solid, edges, dimension, boundary, route, panel, callouts, links, lifeLinks, registration, slots;

  function shader(type, source) {
    const result = gl.createShader(type);
    if (!result) throw new Error("Scene unavailable");
    shaders.push(result);
    gl.shaderSource(result, source);
    gl.compileShader(result);
    if (!gl.getShaderParameter(result, gl.COMPILE_STATUS)) {
      throw new Error("Scene unavailable");
    }
    return result;
  }
  function geometry(positions, normals, primitive, endpoints, corners) {
    const vao = gl.createVertexArray();
    if (!vao) throw new Error("Scene unavailable");
    buffers.push(["vao", vao]);
    gl.bindVertexArray(vao);
    for (const [index, data] of [[0, positions], [1, normals], [2, endpoints], [3, corners]]) {
      if (!data) continue;
      const buffer = gl.createBuffer();
      if (!buffer) throw new Error("Scene unavailable");
      buffers.push(["buffer", buffer]);
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
      gl.enableVertexAttribArray(index);
      gl.vertexAttribPointer(index, 3, gl.FLOAT, false, 0, 0);
    }
    return { vao, primitive, count: positions.length / 3, stroke: !!endpoints };
  }
  function lines(segments) {
    const starts = [], ends = [], corners = [];
    segments.forEach(([a, b], index) => {
      for (const [along, side] of [[0, -1], [0, 1], [1, -1], [1, -1], [0, 1], [1, 1]]) {
        starts.push(...a); ends.push(...b); corners.push(along, side, index);
      }
    });
    return geometry(new Float32Array(starts), null, gl.TRIANGLES,
      new Float32Array(ends), new Float32Array(corners));
  }
  function palette() {
    const key = ["--ink", "--bg", "--accent", "--gate"].map(name => tokens[name]).join("|");
    if (key === colorKey && colors) return;
    colorKey = key;
    redraw = true;
    const color = (key, fallback) => new THREE.Color(tokens[key] || fallback);
    const ink = color("--ink", "#17191f");
    const paper = color("--bg", "#f7f5f0");
    colors = {
      ink, paper,
      metal: paper.clone().lerp(ink, paper.r < 0.2 ? 0.32 : 0.43),
      face: paper.clone().lerp(ink, 0.18),
      selected: paper.clone().lerp(color("--accent", "#0b5cad"), 0.38),
      accent: color("--accent", "#0b5cad"),
      gate: color("--gate", "#c0392b")
    };
  }
  function draw(shape, color, opacity, lit = false, fraction = 1, stroke = 1.25) {
    if (opacity <= 0.002 || fraction <= 0) return;
    gl.bindVertexArray(shape.vao);
    gl.uniformMatrix4fv(uniforms.model, false, model.elements);
    normal.getNormalMatrix(model);
    gl.uniformMatrix3fv(uniforms.normal, false, normal.elements);
    gl.uniform3f(uniforms.color, color.r, color.g, color.b);
    gl.uniform1f(uniforms.alpha, opacity);
    gl.uniform1f(uniforms.lit, lit ? 1 : 0);
    gl.uniform1f(uniforms.strokeMode, shape.stroke ? 1 : 0);
    gl.uniform1f(uniforms.strokeWidth, stroke * dpr);
    gl.uniform1f(uniforms.reveal, shape.count / 6 * clamp(fraction));
    const stride = shape.stroke ? 6 : 3;
    const count = Math.ceil(shape.count * clamp(fraction) / stride) * stride;
    gl.drawArrays(shape.primitive, 0, count);
  }
  function transform(x, y, z, sx = 1, sy = 1, sz = 1) {
    local.makeScale(sx, sy, sz).setPosition(x, y, z);
    model.multiplyMatrices(root, local);
  }
  const parts = [
    [0, 0, 0, 0, 3.8, 0.14, 2.2],
    [0, 0, 0.2, -1.03, 3.8, 0.28, 0.14],
    [0, 0, 0.2, 1.03, 3.8, 0.28, 0.14],
    [1, 0, 0.6, 0, 3.1, 0.14, 1.6],
    [1, -1.46, 0.85, 0, 0.18, 0.4, 1.6],
    [1, 1.46, 0.85, 0, 0.18, 0.4, 1.6],
    [2, 0, 1.22, -0.73, 2.5, 0.14, 0.2],
    [2, 0, 1.22, 0.73, 2.5, 0.14, 0.2],
    [2, -1.15, 1.22, 0, 0.2, 0.14, 1.26],
    [2, 1.15, 1.22, 0, 0.2, 0.14, 1.26]
  ];
  for (let i = 0; i < (lite ? 2 : 4); i++) {
    parts.push([1, -0.9 + i * (lite ? 1.8 : 0.6), 0.76, 0, 0.055, 0.18, 1.35]);
  }

  function target() {
    const t = duration ? clamp(elapsed / duration) : 1;
    const hero = mode === "hero", inspection = mode === "inspection";
    const contact = mode === "contact";
    const drift = still ? 0 : Math.sin(t * Math.PI * 2) * Math.sin(t * Math.PI);
    const diagonal = window.innerWidth < 1000 ? 0.5 : mix(-0.16, 0.65, clamp((1.6 - width / height) / 0.5));
    const rotations = {
      hero: [0.76, 0.58, diagonal], about: [0.88, -0.55 - progress * 0.3, diagonal + 0.1],
      combination: [0.72, 0.5, diagonal], skills: [0.8, 0.66, diagonal + 0.1],
      systems: [0.16, -0.08, 0.04], inspection: [0.7, -0.3, diagonal],
      operator: [0.8 + drift * 0.06, 0.66 + drift * 0.12 + progress * 0.2, diagonal],
      how: [0.5, 0.82, diagonal + 0.13], life: [0.25 + drift * 0.05, -0.2 + drift * 0.1, -0.1],
      os: [0.74, 0.54, diagonal + 0.08], hobbies: [0.9, -0.8, diagonal + 0.6],
      contact: [0.1, 0.1, 0]
    };
    const [rx, ry, rz] = rotations[mode] || rotations.about;
    return {
      rx: hero ? mix(0.06, rx, ease((t - 0.42) / 0.5)) : rx,
      ry: hero ? mix(0.03, ry, ease((t - 0.42) / 0.5)) : ry,
      rz,
      spread: mode === "combination" ? 0.9 * (1 - ease((progress - 0.22) / 0.5))
        : mode === "how" ? 0.62 : mode === "hobbies" ? 0.22 : inspection ? 0.24 : 0,
      depth: hero ? mix(0.025, 1, ease((t - 0.45) / 0.5)) : 1,
      reveal: hero ? mix(0.035, 1, ease(t / 0.72)) : 1,
      fill: hero ? ease((t - 0.62) / 0.38) : inspection ? ease((t - 0.82) / 0.18) : 1,
      inspect: inspection ? 1 : 0,
      gate: inspection ? ease((t - 0.1) / 0.1) * (1 - ease((t - 0.7) / 0.08)) : 0,
      travel: inspection ? (t < 0.28 ? mix(-2.45, -0.4, ease(t / 0.28))
        : t < 0.8 ? -0.4 : mix(-0.4, 2.45, ease((t - 0.8) / 0.2))) : -2.45,
      leaders: mode === "skills" ? 1 : mode === "how" ? 0.48 : 0,
      schematic: mode === "systems" || mode === "life" ? 1 : 0,
      life: mode === "life" ? 1 : 0,
      sheets: mode === "os" ? 1 : 0,
      panel: contact ? 1 : 0,
      size: contact ? 0.57 : 1
    };
  }
  function chooseMode() {
    const id = focusId || viewId;
    if (id !== activeCard) { activeCard = id; redraw = true; }
    canvas.dataset.sceneCard = activeCard || "";
    const next = sectionId === "systems" && ["artifact-safety-layer", "artifact-evals"].includes(id)
      ? "inspection" : sectionId === "top" ? "hero" : modes.includes(sectionId) ? sectionId : "about";
    if (next === mode) return;
    mode = next;
    duration = next === "hero" && !heroSeen ? 4000 : next === "inspection" ? 5600
      : ["operator", "life"].includes(next) ? 9000 : 0;
    heroSeen ||= next === "hero";
    elapsed = still ? duration : 0;
    canvas.dataset.sceneState = mode;
  }
  function applyState(id = sectionId, freshTokens = tokens) {
    if (dead) return;
    if (typeof id === "string") {
      const next = id.replace(/^#/, "") === "hero" ? "top" : id.replace(/^#/, "");
      redraw ||= next !== sectionId;
      sectionId = next;
    }
    tokens = freshTokens;
    palette();
    chooseMode();
    request();
  }
  function setState(id = sectionId, freshTokens = tokens) {
    manual = true;
    applyState(id, freshTokens);
  }
  function sample() {
    const middle = height * 0.52;
    let best = null, distance = Infinity;
    for (const element of sections) {
      const r = element.getBoundingClientRect();
      if (!r.height) continue;
      const d = Math.max(r.top - middle, middle - r.bottom, 0);
      if (d < distance) { best = { element, r }; distance = d; }
    }
    viewId = null;
    let closest = Infinity;
    for (const element of cards) {
      if (!validCards.has(element.id) || (best && element.closest("main > section") !== best.element)) continue;
      const r = element.getBoundingClientRect();
      if (r.bottom <= height * 0.28 || r.top >= height * 0.78) continue;
      const d = Math.abs((r.top + r.bottom) / 2 - middle);
      const inspection = ["artifact-safety-layer", "artifact-evals"].includes(element.id);
      if (d < closest || (inspection && Math.abs(d - closest) < 1)) { viewId = element.id; closest = d; }
    }
    if (focusId) {
      const r = document.getElementById(focusId)?.getBoundingClientRect();
      if (!r || r.bottom <= 0 || r.top >= height) focusId = null;
    }
    if (best) {
      progress = still ? 0.65 : clamp((height * 0.8 - best.r.top) / (best.r.height + height * 0.6));
      applyState(manual ? sectionId : best.element.id);
    } else chooseMode();
    dirty = false;
  }
  function objects() {
    const result = [];
    const add = (x, y, z, sx, sy, sz, color, alpha, selected = false) => {
      if (alpha > 0.002) result.push({ x, y, z, sx, sy, sz, color, alpha, selected });
    };
    const small = mix(1, 0.33, pose.panel);
    const body = (1 - pose.schematic) * (1 - pose.sheets);
    for (const [part, px, py, pz, sx, sy, sz] of parts) {
      const offset = (part - 1) * pose.spread;
      add(-1.6 * pose.panel + (px + offset * 0.5) * small,
        (py + part * pose.spread * 0.85) * small, pz * small * pose.depth,
        sx * small, sy * small, sz * small * pose.depth,
        part === 1 ? colors.metal : colors.face, body);
    }
    const selected = (pose.life > 0.5 ? lifeIds : projectIds).indexOf(activeCard?.replace(/^artifact-/, ""));
    for (let i = 0; i < 9; i++) {
      const x = (i % 3 - 1) * 2.1, y = (1 - Math.floor(i / 3)) * 1.55;
      const lifeX = (i - 1) * 1.95, lifeY = i === 1 ? 0.9 : -0.6;
      add(mix(x, lifeX, pose.life), mix(y, lifeY, pose.life), 0,
        1.24, 0.76, 0.27, i === selected ? colors.selected : colors.metal,
        pose.schematic * (i < 3 ? 1 : 1 - pose.life), i === selected);
    }
    for (let i = 0; i < 5; i++) {
      add((i - 2) * 0.09, (i - 2) * 0.5, 0, 3.5, 0.09, 2.25,
        i % 2 ? colors.metal : colors.face, pose.sheets);
    }
    return result;
  }
  function fit(boxes, amount) {
    root.makeRotationFromEuler(angles.set(pose.rx, pose.ry, pose.rz));
    const e = root.elements;
    const bounds = { left: Infinity, right: -Infinity, bottom: Infinity, top: -Infinity };
    const point = (x, y, z) => {
      const px = e[0] * x + e[4] * y + e[8] * z;
      const py = e[1] * x + e[5] * y + e[9] * z;
      bounds.left = Math.min(bounds.left, px); bounds.right = Math.max(bounds.right, px);
      bounds.bottom = Math.min(bounds.bottom, py); bounds.top = Math.max(bounds.top, py);
    };
    if (pose.panel > 0.5) {
      for (const x of [-2.8, 2.8]) for (const y of [-1.4, 1.4]) point(x, y, 1.7);
    } else {
      for (const b of boxes) {
        if (b.alpha < 0.35) continue;
        for (const x of [-0.5, 0.5]) for (const y of [-0.5, 0.5]) for (const z of [-0.5, 0.5]) {
          point(b.x + b.sx * x, b.y + b.sy * y, b.z + b.sz * z);
        }
      }
    }
    const mobile = window.innerWidth < 1000;
    const reserve = Math.min(height * 0.5, 448);
    const copy = mobile && mode === "hero" ? document.querySelector(".hero-copy")?.getBoundingClientRect() : null;
    const cx = mobile ? width * 0.5 : width * 0.755;
    const cy = copy ? copy.bottom + reserve * 0.5 + 16 : height * (mode === "contact" ? 0.75 : 0.56);
    const available = mobile ? width - 40 : width * 0.47 - 24;
    const bh = Math.max(0.1, bounds.top - bounds.bottom), bw = Math.max(0.1, bounds.right - bounds.left);
    const margin = 1 + pose.leaders * 0.19 + pose.inspect * 0.12;
    const unit = Math.min(height * 0.5 * pose.size / bh, available / bw / margin);
    const goal = { unit, x: cx - (bounds.left + bounds.right) * 0.5 * unit,
      y: height - cy - (bounds.top + bounds.bottom) * 0.5 * unit };
    framing ||= { ...goal };
    let moving = false;
    for (const key of Object.keys(goal)) {
      framing[key] = mix(framing[key], goal[key], amount);
      if (Math.abs(framing[key] - goal[key]) < 0.08) framing[key] = goal[key];
      else moving = true;
    }
    root.scale(scale.set(framing.unit, framing.unit, framing.unit)).setPosition(framing.x, framing.y, 0);
    canvas.dataset.sceneBounds = JSON.stringify({
      left: Math.round(bounds.left * framing.unit + framing.x),
      right: Math.round(bounds.right * framing.unit + framing.x),
      top: Math.round(height - bounds.top * framing.unit - framing.y),
      bottom: Math.round(height - bounds.bottom * framing.unit - framing.y)
    });
    return moving;
  }
  function render(amount) {
    const boxes = objects();
    const reframing = fit(boxes, amount);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.useProgram(program);
    gl.uniformMatrix4fv(uniforms.projection, false, projection.elements);
    gl.uniform2f(uniforms.resolution, canvas.width, canvas.height);
    gl.enable(gl.DEPTH_TEST);
    gl.enable(gl.POLYGON_OFFSET_FILL);
    gl.polygonOffset(1, 1);
    for (const b of boxes) {
      transform(b.x, b.y, b.z, b.sx, b.sy, b.sz);
      const alpha = b.alpha * pose.fill;
      gl.depthMask(alpha > 0.98);
      draw(solid, b.color, alpha, true);
    }
    gl.disable(gl.POLYGON_OFFSET_FILL);
    gl.depthMask(false);
    for (const b of boxes) {
      transform(b.x, b.y, b.z, b.sx, b.sy, b.sz);
      draw(edges, b.selected ? colors.accent : colors.ink, b.alpha, false, pose.reveal, b.selected ? 2.5 : 1.25);
      if (b.sz === 0.27) {
        transform(b.x, b.y, b.z + 0.14);
        draw(slots, b.selected ? colors.accent : colors.ink, b.alpha, false, 1, 1.2);
      }
    }
    const assembly = (1 - pose.panel) * (1 - pose.schematic) * (1 - pose.sheets);
    transform(0, -0.3, 0);
    draw(dimension, colors.ink, 0.82 * assembly, false, pose.reveal, 1.1);
    gl.disable(gl.DEPTH_TEST);
    transform(0, 0, 0);
    draw(callouts, colors.ink, pose.leaders, false, pose.leaders, 1.35);
    draw(links, colors.ink, pose.schematic * (1 - pose.life), false, 1, 1.4);
    draw(lifeLinks, colors.ink, pose.schematic * pose.life, false, 1, 1.4);
    transform(0, 1.1, 0);
    draw(registration, colors.accent, pose.sheets, false, 1, 1.5);
    if (pose.spread > 0.01) {
      transform(0, 0.4, 0, 1, pose.spread * 2.4, 1);
      draw(boundary, colors.ink, pose.spread * 0.85);
    }
    transform(0, -0.7, 1.5);
    draw(route, colors.ink, pose.inspect * 0.8, false, 1, 1.5);
    transform(0, -0.25, 1.5);
    draw(boundary, colors.gate, pose.inspect, false, 1, 2);
    transform(0, mix(1.7, -0.25, pose.gate), 1.5, 0.22, 1.5, 0.22);
    draw(solid, colors.gate, pose.inspect, true);
    draw(edges, colors.gate, pose.inspect, false, 1, 2);
    transform(pose.travel, -0.7, 1.5, 0.29, 0.29, 0.29);
    draw(solid, colors.accent, pose.inspect, true);
    draw(edges, colors.ink, pose.inspect);
    transform(0, 0, 1.7);
    draw(panel, colors.ink, pose.panel, false, 1, 1.4);
    gl.depthMask(true);
    gl.bindVertexArray(null);
    return reframing;
  }
  function allowed() {
    return !dead && !document.hidden && !suspended && onScreen;
  }
  function frame(now) {
    raf = 0;
    if (!allowed()) { last = 0; return; }
    inside = true;
    try {
      const dt = last ? Math.min(64, now - last) : 16;
      last = now;
      if (dirty) sample();
      const below = window.innerWidth < 1000 && mode === "hero"
        && (document.querySelector(".hero-copy")?.getBoundingClientRect().bottom || 0) + 16 >= height;
      elapsed = still ? duration : Math.min(duration, elapsed + (below ? 0 : dt));
      const goal = target();
      redraw ||= !pose;
      pose ||= { ...goal };
      let moving = false;
      const amount = still ? 1 : 1 - Math.exp(-dt / 110);
      for (const key of Object.keys(goal)) {
        const previous = pose[key];
        pose[key] = mix(pose[key], goal[key], amount);
        if (Math.abs(pose[key] - goal[key]) < 0.001) pose[key] = goal[key];
        else moving = true;
        redraw ||= previous !== pose[key];
      }
      const reframing = redraw ? render(amount) : false;
      redraw = reframing;
      inside = false;
      if (!still && !below && (moving || reframing || elapsed < duration)) request();
      else last = 0;
    } catch {
      inside = false;
      destroy();
      canvas.dispatchEvent(new Event("sceneUnavailable"));
    }
  }
  function request() {
    if (!allowed() || raf || inside) return;
    if (still) frame(performance.now());
    else raf = requestAnimationFrame(frame);
  }
  function resize() {
    if (dead) return;
    width = Math.max(1, canvas.clientWidth);
    height = Math.max(1, canvas.clientHeight);
    dpr = Math.min(window.devicePixelRatio || 1, lite ? 1.5 : 2);
    framing = null;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    gl.viewport(0, 0, canvas.width, canvas.height);
    camera.right = width;
    camera.top = height;
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();
    projection.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
    redraw = true;
    dirty = true;
    request();
  }
  function pause() {
    cancelAnimationFrame(raf);
    raf = 0;
    last = 0;
  }
  function destroy() {
    if (dead) return;
    dead = true;
    pause();
    for (const cleanup of cleanups.splice(0)) cleanup();
    for (const [kind, value] of buffers.splice(0)) {
      if (kind === "vao") gl.deleteVertexArray(value);
      else gl.deleteBuffer(value);
    }
    if (program) gl.deleteProgram(program);
    for (const value of shaders) gl.deleteShader(value);
  }

  try {
    program = gl.createProgram();
    if (!program) throw new Error("Scene unavailable");
    gl.attachShader(program, shader(gl.VERTEX_SHADER, `#version 300 es
      precision highp float;
      layout(location=0) in vec3 position;
      layout(location=1) in vec3 normal;
      layout(location=2) in vec3 endpoint;
      layout(location=3) in vec3 corner;
      uniform mat4 projection, model;
      uniform mat3 normalMatrix;
      uniform vec2 resolution;
      uniform float strokeMode, strokeWidth, reveal;
      out vec3 n;
      void main() {
        n = normalMatrix * normal;
        vec4 a = projection * model * vec4(position, 1.0);
        gl_Position = a;
        if (strokeMode > 0.5) {
          vec4 b = projection * model * vec4(endpoint, 1.0);
          vec2 d = (b.xy / b.w - a.xy / a.w) * resolution;
          vec2 perpendicular = vec2(-d.y, d.x) / max(length(d), 0.0001);
          vec4 p = mix(a, b, corner.x * clamp(reveal - corner.z, 0.0, 1.0));
          p.xy += perpendicular * corner.y * strokeWidth / resolution * p.w;
          gl_Position = p;
        }
      }`));
    gl.attachShader(program, shader(gl.FRAGMENT_SHADER, `#version 300 es
      precision mediump float;
      uniform vec3 color;
      uniform float alpha, lit;
      in vec3 n;
      out vec4 pixel;
      void main() {
        vec3 direction = n / max(length(n), 0.0001);
        float light = 0.3 + 0.68 * max(dot(direction, normalize(vec3(-0.65, 0.9, 1.2))), 0.0);
        light += 0.12 * max(dot(direction, normalize(vec3(0.8, -0.1, 0.3))), 0.0);
        vec3 c = max(color * mix(1.0, light, lit), vec3(0.0));
        vec3 srgb = mix(12.92 * c, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(vec3(0.0031308), c));
        pixel = vec4(srgb, alpha);
      }`));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error("Scene unavailable");
    uniforms = Object.fromEntries(["projection", "model", "color", "alpha", "lit",
      "resolution", "strokeMode", "strokeWidth", "reveal"].map(
      key => [key, gl.getUniformLocation(program, key)]
    ));
    uniforms.normal = gl.getUniformLocation(program, "normalMatrix");
    const box = new THREE.BoxGeometry(1, 1, 1);
    const expanded = box.toNonIndexed();
    const outline = new THREE.EdgesGeometry(box);
    solid = geometry(expanded.attributes.position.array, expanded.attributes.normal.array, gl.TRIANGLES);
    const edgePoints = outline.attributes.position.array, edgeSegments = [];
    for (let i = 0; i < edgePoints.length; i += 6) {
      edgeSegments.push([Array.from(edgePoints.slice(i, i + 3)), Array.from(edgePoints.slice(i + 3, i + 6))]);
    }
    edges = lines(edgeSegments);
    box.dispose(); expanded.dispose(); outline.dispose();
    const ticks = [
      [[-2.25, 0, -1.4], [2.25, 0, -1.4]],
      [[-2.25, 0, -1.6], [-2.25, 0, 1.4]],
      [[-1.9, 0, -1.65], [-1.9, 0, -1.15]],
      [[1.9, 0, -1.65], [1.9, 0, -1.15]]
    ];
    for (const x of [-1.9, 1.9]) ticks.push([[x - 0.08, 0, -1.48], [x + 0.08, 0, -1.32]]);
    for (const z of [-1.1, 1.1]) ticks.push([[-2.4, 0, z], [-2.1, 0, z]]);
    dimension = lines(ticks);
    boundary = lines([[[0, -0.4, 0], [0, 1.5, 0]], [[-0.17, -0.4, 0], [0.17, -0.4, 0]]]);
    route = lines([[[-2.7, 0, 0], [2.7, 0, 0]]]);
    const fan = [];
    for (const side of [-1, 1]) for (let i = 0; i < 3; i++) {
      const a = [side * 0.8, 0.3 + i * 0.24, (i - 1) * 0.55];
      const b = [side * (1.85 + i * 0.06), 0.9 + i * 0.27, (i - 1) * 0.5];
      const c = [side * (2.35 + i * 0.04), b[1], b[2]];
      fan.push([a, b], [b, c], [[c[0], c[1] - 0.08, c[2]], [c[0], c[1] + 0.08, c[2]]]);
    }
    callouts = lines(fan);
    slots = lines([-0.3, 0, 0.3].map(x => [[x, -0.17, 0], [x, 0.17, 0]]));
    const paths = [];
    for (let row = 0; row < 3; row++) {
      const y = (1 - row) * 1.55;
      for (const x of [-2.1, 0]) paths.push([[x + 0.62, y, 0], [x + 1.48, y, 0]]);
    }
    for (const y of [-1.55, 0]) paths.push([[0, y + 0.38, 0], [0, y + 1.17, 0]]);
    links = lines(paths);
    lifeLinks = lines([
      [[-1.95, -0.22, 0], [-1.95, 0.9, 0]], [[-1.95, 0.9, 0], [-0.62, 0.9, 0]],
      [[0.62, 0.9, 0], [1.95, 0.9, 0]], [[1.95, 0.9, 0], [1.95, -0.22, 0]]
    ]);
    registration = lines([
      [[-1.5, 0, -0.9], [-1.1, 0, -0.9]], [[-1.5, 0, -0.9], [-1.5, 0, -0.5]],
      [[1.5, 0, 0.9], [1.1, 0, 0.9]], [[1.5, 0, 0.9], [1.5, 0, 0.5]]
    ]);
    panel = lines([
      [[-2.8, -1.4, 0], [2.8, -1.4, 0]], [[2.8, -1.4, 0], [2.8, 1.4, 0]],
      [[2.8, 1.4, 0], [-2.8, 1.4, 0]], [[-2.8, 1.4, 0], [-2.8, -1.4, 0]],
      [[-0.5, -1.4, 0], [-0.5, 1.4, 0]], [[-2.8, -0.85, 0], [2.8, -0.85, 0]],
      [[-0.5, -0.25, 0], [2.8, -0.25, 0]], [[1.9, -1.4, 0], [1.9, -0.85, 0]],
      ...[0.2, 1.1].flatMap(x => [
        [[x, 0.05, 0], [x, 1.05, 0]], [[x, 1.05, 0], [x + 0.5, 1.05, 0]],
        [[x + 0.5, 1.05, 0], [x + 0.5, 0.6, 0]], [[x + 0.5, 0.6, 0], [x, 0.6, 0]],
        [[x, 0.6, 0], [x + 0.6, 0.05, 0]]
      ])
    ]);
    gl.clearColor(0, 0, 0, 0);
    gl.enable(gl.BLEND);
    gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.depthFunc(gl.LEQUAL);
    palette();
    listen(document, "sceneFocus", event => {
      const value = event.detail?.id;
      const id = typeof value === "string" ? value.replace(/^#?(artifact-)?/, "") : "";
      focusId = validCards.has(`artifact-${id}`) ? `artifact-${id}` : null;
      dirty = true;
      request();
    });
    const observed = new IntersectionObserver(() => { dirty = true; request(); }, {
      threshold: [0, 0.25, 0.75]
    });
    [...sections, ...cards].forEach(element => observed.observe(element));
    cleanups.push(() => observed.disconnect());
    const visibility = new IntersectionObserver(entries => {
      onScreen = entries[0].isIntersecting;
      if (onScreen) { dirty = true; request(); } else pause();
    });
    visibility.observe(canvas);
    cleanups.push(() => visibility.disconnect());
    listen(window, "scroll", () => { manual = false; dirty = true; request(); }, { passive: true });
    listen(window, "resize", resize, { passive: true });
    if (typeof ResizeObserver !== "undefined") {
      const observer = new ResizeObserver(() => { dirty = true; request(); });
      sections.forEach(element => observer.observe(element));
      cleanups.push(() => observer.disconnect());
    }
    listen(document, "visibilitychange", () => {
      if (document.hidden) pause(); else { dirty = true; request(); }
    });
    listen(window, "pagehide", () => { suspended = true; pause(); });
    listen(window, "pageshow", () => { suspended = false; dirty = true; request(); });
    listen(canvas, "webglcontextlost", event => {
      event.preventDefault();
      destroy();
      canvas.dispatchEvent(new Event("sceneUnavailable"));
    });
    resize();
    if (dead) throw new Error("Scene unavailable");
    return { setState, resize, destroy };
  } catch (error) {
    destroy();
    throw error;
  }
}
