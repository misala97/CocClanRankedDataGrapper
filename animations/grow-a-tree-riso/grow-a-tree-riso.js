/* How to Grow a Tree, printed in riso: the same ten-second story in four riso inks.
   Pure JavaScript. Canvas 2D paints how much of each ink goes where, a WebGL shader
   turns that into halftone dots, grain and wobbly registration, and Web Audio plays
   a lo-fi beat. No images, audio files or libraries. */
(() => {
'use strict';

// ---------------------------------------------------------------- constants
const W = 1280, H = 720, DURATION = 10, FPS = 12, TAU = Math.PI * 2;
const PRINT = { x0: 30, y0: 30, x1: 1250, y1: 640 };  // riso drums can't print to the edge
const GROUND = 492;
const TREE_X = 830;
// Inks, as [pink, aqua, yellow, blue] everywhere below. Colours are the real riso inks.
const INK_RGB = [[1.0, 0.282, 0.690], [0.369, 0.784, 0.898], [1.0, 0.910, 0.0], [0.239, 0.333, 0.533]];
const PAPER_RGB = [0.953, 0.933, 0.886];
// Printing order (lightest first) and the moment each drum passes over the sheet.
const PASS = [0.333, 0.667, 0.0, 1.0];     // pink, aqua, yellow, blue
const PASS_LEN = 0.25;

// Ink recipes: how much of each ink a thing gets.
const K = [0, 0, 0, 1];
const PAPER = [0, 0, 0, 0];
const INK = {
  skyTop: [0, 0.55, 0, 0], skyLow: [0, 0.08, 0, 0],
  hill1: [0, 0.5, 0.85, 0], hill2: [0.08, 0.85, 1, 0], grass: [0, 1, 1, 0],
  soil: [0.5, 0.35, 0.9, 0], subsoil: [0.75, 0.62, 1, 0],
  sun: [0.22, 0, 1, 0], trunk: [0.82, 0.55, 0.92, 0], sprout: [0, 0.6, 1, 0],
  nut: [0.35, 0, 1, 0], cap: [0.75, 0.5, 0.9, 0], can: [1, 0, 0, 0], water: [0, 1, 0, 0],
  apple: [1, 0, 0.72, 0], bird: [1, 0, 0, 0], beak: [0.55, 0, 1, 0], worm: [0.6, 0, 0.12, 0],
  star: [0.15, 0, 1, 0],
};
const mixInk = (a, b, t) => a.map((v, i) => v + (b[i] - v) * t);

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
function area(pts) {
  let a = 0;
  for (let i = 0; i < pts.length; i++) { const p = pts[i], q = pts[(i + 1) % pts.length]; a += p[0] * q[1] - q[0] * p[1]; }
  return a / 2;
}
function linePath(pts, closed = true, path = new Path2D()) {
  path.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) path.lineTo(pts[i][0], pts[i][1]);
  if (closed) path.closePath();
  return path;
}
function smoothPath(pts, closed = true, path = new Path2D()) {
  const n = pts.length, mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  if (n < 3) return linePath(pts, closed, path);
  if (closed) {
    const m0 = mid(pts[n - 1], pts[0]);
    path.moveTo(m0[0], m0[1]);
    for (let i = 0; i < n; i++) { const m = mid(pts[i], pts[(i + 1) % n]); path.quadraticCurveTo(pts[i][0], pts[i][1], m[0], m[1]); }
    path.closePath();
  } else {
    path.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < n - 1; i++) { const m = mid(pts[i], pts[i + 1]); path.quadraticCurveTo(pts[i][0], pts[i][1], m[0], m[1]); }
    path.lineTo(pts[n - 1][0], pts[n - 1][1]);
  }
  return path;
}
const circle = (x, y, r) => { const p = new Path2D(); p.arc(x, y, r, 0, TAU); return p; };
const rect = (x, y, w, h) => { const p = new Path2D(); p.rect(x, y, w, h); return p; };

// ---------------------------------------------------------------- the press
// Two density plates the size of the output: plate A holds pink, aqua and yellow in its
// red, green and blue channels, plate B holds federal blue. Drawing a shape normally
// knocks out whatever inks were under it, exactly like a riso separation; 'over'
// overprints instead, so the inks mix.
const stage = document.getElementById('stage');
const out = stage.getContext('2d', { alpha: false });
const glCanvas = document.createElement('canvas');
let S = 1, jitterAmp = 1;
const plateA = document.createElement('canvas'), plateB = document.createElement('canvas');
const pa = plateA.getContext('2d', { alpha: false }), pb = plateB.getContext('2d', { alpha: false });
const PLATES = [pa, pb];
const byte = v => Math.round(clamp(v) * 255);
const colA = d => `rgb(${byte(d[0])},${byte(d[1])},${byte(d[2])})`;
const colB = d => `rgb(${byte(d[3])},${byte(d[3])},${byte(d[3])})`;
const usesA = d => d[0] > 0 || d[1] > 0 || d[2] > 0;

function each(fn) { fn(pa, colA, 0); fn(pb, colB, 1); }
const save = () => each(c => c.save());
const restore = () => each(c => c.restore());
const translate = (x, y) => each(c => c.translate(x, y));
const rotate = a => each(c => c.rotate(a));
const scale = (x, y = x) => each(c => c.scale(x, y));
const alpha = a => each(c => { c.globalAlpha = a; });

function fill(path, d, over = false) {
  each((c, col, i) => {
    if (over && !(i ? d[3] > 0 : usesA(d))) return;
    c.globalCompositeOperation = over ? 'lighten' : 'source-over';
    c.fillStyle = col(d);
    c.fill(path);
  });
}
// A gradient fill; stops are [offset, inks]. make(ctx) returns an empty gradient.
function fillGrad(path, make, stops, over = false) {
  each((c, col, i) => {
    if (over && !stops.some(([, d]) => (i ? d[3] > 0 : usesA(d)))) return;
    const g = make(c);
    for (const [o, d] of stops) g.addColorStop(o, col(d));
    c.globalCompositeOperation = over ? 'lighten' : 'source-over';
    c.fillStyle = g;
    c.fill(path);
  });
}
function stroke(path, d, width, over = true, o = {}) {
  each((c, col, i) => {
    if (over && !(i ? d[3] > 0 : usesA(d))) return;
    c.save();
    c.globalCompositeOperation = over ? 'lighten' : 'source-over';
    c.strokeStyle = col(d);
    c.lineWidth = width;
    c.lineCap = c.lineJoin = 'round';
    if (o.dash) { c.setLineDash(o.dash); c.lineDashOffset = o.offset || 0; }
    c.stroke(path);
    c.restore();
  });
}
function text(str, x, y, font, d, over = true, o = {}) {
  each((c, col, i) => {
    if (over && !(i ? d[3] > 0 : usesA(d))) return;
    c.save();
    c.globalCompositeOperation = over ? 'lighten' : 'source-over';
    c.font = font;
    c.textAlign = o.align || 'left';
    if (o.outline) { c.strokeStyle = col(d); c.lineWidth = o.outline; c.lineJoin = 'round'; c.strokeText(str, x, y); }
    else { c.fillStyle = col(d); c.fillText(str, x, y); }
    c.restore();
  });
}
// A hand-drawn line in federal blue: redrawn with a new wobble every frame.
function sketch(pts, seed, o = {}) {
  const r = rng(seed), amp = (o.amp ?? 0.9) * jitterAmp;
  const q = pts.map(([x, y]) => [x + sgn(r()) * amp, y + sgn(r()) * amp]);
  stroke(o.sharp ? linePath(q, !!o.closed) : smoothPath(q, !!o.closed), o.ink || K, o.width ?? 2.2, o.over ?? true, o);
}
const DISPLAY = s => `${s}px "Bowlby One", "Arial Black", Impact, sans-serif`;
const MONO = s => `500 ${s}px "DM Mono", "Courier New", monospace`;

// ---------------------------------------------------------------- the shader
const VERT = 'attribute vec2 p; varying vec2 v; void main() { v = p * 0.5 + 0.5; gl_Position = vec4(p, 0.0, 1.0); }';
const FRAG = `
precision highp float;
uniform sampler2D uA, uB;
uniform vec2 uRes;
uniform vec2 uOff[4];
uniform vec4 uOn;
uniform float uCell, uSeed;
uniform vec3 uInk[4];
uniform vec3 uPaper;
varying vec2 v;
float hash(vec2 p) {
  vec3 q = fract(vec3(p.xyx) * 0.1031);
  q += dot(q, q.yzx + 33.33);
  return fract((q.x + q.y) * q.z);
}
float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p), u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}
// Euclidean dot screen: 1 at a dot's centre, 0 between dots.
float spot(vec2 px, float a) {
  float c = cos(a), s = sin(a);
  vec2 f = fract(vec2(c * px.x - s * px.y, s * px.x + c * px.y) / uCell) - 0.5;
  return 1.0 - 2.0 * dot(f, f);
}
float ink(float d, vec2 px, float a, float k) {
  if (d < 0.004) return 0.0;
  float grain = (hash(px + uSeed * 17.0 + k * 91.0) - 0.5) * 1.4 * d * (1.0 - d);
  float th = 1.0 - d * 1.12;
  float cov = smoothstep(th - 0.07, th + 0.07, spot(px, a) + grain);
  float tex = 0.84 + 0.16 * noise(px * 0.045 + vec2(uSeed * 3.7, k * 11.0));
  float speck = step(0.994, hash(floor(px / 2.0) + uSeed * 5.0 + k * 13.0));
  return cov * tex * (1.0 - 0.85 * speck);
}
float plate(float wipe) { return step(1.0 - v.y, wipe); }
void main() {
  vec2 px = gl_FragCoord.xy, t = 1.0 / uRes;
  float dp = texture2D(uA, v - uOff[0] * t).r;
  float da = texture2D(uA, v - uOff[1] * t).g;
  float dy = texture2D(uA, v - uOff[2] * t).b;
  float db = texture2D(uB, v - uOff[3] * t).r;
  vec3 col = uPaper * (0.975 + 0.025 * noise(px * 0.5)) * (0.985 + 0.015 * noise(px * 0.02));
  col *= mix(vec3(1.0), uInk[2], ink(dy, px - uOff[2], 0.0, 2.0) * plate(uOn.z));
  col *= mix(vec3(1.0), uInk[0], ink(dp, px - uOff[0], 0.2618, 0.0) * plate(uOn.x));
  col *= mix(vec3(1.0), uInk[1], ink(da, px - uOff[1], 1.309, 1.0) * plate(uOn.y));
  col *= mix(vec3(1.0), uInk[3], ink(db, px - uOff[3], 0.7854, 3.0) * plate(uOn.w));
  gl_FragColor = vec4(col, 1.0);
}`;

let gl = null, U = {}, tex = [];
function initGL() {
  try {
    gl = glCanvas.getContext('webgl', { preserveDrawingBuffer: true, antialias: false, alpha: false, premultipliedAlpha: false });
  } catch (e) { gl = null; }
  if (!gl) return false;
  const shader = (type, src) => {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  };
  const program = gl.createProgram();
  gl.attachShader(program, shader(gl.VERTEX_SHADER, VERT));
  gl.attachShader(program, shader(gl.FRAGMENT_SHADER, FRAG));
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
  gl.useProgram(program);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(program, 'p');
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  for (const n of ['uA', 'uB', 'uRes', 'uOff', 'uOn', 'uCell', 'uSeed', 'uInk', 'uPaper']) U[n] = gl.getUniformLocation(program, n);
  tex = [0, 1].map(unit => {
    const t = gl.createTexture();
    gl.activeTexture(gl.TEXTURE0 + unit);
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    return t;
  });
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
  gl.uniform1i(U.uA, 0);
  gl.uniform1i(U.uB, 1);
  gl.uniform3fv(U.uInk, INK_RGB.flat());
  gl.uniform3fv(U.uPaper, PAPER_RGB);
  return true;
}

// Without WebGL: mix the inks on the CPU at a smaller size, flat tints instead of dots.
function composeFallback(on) {
  const w = plateA.width, h = plateA.height;
  const a = pa.getImageData(0, 0, w, h).data, b = pb.getImageData(0, 0, w, h).data;
  const img = out.createImageData(w, h), o = img.data;
  for (let i = 0, p = 0; i < a.length; i += 4, p++) {
    const y = p / w | 0, d = [a[i] / 255, a[i + 1] / 255, a[i + 2] / 255, b[i] / 255];
    let r = PAPER_RGB[0], g = PAPER_RGB[1], bl = PAPER_RGB[2];
    for (let k = 0; k < 4; k++) {
      const c = d[k] * (y / h <= on[k] ? 1 : 0), ink = INK_RGB[k];
      r *= 1 - c * (1 - ink[0]); g *= 1 - c * (1 - ink[1]); bl *= 1 - c * (1 - ink[2]);
    }
    o[i] = r * 255; o[i + 1] = g * 255; o[i + 2] = bl * 255; o[i + 3] = 255;
  }
  out.putImageData(img, 0, 0);
}

// ---------------------------------------------------------------- the story, as data
// Shared by the pictures and the sound so the two stay in step.
const STEPS = [
  { n: '01', text: 'PLANT A SEED', t: 1.0 },
  { n: '02', text: 'WATER IT', t: 2.0 },
  { n: '03', text: 'ADD SUNSHINE', t: 4.0 },
  { n: '04', text: 'BE PATIENT', t: 6.0 },
  { n: '05', text: 'TA-DA!', t: 8.0 },
];
const SUN = { x: 1128, y: 168, from: 560 };
const CAN = { x: 1058, y: 300, tilt: -0.6 };
const CAN_TIP = [-161, -72], CAN_DIR = [-100, -86];
const STAMP = { x: 1124, y: 404 };
const ACORN_REST = 556;
const TRUNK_BASE = [TREE_X, 500];

function buildTree() {
  const r = rng(20260925), segs = [];
  const DUR = [0.5, 0.42, 0.38, 0.34, 0.3], SPREAD = [0, 0.72, 0.6, 0.52, 0.46];
  function grow(p0, ang, len, w0, depth, t0) {
    const p1 = [p0[0] + Math.cos(ang) * len, p0[1] + Math.sin(ang) * len];
    const bend = sgn(r()) * 0.1 * len;
    const c = [(p0[0] + p1[0]) / 2 - Math.sin(ang) * bend, (p0[1] + p1[1]) / 2 + Math.cos(ang) * bend];
    const seg = { p0, c, p1, w0, w1: w0 * 0.68, depth, t0, t1: t0 + DUR[depth], ang };
    segs.push(seg);
    if (depth === 4) return;
    const kids = depth === 0 ? 3 : r() < 0.3 ? 3 : 2;
    for (let k = 0; k < kids; k++) {
      const side = kids === 2 ? (k ? 1 : -1) : k - 1;
      const a = clamp(ang + side * SPREAD[depth + 1] * (0.85 + r() * 0.3) + sgn(r()) * 0.1, -Math.PI + 0.3, -0.3);
      grow(p1, a, len * (0.7 + r() * 0.1), seg.w1, depth + 1, seg.t0 + DUR[depth] * 0.75);
    }
  }
  grow(TRUNK_BASE, -Math.PI / 2, 104, 26, 0, 6.0);
  return segs;
}
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
      const u = (k + 1) / (kids + 1), side = k % 2 ? 1 : -1;
      grow(bez(p0, c, p1, u), clamp(ang + side * (0.9 + r() * 0.5), 0.15, Math.PI - 0.15), len * (0.55 + r() * 0.2), w0 * 0.6, depth + 1, t0 + dur * u * 0.9 + 0.2);
    }
  }
  grow([TREE_X, ACORN_REST + 24], Math.PI / 2 - 0.08, 54, 7, 0, 4.85);
  grow([TREE_X - 6, ACORN_REST + 18], Math.PI / 2 + 0.95, 66, 5, 1, 5.6);
  grow([TREE_X + 6, ACORN_REST + 18], Math.PI / 2 - 0.95, 70, 5, 1, 5.7);
  return segs;
}
const TREE = buildTree(), ROOTS = buildRoots();

// Canopy: blobs at the ends of the upper branches, each popping in as its branch finishes.
const LEAVES = (() => {
  const r = rng(4242), out = [];
  for (const s of TREE) {
    if (s.depth < 1) continue;
    const t = s.t1 + 0.04 + r() * 0.12;
    if (s.depth === 1) { out.push({ x: s.p1[0], y: s.p1[1] + 6, rad: 56 + r() * 10, t: t - 0.25, tone: 0 }); continue; }
    out.push({ x: s.p1[0], y: s.p1[1], rad: [0, 0, 42, 35, 29][s.depth] + sgn(r()) * 5, t, tone: s.depth - 1 + (r() < 0.3 ? 1 : 0) });
    if (s.depth === 4) out.push({ x: s.p1[0] + Math.cos(s.ang) * 14, y: s.p1[1] + Math.sin(s.ang) * 14, rad: 24 + r() * 5, t: t + 0.08, tone: 4 });
  }
  return out.sort((a, b) => a.tone - b.tone || a.y - b.y);
})();
const APPLES = (() => {
  const cand = LEAVES.filter(l => l.tone >= 3);
  const cx = cand.reduce((s, l) => s + l.x, 0) / cand.length, cy = cand.reduce((s, l) => s + l.y, 0) / cand.length;
  const chosen = [cand.reduce((b, l) => (Math.hypot(l.x - cx, l.y - cy) < Math.hypot(b.x - cx, b.y - cy) ? l : b))];
  while (chosen.length < 6) {
    let best = null, bd = -1;
    for (const l of cand) {
      const d = Math.min(...chosen.map(c => Math.hypot(l.x - c.x, l.y - c.y)));
      if (d > bd) { bd = d; best = l; }
    }
    chosen.push(best);
  }
  return chosen.map((l, i) => ({ x: l.x + 4, y: l.y + 8, t: 8.15 + i * 0.11 }));
})();
const PERCH = (() => { const top = LEAVES.reduce((b, l) => (l.y - l.rad < b.y - b.rad ? l : b)); return { x: top.x, y: top.y - top.rad * 0.8 }; })();
const LEAF_POPS = (() => {
  const out = [];
  for (const t of LEAVES.map(l => l.t).sort((a, b) => a - b)) if (!out.length || t - out[out.length - 1] > 0.085) out.push(t);
  return out;
})();

// Water: two drops leave the rose every 90 ms while the can is tipped.
const GRAVITY = 1500;
function canPose(t) {
  let x = CAN.x;
  if (t < 2.5) x = lerp(1460, CAN.x, backOut(prog(t, 2.1, 2.5), 1.4));
  if (t > 3.65) x = lerp(CAN.x, 1480, easeIn(prog(t, 3.65, 4.0)));
  return { x, y: CAN.y, a: CAN.tilt * (easeInOut(prog(t, 2.5, 2.7)) - easeInOut(prog(t, 3.45, 3.65))) };
}
const DROPS = (() => {
  const r = rng(99), out = [], c = Math.cos(CAN.tilt), s = Math.sin(CAN.tilt), L = Math.hypot(CAN_DIR[0], CAN_DIR[1]);
  const tip = [CAN.x + CAN_TIP[0] * c - CAN_TIP[1] * s, CAN.y + CAN_TIP[0] * s + CAN_TIP[1] * c];
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

const YEAR_T0 = 6.1, YEAR_T1 = 7.9;
const yearAt = t => (t < YEAR_T0 ? 1 : Math.min(20, 1 + Math.floor(prog(t, YEAR_T0, YEAR_T1) * 19.999)));
const stepAt = t => { let i = -1; STEPS.forEach((s, k) => { if (t >= s.t) i = k; }); return i; };

// ---------------------------------------------------------------- painting the plates
const clip = path => each(c => c.clip(path));
// Stop-motion life: each frame every piece sits a hair differently.
function nudge(id, f, amp = 0.6) {
  const k = jitterAmp * amp;
  return { dx: sgn(hash(id, f, 1)) * k, dy: sgn(hash(id, f, 2)) * k, dr: sgn(hash(id, f, 3)) * 0.005 * k };
}
const boil = f => (jitterAmp ? f % 3 : 0);

// Fixed shapes, built once.
const SHAPES = (() => {
  const r = rng(5);
  const hill = (x0, x1, base, peak, pw) => {
    const pts = [];
    for (let x = x0; x <= x1; x += 8) pts.push([x, base - peak * Math.pow(Math.sin(Math.PI * (x - x0) / (x1 - x0)), pw)]);
    return linePath(pts.concat([[x1, 560], [x0, 560]]));
  };
  const grass = [[PRINT.x0, 505]];
  for (let x = PRINT.x0; x < PRINT.x1;) {
    const w = 9 + r() * 7;
    grass.push([x, 497 + sgn(r()) * 2], [x + w / 2, 484 - r() * (r() < 0.15 ? 12 : 6)]);
    x += w;
  }
  grass.push([PRINT.x1, 497], [PRINT.x1, 512], [PRINT.x0, 512]);
  const sub = [[PRINT.x0, PRINT.y1]];
  for (let x = PRINT.x0; x <= PRINT.x1; x += 10) sub.push([x, 592 + 7 * Math.sin(x * 0.012) + 3 * Math.sin(x * 0.041)]);
  sub.push([PRINT.x1, PRINT.y1]);
  const pebbles = [];
  const pr = rng(61);
  for (let i = 0; i < 30; i++) {
    const x = PRINT.x0 + 20 + pr() * (PRINT.x1 - PRINT.x0 - 40), y = 522 + pr() * 108, a = pr() * TAU;
    const rx = 4 + pr() * 6, ry = 3 + pr() * 4;
    if (Math.abs(x - TREE_X) < 150 || (x > 930 && x < 1070 && y > 590)) continue;
    pebbles.push(polar(0, 0, rx, ry, 12, u => 1 + 0.08 * Math.sin(u * 3 + i)).map(([px, py]) => [x + px * Math.cos(a) - py * Math.sin(a), y + px * Math.sin(a) + py * Math.cos(a)]));
  }
  const nut = [];
  for (let i = 0; i < 36; i++) {
    const th = i / 36 * TAU, up = Math.cos(th) > 0;
    nut.push([17 * Math.sin(th) * (up ? 1 : 1 - 0.22 * Math.cos(th) ** 2), up ? -14 * Math.cos(th) : -27 * Math.cos(th)]);
  }
  const cap = [];
  for (let i = 0; i <= 16; i++) { const a = Math.PI + i / 16 * Math.PI; cap.push([Math.cos(a) * 21, -7 + Math.sin(a) * 19]); }
  for (let i = 1; i < 12; i++) { const u = i / 12; cap.push([21 - 42 * u, -7 + 5 * Math.sin(Math.PI * u)]); }
  const cloud = (rx, ry, seed) => {
    const cr = rng(seed), ph = cr() * TAU;
    return polar(0, 0, rx, ry, 48, a => 0.8 + 0.22 * Math.abs(Math.sin(a * 2.5 + ph))).map(([x, y]) => [x, Math.min(y, ry * 0.42)]);
  };
  const leaf = seed => { const lr = rng(seed), p1 = lr() * TAU, p2 = lr() * TAU; return smoothPath(polar(0, 0, 40, 38, 22, a => 1 + 0.07 * Math.sin(a * 3 + p1) + 0.04 * Math.sin(a * 5 + p2))); };
  const coty = [];
  for (let i = 0; i <= 10; i++) { const u = i / 10; coty.push([u * 30, -Math.sin(Math.PI * u) * 9 * (1 - 0.25 * u)]); }
  for (let i = 9; i > 0; i--) { const u = i / 10; coty.push([u * 30, Math.sin(Math.PI * u) * 8 * (1 - 0.25 * u)]); }
  const drop = [];
  for (let i = 0; i < 20; i++) { const t = i / 20 * TAU; drop.push([7 * Math.sin(t) * Math.sin(t / 2), -10 * Math.cos(t) + 2]); }
  return {
    hill1: hill(PRINT.x0, 910, 540, 132, 0.8), hill2: hill(560, PRINT.x1, 540, 106, 0.9),
    grass: linePath(grass), subsoil: linePath(sub), pebbles, nut, cap, coty, drop,
    clouds: [cloud(78, 34, 101), cloud(58, 26, 102)], leaves: [0, 1, 2, 3, 4, 5].map(k => leaf(1200 + k)),
  };
})();

function drawSky(t) {
  const warm = easeInOut(prog(t, 4.0, 5.2)) * 0.8;
  fillGrad(rect(PRINT.x0, PRINT.y0, PRINT.x1 - PRINT.x0, 540 - PRINT.y0), c => c.createLinearGradient(0, PRINT.y0, 0, 540), [
    [0, INK.skyTop], [0.72, [warm * 0.12, 0.2, 0, 0]], [1, [warm * 0.4, INK.skyLow[1], warm * 0.2, 0]],
  ]);
}

function drawSun(t, f) {
  if (t < 4.0) return;
  const y = lerp(SUN.from, SUN.y, easeOut(prog(t, 4.0, 4.8))), x = SUN.x, seed = 500 + boil(f);
  const glow = easeOut(prog(t, 4.2, 5.0));
  fillGrad(circle(x, y, 168), c => c.createRadialGradient(x, y, 55, x, y, 168), [[0, [0.46 * glow, 0, 0.3 * glow, 0]], [1, [0, 0, 0, 0]]], true);
  save();
  translate(x, y);
  rotate((t - 4) * 0.35);
  for (let i = 0; i < 12; i++) {
    const a = i / 12 * TAU, r0 = 74, r1 = i % 2 ? 94 : 104;
    const ray = new Path2D();
    ray.moveTo(Math.cos(a) * r0, Math.sin(a) * r0);
    ray.lineTo(Math.cos(a) * r1, Math.sin(a) * r1);
    stroke(ray, [0.55, 0, 1, 0], 11, false);
  }
  restore();
  fill(circle(x, y, 62), INK.sun);
  save();
  translate(x, y);
  fill(new Path2D('M-35 6a8 5 0 1 0 16 0a8 5 0 1 0-16 0M19 6a8 5 0 1 0 16 0a8 5 0 1 0-16 0'), [0.85, 0, 0, 0], true);
  const wink = t > 9.25 && t < 9.75;
  for (const ex of [-18, 18]) {
    if (wink && ex > 0) { sketch([[ex - 7, -5], [ex, -11], [ex + 7, -5]], seed + 1, { width: 3.2 }); continue; }
    const eye = new Path2D();
    eye.ellipse(ex, -7, 4.6, 6.2, 0, 0, TAU);
    fill(eye, K, true);
    fill(circle(ex + 1.6, -9.6, 1.7), PAPER);
  }
  sketch([[-17, 12], [-8, 22], [0, 25], [8, 22], [17, 12]], seed + 3, { width: 3.2 });
  restore();
}

function drawSunbeams(t) {
  const a = prog(t, 4.45, 4.7) * (1 - prog(t, 5.55, 5.9));
  if (a <= 0) return;
  const tx = TREE_X + 12, ty = 468, th = Math.atan2(ty - SUN.y, tx - SUN.x), nx = -Math.sin(th), ny = Math.cos(th);
  for (let k = -1; k <= 1; k++) {
    const s0 = [SUN.x + Math.cos(th) * 116 + nx * k * 26, SUN.y + Math.sin(th) * 116 + ny * k * 26];
    const s1 = [tx + nx * k * 14, ty + ny * k * 14];
    const c = [(s0[0] + s1[0]) / 2 + nx * 30, (s0[1] + s1[1]) / 2 + ny * 30];
    const path = new Path2D();
    path.moveTo(s0[0], s0[1]);
    path.quadraticCurveTo(c[0], c[1], s1[0], s1[1]);
    stroke(path, [0.7 * a, 0, a, 0], 5, true, { dash: [14, 13], offset: -Math.round(t * FPS) / FPS * 110 });
  }
}

function drawClouds(t, f) {
  [[520, 158, 0, 6], [1186, 300, 1, -4]].forEach(([x, y, i, v], k) => {
    const n = nudge(10 + k, f);
    save();
    translate(x + v * t + n.dx, y + n.dy);
    const pts = SHAPES.clouds[i], path = smoothPath(pts);
    fill(path, PAPER);
    fillGrad(path, c => c.createLinearGradient(0, -20, 0, 30), [[0, PAPER], [1, [0, 0.42, 0, 0]]], true);
    sketch(pts, 600 + k * 7 + boil(f), { closed: true, width: 1.8, amp: 0.5 });
    restore();
  });
}

function drawLand(f) {
  fill(SHAPES.hill1, INK.hill1);
  save();
  clip(SHAPES.hill1);
  for (let x = PRINT.x0 - 200; x < 960; x += 26) {
    const s = new Path2D();
    s.moveTo(x, 560); s.lineTo(x + 180, 330); s.lineTo(x + 192, 330); s.lineTo(x + 12, 560); s.closePath();
    fill(s, [0, 0.66, 1, 0]);
  }
  restore();
  fill(SHAPES.hill2, INK.hill2);
  fill(rect(PRINT.x0, 500, PRINT.x1 - PRINT.x0, PRINT.y1 - 500), INK.soil);
  fill(SHAPES.subsoil, INK.subsoil);
  SHAPES.pebbles.forEach((pts, i) => {
    fill(smoothPath(pts), PAPER);
    sketch(pts, 700 + i * 3 + boil(f), { closed: true, width: 1.4, amp: 0.4 });
  });
}

function drawGrass(f) {
  fill(SHAPES.grass, INK.grass);
  const r = rng(71);
  for (let i = 0; i < 46; i++) {
    const x = PRINT.x0 + 12 + r() * (PRINT.x1 - PRINT.x0 - 24);
    sketch([[x, 509], [x + sgn(r()) * 2, 498], [x + sgn(r()) * 3, 488 - r() * 5]], 800 + i * 3 + boil(f), { width: 1.6, amp: 0.5 });
  }
}

// ---- branches and roots: a federal-blue silhouette with the body knocked out inside it
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
function drawBranches(segs, t, o) {
  const outline = new Path2D(), body = new Path2D();
  let any = false;
  const ring = (path, [x, y], r) => { path.moveTo(x + r, y); path.arc(x, y, r, 0, TAU); };
  for (const s of segs) {
    const p = o.progress(s, t);
    if (p < 0.002) continue;
    any = true;
    const g = o.grow, tip = bez(s.p0, s.c, s.p1, p), wt = lerp(s.w0, s.w1, p) * g;
    linePath(segOutline(s, p, g, o.extra), true, outline);
    linePath(segOutline(s, p, g, 0), true, body);
    if (s.depth > 0 || o.roots) { ring(outline, s.p0, (s.w0 * g + o.extra) / 2); ring(body, s.p0, s.w0 * g / 2); }
    ring(outline, tip, (wt + o.extra) / 2);
    ring(body, tip, wt / 2);
  }
  if (!any) return;
  fill(outline, K);
  fill(body, o.ink);
}
const trunkProgress = t => 0.55 * easeOut(prog(t, 5.25, 5.85)) + 0.45 * easeInOut(prog(t, 6.0, 6.5));
const treeProgress = (s, t) => (s.depth === 0 ? trunkProgress(t) : easeOut(prog(t, s.t0, s.t1)));

function drawTree(t) {
  if (t < 5.25) return;
  drawBranches(TREE, t, { progress: treeProgress, grow: lerp(0.2, 1, easeInOut(prog(t, 6.0, 7.8))), extra: 4, ink: mixInk(INK.sprout, INK.trunk, prog(t, 6.05, 6.9)) });
}
function drawRoots(t) {
  drawBranches(ROOTS, t, { progress: (s, tt) => easeOut(prog(tt, s.t0, s.t1)), grow: lerp(0.7, 1.1, prog(t, 6, 8)), extra: 3, ink: PAPER, roots: true });
  const sp = easeOut(prog(t, 4.85, 5.3));
  if (sp > 0) {
    const y0 = ACORN_REST - 20, y1 = lerp(y0, 500, sp), w = lerp(5, 15, easeInOut(prog(t, 6.0, 7.8)));
    const stem = { p0: [TREE_X, y0], c: [TREE_X - 3, (y0 + y1) / 2], p1: [TREE_X, y1], w0: w * 0.9, w1: w, depth: 1 };
    drawBranches([stem], t, { progress: () => 1, grow: 1, extra: 3.4, ink: mixInk(INK.sprout, PAPER, prog(t, 6.0, 7.0)), roots: true });
  }
}

// ---- the acorn: its face tells the story
function acornState(t) {
  if (t < 1.1) return null;
  if (t < 1.6) {
    const p = prog(t, 1.1, 1.6);
    return { x: TREE_X + Math.sin(p * Math.PI) * 26, y: lerp(-50, 468, easeIn(p)), rot: (1 - p) * 3 * Math.PI, sx: 1, sy: 1, under: false };
  }
  if (t < 1.78) {
    const u = prog(t, 1.6, 1.78), squash = u < 0.15;
    return { x: TREE_X, y: 468 - 104 * u * (1 - u), rot: Math.sin(u * Math.PI) * 0.35, sx: squash ? 1.18 : 1, sy: squash ? 0.82 : 1, under: false };
  }
  if (t < 1.85) return { x: TREE_X, y: 468, rot: 0, sx: 1, sy: 1, under: false };
  const p = easeInOut(prog(t, 1.85, 2.15));
  return { x: TREE_X, y: lerp(468, ACORN_REST, p), rot: Math.sin(p * Math.PI) * 0.25, sx: 1, sy: 1, under: true };
}
function drawAcorn(st, t, f) {
  const n = nudge(30, f, 0.4), seed = 900 + boil(f) * 17;
  save();
  translate(st.x + n.dx, st.y + n.dy + 27 * (1 - st.sy));
  rotate(st.rot + n.dr);
  scale(st.sx, st.sy);
  fill(smoothPath(SHAPES.nut), INK.nut);
  fill(new Path2D('M-12 -2q-3 8 2 15q-5-8-2-15z'), PAPER);
  sketch(SHAPES.nut, seed, { closed: true, width: 2 });
  sketch([[0, 25], [0.5, 31]], seed + 1, { width: 2.6 });
  fill(smoothPath(SHAPES.cap), INK.cap);
  for (const y of [-20, -14, -8]) sketch([[-17 + Math.abs(y + 14) * 0.2, y], [0, y - 2], [17 - Math.abs(y + 14) * 0.2, y]], seed + y, { width: 1.3, amp: 0.4 });
  sketch(SHAPES.cap, seed + 2, { closed: true, width: 2 });
  sketch([[0, -25], [2, -30], [6, -34]], seed + 3, { width: 4 });
  const mood = t < 1.85 ? 'wow' : t < 4.45 ? 'sleep' : t < 5.4 ? 'awake' : 'happy';
  fill(new Path2D('M-14.5 11a3.6 2.3 0 1 0 7.2 0a3.6 2.3 0 1 0-7.2 0M7.3 11a3.6 2.3 0 1 0 7.2 0a3.6 2.3 0 1 0-7.2 0'), [0.9, 0, 0, 0], true);
  for (const ex of [-6.5, 6.5]) {
    if (mood === 'sleep') sketch([[ex - 3.5, 4], [ex, 6.5], [ex + 3.5, 4]], seed + ex, { width: 1.7, amp: 0.3 });
    else if (mood === 'happy') sketch([[ex - 3.5, 6], [ex, 2.5], [ex + 3.5, 6]], seed + ex, { width: 1.8, amp: 0.3 });
    else fill(circle(ex, 5, mood === 'awake' ? 2.8 : 2.3), K, true);
  }
  if (mood === 'happy') sketch([[-4, 12], [0, 15], [4, 12]], seed + 9, { width: 1.7, amp: 0.3 });
  else if (mood === 'sleep') sketch([[-2, 13], [2, 13]], seed + 9, { width: 1.6, amp: 0.3 });
  else stroke(circle(0, 13, mood === 'wow' ? 2.8 : 2.2), K, 1.6);
  if (t > 4.7) sketch([[-15, 17], [-8, 13], [-3, 19], [3, 13], [9, 18], [15, 14]], seed + 11, { width: 1.7, sharp: true, amp: 0.4 });
  restore();
}

function drawWorm(t, f) {
  const happy = prog(t, 2.95, 3.1) * (1 - prog(t, 3.9, 4.1));
  const amp = (2.2 + happy * 3) * (jitterAmp ? 1 : 0.4), speed = 5 + happy * 7, pts = [];
  for (let i = 0; i < 9; i++) pts.push([972 + i * 8, 612 + Math.sin(t * speed - i * 0.9) * amp]);
  const path = smoothPath(pts, false);
  stroke(path, K, 15, false);
  stroke(path, INK.worm, 11, false);
  const [hx, hy] = pts[0];
  fill(circle(hx - 1, hy - 2, 1.7), K);
  sketch([[hx - 4, hy + 1.5], [hx - 1.5, hy + 3.5], [hx + 1, hy + 2]], 950 + boil(f), { width: 1.3, amp: 0.2 });
  const hp = prog(t, 3.15, 3.35), hf = 1 - prog(t, 4.2, 4.5);
  if (hp > 0 && hf > 0) drawHeart(964, 590 - hp * 8, 9 * backOut(hp, 2.5), f);
}
function drawHeart(x, y, s, f) {
  const pts = [];
  for (let i = 0; i < 24; i++) {
    const a = i / 24 * TAU;
    pts.push([x + s * 0.8 * Math.sin(a) ** 3, y - s * (0.8 * Math.cos(a) - 0.3 * Math.cos(2 * a) - 0.12 * Math.cos(3 * a) - 0.05 * Math.cos(4 * a))]);
  }
  fill(smoothPath(pts), [1, 0, 0.35, 0]);
  sketch(pts, 960 + boil(f), { closed: true, width: 1.5, amp: 0.3 });
}

function drawUnderground(t, f) {
  const landed = DROPS.filter(d => d.land <= t).length;
  if (landed) {
    const w = easeOut(landed / DROPS.length) * (1 - 0.35 * prog(t, 6, 8.5));
    const pts = polar(TREE_X, 534, 26 + 66 * w, 16 + 34 * w, 26, a => 1 + 0.08 * Math.sin(a * 4 + 1) + 0.05 * Math.sin(a * 7));
    fill(smoothPath(pts), [0, 0.5 * (1 - 0.4 * prog(t, 6, 8.5)), 0, 0], true);
  }
  for (const d of DROPS) {
    for (let k = 0; k < 2; k++) {
      const p = prog(t, d.land + k * 0.1, d.land + k * 0.1 + 0.45);
      if (p > 0 && p < 1) fill(circle(lerp(d.lx, TREE_X + (k ? 7 : -7), easeIn(p)), lerp(GROUND + 22, ACORN_REST - 12, p), 3.4), INK.water);
    }
  }
  drawRoots(t);
  const st = acornState(t);
  if (st && st.under) drawAcorn(st, t, f);
  if (t < 4.45) {
    for (let k = 0; k < 5; k++) {
      const p = prog(t, 2.3 + k * 0.45, 3.3 + k * 0.45);
      if (p > 0 && p < 1) text('z', TREE_X + 18 + p * 40, ACORN_REST - 10 - p * 30, DISPLAY(14 + p * 10), PAPER, false);
    }
  }
  const ex = prog(t, 4.45, 4.6) * (1 - prog(t, 5.0, 5.2));
  if (ex > 0) {
    save();
    translate(TREE_X + 28, ACORN_REST - 30);
    rotate(0.15);
    scale(backOut(ex, 3));
    text('!', 0, 0, DISPLAY(30), [0.2, 0, 1, 0], false);
    text('!', 0, 0, DISPLAY(30), K, true, { outline: 2.5 });
    restore();
  }
  drawWorm(t, f);
}

// ---- above the ground
function drawMound(t, f) {
  const p = prog(t, 1.95, 2.2);
  if (p <= 0) return;
  save();
  translate(TREE_X, 492);
  scale(1, backOut(p, 2));
  const arc = [];
  for (let i = 0; i <= 16; i++) { const a = Math.PI + i / 16 * Math.PI; arc.push([Math.cos(a) * 42, Math.sin(a) * 17 + 2]); }
  fill(smoothPath(arc.concat([[40, 8], [0, 10], [-40, 8]])), INK.subsoil);
  sketch(arc, 1300 + boil(f), { width: 2 });
  restore();
}

function drawSprout(t, f) {
  const s = backOut(prog(t, 5.55, 5.85), 2.2) * (1 - easeIn(prog(t, 6.15, 6.5)));
  if (s > 0.02) {
    const tip = bez(TREE[0].p0, TREE[0].c, TREE[0].p1, trunkProgress(t)), spread = lerp(1.25, 0.42, prog(t, 5.55, 5.85));
    for (const side of [1, -1]) {
      save();
      translate(tip[0] + side, tip[1] + 2);
      rotate(side > 0 ? -spread : Math.PI + spread);
      scale(s, side > 0 ? s : -s);
      fill(smoothPath(SHAPES.coty), [0, 0.45, 1, 0]);
      sketch(SHAPES.coty, 1400 + side + boil(f) * 3, { closed: true, width: 1.5, amp: 0.3 });
      sketch([[2, 0], [16, -1], [26, 0]], 1403 + side, { width: 1.1, amp: 0.2 });
      restore();
    }
  }
  const b = prog(t, 5.3, 5.55);
  if (b > 0 && b < 1) {
    for (let k = 0; k < 4; k++) {
      const a = -Math.PI / 2 + (k - 1.5) * 0.55, r0 = 24 + b * 10, r1 = r0 + 12;
      sketch([[TREE_X + Math.cos(a) * r0, 470 + Math.sin(a) * r0], [TREE_X + Math.cos(a) * r1, 470 + Math.sin(a) * r1]], 1410 + k + boil(f) * 7, { width: 2.6, amp: 0.4 });
    }
  }
}

const TONES = [[0.3, 1, 1, 0.18], [0.12, 0.92, 1, 0], [0.04, 0.74, 1, 0], [0, 0.56, 1, 0], [0, 0.4, 1, 0]];
function drawLeaves(t, f) {
  LEAVES.forEach((l, i) => {
    const p = prog(t, l.t, l.t + 0.3), s = backOut(p, 2.6) * l.rad / 40;
    if (s < 0.02) return;
    const n = nudge(100 + i, f, 0.5), sway = t > 8 ? Math.sin(t * 2.2 + l.x * 0.03) * 1.2 * jitterAmp : 0, d = TONES[l.tone];
    save();
    translate(l.x + n.dx + sway, l.y + n.dy);
    rotate(n.dr + (1 - p) * 0.8);
    scale(s);
    fillGrad(SHAPES.leaves[i % 6], c => c.createRadialGradient(-16, -18, 2, -4, -4, 50), [
      [0, [d[0] * 0.4, Math.max(0, d[1] - 0.26), d[2], 0]], [1, [d[0] + 0.1, Math.min(1, d[1] + 0.14), d[2], d[3]]],
    ]);
    if (i % 3 === 0) {
      const arc = [];
      for (let k = 0; k <= 5; k++) { const a = Math.PI * (0.15 + 0.7 * k / 5); arc.push([6 + Math.cos(a) * 9, 10 + Math.sin(a) * 9]); }
      sketch(arc, 1500 + i + boil(f) * 5, { width: 2.2 / Math.max(0.5, s), amp: 0.4 });
    }
    restore();
  });
}

function drawApples(t, f) {
  APPLES.forEach((a, i) => {
    const p = prog(t, a.t, a.t + 0.25), s = backOut(p, 3);
    if (s < 0.02) return;
    const n = nudge(300 + i, f, 0.4), seed = 1600 + i * 5 + boil(f);
    save();
    translate(a.x + n.dx, a.y + n.dy + Math.sin(t * 3 + i) * 0.8);
    rotate(n.dr + (1 - p));
    scale(s);
    fill(circle(0, 0, 13.5), INK.apple);
    fill(new Path2D('M-8 -3q-2 6 1 9q-4-4-1-9z'), PAPER);
    sketch(polar(0, 0, 13.5, 13.5, 16), seed, { closed: true, width: 1.7, amp: 0.35 });
    sketch([[0, -11], [1, -16], [3, -20]], seed + 1, { width: 2.4, amp: 0.3 });
    const leaf = [[2, -16], [8, -22], [15, -21], [10, -15]];
    fill(smoothPath(leaf), [0, 0.6, 1, 0]);
    sketch(leaf, seed + 2, { closed: true, width: 1.2, amp: 0.3 });
    restore();
  });
}

// A round sticker that counts the years while the tree grows.
function drawStamp(t) {
  const p = prog(t, 6.0, 6.22);
  if (p <= 0) return;
  save();
  translate(STAMP.x, STAMP.y);
  rotate(-0.18);
  scale(1 + (1 - easeOut(p)) * 0.7);
  fill(circle(0, 0, 50), [0.12, 0, 1, 0]);
  stroke(circle(0, 0, 44), K, 3.4);
  stroke(circle(0, 0, 37), K, 1.4);
  text('YEAR', 0, -14, MONO(13), K, true, { align: 'center' });
  text(String(yearAt(t)), 0, 27, DISPLAY(36), K, true, { align: 'center' });
  restore();
}

function drawWater(t) {
  for (const d of DROPS) {
    if (t < d.t0) continue;
    if (t < d.land) {
      const tt = t - d.t0;
      save();
      translate(d.x0 + d.vx * tt, d.y0 + d.vy * tt + 0.5 * GRAVITY * tt * tt);
      rotate(Math.atan2(d.vy + GRAVITY * tt, d.vx) - Math.PI / 2);
      scale(0.95);
      fill(smoothPath(SHAPES.drop), INK.water);
      fill(circle(-2.5, 4, 1.6), PAPER);
      restore();
      continue;
    }
    const q = prog(t, d.land, d.land + 0.25);
    if (q >= 1) continue;
    for (let k = -1; k <= 1; k++) fill(circle(d.lx + k * 14 * q, GROUND - 8 - Math.sin(q * Math.PI) * (k ? 9 : 14), 2.6 * (1 - q * 0.5)), INK.water);
  }
}

function drawCan(t, f) {
  if (t < 2.1 || t > 4.0) return;
  const pose = canPose(t), n = nudge(60, f, 0.5), seed = 1700 + boil(f) * 13;
  const shake = t > 2.7 && t < 3.45 ? sgn(hash(61, f)) * 0.02 * jitterAmp : 0;
  save();
  translate(pose.x + n.dx, pose.y + n.dy);
  rotate(pose.a + shake + n.dr);
  const handle = smoothPath([[8, -50], [30, -104], [78, -92], [86, -30], [62, 2]], false);
  stroke(handle, K, 15, false);
  stroke(handle, INK.can, 10.5, false);
  const base = [-50, 24], tip = [-150, -62], L = Math.hypot(CAN_DIR[0], CAN_DIR[1]), nn = [-CAN_DIR[1] / L, CAN_DIR[0] / L];
  const spout = [[base[0] + nn[0] * 11, base[1] + nn[1] * 11], [tip[0] + nn[0] * 5, tip[1] + nn[1] * 5],
    [tip[0] - nn[0] * 5, tip[1] - nn[1] * 5], [base[0] - nn[0] * 11, base[1] - nn[1] * 11]];
  fill(linePath(spout), INK.can);
  sketch(spout, seed, { closed: true, sharp: true, width: 1.9 });
  const ang = Math.atan2(CAN_DIR[1], CAN_DIR[0]), c = Math.cos(ang), s = Math.sin(ang);
  const rose = [[0, -6], [12, -13], [15, 0], [12, 13], [0, 6]].map(([x, y]) => [tip[0] + x * c - y * s, tip[1] + x * s + y * c]);
  fill(linePath(rose), [0.3, 0, 1, 0]);
  sketch(rose, seed + 1, { closed: true, sharp: true, width: 1.7 });
  const bodyPts = [[-56, -50], [56, -50], [63, 50], [-63, 50]], body = linePath(bodyPts);
  fill(body, INK.can);
  save();
  clip(body);
  for (let row = 0, y = -38; y < 50; y += 15, row++) for (let x = -60 + (row % 2) * 8; x < 66; x += 16) fill(circle(x, y, 2.8), PAPER);
  fill(rect(-80, 2, 160, 24), [0, 0, 1, 0], true);
  restore();
  text('H2O', 0, 22, DISPLAY(18), PAPER, false, { align: 'center' });
  sketch(bodyPts, seed + 2, { closed: true, sharp: true, width: 2.1 });
  const rim = new Path2D(), hole = new Path2D();
  rim.ellipse(0, -50, 57, 9, 0, 0, TAU);
  hole.ellipse(0, -50, 45, 5, 0, 0, TAU);
  fill(rim, [1, 1, 0, 0]);
  fill(hole, [1, 1, 0, 0.8]);
  stroke(rim, K, 2);
  restore();
  const moving = t < 2.45 ? 1 : t > 3.7 ? -1 : 0;
  if (moving) {
    for (let k = 0; k < 3; k++) {
      const x = pose.x + moving * (118 + k * 6), y = pose.y - 30 + k * 26;
      sketch([[x, y], [x + moving * 34, y + 1]], seed + 5 + k, { width: 2.2, amp: 0.6 });
    }
  }
}

function drawFallingAcorn(t, f) {
  const st = acornState(t);
  if (!st || st.under) return;
  drawAcorn(st, t, f);
  if (t > 1.15 && t < 1.58) {
    for (let k = -1; k <= 1; k++) sketch([[st.x + k * 10, st.y - 70 + Math.abs(k) * 8], [st.x + k * 10, st.y - 44]], 1800 + k + boil(f) * 3, { width: 2.2, amp: 0.6 });
  }
  const imp = prog(t, 1.6, 1.75);
  if (imp > 0 && imp < 1) {
    for (const s of [-1, 1]) {
      sketch([[TREE_X + s * 28, 490], [TREE_X + s * 44, 482]], 1810 + s, { width: 2.4, amp: 0.4 });
      sketch([[TREE_X + s * 22, 476], [TREE_X + s * 32, 462]], 1820 + s, { width: 2.4, amp: 0.4 });
    }
  }
}

function drawDirt(t) {
  if (t < 1.85 || t > 2.45) return;
  const r = rng(555);
  for (let i = 0; i < 12; i++) {
    const vx = sgn(r()) * 140, vy = -150 - r() * 170, sz = 3 + r() * 4, spin = sgn(r()) * 8, t0 = 1.86 + r() * 0.08, tt = t - t0;
    if (tt <= 0 || tt > 0.5) continue;
    const y = 474 + vy * tt + 700 * tt * tt;
    if (y > 498) continue;
    save();
    translate(TREE_X + vx * tt, y);
    rotate(spin * tt);
    fill(rect(-sz / 2, -sz / 2, sz, sz * 0.8), i % 3 ? INK.subsoil : INK.soil);
    restore();
  }
}

function drawNote(x, y, s) {
  save();
  translate(x, y);
  scale(s);
  const head = new Path2D(), stem = new Path2D();
  head.ellipse(0, 0, 4.6, 3.4, -0.4, 0, TAU);
  fill(head, K, true);
  stem.moveTo(4, -1);
  stem.lineTo(4, -17);
  stem.quadraticCurveTo(9, -13, 10, -8);
  stroke(stem, K, 1.9);
  restore();
}
function drawBird(t, f) {
  if (t < 8.4) return;
  const p = prog(t, 8.4, 9.0);
  let x = PERCH.x, y = PERCH.y - 22, pose = 2;
  if (p < 1) { [x, y] = bez([W + 60, 300], [1090, 170], [PERCH.x, PERCH.y - 22], easeOut(p)); pose = f % 2; }
  else y -= Math.sin(prog(t, 9.3, 9.45) * Math.PI) * 7;
  const n = nudge(70, f, 0.4), seed = 1900 + boil(f) * 11;
  save();
  translate(x + n.dx, y + n.dy);
  rotate(n.dr + (p < 1 ? -0.12 : 0));
  const tail = [[14, -4], [34, -14], [36, -8], [31, 3]];
  fill(linePath(tail), [1, 1, 0, 0]);
  sketch(tail, seed, { closed: true, sharp: true, width: 1.6 });
  const bodyPts = polar(0, 0, 20, 16, 24, a => 1 + 0.06 * Math.cos(a)), body = smoothPath(bodyPts);
  fill(body, INK.bird);
  save();
  clip(body);
  fill(smoothPath(polar(-6, 9, 14, 10, 16)), [0, 0, 1, 0], true);
  restore();
  sketch(bodyPts, seed + 1, { closed: true, width: 1.8 });
  const wing = pose === 0 ? [[-2, -6], [6, -30], [16, -34], [14, -8]] : pose === 1 ? [[-2, -2], [4, 22], [14, 26], [14, 0]] : [[-6, -2], [8, -8], [21, 0], [8, 8]];
  fill(smoothPath(wing), [0, 1, 0, 0], true);
  sketch(wing, seed + 2 + pose, { closed: true, width: 1.5 });
  const beak = [[-18, -5], [-30, -1], [-18, 3]];
  fill(linePath(beak), INK.beak);
  sketch(beak, seed + 5, { closed: true, sharp: true, width: 1.4 });
  fill(circle(-9, -6, 3.8), PAPER);
  fill(circle(-10, -6, 2.1), K);
  if (pose === 2) { sketch([[-4, 14], [-5, 23]], seed + 6, { width: 2.2 }); sketch([[4, 14], [5, 23]], seed + 7, { width: 2.2 }); }
  restore();
  for (let k = 0; k < 2; k++) {
    const q = prog(t, 9.15 + k * 0.3, 9.95 + k * 0.3);
    if (q > 0 && q < 1) drawNote(x - 26 - q * 24 - k * 8, y - 26 - q * 30, 0.9 + k * 0.2);
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
    fill(linePath(pts), INK.star);
    sketch(pts, 2000 + k * 3 + boil(f), { closed: true, sharp: true, width: 1.6, amp: 0.4 });
  });
}

// ---- the type: a pink shadow printed a little off, and a big numeral per step
function drawType(t) {
  for (const [str, y] of [['HOW TO GROW', 96], ['A TREE', 146]]) {
    text(str, 61, y + 3, DISPLAY(46), [1, 0, 0, 0]);
    text(str, 58, y, DISPLAY(46), K);
  }
  const i = stepAt(t);
  if (i < 0) return;
  const s = STEPS[i], p = prog(t, s.t, s.t + 0.2), slam = 1 + (1 - easeOut(p)) * 0.35;
  save();
  translate(190, 290);
  scale(slam);
  translate(-190, -290);
  text(s.n, 52, 362, DISPLAY(210), [1, 0, 0, 0]);
  text(s.n, 46, 356, DISPLAY(210), K, true, { outline: 3 });
  restore();
  text(s.text, 58, 424, DISPLAY(42), K);
  text(`STEP ${i + 1} OF 5`, 60, 456, MONO(17), K);
}

// ---- printer's marks in the margin: crop marks, a registration target, the colour bar
function drawMarks(f) {
  const REG = [1, 1, 1, 1];
  for (const [x, y, sx, sy] of [[PRINT.x0, PRINT.y0, -1, -1], [PRINT.x1, PRINT.y0, 1, -1], [PRINT.x0, PRINT.y1, -1, 1], [PRINT.x1, PRINT.y1, 1, 1]]) {
    const m = new Path2D();
    m.moveTo(x + sx * 6, y); m.lineTo(x + sx * 24, y);
    m.moveTo(x, y + sy * 6); m.lineTo(x, y + sy * 24);
    stroke(m, REG, 1.2);
  }
  const cross = new Path2D();
  cross.moveTo(629, 15); cross.lineTo(651, 15); cross.moveTo(640, 4); cross.lineTo(640, 26);
  stroke(cross, REG, 1.2);
  stroke(circle(640, 15, 6.5), REG, 1.2);
  [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]].forEach((d, k) => {
    fill(rect(PRINT.x0 + k * 50, 656, 22, 22), d);
    fill(rect(PRINT.x0 + k * 50 + 24, 656, 22, 22), d.map(v => v * 0.45));
  });
  text('FLUO PINK · AQUA · YELLOW · FEDERAL BLUE', PRINT.x0 + 214, 672, MONO(12), K);
  text(`HOW TO GROW A TREE · 4-COLOUR RISO · FRAME ${String(f).padStart(3, '0')}/120`, PRINT.x1, 672, MONO(12), K, true, { align: 'right' });
}

// ---------------------------------------------------------------- one frame
const REG_BASE = [[1.6, -1.1], [-1.3, 1.5], [0, 0], [0.7, 0.9]];
function drawFrame(t) {
  const f = Math.round(t * FPS);
  each(c => {
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.globalCompositeOperation = 'source-over';
    c.globalAlpha = 1;
    c.fillStyle = '#000';
    c.fillRect(0, 0, c.canvas.width, c.canvas.height);
    c.setTransform(S, 0, 0, S, 0, 0);
  });
  save();
  clip(rect(PRINT.x0, PRINT.y0, PRINT.x1 - PRINT.x0, PRINT.y1 - PRINT.y0));
  drawSky(t);
  drawSun(t, f);
  drawClouds(t, f);
  drawLand(f);
  drawUnderground(t, f);
  drawGrass(f);
  drawSunbeams(t);
  drawTree(t);
  drawMound(t, f);
  drawSprout(t, f);
  drawLeaves(t, f);
  drawApples(t, f);
  drawStamp(t);
  drawWater(t);
  drawCan(t, f);
  drawFallingAcorn(t, f);
  drawDirt(t);
  drawBird(t, f);
  drawSparkles(t, f);
  drawType(t);
  restore();
  drawMarks(f);
  present(t, f);
}

// Run the plates through the press: halftone, grain and registration in the shader.
function present(t, f) {
  const on = PASS.map(p0 => prog(t, p0, p0 + PASS_LEN));
  if (!gl) { composeFallback(on); return; }
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, tex[0]);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, plateA);
  gl.activeTexture(gl.TEXTURE1);
  gl.bindTexture(gl.TEXTURE_2D, tex[1]);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, plateB);
  const off = [];
  REG_BASE.forEach(([bx, by], k) => {
    off.push((bx + sgn(hash(k, f, 7)) * 0.9 * jitterAmp) * S, -(by + sgn(hash(k, f, 8)) * 0.9 * jitterAmp) * S);
  });
  gl.uniform2f(U.uRes, glCanvas.width, glCanvas.height);
  gl.uniform2fv(U.uOff, off);
  gl.uniform4f(U.uOn, on[0], on[1], on[2], on[3]);
  gl.uniform1f(U.uCell, Math.max(3.2, 5.2 * S));
  gl.uniform1f(U.uSeed, jitterAmp ? f : 0);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
  out.drawImage(glCanvas, 0, 0);
}

// ---------------------------------------------------------------- sound: a lo-fi beat
// Electric piano (FM), sub bass, boom-bap drums and vinyl crackle, all from oscillators and
// noise. The four passes of the riso drum are the first beats of the song.
const BEAT = 60 / 90;                          // 90 BPM: every step lands on a beat
const TAPE_STOP = 9.45;
let tapeStopAt = TAPE_STOP;            // absolute time on the audio clock, set by the score
function hz(name) {
  const m = /^([A-G])(#|b)?(\d)$/.exec(name);
  const semis = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 }[m[1]] + (m[2] === '#' ? 1 : m[2] === 'b' ? -1 : 0) + (+m[3] + 1) * 12;
  return 440 * 2 ** ((semis - 69) / 12);
}

function makeMix(ac, dest) {
  const out = ac.createGain(), comp = ac.createDynamicsCompressor();
  comp.threshold.value = -15;
  comp.knee.value = 10;
  comp.ratio.value = 3.5;
  comp.attack.value = 0.005;
  comp.release.value = 0.2;
  const trim = ac.createGain();
  trim.gain.value = 0.55;
  out.connect(comp).connect(trim).connect(dest);
  const warm = ac.createBiquadFilter(), sat = ac.createWaveShaper();
  warm.type = 'lowpass';
  warm.frequency.value = 5200;
  warm.Q.value = 0.4;
  const curve = new Float32Array(1024);
  for (let i = 0; i < curve.length; i++) { const x = i / 511.5 - 1; curve[i] = Math.tanh(x * 1.6) / Math.tanh(1.6); }
  sat.curve = curve;
  warm.connect(sat).connect(out);
  const len = Math.floor(ac.sampleRate * 1.3), ir = ac.createBuffer(2, len, ac.sampleRate);
  for (let c = 0; c < 2; c++) { const d = ir.getChannelData(c); for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / len) ** 3; }
  const verb = ac.createConvolver(), wet = ac.createGain();
  verb.buffer = ir;
  wet.gain.value = 0.2;
  verb.connect(wet).connect(out);
  const bus = (level, send, into) => {
    const g = ac.createGain(), s = ac.createGain();
    g.gain.value = level;
    s.gain.value = send;
    g.connect(into);
    g.connect(s).connect(verb);
    return g;
  };
  return {
    out, warm,
    keys: bus(0.34, 0.28, warm), drums: bus(0.75, 0.05, warm), bass: bus(0.5, 0, warm),
    vinyl: bus(0.5, 0, out), bells: bus(0.4, 0.4, warm), fx: bus(0.72, 0.16, out),
  };
}

let noiseBuf = null, crackleBuf = null;
function noiseBuffer(ac) {
  if (!noiseBuf || noiseBuf.sampleRate !== ac.sampleRate) {
    noiseBuf = ac.createBuffer(1, ac.sampleRate * 2, ac.sampleRate);
    const d = noiseBuf.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  }
  return noiseBuf;
}
function crackleBuffer(ac) { // soft hiss with the odd pop and click, like an old record
  if (crackleBuf && crackleBuf.sampleRate === ac.sampleRate) return crackleBuf;
  const sr = ac.sampleRate, len = sr * 3;
  crackleBuf = ac.createBuffer(1, len, sr);
  const d = crackleBuf.getChannelData(0);
  let hiss = 0;
  for (let i = 0; i < len; i++) { hiss = hiss * 0.95 + (Math.random() * 2 - 1) * 0.05; d[i] = hiss * 0.3; }
  for (let k = 0; k < 80; k++) {
    const at = Math.floor(Math.random() * (len - 60)), amp = (Math.random() < 0.15 ? 0.8 : 0.25) * (Math.random() < 0.5 ? -1 : 1);
    for (let j = 0; j < 50; j++) d[at + j] += amp * Math.exp(-j / 5) * (j % 2 ? -0.6 : 1);
  }
  return crackleBuf;
}
function noise(ac, dest, when, dur, o = {}) {
  const src = ac.createBufferSource(), flt = ac.createBiquadFilter(), g = ac.createGain();
  src.buffer = noiseBuffer(ac);
  src.loop = true;
  flt.type = o.type || 'bandpass';
  flt.Q.value = o.q ?? 1;
  flt.frequency.setValueAtTime(o.f0 ?? 2000, when);
  if (o.f1) flt.frequency.exponentialRampToValueAtTime(o.f1, when + dur);
  const attack = o.attack ?? 0.003;
  g.gain.setValueAtTime(0, when);
  g.gain.linearRampToValueAtTime(o.gain ?? 0.3, when + attack);
  g.gain.exponentialRampToValueAtTime(0.0005, when + Math.max(dur, attack + 0.01));
  src.connect(flt).connect(g);
  if (o.flutter) {
    const lfo = ac.createOscillator(), depth = ac.createGain(), vca = ac.createGain();
    lfo.type = 'triangle';
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
  const attack = o.attack ?? 0.004;
  g.gain.setValueAtTime(0, when);
  g.gain.linearRampToValueAtTime(o.gain ?? 0.3, when + attack);
  g.gain.exponentialRampToValueAtTime(0.0005, when + dur);
  osc.connect(g).connect(dest);
  osc.start(when);
  osc.stop(when + dur + 0.05);
}

// Electric piano: a 1:1 FM pair with a short metal "tine" on top, and a slow tape wobble.
function epiano(ac, dest, when, f, vel, dur) {
  const car = ac.createOscillator(), mod = ac.createOscillator(), index = ac.createGain(), amp = ac.createGain();
  car.frequency.value = f;
  mod.frequency.value = f;
  index.gain.setValueAtTime(f * 1.4, when);
  index.gain.exponentialRampToValueAtTime(f * 0.18, when + 1.0);
  mod.connect(index).connect(car.frequency);
  const tine = ac.createOscillator(), tg = ac.createGain();
  tine.frequency.value = f * 7.02;
  tg.gain.setValueAtTime(0.025 * vel, when);
  tg.gain.exponentialRampToValueAtTime(0.0001, when + 0.1);
  tine.connect(tg).connect(dest);
  amp.gain.setValueAtTime(0, when);
  amp.gain.linearRampToValueAtTime(0.12 * vel, when + 0.008);
  amp.gain.exponentialRampToValueAtTime(0.035 * vel, when + 0.9);
  amp.gain.exponentialRampToValueAtTime(0.0001, when + dur);
  car.connect(amp).connect(dest);
  const wob = ac.createOscillator(), wg = ac.createGain();
  wob.frequency.value = 0.55;
  wg.gain.value = 9;
  wob.connect(wg);
  wg.connect(car.detune);
  wg.connect(mod.detune);
  if (when + dur > tapeStopAt) { // the tape slows down and the pitch sags
    for (const o of [car, mod]) {
      o.detune.setValueAtTime(0, Math.max(when, tapeStopAt));
      o.detune.linearRampToValueAtTime(-1900, tapeStopAt + 0.65);
    }
  }
  for (const o of [car, mod, tine, wob]) { o.start(when); o.stop(when + dur + 0.05); }
}
function chord(ac, dest, when, notes, vel, dur) {
  notes.forEach((n, i) => epiano(ac, dest, when + i * 0.012, hz(n), vel * (1 - i * 0.06), dur));
}
function bassNote(ac, dest, when, f, dur) {
  const o = ac.createOscillator(), o2 = ac.createOscillator(), h = ac.createGain(), lp = ac.createBiquadFilter(), g = ac.createGain();
  o.frequency.value = f;
  o2.type = 'triangle';
  o2.frequency.value = f * 2;
  h.gain.value = 0.18;
  lp.type = 'lowpass';
  lp.frequency.value = 420;
  g.gain.setValueAtTime(0, when);
  g.gain.linearRampToValueAtTime(0.42, when + 0.02);
  g.gain.setTargetAtTime(0.2, when + 0.05, 0.3);
  g.gain.setTargetAtTime(0, when + dur - 0.12, 0.05);
  o.connect(lp);
  o2.connect(h).connect(lp);
  lp.connect(g).connect(dest);
  if (when + dur > tapeStopAt) for (const x of [o, o2]) { x.detune.setValueAtTime(0, tapeStopAt); x.detune.linearRampToValueAtTime(-1900, tapeStopAt + 0.65); }
  for (const x of [o, o2]) { x.start(when); x.stop(when + dur + 0.1); }
}
function kick(ac, dest, when, vel = 1) {
  tone(ac, dest, when, 0.34, { f0: 115, f1: 42, glide: 0.12, gain: 0.9 * vel, attack: 0.002 });
  noise(ac, dest, when, 0.012, { type: 'highpass', f0: 2500, gain: 0.12 * vel });
}
function snare(ac, dest, when, vel = 1) {
  noise(ac, dest, when, 0.2, { f0: 1900, q: 0.7, gain: 0.42 * vel });
  tone(ac, dest, when, 0.08, { type: 'triangle', f0: 190, f1: 150, gain: 0.3 * vel, attack: 0.002 });
}
const hat = (ac, dest, when, vel = 1, open = false) => noise(ac, dest, when, open ? 0.2 : 0.035, { type: 'highpass', f0: 7200, gain: 0.13 * vel });
function bell(ac, dest, when, f, vel = 1) { // FM bell for sparkles
  const car = ac.createOscillator(), mod = ac.createOscillator(), idx = ac.createGain(), g = ac.createGain();
  car.frequency.value = f;
  mod.frequency.value = f * 3.5;
  idx.gain.setValueAtTime(f * 2.2, when);
  idx.gain.exponentialRampToValueAtTime(f * 0.1, when + 0.8);
  mod.connect(idx).connect(car.frequency);
  g.gain.setValueAtTime(0, when);
  g.gain.linearRampToValueAtTime(0.18 * vel, when + 0.004);
  g.gain.exponentialRampToValueAtTime(0.0001, when + 1.1);
  car.connect(g).connect(dest);
  for (const o of [car, mod]) { o.start(when); o.stop(when + 1.15); }
}

const sfx = {
  // one pass of the riso drum: a tuned thud, the clack of the paper feed, the roller's whirr
  press: (ac, d, t, f) => {
    tone(ac, d, t, 0.26, { f0: f * 1.6, f1: f, glide: 0.08, gain: 0.55, attack: 0.002 });
    noise(ac, d, t + 0.01, 0.05, { f0: 1100, q: 2, gain: 0.22 });
    noise(ac, d, t, 0.24, { f0: 400, f1: 1500, q: 1.5, gain: 0.08, attack: 0.08 });
  },
  stamp: (ac, d, t) => {
    tone(ac, d, t, 0.16, { f0: 150, f1: 60, gain: 0.45, attack: 0.002 });
    noise(ac, d, t, 0.05, { f0: 2300, q: 0.9, gain: 0.2 });
  },
  pop: (ac, d, t, f, gain = 0.28) => {
    tone(ac, d, t, 0.1, { f0: f * 0.55, f1: f * 1.3, glide: 0.035, gain });
    noise(ac, d, t, 0.016, { type: 'highpass', f0: 3000, gain: gain * 0.2 });
  },
  whistle: (ac, d, t, dur, f0, f1, gain = 0.14) => tone(ac, d, t, dur, { type: 'triangle', f0, f1, gain, attack: 0.03, vib: f0 * 0.012, vibRate: 11 }),
  tok: (ac, d, t, f, gain = 0.38) => { tone(ac, d, t, 0.07, { f0: f, f1: f * 0.9, gain, attack: 0.002 }); noise(ac, d, t, 0.02, { f0: f * 2.5, q: 2, gain: gain * 0.3 }); },
  dig: (ac, d, t, f) => noise(ac, d, t, 0.075, { f0: f, q: 1.6, gain: 0.2, attack: 0.01 }),
  whoosh: (ac, d, t, dur, f0, f1, gain) => noise(ac, d, t, dur, { f0, f1, q: 1.3, gain, attack: dur * 0.45 }),
  clink: (ac, d, t) => { for (const [f, g] of [[2100, 0.08], [5390, 0.04]]) tone(ac, d, t, 0.3, { f0: f, gain: g, attack: 0.002 }); },
  bloop: (ac, d, t, f) => tone(ac, d, t, 0.11, { f0: f, f1: f * 2.3, glide: 0.05, gain: 0.26, attack: 0.003 }),
  trickle: (ac, d, t, dur) => noise(ac, d, t, dur, { f0: 5200, q: 2.5, gain: 0.045, attack: 0.1, flutter: 23 }),
  crack: (ac, d, t) => { for (let i = 0; i < 4; i++) noise(ac, d, t + i * 0.022, 0.014, { type: 'highpass', f0: 2500, gain: 0.18 }); },
  tick: (ac, d, t) => noise(ac, d, t, 0.02, { f0: 2600, q: 3, gain: 0.22 }),
  chirp: (ac, d, t) => {
    tone(ac, d, t, 0.07, { f0: 2900, f1: 4500, glide: 0.05, gain: 0.12, attack: 0.004 });
    tone(ac, d, t + 0.075, 0.08, { f0: 4200, f1: 3000, glide: 0.06, gain: 0.1, attack: 0.004 });
  },
  flutter: (ac, d, t, dur) => noise(ac, d, t, dur, { type: 'lowpass', f0: 900, gain: 0.07, attack: 0.05, flutter: FPS / 2 }),
  // a record scratch: a buzzy tone pushed back and forth, with the needle's hiss
  scratch: (ac, d, t) => {
    const o = ac.createOscillator(), bp = ac.createBiquadFilter(), g = ac.createGain();
    o.type = 'sawtooth';
    o.frequency.setValueCurveAtTime(new Float32Array([160, 520, 180, 90, 460, 140]), t, 0.26);
    bp.type = 'bandpass';
    bp.frequency.value = 1300;
    bp.Q.value = 0.8;
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(0.22, t + 0.02);
    g.gain.setValueAtTime(0.22, t + 0.1);
    g.gain.linearRampToValueAtTime(0.03, t + 0.13);
    g.gain.linearRampToValueAtTime(0.2, t + 0.16);
    g.gain.exponentialRampToValueAtTime(0.0005, t + 0.27);
    o.connect(bp).connect(g).connect(d);
    o.start(t);
    o.stop(t + 0.3);
    noise(ac, d, t, 0.26, { f0: 3000, q: 0.7, gain: 0.06 });
  },
};

// The score. Every cue is tied to the numbers the pictures use.
function scheduleScore(ac, mix, T) {
  const at = s => T + s, { keys, drums, bass, vinyl, bells, fx } = mix;
  tapeStopAt = at(TAPE_STOP);
  // the needle drops, then the record crackles all the way through
  noise(ac, fx, at(0), 0.16, { type: 'lowpass', f0: 500, gain: 0.3 });
  const cr = ac.createBufferSource();
  cr.buffer = crackleBuffer(ac);
  cr.loop = true;
  const cg = ac.createGain();
  cg.gain.setValueAtTime(0.16, at(0));
  cr.connect(cg).connect(vinyl);
  cr.start(at(0));
  cr.stop(at(10.4));

  // intro: the four riso passes, tuned to F, A, C, F
  ['F2', 'A2', 'C3', 'F3'].forEach((n, i) => sfx.press(ac, fx, at(PASS[[2, 0, 1, 3][i]]), hz(n)));
  // keys: Fmaj9 | Em9 | Dm9 G13 | Cmaj9, and "ta-DA" lands on the C
  const CH = [
    [0, ['A3', 'E4', 'G4', 'C5'], 0.9, 1.7], [2.5 * BEAT, ['A3', 'E4', 'G4', 'C5'], 0.6, 1.4],
    [4 * BEAT, ['G3', 'D4', 'F#4', 'B4'], 0.9, 1.7], [6.5 * BEAT, ['G3', 'D4', 'F#4', 'B4'], 0.6, 1.2],
    [8 * BEAT, ['F3', 'C4', 'E4', 'A4'], 0.9, 1.4], [10 * BEAT, ['F3', 'B3', 'E4', 'A4'], 0.85, 1.4],
    [12 * BEAT, ['E3', 'B3', 'D4', 'G4', 'E5'], 1.1, 2.4],
  ];
  CH.forEach(([s, notes, v, dur]) => chord(ac, keys, at(s), notes, v, dur));
  [['F2', 0, 4], ['E2', 4, 4], ['D2', 8, 2], ['G2', 10, 2], ['C2', 12, 2.6]].forEach(([n, b, len]) => bassNote(ac, bass, at(b * BEAT), hz(n), len * BEAT));

  // drums: boom-bap with swung eighths, entering on beat 2 and dropping out for the scratch
  const SIXTEENTH = BEAT / 4, swing = i => (i % 4 === 2 ? 0.035 : 0);
  const kicks = [];
  for (let bar = 0; bar < 4; bar++) {
    for (let i = 0; i < 16; i++) {
      const pos = bar * 16 + i;
      if (pos < 8 || (pos >= 46 && pos < 48) || pos >= 56) continue;
      const s = pos * SIXTEENTH + swing(i);
      if (i === 0 || i === 7 || i === 10) { kick(ac, drums, at(s), i === 0 ? 1 : 0.8); kicks.push(s); }
      if (i === 4 || i === 12) snare(ac, drums, at(s), i === 12 ? 1 : 0.85);
      if (i % 2 === 0) hat(ac, drums, at(s), i % 4 === 0 ? 1 : 0.6, i === 14 && bar === 1);
    }
  }
  // sidechain: the keys duck a little under every kick
  keys.gain.setValueAtTime(0.34, at(0));
  for (const s of kicks) {
    keys.gain.setValueAtTime(0.34, at(s));
    keys.gain.linearRampToValueAtTime(0.22, at(s + 0.02));
    keys.gain.linearRampToValueAtTime(0.34, at(s + 0.22));
  }

  // step stamps
  STEPS.forEach(s => sfx.stamp(ac, fx, at(s.t)));
  // 1. plant a seed
  sfx.whistle(ac, fx, at(1.1), 0.5, 1300, 360);
  sfx.tok(ac, fx, at(1.6), 720);
  sfx.tok(ac, fx, at(1.78), 860, 0.2);
  [1.88, 1.97, 2.07].forEach((s, i) => sfx.dig(ac, fx, at(s), [1300, 1700, 1100][i]));
  // 2. water it
  sfx.whoosh(ac, fx, at(2.1), 0.35, 400, 1800, 0.1);
  sfx.clink(ac, fx, at(2.5));
  sfx.trickle(ac, fx, at(2.7), 0.8);
  const DROP_NOTES = ['E5', 'G5', 'B5', 'D6', 'F#5', 'B5', 'G5', 'E6'];
  DROPS.filter((_, i) => i % 2 === 0).forEach(d => sfx.bloop(ac, fx, at(d.land), hz(DROP_NOTES[d.note]) * 0.5));
  sfx.whoosh(ac, fx, at(3.65), 0.35, 1800, 500, 0.1);
  bell(ac, bells, at(3.2), hz('B5'), 0.6);
  // 3. add sunshine: the sun swells up behind the hill
  ['G4', 'B4', 'D5', 'F#5'].forEach(n => tone(ac, keys, at(4.0), 1.2, { type: 'triangle', f0: hz(n), gain: 0.05, attack: 0.5 }));
  ['B5', 'D6', 'F#6', 'A6'].forEach((n, i) => bell(ac, bells, at(4.2 + i * 0.09), hz(n), 0.7));
  tone(ac, fx, at(4.45), 0.14, { type: 'triangle', f0: 620, f1: 1250, gain: 0.12 });
  sfx.crack(ac, fx, at(4.7));
  sfx.whistle(ac, fx, at(4.85), 0.45, 300, 900, 0.09);
  sfx.pop(ac, fx, at(5.3), 900, 0.36);
  sfx.pop(ac, fx, at(5.58), hz('C6'));
  sfx.pop(ac, fx, at(5.68), hz('F6'));
  // 4. be patient: the years tick past while the tree grows
  tone(ac, fx, at(6.0), 1.9, { type: 'triangle', f0: 196, f1: 784, gain: 0.05, attack: 0.4, vib: 5, vibRate: 7 });
  sfx.whoosh(ac, fx, at(6.0), 1.8, 300, 3200, 0.06);
  for (let y = 2; y <= 20; y++) sfx.tick(ac, fx, at(YEAR_T0 + (y - 1) / 19.999 * (YEAR_T1 - YEAR_T0)));
  const PENTA = ['D5', 'E5', 'G5', 'A5', 'C6', 'D6', 'E6', 'G6', 'A6', 'C7', 'D7', 'E7'];
  LEAF_POPS.forEach((s, i) => sfx.pop(ac, fx, at(s), hz(PENTA[Math.min(i, PENTA.length - 1)]), 0.22));
  // 5. ta-da!
  sfx.scratch(ac, fx, at(7.7));
  ['C6', 'E6', 'G6', 'B6'].forEach((n, i) => bell(ac, bells, at(8.0 + i * 0.07), hz(n), 0.9));
  noise(ac, fx, at(8.0), 1.3, { type: 'highpass', f0: 5000, gain: 0.07 });
  APPLES.forEach((a, i) => sfx.pop(ac, fx, at(a.t), hz(['E5', 'G5', 'A5', 'C6', 'E6', 'G6'][i]), 0.22));
  sfx.flutter(ac, fx, at(8.4), 0.6);
  [9.1, 9.3, 9.55].forEach(s => sfx.chirp(ac, fx, at(s)));
  bell(ac, bells, at(9.25), hz('G6'), 0.5);
  // the tape stops
  mix.warm.frequency.setValueAtTime(5200, at(TAPE_STOP));
  mix.warm.frequency.exponentialRampToValueAtTime(500, at(TAPE_STOP + 0.65));
  mix.out.gain.setValueAtTime(1, at(9.7));
  mix.out.gain.linearRampToValueAtTime(0.0001, at(10.35));
}

// ---------------------------------------------------------------- playback
const playBtn = document.getElementById('play');
const againBtn = document.getElementById('again');
const soundBtn = document.getElementById('sound');
let ac = null, master = null, mix = null, audioClock = false;
let startAt = 0, clockStart = 0, playing = false, lastFrame = -1, raf = 0, shownT = DURATION;
let muted = false;
try { muted = localStorage.getItem('riso-tree:muted') === '1'; } catch (e) { /* storage blocked */ }

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
  playBtn.querySelector('.label').textContent = shownT >= DURATION && lastFrame > 0 ? 'Print again' : 'Play';
  againBtn.textContent = playing ? 'Start over' : 'Play';
  soundBtn.setAttribute('aria-pressed', String(!muted));
  soundBtn.textContent = muted ? 'Sound: off' : 'Sound: on';
}

function toggleSound() {
  muted = !muted;
  try { localStorage.setItem('riso-tree:muted', muted ? '1' : '0'); } catch (e) { /* storage blocked */ }
  if (master) master.gain.setTargetAtTime(muted ? 0 : 1, ac.currentTime, 0.03);
  setUI();
}

// Size the plates and the press to the screen.
function layout() {
  const box = stage.getBoundingClientRect(), dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = Math.round(clamp(box.width * dpr, 640, gl ? 2560 : 960)), h = Math.round(w * 9 / 16);
  if (w === stage.width && plateA.width === w) return;
  for (const c of [stage, plateA, plateB, glCanvas]) { c.width = w; c.height = h; }
  S = w / W;
  if (gl) gl.viewport(0, 0, w, h);
}

async function boot() {
  jitterAmp = matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 1;
  try { initGL(); } catch (e) { gl = null; }
  const faces = ['32px "Bowlby One"', '500 16px "DM Mono"'];
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

// For scrubbing from the console: risoTree.seek(4.2)
window.risoTree = { play, seek(t) { shownT = clamp(+t || 0, 0, DURATION); drawFrame(shownT); } };
boot();
})();
