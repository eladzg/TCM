// The opening screen's figure: the body as a cloud of dots, the 14 channels as streams of coloured dots
// with a slow glint running along them, and the 361 points as brighter dots on both sides.
// The dots come from hero_points.js (tools/interview/build_hero_points.py: the skin of body.glb, "Male base
// muscular anatomy" by Harshit Prajapati, Sketchfab, CC BY 4.0) and the channels from points3d.js, so
// the 4 MB model is not loaded here. Everything is drawn in two calls of one small shader, so it stays
// light: the dots gather into the body when it first shows, part around the pointer, breathe slowly, and
// the figure turns freely with inertia when dragged. Reduced motion stills the gathering and the breath.
import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.160.0/+esm";

const HP = window.TCM_HERO_POINTS;
const P3 = window.TCM_POINTS3D || {};
const PATHS = window.TCM_PATHS3D || null;
const BM = window.TCMBodyMap;
const CENTRE = -0.075;
const reduced = () => window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

function webgl() {
  try { const c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch (e) { return false; }
}
function bytes(b64) { const s = atob(b64), a = new Uint8Array(s.length); for (let i = 0; i < s.length; i++) a[i] = s.charCodeAt(i); return a.buffer; }
function cssColor(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  try { return new THREE.Color(v || fallback); } catch (e) { return new THREE.Color(fallback); }
}

const VS = `
attribute vec3 color; attribute vec3 aRand; attribute float aU; attribute float aCh; attribute float aSel;
uniform float uTime, uForm, uScale, uSize, uMax, uFlow, uBreath, uAspect, uFocus;
uniform float uHi[14];
uniform float uHov;
varying vec3 vCol; varying float vA;
float hash(float n) { return fract(sin(n) * 43758.5453); }
void main() {
  vec3 p = position;
  float ph = aRand.x * 6.2831;
  p += normal * sin(uTime * 1.1 + ph) * 0.00022 * uBreath;
  vec3 dir = normalize(vec3(hash(aRand.x * 91.7) - .5, hash(aRand.y * 37.3) - .5, hash(aRand.z * 53.1) - .5));
  float f = smoothstep(0., 1., clamp(uForm * 1.35 - aRand.y * .35, 0., 1.));
  p += dir * (1. - f) * (0.05 + aRand.z * 0.07);
  vec4 mv = modelViewMatrix * vec4(p, 1.);
  vec3 n = normalize(normalMatrix * normal);
  float facing = dot(n, normalize(-mv.xyz));
  vec4 cp = projectionMatrix * mv;
  gl_Position = cp;
  float front = smoothstep(-.1, .45, facing);
  float lit = max(dot(n, normalize(vec3(-.45, .55, .7))), 0.);
  gl_PointSize = clamp(uSize * (0.75 + aRand.z * 0.5) * (.55 + .45 * front) * uScale / -mv.z, 1., uMax);
  float glint = uFlow > 0. ? pow(fract(aU * 18. - uTime * .22), 10.) : 0.;
  float pt = uFlow > 0. && aU < -.5 ? 1. : 0.;   // an acupuncture point, not a step along a channel
  gl_PointSize = min(gl_PointSize * (1. + pt * .7), uMax * 1.3);
  vCol = color * (1. + glint * 1.8 + pt * .3);
  vA = mix(.06, 1., front) * (.35 + .85 * lit) * (.55 + .45 * f);
  // Focus: the channels of the chosen points lead, the rest fall back; the chosen points pulse.
  float hi = aCh > -.5 ? uHi[int(aCh + .5)] : 0.;
  vA *= uFlow > 0. ? mix(1., mix(.14, 1.3, hi), uFocus) : mix(1., .6, uFocus);
  gl_PointSize *= uFlow > 0. ? mix(1., mix(.8, 1.3, hi), uFocus) : 1.;
  float sel = step(.5, aSel) * uFocus;
  gl_PointSize = mix(gl_PointSize, min(gl_PointSize * (2.4 + .5 * sin(uTime * 2.6)), uMax * 2.6), sel);
  vCol = mix(vCol, mix(vec3(1., .97, .86), vec3(.95, .55, .45), step(1.5, aSel)), sel * .6);
  vA = mix(vA, 1.4, sel);
  // The channel under the pointer lights up.
  float hov = uFlow > 0. && abs(aCh - uHov) < .5 ? 1. : 0.;
  vA *= 1. + hov * 1.2; gl_PointSize *= 1. + hov * .35; vCol = mix(vCol, vec3(1.), hov * .15);
}`;
const FS = `
uniform float uAlpha; varying vec3 vCol; varying float vA;
void main() {
  float d = length(gl_PointCoord - .5);
  if (d > .5) discard;
  gl_FragColor = vec4(vCol, vA * uAlpha * smoothstep(.5, .15, d));
}`;

function material(o) {
  return new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 }, uForm: { value: 0 }, uScale: { value: 800 }, uSize: { value: o.size }, uMax: { value: o.max },
      uFlow: { value: o.flow ? 1 : 0 }, uBreath: { value: 1 }, uAspect: { value: 1 }, uAlpha: { value: o.alpha },
      uHov: { value: -1 }, uFocus: { value: 0 }, uHi: { value: new Array(14).fill(0) }
    },
    vertexShader: VS, fragmentShader: FS, transparent: true, depthWrite: false, depthTest: false
  });
}

// The body's dots, from hero_points.js.
function bodyCloud() {
  const n = HP.n, q = new Uint16Array(bytes(HP.p)), nr = new Int8Array(bytes(HP.nrm));
  const pos = new Float32Array(n * 3), nor = new Float32Array(n * 3), rnd = new Float32Array(n * 3), col = new Float32Array(n * 3);
  for (let i = 0; i < n * 3; i++) {
    const k = i % 3;
    pos[i] = HP.lo[k] + q[i] / 65535 * (HP.hi[k] - HP.lo[k]);
    nor[i] = nr[i] / 127;
    rnd[i] = Math.random();
    col[i] = 1;
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setAttribute("normal", new THREE.BufferAttribute(nor, 3));
  g.setAttribute("aRand", new THREE.BufferAttribute(rnd, 3));
  g.setAttribute("color", new THREE.BufferAttribute(col, 3));
  g.setAttribute("aU", new THREE.BufferAttribute(new Float32Array(n), 1));
  g.setAttribute("aCh", new THREE.BufferAttribute(new Float32Array(n).fill(-1), 1));
  g.setAttribute("aSel", new THREE.BufferAttribute(new Float32Array(n), 1));
  return g;
}

// The channels as dots along their lines (both sides), and the points as bigger dots.
const CHS = ["LU", "LI", "ST", "SP", "HT", "SI", "BL", "KI", "PC", "TE", "GB", "LR", "CV", "GV"];
function channelCloud() {
  const pos = [], nor = [], col = [], u = [], chi = [], where = {};
  let cur = -1;
  const add = (p, nn, c, uu) => { pos.push(p.x, p.y, p.z); nor.push(nn.x, nn.y, nn.z); col.push(c.r, c.g, c.b); u.push(uu); chi.push(cur); };
  const color = (ch) => new THREE.Color(BM ? BM.channels([ch + "1"])[0].color : "#b9cf9c");
  const out = new THREE.Vector3(0, 0, 1);
  if (PATHS) Object.keys(PATHS).forEach((ch) => {
    const c = color(ch);
    cur = CHS.indexOf(ch);
    (ch === "CV" || ch === "GV" ? [1] : [1, -1]).forEach((side) => {
      PATHS[ch].forEach((pl) => {
        let len = 0;
        for (let i = 1; i < pl.length; i++) {
          const a = new THREE.Vector3(pl[i - 1][0] * side, pl[i - 1][1], pl[i - 1][2]);
          const b = new THREE.Vector3(pl[i][0] * side, pl[i][1], pl[i][2]);
          const d = a.distanceTo(b), steps = Math.max(1, Math.round(d / 0.0008));
          const nn = new THREE.Vector3(a.x, 0, a.z).normalize();
          for (let s = 0; s < steps; s++) add(a.clone().lerp(b, s / steps), nn.lengthSq() ? nn : out, c, len + d * s / steps);
          len += d;
        }
      });
    });
  });
  const lineCount = u.length;
  Object.keys(P3).forEach((id) => {
    const p = P3[id], ch = (/^([A-Z]+)/.exec(id) || [])[1];
    const c = color(ch).lerp(new THREE.Color(1, 1, 1), 0.15);
    cur = CHS.indexOf(ch); where[id] = [];
    (/^(CV|GV)/.test(id) ? [1] : [1, -1]).forEach((s) => {
      where[id].push(u.length);
      add(new THREE.Vector3(p[0] * s, p[1], p[2]), new THREE.Vector3(p[3] * s, p[4], p[5]), c, -1);
    });
  });
  const g = new THREE.BufferGeometry(), n = u.length;
  const rnd = new Float32Array(n * 3); for (let i = 0; i < rnd.length; i++) rnd[i] = Math.random();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("normal", new THREE.Float32BufferAttribute(nor, 3));
  g.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
  g.setAttribute("aU", new THREE.Float32BufferAttribute(u, 1));
  g.setAttribute("aRand", new THREE.BufferAttribute(rnd, 3));
  g.setAttribute("aCh", new THREE.Float32BufferAttribute(chi, 1));
  g.setAttribute("aSel", new THREE.BufferAttribute(new Float32Array(n), 1));
  g.userData.lineCount = lineCount;
  g.userData.where = where;
  return g;
}

// opts: height() -> the stage's height; onframe(viewer) -> after every frame.
function create(host, opts) {
  opts = opts || {};
  const wrap = document.createElement("div");
  wrap.className = "h3d";
  host.appendChild(wrap);
  const renderer = new THREE.WebGLRenderer({ antialias: false, alpha: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
  renderer.domElement.style.touchAction = "pan-y";
  wrap.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, 1, 0.005, 5);
  camera.position.set(0, CENTRE + 0.01, 0.4);
  const rig = new THREE.Group(), inner = new THREE.Group();
  rig.position.set(0, CENTRE, 0); inner.position.set(0, -CENTRE, 0);
  rig.add(inner); scene.add(rig);

  const bodyMat = material({ size: 0.00042, max: 3, alpha: 0.3 });   // the skin: fine, dense and half see-through
  const lineMat = material({ size: 0.0011, max: 7, alpha: 1, flow: true });   // the channels and points stand out
  const body = new THREE.Points(bodyCloud(), bodyMat);
  const lines = new THREE.Points(channelCloud(), lineMat);
  body.frustumCulled = lines.frustumCulled = false;
  inner.add(body); inner.add(lines);
  const mats = [bodyMat, lineMat];

  function applyTheme() {
    const light = document.documentElement.getAttribute("data-theme") === "light" ||
      (!document.documentElement.hasAttribute("data-theme") && false);
    const ink = cssColor("--ink", "#f0eadc");
    const c = body.geometry.getAttribute("color");
    for (let i = 0; i < c.count; i++) c.setXYZ(i, ink.r, ink.g, ink.b);
    c.needsUpdate = true;
    mats.forEach((m) => { m.blending = light ? THREE.NormalBlending : THREE.AdditiveBlending; m.needsUpdate = true; });
    bodyMat.uniforms.uAlpha.value = light ? 0.26 : 0.3;
    request();
  }

  // ---- motion: drag with inertia, a slow sway, a faint lean toward the pointer, the camera on a rail ----
  let yaw = 0, vy = 0, drag = null, lastDrag = 0, goalYaw = null, mx = 0, my = 0, sx = 0, sy = 0;
  let focusOn = 0, focusGoal = 0, camGoal = null, turn = 0, form = reduced() ? 1 : 0, t0 = performance.now(), visible = true, raf = 0;
  const goalPos = new THREE.Vector3();
  const el = renderer.domElement;
  el.addEventListener("pointerdown", (e) => { drag = { x: e.clientX }; vy = 0; goalYaw = null; request(); });
  window.addEventListener("pointermove", (e) => {
    mx = e.clientX / window.innerWidth * 2 - 1; my = e.clientY / window.innerHeight * 2 - 1;
    if (!drag && e.pointerType === "mouse") { if (e.target === el) hoverAt(e.clientX, e.clientY); else if (hovKey) hoverAt(-1e4, -1e4); }
    if (drag) { const dx = e.clientX - drag.x; drag.x = e.clientX; vy = dx * 0.006; yaw += vy; }
    request();
  }, { passive: true });
  const end = () => { if (drag) { drag = null; lastDrag = performance.now(); } };
  window.addEventListener("pointerup", end); el.addEventListener("pointercancel", end);
  el.addEventListener("pointerleave", () => hoverAt(-1e4, -1e4));

  // ---- hover: the point or channel under the pointer names itself ----
  const tip = document.createElement("div");
  tip.className = "h3d-tip"; tip.hidden = true; tip.setAttribute("role", "status");
  wrap.appendChild(tip);
  const ELEM = { LU: "מתכת", LI: "מתכת", ST: "אדמה", SP: "אדמה", HT: "אש", SI: "אש", PC: "אש", TE: "אש", BL: "מים", KI: "מים", GB: "עץ", LR: "עץ" };
  const YIN = { LU: "יין, יד", PC: "יין, יד", HT: "יין, יד", LI: "יאנג, יד", TE: "יאנג, יד", SI: "יאנג, יד",
    SP: "יין, רגל", LR: "יין, רגל", KI: "יין, רגל", ST: "יאנג, רגל", GB: "יאנג, רגל", BL: "יאנג, רגל" };
  const chName = (ch) => { const c = BM && BM.channels([ch + "1"])[0]; return c ? c.he : ch; };
  const chInfo = (ch) => ch === "CV" ? "כלי מיוחד · קו האמצע הקדמי" : ch === "GV" ? "כלי מיוחד · קו האמצע האחורי"
    : chName(ch) + " · יסוד " + ELEM[ch] + " · " + YIN[ch];
  const wp = new THREE.Vector3(), wn = new THREE.Vector3(), cam = new THREE.Vector3();
  let hovKey = null, pend = null;
  function hoverAt(x, y) {
    if (pend === null) requestAnimationFrame(() => { const q = pend; pend = null; pick(q[0], q[1]); });
    pend = [x, y];
  }
  function near(arr, i, rect, x, y, lim) {
    wp.set(arr[i * 3], arr[i * 3 + 1], arr[i * 3 + 2]).applyMatrix4(inner.matrixWorld);
    const nrm = lines.geometry.getAttribute("normal").array;
    wn.set(nrm[i * 3], nrm[i * 3 + 1], nrm[i * 3 + 2]).applyQuaternion(rig.quaternion);
    if (cam.subVectors(camera.position, wp).dot(wn) < 0) return Infinity;   // on the far side of the body
    wp.project(camera);
    const dx = (wp.x + 1) / 2 * rect.width - x, dy = (1 - wp.y) / 2 * rect.height - y, d = Math.hypot(dx, dy);
    return d < lim ? d : Infinity;
  }
  function pick(cx, cy) {
    const rect = el.getBoundingClientRect(), x = cx - rect.left, y = cy - rect.top;
    let best = null;
    if (x >= 0 && y >= 0 && x <= rect.width && y <= rect.height && form >= 1) {
      const g = lines.geometry, pos = g.getAttribute("position").array, chA = g.getAttribute("aCh").array, where = g.userData.where;
      let bd = Infinity;
      Object.keys(where).forEach((id) => where[id].forEach((i) => {
        const d = near(pos, i, rect, x, y, 11); if (d < bd) { bd = d; best = { id, ch: (/^([A-Z]+)/.exec(id) || [])[1] }; }
      }));
      if (!best) for (let i = 0; i < g.userData.lineCount; i += 2) {
        const d = near(pos, i, rect, x, y, 6); if (d < bd) { bd = d; best = { ch: CHS[chA[i]] }; }
      }
    }
    const key = best ? (best.id || best.ch) : null;
    if (key !== hovKey) {
      hovKey = key;
      lineMat.uniforms.uHov.value = best ? CHS.indexOf(best.ch) : -1;
      tip.textContent = "";
      if (best) {
        const T = window.TCMTreatment, add = (cls, text) => { const e = document.createElement(cls === "b" ? "b" : "span"); if (cls !== "b") e.className = cls; e.textContent = text; tip.appendChild(e); };
        if (best.id) {
          add("b", T && T.label ? T.label(best.id) : best.id);
          const loc = T && T.tx && T.tx.points[best.id] ? T.tx.points[best.id].loc || "" : "";
          if (loc) add("loc", loc.length > 180 ? loc.slice(0, 177) + "…" : loc);
          add("ch", chInfo(best.ch));
        } else {
          add("b", best.ch + " · " + chName(best.ch));
          add("ch", chInfo(best.ch));
        }
      }
      tip.hidden = !best;
      el.style.cursor = best ? "help" : "";
      request();
    }
    if (best) {
      const left = Math.min(Math.max(8, x + 16), rect.width - tip.offsetWidth - 8), top = Math.min(Math.max(8, y + 14), rect.height - tip.offsetHeight - 8);
      tip.style.transform = "translate(" + Math.round(left) + "px," + Math.round(top) + "px)";
    }
  }

  function step(now) {
    const still = reduced();
    let moving = !!drag;
    if (!drag) { yaw += vy; vy *= 0.95; if (Math.abs(vy) > 1e-4) moving = true; }
    if (!drag && goalYaw === null && lastDrag && now - lastDrag > 2500) {
      goalYaw = 2 * Math.PI * Math.round(yaw / (2 * Math.PI)); lastDrag = 0;
    }
    if (goalYaw !== null) { yaw += (goalYaw - yaw) * 0.05; if (Math.abs(goalYaw - yaw) < 0.001) { yaw = goalYaw; goalYaw = null; } else moving = true; }
    if (camGoal) {
      goalPos.set(0, camGoal.y, camGoal.dist);
      camera.position.lerp(goalPos, still ? 1 : 0.12);
      if (camera.position.distanceTo(goalPos) > 1e-5) moving = true;
      camera.lookAt(0, camera.position.y, 0);
    }
    if (form < 1) { form = Math.min(1, (now - t0) / 2200); moving = true; }
    focusOn += (focusGoal - focusOn) * (still ? 1 : 0.06);
    if (Math.abs(focusGoal - focusOn) > 0.002) moving = true;
    sx += ((still ? 0 : mx * 0.05) - sx) * 0.03;
    sy += ((still ? 0 : my * 0.025) - sy) * 0.03;
    const sway = still ? 0 : Math.sin(now * 0.00035) * 0.02;
    if (camGoal) { turn += ((camGoal.turn || 0) - turn) * (still ? 1 : 0.1); if (Math.abs((camGoal.turn || 0) - turn) > 1e-4) moving = true; }
    rig.rotation.set(sy, yaw + turn + sx + sway, 0);
    const t = (now - t0) / 1000;
    mats.forEach((m) => {
      m.uniforms.uTime.value = still ? 0 : t; m.uniforms.uForm.value = form;
      m.uniforms.uBreath.value = still ? 0 : 1; m.uniforms.uFocus.value = focusOn;
    });
    return moving || !still;
  }
  function render() { renderer.render(scene, camera); if (opts.onframe) opts.onframe(api); }
  function loop(now) {
    raf = 0;
    const more = step(now);
    render();
    if (visible && !document.hidden && more) raf = requestAnimationFrame(loop);
  }
  function request() { if (!raf && visible) raf = requestAnimationFrame(loop); }

  function size() {
    const w = host.clientWidth || 600, h = Math.round(opts.height ? opts.height() : host.clientHeight || 600);
    renderer.setSize(w, h);
    camera.aspect = w / h; camera.updateProjectionMatrix();
    const scale = h * renderer.getPixelRatio() / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)));
    mats.forEach((m) => { m.uniforms.uScale.value = scale; m.uniforms.uAspect.value = w / h; m.uniforms.uMax.value = (m === bodyMat ? 3 : 7) * renderer.getPixelRatio(); });
    if (camGoal) { camera.position.set(0, camGoal.y, camGoal.dist); camera.lookAt(0, camGoal.y, 0); }
    request();
  }
  new ResizeObserver(size).observe(host);
  new IntersectionObserver((es) => { visible = es[0].isIntersecting; request(); }).observe(wrap);
  document.addEventListener("visibilitychange", request);
  new MutationObserver(applyTheme).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  const sp = new THREE.Vector3();
  function screen(id, side) {
    const p = P3[id];
    if (!p) return null;
    const s = side < 0 && !/^(CV|GV)/.test(id) ? -1 : 1;
    sp.set(p[0] * s, p[1], p[2]).applyMatrix4(inner.matrixWorld).project(camera);
    return { x: (sp.x + 1) / 2 * el.clientWidth, y: (1 - sp.y) / 2 * el.clientHeight };
  }
  // An outside driver frames the body: the camera glides to look level at height y from distance dist,
  // and the figure turns by `turn` radians (the opening screen starts a little in profile).
  function frame(y, dist, now, t) {
    camGoal = { y, dist, turn: t || 0 };
    if (now) { camera.position.set(0, y, dist); camera.lookAt(0, y, 0); turn = t || 0; }
    request();
  }
  // Bring the chosen points forward: sel = {acu: [ids], shiatsu: [ids], warn: [ids]}, or null to let go.
  function focus(sel) {
    const g = lines.geometry, a = g.getAttribute("aSel"), where = g.userData.where, hi = lineMat.uniforms.uHi.value;
    a.array.fill(0); hi.fill(0);
    const ids = sel ? (sel.acu || []).concat(sel.shiatsu || []) : [];
    const warn = sel && sel.warn ? sel.warn : [];
    ids.forEach((id) => {
      (where[id] || []).forEach((i) => { a.array[i] = warn.indexOf(id) >= 0 ? 2 : 1; });
      const k = CHS.indexOf((/^([A-Z]+)/.exec(id) || [])[1]); if (k >= 0) hi[k] = 1;
    });
    a.needsUpdate = true;
    focusGoal = ids.length ? 1 : 0;
    request();
  }
  const api = { frame, screen, focus, element: wrap, ready: Promise.resolve() };
  applyTheme(); size();
  scene.updateMatrixWorld(true);
  return api;
}

window.TCMHero3D = { available: !!HP && webgl(), create };
window.dispatchEvent(new Event("tcm-hero3d-ready"));
