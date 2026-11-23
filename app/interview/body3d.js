// 3D body figure for the treatment plan: the "Male base muscular anatomy" model (Harshit Prajapati,
// Sketchfab, CC BY 4.0) drawn as glass with a soft halo. All 14 channels and all 361 points show faintly
// on both sides of the body; the channels of the chosen points are drawn bright with arrows for their
// direction of flow, and the chosen points are marked (filled = acupuncture, ring = shiatsu).
// Point positions and the channel lines come from app/interview/points3d.js
// (tools/treatment/build_points3d.py): the AcuAtlas location text placed on a cun grid measured on the
// model, and the lines between the points laid over the skin. They are approximate; the exact
// location is the AcuAtlas text shown with every point.
// Motion: the figure turns in a rig around its own centre. Dragging spins it with inertia in any
// direction, a tilt springs back to upright, and when nothing happens it breathes slowly and leans a
// little toward the pointer. Reduced motion turns the breathing and the lean off.
import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.160.0/+esm";
import { GLTFLoader } from "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/loaders/GLTFLoader.js/+esm";
import { OrbitControls } from "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/controls/OrbitControls.js/+esm";
import { CSS2DRenderer, CSS2DObject } from "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/renderers/CSS2DRenderer.js/+esm";

const P3 = window.TCM_POINTS3D || {};
const PATHS = window.TCM_PATHS3D || null;   // {channel: [[[x, y, z], ...], ...]}, already off the skin
const BM = window.TCMBodyMap;
const LIFT = 0.0007;          // markers sit this far off the skin, along the normal
const CENTRE = -0.075;        // height of the body's middle: the rig turns around it
let model = null;              // Promise of the loaded glTF scene, shared by every viewer

function loadModel() {
  if (!model) {
    const src = window.TCM_BODY_GLB || "body.glb";
    model = new GLTFLoader().loadAsync(src).then((g) => g.scene);
  }
  return model;
}

function webgl() {
  try { const c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch (e) { return false; }
}

function vec(id, side) {
  const p = P3[id];
  if (!p) return null;
  const mid = /^(CV|GV)/.test(id);
  const s = side < 0 && !mid ? -1 : 1;
  return { pos: new THREE.Vector3(p[0] * s, p[1], p[2]).addScaledVector(new THREE.Vector3(p[3] * s, p[4], p[5]), LIFT),
           n: new THREE.Vector3(p[3] * s, p[4], p[5]) };
}

// The channel as runs of consecutive point numbers, broken where body_map.js starts a new stroke.
function runs(ch) {
  const anchors = BM.CH[ch];
  const last = anchors[anchors.length - 1][0];
  const breaks = new Set(anchors.filter((a) => a[4] === "jump").map((a) => a[0]));
  const out = [[]];
  for (let n = 1; n <= last; n++) {
    if (breaks.has(n) && out[out.length - 1].length) out.push([]);
    out[out.length - 1].push(ch + n);
  }
  return out.filter((r) => r.length > 1);
}

function channelOf(id) { const m = /^([A-Z]+)\d+$/.exec(id); return m ? m[1] : null; }
const chColor = (ch) => new THREE.Color(BM.channels([ch + "1"])[0].color);

// The channel's lines on one side of the body, as arrays of Vector3.
function channelLines(ch, side) {
  const lines = PATHS && PATHS[ch]
    ? PATHS[ch].map((pl) => pl.map((p) => new THREE.Vector3(side < 0 ? -p[0] : p[0], p[1], p[2])))
    : runs(ch).map((run) => run.map((id) => vec(id, side)).filter(Boolean).map((v) => v.pos));
  return lines.map((raw) => raw.filter((v, i, a) => i === 0 || v.distanceTo(a[i - 1]) > 1e-5)).filter((pts) => pts.length > 1);
}

// Theme colours come from CSS custom properties, so the figure follows the page's light or dark theme.
function cssColor(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  try { return new THREE.Color(v || fallback); } catch (e) { return new THREE.Color(fallback); }
}

const VS = "varying vec3 vN;varying vec3 vV;uniform float grow;" +
  "void main(){vec4 mv=modelViewMatrix*vec4(position+normal*grow,1.);vN=normalize(normalMatrix*normal);vV=normalize(-mv.xyz);gl_Position=projectionMatrix*mv;}";
function glassMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: { grow: { value: 0 }, c: { value: new THREE.Color(0x6d7f55) }, rim: { value: new THREE.Color(0xf3e7cc) } },
    vertexShader: VS,
    fragmentShader: "varying vec3 vN;varying vec3 vV;uniform vec3 c;uniform vec3 rim;" +
      "void main(){float f=pow(1.-abs(dot(vN,vV)),2.4);gl_FragColor=vec4(mix(c*.8,rim,f),.1+f*.6);}",
    transparent: true, depthWrite: false
  });
}
function haloMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: { grow: { value: 0 }, c: { value: new THREE.Color(0xa9bb88) }, k: { value: 0.32 } },
    vertexShader: VS,
    fragmentShader: "varying vec3 vN;varying vec3 vV;uniform vec3 c;uniform float k;" +
      "void main(){float d=clamp(-dot(vN,vV),0.,1.);gl_FragColor=vec4(c,pow(d,1.8)*k);}",
    side: THREE.BackSide, transparent: true, depthWrite: false
  });
}
function dotTexture() {
  const c = document.createElement("canvas"); c.width = c.height = 64;
  const x = c.getContext("2d"), g = x.createRadialGradient(32, 32, 0, 32, 32, 32);
  g.addColorStop(0, "rgba(255,255,255,1)"); g.addColorStop(0.3, "rgba(255,255,255,.9)"); g.addColorStop(0.55, "rgba(255,255,255,.3)"); g.addColorStop(1, "rgba(255,255,255,0)");
  x.fillStyle = g; x.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
}
const reduced = () => window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
const ALL_KEY = "tcm-b3d-all";

// opts: label(id) -> name for tooltips; height(width) -> stage height; dist(aspect) -> the camera's resting
// distance; onframe(viewer) -> called after every drawn frame; hero: the opening screen's figure (every
// channel always on, the choice not remembered, and it turns back to face the viewer when left alone).
function create(container, opts) {
  opts = opts || {};
  const api = {};   // the viewer's handle, filled in below
  const wrap = document.createElement("div");
  wrap.className = "b3d";
  const stage = document.createElement("div");
  stage.className = "b3d-stage";
  wrap.appendChild(stage);
  const bar = document.createElement("div");
  bar.className = "b3d-bar";
  wrap.appendChild(bar);
  container.appendChild(wrap);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  stage.appendChild(renderer.domElement);
  const labels = new CSS2DRenderer();
  labels.domElement.className = "b3d-labels";
  stage.appendChild(labels.domElement);
  const tip = document.createElement("div");
  tip.className = "b3d-tip";
  tip.hidden = true;
  stage.appendChild(tip);

  const scene = new THREE.Scene();
  const rig = new THREE.Group(), inner = new THREE.Group();
  rig.position.set(0, CENTRE, 0); inner.position.set(0, -CENTRE, 0);
  rig.add(inner); scene.add(rig);
  const marks = new THREE.Group();
  inner.add(marks);
  const allLayer = new THREE.Group();     // every channel and point, faint
  inner.add(allLayer);

  const glass = glassMaterial(), halo = haloMaterial(), occ = new THREE.MeshBasicMaterial({ colorWrite: false });
  function applyTheme() {
    glass.uniforms.c.value = cssColor("--b3d-glass", "#6d7f55");
    glass.uniforms.rim.value = cssColor("--b3d-rim", "#f3e7cc");
    halo.uniforms.c.value = cssColor("--b3d-halo", "#a9bb88");
    request();
  }

  const camera = new THREE.PerspectiveCamera(30, 1, 0.005, 5);
  const target = new THREE.Vector3(0, CENTRE, 0);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.copy(target);
  controls.enablePan = false;
  controls.enableRotate = false;      // turning is the rig's (below); the controls only zoom
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.zoomSpeed = 0.6;
  controls.minDistance = 0.08;
  controls.maxDistance = 0.8;
  camera.position.set(0, CENTRE + 0.01, 0.42);

  // ---- motion ----
  let visible = true, raf = 0;   // the render loop's state (below)
  let yaw = 0, pit = 0, vy = 0, vp = 0, drag = null, goalYaw = null, camHome = 0, mx = 0, my = 0, sx = 0, sy = 0, lastDrag = 0;
  const homeDist = () => (opts.dist ? opts.dist(camera.aspect || 1) : 0.42);
  renderer.domElement.addEventListener("pointerdown", (e) => {
    drag = { x: e.clientX, y: e.clientY }; vy = vp = 0; goalYaw = null;
    try { renderer.domElement.setPointerCapture(e.pointerId); } catch (err) { /* not needed */ }
    request();
  });
  renderer.domElement.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    drag.x = e.clientX; drag.y = e.clientY;
    vy = dx * 0.0055; vp = dy * 0.0035; yaw += vy; pit += vp;
    request();
  });
  const endDrag = () => { if (drag) { drag = null; lastDrag = performance.now(); request(); } };
  renderer.domElement.addEventListener("pointerup", endDrag);
  renderer.domElement.addEventListener("pointercancel", endDrag);
  window.addEventListener("pointermove", (e) => {
    const r = stage.getBoundingClientRect();
    if (!r.width) return;
    mx = Math.max(-1, Math.min(1, ((e.clientX - r.left) / r.width) * 2 - 1));
    my = Math.max(-1, Math.min(1, ((e.clientY - r.top) / r.height) * 2 - 1));
  }, { passive: true });
  controls.addEventListener("change", request);

  // Returns true while something still moves, so the loop knows whether to keep going.
  function step(now) {
    let moving = !!drag || camHome > 0;
    if (!drag) {
      yaw += vy; pit += vp; vy *= 0.955; vp *= 0.9;
      pit += (0 - pit) * 0.012;
      if (Math.abs(vy) > 1e-4 || Math.abs(vp) > 1e-4 || Math.abs(pit) > 1e-3) moving = true;
    }
    pit = Math.max(-0.5, Math.min(0.5, pit));
    if (opts.hero && !drag && goalYaw === null && lastDrag && now - lastDrag > 2500) {
      const front = 2 * Math.PI * Math.round(yaw / (2 * Math.PI));
      if (Math.abs(front - yaw) > 0.01) goalYaw = front;
      lastDrag = 0;
    }
    if (goalYaw !== null) {
      yaw += (goalYaw - yaw) * 0.06;
      if (Math.abs(goalYaw - yaw) < 0.001) { yaw = goalYaw; goalYaw = null; } else moving = true;
    }
    if (camHome > 0) {
      const home = new THREE.Vector3(0, CENTRE + 0.01, homeDist());
      camera.position.lerp(home, 0.08); controls.target.lerp(target, 0.08);
      if (camera.position.distanceTo(home) < 0.001) camHome = 0;
    }
    const still = reduced();
    sx += ((still ? 0 : mx * 0.05) - sx) * 0.025;
    sy += ((still ? 0 : my * 0.03) - sy) * 0.025;
    const sway = still ? 0 : Math.sin(now * 0.00035) * 0.015;
    rig.rotation.set(pit + sy, yaw + sx + sway, 0);
    rig.position.y = CENTRE + (still ? 0 : Math.sin(now * 0.0008) * 0.0004);
    return moving || !still;
  }

  const VIEWS = { front: 0, back: Math.PI, right: Math.PI / 2, left: -Math.PI / 2 };
  function look(v) {
    const a = VIEWS[v];
    goalYaw = a + 2 * Math.PI * Math.round((yaw - a) / (2 * Math.PI));
    vy = vp = 0; camHome = 1;
    request();
  }
  [["front", "מלפנים"], ["back", "מאחור"], ["right", "צד ימין"], ["left", "צד שמאל"]].forEach(([v, he]) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "mini"; b.textContent = he;
    b.addEventListener("click", () => look(v));
    bar.appendChild(b);
  });
  let showAll = true;
  if (!opts.hero) try { showAll = localStorage.getItem(ALL_KEY) !== "0"; } catch (e) { /* storage off */ }
  const allBtn = document.createElement("button");
  allBtn.type = "button"; allBtn.className = "mini"; allBtn.textContent = "כל המרידיאנים והנקודות";
  const setAll = (on) => {
    showAll = on; allLayer.visible = on; allBtn.setAttribute("aria-pressed", String(on));
    if (!opts.hero) try { localStorage.setItem(ALL_KEY, on ? "1" : "0"); } catch (e) { /* storage off */ }
    request();
  };
  allBtn.addEventListener("click", () => setAll(!showAll));
  bar.appendChild(allBtn);
  setAll(showAll);

  function size() {
    const w = stage.clientWidth || 600, h = opts.height ? Math.round(opts.height(w)) : Math.round(Math.min(640, Math.max(380, w * 1.0)));
    renderer.setSize(w, h); labels.setSize(w, h);
    camera.aspect = w / h; camera.updateProjectionMatrix();
    if (opts.dist) { camera.position.set(0, CENTRE + 0.01, homeDist()); controls.target.copy(target); }
    request();
  }

  const tags = [];   // {el, pos, n} in the body's own frame: a label shows only while its point faces the camera
  const toCam = new THREE.Vector3(), wp = new THREE.Vector3(), wn = new THREE.Vector3();
  function render() {
    rig.updateMatrixWorld(true);
    tags.forEach((t) => {
      wp.copy(t.pos).applyMatrix4(inner.matrixWorld);
      wn.copy(t.n).applyQuaternion(rig.quaternion);
      t.el.style.visibility = toCam.subVectors(camera.position, wp).dot(wn) > 0 ? "visible" : "hidden";
    });
    renderer.render(scene, camera);
    labels.render(scene, camera);
    if (opts.onframe) opts.onframe(api);
  }

  // The loop runs while the figure is on screen and something moves (or it breathes); otherwise it sleeps.
  function loop(now) {
    raf = 0;
    controls.update();
    const more = step(now);
    render();
    if (visible && !document.hidden && more) raf = requestAnimationFrame(loop);
  }
  function request() { if (!raf && visible) raf = requestAnimationFrame(loop); }
  new IntersectionObserver((es) => { visible = es[0].isIntersecting; request(); }).observe(stage);
  document.addEventListener("visibilitychange", request);
  window.addEventListener("pointermove", () => { if (!reduced()) request(); }, { passive: true });
  new ResizeObserver(size).observe(stage);
  new MutationObserver(applyTheme).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  if (window.matchMedia) matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);

  // ---- every channel and point, faint; a hovered point names itself ----
  let allPts = null; const ptsInfo = [];
  function buildAll() {
    Object.keys(BM.CH).forEach((ch) => {
      const color = chColor(ch);
      const mat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.4, depthWrite: false, toneMapped: false });
      (ch === "CV" || ch === "GV" ? [1] : [1, -1]).forEach((side) => {
        channelLines(ch, side).forEach((pts) => {
          const curve = new THREE.CatmullRomCurve3(pts, false, "centripetal");
          const t = new THREE.Mesh(new THREE.TubeGeometry(curve, Math.max(8, pts.length * 3), 0.00017, 5, false), mat);
          t.renderOrder = 3; allLayer.add(t);
        });
      });
    });
    const pos = [], col = [];
    Object.keys(P3).forEach((id) => {
      const ch = channelOf(id); if (!ch || !BM.CH[ch]) return;
      const c = chColor(ch);
      (ch === "CV" || ch === "GV" ? [1] : [1, -1]).forEach((side) => {
        const v = vec(id, side);
        v.pos.addScaledVector(v.n, 0.0003);
        pos.push(v.pos.x, v.pos.y, v.pos.z); col.push(c.r, c.g, c.b);
        ptsInfo.push({ id, n: v.n });
      });
    });
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    geo.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
    allPts = new THREE.Points(geo, new THREE.PointsMaterial({ size: 0.0055, map: dotTexture(), vertexColors: true, transparent: true, opacity: 0.85, depthWrite: false, toneMapped: false }));
    allPts.renderOrder = 4; allLayer.add(allPts);
  }
  const ray = new THREE.Raycaster(); ray.params.Points.threshold = 0.0016;
  const mouse = new THREE.Vector2();
  renderer.domElement.addEventListener("pointermove", (e) => {
    if (drag || !allPts || !showAll) { tip.hidden = true; return; }
    const r = renderer.domElement.getBoundingClientRect();
    mouse.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(mouse, camera);
    const hit = ray.intersectObject(allPts)
      .filter((h) => ray.ray.direction.dot(wn.copy(ptsInfo[h.index].n).applyQuaternion(rig.quaternion)) < 0)
      .sort((a, b) => a.distanceToRay - b.distanceToRay)[0];
    if (!hit) { tip.hidden = true; return; }
    const id = ptsInfo[hit.index].id;
    const name = opts.label ? opts.label(id) : id;
    tip.textContent = name && name !== id ? id + " · " + name : id;
    tip.style.left = (e.clientX - r.left) + "px"; tip.style.top = (e.clientY - r.top) + "px";
    tip.hidden = false;
  });
  renderer.domElement.addEventListener("pointerleave", () => { tip.hidden = true; });

  const ready = api.ready = loadModel().then((m) => {
    const body = m.clone();
    inner.add(body);
    inner.updateMatrixWorld(true);
    const meshes = [];
    body.traverse((o) => { if (o.isMesh) meshes.push(o); });
    meshes.forEach((o) => {
      o.material = glass; o.renderOrder = 1;
      const hide = new THREE.Mesh(o.geometry, occ); hide.renderOrder = 0; o.add(hide);   // depth only: hides what is behind the skin
      if (/body/i.test(o.name)) {
        const ws = new THREE.Vector3(); o.getWorldScale(ws);
        const h = new THREE.Mesh(o.geometry, halo); h.renderOrder = 2; o.add(h);
        halo.uniforms.grow.value = 0.0045 / (ws.x || 1);
      }
    });
    buildAll();
    allLayer.visible = showAll;
    applyTheme(); size();
  }, () => {
    stage.textContent = "לא הצלחתי לטעון את הדמות התלת־ממדית. התרשים הדו־ממדי למטה מראה את אותן נקודות.";
    stage.className = "b3d-stage hint";
  });

  // Where a point sits on the screen now, in the stage's pixels (for menus anchored to the body).
  const sp = new THREE.Vector3();
  function screen(id, side) {
    const v = vec(id, side || 1);
    if (!v) return null;
    sp.copy(v.pos).applyMatrix4(inner.matrixWorld).project(camera);
    return { x: (sp.x + 1) / 2 * renderer.domElement.clientWidth, y: (1 - sp.y) / 2 * renderer.domElement.clientHeight };
  }
  Object.assign(api, { show: (sel) => show(sel), element: wrap, screen, stage });

  function clear() {
    marks.children.slice().forEach((c) => {
      marks.remove(c);
      c.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.element) o.element.remove(); });
    });
  }

  function show(sel) {
    const acu = sel.acu || [], press = sel.shiatsu || [], warn = sel.warn || [];
    const ids = acu.concat(press.filter((id) => acu.indexOf(id) === -1)).filter((id) => P3[id]);
    clear();
    tags.length = 0;
    const chans = [...new Set(ids.map(channelOf))];
    chans.forEach((ch) => {
      const color = chColor(ch);
      const lineMat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.95, toneMapped: false });
      [1, -1].forEach((side) => {
        if (side < 0 && /^(CV|GV)$/.test(ch)) return;
        channelLines(ch, side).forEach((pts) => {
          const curve = new THREE.CatmullRomCurve3(pts, false, "centripetal");
          const len = curve.getLength();
          const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, Math.max(8, pts.length * 2), 0.0004, 6, false), lineMat);
          tube.renderOrder = 5; marks.add(tube);
          // arrows along the flow (increasing point numbers), about every 0.025 along the line
          const n = Math.max(1, Math.round(len / 0.025));
          for (let i = 0; i < n; i++) {
            const t = (i + 0.5) / n;
            const cone = new THREE.Mesh(new THREE.ConeGeometry(0.0009, 0.0026, 10), lineMat);
            cone.position.copy(curve.getPointAt(t));
            cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), curve.getTangentAt(t));
            cone.renderOrder = 5; marks.add(cone);
          }
        });
      });
    });
    ids.forEach((id) => {
      const color = chColor(channelOf(id));
      const isAcu = acu.indexOf(id) !== -1, isPress = press.indexOf(id) !== -1;
      [1, -1].forEach((side) => {
        if (side < 0 && /^(CV|GV)/.test(id)) return;
        const v = vec(id, side);
        const g = new THREE.Group();
        g.position.copy(v.pos);
        g.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), v.n);
        const mat = new THREE.MeshBasicMaterial({ color, toneMapped: false });
        if (isAcu) g.add(new THREE.Mesh(new THREE.SphereGeometry(0.0015, 16, 12), mat));
        if (isPress) g.add(new THREE.Mesh(new THREE.TorusGeometry(0.0024, 0.00045, 8, 24), mat));
        if (warn.indexOf(id) !== -1) {   // a warning in the safety check: a small red dot beside the marker
          const w = new THREE.Mesh(new THREE.SphereGeometry(0.0009, 12, 10), new THREE.MeshBasicMaterial({ color: 0xd0302a, toneMapped: false }));
          w.position.set(0.0024, 0.0024, 0.0004);
          g.add(w);
        }
        g.traverse((o) => { o.renderOrder = 6; });
        {
          const el = document.createElement("span");
          el.className = "b3d-label";
          el.style.setProperty("--ch", "#" + color.getHexString());
          el.textContent = id;
          if (warn.indexOf(id) !== -1) {   // the red dot also on the label, so it shows at any zoom
            const dot = document.createElement("i");
            dot.className = "b3d-warn";
            el.appendChild(dot);
          }
          el.title = (opts.label ? opts.label(id) : id) + (isAcu && isPress ? " · דיקור ושיאצו" : isAcu ? " · דיקור" : " · שיאצו") +
            (warn.indexOf(id) !== -1 ? " · יש אזהרה בבדיקת הבטיחות" : "");
          const lab = new CSS2DObject(el);
          lab.position.set(0, 0, 0.002);
          g.add(lab);
          tags.push({ el, pos: v.pos, n: v.n });
        }
        marks.add(g);
      });
    });
    ready.then(request);
  }

  return api;
}

window.TCMBody3D = { available: webgl() && !!window.TCMBodyMap && Object.keys(P3).length > 0, create };
window.dispatchEvent(new Event("tcm-body3d-ready"));
