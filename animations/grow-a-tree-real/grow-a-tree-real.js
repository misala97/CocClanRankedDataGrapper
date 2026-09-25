/* How to Grow a Tree, filmed: the ten-second story as a photoreal time-lapse.
   Pure JavaScript and WebGL2. Every blade of grass, leaf, grain of soil and ray of light
   is generated in code and lit with a physical sky, sun shadows, depth of field and
   bloom. Web Audio plays the meadow and the score. No images, audio files or libraries. */
(() => {
'use strict';

const DURATION = 10, TAU = Math.PI * 2, DEG = Math.PI / 180;
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lerp = (a, b, t) => a + (b - a) * t;
const prog = (t, a, b) => clamp((t - a) / (b - a));
const smooth = x => x * x * (3 - 2 * x);
const easeInOut = x => (x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2);
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

// ---------------------------------------------------------------- vectors and matrices
const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const mulS = (a, s) => [a[0] * s, a[1] * s, a[2] * s];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const len = a => Math.hypot(a[0], a[1], a[2]);
const norm = a => { const l = len(a) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };
const mix3 = (a, b, t) => [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];
function perpendicular(d) { // any unit vector at right angles to d
  const a = Math.abs(d[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0];
  return norm(cross(d, a));
}
function rotateAxis(v, axis, ang) { // Rodrigues
  const c = Math.cos(ang), s = Math.sin(ang), k = axis;
  return add(add(mulS(v, c), mulS(cross(k, v), s)), mulS(k, dot(k, v) * (1 - c)));
}

// Column-major 4x4 matrices, as WebGL expects.
function perspective(fovy, aspect, near, far) {
  const f = 1 / Math.tan(fovy / 2), nf = 1 / (near - far);
  return new Float32Array([f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) * nf, -1, 0, 0, 2 * far * near * nf, 0]);
}
function ortho(l, r, b, t, n, f) {
  return new Float32Array([2 / (r - l), 0, 0, 0, 0, 2 / (t - b), 0, 0, 0, 0, -2 / (f - n), 0, -(r + l) / (r - l), -(t + b) / (t - b), -(f + n) / (f - n), 1]);
}
function lookAt(eye, target, up = [0, 1, 0]) {
  const z = norm(sub(eye, target)), x = norm(cross(up, z)), y = cross(z, x);
  return new Float32Array([x[0], y[0], z[0], 0, x[1], y[1], z[1], 0, x[2], y[2], z[2], 0, -dot(x, eye), -dot(y, eye), -dot(z, eye), 1]);
}
function mat4mul(a, b) {
  const o = new Float32Array(16);
  for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) {
    let s = 0;
    for (let k = 0; k < 4; k++) s += a[k * 4 + r] * b[c * 4 + k];
    o[c * 4 + r] = s;
  }
  return o;
}
function mat4inv(m) {
  const a = m, o = new Float32Array(16);
  const b00 = a[0] * a[5] - a[1] * a[4], b01 = a[0] * a[6] - a[2] * a[4], b02 = a[0] * a[7] - a[3] * a[4];
  const b03 = a[1] * a[6] - a[2] * a[5], b04 = a[1] * a[7] - a[3] * a[5], b05 = a[2] * a[7] - a[3] * a[6];
  const b06 = a[8] * a[13] - a[9] * a[12], b07 = a[8] * a[14] - a[10] * a[12], b08 = a[8] * a[15] - a[11] * a[12];
  const b09 = a[9] * a[14] - a[10] * a[13], b10 = a[9] * a[15] - a[11] * a[13], b11 = a[10] * a[15] - a[11] * a[14];
  const det = 1 / (b00 * b11 - b01 * b10 + b02 * b09 + b03 * b08 - b04 * b07 + b05 * b06);
  o[0] = (a[5] * b11 - a[6] * b10 + a[7] * b09) * det; o[1] = (a[2] * b10 - a[1] * b11 - a[3] * b09) * det;
  o[2] = (a[13] * b05 - a[14] * b04 + a[15] * b03) * det; o[3] = (a[10] * b04 - a[9] * b05 - a[11] * b03) * det;
  o[4] = (a[6] * b08 - a[4] * b11 - a[7] * b07) * det; o[5] = (a[0] * b11 - a[2] * b08 + a[3] * b07) * det;
  o[6] = (a[14] * b02 - a[12] * b05 - a[15] * b01) * det; o[7] = (a[8] * b05 - a[10] * b02 + a[11] * b01) * det;
  o[8] = (a[4] * b10 - a[5] * b08 + a[7] * b06) * det; o[9] = (a[1] * b08 - a[0] * b10 - a[3] * b06) * det;
  o[10] = (a[12] * b04 - a[13] * b02 + a[15] * b00) * det; o[11] = (a[9] * b02 - a[8] * b04 - a[11] * b00) * det;
  o[12] = (a[5] * b07 - a[4] * b09 - a[6] * b06) * det; o[13] = (a[0] * b09 - a[1] * b07 + a[2] * b06) * det;
  o[14] = (a[13] * b01 - a[12] * b03 - a[14] * b00) * det; o[15] = (a[8] * b03 - a[9] * b01 + a[10] * b00) * det;
  return o;
}
function project(m, p) { // world point -> clip space
  const x = m[0] * p[0] + m[4] * p[1] + m[8] * p[2] + m[12], y = m[1] * p[0] + m[5] * p[1] + m[9] * p[2] + m[13];
  const z = m[2] * p[0] + m[6] * p[1] + m[10] * p[2] + m[14], w = m[3] * p[0] + m[7] * p[1] + m[11] * p[2] + m[15];
  return [x / w, y / w, z / w, w];
}

// ---------------------------------------------------------------- WebGL2 plumbing
const stage = document.getElementById('stage');
const out = stage.getContext('2d', { alpha: false });
const glCanvas = document.createElement('canvas');
let gl = null, HALF_FLOAT_OK = false;

function program(vs, fs) {
  const make = (type, src) => {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      const lines = src.split('\n').map((l, i) => `${i + 1}: ${l}`).join('\n');
      throw new Error(gl.getShaderInfoLog(s) + '\n' + lines);
    }
    return s;
  };
  const p = gl.createProgram();
  gl.attachShader(p, make(gl.VERTEX_SHADER, vs));
  gl.attachShader(p, make(gl.FRAGMENT_SHADER, fs));
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
  const cache = new Map();
  p.u = name => { if (!cache.has(name)) cache.set(name, gl.getUniformLocation(p, name)); return cache.get(name); };
  return p;
}
// Set uniforms by name; numbers, arrays of 2-4 floats, 4x4 matrices, textures via [unit, tex].
function uniforms(p, map) {
  for (const k in map) {
    const v = map[k], loc = p.u(k);
    if (loc === null) continue;
    if (typeof v === 'number') gl.uniform1f(loc, v);
    else if (v.tex) { gl.activeTexture(gl.TEXTURE0 + v.unit); gl.bindTexture(gl.TEXTURE_2D, v.tex); gl.uniform1i(loc, v.unit); }
    else if (v.length === 16) gl.uniformMatrix4fv(loc, false, v);
    else if (v.length === 2) gl.uniform2fv(loc, v);
    else if (v.length === 3) gl.uniform3fv(loc, v);
    else if (v.length === 4) gl.uniform4fv(loc, v);
    else gl.uniform4fv(loc, v); // vec4 arrays
  }
}
const T = (unit, tex) => ({ unit, tex });
// A vertex array from attribute specs: { loc, data (Float32Array), size, divisor }.
function vertexArray(specs, indices) {
  const vao = gl.createVertexArray();
  gl.bindVertexArray(vao);
  for (const s of specs) {
    const b = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, b);
    gl.bufferData(gl.ARRAY_BUFFER, s.data, s.dynamic ? gl.DYNAMIC_DRAW : gl.STATIC_DRAW);
    gl.enableVertexAttribArray(s.loc);
    gl.vertexAttribPointer(s.loc, s.size, gl.FLOAT, false, 0, 0);
    if (s.divisor) gl.vertexAttribDivisor(s.loc, s.divisor);
    s.buffer = b;
  }
  if (indices) {
    const ib = gl.createBuffer();
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ib);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, indices, gl.STATIC_DRAW);
  }
  gl.bindVertexArray(null);
  return vao;
}
function texture(w, h, internal, format, type, filter = gl.LINEAR) {
  const t = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, t);
  gl.texImage2D(gl.TEXTURE_2D, 0, internal, w, h, 0, format, type, null);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filter);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  t.w = w; t.h = h;
  return t;
}
const colorTex = (w, h) => (HALF_FLOAT_OK ? texture(w, h, gl.RGBA16F, gl.RGBA, gl.HALF_FLOAT) : texture(w, h, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE));
function framebuffer(color, depth) {
  const f = gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, f);
  if (color) gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, color, 0);
  if (depth) gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.TEXTURE_2D, depth, 0);
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  f.w = (color || depth).w; f.h = (color || depth).h;
  return f;
}

// ---------------------------------------------------------------- shared shader code
const SUN_I = 22.0;
const COMMON = `#version 300 es
precision highp float;
precision highp sampler2D;
precision highp sampler2DShadow;
#define PI 3.14159265359
uniform float uTime, uGrow, uMound, uWind, uWetAll;
uniform vec4 uWet[10];
uniform vec2 uWindDir;
uniform vec3 uCamPos, uSunDir, uSunCol, uSkyCol, uBounceCol, uFogCol, uFogSun;
uniform float uFogDensity;
uniform mat4 uShadowMat;
uniform sampler2DShadow uShadow;
uniform float uShadowTexel, uShadowNormalOff, uShadowDepthBias;

float hash12(vec2 p) { vec3 q = fract(vec3(p.xyx) * 0.1031); q += dot(q, q.yzx + 33.33); return fract((q.x + q.y) * q.z); }
vec2 hash22(vec2 p) { vec3 q = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973)); q += dot(q, q.yzx + 33.33); return fract((q.xx + q.yz) * q.zy); }
float noise2(vec2 p) {
  vec2 i = floor(p), f = fract(p), u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash12(i), hash12(i + vec2(1.0, 0.0)), u.x), mix(hash12(i + vec2(0.0, 1.0)), hash12(i + vec2(1.0, 1.0)), u.x), u.y);
}
float fbm2(vec2 p) { float s = 0.0, a = 0.5; for (int i = 0; i < 5; i++) { s += a * noise2(p); p = mat2(1.6, 1.2, -1.2, 1.6) * p + 17.1; a *= 0.5; } return s; }
float fbm3(vec2 p) { float s = 0.0, a = 0.5; for (int i = 0; i < 3; i++) { s += a * noise2(p); p = mat2(1.6, 1.2, -1.2, 1.6) * p + 5.3; a *= 0.5; } return s; }

// The ground: hills far off, a meadow, and a slightly raised bed of crumbly soil in the middle.
float crumbs(vec2 p) { // a field of rounded clods, one per cell
  vec2 ip = floor(p), fp = fract(p);
  float h = 0.0;
  for (int y = -1; y <= 1; y++) for (int x = -1; x <= 1; x++) {
    vec2 o = vec2(float(x), float(y)), c = o + hash22(ip + o) * 0.8 + 0.1 - fp;
    float r = 0.55 + 0.35 * hash12(ip + o + 3.7);
    h = max(h, 1.0 - dot(c, c) / (r * r));
  }
  return h;
}
float soilDetail(vec2 p) {
  return crumbs(p * 90.0) * 0.0032 + crumbs(p * 260.0 + 17.0) * 0.0012 + (noise2(p * 18.0) - 0.5) * 0.004;
}
float terrainH(vec2 p) {
  float r = length(p);
  float hills = (fbm3(p * 0.022 + 3.1) - 0.5) * 9.0 * smoothstep(8.0, 45.0, r);
  float meadow = (fbm3(p * 0.35) - 0.5) * 0.14 * smoothstep(0.7, 3.0, r);
  float bedMask = 1.0 - smoothstep(0.32, 0.52, r);
  vec2 m = p - vec2(-0.0125, 0.0);
  float mound = uMound * 0.006 * exp(-dot(m, m) / 0.0008);
  float settle = 1.0 - 0.85 * smoothstep(0.4, 0.85, uGrow);
  return hills + meadow + (soilDetail(p) + 0.014) * bedMask * settle + mound;
}

const vec2 POISSON[8] = vec2[8](vec2(-0.613, 0.617), vec2(0.170, -0.040), vec2(-0.299, -0.792), vec2(0.645, 0.493),
  vec2(-0.651, -0.228), vec2(0.421, -0.669), vec2(-0.094, 0.940), vec2(0.917, -0.132));
float sunShadow(vec3 wp, vec3 n) {
  vec4 sp = uShadowMat * vec4(wp + n * uShadowNormalOff, 1.0);
  vec3 s = sp.xyz / sp.w * 0.5 + 0.5;
  if (s.x < 0.0 || s.x > 1.0 || s.y < 0.0 || s.y > 1.0 || s.z > 1.0) return 1.0;
  float sum = 0.0;
  for (int i = 0; i < 8; i++) sum += texture(uShadow, vec3(s.xy + POISSON[i] * uShadowTexel * 1.5, s.z - uShadowDepthBias));
  return sum * 0.125;
}
vec3 ambient(vec3 n, float ao) { return (uSkyCol * (0.55 + 0.45 * n.y) + uBounceCol * (0.45 - 0.45 * n.y)) * ao; }
float ggx(vec3 n, vec3 v, vec3 l, float rough) { // specular times N.L
  vec3 h = normalize(v + l);
  float a = rough * rough, a2 = a * a;
  float nh = max(dot(n, h), 0.0), nl = max(dot(n, l), 0.0), nv = max(dot(n, v), 1e-3);
  float d = a2 / (PI * pow(nh * nh * (a2 - 1.0) + 1.0, 2.0));
  float k = a * 0.5, g = nl / (nl * (1.0 - k) + k) * nv / (nv * (1.0 - k) + k);
  float f = 0.04 + 0.96 * pow(1.0 - max(dot(h, v), 0.0), 5.0);
  return d * g * f / (4.0 * nv * max(nl, 1e-3)) * nl;
}
vec3 applyFog(vec3 col, vec3 wp) {
  vec3 d = wp - uCamPos;
  float dist = length(d), f = 1.0 - exp(-dist * uFogDensity);
  vec3 fogc = uFogCol + uFogSun * pow(max(dot(d / dist, uSunDir), 0.0), 8.0);
  return mix(col, fogc, f);
}
`;

// ---------------------------------------------------------------- the sky
// Single-scattering Rayleigh and Mie, the same maths on the GPU (for the sky) and in
// JavaScript (for the colour of the sunlight and the ambient light it gives).
const ATMOS_GLSL = `
vec3 atmosphere(vec3 rd, vec3 sd) {
  const float Re = 6360e3, Ra = 6420e3, Hr = 7994.0, Hm = 1200.0;
  const vec3 bR = vec3(5.8e-6, 13.5e-6, 33.1e-6);
  const float bM = 21e-6, g = 0.76;
  vec3 ro = vec3(0.0, Re + 200.0, 0.0);
  float b = dot(ro, rd), c = dot(ro, ro) - Ra * Ra, t1 = -b + sqrt(b * b - c);
  float seg = t1 / 12.0, mu = dot(rd, sd);
  float pr = 3.0 / (16.0 * PI) * (1.0 + mu * mu);
  float pm = 3.0 / (8.0 * PI) * ((1.0 - g * g) * (1.0 + mu * mu)) / ((2.0 + g * g) * pow(1.0 + g * g - 2.0 * g * mu, 1.5));
  vec3 sr = vec3(0.0), sm = vec3(0.0);
  float odr = 0.0, odm = 0.0;
  for (int i = 0; i < 12; i++) {
    vec3 p = ro + rd * (float(i) + 0.5) * seg;
    float h = length(p) - Re, hr = exp(-h / Hr) * seg, hm = exp(-h / Hm) * seg;
    odr += hr; odm += hm;
    float b2 = dot(p, sd), c2 = dot(p, p) - Ra * Ra, sl = (-b2 + sqrt(b2 * b2 - c2)) / 6.0;
    float odrl = 0.0, odml = 0.0;
    bool lit = true;
    for (int j = 0; j < 6; j++) {
      float hl = length(p + sd * (float(j) + 0.5) * sl) - Re;
      if (hl < 0.0) { lit = false; break; }
      odrl += exp(-hl / Hr) * sl; odml += exp(-hl / Hm) * sl;
    }
    if (lit) { vec3 att = exp(-(bR * (odr + odrl) + bM * 1.1 * (odm + odml))); sr += att * hr; sm += att * hm; }
  }
  return ${SUN_I.toFixed(1)} * (sr * bR * pr + sm * bM * pm);
}`;

function atmosphereJS(rd, sd) {
  const Re = 6360e3, Ra = 6420e3, Hr = 7994, Hm = 1200, bR = [5.8e-6, 13.5e-6, 33.1e-6], bM = 21e-6, g = 0.76;
  const ro = [0, Re + 200, 0], b = dot(ro, rd), c = dot(ro, ro) - Ra * Ra, t1 = -b + Math.sqrt(b * b - c);
  const seg = t1 / 12, mu = dot(rd, sd);
  const pr = 3 / (16 * Math.PI) * (1 + mu * mu);
  const pm = 3 / (8 * Math.PI) * ((1 - g * g) * (1 + mu * mu)) / ((2 + g * g) * Math.pow(1 + g * g - 2 * g * mu, 1.5));
  const sr = [0, 0, 0], sm = [0, 0, 0];
  let odr = 0, odm = 0;
  for (let i = 0; i < 12; i++) {
    const p = add(ro, mulS(rd, (i + 0.5) * seg)), h = len(p) - Re, hr = Math.exp(-h / Hr) * seg, hm = Math.exp(-h / Hm) * seg;
    odr += hr; odm += hm;
    const b2 = dot(p, sd), c2 = dot(p, p) - Ra * Ra, sl = (-b2 + Math.sqrt(b2 * b2 - c2)) / 6;
    let odrl = 0, odml = 0, lit = true;
    for (let j = 0; j < 6; j++) {
      const hl = len(add(p, mulS(sd, (j + 0.5) * sl))) - Re;
      if (hl < 0) { lit = false; break; }
      odrl += Math.exp(-hl / Hr) * sl; odml += Math.exp(-hl / Hm) * sl;
    }
    if (!lit) continue;
    for (let k = 0; k < 3; k++) {
      const att = Math.exp(-(bR[k] * (odr + odrl) + bM * 1.1 * (odm + odml)));
      sr[k] += att * hr; sm[k] += att * hm;
    }
  }
  return [0, 1, 2].map(k => SUN_I * (sr[k] * bR[k] * pr + sm[k] * bM * pm));
}
// How much sunlight survives the trip through the air to the ground.
function sunTransmittance(sd) {
  const Re = 6360e3, Ra = 6420e3, Hr = 7994, Hm = 1200, bR = [5.8e-6, 13.5e-6, 33.1e-6], bM = 21e-6;
  const ro = [0, Re + 200, 0], dir = norm([sd[0], Math.max(sd[1], -0.02), sd[2]]);
  const b = dot(ro, dir), c = dot(ro, ro) - Ra * Ra, tl = -b + Math.sqrt(b * b - c), seg = tl / 24;
  let odr = 0, odm = 0;
  for (let i = 0; i < 24; i++) {
    const h = Math.max(0, len(add(ro, mulS(dir, (i + 0.5) * seg))) - Re);
    odr += Math.exp(-h / Hr) * seg; odm += Math.exp(-h / Hm) * seg;
  }
  return bR.map(br => Math.exp(-(br * odr + bM * 1.1 * odm)));
}
// Sun colour, sky ambient and haze colour for a sun direction.
function lightFor(sd, sunVis) {
  const T = sunTransmittance(sd), horizon = clamp((sd[1] + 0.02) / 0.06);
  const sunCol = T.map(v => v * SUN_I * sunVis * horizon);
  let sky = [0, 0, 0], wsum = 0;
  for (const el of [12, 35, 62, 85]) for (let a = 0; a < 6; a++) {
    const e = el * DEG, az = a / 6 * TAU, d = [Math.cos(e) * Math.cos(az), Math.sin(e), Math.cos(e) * Math.sin(az)], w = Math.sin(e);
    sky = add(sky, mulS(atmosphereJS(d, sd), w)); wsum += w;
  }
  sky = mulS(sky, Math.PI / wsum);
  let fog = [0, 0, 0];
  for (let a = 0; a < 8; a++) { const az = a / 8 * TAU; fog = add(fog, atmosphereJS(norm([Math.cos(az), 0.05, Math.sin(az)]), sd)); }
  fog = mulS(fog, 1 / 8);
  const toward = atmosphereJS(norm([sd[0], 0.05, sd[2]]), sd);
  return { sunCol, sky, fog, fogSun: sub(toward, fog).map(v => Math.max(0, v)) };
}

const FULLSCREEN_VS = `#version 300 es
const vec2 P[3] = vec2[3](vec2(-1.0, -1.0), vec2(3.0, -1.0), vec2(-1.0, 3.0));
out vec2 vUv;
out vec2 vNdc;
void main() { vec2 p = P[gl_VertexID]; vNdc = p; vUv = p * 0.5 + 0.5; gl_Position = vec4(p, 1.0, 1.0); }`;

const SKY_FS = COMMON + ATMOS_GLSL + `
uniform mat4 uInvViewProj;
uniform float uCloudCover;
in vec2 vNdc;
out vec4 oColor;
void main() {
  vec4 w = uInvViewProj * vec4(vNdc, 1.0, 1.0);
  vec3 rd = normalize(w.xyz / w.w - uCamPos);
  vec3 col = atmosphere(normalize(vec3(rd.x, max(rd.y, 0.003), rd.z)), uSunDir);
  float mu = dot(rd, uSunDir);
  if (rd.y > 0.0) {
    float t = (1600.0 - uCamPos.y) / rd.y;
    vec2 cp = uCamPos.xz + rd.xz * t;
    vec2 drift = vec2(uTime * 6.0, uTime * 1.5);
    float n = fbm2((cp + drift) * 0.00032);
    float cov = mix(0.66, 0.4, uCloudCover);
    float dens = smoothstep(cov, cov + 0.22, n) * smoothstep(0.02, 0.18, rd.y);
    float n2 = fbm2((cp + drift + uSunDir.xz * 300.0) * 0.00032);
    float selfShade = clamp(1.0 - (n2 - n) * 5.0, 0.35, 1.25);
    vec3 cloud = uSunCol * 0.085 * selfShade * (0.7 + 1.6 * pow(max(mu, 0.0), 8.0)) + uSkyCol * 0.33;
    col = mix(col, cloud, dens * 0.92);
  }
  float disk = smoothstep(0.99996, 0.999985, mu);
  col += uSunCol * (60.0 * disk + 0.9 * pow(max(mu, 0.0), 2000.0) + 0.06 * pow(max(mu, 0.0), 120.0));
  col = mix(col, uFogCol, smoothstep(0.0, -0.06, rd.y));
  oColor = vec4(col, 1.0);
}`;

// ---------------------------------------------------------------- materials
const WIND_GLSL = `
vec3 windOffset(vec3 p) {
  float a = smoothstep(0.8, 7.0, p.y);
  return vec3(uWindDir.x, 0.0, uWindDir.y) * (sin(uTime * 1.1 + p.x * 0.35 + p.z * 0.2) * 0.5 + 0.5) * a * 0.07 * uWind;
}`;

// ---- ground
const TERRAIN_VS = COMMON + `
layout(location = 0) in vec2 aXZ;
uniform mat4 uViewProj;
out vec3 vWorld;
void main() { vec3 p = vec3(aXZ.x, terrainH(aXZ), aXZ.y); vWorld = p; gl_Position = uViewProj * vec4(p, 1.0); }`;
const TERRAIN_FS = COMMON + `
in vec3 vWorld;
out vec4 oColor;
float wetness(vec2 p) {
  float w = uWetAll * exp(-dot(p, p) / 0.0035);
  for (int i = 0; i < 10; i++) {
    vec4 d = uWet[i];
    float age = uTime - d.z;
    if (age < 0.0) continue;
    float r = 0.004 + 0.02 * sqrt(min(age, 1.5));
    vec2 q = p - d.xy;
    w += exp(-dot(q, q) / (r * r)) * d.w;
  }
  return clamp(w, 0.0, 1.0);
}
vec3 soilColor(vec2 p, float wet, out float stone) {
  float n1 = fbm2(p * 9.0), n2 = noise2(p * 70.0), top = crumbs(p * 90.0);
  vec3 c = mix(vec3(0.04, 0.028, 0.019), vec3(0.11, 0.078, 0.05), smoothstep(0.25, 0.8, n1));
  c *= (0.75 + 0.35 * n2) * (0.7 + 0.55 * top * top);
  vec2 g = p * 42.0, ip = floor(g), fp = fract(g), id = vec2(0.0);
  float md = 9.0;
  for (int y = -1; y <= 1; y++) for (int x = -1; x <= 1; x++) {
    vec2 o = vec2(float(x), float(y)), h = hash22(ip + o);
    float d = length(o + h - fp);
    if (d < md) { md = d; id = ip + o; }
  }
  float rad = 0.12 + 0.22 * hash12(id * 3.1);
  stone = 0.0;
  c = mix(c, mix(vec3(0.07, 0.06, 0.05), vec3(0.14, 0.12, 0.1), hash12(id * 5.3)), stone);
  float straw = smoothstep(0.8, 0.9, noise2(p * 34.0 + 7.0)) * smoothstep(0.55, 0.8, noise2(p * 120.0));
  c = mix(c, vec3(0.2, 0.13, 0.06), straw * 0.6);
  return c * mix(1.0, 0.42, wet * (1.0 - stone * 0.5));
}
void main() {
  vec2 p = vWorld.xz;
  float r = length(p), dist = length(vWorld - uCamPos);
  float e = clamp(dist * 0.0012, 0.0004, 0.5);
  vec3 n = normalize(vec3(terrainH(p - vec2(e, 0.0)) - terrainH(p + vec2(e, 0.0)), 2.0 * e,
                          terrainH(p - vec2(0.0, e)) - terrainH(p + vec2(0.0, e))));
  float wet = wetness(p), stone;
  vec3 soil = soilColor(p, wet, stone);
  float far = smoothstep(16.0, 40.0, r);
  vec3 meadow = mix(vec3(0.04, 0.045, 0.018), mix(vec3(0.08, 0.12, 0.03), vec3(0.17, 0.18, 0.06), fbm3(p * 0.08)), far);
  float grassy = max(smoothstep(0.36, 0.5, r + (noise2(p * 20.0) - 0.5) * 0.06), smoothstep(0.4, 0.85, uGrow));
  vec3 alb = mix(soil, meadow, grassy);
  float ao = mix(1.0, 0.5, grassy * (1.0 - far));
  vec3 V = normalize(uCamPos - vWorld), L = uSunDir;
  float sh = sunShadow(vWorld, n);
  vec3 col = alb * (uSunCol * max(dot(n, L), 0.0) * sh * ao + ambient(n, ao));
  float soilOnly = 1.0 - grassy;
  col += uSunCol * sh * ggx(n, V, L, mix(0.9, 0.48, wet)) * mix(0.06, 0.35, wet) * soilOnly;
  oColor = vec4(applyFog(col, vWorld), 1.0);
}`;

// ---- grass: instanced blades, bent and pushed around by gusts
const GRASS_VS = COMMON + `
layout(location = 0) in vec2 aBlade;
layout(location = 1) in vec4 aI0;
layout(location = 2) in vec4 aI1;
uniform mat4 uViewProj;
out vec3 vWorld, vNrm;
out float vU, vTint;
void main() {
  float u = aBlade.x, side = aBlade.y, w = aI0.w;
  vec2 xz = aI0.xy;
  float h = aI0.z * (length(xz) < 0.45 ? smoothstep(0.4, 0.85, uGrow) : 1.0);
  h *= smoothstep(0.1, 0.45, distance(vec3(xz.x, 0.0, xz.y), vec3(uCamPos.x, 0.0, uCamPos.z)) + max(uCamPos.y - 0.3, 0.0));
  vec2 fwd = vec2(cos(aI1.x), sin(aI1.x)), across = vec2(-fwd.y, fwd.x);
  float b = aI1.y;
  if (abs(b) < 1e-3) b = 1e-3;
  float sx = (1.0 - cos(b * u)) / b * h, sy = sin(b * u) / b * h;
  vec3 base = vec3(xz.x, terrainH(xz), xz.y);
  vec3 center = base + vec3(fwd.x * sx, sy, fwd.y * sx);
  float gust = noise2(xz * 0.3 - uWindDir * uTime * 1.6);
  float push = (0.25 + 0.75 * gust + 0.15 * sin(uTime * 3.1 + aI1.w)) * uWind;
  center.xz += uWindDir * push * h * u * u * 0.55;
  center.y -= push * push * h * u * u * 0.12;
  float width = w * pow(1.0 - u, 0.7) * (0.8 + 0.2 * sin(u * 3.14159));
  vec3 acr = vec3(across.x, 0.0, across.y);
  vec3 pos = center + acr * width * 0.5 * side;
  vec3 tang = normalize(vec3(fwd.x * sin(b * u), cos(b * u), fwd.y * sin(b * u)) + vec3(uWindDir.x, 0.0, uWindDir.y) * push * u);
  vec3 nrm = normalize(cross(acr, tang) + acr * side * 0.35);
  vWorld = pos; vNrm = nrm; vU = u; vTint = aI1.z;
  gl_Position = uViewProj * vec4(pos, 1.0);
}`;
const GRASS_FS = COMMON + `
in vec3 vWorld, vNrm;
in float vU, vTint;
out vec4 oColor;
void main() {
  vec3 V = normalize(uCamPos - vWorld), L = uSunDir, n = normalize(vNrm);
  if (dot(n, V) < 0.0) n = -n;
  vec3 tip = mix(vec3(0.075, 0.16, 0.035), vec3(0.22, 0.2, 0.08), vTint * vTint);
  vec3 alb = mix(vec3(0.025, 0.05, 0.012), tip, smoothstep(0.0, 0.85, vU));
  float ao = mix(0.22, 1.0, smoothstep(0.0, 0.75, vU));
  float sh = sunShadow(vWorld, n);
  float diff = max(dot(n, L), 0.0) * 0.8 + 0.2;
  float trans = pow(max(dot(-V, L), 0.0), 3.0) * max(0.0, -dot(n, L) + 0.3);
  vec3 col = alb * (uSunCol * diff * sh * ao + ambient(n, ao)) + uSunCol * vec3(0.3, 0.45, 0.08) * alb * 6.0 * trans * sh * ao;
  col += uSunCol * sh * ggx(n, V, L, 0.38) * 0.35 * ao;
  oColor = vec4(applyFog(col, vWorld), 1.0);
}`;

// ---- the tree: tubes that grow along their length and thicken over the years
const TREE_VS = COMMON + WIND_GLSL + `
layout(location = 0) in vec3 aA;
layout(location = 1) in vec3 aB;
layout(location = 2) in vec2 aRad;
layout(location = 3) in vec2 aBirth;
layout(location = 4) in vec3 aDir;
layout(location = 5) in float aEnd;
layout(location = 6) in vec2 aUV;
uniform mat4 uViewProj;
out vec3 vWorld, vNrm;
out vec2 vUV;
out float vR;
void main() {
  float f = clamp((uGrow - aBirth.x) / max(aBirth.y - aBirth.x, 1e-5), 0.0, 1.0);
  bool tipRing = aEnd > 0.5;
  vec3 center = tipRing ? mix(aA, aB, f) : aA;
  float born = tipRing ? mix(aBirth.x, aBirth.y, f) : aBirth.x;
  float thick = clamp((uGrow - born) / max(1.0 - born, 1e-3), 0.0, 1.0);
  float r = max(0.0011, (tipRing ? aRad.y : aRad.x) * thick * thick);
  if (tipRing && f < 1.0) r *= 0.4;
  if (f <= 0.0) r = 0.0;
  center += windOffset(center);
  vec3 pos = center + aDir * r;
  vWorld = pos; vNrm = aDir; vUV = aUV; vR = r;
  gl_Position = uViewProj * vec4(pos, 1.0);
}`;
const TREE_FS = COMMON + `
uniform float uCanopy;
in vec3 vWorld, vNrm;
in vec2 vUV;
in float vR;
out vec4 oColor;
void main() {
  vec3 n = normalize(vNrm);
  float ridge = noise2(vec2(vUV.x * 9.0, vUV.y * 2.2)), fine = noise2(vec2(vUV.x * 38.0, vUV.y * 9.0));
  float young = 1.0 - smoothstep(0.003, 0.02, vR);
  vec3 bark = mix(vec3(0.05, 0.043, 0.036), vec3(0.16, 0.135, 0.11), ridge) * (0.75 + 0.4 * fine);
  vec3 alb = mix(bark, vec3(0.2, 0.15, 0.07), young);
  vec3 t = normalize(cross(n, vec3(0.0, 1.0, 0.0)) + vec3(1e-4));
  n = normalize(n + t * (ridge - 0.5) * 0.9 * (1.0 - young));
  float ao = mix(0.5, 1.0, smoothstep(0.0, 0.8, vWorld.y)) * (1.0 - 0.55 * uCanopy * smoothstep(1.8, 3.2, vWorld.y));
  vec3 V = normalize(uCamPos - vWorld), L = uSunDir;
  float sh = sunShadow(vWorld, n);
  vec3 col = alb * (uSunCol * max(dot(n, L), 0.0) * sh + ambient(n, ao)) + uSunCol * sh * ggx(n, V, L, 0.6) * 0.25;
  oColor = vec4(applyFog(col, vWorld), 1.0);
}`;

// ---- leaves: oak-shaped cards that unfold, flutter and glow when the sun is behind them
const LEAF_SHAPE = `
float leafMask(vec2 c) {
  float u = c.y, x = abs(c.x);
  float k = clamp((u - 0.07) / 0.93, 0.0, 1.0);
  float w = 0.31 * pow(sin(3.14159 * k), 0.85) * (1.0 - 0.3 * k) * (0.66 + 0.34 * abs(sin(k * 5.5 * 3.14159 + 0.4)));
  float stalk = u < 0.09 ? 0.03 : 0.0;
  float edge = max(w, stalk) - x;
  return clamp(edge / max(fwidth(edge), 1e-4) + 0.5, 0.0, 1.0);
}`;
const LEAF_VS = COMMON + WIND_GLSL + `
layout(location = 0) in vec2 aCorner;
layout(location = 1) in vec4 aL0;
layout(location = 2) in vec4 aL1;
layout(location = 3) in vec4 aL2;
layout(location = 4) in vec3 aL3;
uniform mat4 uViewProj;
out vec2 vLeaf;
out vec3 vWorld, vNrm;
out float vTint, vAO;
void main() {
  float s = smoothstep(aL1.w, aL1.w + 0.035, uGrow) * (1.0 - smoothstep(aL2.w, aL2.w + 0.03, uGrow));
  vec3 ax = aL1.xyz, nm = aL2.xyz, side = normalize(cross(ax, nm));
  float flutter = (sin(uTime * 7.3 + aL3.y * 6.28) * 0.12 + sin(uTime * 2.3 + aL3.y * 3.0) * 0.1) * uWind;
  ax = normalize(ax + nm * flutter);
  nm = normalize(cross(side, ax));
  float size = aL0.w * s;
  vec3 root = aL0.xyz + windOffset(aL0.xyz);
  vec3 pos = root + (ax * aCorner.y + side * aCorner.x + nm * aCorner.x * aCorner.x * 0.35) * size;
  vLeaf = vec2(aCorner.x, aCorner.y);
  vWorld = pos;
  vNrm = normalize(nm - side * aCorner.x * 0.7);
  vTint = aL3.x; vAO = aL3.z;
  gl_Position = uViewProj * vec4(pos, 1.0);
}`;
const LEAF_FS = COMMON + LEAF_SHAPE + `
in vec2 vLeaf;
in vec3 vWorld, vNrm;
in float vTint, vAO;
out vec4 oColor;
void main() {
  float a = leafMask(vLeaf);
  if (a < 0.02) discard;
  vec3 V = normalize(uCamPos - vWorld), L = uSunDir, n = normalize(vNrm);
  bool back = dot(n, V) < 0.0;
  if (back) n = -n;
  float vein = smoothstep(0.02, 0.0, abs(vLeaf.x)) * step(0.07, vLeaf.y)
             + 0.6 * smoothstep(0.05, 0.0, abs(fract(vLeaf.y * 5.5 - abs(vLeaf.x) * 1.6) - 0.5) * 0.3) * step(0.03, abs(vLeaf.x));
  vec3 alb = mix(vec3(0.045, 0.11, 0.018), vec3(0.12, 0.2, 0.035), vTint) * (back ? 1.3 : 1.0);
  alb = mix(alb, alb * 1.6 + vec3(0.02, 0.02, 0.0), clamp(vein, 0.0, 1.0) * 0.5);
  float sh = sunShadow(vWorld, n);
  float ao = vAO;
  float trans = max(-dot(n, L), 0.0) * (0.35 + 0.65 * pow(max(dot(-V, L), 0.0), 4.0));
  vec3 col = alb * (uSunCol * max(dot(n, L), 0.0) * sh * (0.4 + 0.6 * ao) + ambient(n, ao))
           + uSunCol * vec3(0.16, 0.26, 0.03) * trans * sh * (0.5 + 0.5 * ao) * (1.0 - vein * 0.4);
  col += uSunCol * sh * ggx(n, V, L, back ? 0.55 : 0.32) * 0.5;
  oColor = vec4(applyFog(col, vWorld), a);
}`;
const LEAF_SHADOW_FS = COMMON + LEAF_SHAPE + `
in vec2 vLeaf;
out vec4 oColor;
void main() { if (leafMask(vLeaf) < 0.5) discard; oColor = vec4(1.0); }`;

// ---- the acorn
const ACORN_VS = COMMON + `
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aNrm;
layout(location = 2) in vec2 aMat;
uniform mat4 uViewProj, uModel;
out vec3 vWorld, vNrm, vLocal;
out vec2 vMat;
void main() {
  vec4 w = uModel * vec4(aPos, 1.0);
  vWorld = w.xyz; vNrm = mat3(uModel) * aNrm; vLocal = aPos; vMat = aMat;
  gl_Position = uViewProj * w;
}`;
const ACORN_FS = COMMON + `
in vec3 vWorld, vNrm, vLocal;
in vec2 vMat;
out vec4 oColor;
void main() {
  vec3 n = normalize(vNrm), V = normalize(uCamPos - vWorld), L = uSunDir;
  float ang = atan(vLocal.z, vLocal.x);
  vec3 alb;
  float rough;
  if (vMat.x < 0.5) {
    float stripes = noise2(vec2(ang * 7.0, vLocal.y * 90.0));
    alb = mix(vec3(0.2, 0.075, 0.022), vec3(0.36, 0.15, 0.045), stripes) * mix(1.0, 1.25, smoothstep(0.004, -0.01, vLocal.y));
    rough = 0.3;
  } else {
    vec2 sc = vec2(ang * 9.0, vLocal.y * 760.0), ip = floor(sc), fp = fract(sc), best = vec2(0.0);
    float md = 9.0;
    for (int y = -1; y <= 1; y++) for (int x = -1; x <= 1; x++) {
      vec2 o = vec2(float(x), float(y)), c = o + hash22(ip + o) * 0.7 + 0.15 - fp;
      float dd = dot(c * vec2(1.0, 1.5), c * vec2(1.0, 1.5));
      if (dd < md) { md = dd; best = c; }
    }
    float scale = smoothstep(0.0, 0.5, best.y + 0.25) * (1.0 - smoothstep(0.35, 0.75, sqrt(md)));
    alb = mix(vec3(0.09, 0.072, 0.05), vec3(0.19, 0.155, 0.105), scale) * (0.85 + 0.3 * noise2(sc * 3.0));
    rough = 0.85;
  }
  float sh = sunShadow(vWorld, n);
  vec3 col = alb * (uSunCol * max(dot(n, L), 0.0) * sh + ambient(n, 1.0)) + uSunCol * sh * ggx(n, V, L, rough) * (vMat.x < 0.5 ? 0.6 : 0.15);
  oColor = vec4(applyFog(col, vWorld), 1.0);
}`;

// ---- water: drops streaked by the shutter, with a bright glint
const DROP_VS = COMMON + `
layout(location = 0) in vec2 aCorner;
layout(location = 1) in vec4 aD0;
layout(location = 2) in vec4 aD1;
uniform mat4 uViewProj;
uniform float uShutter;
out vec2 vLocal;
out float vRatio, vAlpha;
void main() {
  vec3 p = aD0.xyz, v = aD1.xyz;
  float r = aD0.w, speed = length(v), streak = speed * uShutter;
  vec3 ax = speed > 1e-4 ? v / speed : vec3(0.0, 1.0, 0.0);
  vec3 toCam = normalize(uCamPos - p), side = normalize(cross(ax, toCam));
  float halfLen = streak * 0.5 + r;
  vec3 pos = p - ax * streak * 0.5 + ax * aCorner.y * halfLen + side * aCorner.x * r;
  vLocal = aCorner; vRatio = r / halfLen; vAlpha = aD1.w;
  gl_Position = uViewProj * vec4(pos, 1.0);
}`;
const DROP_FS = COMMON + `
in vec2 vLocal;
in float vRatio, vAlpha;
out vec4 oColor;
void main() {
  float y = max(abs(vLocal.y) - (1.0 - vRatio), 0.0) / vRatio;
  float d = length(vec2(vLocal.x, y));
  if (d > 1.0) discard;
  float rim = pow(d, 3.0);
  vec3 col = (uSkyCol * 0.45 + uFogCol * 0.25) * (0.35 + 1.4 * rim) + (uSunCol + uSkyCol) * 0.8 * smoothstep(0.32, 0.0, length(vec2(vLocal.x + 0.35, y - 0.3)));
  float a = (0.3 + 0.6 * rim) * vAlpha * smoothstep(1.0, 0.85, d);
  oColor = vec4(col * a, a);
}`;

const DEPTH_FS = `#version 300 es
precision highp float;
out vec4 oColor;
void main() { oColor = vec4(1.0); }`;

// ---------------------------------------------------------------- the lens: post-processing
const POST_HEAD = `#version 300 es
precision highp float;
precision highp sampler2D;
in vec2 vUv;
out vec4 oColor;
uniform float uNear, uFar;
float linZ(float d) { float z = d * 2.0 - 1.0; return 2.0 * uNear * uFar / (uFar + uNear - z * (uFar - uNear)); }
float hash12(vec2 p) { vec3 q = fract(vec3(p.xyx) * 0.1031); q += dot(q, q.yzx + 33.33); return fract((q.x + q.y) * q.z); }
`;
// Half-size copy; with a threshold it keeps only the bright parts, for bloom.
const DOWN_FS = POST_HEAD + `
uniform sampler2D uSrc;
uniform vec2 uTexel;
uniform float uThreshold;
void main() {
  vec2 o = uTexel * 0.5;
  vec3 c = (texture(uSrc, vUv + vec2(-o.x, -o.y)).rgb + texture(uSrc, vUv + vec2(o.x, -o.y)).rgb
          + texture(uSrc, vUv + vec2(-o.x, o.y)).rgb + texture(uSrc, vUv + vec2(o.x, o.y)).rgb) * 0.25;
  if (uThreshold > 0.0) {
    float l = max(max(c.r, c.g), c.b), knee = uThreshold * 0.5;
    float soft = clamp(l - uThreshold + knee, 0.0, 2.0 * knee);
    soft = soft * soft / (4.0 * knee + 1e-4);
    c *= max(soft, l - uThreshold) / max(l, 1e-4);
    c = min(c, vec3(60.0));
  }
  oColor = vec4(c, 1.0);
}`;
// Depth of field: gather in a golden-angle spiral; far samples may not blur over sharper near ones.
const DOF_FS = POST_HEAD + `
uniform sampler2D uSrc, uDepth;
uniform vec2 uTexel;
uniform float uFocus, uAperture, uMaxCoC;
float coc(float z) { return clamp(uAperture * (1.0 - uFocus / z), -uMaxCoC, uMaxCoC); }
void main() {
  float cz = linZ(texture(uDepth, vUv).r), cs = abs(coc(cz));
  vec3 col = texture(uSrc, vUv).rgb;
  float tot = 1.0, radius = 1.0, ang = 0.0;
  for (int i = 0; i < 90; i++) {
    if (radius >= uMaxCoC) break;
    vec2 tc = vUv + vec2(cos(ang), sin(ang)) * uTexel * radius;
    vec3 sc = texture(uSrc, tc).rgb;
    float sz = linZ(texture(uDepth, tc).r), ss = abs(coc(sz));
    if (sz > cz) ss = clamp(ss, 0.0, cs * 2.0);
    float m = smoothstep(radius - 0.5, radius + 0.5, ss);
    col += mix(col / tot, sc, m);
    tot += 1.0;
    radius += 3.2 / radius;
    ang += 2.39996323;
  }
  oColor = vec4(col / tot, cs);
}`;
// Light shafts: march toward the sun, gathering only what is open sky.
const RAYS_FS = POST_HEAD + `
uniform sampler2D uSrc, uDepth;
uniform vec2 uSunUV;
uniform float uStrength;
void main() {
  vec2 d = uSunUV - vUv;
  vec2 stepv = d / 44.0;
  vec2 uv = vUv;
  float decay = 1.0;
  vec3 acc = vec3(0.0);
  for (int i = 0; i < 44; i++) {
    uv += stepv;
    if (uv.x < 0.0 || uv.y < 0.0 || uv.x > 1.0 || uv.y > 1.0) break;
    float sky = step(0.99999, texture(uDepth, uv).r);
    acc += min(texture(uSrc, uv).rgb, vec3(14.0)) * sky * decay;
    decay *= 0.955;
  }
  oColor = vec4(acc / 44.0 * uStrength * smoothstep(1.3, 0.0, length(d * vec2(1.6, 1.0))), 1.0);
}`;
// Bloom: a 13-tap downsample chain, then a tent-filtered upsample added back on the way up.
const BLOOM_DOWN_FS = POST_HEAD + `
uniform sampler2D uSrc;
uniform vec2 uTexel;
void main() {
  vec2 t = uTexel;
  vec3 a = texture(uSrc, vUv + t * vec2(-2, 2)).rgb, b = texture(uSrc, vUv + t * vec2(0, 2)).rgb, c = texture(uSrc, vUv + t * vec2(2, 2)).rgb;
  vec3 d = texture(uSrc, vUv + t * vec2(-2, 0)).rgb, e = texture(uSrc, vUv).rgb, f = texture(uSrc, vUv + t * vec2(2, 0)).rgb;
  vec3 g = texture(uSrc, vUv + t * vec2(-2, -2)).rgb, h = texture(uSrc, vUv + t * vec2(0, -2)).rgb, i = texture(uSrc, vUv + t * vec2(2, -2)).rgb;
  vec3 j = texture(uSrc, vUv + t * vec2(-1, 1)).rgb, k = texture(uSrc, vUv + t * vec2(1, 1)).rgb;
  vec3 l = texture(uSrc, vUv + t * vec2(-1, -1)).rgb, m = texture(uSrc, vUv + t * vec2(1, -1)).rgb;
  vec3 s = e * 0.125 + (a + c + g + i) * 0.03125 + (b + d + f + h) * 0.0625 + (j + k + l + m) * 0.125;
  oColor = vec4(s, 1.0);
}`;
const BLOOM_UP_FS = POST_HEAD + `
uniform sampler2D uSrc;
uniform vec2 uTexel;
void main() {
  vec2 t = uTexel;
  vec3 s = texture(uSrc, vUv).rgb * 4.0;
  s += (texture(uSrc, vUv + vec2(-t.x, 0)).rgb + texture(uSrc, vUv + vec2(t.x, 0)).rgb + texture(uSrc, vUv + vec2(0, t.y)).rgb + texture(uSrc, vUv + vec2(0, -t.y)).rgb) * 2.0;
  s += texture(uSrc, vUv + vec2(-t.x, t.y)).rgb + texture(uSrc, vUv + vec2(t.x, t.y)).rgb + texture(uSrc, vUv + vec2(-t.x, -t.y)).rgb + texture(uSrc, vUv + vec2(t.x, -t.y)).rgb;
  oColor = vec4(s / 16.0, 1.0);
}`;
// The final image: focus blend, glow, shafts, exposure, filmic curve, grade, vignette and grain.
const FINAL_FS = POST_HEAD + `
uniform sampler2D uScene, uDof, uBloom, uRays, uDepth;
uniform float uExposure, uBloomStrength, uFocus, uAperture, uSeed, uFade;
uniform vec2 uRes;
vec3 aces(vec3 x) { return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0); }
void main() {
  vec2 dc = vUv - 0.5;
  float ca = 0.004 * dot(dc, dc);
  vec3 sharp = vec3(texture(uScene, vUv - dc * ca).r, texture(uScene, vUv).g, texture(uScene, vUv + dc * ca).b);
  float cc = abs(uAperture * (1.0 - uFocus / linZ(texture(uDepth, vUv).r)));
  vec3 col = mix(sharp, texture(uDof, vUv).rgb, smoothstep(0.3, 1.1, cc));
  col += texture(uBloom, vUv).rgb * uBloomStrength + texture(uRays, vUv).rgb;
  col = aces(col * uExposure);
  col = pow(col, vec3(1.0 / 2.2));
  float lum = dot(col, vec3(0.299, 0.587, 0.114));
  col += vec3(0.022, 0.01, -0.018) * smoothstep(0.45, 1.0, lum) + vec3(-0.012, 0.0, 0.016) * (1.0 - smoothstep(0.0, 0.35, lum));
  col *= 1.0 - 0.5 * pow(length(dc * vec2(1.0, 0.92)) * 1.3, 2.8);
  col += (hash12(vUv * uRes + uSeed) - 0.5) * 0.03;
  oColor = vec4(clamp(col * uFade, 0.0, 1.0), 1.0);
}`;

// ---------------------------------------------------------------- the set
// JavaScript twins of the shader noise, so things can be placed exactly on the ground.
const fract = x => x - Math.floor(x);
const smoothstepJS = (a, b, x) => { const t = clamp((x - a) / (b - a)); return t * t * (3 - 2 * t); };
function hashJS(x, y) {
  const a = fract(x * 0.1031), b = fract(y * 0.1031), s = a * (b + 33.33) + b * (a + 33.33) + a * (a + 33.33);
  return fract((a + b + 2 * s) * (a + s));
}
function noiseJS(x, y) {
  const ix = Math.floor(x), iy = Math.floor(y), fx = x - ix, fy = y - iy, ux = fx * fx * (3 - 2 * fx), uy = fy * fy * (3 - 2 * fy);
  return lerp(lerp(hashJS(ix, iy), hashJS(ix + 1, iy), ux), lerp(hashJS(ix, iy + 1), hashJS(ix + 1, iy + 1), ux), uy);
}
function fbm3JS(x, y) {
  let s = 0, a = 0.5;
  for (let i = 0; i < 3; i++) { s += a * noiseJS(x, y); const nx = 1.6 * x - 1.2 * y + 5.3, ny = 1.2 * x + 1.6 * y + 5.3; x = nx; y = ny; a *= 0.5; }
  return s;
}
function hash22JS(x, y) {
  const a = fract(x * 0.1031), b = fract(y * 0.1030), c = fract(x * 0.0973);
  const s = a * (b + 33.33) + b * (c + 33.33) + c * (a + 33.33), qa = a + s, qb = b + s, qc = c + s;
  return [fract((qa + qb) * qc), fract((qa + qc) * qb)];
}
function crumbsJS(x, y) {
  const ix = Math.floor(x), iy = Math.floor(y), fx = x - ix, fy = y - iy;
  let h = 0;
  for (let oy = -1; oy <= 1; oy++) for (let ox = -1; ox <= 1; ox++) {
    const hh = hash22JS(ix + ox, iy + oy), cx = ox + hh[0] * 0.8 + 0.1 - fx, cy = oy + hh[1] * 0.8 + 0.1 - fy;
    const r = 0.55 + 0.35 * hashJS(ix + ox + 3.7, iy + oy + 3.7);
    h = Math.max(h, 1 - (cx * cx + cy * cy) / (r * r));
  }
  return h;
}
function terrainJS(x, z, mound = 0) {
  const r = Math.hypot(x, z), bed = 1 - smoothstepJS(0.32, 0.52, r);
  const hills = (fbm3JS(x * 0.022 + 3.1, z * 0.022 + 3.1) - 0.5) * 9 * smoothstepJS(8, 45, r);
  const meadow = (fbm3JS(x * 0.35, z * 0.35) - 0.5) * 0.14 * smoothstepJS(0.7, 3, r);
  const soil = crumbsJS(x * 90, z * 90) * 0.0032 + crumbsJS(x * 260 + 17, z * 260 + 17) * 0.0012 + (noiseJS(x * 18, z * 18) - 0.5) * 0.004;
  return hills + meadow + soil * bed + 0.014 * bed + mound * 0.006 * Math.exp(-((x + 0.0125) ** 2 + z * z) / 0.0008);
}

// Ground: rings that start millimetres apart at the planting spot and end metres apart at the horizon.
function buildTerrain() {
  const A = 256, R = 175, c = 0.0556, q = 1.045, xz = new Float32Array((1 + A * R) * 2), idx = [];
  let k = 2;
  for (let i = 1; i <= R; i++) {
    const r = c * (Math.pow(q, i) - 1);
    for (let j = 0; j < A; j++) { const a = (j + (i % 2) * 0.5) / A * TAU; xz[k++] = Math.cos(a) * r; xz[k++] = Math.sin(a) * r; }
  }
  for (let j = 0; j < A; j++) idx.push(0, 1 + j, 1 + (j + 1) % A);
  for (let i = 1; i < R; i++) {
    const a0 = 1 + (i - 1) * A, b0 = 1 + i * A;
    for (let j = 0; j < A; j++) { const j1 = (j + 1) % A; idx.push(a0 + j, b0 + j, b0 + j1, a0 + j, b0 + j1, a0 + j1); }
  }
  return { vao: vertexArray([{ loc: 0, data: xz, size: 2 }], new Uint32Array(idx)), count: idx.length };
}

// Grass: three bands of blades, finer near the soil, coarser toward the hills.
function buildGrass() {
  const r = rng(11), i0 = [], i1 = [];
  const band = (count, r0, r1, hMin, hMax, wMin, wMax) => {
    for (let n = 0; n < count; n++) {
      const rr = Math.sqrt(lerp(r0 * r0, r1 * r1, r())), a = r() * TAU, x = Math.cos(a) * rr, z = Math.sin(a) * rr;
      const clump = 0.55 + 0.9 * noiseJS(x * 1.3 + 7, z * 1.3);
      i0.push(x, z, lerp(hMin, hMax, Math.pow(r(), 1.4)) * clump, lerp(wMin, wMax, r()));
      i1.push(r() * TAU, (r() - 0.5) * 1.1 + 0.3, r() < 0.12 ? 0.55 + r() * 0.45 : r() * 0.3, r() * TAU);
    }
  };
  band(9000, 0.02, 0.45, 0.05, 0.16, 0.0035, 0.006);
  band(46000, 0.43, 2.6, 0.05, 0.19, 0.0035, 0.006);
  band(40000, 2.6, 11, 0.12, 0.32, 0.008, 0.016);
  band(28000, 11, 42, 0.3, 0.6, 0.025, 0.05);
  const SEG = 5, tpl = [], idx = [];
  for (let s = 0; s <= SEG; s++) tpl.push(s / SEG, -1, s / SEG, 1);
  for (let s = 0; s < SEG; s++) { const a = s * 2; idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
  return {
    vao: vertexArray([
      { loc: 0, data: new Float32Array(tpl), size: 2 },
      { loc: 1, data: new Float32Array(i0), size: 4, divisor: 1 },
      { loc: 2, data: new Float32Array(i1), size: 4, divisor: 1 },
    ], new Uint16Array(idx)),
    count: idx.length, instances: i0.length / 4,
  };
}

// The oak: a seeded branching structure. Each point knows when growth reaches it (0..1).
const SEEDLING_H = 0.14;
function buildTree() {
  const r = rng(424242), branches = [], twigs = [];
  function grow(p0, dir, L, r0, depth, path0) {
    const nSeg = [14, 8, 6, 4, 3][depth], pts = [p0], radii = [r0], paths = [path0];
    let p = p0, d = dir, walked = 0;
    for (let i = 1; i <= nSeg; i++) {
      const step = depth === 0 ? (i === 1 ? SEEDLING_H : (L - SEEDLING_H) / (nSeg - 1)) : L / nSeg;
      walked += step;
      const u = walked / L;
      d = depth === 0 && i === 1 ? [0, 1, 0] : norm(add(d, [(r() - 0.5) * 0.3, depth === 0 ? 0.05 : 0.02 + 0.05 * depth * u, (r() - 0.5) * 0.3]));
      p = add(p, mulS(d, step));
      pts.push(p); radii.push(r0 * Math.pow(1 - 0.65 * u, 1.2)); paths.push(path0 + walked);
    }
    branches.push({ pts, radii, paths, depth });
    if (depth === 4) { twigs.push({ pts, paths }); return; }
    const kids = [6, 4, 4, 5][depth];
    for (let k = 0; k < kids; k++) {
      const u = depth === 0 ? lerp(0.38, 0.97, k / (kids - 1)) : lerp(0.25, 0.92, (k + r() * 0.6) / kids);
      const i = Math.min(nSeg - 1, Math.floor(u * nSeg)), pd = norm(sub(pts[i + 1], pts[i]));
      const perp = rotateAxis(perpendicular(pd), pd, k * 2.39996 + r() * 0.8);
      const tilt = depth === 0 ? lerp(0.9, 1.2, r()) : lerp(0.55, 0.95, r());
      let cd = norm(add(mulS(pd, Math.cos(tilt)), mulS(perp, Math.sin(tilt))));
      if (depth === 0) cd = norm([cd[0], cd[1] * 0.5 + 0.28, cd[2]]);
      const cl = L * (depth === 0 ? lerp(0.62, 0.8, r()) * (1.15 - 0.45 * u) : lerp(0.55, 0.72, r()));
      grow(pts[i], cd, cl, radii[i] * lerp(0.5, 0.66, r()), depth + 1, paths[i]);
    }
  }
  grow([0, -0.012, 0], [0, 1, 0], 3.6, 0.3, 0, 0);
  const maxPath = Math.max(...twigs.map(t => t.paths[t.paths.length - 1]));
  // growth reaches the seedling's height first, then races through the crown
  const birth = path => (path <= SEEDLING_H ? path / SEEDLING_H * 0.1 : 0.1 + 0.85 * Math.pow((path - SEEDLING_H) / (maxPath - SEEDLING_H), 0.8));

  const A = [], B = [], RAD = [], BIRTH = [], DIR = [], END = [], UV = [], idx = [];
  for (const br of branches) {
    const ringN = [12, 10, 8, 6, 5][br.depth], n = br.pts.length, circ = TAU * br.radii[0];
    const frames = [];
    let nrm = perpendicular(norm(sub(br.pts[1], br.pts[0])));
    for (let i = 0; i < n; i++) {
      const tg = norm(sub(br.pts[Math.min(n - 1, i + 1)], br.pts[Math.max(0, i - 1)]));
      nrm = norm(sub(nrm, mulS(tg, dot(nrm, tg))));
      frames.push([nrm, cross(tg, nrm)]);
    }
    for (let i = 0; i < n - 1; i++) {
      const a = br.pts[i], b = br.pts[i + 1], ga = birth(br.paths[i]), gb = birth(br.paths[i + 1]), base = A.length / 3;
      for (let e = 0; e < 2; e++) {
        const [fn, fb] = frames[i + e];
        for (let k = 0; k <= ringN; k++) {
          const ang = k / ringN * TAU, dir = add(mulS(fn, Math.cos(ang)), mulS(fb, Math.sin(ang)));
          A.push(...a); B.push(...b); RAD.push(br.radii[i], br.radii[i + 1]); BIRTH.push(ga, gb);
          DIR.push(...dir); END.push(e); UV.push(k / ringN * circ, br.paths[i + e]);
        }
      }
      for (let k = 0; k < ringN; k++) { const p = base + k, q2 = base + ringN + 1 + k; idx.push(p, q2, p + 1, p + 1, q2, q2 + 1); }
    }
  }
  const tree = {
    vao: vertexArray([
      { loc: 0, data: new Float32Array(A), size: 3 }, { loc: 1, data: new Float32Array(B), size: 3 },
      { loc: 2, data: new Float32Array(RAD), size: 2 }, { loc: 3, data: new Float32Array(BIRTH), size: 2 },
      { loc: 4, data: new Float32Array(DIR), size: 3 }, { loc: 5, data: new Float32Array(END), size: 1 },
      { loc: 6, data: new Float32Array(UV), size: 2 },
    ], new Uint32Array(idx)),
    count: idx.length,
  };

  // Leaves: clusters along every twig, plus the seedling's first four leaves.
  const tips = twigs.map(t => t.pts[t.pts.length - 1]);
  const crownC = mulS(tips.reduce((s, p) => add(s, p), [0, 0, 0]), 1 / tips.length);
  const crownR = Math.max(...tips.map(p => len(sub(p, crownC))));
  const L0 = [], L1 = [], L2 = [], L3 = [];
  const leaf = (pos, axis, size, born, dies, ao) => {
    let n = sub([0, 1, 0], mulS(axis, axis[1]));
    n = norm(add(norm(n), [(r() - 0.5) * 0.9, 0, (r() - 0.5) * 0.9]));
    n = norm(sub(n, mulS(axis, dot(n, axis))));
    L0.push(...pos, size); L1.push(...axis, born); L2.push(...n, dies); L3.push(r(), r(), ao);
  };
  // young leaves along the sapling's stem, shed as the trunk matures
  const trunk = branches[0];
  for (let n = 0; n < 70; n++) {
    const path = lerp(0.25, 2.6, r()), i = trunk.paths.findIndex(p => p > path) - 1, f = (path - trunk.paths[i]) / (trunk.paths[i + 1] - trunk.paths[i]);
    const pos = mix3(trunk.pts[i], trunk.pts[i + 1], f), ang = r() * TAU;
    const b = birth(path) + 0.01;
    leaf(pos, norm([Math.cos(ang), 0.45 + r() * 0.4, Math.sin(ang)]), lerp(0.1, 0.15, r()), b, b + 0.22 + r() * 0.1, 1);
  }
  // leaves along the outer half of the middle branches, so the crown fills in as it grows
  for (const br of branches) {
    if (br.depth < 2 || br.depth > 3) continue;
    const count = br.depth === 2 ? 8 : 12;
    for (let n = 0; n < count; n++) {
      const u = lerp(0.45, 1, r()) * (br.pts.length - 1), i = Math.min(br.pts.length - 2, Math.floor(u)), f = u - i;
      const pos = mix3(br.pts[i], br.pts[i + 1], f), td = norm(sub(br.pts[i + 1], br.pts[i]));
      const axis = norm(add(add(mulS(rotateAxis(perpendicular(td), td, r() * TAU), 0.8), mulS(td, 0.4)), [0, 0.2, 0]));
      const out = len(sub(pos, crownC)) / crownR;
      leaf(pos, axis, lerp(0.12, 0.18, r()), birth(lerp(br.paths[i], br.paths[i + 1], f)) + 0.02 + r() * 0.04, 9, 0.3 + 0.7 * smoothstepJS(0.3, 1.0, out));
    }
  }
  for (const tw of twigs) {
    for (let n = 0; n < 30; n++) {
      const u = lerp(0.2, 1, r()) * (tw.pts.length - 1), i = Math.min(tw.pts.length - 2, Math.floor(u)), f = u - i;
      const pos = mix3(tw.pts[i], tw.pts[i + 1], f), td = norm(sub(tw.pts[i + 1], tw.pts[i]));
      const around = rotateAxis(perpendicular(td), td, r() * TAU);
      const axis = norm(add(add(mulS(around, 0.8), mulS(td, 0.45)), [0, 0.2, 0]));
      const out = len(sub(pos, crownC)) / crownR;
      leaf(pos, axis, lerp(0.12, 0.18, r()), birth(lerp(tw.paths[i], tw.paths[i + 1], f)) + 0.01 + r() * 0.04, 9, 0.3 + 0.7 * smoothstepJS(0.3, 1.0, out));
    }
  }
  for (let k = 0; k < 4; k++) {
    const h = 0.095 + k * 0.013, ang = k * 1.9 + 0.4;
    const axis = norm([Math.cos(ang), 0.5 + 0.12 * k, Math.sin(ang)]);
    leaf([0, h, 0], axis, 0.07 - k * 0.006, 0.05 + k * 0.008, 0.22 + k * 0.02, 1);
  }
  const leaves = {
    vao: vertexArray([
      { loc: 0, data: new Float32Array([-0.34, 0, 0.34, 0, 0.34, 1, -0.34, 1]), size: 2 },
      { loc: 1, data: new Float32Array(L0), size: 4, divisor: 1 }, { loc: 2, data: new Float32Array(L1), size: 4, divisor: 1 },
      { loc: 3, data: new Float32Array(L2), size: 4, divisor: 1 }, { loc: 4, data: new Float32Array(L3), size: 3, divisor: 1 },
    ], new Uint16Array([0, 1, 2, 0, 2, 3])),
    count: 6, instances: L0.length / 4,
  };
  return { tree, leaves, crownC, crownR, height: Math.max(...tips.map(p => p[1])) };
}

// The acorn, turned on a lathe: a glossy nut in a scaly cup.
function buildAcorn() {
  const P = [], N = [], M = [], idx = [];
  const lathe = (profile, mat) => {
    const seg = 28, base = P.length / 3;
    profile.forEach(([rr, y], i) => {
      const [r0, y0] = profile[Math.max(0, i - 1)], [r1, y1] = profile[Math.min(profile.length - 1, i + 1)];
      const tr = r1 - r0, ty = y1 - y0, l = Math.hypot(tr, ty) || 1;
      for (let j = 0; j <= seg; j++) {
        const a = j / seg * TAU, c = Math.cos(a), s = Math.sin(a);
        P.push(rr * c, y, rr * s); N.push(ty / l * c, -tr / l, ty / l * s); M.push(mat, y);
      }
    });
    for (let i = 0; i < profile.length - 1; i++) for (let j = 0; j < seg; j++) {
      const a = base + i * (seg + 1) + j, b = a + seg + 1;
      idx.push(a, b, a + 1, a + 1, b, b + 1);
    }
  };
  const nut = [], cup = [];
  for (let i = 0; i <= 18; i++) { const s = i / 18; nut.push([0.0083 * Math.pow(Math.sin(Math.PI / 2 * Math.min(1, s * 1.15)), 0.75) + 0.0002, -0.0125 + s * 0.0162]); }
  for (let i = 0; i <= 12; i++) { const s = i / 12; cup.push([0.0091 * Math.pow(Math.cos(Math.PI / 2 * s), 0.6) + 0.0012 * s, 0.0005 + 0.0092 * Math.sin(Math.PI / 2 * s)]); }
  cup.push([0.0012, 0.0115], [0.001, 0.0135], [0.0, 0.0138]);
  lathe(nut, 0);
  lathe(cup, 1);
  return {
    vao: vertexArray([{ loc: 0, data: new Float32Array(P), size: 3 }, { loc: 1, data: new Float32Array(N), size: 3 }, { loc: 2, data: new Float32Array(M), size: 2 }], new Uint16Array(idx)),
    count: idx.length,
  };
}
function modelMatrix(pos, rx, ry, rz, s = 1) {
  const cx = Math.cos(rx), sx = Math.sin(rx), cy = Math.cos(ry), sy = Math.sin(ry), cz = Math.cos(rz), sz = Math.sin(rz);
  // R = Ry * Rx * Rz, column-major
  const m00 = cy * cz + sy * sx * sz, m01 = cx * sz, m02 = -sy * cz + cy * sx * sz;
  const m10 = -cy * sz + sy * sx * cz, m11 = cx * cz, m12 = sy * sz + cy * sx * cz;
  const m20 = sy * cx, m21 = -sx, m22 = cy * cx;
  return new Float32Array([m00 * s, m01 * s, m02 * s, 0, m10 * s, m11 * s, m12 * s, 0, m20 * s, m21 * s, m22 * s, 0, pos[0], pos[1], pos[2], 1]);
}

// Water: up to 9 drops and their splashes, rewritten every frame.
const MAX_DROPS = 9 + 9 * 8;
function buildDrops() {
  const d0 = new Float32Array(MAX_DROPS * 4), d1 = new Float32Array(MAX_DROPS * 4);
  const specs = [
    { loc: 0, data: new Float32Array([-1, -1, 1, -1, 1, 1, -1, 1]), size: 2 },
    { loc: 1, data: d0, size: 4, divisor: 1, dynamic: true }, { loc: 2, data: d1, size: 4, divisor: 1, dynamic: true },
  ];
  return { vao: vertexArray(specs, new Uint16Array([0, 1, 2, 0, 2, 3])), d0, d1, b0: specs[1].buffer, b1: specs[2].buffer, n: 0 };
}

// ---------------------------------------------------------------- the shoot: camera, light and growth over time
// Keys: time, horizontal distance (m), azimuth (deg), camera height (m), target height (m), vertical fov (deg)
const CAM_KEYS = [
  [0.0, 0.16, 205, 0.04, 0.013, 30],
  [1.3, 0.14, 207, 0.036, 0.013, 30],
  [3.7, 0.13, 213, 0.034, 0.014, 30],
  [4.7, 0.17, 220, 0.03, 0.03, 32],
  [6.0, 0.36, 228, 0.05, 0.075, 32],
  [6.55, 1.1, 231, 0.42, 0.45, 33],
  [7.2, 4.0, 236, 0.85, 1.6, 34],
  [8.3, 10.0, 243, 1.5, 3.7, 36],
  [10.0, 12.5, 250, 1.6, 4.3, 38],
];
const LOG_CH = [true, false, true, true, false];
function hermite(keys, t, ch, log) {
  const n = keys.length, v = k => (log ? Math.log(keys[k][ch]) : keys[k][ch]);
  if (t <= keys[0][0]) return keys[0][ch];
  if (t >= keys[n - 1][0]) return keys[n - 1][ch];
  let i = 0;
  while (keys[i + 1][0] < t) i++;
  const t0 = keys[i][0], t1 = keys[i + 1][0], h = t1 - t0, u = (t - t0) / h;
  const slope = k => (k <= 0 ? (v(1) - v(0)) / (keys[1][0] - keys[0][0]) : k >= n - 1 ? (v(n - 1) - v(n - 2)) / (keys[n - 1][0] - keys[n - 2][0]) : (v(k + 1) - v(k - 1)) / (keys[k + 1][0] - keys[k - 1][0]));
  const m0 = slope(i) * h, m1 = slope(i + 1) * h, u2 = u * u, u3 = u2 * u;
  const y = (2 * u3 - 3 * u2 + 1) * v(i) + (u3 - 2 * u2 + u) * m0 + (-2 * u3 + 3 * u2) * v(i + 1) + (u3 - u2) * m1;
  return log ? Math.exp(y) : y;
}
function cameraAt(t) {
  const [d, az, cy, ty, fov] = [1, 2, 3, 4, 5].map((ch, k) => hermite(CAM_KEYS, t, ch, LOG_CH[k]));
  const a = az * DEG, pos = [Math.sin(a) * d, cy, Math.cos(a) * d], target = [0, ty, 0];
  return { pos, target, fov: fov * DEG, dist: len(sub(target, pos)), az, d };
}

// Growth: nothing until the acorn wakes, a seedling by step 4, then twenty years in two seconds.
function growAt(t) {
  if (t < 4.85) return 0;
  if (t < 6.0) return 0.1 * smooth(prog(t, 4.85, 6.0));
  const u = prog(t, 6.0, 8.0);
  return 0.1 + 0.9 * u * u * (2 - u);
}

// The sun: hazy dawn, breaking through for step 3, racing round the sky for step 4, golden for the end.
function sunAt(t) {
  const golden = [56, 6.5];
  let az = 30, el = 9, vis = lerp(0.12, 1, smooth(prog(t, 3.95, 4.7))), cloud = lerp(0.9, 0.3, smooth(prog(t, 3.9, 4.8)));
  if (t >= 6.0) {
    const u = prog(t, 6.0, 8.0), e = easeInOut(u);
    az = lerp(30, golden[0] + 720, e);
    el = lerp(9, golden[1], u) + 36 * Math.pow(Math.sin(Math.PI * 2 * e), 2);
  }
  if (t >= 8.0) { az = golden[0]; el = lerp(golden[1], 5.5, prog(t, 8, 10)); }
  const a = az * DEG, e = el * DEG;
  return { dir: [Math.cos(e) * Math.sin(a), Math.sin(e), Math.cos(e) * Math.cos(a)], vis, cloud };
}

const MOUND = t => smooth(prog(t, 1.65, 2.05));
const ACORN_X = -0.0125;
function acornMatrix(t, g) {
  if (t < 1.0) return null;
  const rest = terrainJS(ACORN_X, 0, 0) + 0.0082;
  let x = ACORN_X, y = rest, rx = 0, rz = Math.PI / 2;
  if (t < 1.28) {
    const u = prog(t, 1.0, 1.28);
    x += (1 - u) * 0.018; y = lerp(rest + 0.3, rest, u * u); rx = (1 - u) * 5; rz = Math.PI / 2 * u + (1 - u) * 0.5;
  } else if (t < 1.5) {
    const u = prog(t, 1.28, 1.5);
    y = rest + Math.sin(u * Math.PI) * 0.01; rz = Math.PI / 2 + Math.sin(u * Math.PI) * 0.25;
  }
  y -= smooth(prog(t, 1.65, 2.05)) * 0.0035;
  const s = 1 - smooth(prog(g, 0.2, 0.26));
  return s > 0 ? modelMatrix([x, y, 0], rx, 0.35, rz, s) : null;
}

// Nine drops of water from a can just out of frame, filmed in slow motion so each one can be seen.
const SLOW_G = 1.2, DROP_V0 = 0.25, DROP_H = 0.1;
const DROPS = (() => {
  const r = rng(99), list = [];
  for (let i = 0; i < 9; i++) {
    const land = 2.3 + i * 0.13 + r() * 0.05, a = r() * TAU, rr = 0.006 + r() * 0.022;
    const x = -0.006 + Math.cos(a) * rr, z = Math.sin(a) * rr;
    list.push({ land, x, z, y: terrainJS(x, z, 1), r: 0.0032 + r() * 0.0012, spray: Array.from({ length: 8 }, () => [r() * TAU, 0.5 + r() * 0.7, 0.8 + r() * 0.8]) });
  }
  return list;
})();
function updateDrops(D, t) {
  let n = 0;
  const put = (p, v, rad, alpha) => { D.d0.set([p[0], p[1], p[2], rad], n * 4); D.d1.set([v[0], v[1], v[2], alpha], n * 4); n++; };
  for (const d of DROPS) {
    const fall = (-DROP_V0 + Math.sqrt(DROP_V0 * DROP_V0 + 2 * SLOW_G * DROP_H)) / SLOW_G, t0 = d.land - fall;
    if (t >= t0 && t < d.land) {
      const tt = t - t0;
      put([d.x, d.y + DROP_H - DROP_V0 * tt - 0.5 * SLOW_G * tt * tt, d.z], [0, -(DROP_V0 + SLOW_G * tt), 0], d.r, 1);
    } else if (t >= d.land && t < d.land + 0.3) {
      const tt = t - d.land;
      if (tt > 0.28) continue;
      for (const [a, sp, up] of d.spray.slice(0, 6)) {
        const vy = up * 0.14 - SLOW_G * tt, v = [Math.cos(a) * sp * 0.09, vy, Math.sin(a) * sp * 0.09];
        put([d.x + v[0] * tt, d.y + 0.002 + up * 0.14 * tt - 0.5 * SLOW_G * tt * tt, d.z + v[2] * tt], v, 0.0006, 0.75 * (1 - tt / 0.28));
      }
    }
  }
  D.n = n;
  if (n) {
    gl.bindBuffer(gl.ARRAY_BUFFER, D.b0); gl.bufferSubData(gl.ARRAY_BUFFER, 0, D.d0, 0, n * 4);
    gl.bindBuffer(gl.ARRAY_BUFFER, D.b1); gl.bufferSubData(gl.ARRAY_BUFFER, 0, D.d1, 0, n * 4);
  }
}
const WET = new Float32Array(DROPS.flatMap(d => [d.x, d.z, d.land, 1]));

// Captions, drawn over the film like a nature documentary's lower thirds.
const STEPS = [
  { t: 1.0, end: 2.0, text: 'Plant a seed' }, { t: 2.0, end: 4.0, text: 'Water it' },
  { t: 4.0, end: 6.0, text: 'Let the sun in' }, { t: 6.0, end: 8.0, text: 'Be patient' },
  { t: 8.0, end: 99, text: 'Enjoy the shade' },
];
const SERIF = (s, style = 'italic 500') => `${style} ${s}px "Cormorant Garamond", "Iowan Old Style", Georgia, serif`;
const SANS = (s, w = 600) => `${w} ${s}px Figtree, "Segoe UI", "Helvetica Neue", Arial, sans-serif`;
function timelapseLabel(t) {
  const p = prog(t, 6.0, 8.0);
  if (p < 0.12) return `DAY ${1 + Math.floor(p / 0.12 * 29)}`;
  if (p < 0.25) return `MONTH ${2 + Math.floor((p - 0.12) / 0.13 * 10)}`;
  return `YEAR ${Math.min(20, 1 + Math.floor((p - 0.25) / 0.75 * 19.999))}`;
}
function drawCaptions(t) {
  const s = stage.width / 1280;
  out.save();
  out.scale(s, s);
  out.shadowColor = 'rgba(0, 0, 0, 0.55)';
  out.shadowBlur = 14 * s;
  out.fillStyle = '#f3eee2';
  const ta = prog(t, 0.3, 0.75) * (1 - prog(t, 1.45, 1.85));
  if (ta > 0) {
    out.globalAlpha = ta;
    out.textAlign = 'center';
    out.font = SERIF(62);
    out.fillText('How to grow a tree', 640, 372);
  }
  out.textAlign = 'left';
  STEPS.forEach((st, i) => {
    const a = prog(t, st.t + 0.05, st.t + 0.35) * (1 - prog(t, st.end - 0.3, st.end));
    if (a <= 0) return;
    out.globalAlpha = a;
    const y = 640 + (1 - a) * 6;
    out.fillRect(64, y - 58, 34, 1.5);
    out.font = SANS(13);
    if ('letterSpacing' in out) out.letterSpacing = '2.5px';
    out.fillText(`STEP ${i + 1} OF 5`, 64, y - 34);
    if ('letterSpacing' in out) out.letterSpacing = '0px';
    out.font = SERIF(46);
    out.fillText(st.text, 62, y + 4);
  });
  const ca = prog(t, 6.0, 6.2) * (1 - prog(t, 8.3, 8.7));
  if (ca > 0) {
    out.globalAlpha = ca;
    out.textAlign = 'right';
    out.font = SANS(12);
    if ('letterSpacing' in out) out.letterSpacing = '2.5px';
    out.fillText('TIME-LAPSE', 1216, 74);
    const labelW = out.measureText('TIME-LAPSE').width;
    if ('letterSpacing' in out) out.letterSpacing = '0px';
    out.font = SANS(30, 500);
    out.fillText(timelapseLabel(t), 1216, 110);
    out.fillStyle = '#e25b4a';
    out.beginPath();
    out.arc(1216 - labelW - 12, 69, 4, 0, TAU);
    out.fill();
  }
  out.restore();
}

// ---------------------------------------------------------------- rendering
let P = null, SET = null, RT = null, emptyVAO = null, shadowTex = null, shadowFB = null;
const SHADOW_SIZE = 2048;

function initRenderer() {
  gl = glCanvas.getContext('webgl2', { antialias: false, alpha: false, depth: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
  if (!gl) return false;
  HALF_FLOAT_OK = !!gl.getExtension('EXT_color_buffer_float');
  gl.getExtension('OES_texture_float_linear');
  P = {
    sky: program(FULLSCREEN_VS, SKY_FS),
    terrain: program(TERRAIN_VS, TERRAIN_FS),
    grass: program(GRASS_VS, GRASS_FS),
    tree: program(TREE_VS, TREE_FS), treeShadow: program(TREE_VS, DEPTH_FS),
    leaf: program(LEAF_VS, LEAF_FS), leafShadow: program(LEAF_VS, LEAF_SHADOW_FS),
    acorn: program(ACORN_VS, ACORN_FS), acornShadow: program(ACORN_VS, DEPTH_FS),
    drop: program(DROP_VS, DROP_FS),
    down: program(FULLSCREEN_VS, DOWN_FS), dof: program(FULLSCREEN_VS, DOF_FS), rays: program(FULLSCREEN_VS, RAYS_FS),
    bloomDown: program(FULLSCREEN_VS, BLOOM_DOWN_FS), bloomUp: program(FULLSCREEN_VS, BLOOM_UP_FS), final: program(FULLSCREEN_VS, FINAL_FS),
  };
  const oak = buildTree();
  SET = { terrain: buildTerrain(), grass: buildGrass(), tree: oak.tree, leaves: oak.leaves, oak, acorn: buildAcorn(), drops: buildDrops() };
  emptyVAO = gl.createVertexArray();
  shadowTex = texture(SHADOW_SIZE, SHADOW_SIZE, gl.DEPTH_COMPONENT24, gl.DEPTH_COMPONENT, gl.UNSIGNED_INT, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_COMPARE_MODE, gl.COMPARE_REF_TO_TEXTURE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_COMPARE_FUNC, gl.LEQUAL);
  shadowFB = framebuffer(null, shadowTex);
  gl.bindFramebuffer(gl.FRAMEBUFFER, shadowFB);
  gl.drawBuffers([gl.NONE]);
  gl.readBuffer(gl.NONE);
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  return true;
}

function makeTargets(w, h) {
  if (RT) {
    for (const f of [RT.msaa, RT.scene, RT.half, RT.dof, RT.rays, ...RT.bloom]) gl.deleteFramebuffer(f);
    for (const t of [RT.sceneTex, RT.depthTex, RT.half.tex, RT.dof.tex, RT.rays.tex, ...RT.bloom.map(b => b.tex)]) gl.deleteTexture(t);
    gl.deleteRenderbuffer(RT.cRB); gl.deleteRenderbuffer(RT.dRB);
  }
  const samples = Math.min(4, gl.getParameter(gl.MAX_SAMPLES));
  const msaa = gl.createFramebuffer(), cRB = gl.createRenderbuffer(), dRB = gl.createRenderbuffer();
  gl.bindRenderbuffer(gl.RENDERBUFFER, cRB);
  gl.renderbufferStorageMultisample(gl.RENDERBUFFER, samples, HALF_FLOAT_OK ? gl.RGBA16F : gl.RGBA8, w, h);
  gl.bindRenderbuffer(gl.RENDERBUFFER, dRB);
  gl.renderbufferStorageMultisample(gl.RENDERBUFFER, samples, gl.DEPTH_COMPONENT24, w, h);
  gl.bindFramebuffer(gl.FRAMEBUFFER, msaa);
  gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.RENDERBUFFER, cRB);
  gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.RENDERBUFFER, dRB);
  msaa.w = w; msaa.h = h;
  const sceneTex = colorTex(w, h), depthTex = texture(w, h, gl.DEPTH_COMPONENT24, gl.DEPTH_COMPONENT, gl.UNSIGNED_INT, gl.NEAREST);
  const target = (tw, th) => { const tex = colorTex(tw, th), f = framebuffer(tex); f.tex = tex; return f; };
  const hw = Math.max(1, w >> 1), hh = Math.max(1, h >> 1), bloom = [target(hw, hh)];
  for (let i = 0, bw = hw, bh = hh; i < 4; i++) { bw = Math.max(1, bw >> 1); bh = Math.max(1, bh >> 1); bloom.push(target(bw, bh)); }
  RT = { w, h, msaa, cRB, dRB, sceneTex, depthTex, scene: framebuffer(sceneTex, depthTex), half: target(hw, hh), dof: target(hw, hh), rays: target(hw, hh), bloom };
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
}

function pass(fb, prog, u) {
  gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
  gl.viewport(0, 0, fb ? fb.w : glCanvas.width, fb ? fb.h : glCanvas.height);
  gl.useProgram(prog);
  uniforms(prog, u);
  gl.bindVertexArray(emptyVAO);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
}

// Everything that changes with time, gathered in one place.
function stateAt(t) {
  const cam = cameraAt(t), sun = sunAt(t), g = growAt(t);
  const light = lightFor(sun.dir, sun.vis);
  const lum = c => 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  const scene = lum(light.sunCol) * 0.5 + lum(light.sky);
  return {
    t, cam, sun, g, light,
    exposure: 0.5 / (0.18 * scene + 0.3),
    wind: t < 6 ? 0.35 : t < 8 ? 0.35 + 0.6 * Math.sin(Math.PI * prog(t, 6, 8)) : 0.45,
    mound: MOUND(t), wetAll: smooth(prog(t, 2.4, 3.6)) * (1 - 0.6 * prog(t, 6, 8)),
    aperture: lerp(15, 1.4, prog(Math.log(cam.d), Math.log(0.3), Math.log(14))),
    canopy: smooth(prog(g, 0.45, 0.9)),
  };
}

function renderFrame(t) {
  const S = stateAt(t), { cam, light, sun } = S, w = RT.w, h = RT.h;
  const near = Math.max(0.004, cam.dist * 0.03), far = 700;
  const view = lookAt(cam.pos, cam.target), proj = perspective(cam.fov, w / h, near, far), viewProj = mat4mul(proj, view);

  // The sun's shadow map covers the subject and the ground between it and the camera.
  const focus = mix3(cam.target, [cam.pos[0], cam.target[1] * 0.5, cam.pos[2]], 0.35);
  const radius = clamp(cam.dist * 0.75 + 0.12 + Math.min(cam.target[1], 6) * 0.6, 0.18, 22);
  const lightPos = add(focus, mulS(sun.dir, radius + 14)), lightDepth = radius * 2 + 30;
  const lightView = lookAt(lightPos, focus, Math.abs(sun.dir[1]) > 0.99 ? [1, 0, 0] : [0, 1, 0]);
  const lightVP = mat4mul(ortho(-radius, radius, -radius, radius, 0.05, lightDepth), lightView);
  const texel = radius * 2 / SHADOW_SIZE;
  const acornM = acornMatrix(t, S.g);

  const common = {
    uTime: t, uGrow: S.g, uMound: S.mound, uWind: S.wind, uWindDir: [0.8, 0.6], uWetAll: S.wetAll, uWet: WET,
    uCamPos: cam.pos, uSunDir: sun.dir, uSunCol: light.sunCol, uSkyCol: light.sky,
    uBounceCol: mulS([0.09, 0.1, 0.05], (light.sunCol[1] * Math.max(sun.dir[1], 0) + light.sky[1] * 0.5)),
    uFogCol: light.fog, uFogSun: mulS(light.fogSun, 0.35), uFogDensity: 0.0022 + 0.003 * (1 - sun.vis),
    uShadowMat: lightVP, uShadow: T(7, shadowTex), uShadowTexel: 1 / SHADOW_SIZE,
    uShadowNormalOff: texel * 1.5, uShadowDepthBias: texel / lightDepth * 1.5,
    uCanopy: S.canopy, uCloudCover: sun.cloud, uShutter: 1 / 60,
  };

  // 1. shadow map
  gl.bindFramebuffer(gl.FRAMEBUFFER, shadowFB);
  gl.viewport(0, 0, SHADOW_SIZE, SHADOW_SIZE);
  gl.enable(gl.DEPTH_TEST);
  gl.depthFunc(gl.LEQUAL);
  gl.depthMask(true);
  gl.disable(gl.BLEND);
  gl.clear(gl.DEPTH_BUFFER_BIT);
  const shadowU = { ...common, uViewProj: lightVP, uShadow: undefined };
  delete shadowU.uShadow;
  if (S.g > 0) {
    gl.useProgram(P.treeShadow); uniforms(P.treeShadow, shadowU);
    gl.bindVertexArray(SET.tree.vao); gl.drawElements(gl.TRIANGLES, SET.tree.count, gl.UNSIGNED_INT, 0);
    gl.useProgram(P.leafShadow); uniforms(P.leafShadow, shadowU);
    gl.bindVertexArray(SET.leaves.vao); gl.drawElementsInstanced(gl.TRIANGLES, 6, gl.UNSIGNED_SHORT, 0, SET.leaves.instances);
  }
  if (acornM) {
    gl.useProgram(P.acornShadow); uniforms(P.acornShadow, { ...shadowU, uModel: acornM });
    gl.bindVertexArray(SET.acorn.vao); gl.drawElements(gl.TRIANGLES, SET.acorn.count, gl.UNSIGNED_SHORT, 0);
  }

  // 2. the scene, in HDR with 4x multisampling
  gl.bindFramebuffer(gl.FRAMEBUFFER, RT.msaa);
  gl.viewport(0, 0, w, h);
  gl.clearColor(0, 0, 0, 1);
  gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  const main = { ...common, uViewProj: viewProj };
  gl.depthMask(false);
  gl.useProgram(P.sky); uniforms(P.sky, { ...main, uInvViewProj: mat4inv(viewProj) });
  gl.bindVertexArray(emptyVAO); gl.drawArrays(gl.TRIANGLES, 0, 3);
  gl.depthMask(true);
  gl.useProgram(P.terrain); uniforms(P.terrain, main);
  gl.bindVertexArray(SET.terrain.vao); gl.drawElements(gl.TRIANGLES, SET.terrain.count, gl.UNSIGNED_INT, 0);
  gl.useProgram(P.grass); uniforms(P.grass, main);
  gl.bindVertexArray(SET.grass.vao); gl.drawElementsInstanced(gl.TRIANGLES, SET.grass.count, gl.UNSIGNED_SHORT, 0, SET.grass.instances);
  if (S.g > 0) {
    gl.useProgram(P.tree); uniforms(P.tree, main);
    gl.bindVertexArray(SET.tree.vao); gl.drawElements(gl.TRIANGLES, SET.tree.count, gl.UNSIGNED_INT, 0);
  }
  if (acornM) {
    gl.useProgram(P.acorn); uniforms(P.acorn, { ...main, uModel: acornM });
    gl.bindVertexArray(SET.acorn.vao); gl.drawElements(gl.TRIANGLES, SET.acorn.count, gl.UNSIGNED_SHORT, 0);
  }
  if (S.g > 0) {
    gl.enable(gl.SAMPLE_ALPHA_TO_COVERAGE);
    gl.useProgram(P.leaf); uniforms(P.leaf, main);
    gl.bindVertexArray(SET.leaves.vao); gl.drawElementsInstanced(gl.TRIANGLES, 6, gl.UNSIGNED_SHORT, 0, SET.leaves.instances);
    gl.disable(gl.SAMPLE_ALPHA_TO_COVERAGE);
  }
  updateDrops(SET.drops, t);
  if (SET.drops.n) {
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.depthMask(false);
    gl.useProgram(P.drop); uniforms(P.drop, main);
    gl.bindVertexArray(SET.drops.vao); gl.drawElementsInstanced(gl.TRIANGLES, 6, gl.UNSIGNED_SHORT, 0, SET.drops.n);
    gl.depthMask(true);
    gl.disable(gl.BLEND);
  }

  // 3. resolve the samples into textures
  gl.bindFramebuffer(gl.READ_FRAMEBUFFER, RT.msaa);
  gl.bindFramebuffer(gl.DRAW_FRAMEBUFFER, RT.scene);
  gl.blitFramebuffer(0, 0, w, h, 0, 0, w, h, gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT, gl.NEAREST);
  gl.bindFramebuffer(gl.READ_FRAMEBUFFER, null);
  gl.bindFramebuffer(gl.DRAW_FRAMEBUFFER, null);
  gl.disable(gl.DEPTH_TEST);

  // 4. the lens
  const lens = { uNear: near, uFar: far };
  pass(RT.half, P.down, { ...lens, uSrc: T(0, RT.sceneTex), uTexel: [1 / w, 1 / h], uThreshold: 0 });
  pass(RT.bloom[0], P.down, { ...lens, uSrc: T(0, RT.sceneTex), uTexel: [1 / w, 1 / h], uThreshold: 1.6 / S.exposure });
  for (let i = 0; i < 4; i++) pass(RT.bloom[i + 1], P.bloomDown, { ...lens, uSrc: T(0, RT.bloom[i].tex), uTexel: [1 / RT.bloom[i].w, 1 / RT.bloom[i].h] });
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.ONE, gl.ONE);
  for (let i = 4; i > 0; i--) pass(RT.bloom[i - 1], P.bloomUp, { ...lens, uSrc: T(0, RT.bloom[i].tex), uTexel: [1 / RT.bloom[i].w, 1 / RT.bloom[i].h] });
  gl.disable(gl.BLEND);
  const halfPx = h / 2 / 540;
  pass(RT.dof, P.dof, { ...lens, uSrc: T(0, RT.half.tex), uDepth: T(1, RT.depthTex), uTexel: [1 / RT.half.w, 1 / RT.half.h], uFocus: cam.dist, uAperture: S.aperture * halfPx, uMaxCoC: Math.max(1.5, S.aperture * halfPx * 1.4) });
  const sc = project(viewProj, add(cam.pos, mulS(sun.dir, 1000)));
  const onScreen = sc[3] > 0 ? 1 : 0;
  pass(RT.rays, P.rays, { ...lens, uSrc: T(0, RT.half.tex), uDepth: T(1, RT.depthTex), uSunUV: [sc[0] * 0.5 + 0.5, sc[1] * 0.5 + 0.5], uStrength: onScreen * 0.35 * sun.vis });
  pass(null, P.final, {
    ...lens, uScene: T(0, RT.sceneTex), uDof: T(1, RT.dof.tex), uBloom: T(2, RT.bloom[0].tex), uRays: T(3, RT.rays.tex), uDepth: T(4, RT.depthTex),
    uExposure: S.exposure, uBloomStrength: 0.035, uFocus: cam.dist, uAperture: S.aperture * halfPx * 2, uSeed: (t * 60) % 97, uFade: smooth(prog(t, 0, 0.45)),
    uRes: [w, h],
  });
  out.drawImage(glCanvas, 0, 0, stage.width, stage.height);
  drawCaptions(t);
}

// ---------------------------------------------------------------- sound: the meadow and a small score
function hz(name) {
  const m = /^([A-G])(#|b)?(\d)$/.exec(name);
  const semis = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 }[m[1]] + (m[2] === '#' ? 1 : m[2] === 'b' ? -1 : 0) + (+m[3] + 1) * 12;
  return 440 * 2 ** ((semis - 69) / 12);
}
function makeMix(ac, dest) {
  const out = ac.createGain(), comp = ac.createDynamicsCompressor(), trim = ac.createGain();
  comp.threshold.value = -16; comp.knee.value = 10; comp.ratio.value = 3; comp.attack.value = 0.006; comp.release.value = 0.25;
  trim.gain.value = 1.0;
  out.connect(comp).connect(trim).connect(dest);
  const len = Math.floor(ac.sampleRate * 3.2), ir = ac.createBuffer(2, len, ac.sampleRate);
  for (let c = 0; c < 2; c++) {
    const d = ir.getChannelData(c);
    for (let i = 0; i < len; i++) { const s = i / ac.sampleRate; d[i] = (Math.random() * 2 - 1) * Math.exp(-s * 2.2) * Math.min(1, s / 0.02); }
  }
  const verb = ac.createConvolver(), wet = ac.createGain();
  verb.buffer = ir;
  wet.gain.value = 0.32;
  verb.connect(wet).connect(out);
  const bus = (level, send) => {
    const g = ac.createGain(), s = ac.createGain();
    g.gain.value = level; s.gain.value = send;
    g.connect(out); g.connect(s).connect(verb);
    return g;
  };
  return { out, score: bus(0.7, 0.5), air: bus(0.9, 0.12), foley: bus(0.9, 0.12), birds: bus(0.5, 0.6) };
}

let whiteBuf = null, brownBuf = null;
function buffers(ac) {
  if (whiteBuf && whiteBuf.sampleRate === ac.sampleRate) return;
  const n = ac.sampleRate * 3;
  whiteBuf = ac.createBuffer(1, n, ac.sampleRate);
  brownBuf = ac.createBuffer(1, n, ac.sampleRate);
  const w = whiteBuf.getChannelData(0), b = brownBuf.getChannelData(0);
  let last = 0;
  for (let i = 0; i < n; i++) { w[i] = Math.random() * 2 - 1; last = (last + 0.02 * w[i]) / 1.02; b[i] = last * 3.5; }
}
function noise(ac, dest, when, dur, o = {}) {
  buffers(ac);
  const src = ac.createBufferSource(), flt = ac.createBiquadFilter(), g = ac.createGain();
  src.buffer = o.brown ? brownBuf : whiteBuf;
  src.loop = true;
  flt.type = o.type || 'bandpass';
  flt.Q.value = o.q ?? 1;
  flt.frequency.setValueAtTime(o.f0 ?? 2000, when);
  if (o.f1) flt.frequency.exponentialRampToValueAtTime(o.f1, when + dur);
  if (o.curve) g.gain.setValueCurveAtTime(o.curve, when, dur);
  else {
    const attack = o.attack ?? 0.003;
    g.gain.setValueAtTime(0, when);
    g.gain.linearRampToValueAtTime(o.gain ?? 0.3, when + attack);
    g.gain.exponentialRampToValueAtTime(0.0005, when + Math.max(dur, attack + 0.01));
  }
  let node = src.connect(flt).connect(g);
  if (o.pan !== undefined) { const p = ac.createStereoPanner(); p.pan.value = o.pan; node = node.connect(p); }
  node.connect(dest);
  src.start(when, Math.random() * 2);
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
    lfo.start(when); lfo.stop(when + dur + 0.05);
  }
  const attack = o.attack ?? 0.004;
  g.gain.setValueAtTime(0, when);
  g.gain.linearRampToValueAtTime(o.gain ?? 0.3, when + attack);
  g.gain.exponentialRampToValueAtTime(0.0005, when + dur);
  let node = osc.connect(g);
  if (o.pan !== undefined) { const p = ac.createStereoPanner(); p.pan.value = o.pan; node = node.connect(p); }
  node.connect(dest);
  osc.start(when); osc.stop(when + dur + 0.05);
}

// A felt piano: slightly stretched partials that fade faster the higher they are.
function piano(ac, dest, when, f, vel = 0.5, dur = 3.5) {
  const lp = ac.createBiquadFilter(), g = ac.createGain();
  lp.type = 'lowpass';
  lp.frequency.setValueAtTime(1800 + 3200 * vel, when);
  lp.frequency.exponentialRampToValueAtTime(700, when + dur);
  g.gain.value = 0.24 * vel;
  lp.connect(g).connect(dest);
  for (let n = 1; n <= 7; n++) {
    const fn = f * n * Math.sqrt(1 + 0.00035 * n * n);
    if (fn > 11000) break;
    const o = ac.createOscillator(), og = ac.createGain(), amp = Math.pow(n, -1.3), decay = dur / (1 + (n - 1) * 0.6);
    o.frequency.value = fn;
    og.gain.setValueAtTime(0, when);
    og.gain.linearRampToValueAtTime(amp, when + 0.003);
    og.gain.exponentialRampToValueAtTime(amp * 0.35, when + 0.3);
    og.gain.exponentialRampToValueAtTime(0.0001, when + decay);
    o.connect(og).connect(lp);
    o.start(when); o.stop(when + decay + 0.05);
  }
  noise(ac, dest, when, 0.025, { f0: Math.min(7000, f * 4), q: 1.2, gain: 0.018 * vel });
}
// A string section: three detuned saws per note, a slow bow and a little vibrato.
function strings(ac, dest, when, notes, dur, vel = 1, attack = 0.9) {
  for (const name of notes) {
    const lp = ac.createBiquadFilter(), g = ac.createGain(), vib = ac.createOscillator(), vg = ac.createGain();
    lp.type = 'lowpass';
    lp.Q.value = 0.5;
    lp.frequency.setValueAtTime(420, when);
    lp.frequency.linearRampToValueAtTime(1500 + 700 * vel, when + attack);
    g.gain.setValueAtTime(0, when);
    g.gain.linearRampToValueAtTime(0.045 * vel, when + attack);
    g.gain.setValueAtTime(0.045 * vel, when + Math.max(attack, dur - 0.5));
    g.gain.linearRampToValueAtTime(0, when + dur);
    lp.connect(g).connect(dest);
    vib.frequency.value = 5.1;
    vg.gain.value = 5;
    vib.connect(vg);
    for (const det of [-7, 0, 6]) {
      const o = ac.createOscillator();
      o.type = 'sawtooth';
      o.frequency.value = hz(name);
      o.detune.value = det;
      vg.connect(o.detune);
      o.connect(lp);
      o.start(when); o.stop(when + dur + 0.05);
    }
    vib.start(when); vib.stop(when + dur + 0.05);
  }
}
function bird(ac, dest, when, kind, pan, vol) {
  if (kind === 'trill') {
    for (let i = 0; i < 7; i++) { const f0 = 3100 + Math.random() * 700; tone(ac, dest, when + i * 0.068, 0.05, { f0, f1: f0 * 1.35, glide: 0.04, gain: 0.05 * vol, pan }); }
  } else if (kind === 'whistle') {
    for (const [dt, f0, f1, d] of [[0, 1900, 2350, 0.2], [0.24, 2550, 2200, 0.15], [0.42, 2100, 2650, 0.24]]) {
      tone(ac, dest, when + dt, d, { f0, f1, glide: d * 0.8, gain: 0.06 * vol, attack: 0.025, vib: 45, vibRate: 24, pan });
    }
  } else {
    for (const dt of [0, 0.13]) tone(ac, dest, when + dt, 0.07, { f0: 2900, f1: 4300, glide: 0.05, gain: 0.05 * vol, pan });
  }
}
const crumble = (ac, dest, when, dur, grains, gain) => {
  for (let i = 0; i < grains; i++) noise(ac, dest, when + Math.random() * dur, 0.008 + Math.random() * 0.018, { f0: 1200 + Math.random() * 3200, q: 2.5, gain: gain * (0.4 + Math.random() * 0.6) });
};
const creak = (ac, dest, when, dur) => noise(ac, dest, when, dur, { brown: true, f0: 150, f1: 230, q: 14, gain: 0.35, attack: dur * 0.3 });

// The score. Every cue lands on something in the picture.
function scheduleScore(ac, mix, T) {
  const at = s => T + s, { score, air, foley, birds } = mix;
  const curve = (fn, n = 120) => Float32Array.from({ length: n + 1 }, (_, i) => fn(i / n * 10.4));
  noise(ac, air, at(0), 10.4, { brown: true, type: 'lowpass', f0: 420, curve: curve(s => 0.16 + 0.05 * Math.sin(s * 1.3) + 0.24 * (s > 6 && s < 8 ? Math.sin(Math.PI * (s - 6) / 2) : 0) + (s > 8 ? 0.04 : 0)) });
  noise(ac, air, at(0), 10.4, { f0: 3200, q: 0.7, curve: curve(s => 0.012 + clamp((s - 6.6) / 1.4) * 0.07 * (0.8 + 0.2 * Math.sin(s * 9))) });

  [[0.4, 'whistle', -0.6, 0.5], [1.9, 'trill', 0.5, 0.4], [3.05, 'chirp', -0.3, 0.45], [4.5, 'whistle', 0.35, 0.7], [5.5, 'trill', -0.5, 0.5],
    [8.45, 'whistle', 0.4, 1], [9.15, 'chirp', -0.25, 0.9], [9.55, 'trill', 0.55, 0.8]].forEach(([s, k, p, v]) => bird(ac, birds, at(s), k, p, v));
  for (let i = 0; i < 10; i++) bird(ac, birds, at(6.15 + i * 0.17), 'chirp', Math.random() * 1.6 - 0.8, 0.25); // days flying past

  tone(ac, foley, at(1.28), 0.12, { f0: 150, f1: 60, gain: 0.35 });
  crumble(ac, foley, at(1.29), 0.25, 10, 0.1);
  tone(ac, foley, at(1.5), 0.05, { f0: 420, f1: 300, gain: 0.08 });
  crumble(ac, foley, at(1.65), 0.4, 16, 0.07);
  for (const d of DROPS) {
    noise(ac, foley, at(d.land), 0.006, { type: 'highpass', f0: 3000, gain: 0.1 });
    tone(ac, foley, at(d.land), 0.04, { f0: 520 + Math.random() * 120, f1: 250, gain: 0.12 });
    crumble(ac, foley, at(d.land + 0.005), 0.05, 3, 0.03);
  }
  crumble(ac, foley, at(5.1), 0.45, 14, 0.06);
  creak(ac, foley, at(5.2), 0.35);
  noise(ac, foley, at(6.35), 0.9, { f0: 300, f1: 1400, q: 1.3, gain: 0.09, attack: 0.4 });
  noise(ac, foley, at(7.25), 0.9, { f0: 300, f1: 1600, q: 1.3, gain: 0.11, attack: 0.4 });
  creak(ac, foley, at(6.8), 0.6);
  creak(ac, foley, at(7.5), 0.5);

  [[0.25, 'D3', 0.45, 5], [0.25, 'A3', 0.35, 5], [0.9, 'F#5', 0.55], [1.45, 'E5', 0.45], [2.0, 'D5', 0.55], [2.0, 'D4', 0.3],
    [2.6, 'A4', 0.45], [3.2, 'B4', 0.5], [3.2, 'G3', 0.35], [3.75, 'A4', 0.45], [4.1, 'D5', 0.55],
    [4.55, 'F#5', 0.42], [4.7, 'A5', 0.42], [4.85, 'D6', 0.4], [5.3, 'E5', 0.45], [5.75, 'F#5', 0.45],
    [6.0, 'B4', 0.45], [6.33, 'C#5', 0.5], [6.67, 'D5', 0.55], [7.0, 'E5', 0.6], [7.33, 'F#5', 0.65], [7.67, 'A5', 0.7],
    [8.0, 'D3', 0.6, 5], [8.0, 'A3', 0.5, 5], [8.0, 'D4', 0.5, 5], [8.0, 'F#4', 0.5, 5], [8.0, 'A4', 0.5, 5], [8.0, 'D5', 0.55, 5],
    [8.9, 'F#5', 0.4], [9.35, 'A5', 0.35]].forEach(([s, n, v, d]) => piano(ac, score, at(s), hz(n), v, d || 3.5));
  strings(ac, score, at(4.0), ['D3', 'A3', 'F#4', 'A4'], 2.1, 0.7, 1.2);
  strings(ac, score, at(6.0), ['B2', 'F#3', 'D4', 'B4'], 0.8, 0.8, 0.35);
  strings(ac, score, at(6.7), ['G2', 'D3', 'B3', 'G4'], 0.75, 0.9, 0.3);
  strings(ac, score, at(7.35), ['A2', 'E3', 'C#4', 'A4'], 0.75, 1.0, 0.3);
  strings(ac, score, at(8.0), ['D2', 'A2', 'D3', 'F#3', 'A3', 'D4', 'F#4'], 2.4, 1.1, 0.25);
  for (let i = 0; i < 8; i++) {
    const s = 6.0 + i * 0.25, f = hz(s < 6.7 ? 'B1' : s < 7.35 ? 'G1' : 'A1');
    tone(ac, score, at(s), 0.2, { type: 'sawtooth', f0: f, gain: 0.05 + i * 0.008 });
  }
  tone(ac, foley, at(8.0), 1.4, { f0: 58, f1: 34, gain: 0.3, attack: 0.01 });
  noise(ac, foley, at(8.0), 0.5, { type: 'lowpass', f0: 180, gain: 0.25 });
  for (const n of ['D6', 'A6', 'F#6']) tone(ac, score, at(8.05), 2.2, { f0: hz(n), gain: 0.018, attack: 0.6, vib: 4, vibRate: 5 });
  mix.out.gain.setValueAtTime(1, at(9.6));
  mix.out.gain.linearRampToValueAtTime(0.0001, at(10.4));
}

// ---------------------------------------------------------------- playback
const playBtn = document.getElementById('play');
const againBtn = document.getElementById('again');
const soundBtn = document.getElementById('sound');
const notice = document.getElementById('notice');
let ac = null, master = null, mix = null, audioClock = false;
let startAt = 0, clockStart = 0, playing = false, raf = 0, shownT = DURATION, renderScale = 1, slowFrames = 0, lastStamp = 0;
let muted = false;
try { muted = localStorage.getItem('tree-film:muted') === '1'; } catch (e) { /* storage blocked */ }

function now() {
  if (audioClock) return ac.currentTime - startAt - (ac.outputLatency || 0);
  return performance.now() / 1000 - clockStart;
}
async function play() {
  if (!gl) return;
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
    startAt = ac.currentTime + 0.2;
    scheduleScore(ac, mix, startAt);
  }
  clockStart = performance.now() / 1000 + 0.2;
  playing = true;
  lastStamp = 0;
  setUI();
  cancelAnimationFrame(raf);
  raf = requestAnimationFrame(tick);
}
function tick(stamp) {
  const t = now();
  shownT = clamp(t, 0, DURATION);
  renderFrame(shownT);
  // a machine that can't keep up gets a smaller picture, once
  if (lastStamp && stamp - lastStamp > 45) slowFrames++;
  lastStamp = stamp;
  if (slowFrames > 20 && renderScale > 0.7) { renderScale = 0.66; slowFrames = 0; layout(true); }
  if (t < DURATION + 0.1) raf = requestAnimationFrame(tick);
  else { playing = false; shownT = DURATION; renderFrame(DURATION); setUI(); }
}
function setUI() {
  playBtn.hidden = playing || !gl;
  playBtn.querySelector('.label').textContent = shownT >= DURATION && lastStamp ? 'Watch again' : 'Play';
  againBtn.textContent = playing ? 'Start over' : 'Play';
  againBtn.disabled = !gl;
  soundBtn.setAttribute('aria-pressed', String(!muted));
  soundBtn.textContent = muted ? 'Sound off' : 'Sound on';
}
function toggleSound() {
  muted = !muted;
  try { localStorage.setItem('tree-film:muted', muted ? '1' : '0'); } catch (e) { /* storage blocked */ }
  if (master) master.gain.setTargetAtTime(muted ? 0 : 1, ac.currentTime, 0.03);
  setUI();
}

// The visible canvas follows the page; the film renders at up to 1080p behind it.
function layout(force = false) {
  const box = stage.getBoundingClientRect(), dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = Math.round(clamp(box.width * dpr, 480, 2560)), h = Math.round(w * 9 / 16);
  const rw = Math.round(Math.min(w, 1920) * renderScale), rh = Math.round(rw * 9 / 16);
  if (!force && w === stage.width && RT && RT.w === rw) return;
  stage.width = w; stage.height = h;
  glCanvas.width = rw; glCanvas.height = rh;
  makeTargets(rw, rh);
}

function boot() {
  let ok = false;
  try { ok = initRenderer(); } catch (e) { console.error(e); ok = false; gl = null; }
  if (!ok) {
    gl = null;
    notice.hidden = false;
    setUI();
    return;
  }
  const faces = ['italic 500 40px "Cormorant Garamond"', '600 16px Figtree'];
  Promise.race([Promise.all(faces.map(f => document.fonts.load(f))), new Promise(r => setTimeout(r, 2500))]).catch(() => {}).then(() => {
    layout();
    renderFrame(shownT);
    setUI();
    document.body.classList.add('ready');
  });
  let timer = 0;
  window.addEventListener('resize', () => {
    clearTimeout(timer);
    timer = setTimeout(() => { layout(); if (!playing) renderFrame(shownT); }, 150);
  });
  playBtn.addEventListener('click', play);
  againBtn.addEventListener('click', play);
  soundBtn.addEventListener('click', toggleSound);
  stage.addEventListener('click', () => { if (!playing) play(); });
}

// For scrubbing from the console: treeFilm.seek(4.2)
window.treeFilm = { play, seek(t) { shownT = clamp(+t || 0, 0, DURATION); renderFrame(shownT); } };
boot();
})();
