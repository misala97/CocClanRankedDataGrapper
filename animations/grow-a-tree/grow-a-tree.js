/* How to Grow a Tree: a 10-second paper-cutout animation.
   Pure JavaScript. Canvas 2D draws every piece of paper, Web Audio plays
   every note and sound effect. No images, no audio files, no libraries. */
(() => {
'use strict';

// ---------------------------------------------------------------- constants
const W = 1280, H = 720;        // logical stage, 16:9
const DURATION = 10;            // seconds
const FPS = 12;                 // stop-motion: every picture is held for two 24fps frames
const TAU = Math.PI * 2;
const GROUND = 520;             // top of the soil, under the grass
const TREE_X = 800;             // where the acorn gets planted
const INK = '#2e2420';
const GRAPHITE = '#3b3431';

const C = {
  paper: '#efe3c8', sky: '#bcdfe4', cloud: '#fbf8ef',
  hill1: '#a7cd78', hill2: '#86bc5f', grass: '#6db357', grassDark: '#3e8744',
  soil: '#9c6a42', subsoil: '#7d5234', soilDark: '#5f3d25',
  sun: '#ffcf3a', ray: '#f59e2a', ray2: '#ffb937',
  teal: '#2c9a93', tealDark: '#1f6f6a', yellow: '#ffd23f', red: '#e4473a',
  pink: '#f4a1b4', blue: '#5ab6e4', bark: '#8b5a35', sprout: '#7fb744', root: '#f1e0bf',
  pencilRed: '#d33f35', leaves: ['#3f8547', '#4e9a45', '#66ae55', '#86c066', '#a3cd6c', '#58a45c'],
};

// ---------------------------------------------------------------- tiny maths
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lerp = (a, b, t) => a + (b - a) * t;
const prog = (t, a, b) => clamp((t - a) / (b - a));
const easeIn = x => x * x;
const easeOut = x => 1 - (1 - x) * (1 - x);
const easeInOut = x => (x < 0.5 ? 2 * x * x : 1 - ((-2 * x + 2) ** 2) / 2);
const backOut = (x, s = 1.9) => (x <= 0 ? 0 : x >= 1 ? 1 : 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2);
const sgn = x => x * 2 - 1;

function rng(seed) { // mulberry32
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function hash(a, b = 0, c = 0) {
  let h = Math.imul(a | 0, 0x27d4eb2d) ^ Math.imul((b | 0) + 0x9e3779b9, 0x165667b1) ^ Math.imul((c | 0) + 0x7f4a7c15, 0x85ebca77);
  h = Math.imul(h ^ (h >>> 15), 0x2c1b3c6d);
  h = Math.imul(h ^ (h >>> 12), 0x297a2d39);
  return ((h ^ (h >>> 15)) >>> 0) / 4294967296;
}
function blend(c1, c2, t) {
  const a = parseInt(c1.slice(1), 16), b = parseInt(c2.slice(1), 16);
  const ch = s => Math.round(lerp((a >> s) & 255, (b >> s) & 255, t));
  return `rgb(${ch(16)},${ch(8)},${ch(0)})`;
}

// ---------------------------------------------------------------- canvas
const stage = document.getElementById('stage');
const ctx = stage.getContext('2d');
let S = 1;                      // device pixels per logical unit
let jitterAmp = 1;              // 0 when the viewer prefers reduced motion

function makeCanvas(w, h) {
  const c = document.createElement('canvas');
  c.width = Math.max(1, Math.ceil(w));
  c.height = Math.max(1, Math.ceil(h));
  return c;
}

// A repeating texture drawn at device resolution but sized in logical units.
function pattern(w, h, draw) {
  const cw = Math.max(2, Math.round(w * S)), ch = Math.max(2, Math.round(h * S));
  const c = makeCanvas(cw, ch), g = c.getContext('2d');
  g.scale(cw / w, ch / h);
  draw(g, w, h);
  const p = ctx.createPattern(c, 'repeat');
  p.setTransform(new DOMMatrix([w / cw, 0, 0, h / ch, 0, 0]));
  return p;
}

// ---------------------------------------------------------------- geometry
function resample(pts, step, closed = true) {
  const out = [], n = pts.length, m = closed ? n : n - 1;
  for (let i = 0; i < m; i++) {
    const [x1, y1] = pts[i], [x2, y2] = pts[(i + 1) % n];
    const k = Math.max(1, Math.round(Math.hypot(x2 - x1, y2 - y1) / step));
    for (let j = 0; j < k; j++) out.push([x1 + (x2 - x1) * j / k, y1 + (y2 - y1) * j / k]);
  }
  if (!closed) out.push(pts[n - 1]);
  return out;
}
function area(pts) {
  let a = 0;
  for (let i = 0; i < pts.length; i++) {
    const p = pts[i], q = pts[(i + 1) % pts.length];
    a += p[0] * q[1] - q[0] * p[1];
  }
  return a / 2;
}
function normals(pts) { // outward unit normals of a closed outline
  const n = pts.length, s = area(pts) >= 0 ? 1 : -1;
  return pts.map((_, i) => {
    const p = pts[(i - 1 + n) % n], q = pts[(i + 1) % n];
    const dx = q[0] - p[0], dy = q[1] - p[1], l = Math.hypot(dx, dy) || 1;
    return [s * dy / l, -s * dx / l];
  });
}
function wander(n, amp, every, r) { // a smooth random loop of n values
  const k = Math.max(3, Math.round(n / every));
  const knots = Array.from({ length: k }, () => sgn(r()) * amp);
  return Array.from({ length: n }, (_, i) => {
    const u = i / n * k, a = Math.floor(u), s = (1 - Math.cos((u - a) * Math.PI)) / 2;
    return lerp(knots[a % k], knots[(a + 1) % k], s);
  });
}
const offset = (pts, nrm, d) => pts.map((p, i) => [p[0] + nrm[i][0] * d[i], p[1] + nrm[i][1] * d[i]]);
const shift = (pts, dx, dy) => pts.map(([x, y]) => [x + dx, y + dy]);
const rot = (pts, a) => { const c = Math.cos(a), s = Math.sin(a); return pts.map(([x, y]) => [x * c - y * s, x * s + y * c]); };
function polar(cx, cy, rx, ry, n, rf = () => 1) {
  return Array.from({ length: n }, (_, i) => {
    const a = i / n * TAU, r = rf(a);
    return [cx + Math.cos(a) * rx * r, cy + Math.sin(a) * ry * r];
  });
}
function bez(p0, c, p1, u) {
  const v = 1 - u;
  return [v * v * p0[0] + 2 * v * u * c[0] + u * u * p1[0], v * v * p0[1] + 2 * v * u * c[1] + u * u * p1[1]];
}

function linePath(pts, closed = true, path = new Path2D()) {
  path.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) path.lineTo(pts[i][0], pts[i][1]);
  if (closed) path.closePath();
  return path;
}
function smoothPath(pts, closed = true, path = new Path2D()) {
  const n = pts.length;
  if (n < 3) return linePath(pts, closed, path);
  const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  if (closed) {
    const m0 = mid(pts[n - 1], pts[0]);
    path.moveTo(m0[0], m0[1]);
    for (let i = 0; i < n; i++) {
      const m = mid(pts[i], pts[(i + 1) % n]);
      path.quadraticCurveTo(pts[i][0], pts[i][1], m[0], m[1]);
    }
    path.closePath();
  } else {
    path.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < n - 1; i++) {
      const m = mid(pts[i], pts[i + 1]);
      path.quadraticCurveTo(pts[i][0], pts[i][1], m[0], m[1]);
    }
    path.lineTo(pts[n - 1][0], pts[n - 1][1]);
  }
  return path;
}

// ---------------------------------------------------------------- paper craft
function shadow(g, k = 1) {
  g.shadowColor = 'rgba(58,36,14,0.33)';
  g.shadowBlur = 5 * S * k;
  g.shadowOffsetX = 2.2 * S * k;
  g.shadowOffsetY = 3.2 * S * k;
}
function layer(g, path, tex = []) {
  for (const [pat, a] of tex) { g.globalAlpha = a; g.fillStyle = pat; g.fill(path); }
  g.globalAlpha = 1;
}

// Torn paper: the coloured face with a pale fibrous rim peeking out below it.
function torn(g, base, fill, o = {}) {
  const r = rng(o.seed ?? 1), n = base.length, nrm = normals(base);
  const low = wander(n, o.wander ?? 1.6, 7, r), jag = o.jag ?? 0.9, rim = o.rim ?? 2.2;
  const face = offset(base, nrm, low.map(v => v + sgn(r()) * jag));
  const edge = offset(base, nrm, low.map(v => v + rim * (0.3 + r()) + sgn(r()) * jag * 1.3));
  const path = linePath(face);
  g.save();
  if (o.shadow !== 0) shadow(g, o.shadow ?? 1);
  g.fillStyle = o.rimColor || '#fffcf2';
  g.fill(linePath(edge));
  g.restore();
  g.fillStyle = fill;
  g.fill(path);
  layer(g, path, o.tex);
  return { path, pts: face };
}

// Scissor cut: a clean edge and a drop shadow.
function cut(g, pts, fill, o = {}) {
  const path = o.sharp ? linePath(pts) : smoothPath(pts);
  g.save();
  if (o.shadow !== 0) shadow(g, o.shadow ?? 1);
  g.fillStyle = fill;
  g.fill(path);
  g.restore();
  layer(g, path, o.tex);
  return path;
}

// Pencil: two slightly different passes over the same line, like a real sketch.
function pencil(g, pts, seed, o = {}) {
  const r = rng(seed), amp = (o.amp ?? 1) * jitterAmp;
  g.save();
  g.strokeStyle = o.color || INK;
  g.lineWidth = o.width ?? 2;
  g.lineCap = g.lineJoin = 'round';
  const passes = o.passes ?? 2;
  for (let k = 0; k < passes; k++) {
    g.globalAlpha = (o.alpha ?? 0.9) * (k ? 0.5 : 1);
    const q = pts.map(([x, y]) => [x + sgn(r()) * amp, y + sgn(r()) * amp]);
    g.stroke(o.sharp ? linePath(q, !!o.closed) : smoothPath(q, !!o.closed));
  }
  g.restore();
}

// A crescent of hatching on the side facing away from the light (top left).
function hatchShade(g, pts, dx, dy, style, alpha = 1) {
  const p = linePath(pts);
  const both = linePath(shift(pts, dx, dy), true, linePath(pts));
  g.save();
  g.clip(p);
  g.clip(both, 'evenodd');
  g.globalAlpha = alpha;
  g.fillStyle = style;
  g.fill(p);
  g.restore();
}

// Crayon scribble inside a shape.
function scribble(g, path, cx, cy, R, o = {}) {
  const r = rng(o.seed ?? 3), gap = o.gap ?? 5;
  g.save();
  g.clip(path);
  g.translate(cx, cy);
  g.rotate(o.angle ?? -0.6);
  g.strokeStyle = o.color || INK;
  g.lineWidth = o.width ?? 1.4;
  g.globalAlpha = o.alpha ?? 0.5;
  g.lineCap = g.lineJoin = 'round';
  g.beginPath();
  g.moveTo(-R, -R);
  for (let y = -R, k = 0; y <= R; y += gap / 2, k++) g.lineTo((k % 2 ? R : -R) + sgn(r()) * 4, y + sgn(r()) * 1.2);
  g.stroke();
  g.restore();
}

// ---------------------------------------------------------------- textures
const P = {};
function buildPatterns() {
  P.grain = pattern(128, 128, (g, w, h) => {
    const r = rng(11);
    for (let i = 0; i < 900; i++) {
      g.fillStyle = `rgba(80,50,20,${0.03 + r() * 0.1})`;
      const s = 0.5 + r() * 1.2;
      g.fillRect(r() * w, r() * h, s, s);
    }
    for (let i = 0; i < 300; i++) {
      g.fillStyle = `rgba(255,255,255,${0.1 + r() * 0.25})`;
      const s = 0.5 + r();
      g.fillRect(r() * w, r() * h, s, s);
    }
    g.lineWidth = 0.5;
    for (let i = 0; i < 12; i++) {
      g.strokeStyle = `rgba(90,60,30,${0.05 + r() * 0.08})`;
      const x = r() * w, y = r() * h, a = r() * TAU, l = 6 + r() * 14;
      g.beginPath();
      g.moveTo(x, y);
      g.quadraticCurveTo(x + Math.cos(a) * l / 2 + sgn(r()) * 3, y + Math.sin(a) * l / 2 + sgn(r()) * 3, x + Math.cos(a) * l, y + Math.sin(a) * l);
      g.stroke();
    }
  });
  const hatch = (color, gap, width, dir = 1) => pattern(gap * 6, gap * 6, (g, w) => {
    g.strokeStyle = color;
    g.lineWidth = width;
    g.beginPath();
    for (let k = -w; k <= 2 * w; k += gap) {
      if (dir > 0) { g.moveTo(k, 0); g.lineTo(k - w, w); } else { g.moveTo(k, 0); g.lineTo(k + w, w); }
    }
    g.stroke();
  });
  const dots = (color, gap, rad) => pattern(gap, gap, g => {
    g.fillStyle = color;
    for (const [x, y] of [[gap / 4, gap / 4], [gap * 3 / 4, gap * 3 / 4]]) { g.beginPath(); g.arc(x, y, rad, 0, TAU); g.fill(); }
  });
  P.hatch = hatch('rgba(46,36,32,0.55)', 5, 1);
  P.hatchX = hatch('rgba(46,36,32,0.45)', 5, 1, -1);
  P.hatchGreen = hatch('rgba(20,70,30,0.5)', 4.5, 1.1);
  P.hatchBlue = hatch('rgba(60,120,160,0.16)', 7, 1.2, -1);
  P.stripes = hatch('rgba(255,255,255,0.22)', 11, 4);
  P.stripesDark = hatch('rgba(20,60,30,0.16)', 12, 4, -1);
  P.dots = dots('rgba(255,255,255,0.26)', 18, 2.4);
  P.dotsDark = dots('rgba(20,60,30,0.18)', 16, 2.2);
  P.grid = pattern(14, 14, (g, w, h) => { g.fillStyle = 'rgba(255,255,255,0.3)'; g.fillRect(0, 0, w, 0.8); g.fillRect(0, 0, 0.8, h); });
  P.news = pattern(150, 104, (g, w, h) => {
    const r = rng(21);
    g.fillStyle = 'rgba(45,40,35,0.55)';
    for (let col = 0; col < 2; col++) {
      for (let y = 3; y < h - 2; y += 5.2) {
        let x = col * 76 + 2;
        const end = col * 76 + 72 - (r() < 0.12 ? r() * 30 : 0);
        while (x < end) { const ww = Math.min(end - x, 4 + r() * 16); g.fillRect(x, y, ww, 2); x += ww + 2.6; }
      }
    }
  });
  P.bark = pattern(34, 60, (g, w, h) => {
    const r = rng(33);
    g.strokeStyle = 'rgba(55,30,12,0.45)';
    g.lineCap = 'round';
    for (let i = 0; i < 4; i++) {
      const x = 4 + i * 8.5 + sgn(r()) * 2;
      g.lineWidth = 0.8 + r() * 1.2;
      g.beginPath();
      g.moveTo(x, -2);
      g.bezierCurveTo(x + sgn(r()) * 3, h * 0.3, x + sgn(r()) * 3, h * 0.7, x, h + 2);
      g.stroke();
    }
  });
  P.fibers = pattern(90, 90, (g, w, h) => {
    const r = rng(44);
    g.lineWidth = 0.7;
    for (let i = 0; i < 40; i++) {
      g.strokeStyle = r() < 0.5 ? 'rgba(255,235,200,0.22)' : 'rgba(60,35,15,0.18)';
      const x = r() * w, y = r() * h, a = r() * TAU, l = 4 + r() * 10;
      g.beginPath();
      g.moveTo(x, y);
      g.lineTo(x + Math.cos(a) * l, y + Math.sin(a) * l);
      g.stroke();
    }
  });
}

// ---------------------------------------------------------------- sprites
const HAND = s => `700 ${s}px Caveat, "Segoe Print", "Bradley Hand", "Comic Sans MS", cursive`;
const MARKER = s => `${s}px "Permanent Marker", "Arial Black", Impact, sans-serif`;

// A piece pre-drawn once into its own canvas; (x0,y0)-(x1,y1) are its local bounds.
function sprite(x0, y0, x1, y1, draw, pad = 14) {
  const x = x0 - pad, y = y0 - pad;
  const cw = Math.ceil((x1 - x0 + pad * 2) * S), ch = Math.ceil((y1 - y0 + pad * 2) * S);
  const c = makeCanvas(cw, ch), g = c.getContext('2d');
  g.setTransform(S, 0, 0, S, -x * S, -y * S);
  draw(g);
  return { c, x, y, w: cw / S, h: ch / S };
}
function blit(spr, x, y, o = {}) {
  ctx.save();
  ctx.translate(x, y);
  if (o.rot) ctx.rotate(o.rot);
  if (o.sx !== undefined) ctx.scale(o.sx, o.sy ?? o.sx);
  if (o.alpha !== undefined) ctx.globalAlpha = o.alpha;
  if (o.shadow) shadow(ctx, o.shadow);
  if (o.crop !== undefined) {
    const k = clamp(o.crop);
    if (k > 0) ctx.drawImage(spr.c, 0, 0, spr.c.width * k, spr.c.height, spr.x, spr.y, spr.w * k, spr.h);
  } else ctx.drawImage(spr.c, spr.x, spr.y, spr.w, spr.h);
  ctx.restore();
}
// Stop-motion life: each frame the animator nudges every piece a hair.
function nudge(id, f, amp = 0.6) {
  const k = jitterAmp * amp;
  return { dx: sgn(hash(id, f, 1)) * k, dy: sgn(hash(id, f, 2)) * k, dr: sgn(hash(id, f, 3)) * 0.005 * k };
}
const pick = (arr, id, f) => arr[jitterAmp ? (f + id) % arr.length : 0];
const angDiff = (a, b) => ((((a - b) % TAU) + TAU + Math.PI) % TAU) - Math.PI;

// ---- the page, sky, hills and soil: glued down, so they never move
function paintBackground(g) {
  const r = rng(5);
  g.fillStyle = C.paper;
  g.fillRect(0, 0, W, H);
  for (let i = 0; i < 16; i++) {
    const x = r() * W, y = r() * H, rad = 80 + r() * 240, dark = r() < 0.5;
    const gr = g.createRadialGradient(x, y, 0, x, y, rad);
    gr.addColorStop(0, dark ? 'rgba(150,110,60,0.08)' : 'rgba(255,255,255,0.2)');
    gr.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = gr;
    g.fillRect(x - rad, y - rad, rad * 2, rad * 2);
  }
  g.fillStyle = P.grain;
  g.fillRect(0, 0, W, H);
  g.globalAlpha = 0.6;
  g.fillStyle = P.fibers;
  g.fillRect(0, 0, W, H);
  g.globalAlpha = 1;

  const sky = torn(g, resample([[30, 26], [W - 34, 22], [W - 26, 590], [24, 594]], 7), C.sky,
    { seed: 31, wander: 2.4, shadow: 0.8, tex: [[P.grain, 1], [P.hatchBlue, 1]] });
  g.save();
  g.clip(sky.path);
  for (let i = 0; i < 10; i++) {
    const x = 60 + r() * (W - 120), y = 40 + r() * 420, rad = 60 + r() * 160;
    const gr = g.createRadialGradient(x, y, 0, x, y, rad);
    gr.addColorStop(0, r() < 0.5 ? 'rgba(255,255,255,0.22)' : 'rgba(120,180,200,0.12)');
    gr.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = gr;
    g.fillRect(x - rad, y - rad, rad * 2, rad * 2);
  }
  g.restore();

  const hill = (x0, x1, base, peak, pw) => {
    const pts = [];
    for (let x = x0; x <= x1; x += 6) pts.push([x, base - peak * Math.pow(Math.sin(Math.PI * (x - x0) / (x1 - x0)), pw)]);
    pts.push([x1, 640], [x0, 640]);
    return resample(pts, 6);
  };
  torn(g, hill(30, 910, 548, 110, 0.8), C.hill1, { seed: 41, tex: [[P.stripes, 1], [P.grain, 1]] });
  torn(g, hill(560, 1250, 548, 86, 0.9), C.hill2, { seed: 42, tex: [[P.dots, 1], [P.grain, 1]] });

  // soil in cross-section: a dark sheet, with a lighter layer of topsoil torn over it
  const sheet = torn(g, resample([[20, 505], [W - 20, 502], [W - 16, 708], [22, 705]], 7), C.subsoil,
    { seed: 51, tex: [[P.grain, 1], [P.fibers, 1], [P.hatch, 0.1]] });
  const top = [[22, 503]];
  for (let x = 22; x <= W - 18; x += 6) top.push([x, 640 + 9 * Math.sin(x * 0.011) + 4 * Math.sin(x * 0.037)]);
  top.push([W - 18, 500]);
  torn(g, resample(top, 6), C.soil, { seed: 52, rimColor: '#d8b489', rim: 2.6, shadow: 0.6, tex: [[P.grain, 1], [P.fibers, 1], [P.grain, 0.6]] });

  g.save();
  g.clip(sheet.path);
  const pr = rng(61);
  const stones = ['#c9b59b', '#a8957e', '#8d7b67', '#d8c6a8'];
  for (let i = 0; i < 34; i++) {
    const x = 40 + pr() * (W - 80), y = 552 + pr() * 140;
    const rx = 4 + pr() * 7, ry = 3 + pr() * 4.5, a = pr() * TAU;
    if (Math.abs(x - TREE_X) < 150 || (x > 900 && x < 1060 && y > 610)) continue;
    const pts = shift(rot(polar(0, 0, rx, ry, 14, t => 1 + 0.08 * Math.sin(t * 3 + i)), a), x, y);
    cut(g, pts, stones[i % 4], { shadow: 0.5, tex: [[P.grain, 1]] });
    pencil(g, pts, 900 + i, { closed: true, width: 1.1, alpha: 0.6, passes: 1 });
  }
  for (let i = 0; i < 90; i++) {
    g.fillStyle = `rgba(40,24,10,${0.2 + pr() * 0.3})`;
    g.beginPath();
    g.ellipse(30 + pr() * (W - 60), 545 + pr() * 155, 0.8 + pr() * 1.4, 0.6 + pr(), pr() * 3, 0, TAU);
    g.fill();
  }
  g.restore();
}

// ---- grass: zigzag-cut green paper with a few daisies
function paintGrass(g) {
  const r = rng(71), pts = [];
  for (let x = 16; x < W - 16;) {
    const w = 8 + r() * 7;
    pts.push([x, 506 + sgn(r()) * 2], [x + w / 2, 493 - r() * (r() < 0.15 ? 14 : 7)]);
    x += w;
  }
  pts.push([W - 16, 506]);
  for (let x = W - 16; x >= 16; x -= 7) pts.push([x, 537 + sgn(r()) * 1.4]);
  cut(g, pts, C.grass, { sharp: true, tex: [[P.grain, 1], [P.hatchGreen, 0.22]] });
  for (let i = 0; i < 70; i++) {
    const x = 24 + r() * (W - 48);
    pencil(g, [[x, 532], [x + sgn(r()) * 2, 518], [x + sgn(r()) * 4, 505 - r() * 6]], 1000 + i,
      { color: C.grassDark, width: 1.4, alpha: 0.55, passes: 1, amp: 0.5 });
  }
  for (const [fx, fy, s] of [[112, 497, 1], [412, 500, 0.8], [1016, 496, 0.9], [1206, 499, 1.1]]) {
    pencil(g, [[fx, fy + 32], [fx + 2, fy + 16], [fx, fy]], fx, { color: C.grassDark, width: 2.2, passes: 1 });
    for (let k = 0; k < 7; k++) {
      const pts2 = shift(rot(polar(7.5 * s, 0, 7 * s, 3.3 * s, 12), k / 7 * TAU + fx), fx, fy);
      cut(g, pts2, '#fffdf6', { shadow: 0.35 });
      pencil(g, pts2, fx + k, { closed: true, width: 0.9, alpha: 0.5, passes: 1, amp: 0.3 });
    }
    const c = polar(fx, fy, 4.2 * s, 4.2 * s, 10);
    cut(g, c, C.yellow, { shadow: 0.3, tex: [[P.hatch, 0.3]] });
    pencil(g, c, fx + 50, { closed: true, width: 1, alpha: 0.7, passes: 1, amp: 0.3 });
  }
}

// ---- clouds: torn from a newspaper page
function paintCloud(g, rx, ry, seed) {
  const r = rng(seed), ph = r() * TAU;
  const pts = polar(0, 0, rx, ry, 64, a => 0.8 + 0.22 * Math.abs(Math.sin(a * 2.5 + ph))).map(([x, y]) => [x, Math.min(y, ry * 0.42)]);
  const t = torn(g, resample(pts, 5), C.cloud, { seed, rim: 1.4, jag: 0.6, tex: [[P.news, 0.3], [P.grain, 1]] });
  hatchShade(g, t.pts, -7, -9, P.hatchBlue, 1);
  hatchShade(g, t.pts, -7, -9, P.hatchBlue, 1);
}

// ---- the sun: a ring of cut rays that spins, and a torn yellow face
function paintRays(g) {
  for (let i = 0; i < 12; i++) {
    const a = i / 12 * TAU, len = i % 2 ? 80 : 95, w = 0.17;
    const pts = [[Math.cos(a - w) * 48, Math.sin(a - w) * 48], [Math.cos(a) * len, Math.sin(a) * len], [Math.cos(a + w) * 48, Math.sin(a + w) * 48]];
    cut(g, pts, i % 2 ? C.ray2 : C.ray, { sharp: true, shadow: 0, tex: [[P.grain, 1]] });
    pencil(g, pts, 80 + i, { sharp: true, width: 1.5, alpha: 0.55, passes: 1 });
  }
}
function paintSunBody(g, v) {
  const t = torn(g, polar(0, 0, 54, 54, 44, a => 1 + 0.015 * Math.sin(a * 5)), C.sun, { seed: 90, rim: 1.8, tex: [[P.grain, 1]] });
  g.save();
  g.clip(t.path);
  const sp = [];
  for (let k = 0; k < 92; k++) sp.push([Math.cos(k * 0.28) * (4 + k * 0.52), Math.sin(k * 0.28) * (4 + k * 0.52)]);
  pencil(g, sp, 91 + v, { color: '#f0961c', width: 2.4, alpha: 0.4, passes: 1, amp: 0.8 });
  g.restore();
  hatchShade(g, t.pts, -8, -8, P.hatch, 0.22);
}

// ---- the acorn
function acornShape() {
  const pts = [];
  for (let i = 0; i < 40; i++) {
    const th = i / 40 * TAU, up = Math.cos(th) > 0;
    pts.push([17 * Math.sin(th) * (up ? 1 : 1 - 0.22 * Math.cos(th) ** 2), up ? -14 * Math.cos(th) : -27 * Math.cos(th)]);
  }
  return pts;
}
function paintAcorn(g, v) {
  const nut = acornShape();
  cut(g, nut, '#d49a56', { tex: [[P.grain, 1]] });
  hatchShade(g, nut, -6, -4, P.hatch, 0.45);
  pencil(g, [[-11, -2], [-12, 6], [-8, 14]], 200 + v, { color: '#fff3d6', width: 3, alpha: 0.75, passes: 1 });
  pencil(g, nut, 210 + v, { closed: true, width: 1.8 });
  pencil(g, [[0, 25], [0.5, 31]], 220 + v, { width: 2.5 });
  const cap = [];
  for (let i = 0; i <= 16; i++) { const a = Math.PI + i / 16 * Math.PI; cap.push([Math.cos(a) * 21, -7 + Math.sin(a) * 19]); }
  for (let i = 1; i < 12; i++) { const u = i / 12; cap.push([21 - 42 * u, -7 + 5 * Math.sin(Math.PI * u)]); }
  cut(g, cap, '#8a5a35', { tex: [[P.grain, 1], [P.hatch, 0.55], [P.hatchX, 0.55]] });
  pencil(g, cap, 230 + v, { closed: true, width: 1.8 });
  pencil(g, [[0, -25], [2, -30], [6, -34]], 240 + v, { width: 4, color: '#5e3b22', passes: 1 });
}

// ---- a little mound of fresh soil over the planted acorn
function paintMound(g, v) {
  const arc = [];
  for (let i = 0; i <= 20; i++) { const a = Math.PI + i / 20 * Math.PI; arc.push([Math.cos(a) * 42, Math.sin(a) * 17 + 2]); }
  const pts = resample(arc.concat([[40, 7], [0, 9], [-40, 7]]), 5);
  const p = cut(g, pts, C.soilDark, { tex: [[P.grain, 1], [P.fibers, 1]] });
  scribble(g, p, 0, -4, 44, { seed: 300 + v, color: '#3a2413', alpha: 0.35, gap: 5, angle: -0.4 });
  pencil(g, arc, 310 + v, { width: 1.8 });
  const r = rng(320);
  for (let i = 0; i < 7; i++) {
    const c = polar(sgn(r()) * 46, 4 + r() * 5, 2 + r() * 2, 1.5 + r() * 1.5, 7);
    cut(g, c, C.soilDark, { shadow: 0.4 });
  }
}

// ---- the watering can, spout to the left
const CAN_TIP = [-161, -72];     // where the water leaves the rose, in can space
const CAN_DIR = [-100, -86];     // direction of the spout, in can space
function paintCan(g, v) {
  const handle = [[8, -50], [30, -104], [78, -92], [86, -30], [62, 2]];
  g.save();
  g.lineCap = g.lineJoin = 'round';
  shadow(g);
  g.strokeStyle = INK;
  g.lineWidth = 15;
  g.stroke(smoothPath(handle, false));
  g.restore();
  g.save();
  g.lineCap = g.lineJoin = 'round';
  g.strokeStyle = C.teal;
  g.lineWidth = 10.5;
  g.stroke(smoothPath(handle, false));
  g.restore();

  const base = [-50, 24], tip = [-150, -62], L = Math.hypot(CAN_DIR[0], CAN_DIR[1]);
  const n = [-CAN_DIR[1] / L, CAN_DIR[0] / L];
  const spout = [[base[0] + n[0] * 11, base[1] + n[1] * 11], [tip[0] + n[0] * 5, tip[1] + n[1] * 5],
    [tip[0] - n[0] * 5, tip[1] - n[1] * 5], [base[0] - n[0] * 11, base[1] - n[1] * 11]];
  cut(g, spout, C.teal, { sharp: true, tex: [[P.grain, 1]] });
  pencil(g, spout, 400 + v, { closed: true, sharp: true, width: 1.8 });
  const rose = shift(rot([[0, -6], [12, -13], [15, 0], [12, 13], [0, 6]], Math.atan2(CAN_DIR[1], CAN_DIR[0])), tip[0], tip[1]);
  cut(g, rose, C.yellow, { sharp: true, tex: [[P.grain, 1], [P.hatch, 0.25]] });
  pencil(g, rose, 410 + v, { closed: true, sharp: true, width: 1.6 });

  const body = resample([[-56, -50], [56, -50], [63, 50], [-63, 50]], 10);
  const bp = cut(g, body, C.teal, { tex: [[P.grain, 1], [P.dots, 1]] });
  g.save();
  g.clip(bp);
  g.fillStyle = C.yellow;
  g.fillRect(-80, 2, 160, 24);
  layer(g, new Path2D('M-80 2h160v24h-160z'), [[P.grain, 1]]);
  g.restore();
  pencil(g, [[-60, 2], [0, 3], [60, 2]], 420 + v, { width: 1.4, alpha: 0.7, passes: 1 });
  pencil(g, [[-61, 26], [0, 27], [61, 26]], 421 + v, { width: 1.4, alpha: 0.7, passes: 1 });
  g.font = HAND(24);
  g.fillStyle = C.red;
  g.textAlign = 'center';
  g.fillText('H₂O', 0, 22);
  hatchShade(g, body, -12, 0, P.hatch, 0.3);
  pencil(g, body, 430 + v, { closed: true, width: 1.8 });
  const rim = polar(0, -50, 57, 9, 24);
  cut(g, rim, C.tealDark, { shadow: 0, tex: [[P.grain, 1]] });
  cut(g, polar(0, -50, 45, 5, 20), '#123c39', { shadow: 0 });
  pencil(g, rim, 440 + v, { closed: true, width: 1.6 });
}

// ---- the to-do list: a sheet torn from a notebook, taped to the page
const STEPS = [
  { text: 'plant a seed', write: 1.0, check: 2.0 },
  { text: 'water it', write: 2.05, check: 4.0 },
  { text: 'add sunshine', write: 4.05, check: 6.0 },
  { text: 'be patient…', write: 6.05, check: 8.0 },
  { text: 'ta-da! a tree!', write: 8.05, check: 9.1 },
];
const ROW_Y = i => -62 + i * 44;
function tape(g, x, y, a, color) {
  const hw = 38, hh = 12, pts = [[-hw, -hh], [hw, -hh]];
  for (let k = 1; k < 6; k++) pts.push([hw + (k % 2 ? 3 : 0), -hh + k * hh / 3]);
  pts.push([hw, hh], [-hw, hh]);
  for (let k = 5; k > 0; k--) pts.push([-hw - (k % 2 ? 3 : 0), -hh + k * hh / 3]);
  g.save();
  g.translate(x, y);
  g.rotate(a);
  cut(g, pts, color, { sharp: true, shadow: 0.35, tex: [[P.stripes, 1]] });
  g.restore();
}
function paintNotepad(g, v) {
  const r = rng(500), x0 = -145, y0 = -160, w = 290, h = 320, top = [];
  for (let x = x0; x <= x0 + w; x += 6) top.push([x, y0 + sgn(r()) * 1.5 + (Math.floor((x - x0) / 12) % 2 ? 1.5 : 0)]);
  const path = cut(g, top.concat([[x0 + w, y0 + h], [x0, y0 + h]]), '#fffaf0', { sharp: true, tex: [[P.grain, 0.7]] });
  g.save();
  g.clip(path);
  g.strokeStyle = 'rgba(80,150,210,0.5)';
  g.lineWidth = 1.4;
  for (let k = 0; k < 6; k++) { g.beginPath(); g.moveTo(x0, -100 + k * 44); g.lineTo(x0 + w, -100 + k * 44); g.stroke(); }
  g.strokeStyle = 'rgba(230,90,90,0.55)';
  g.beginPath();
  g.moveTo(-98, y0);
  g.lineTo(-98, y0 + h);
  g.stroke();
  for (let k = 0; k < 9; k++) { g.fillStyle = 'rgba(80,60,40,0.18)'; g.beginPath(); g.arc(x0 + 16 + k * 32, y0 + 10, 3.2, 0, TAU); g.fill(); }
  g.restore();
  g.font = HAND(38);
  g.fillStyle = GRAPHITE;
  g.fillText('to do:', -86, -112);
  pencil(g, [[-90, -103], [-40, -101], [4, -104]], 510 + v, { color: C.pencilRed, width: 2.2, amp: 0.8 });
  for (let i = 0; i < 5; i++) {
    const cy = ROW_Y(i) - 10;
    pencil(g, [[-130, cy - 9], [-112, cy - 9.5], [-112, cy + 8.5], [-130, cy + 9]], 520 + i * 7 + v, { closed: true, sharp: true, width: 1.7, amp: 0.7 });
  }
  tape(g, -118, -160, -0.55, 'rgba(246,160,182,0.82)');
  tape(g, 116, -156, 0.5, 'rgba(140,210,198,0.82)');
}

// ---- title: ransom-note letters cut from magazines
const TITLE = 'HoW tO GRoW a TrEe';
const TILE_COLORS = ['#fffdf5', '#ffe066', '#ff9fb2', '#9edcd0', '#2e2420', '#f9a03f', '#cfe6ff', '#e8d8bc', '#c6e39a'];
const TILE_FONTS = [
  s => `${s}px "Abril Fatface", Georgia, serif`,
  s => MARKER(s),
  s => HAND(s * 1.3),
  s => `italic 700 ${s}px Georgia, "Times New Roman", serif`,
  s => `900 ${s}px "Arial Black", "Helvetica Neue", Arial, sans-serif`,
  s => `700 ${s}px "Courier New", Courier, monospace`,
];
function layoutTitle() {
  const r = rng(808), tiles = [];
  let x = 0, pf = -1, pc = -1;
  for (const ch of TITLE) {
    if (ch === ' ') { x += 20; continue; }
    let fi, ci;
    do fi = Math.floor(r() * TILE_FONTS.length); while (fi === pf);
    do ci = Math.floor(r() * TILE_COLORS.length); while (ci === pc);
    pf = fi; pc = ci;
    const font = TILE_FONTS[fi](36 + r() * 10);
    ctx.font = font;
    const m = ctx.measureText(ch);
    const box = { l: m.actualBoundingBoxLeft, r: m.actualBoundingBoxRight, a: m.actualBoundingBoxAscent, d: m.actualBoundingBoxDescent };
    const tw = box.l + box.r + 14 + r() * 8, th = box.a + box.d + 14 + r() * 8;
    tiles.push({
      ch, font, box, tw, th, fill: TILE_COLORS[ci], x: x + tw / 2, y: 80 + sgn(r()) * 5, rot: sgn(r()) * 0.13,
      seed: Math.floor(r() * 1e6), ink: ci === 4 ? '#fffdf5' : [INK, '#c7362b', '#1f5fa8', INK][Math.floor(r() * 4)],
      news: ci === 0 || ci === 7,
    });
    x += tw + 4;
  }
  const dx = 640 - (x - 4) / 2;
  tiles.forEach(t => { t.x += dx; });
  return tiles;
}
function paintTile(g, t) {
  const r = rng(t.seed), hw = t.tw / 2, hh = t.th / 2, j = () => sgn(r()) * 2;
  cut(g, [[-hw + j(), -hh + j()], [hw + j(), -hh + j()], [hw + j(), hh + j()], [-hw + j(), hh + j()]], t.fill,
    { sharp: true, tex: t.news ? [[P.grain, 1], [P.news, 0.22]] : [[P.grain, 1]] });
  g.font = t.font;
  g.fillStyle = t.ink;
  g.fillText(t.ch, -(t.box.l + t.box.r) / 2 + t.box.l, (t.box.a - t.box.d) / 2);
}

// ---- leaves: torn circles from six different papers
function leafStyles() {
  return [
    { fill: C.leaves[0], tex: [[P.grain, 1], [P.dotsDark, 1]] },
    { fill: C.leaves[1], tex: [[P.grain, 1], [P.stripes, 1]] },
    { fill: C.leaves[2], tex: [[P.grain, 1]] },
    { fill: C.leaves[3], tex: [[P.grain, 1], [P.grid, 1]] },
    { fill: C.leaves[4], tex: [[P.grain, 1], [P.news, 0.3]] },
    { fill: C.leaves[5], tex: [[P.grain, 1], [P.dots, 1]] },
  ];
}
function paintLeaf(g, st, seed) {
  const r = rng(seed), ph = r() * TAU, ph2 = r() * TAU;
  const base = resample(polar(0, 0, 40, 38, 30, a => 1 + 0.07 * Math.sin(a * 3 + ph) + 0.04 * Math.sin(a * 5 + ph2)), 5);
  const t = torn(g, base, st.fill, { seed, rim: 1.8, jag: 0.8, tex: st.tex });
  hatchShade(g, t.pts, -10, -10, P.hatchGreen, 0.55);
  for (let k = 0; k < 3; k++) {
    const cx = -4 + sgn(r()) * 16, cy = 2 + sgn(r()) * 14, rr = 6 + r() * 4, arc = [];
    for (let i = 0; i <= 6; i++) { const a = Math.PI * (0.15 + 0.7 * i / 6); arc.push([cx + Math.cos(a) * rr, cy + Math.sin(a) * rr]); }
    pencil(g, arc, seed + k, { color: '#1f4a24', width: 1.6, alpha: 0.5, passes: 1 });
  }
}

// ---- apple
function paintApple(g, v) {
  const pts = polar(0, 0, 14, 13.5, 30, a => 1 - 0.13 * Math.exp(-(angDiff(a, 1.5 * Math.PI) ** 2) / 0.08));
  cut(g, pts, C.red, { tex: [[P.grain, 1]] });
  hatchShade(g, pts, -5, -5, P.hatch, 0.35);
  pencil(g, [[-8, -4], [-9, 2], [-6, 7]], 600 + v, { color: '#fff4ea', width: 2.4, alpha: 0.85, passes: 1 });
  pencil(g, pts, 610 + v, { closed: true, width: 1.6 });
  pencil(g, [[0, -11], [1, -16], [3, -20]], 620 + v, { width: 2.4, color: '#4a2f1a', passes: 1 });
  const leaf = [[2, -16], [8, -22], [15, -21], [10, -15]];
  cut(g, leaf, C.leaves[2], { shadow: 0.4 });
  pencil(g, leaf, 630 + v, { closed: true, width: 1.2 });
}

// ---- a little blue bird: wings up, wings down, perched
function paintBird(g, pose) {
  const BLUE = '#4a7fd6', DARK = '#2c5aa8', BELLY = '#f7a449';
  const tail = [[14, -4], [34, -14], [36, -8], [31, 3]];
  cut(g, tail, DARK, { sharp: true, tex: [[P.grain, 1]] });
  pencil(g, tail, 700, { closed: true, sharp: true, width: 1.5 });
  const body = polar(0, 0, 20, 16, 30, a => 1 + 0.06 * Math.cos(a));
  const bp = cut(g, body, BLUE, { tex: [[P.grain, 1], [P.dots, 1]] });
  g.save();
  g.clip(bp);
  cut(g, polar(-6, 9, 14, 10, 20), BELLY, { shadow: 0, tex: [[P.grain, 1]] });
  g.restore();
  pencil(g, body, 710, { closed: true, width: 1.6 });
  const wing = pose === 0 ? [[-2, -6], [6, -30], [16, -34], [14, -8]]
    : pose === 1 ? [[-2, -2], [4, 22], [14, 26], [14, 0]] : [[-6, -2], [8, -8], [21, 0], [8, 8]];
  cut(g, wing, DARK, { tex: [[P.grain, 1], [P.stripes, 1]] });
  pencil(g, wing, 720 + pose, { closed: true, width: 1.4 });
  const beak = [[-18, -5], [-30, -1], [-18, 3]];
  cut(g, beak, C.ray, { sharp: true, shadow: 0.5 });
  pencil(g, beak, 730, { closed: true, sharp: true, width: 1.3 });
  g.fillStyle = '#fffdf6';
  g.beginPath(); g.arc(-9, -6, 3.8, 0, TAU); g.fill();
  g.fillStyle = INK;
  g.beginPath(); g.arc(-10, -6, 2.1, 0, TAU); g.fill();
  g.fillStyle = 'rgba(244,120,140,0.55)';
  g.beginPath(); g.ellipse(-12, 3, 3.5, 2.2, 0, 0, TAU); g.fill();
  if (pose === 2) {
    pencil(g, [[-4, 14], [-5, 23]], 740, { width: 2, color: '#5e3b22', passes: 1 });
    pencil(g, [[4, 14], [5, 23]], 741, { width: 2, color: '#5e3b22', passes: 1 });
  }
}

// ---- a tear-off calendar that counts the years
function paintCalendar(g) {
  const pts = resample([[-46, -48], [46, -50], [47, 52], [-45, 50]], 8);
  cut(g, shift(pts, 5, 6), '#e9e0cf', { tex: [[P.grain, 1]] });
  cut(g, shift(pts, 2.5, 3), '#f4ede0', { shadow: 0.5, tex: [[P.grain, 1]] });
  const p = cut(g, pts, '#fffdf6', { shadow: 0.5, tex: [[P.grain, 1]] });
  g.save();
  g.clip(p);
  g.fillStyle = C.red;
  g.fillRect(-60, -60, 120, 34);
  layer(g, new Path2D('M-60 -60h120v34h-120z'), [[P.grain, 1]]);
  g.restore();
  pencil(g, pts, 750, { closed: true, width: 1.6 });
  g.font = MARKER(15);
  g.fillStyle = '#fffdf6';
  g.textAlign = 'center';
  g.fillText('YEAR', 0, -31);
  for (const x of [-24, 24]) {
    g.fillStyle = INK;
    g.beginPath(); g.arc(x, -44, 3, 0, TAU); g.fill();
    g.strokeStyle = '#8c8f94';
    g.lineWidth = 3;
    g.beginPath(); g.arc(x, -50, 6, Math.PI * 1.05, Math.PI * 1.95); g.stroke();
  }
}

// ---- the seed leaves of the sprout, and a drop of water
function paintCotyledon(g) {
  const pts = [];
  for (let i = 0; i <= 12; i++) { const u = i / 12; pts.push([u * 30, -Math.sin(Math.PI * u) * 9 * (1 - 0.25 * u)]); }
  for (let i = 11; i > 0; i--) { const u = i / 12; pts.push([u * 30, Math.sin(Math.PI * u) * 8 * (1 - 0.25 * u)]); }
  cut(g, pts, '#8cc84b', { shadow: 0.7, tex: [[P.grain, 1]] });
  pencil(g, pts, 760, { closed: true, width: 1.4 });
  pencil(g, [[2, 0], [16, -1], [26, 0]], 761, { width: 1.1, color: '#3e7a2a', passes: 1 });
}
function paintDrop(g) {
  const pts = [];
  for (let i = 0; i < 28; i++) { const t = i / 28 * TAU; pts.push([7 * Math.sin(t) * Math.sin(t / 2), -10 * Math.cos(t) + 2]); }
  cut(g, pts, C.blue, { shadow: 0.5, tex: [[P.grain, 1]] });
  pencil(g, [[-3, 3], [-3.5, 6], [-1.5, 8.5]], 770, { color: '#ffffff', width: 1.8, alpha: 0.85, passes: 1, amp: 0.2 });
  pencil(g, pts, 771, { closed: true, width: 1.2, alpha: 0.8, passes: 1, amp: 0.3 });
}

// ---- build every piece at the current resolution
let BG = null, TILES = [];
const SPR = {};
function buildSprites() {
  buildPatterns();
  BG = makeCanvas(stage.width, stage.height);
  const bg = BG.getContext('2d');
  bg.setTransform(stage.width / W, 0, 0, stage.height / H, 0, 0);
  paintBackground(bg);
  SPR.grass = sprite(0, 470, W, 545, paintGrass);
  SPR.clouds = [[92, 44, 101], [72, 36, 102], [56, 30, 103]].map(([rx, ry, s]) => sprite(-rx - 8, -ry - 8, rx + 8, ry + 8, g => paintCloud(g, rx, ry, s)));
  SPR.rays = sprite(-100, -100, 100, 100, paintRays);
  SPR.sun = [0, 1, 2].map(v => sprite(-60, -60, 60, 60, g => paintSunBody(g, v)));
  SPR.acorn = [0, 1, 2].map(v => sprite(-24, -36, 24, 34, g => paintAcorn(g, v)));
  SPR.mound = [0, 1, 2].map(v => sprite(-52, -20, 52, 14, g => paintMound(g, v)));
  SPR.can = [0, 1, 2].map(v => sprite(-176, -116, 100, 60, g => paintCan(g, v)));
  SPR.notepad = [0, 1, 2].map(v => sprite(-170, -185, 170, 168, g => paintNotepad(g, v)));
  SPR.items = STEPS.map(s => {
    ctx.font = HAND(31);
    const w = ctx.measureText(s.text).width;
    return sprite(0, -30, w + 2, 10, g => { g.font = HAND(31); g.fillStyle = GRAPHITE; g.fillText(s.text, 0, 0); }, 4);
  });
  TILES = layoutTitle();
  SPR.tiles = TILES.map(t => sprite(-t.tw / 2 - 4, -t.th / 2 - 4, t.tw / 2 + 4, t.th / 2 + 4, g => paintTile(g, t)));
  const styles = leafStyles();
  SPR.leaves = [];
  for (let s = 0; s < styles.length; s++) for (let k = 0; k < 2; k++) SPR.leaves.push(sprite(-46, -46, 46, 46, g => paintLeaf(g, styles[s], 1200 + s * 10 + k)));
  SPR.apple = [0, 1, 2].map(v => sprite(-18, -26, 20, 18, g => paintApple(g, v)));
  SPR.bird = [0, 1, 2].map(pose => sprite(-34, -40, 40, 30, g => paintBird(g, pose)));
  SPR.calendar = sprite(-52, -60, 56, 62, paintCalendar);
  SPR.cotyledon = sprite(-2, -12, 32, 12, paintCotyledon);
  SPR.drop = sprite(-9, -12, 9, 14, paintDrop, 6);
}

// ---------------------------------------------------------------- the story, as data
// Everything below is shared by the pictures and the sound, so they stay in step.
const SUN = { x: 1150, y: 162 };
const CAN = { x: 1012, y: 332, tilt: -0.6 };
const CAL = { x: 1112, y: 432 };
const ACORN_REST = 590;          // y of the buried acorn's centre
const TRUNK_BASE = [TREE_X, 530];

// Branches: a seeded recursive tree. Each segment knows when it starts and stops growing.
function buildTree() {
  const r = rng(20260925), segs = [];
  const DUR = [0.5, 0.42, 0.38, 0.34, 0.3];
  const SPREAD = [0, 0.72, 0.6, 0.52, 0.46];
  const MAXD = 4;
  function grow(p0, ang, len, w0, depth, t0) {
    const p1 = [p0[0] + Math.cos(ang) * len, p0[1] + Math.sin(ang) * len];
    const bend = sgn(r()) * 0.1 * len;
    const c = [(p0[0] + p1[0]) / 2 - Math.sin(ang) * bend, (p0[1] + p1[1]) / 2 + Math.cos(ang) * bend];
    const seg = { p0, c, p1, w0, w1: w0 * 0.68, depth, t0, t1: t0 + DUR[depth], ang, len };
    segs.push(seg);
    if (depth === MAXD) return;
    const kids = depth === 0 ? 3 : r() < 0.3 ? 3 : 2;
    for (let k = 0; k < kids; k++) {
      const side = kids === 2 ? (k ? 1 : -1) : k - 1;
      let a = ang + side * SPREAD[depth + 1] * (0.85 + r() * 0.3) + sgn(r()) * 0.1;
      a = clamp(a, -Math.PI + 0.3, -0.3);
      grow(p1, a, len * (0.7 + r() * 0.1), seg.w1, depth + 1, seg.t0 + DUR[depth] * 0.75);
    }
  }
  grow(TRUNK_BASE, -Math.PI / 2, 108, 26, 0, 6.0);
  return segs;
}

// Roots: pale threads that spread through the soil from the acorn.
function buildRoots() {
  const r = rng(77), segs = [];
  function grow(p0, ang, len, w0, depth, t0) {
    const p1 = [p0[0] + Math.cos(ang) * len, p0[1] + Math.sin(ang) * len];
    const bend = sgn(r()) * 0.25 * len;
    const c = [(p0[0] + p1[0]) / 2 - Math.sin(ang) * bend, (p0[1] + p1[1]) / 2 + Math.cos(ang) * bend];
    const dur = depth === 0 ? 1.2 : 0.9;
    segs.push({ p0, c, p1, w0, w1: w0 * 0.6, depth, t0, t1: t0 + dur });
    if (depth === 2) return;
    const kids = depth === 0 ? 4 : 2;
    for (let k = 0; k < kids; k++) {
      const u = (k + 1) / (kids + 1);
      const at = bez(p0, c, p1, u);
      const side = k % 2 ? 1 : -1;
      grow(at, clamp(ang + side * (0.9 + r() * 0.5), 0.15, Math.PI - 0.15), len * (0.55 + r() * 0.2), w0 * 0.6, depth + 1, t0 + dur * u * 0.9 + 0.2);
    }
  }
  grow([TREE_X, ACORN_REST + 24], Math.PI / 2 - 0.08, 92, 7, 0, 4.85);
  grow([TREE_X - 6, ACORN_REST + 18], Math.PI / 2 + 0.9, 70, 5, 1, 5.6);
  grow([TREE_X + 6, ACORN_REST + 18], Math.PI / 2 - 0.9, 74, 5, 1, 5.7);
  return segs;
}

const TREE = buildTree(), ROOTS = buildRoots();

// Canopy: torn-paper leaves at the ends of the upper branches, popping in as each branch finishes.
const LEAVES = (() => {
  const r = rng(4242), out = [];
  for (const s of TREE) {
    if (s.depth < 1) continue;
    const t = s.t1 + 0.04 + r() * 0.12;
    if (s.depth === 1) {
      out.push({ x: s.p1[0], y: s.p1[1] + 6, rad: 56 + r() * 10, t: t - 0.25, spr: 2 * r() < 1 ? 0 : 1, layer: 0 });
      continue;
    }
    const rad = [0, 0, 42, 35, 29][s.depth] + sgn(r()) * 5;
    out.push({ x: s.p1[0], y: s.p1[1], rad, t, spr: 2 + Math.floor(r() * 10), layer: s.depth });
    if (s.depth === 4) out.push({ x: s.p1[0] + Math.cos(s.ang) * 14, y: s.p1[1] + Math.sin(s.ang) * 14, rad: 24 + r() * 5, t: t + 0.08, spr: 2 + Math.floor(r() * 10), layer: 5 });
  }
  return out.sort((a, b) => a.layer - b.layer || a.y - b.y);
})();

// Apples on well spread-out leaves; the bird lands on the highest one.
const APPLES = (() => {
  const cand = LEAVES.filter(l => l.layer >= 4);
  const cx = cand.reduce((s, l) => s + l.x, 0) / cand.length, cy = cand.reduce((s, l) => s + l.y, 0) / cand.length;
  const chosen = [cand.reduce((b, l) => (Math.hypot(l.x - cx, l.y - cy) < Math.hypot(b.x - cx, b.y - cy) ? l : b))];
  while (chosen.length < 5) {
    let best = null, bd = -1;
    for (const l of cand) {
      const d = Math.min(...chosen.map(c => Math.hypot(l.x - c.x, l.y - c.y)));
      if (d > bd) { bd = d; best = l; }
    }
    chosen.push(best);
  }
  return chosen.map((l, i) => ({ x: l.x + 4, y: l.y + 8, t: 8.15 + i * 0.14 }));
})();
const PERCH = (() => { const top = LEAVES.reduce((b, l) => (l.y - l.rad < b.y - b.rad ? l : b)); return { x: top.x, y: top.y - top.rad * 0.8 }; })();

// Water: two drops leave the rose every 90 ms while the can is tipped.
const GRAVITY = 1500;
function canPose(t) {
  let x = CAN.x, y = CAN.y, a = 0;
  if (t < 2.5) x = lerp(1440, CAN.x, backOut(prog(t, 2.1, 2.5), 1.4));
  if (t > 3.65) x = lerp(CAN.x, 1460, easeIn(prog(t, 3.65, 4.0)));
  a = CAN.tilt * (easeInOut(prog(t, 2.5, 2.7)) - easeInOut(prog(t, 3.45, 3.65)));
  return { x, y: y + Math.sin(t * 9) * 2 * (t < 2.5 ? 1 : 0), a };
}
function canTip(pose) {
  const c = Math.cos(pose.a), s = Math.sin(pose.a);
  return [pose.x + CAN_TIP[0] * c - CAN_TIP[1] * s, pose.y + CAN_TIP[0] * s + CAN_TIP[1] * c];
}
const DROPS = (() => {
  const r = rng(99), out = [];
  const tip = canTip({ x: CAN.x, y: CAN.y, a: CAN.tilt });
  const c = Math.cos(CAN.tilt), s = Math.sin(CAN.tilt), L = Math.hypot(CAN_DIR[0], CAN_DIR[1]);
  const dir = [(CAN_DIR[0] * c - CAN_DIR[1] * s) / L, (CAN_DIR[0] * s + CAN_DIR[1] * c) / L];
  for (let i = 0; i < 8; i++) {
    for (let k = 0; k < 2; k++) {
      const sp = 95 + r() * 50, vx = dir[0] * sp + sgn(r()) * 18, vy = dir[1] * sp + sgn(r()) * 18;
      const t0 = 2.72 + i * 0.09 + k * 0.03, dy = GROUND - 4 - tip[1];
      const tf = (-vy + Math.sqrt(vy * vy + 2 * GRAVITY * dy)) / GRAVITY;
      out.push({ t0, x0: tip[0], y0: tip[1], vx, vy, land: t0 + tf, lx: tip[0] + vx * tf, note: i });
    }
  }
  return out;
})();

// The years flick past on the calendar while the tree grows.
const YEAR_T0 = 6.1, YEAR_T1 = 7.9;
const yearAt = t => (t < YEAR_T0 ? 1 : Math.min(20, 1 + Math.floor(prog(t, YEAR_T0, YEAR_T1) * 19.999)));

// Leaf pops that get their own sound: one per little cluster of leaves.
const LEAF_POPS = (() => {
  const times = LEAVES.map(l => l.t).sort((a, b) => a - b), out = [];
  for (const t of times) if (!out.length || t - out[out.length - 1] > 0.085) out.push(t);
  return out;
})();

// ---------------------------------------------------------------- drawing one frame
function circleTo(path, [x, y], r) { path.moveTo(x + r, y); path.arc(x, y, r, 0, TAU); }
function segOutline(s, p, grow, extra) {
  const N = 7, L = [], R = [];
  for (let i = 0; i <= N; i++) {
    const u = p * i / N, q = bez(s.p0, s.c, s.p1, u);
    const dx = 2 * (1 - u) * (s.c[0] - s.p0[0]) + 2 * u * (s.p1[0] - s.c[0]);
    const dy = 2 * (1 - u) * (s.c[1] - s.p0[1]) + 2 * u * (s.p1[1] - s.c[1]);
    const l = Math.hypot(dx, dy) || 1, w = (lerp(s.w0, s.w1, u) * grow + extra) / 2;
    L.push([q[0] - dy / l * w, q[1] + dx / l * w]);
    R.push([q[0] + dy / l * w, q[1] - dx / l * w]);
  }
  const poly = L.concat(R.reverse());
  return area(poly) < 0 ? poly.reverse() : poly;
}
// Branches and roots: an ink silhouette, then the paper colour inside it.
function drawBranches(segs, t, o) {
  const outline = new Path2D(), body = new Path2D();
  let any = false;
  for (const s of segs) {
    const p = o.progress(s, t);
    if (p < 0.002) continue;
    any = true;
    const g = o.grow, tip = bez(s.p0, s.c, s.p1, p), wt = lerp(s.w0, s.w1, p) * g;
    linePath(segOutline(s, p, g, o.extra), true, outline);
    linePath(segOutline(s, p, g, 0), true, body);
    if (s.depth > 0 || o.roots) { circleTo(outline, s.p0, (s.w0 * g + o.extra) / 2); circleTo(body, s.p0, s.w0 * g / 2); }
    circleTo(outline, tip, (wt + o.extra) / 2);
    circleTo(body, tip, wt / 2);
  }
  if (!any) return;
  ctx.save();
  if (o.shadow) shadow(ctx, o.shadow);
  ctx.fillStyle = o.ink;
  ctx.fill(outline);
  ctx.restore();
  ctx.fillStyle = o.fill;
  ctx.fill(body);
  if (o.tex) layer(ctx, body, o.tex);
}

const trunkProgress = t => 0.55 * easeOut(prog(t, 5.25, 5.85)) + 0.45 * easeInOut(prog(t, 6.0, 6.5));
const treeProgress = (s, t) => (s.depth === 0 ? trunkProgress(t) : easeOut(prog(t, s.t0, s.t1)));
const thickness = t => lerp(0.2, 1, easeInOut(prog(t, 6.0, 7.8)));

function drawTree(t) {
  if (t < 5.25) return;
  const brown = prog(t, 6.05, 6.9);
  drawBranches(TREE, t, {
    progress: treeProgress, grow: thickness(t), extra: 3.6, ink: INK, shadow: 1,
    fill: blend(C.sprout, C.bark, brown), tex: brown > 0 ? [[P.bark, brown * 0.8], [P.grain, 1]] : [[P.grain, 1]],
  });
}

function drawRoots(t) {
  drawBranches(ROOTS, t, {
    progress: (s, tt) => easeOut(prog(tt, s.t0, s.t1)), grow: lerp(0.7, 1.1, prog(t, 6, 8)), extra: 2.6,
    ink: 'rgba(46,36,32,0.9)', fill: C.root, roots: true, tex: [[P.grain, 1]],
  });
  const sp = easeOut(prog(t, 4.85, 5.3));
  if (sp > 0) { // the shoot, from the acorn up to the light
    const y0 = ACORN_REST - 20, y1 = lerp(y0, 515, sp), w = lerp(5, 16, easeInOut(prog(t, 6.0, 7.8)));
    const stem = { p0: [TREE_X, y0], c: [TREE_X - 3, (y0 + y1) / 2], p1: [TREE_X, y1], w0: w * 0.9, w1: w, depth: 1 };
    drawBranches([stem], t, { progress: () => 1, grow: 1, extra: 3, ink: INK, fill: blend(C.sprout, C.root, prog(t, 6.0, 7.0)), roots: true });
  }
}

// ---- the acorn, with a face that tells the story
function acornState(t) {
  if (t < 1.1) return null;
  if (t < 1.6) {
    const p = prog(t, 1.1, 1.6);
    return { x: TREE_X + Math.sin(p * Math.PI) * 26, y: lerp(-50, 500, easeIn(p)), rot: (1 - p) * 3 * Math.PI, sx: 1, sy: 1, under: false };
  }
  if (t < 1.78) {
    const u = prog(t, 1.6, 1.78), squash = u < 0.15;
    return { x: TREE_X, y: 500 - 104 * u * (1 - u), rot: Math.sin(u * Math.PI) * 0.35, sx: squash ? 1.18 : 1, sy: squash ? 0.82 : 1, under: false };
  }
  if (t < 1.85) return { x: TREE_X, y: 500, rot: 0, sx: 1, sy: 1, under: false };
  const p = easeInOut(prog(t, 1.85, 2.15));
  return { x: TREE_X, y: lerp(500, ACORN_REST, p), rot: Math.sin(p * Math.PI) * 0.25, sx: 1, sy: 1, under: true };
}
function drawAcorn(st, t, f) {
  const n = nudge(30, f, 0.4), x = st.x + n.dx, y = st.y + n.dy + 27 * (1 - st.sy), a = st.rot + n.dr;
  blit(pick(SPR.acorn, 2, f), x, y, { rot: a, sx: st.sx, sy: st.sy });
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(a);
  ctx.scale(st.sx, st.sy);
  const seed = 3300 + (f % 3);
  const mood = t < 1.85 ? 'wow' : t < 4.45 ? 'sleep' : t < 5.4 ? 'awake' : 'happy';
  ctx.fillStyle = 'rgba(240,110,120,0.5)';
  for (const cx of [-11, 11]) { ctx.beginPath(); ctx.ellipse(cx, 11, 3.6, 2.3, 0, 0, TAU); ctx.fill(); }
  for (const ex of [-6.5, 6.5]) {
    if (mood === 'sleep') pencil(ctx, [[ex - 3.5, 4], [ex, 6.5], [ex + 3.5, 4]], seed + ex, { width: 1.6, amp: 0.3, passes: 1 });
    else if (mood === 'happy') pencil(ctx, [[ex - 3.5, 6], [ex, 2.5], [ex + 3.5, 6]], seed + ex, { width: 1.7, amp: 0.3, passes: 1 });
    else {
      ctx.fillStyle = INK;
      ctx.beginPath(); ctx.ellipse(ex, 5, 2.2, mood === 'awake' ? 3 : 2.5, 0, 0, TAU); ctx.fill();
      ctx.fillStyle = '#fff';
      ctx.beginPath(); ctx.arc(ex + 0.8, 4, 0.8, 0, TAU); ctx.fill();
    }
  }
  if (mood === 'happy') pencil(ctx, [[-4, 12], [0, 15], [4, 12]], seed + 9, { width: 1.6, amp: 0.3, passes: 1 });
  else if (mood === 'sleep') pencil(ctx, [[-2, 13], [2, 13]], seed + 9, { width: 1.5, amp: 0.3, passes: 1 });
  else { ctx.strokeStyle = INK; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.ellipse(0, 13, 2.2, mood === 'wow' ? 3 : 2.4, 0, 0, TAU); ctx.stroke(); }
  if (t > 4.7) pencil(ctx, [[-15, 17], [-8, 13], [-3, 19], [3, 13], [9, 18], [15, 14]], seed + 11, { width: 1.6, sharp: true, amp: 0.4 });
  ctx.restore();
}

function drawWorm(t, f) {
  const happy = prog(t, 2.95, 3.1) * (1 - prog(t, 3.9, 4.1));
  const amp = (2.2 + happy * 3) * (jitterAmp ? 1 : 0.4), speed = 5 + happy * 7, pts = [];
  for (let i = 0; i < 9; i++) pts.push([952 + i * 8, 656 + Math.sin(t * speed - i * 0.9) * amp]);
  const path = smoothPath(pts, false);
  ctx.save();
  ctx.lineCap = ctx.lineJoin = 'round';
  ctx.strokeStyle = INK; ctx.lineWidth = 15; ctx.stroke(path);
  ctx.strokeStyle = '#f4a0b2'; ctx.lineWidth = 11.5; ctx.stroke(path);
  ctx.strokeStyle = 'rgba(170,70,95,0.45)'; ctx.lineWidth = 1.4;
  for (let i = 2; i < 8; i++) { const [x, y] = pts[i]; ctx.beginPath(); ctx.moveTo(x, y - 5); ctx.lineTo(x + 1, y + 5); ctx.stroke(); }
  const [hx, hy] = pts[0];
  ctx.fillStyle = INK;
  ctx.beginPath(); ctx.arc(hx - 1, hy - 2, 1.6, 0, TAU); ctx.fill();
  ctx.restore();
  pencil(ctx, [[hx - 4, hy + 1.5], [hx - 1.5, hy + 3.5], [hx + 1, hy + 2]], 3400 + (f % 3), { width: 1.3, amp: 0.2, passes: 1 });
  const hp = prog(t, 3.15, 3.35), hf = 1 - prog(t, 4.2, 4.5);
  if (hp > 0 && hf > 0) drawHeart(944, 630 - hp * 8, 9 * backOut(hp, 2.5), hf, f);
}
function drawHeart(x, y, s, alpha, f) {
  const pts = [];
  for (let i = 0; i < 24; i++) {
    const a = i / 24 * TAU;
    pts.push([x + s * 0.8 * Math.sin(a) ** 3, y - s * (0.8 * Math.cos(a) - 0.3 * Math.cos(2 * a) - 0.12 * Math.cos(3 * a) - 0.05 * Math.cos(4 * a))]);
  }
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.fillStyle = C.red;
  ctx.fill(smoothPath(pts));
  pencil(ctx, pts, 3500 + (f % 3), { closed: true, width: 1.4, amp: 0.3, alpha: alpha * 0.9 });
  ctx.restore();
}

function drawUnderground(t, f) {
  const landed = DROPS.filter(d => d.land <= t).length;
  if (landed) {
    const w = easeOut(landed / DROPS.length) * (1 - 0.35 * prog(t, 6, 8.5));
    const pts = polar(TREE_X, 568, 26 + 66 * w, 18 + 40 * w, 26, a => 1 + 0.08 * Math.sin(a * 4 + 1) + 0.05 * Math.sin(a * 7));
    ctx.fillStyle = `rgba(56,32,16,${0.34 * (1 - 0.5 * prog(t, 6, 8.5))})`;
    ctx.fill(smoothPath(shift(pts, sgn(hash(7, f)) * 0.6 * jitterAmp, 0)));
  }
  for (const d of DROPS) {
    for (let k = 0; k < 2; k++) {
      const p = prog(t, d.land + k * 0.1, d.land + k * 0.1 + 0.45);
      if (p <= 0 || p >= 1) continue;
      ctx.fillStyle = `rgba(90,182,228,${0.95 * (1 - p * 0.5)})`;
      ctx.beginPath();
      ctx.ellipse(lerp(d.lx, TREE_X + (k ? 7 : -7), easeIn(p)), lerp(GROUND + 20, ACORN_REST - 12, p), 3, 3.8, 0, 0, TAU);
      ctx.fill();
    }
  }
  drawRoots(t);
  const st = acornState(t);
  if (st && st.under) drawAcorn(st, t, f);
  if (t < 4.45) {
    ctx.save();
    for (let k = 0; k < 5; k++) {
      const p = prog(t, 2.3 + k * 0.45, 3.3 + k * 0.45);
      if (p <= 0 || p >= 1) continue;
      ctx.font = HAND(16 + p * 12);
      ctx.fillStyle = `rgba(255,244,220,${(1 - p) * 0.95})`;
      ctx.fillText('z', TREE_X + 18 + p * 40, ACORN_REST - 10 - p * 36);
    }
    ctx.restore();
  }
  const ex = prog(t, 4.45, 4.6) * (1 - prog(t, 5.0, 5.2));
  if (ex > 0) {
    ctx.save();
    ctx.translate(TREE_X + 26, ACORN_REST - 30);
    ctx.rotate(0.15);
    ctx.scale(backOut(ex, 3), backOut(ex, 3));
    ctx.font = MARKER(28);
    ctx.lineWidth = 4;
    ctx.strokeStyle = INK;
    ctx.fillStyle = C.yellow;
    ctx.strokeText('!', 0, 0);
    ctx.fillText('!', 0, 0);
    ctx.restore();
  }
  drawWorm(t, f);
}

// ---- above the ground
const CLOUDS = [[470, 180, 0, 7], [1182, 318, 1, -5], [655, 238, 2, 6]];
function drawClouds(t, f) {
  CLOUDS.forEach(([x, y, i, v], k) => { const n = nudge(10 + k, f); blit(SPR.clouds[i], x + v * t + n.dx, y + n.dy, { rot: n.dr }); });
}

function drawSun(t, f) {
  const p = prog(t, 4.0, 4.45);
  if (p <= 0) return;
  const sc = backOut(p, 2.4), n = nudge(20, f), x = SUN.x + n.dx, y = SUN.y + n.dy;
  blit(SPR.rays, x, y, { rot: (t - 4) * 0.5, sx: sc, shadow: 1 });
  blit(pick(SPR.sun, 1, f), x, y, { rot: n.dr, sx: sc });
  ctx.save();
  ctx.translate(x, y);
  ctx.scale(sc, sc);
  const seed = 3600 + (f % 3), wink = t > 9.25 && t < 9.75;
  ctx.fillStyle = 'rgba(245,110,110,0.45)';
  for (const cx of [-27, 27]) { ctx.beginPath(); ctx.ellipse(cx, 12, 8, 5, 0, 0, TAU); ctx.fill(); }
  for (const ex of [-17, 17]) {
    if (wink && ex > 0) { pencil(ctx, [[ex - 7, -5], [ex, -10], [ex + 7, -5]], seed + 1, { width: 2.6, amp: 0.4 }); continue; }
    ctx.fillStyle = INK;
    ctx.beginPath(); ctx.ellipse(ex, -7, 4, 5.5, 0, 0, TAU); ctx.fill();
    ctx.fillStyle = '#fff';
    ctx.beginPath(); ctx.arc(ex + 1.5, -9, 1.5, 0, TAU); ctx.fill();
  }
  pencil(ctx, [[-16, 12], [-8, 21], [0, 24], [8, 21], [16, 12]], seed + 2, { width: 2.8, amp: 0.5 });
  ctx.restore();
}

function drawSunbeams(t, f) {
  const a = prog(t, 4.35, 4.6) * (1 - prog(t, 5.55, 5.9));
  if (a <= 0) return;
  const tx = TREE_X + 10, ty = 470, th = Math.atan2(ty - SUN.y, tx - SUN.x), nx = -Math.sin(th), ny = Math.cos(th);
  ctx.save();
  ctx.globalAlpha = a;
  ctx.setLineDash([13, 12]);
  ctx.lineDashOffset = -t * 110;
  for (let k = -1; k <= 1; k++) {
    const r = rng(3700 + k * 10 + (f % 3));
    const s0 = [SUN.x + Math.cos(th) * 104 + nx * k * 26, SUN.y + Math.sin(th) * 104 + ny * k * 26];
    const s1 = [tx + nx * k * 16, ty + ny * k * 16];
    const c = [(s0[0] + s1[0]) / 2 + nx * 30 + sgn(r()) * 3, (s0[1] + s1[1]) / 2 + ny * 30 + sgn(r()) * 3];
    const pts = [];
    for (let i = 0; i <= 12; i++) pts.push(bez(s0, c, s1, i / 12));
    pencil(ctx, pts, 3710 + k + (f % 3) * 5, { color: C.ray, width: 3.4, amp: 0.8, passes: 1, alpha: 1 });
  }
  ctx.restore();
}

function drawMound(t, f) {
  const p = prog(t, 1.95, 2.2);
  if (p > 0) blit(pick(SPR.mound, 3, f), TREE_X + nudge(40, f, 0.3).dx, 520, { sx: 1, sy: backOut(p, 2) });
}

function drawSprout(t, f) {
  const tp = trunkProgress(t);
  const open = backOut(prog(t, 5.55, 5.85), 2.2), shrink = 1 - easeIn(prog(t, 6.15, 6.5));
  const s = open * shrink;
  if (s > 0.01) {
    const trunk = TREE[0], tip = bez(trunk.p0, trunk.c, trunk.p1, tp);
    const spread = lerp(1.25, 0.42, prog(t, 5.55, 5.85));
    blit(SPR.cotyledon, tip[0] + 1, tip[1] + 2, { rot: -spread, sx: s });
    blit(SPR.cotyledon, tip[0] - 1, tip[1] + 2, { rot: Math.PI + spread, sx: s, sy: -s });
  }
  const b = prog(t, 5.3, 5.55);
  if (b > 0 && b < 1) {
    for (let k = 0; k < 4; k++) {
      const a = -Math.PI / 2 + (k - 1.5) * 0.55, r0 = 24 + b * 10, r1 = r0 + 12;
      pencil(ctx, [[TREE_X + Math.cos(a) * r0, 500 + Math.sin(a) * r0], [TREE_X + Math.cos(a) * r1, 500 + Math.sin(a) * r1]],
        3800 + k + (f % 3) * 7, { width: 2.4, amp: 0.4, passes: 1 });
    }
  }
}

function drawLeaves(t, f) {
  for (let i = 0; i < LEAVES.length; i++) {
    const l = LEAVES[i], p = prog(t, l.t, l.t + 0.3);
    if (p <= 0) continue;
    const n = nudge(100 + i, f, 0.5), sway = t > 8 ? Math.sin(t * 2.2 + l.x * 0.03) * 1.2 * jitterAmp : 0;
    blit(SPR.leaves[l.spr], l.x + n.dx + sway, l.y + n.dy, { rot: n.dr + (1 - p) * 0.8, sx: backOut(p, 2.6) * l.rad / 40 });
  }
}

function drawApples(t, f) {
  APPLES.forEach((a, i) => {
    const p = prog(t, a.t, a.t + 0.25);
    if (p <= 0) return;
    const n = nudge(300 + i, f, 0.4);
    blit(pick(SPR.apple, i, f), a.x + n.dx, a.y + n.dy + Math.sin(t * 3 + i) * 0.8, { rot: n.dr + (1 - p), sx: backOut(p, 3) });
  });
}

function drawCalendar(t, f) {
  const p = prog(t, 6.0, 6.3);
  if (p <= 0) return;
  const sc = backOut(p, 2.2), n = nudge(50, f, 0.5), a = -0.06 + n.dr;
  for (let k = 2; k < 19; k += 3) { // torn-off pages flutter away
    const t0 = YEAR_T0 + k * (YEAR_T1 - YEAR_T0) / 19, tt = t - t0;
    if (tt <= 0 || tt > 0.7) continue;
    const x = CAL.x + (150 + k * 4) * tt, y = CAL.y + 10 - 260 * tt + 700 * tt * tt;
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(tt * (5 + k * 0.2));
    const page = [[-40, -32], [40, -34], [41, 36], [-39, 34]];
    cut(ctx, page, '#fffdf6', { sharp: true, shadow: 0.7, tex: [[P.grain, 1]] });
    ctx.font = MARKER(34);
    ctx.fillStyle = 'rgba(46,36,32,0.8)';
    ctx.textAlign = 'center';
    ctx.fillText(String(k), 0, 14);
    ctx.restore();
  }
  blit(SPR.calendar, CAL.x + n.dx, CAL.y + n.dy, { rot: a, sx: sc });
  ctx.save();
  ctx.translate(CAL.x + n.dx, CAL.y + n.dy);
  ctx.rotate(a);
  ctx.scale(sc, sc);
  ctx.font = MARKER(46);
  ctx.fillStyle = INK;
  ctx.textAlign = 'center';
  ctx.fillText(String(yearAt(t)), 0, 38);
  ctx.restore();
}

function drawWater(t, f) {
  for (const d of DROPS) {
    if (t < d.t0) continue;
    if (t < d.land) {
      const tt = t - d.t0;
      blit(SPR.drop, d.x0 + d.vx * tt, d.y0 + d.vy * tt + 0.5 * GRAVITY * tt * tt,
        { rot: Math.atan2(d.vy + GRAVITY * tt, d.vx) - Math.PI / 2, sx: 0.9 });
      continue;
    }
    const q = prog(t, d.land, d.land + 0.25);
    if (q >= 1) continue;
    ctx.fillStyle = `rgba(90,182,228,${1 - q})`;
    for (let k = -1; k <= 1; k++) {
      ctx.beginPath();
      ctx.arc(d.lx + k * 14 * q, GROUND - 6 - Math.sin(q * Math.PI) * (k ? 9 : 14), 2.4, 0, TAU);
      ctx.fill();
    }
  }
}

function drawCan(t, f) {
  if (t < 2.1 || t > 4.0) return;
  const pose = canPose(t), n = nudge(60, f, 0.5);
  const shake = t > 2.7 && t < 3.45 ? sgn(hash(61, f)) * 0.02 * jitterAmp : 0;
  blit(pick(SPR.can, 4, f), pose.x + n.dx, pose.y + n.dy, { rot: pose.a + shake + n.dr });
  const moving = t < 2.45 ? 1 : t > 3.7 ? -1 : 0;
  if (moving) {
    for (let k = 0; k < 3; k++) {
      const x = pose.x + moving * (118 + k * 6), y = pose.y - 30 + k * 26;
      pencil(ctx, [[x, y], [x + moving * 34, y + 1]], 3900 + k + (f % 3) * 3, { width: 2, amp: 0.6, passes: 1 });
    }
  }
}

function drawFallingAcorn(t, f) {
  const st = acornState(t);
  if (!st || st.under) return;
  drawAcorn(st, t, f);
  if (t > 1.15 && t < 1.58) {
    for (let k = -1; k <= 1; k++) {
      pencil(ctx, [[st.x + k * 10, st.y - 70 + Math.abs(k) * 8], [st.x + k * 10, st.y - 44]], 4000 + k + (f % 3) * 3, { width: 2, amp: 0.6, passes: 1 });
    }
  }
  const imp = prog(t, 1.6, 1.75);
  if (imp > 0 && imp < 1) {
    for (const s of [-1, 1]) {
      pencil(ctx, [[TREE_X + s * 28, 522], [TREE_X + s * 44, 514]], 4010 + s, { width: 2.2, amp: 0.4, passes: 1 });
      pencil(ctx, [[TREE_X + s * 22, 508], [TREE_X + s * 32, 494]], 4020 + s, { width: 2.2, amp: 0.4, passes: 1 });
    }
  }
}

function drawDirt(t) {
  if (t < 1.85 || t > 2.45) return;
  const r = rng(555);
  for (let i = 0; i < 12; i++) {
    const vx = sgn(r()) * 140, vy = -150 - r() * 170, sz = 3 + r() * 4, spin = sgn(r()) * 8, t0 = 1.86 + r() * 0.08, tt = t - t0;
    if (tt <= 0 || tt > 0.5) continue;
    const y = 506 + vy * tt + 700 * tt * tt;
    if (y > 530) continue;
    ctx.save();
    ctx.translate(TREE_X + vx * tt, y);
    ctx.rotate(spin * tt);
    ctx.fillStyle = i % 3 ? C.soilDark : C.soil;
    ctx.fillRect(-sz / 2, -sz / 2, sz, sz * 0.8);
    ctx.restore();
  }
}

function drawNote(x, y, s, alpha) {
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.translate(x, y);
  ctx.scale(s, s);
  ctx.fillStyle = INK;
  ctx.beginPath(); ctx.ellipse(0, 0, 4.6, 3.4, -0.4, 0, TAU); ctx.fill();
  ctx.strokeStyle = INK;
  ctx.lineWidth = 1.8;
  ctx.beginPath(); ctx.moveTo(4, -1); ctx.lineTo(4, -17); ctx.quadraticCurveTo(9, -13, 10, -8); ctx.stroke();
  ctx.restore();
}
function drawBird(t, f) {
  if (t < 8.4) return;
  const p = prog(t, 8.4, 9.0);
  let x = PERCH.x, y = PERCH.y - 22, pose = 2;
  if (p < 1) {
    [x, y] = bez([W + 60, 300], [1090, 170], [PERCH.x, PERCH.y - 22], easeOut(p));
    pose = f % 2;
  } else {
    y -= Math.sin(prog(t, 9.3, 9.45) * Math.PI) * 7;
  }
  const n = nudge(70, f, 0.4);
  blit(SPR.bird[pose], x + n.dx, y + n.dy, { rot: n.dr + (p < 1 ? -0.12 : 0) });
  for (let k = 0; k < 2; k++) {
    const q = prog(t, 9.15 + k * 0.3, 9.95 + k * 0.3);
    if (q > 0 && q < 1) drawNote(x - 26 - q * 24 - k * 8, y - 26 - q * 30, 0.9 + k * 0.2, 1 - q);
  }
}

const STARS = (() => {
  const xs = LEAVES.map(l => l.x), ys = LEAVES.map(l => l.y);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  return [[x0 - 34, y0 + 44], [x1 + 38, y0 + 62], [x0 + 46, y0 - 36], [x1 - 20, y1 - 6], [x0 - 18, y1 - 34], [(x0 + x1) / 2 + 84, y0 - 50]];
})();
function drawSparkles(t, f) {
  STARS.forEach(([x, y], k) => {
    const p = prog(t, 8.05 + k * 0.12, 8.3 + k * 0.12);
    if (p <= 0) return;
    const s = backOut(p, 2.5) * (0.85 + 0.15 * Math.sin(t * 9 + k * 2)), pts = [];
    for (let i = 0; i < 8; i++) { const a = i / 8 * TAU - Math.PI / 2, r = i % 2 ? 4.5 : 14; pts.push([x + Math.cos(a) * r * s, y + Math.sin(a) * r * s]); }
    cut(ctx, pts, C.yellow, { sharp: true, shadow: 0.6 });
    pencil(ctx, pts, 4100 + k * 3 + (f % 3), { closed: true, sharp: true, width: 1.5, amp: 0.4, passes: 1 });
  });
}

function drawCheck(x, y, p, seed) {
  const pts = [[x - 8, y - 1], [x - 2, y + 7], [x + 13, y - 15]];
  ctx.save();
  ctx.setLineDash([36 * p, 100]);
  pencil(ctx, pts, seed, { color: C.pencilRed, width: 3.2, amp: 0.5, sharp: true });
  ctx.restore();
}
function drawNotepad(t, f) {
  const p = prog(t, 0.45, 0.9);
  if (p <= 0) return;
  const e = backOut(p, 1.3), n = nudge(80, f, 0.4);
  const x = lerp(-260, 200, e) + n.dx, y = 330 + n.dy, a = lerp(-0.3, -0.06, e) + n.dr;
  blit(pick(SPR.notepad, 5, f), x, y, { rot: a });
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(a);
  STEPS.forEach((s, i) => {
    const wp = prog(t, s.write, s.write + 0.45), hl = wp * (1 - prog(t, s.check, s.check + 0.3));
    if (hl > 0) {
      const w = SPR.items[i].w - 6, y0 = ROW_Y(i) - 14;
      ctx.save();
      ctx.globalAlpha = hl;
      ctx.fillStyle = 'rgba(255,221,64,0.55)';
      ctx.fill(linePath([[-90, y0 - 9], [-90 + w * wp, y0 - 11], [-88 + w * wp, y0 + 10], [-91, y0 + 11]]));
      ctx.restore();
    }
    if (wp > 0) blit(SPR.items[i], -86, ROW_Y(i), { crop: wp });
    const cp = prog(t, s.check, s.check + 0.18);
    if (cp > 0) drawCheck(-121, ROW_Y(i) - 10, cp, 4200 + i * 5 + (f % 3));
  });
  ctx.restore();
}

const TILE_T = i => 0.12 + i * 0.075;
function drawTitle(t, f) {
  TILES.forEach((tile, i) => {
    const p = prog(t, TILE_T(i), TILE_T(i) + 0.22);
    if (p <= 0) return;
    const n = nudge(200 + i, f, 0.35);
    blit(SPR.tiles[i], tile.x + n.dx, tile.y + n.dy, { rot: tile.rot + n.dr + (1 - p) * 0.9, sx: backOut(p, 2.8) });
  });
}

function drawFrame(t) {
  const f = Math.round(t * FPS);
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.drawImage(BG, 0, 0);
  ctx.setTransform(stage.width / W, 0, 0, stage.height / H, 0, 0);
  drawClouds(t, f);
  drawSun(t, f);
  drawSunbeams(t, f);
  drawUnderground(t, f);
  blit(SPR.grass, 0, 0);
  drawTree(t);
  drawMound(t, f);
  drawSprout(t, f);
  drawLeaves(t, f);
  drawApples(t, f);
  drawCalendar(t, f);
  drawWater(t, f);
  drawCan(t, f);
  drawFallingAcorn(t, f);
  drawDirt(t);
  drawBird(t, f);
  drawSparkles(t, f);
  drawNotepad(t, f);
  drawTitle(t, f);
}

// ---------------------------------------------------------------- sound
// A small band made of oscillators and noise: a Karplus-Strong ukulele, a glockenspiel,
// a plucked bass, a shaker, and a box of cartoon sound effects.
function hz(name) {
  const m = /^([A-G])(#|b)?(\d)$/.exec(name);
  const semis = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 }[m[1]] + (m[2] === '#' ? 1 : m[2] === 'b' ? -1 : 0) + (+m[3] + 1) * 12;
  return 440 * 2 ** ((semis - 69) / 12);
}

function makeMix(ac, dest) {
  const out = ac.createGain();
  const comp = ac.createDynamicsCompressor();
  comp.threshold.value = -16;
  comp.knee.value = 10;
  comp.ratio.value = 4;
  comp.attack.value = 0.004;
  comp.release.value = 0.18;
  out.connect(comp).connect(dest);
  const len = Math.floor(ac.sampleRate * 1.6), ir = ac.createBuffer(2, len, ac.sampleRate);
  for (let c = 0; c < 2; c++) {
    const d = ir.getChannelData(c);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / len) ** 2.8;
  }
  const verb = ac.createConvolver();
  verb.buffer = ir;
  const wet = ac.createGain();
  wet.gain.value = 0.22;
  verb.connect(wet).connect(out);
  const bus = (level, send) => {
    const g = ac.createGain();
    g.gain.value = level;
    g.connect(out);
    const s = ac.createGain();
    s.gain.value = send;
    g.connect(s).connect(verb);
    return g;
  };
  return { out, music: bus(0.5, 0.18), bells: bus(0.5, 0.35), fx: bus(0.8, 0.2) };
}

const ksCache = new Map();
function ksString(ac, f) { // a plucked string, simulated once per pitch and reused
  const key = `${ac.sampleRate}:${f.toFixed(2)}`;
  if (ksCache.has(key)) return ksCache.get(key);
  const sr = ac.sampleRate, N = Math.max(2, Math.floor(sr / f - 0.5)), len = Math.floor(sr * 1.6);
  const buf = ac.createBuffer(1, len, sr), d = buf.getChannelData(0), ring = new Float32Array(N);
  let prev = 0;
  for (let i = 0; i < N; i++) { prev = prev * 0.45 + (Math.random() * 2 - 1) * 0.55; ring[i] = prev; }
  for (let i = 0, j = 0; i < len; i++) {
    const a = ring[j], b = ring[(j + 1) % N];
    d[i] = a;
    ring[j] = (a + b) * 0.5 * 0.9965;
    j = (j + 1) % N;
  }
  const s = { buf, rate: f / (sr / (N + 0.5)) };
  ksCache.set(key, s);
  return s;
}
function pluck(ac, dest, when, f, vel, tone) {
  const { buf, rate } = ksString(ac, f);
  const src = ac.createBufferSource();
  src.buffer = buf;
  src.playbackRate.value = rate;
  const lp = ac.createBiquadFilter();
  lp.type = 'lowpass';
  lp.frequency.value = tone;
  lp.Q.value = 0.5;
  const g = ac.createGain();
  g.gain.setValueAtTime(0.0001, when);
  g.gain.linearRampToValueAtTime(0.34 * vel, when + 0.004);
  g.gain.setTargetAtTime(0, when + 0.8, 0.16);
  src.connect(lp).connect(g).connect(dest);
  src.start(when);
  src.stop(when + 1.6);
}
const UKE = { C: ['G4', 'C4', 'E4', 'C5'], Am: ['A4', 'C4', 'E4', 'A4'], F: ['A4', 'C4', 'F4', 'A4'], G: ['G4', 'D4', 'G4', 'B4'] };
function strum(ac, dest, when, chord, down, vel) {
  const notes = down ? UKE[chord] : [...UKE[chord]].reverse();
  notes.forEach((n, i) => pluck(ac, dest, when + i * 0.014, hz(n), vel * (down ? 1 : 0.7), down ? 3400 : 2400));
}

function glock(ac, dest, when, f, vel = 1) {
  for (const [ratio, amp, dec] of [[1, 1, 1.3], [2.756, 0.32, 0.45], [5.404, 0.12, 0.2], [8.933, 0.05, 0.1]]) {
    if (f * ratio > 15000) continue;
    const o = ac.createOscillator(), g = ac.createGain();
    o.frequency.value = f * ratio;
    g.gain.setValueAtTime(0, when);
    g.gain.linearRampToValueAtTime(0.22 * amp * vel, when + 0.003);
    g.gain.exponentialRampToValueAtTime(0.0001, when + dec);
    o.connect(g).connect(dest);
    o.start(when);
    o.stop(when + dec + 0.05);
  }
}

function bass(ac, dest, when, f, vel = 1) {
  const o = ac.createOscillator(), o2 = ac.createOscillator(), h = ac.createGain(), lp = ac.createBiquadFilter(), g = ac.createGain();
  o.type = 'triangle';
  o.frequency.value = f;
  o2.frequency.value = f * 2;
  h.gain.value = 0.25;
  lp.type = 'lowpass';
  lp.frequency.setValueAtTime(1000, when);
  lp.frequency.exponentialRampToValueAtTime(240, when + 0.3);
  g.gain.setValueAtTime(0, when);
  g.gain.linearRampToValueAtTime(0.55 * vel, when + 0.008);
  g.gain.exponentialRampToValueAtTime(0.001, when + 0.6);
  o.connect(lp);
  o2.connect(h).connect(lp);
  lp.connect(g).connect(dest);
  for (const x of [o, o2]) { x.start(when); x.stop(when + 0.65); }
}

let noiseCache = null;
function noise(ac, dest, when, dur, o = {}) {
  if (!noiseCache || noiseCache.sampleRate !== ac.sampleRate) {
    noiseCache = ac.createBuffer(1, ac.sampleRate * 2, ac.sampleRate);
    const d = noiseCache.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  }
  const src = ac.createBufferSource(), flt = ac.createBiquadFilter(), g = ac.createGain();
  src.buffer = noiseCache;
  src.loop = true;
  flt.type = o.type || 'bandpass';
  flt.Q.value = o.q ?? 1;
  flt.frequency.setValueAtTime(o.f0 ?? 2000, when);
  if (o.f1) flt.frequency.exponentialRampToValueAtTime(o.f1, when + dur);
  const attack = o.attack ?? 0.004;
  g.gain.setValueAtTime(0, when);
  g.gain.linearRampToValueAtTime(o.gain ?? 0.3, when + attack);
  g.gain.exponentialRampToValueAtTime(0.0006, when + Math.max(dur, attack + 0.01));
  src.connect(flt).connect(g);
  if (o.flutter) { // amplitude wobble: pencil strokes, trickling water, wing beats
    const lfo = ac.createOscillator(), depth = ac.createGain(), vca = ac.createGain();
    lfo.type = o.flutterType || 'sine';
    lfo.frequency.value = o.flutter;
    depth.gain.value = 0.5;
    vca.gain.value = 0.5;
    lfo.connect(depth).connect(vca.gain);
    g.connect(vca).connect(dest);
    lfo.start(when);
    lfo.stop(when + dur + 0.05);
  } else g.connect(dest);
  src.start(when, Math.random());
  src.stop(when + dur + 0.05);
}

function tone(ac, dest, when, dur, o) {
  const osc = ac.createOscillator(), g = ac.createGain();
  osc.type = o.type || 'sine';
  osc.frequency.setValueAtTime(o.f0, when);
  if (o.f1) osc.frequency.exponentialRampToValueAtTime(o.f1, when + (o.glide ?? dur));
  if (o.vib) {
    const lfo = ac.createOscillator(), lg = ac.createGain();
    lfo.frequency.value = o.vibRate ?? 6;
    lg.gain.value = o.vib;
    lfo.connect(lg).connect(osc.frequency);
    lfo.start(when);
    lfo.stop(when + dur + 0.05);
  }
  const attack = o.attack ?? 0.005;
  g.gain.setValueAtTime(0, when);
  g.gain.linearRampToValueAtTime(o.gain ?? 0.3, when + attack);
  g.gain.exponentialRampToValueAtTime(0.0006, when + dur);
  osc.connect(g).connect(dest);
  osc.start(when);
  osc.stop(when + dur + 0.05);
}

// cartoon sound effects
const sfx = {
  pop: (ac, d, t, f, gain = 0.32) => {
    tone(ac, d, t, 0.1, { f0: f * 0.55, f1: f * 1.3, glide: 0.035, gain });
    noise(ac, d, t, 0.018, { type: 'highpass', f0: 3000, gain: gain * 0.25 });
  },
  paper: (ac, d, t) => noise(ac, d, t, 0.04, { f0: 2400, q: 0.8, gain: 0.16 }),
  whoosh: (ac, d, t, dur, f0, f1, gain) => noise(ac, d, t, dur, { f0, f1, q: 1.3, gain, attack: dur * 0.45 }),
  whistle: (ac, d, t, dur, f0, f1, gain = 0.16) => tone(ac, d, t, dur, { type: 'triangle', f0, f1, gain, attack: 0.03, vib: f0 * 0.012, vibRate: 11 }),
  tok: (ac, d, t, f, gain = 0.4) => {
    tone(ac, d, t, 0.08, { f0: f, f1: f * 0.9, gain, attack: 0.002 });
    noise(ac, d, t, 0.025, { f0: f * 2.5, q: 2, gain: gain * 0.3 });
  },
  thump: (ac, d, t) => tone(ac, d, t, 0.2, { f0: 160, f1: 55, gain: 0.5, attack: 0.003 }),
  dig: (ac, d, t, f) => noise(ac, d, t, 0.075, { f0: f, q: 1.6, gain: 0.22, attack: 0.01 }),
  pencil: (ac, d, t, dur, gain) => noise(ac, d, t, dur, { f0: 3600, q: 1.8, gain, attack: 0.02, flutter: 15, flutterType: 'triangle' }),
  bloop: (ac, d, t, f) => tone(ac, d, t, 0.11, { f0: f, f1: f * 2.3, glide: 0.05, gain: 0.3, attack: 0.003 }),
  trickle: (ac, d, t, dur) => noise(ac, d, t, dur, { f0: 5200, q: 2.5, gain: 0.05, attack: 0.1, flutter: 23 }),
  clink: (ac, d, t) => { for (const [f, g] of [[2100, 0.1], [5390, 0.05], [8900, 0.02]]) tone(ac, d, t, 0.3, { f0: f, gain: g, attack: 0.002 }); },
  crack: (ac, d, t) => { for (let i = 0; i < 4; i++) noise(ac, d, t + i * 0.022 + Math.random() * 0.01, 0.014, { type: 'highpass', f0: 2500, gain: 0.2 }); },
  chirp: (ac, d, t) => {
    tone(ac, d, t, 0.07, { f0: 2900, f1: 4600, glide: 0.05, gain: 0.14, attack: 0.004 });
    tone(ac, d, t + 0.075, 0.08, { f0: 4300, f1: 3000, glide: 0.06, gain: 0.12, attack: 0.004 });
  },
  flutter: (ac, d, t, dur) => noise(ac, d, t, dur, { type: 'lowpass', f0: 900, gain: 0.08, attack: 0.05, flutter: FPS / 2, flutterType: 'triangle' }),
  tick: (ac, d, t) => {
    noise(ac, d, t, 0.014, { type: 'highpass', f0: 4200, gain: 0.12 });
    tone(ac, d, t, 0.025, { f0: 2600, gain: 0.03, attack: 0.001 });
  },
  shimmer: (ac, d, t, dur, gain) => noise(ac, d, t, dur, { type: 'highpass', f0: 6500, gain, attack: 0.02 }),
};

// The score: every cue is tied to the same numbers the pictures use.
function scheduleScore(ac, mix, T) {
  const { music, bells, fx } = mix, at = s => T + s;
  // ukulele, island strum (D, D U, U D U) over C, Am, F, G, then "ta-DA" on C
  const PATTERN = [[0, 1, 1], [0.5, 1, 0.75], [0.75, 0, 0.6], [1.25, 0, 0.6], [1.5, 1, 0.75], [1.75, 0, 0.6]];
  ['C', 'Am', 'F', 'G'].forEach((ch, bar) => PATTERN.forEach(([b, down, v]) => strum(ac, music, at(bar * 2 + b), ch, !!down, v)));
  strum(ac, music, at(8), 'C', true, 1.3);
  strum(ac, music, at(9), 'C', true, 0.55);
  [['C3', 'G2'], ['A2', 'E2'], ['F2', 'C3'], ['G2', 'B2'], ['C3', null]].forEach(([a, b], bar) => {
    bass(ac, music, at(bar * 2), hz(a));
    if (b) bass(ac, music, at(bar * 2 + 1), hz(b), 0.8);
  });
  for (let i = 0; i < 16; i++) noise(ac, music, at(i * 0.5 + 0.25), 0.05, { type: 'highpass', f0: 6500, gain: i % 2 ? 0.07 : 0.045 });

  // the title letters slap down, each one a note
  const TUNE = ['C5', 'E5', 'G5', 'A5', 'G5', 'C6', 'A5', 'G5', 'E5', 'D5', 'E5', 'G5', 'A5', 'C6'];
  TILES.forEach((_, i) => { sfx.paper(ac, fx, at(TILE_T(i))); glock(ac, bells, at(TILE_T(i)), hz(TUNE[i % TUNE.length]), 0.45); });
  sfx.whoosh(ac, fx, at(0.45), 0.4, 600, 2600, 0.14);
  STEPS.forEach(s => { sfx.pencil(ac, fx, at(s.write), 0.45, 0.07); sfx.pencil(ac, fx, at(s.check), 0.2, 0.1); });

  // 1. plant a seed
  sfx.whistle(ac, fx, at(1.1), 0.5, 1500, 380);
  sfx.tok(ac, fx, at(1.6), 720);
  sfx.tok(ac, fx, at(1.78), 860, 0.22);
  sfx.thump(ac, fx, at(1.86));
  [1.88, 1.97, 2.07].forEach((s, i) => sfx.dig(ac, fx, at(s), [1300, 1700, 1100][i]));

  // 2. water it
  sfx.whoosh(ac, fx, at(2.1), 0.35, 400, 1800, 0.12);
  sfx.clink(ac, fx, at(2.5));
  sfx.trickle(ac, fx, at(2.7), 0.8);
  const DROP_NOTES = ['A4', 'C5', 'E5', 'G4', 'A4', 'E5', 'C5', 'A5'];
  DROPS.filter((_, i) => i % 2 === 0).forEach(d => sfx.bloop(ac, fx, at(d.land), hz(DROP_NOTES[d.note])));
  sfx.whoosh(ac, fx, at(3.65), 0.35, 1800, 500, 0.12);
  glock(ac, bells, at(3.2), hz('E6'), 0.6);

  // 3. add sunshine
  sfx.pop(ac, fx, at(4.0), 520, 0.4);
  ['F5', 'A5', 'C6', 'F6', 'A6'].forEach((n, i) => glock(ac, bells, at(4.03 + i * 0.07), hz(n), 0.8));
  sfx.shimmer(ac, fx, at(4.0), 0.9, 0.04);
  tone(ac, fx, at(4.45), 0.14, { type: 'triangle', f0: 620, f1: 1250, gain: 0.14 });
  sfx.crack(ac, fx, at(4.7));
  sfx.whistle(ac, fx, at(4.85), 0.45, 300, 900, 0.1);
  sfx.pop(ac, fx, at(5.3), 900, 0.4);
  sfx.pop(ac, fx, at(5.58), hz('C6'), 0.3);
  sfx.pop(ac, fx, at(5.68), hz('F6'), 0.3);

  // 4. be patient: the years tick by while the tree grows
  sfx.paper(ac, fx, at(6.0));
  tone(ac, fx, at(6.0), 1.9, { type: 'triangle', f0: 196, f1: 784, gain: 0.07, attack: 0.4, vib: 5, vibRate: 7 });
  sfx.whoosh(ac, fx, at(6.0), 1.9, 300, 3200, 0.07);
  for (let y = 2; y <= 20; y++) sfx.tick(ac, fx, at(YEAR_T0 + (y - 1) / 19.999 * (YEAR_T1 - YEAR_T0)));
  const PENTA = ['G4', 'B4', 'D5', 'E5', 'G5', 'A5', 'B5', 'D6', 'E6', 'G6', 'A6', 'B6', 'D7'];
  LEAF_POPS.forEach((s, i) => sfx.pop(ac, fx, at(s), hz(PENTA[Math.min(i, PENTA.length - 1)]), 0.26));

  // 5. ta-da!
  ['C6', 'E6', 'G6', 'C7'].forEach((n, i) => glock(ac, bells, at(8.0 + i * 0.06), hz(n), 0.9));
  sfx.shimmer(ac, fx, at(8.0), 1.5, 0.05);
  APPLES.forEach((a, i) => sfx.pop(ac, fx, at(a.t), hz(['E5', 'G5', 'C6', 'E6', 'G6'][i]), 0.25));
  sfx.flutter(ac, fx, at(8.4), 0.6);
  [9.1, 9.3, 9.55].forEach(s => sfx.chirp(ac, fx, at(s)));
  glock(ac, bells, at(9.25), hz('G6'), 0.5);
  mix.out.gain.setValueAtTime(1, at(9.5));
  mix.out.gain.linearRampToValueAtTime(0.0001, at(10.35));
}

// ---------------------------------------------------------------- playback
const playBtn = document.getElementById('play');
const againBtn = document.getElementById('again');
const soundBtn = document.getElementById('sound');
let ac = null, master = null, mix = null, audioClock = false;
let startAt = 0, clockStart = 0, playing = false, lastFrame = -1, raf = 0, shownT = DURATION;
let muted = false;
try { muted = localStorage.getItem('grow-a-tree:muted') === '1'; } catch (e) { /* storage blocked */ }

function now() {
  if (audioClock) return ac.currentTime - startAt - (ac.outputLatency || 0);
  return performance.now() / 1000 - clockStart;
}

async function play() {
  if (!ac) {
    const AC = window.AudioContext || window.webkitAudioContext;
    try {
      ac = new AC({ latencyHint: 'interactive' });
      master = ac.createGain();
      master.gain.value = muted ? 0 : 1;
      master.connect(ac.destination);
    } catch (e) { ac = null; }
  }
  if (ac && ac.state !== 'running') { try { await ac.resume(); } catch (e) { /* stays silent */ } }
  audioClock = !!ac && ac.state === 'running';
  if (mix) {
    const old = mix;
    old.out.gain.cancelScheduledValues(ac.currentTime);
    old.out.gain.setTargetAtTime(0, ac.currentTime, 0.02);
    setTimeout(() => old.out.disconnect(), 400);
    mix = null;
  }
  if (audioClock) {
    mix = makeMix(ac, master);
    startAt = ac.currentTime + 0.15;
    scheduleScore(ac, mix, startAt);
  }
  clockStart = performance.now() / 1000 + 0.15;
  playing = true;
  lastFrame = -1;
  setUI();
  cancelAnimationFrame(raf);
  raf = requestAnimationFrame(tick);
}

function tick() {
  const t = now(), f = Math.floor(clamp(t, 0, DURATION) * FPS);
  if (f !== lastFrame) { lastFrame = f; shownT = f / FPS; drawFrame(shownT); }
  if (t < DURATION + 0.1) raf = requestAnimationFrame(tick);
  else { playing = false; shownT = DURATION; drawFrame(DURATION); setUI(); }
}

function setUI() {
  playBtn.hidden = playing;
  playBtn.querySelector('.label').textContent = shownT >= DURATION && lastFrame > 0 ? 'Watch again' : 'Play';
  againBtn.textContent = playing ? 'Start over' : 'Play';
  soundBtn.setAttribute('aria-pressed', String(!muted));
  soundBtn.textContent = muted ? 'Sound: off' : 'Sound: on';
}

function toggleSound() {
  muted = !muted;
  try { localStorage.setItem('grow-a-tree:muted', muted ? '1' : '0'); } catch (e) { /* storage blocked */ }
  if (master) master.gain.setTargetAtTime(muted ? 0 : 1, ac.currentTime, 0.03);
  setUI();
}

// Size the drawing surface to the screen, then redraw every piece at that resolution.
function layout() {
  const rect = stage.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = Math.round(clamp(rect.width * dpr, 640, 2560)), h = Math.round(w * 9 / 16);
  if (BG && w === stage.width) return;
  stage.width = w;
  stage.height = h;
  S = w / W;
  buildSprites();
}

async function boot() {
  jitterAmp = matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 1;
  const faces = ['700 32px Caveat', '32px "Permanent Marker"', '32px "Abril Fatface"'];
  try {
    await Promise.race([Promise.all(faces.map(face => document.fonts.load(face))), new Promise(r => setTimeout(r, 2500))]);
  } catch (e) { /* fall back to system faces */ }
  layout();
  drawFrame(shownT);
  setUI();
  let timer = 0;
  window.addEventListener('resize', () => {
    clearTimeout(timer);
    timer = setTimeout(() => { layout(); drawFrame(shownT); }, 150);
  });
  playBtn.addEventListener('click', play);
  againBtn.addEventListener('click', play);
  soundBtn.addEventListener('click', toggleSound);
  stage.addEventListener('click', () => { if (!playing) play(); });
  document.body.classList.add('ready');
}

// For scrubbing from the console: growATree.seek(4.2)
window.growATree = { play, seek(t) { shownT = clamp(+t || 0, 0, DURATION); drawFrame(shownT); } };
boot();
})();
