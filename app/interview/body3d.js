// 3D body figure for the treatment plan: the "Male base muscular anatomy" model (Harshit Prajapati,
// Sketchfab, CC BY 4.0) with the course of the channels used, arrows for their direction of flow, and
// the chosen points (filled = acupuncture, ring = shiatsu), on both sides of the body.
// Point positions come from app/interview/points3d.js (tools/treatment/build_points3d.py): the
// schematic anchors of body_map.js placed on the model's surface. They are approximate; the exact
// location is the AcuAtlas text shown with every point.
import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.160.0/+esm";
import { GLTFLoader } from "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/loaders/GLTFLoader.js/+esm";
import { OrbitControls } from "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/controls/OrbitControls.js/+esm";
import { CSS2DRenderer, CSS2DObject } from "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/renderers/CSS2DRenderer.js/+esm";

const P3 = window.TCM_POINTS3D || {};
const BM = window.TCMBodyMap;
const LIFT = 0.0007;          // markers sit this far off the skin, along the normal
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

function create(container, opts) {
  opts = opts || {};
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

  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8a8a, 2.0));
  const key = new THREE.DirectionalLight(0xffffff, 1.4);
  key.position.set(0.5, 1, 1.2);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0xffffff, 0.8);
  rim.position.set(-0.6, 0.4, -1);
  scene.add(rim);
  const marks = new THREE.Group();
  scene.add(marks);

  const camera = new THREE.PerspectiveCamera(30, 1, 0.005, 5);
  const target = new THREE.Vector3(0, -0.075, 0);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.copy(target);
  controls.enablePan = false;
  controls.minDistance = 0.08;
  controls.maxDistance = 0.8;

  const VIEWS = { front: [0, 0, 1], back: [0, 0, -1], right: [-1, 0, 0.15], left: [1, 0, 0.15] };
  function look(v, dist) {
    const d = VIEWS[v];
    camera.position.set(target.x + d[0] * (dist || 0.42), target.y + 0.01, target.z + d[2] * (dist || 0.42));
    controls.target.copy(target);
    controls.update();
    render();
  }
  [["front", "מלפנים"], ["back", "מאחור"], ["right", "צד ימין"], ["left", "צד שמאל"]].forEach(([v, he]) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "mini"; b.textContent = he;
    b.addEventListener("click", () => look(v));
    bar.appendChild(b);
  });

  function size() {
    const w = stage.clientWidth || 600, h = Math.round(Math.min(560, Math.max(360, w * 0.9)));
    renderer.setSize(w, h); labels.setSize(w, h);
    camera.aspect = w / h; camera.updateProjectionMatrix();
    render();
  }
  const tags = [];   // {el, pos, n}: a label shows only while its point faces the camera
  const toCam = new THREE.Vector3();
  function render() {
    tags.forEach((t) => { t.el.style.visibility = toCam.subVectors(camera.position, t.pos).dot(t.n) > 0 ? "visible" : "hidden"; });
    renderer.render(scene, camera);
    labels.render(scene, camera);
  }
  controls.addEventListener("change", render);
  new ResizeObserver(size).observe(stage);

  const ready = loadModel().then((m) => { scene.add(m.clone()); size(); look("front"); }, () => {
    stage.textContent = "לא הצלחתי לטעון את הדמות התלת־ממדית. התרשים הדו־ממדי למטה מראה את אותן נקודות.";
    stage.className = "b3d-stage hint";
  });

  function clear() {
    marks.children.slice().forEach((c) => {
      marks.remove(c);
      c.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.element) o.element.remove(); });
    });
  }

  function show(sel) {
    const acu = sel.acu || [], press = sel.shiatsu || [];
    const ids = acu.concat(press.filter((id) => acu.indexOf(id) === -1)).filter((id) => P3[id]);
    clear();
    tags.length = 0;
    const chans = [...new Set(ids.map(channelOf))];
    chans.forEach((ch) => {
      const color = new THREE.Color(BM.channels([ch + "1"])[0].color);
      const lineMat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.85 });
      [1, -1].forEach((side) => {
        if (side < 0 && /^(CV|GV)$/.test(ch)) return;
        runs(ch).forEach((run) => {
          const pts = run.map((id) => vec(id, side)).filter(Boolean).map((v) => v.pos)
            .filter((v, i, a) => i === 0 || v.distanceTo(a[i - 1]) > 1e-5);   // points that share a spot
          if (pts.length < 2) return;
          const curve = new THREE.CatmullRomCurve3(pts, false, "centripetal");
          marks.add(new THREE.Mesh(new THREE.TubeGeometry(curve, Math.max(8, pts.length * 6), 0.00042, 6, false), lineMat));
          // arrows along the flow (increasing point numbers)
          const every = Math.max(2, Math.round(pts.length / 4));
          for (let i = every; i < pts.length; i += every) {
            const t = (i - 0.5) / (pts.length - 1);
            const cone = new THREE.Mesh(new THREE.ConeGeometry(0.0009, 0.0026, 10), lineMat);
            cone.position.copy(curve.getPointAt(Math.min(1, t)));
            cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), curve.getTangentAt(Math.min(1, t)));
            marks.add(cone);
          }
        });
      });
    });
    ids.forEach((id) => {
      const color = new THREE.Color(BM.channels([id])[0].color);
      const isAcu = acu.indexOf(id) !== -1, isPress = press.indexOf(id) !== -1;
      [1, -1].forEach((side) => {
        if (side < 0 && /^(CV|GV)/.test(id)) return;
        const v = vec(id, side);
        const g = new THREE.Group();
        g.position.copy(v.pos);
        g.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), v.n);
        if (isAcu) g.add(new THREE.Mesh(new THREE.SphereGeometry(0.0015, 16, 12), new THREE.MeshBasicMaterial({ color })));
        if (isPress) g.add(new THREE.Mesh(new THREE.TorusGeometry(0.0024, 0.00045, 8, 24), new THREE.MeshBasicMaterial({ color })));
        {
          const el = document.createElement("span");
          el.className = "b3d-label";
          el.style.color = "#" + color.getHexString();
          el.textContent = id;
          el.title = (opts.label ? opts.label(id) : id) + (isAcu && isPress ? " · דיקור ושיאצו" : isAcu ? " · דיקור" : " · שיאצו");
          const lab = new CSS2DObject(el);
          lab.position.set(0, 0, 0.002);
          g.add(lab);
          tags.push({ el, pos: v.pos, n: v.n });
        }
        marks.add(g);
      });
    });
    ready.then(render);
  }

  return { show, ready, element: wrap };
}

window.TCMBody3D = { available: webgl() && !!window.TCMBodyMap && Object.keys(P3).length > 0, create };
window.dispatchEvent(new Event("tcm-body3d-ready"));
