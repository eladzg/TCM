"""Place the acupuncture points on the 3D body model used by the treatment plan.

Reads the model (app/interview/body.glb: "Male base muscular anatomy" by Harshit Prajapati, Sketchfab,
CC BY 4.0, T-pose, front = +z) and the schematic point positions of app/interview/body_map.js, maps
each schematic position onto the model's surface, and writes app/interview/points3d.js
(window.TCM_POINTS3D = {point_id: [x, y, z, nx, ny, nz]}, the patient's right side; the viewer mirrors
them to the left).

The mapping is approximate (landmark heights, body widths measured on the model, and the arm turned
from the figure's hanging arm to the model's T-pose, palm down), so the 3D points are a map like the
2D figure, not anatomical locations.

Usage:
    python3 tools/treatment/build_points3d.py
"""

import json
import math
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app" / "interview"
GLB = APP / "body.glb"
OUT = APP / "points3d.js"


def load_mesh(path):
    """World-space vertices and normals of the body mesh (the largest mesh in the file)."""
    f = path.read_bytes()
    clen, _ = struct.unpack("<II", f[12:20])
    j = json.loads(f[20:20 + clen])
    off = 20 + clen
    blen, _ = struct.unpack("<II", f[off:off + 8])
    binary = f[off + 8:off + 8 + blen]

    def acc(i):
        a = j["accessors"][i]
        bv = j["bufferViews"][a["bufferView"]]
        n = {"VEC3": 3, "VEC2": 2, "SCALAR": 1, "VEC4": 4}[a["type"]]
        dt = {5126: np.float32, 5125: np.uint32, 5123: np.uint16}[a["componentType"]]
        start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        size = np.dtype(dt).itemsize * n
        stride = bv.get("byteStride") or size
        raw = np.frombuffer(binary, dtype=np.uint8, count=stride * (a["count"] - 1) + size, offset=start)
        rows = np.lib.stride_tricks.as_strided(raw, shape=(a["count"], size), strides=(stride, 1))
        return np.ascontiguousarray(rows).view(dt).reshape(a["count"], n).astype(float)

    # world matrix of each mesh node
    parents = {c: i for i, n in enumerate(j["nodes"]) for c in n.get("children", [])}

    def world(i):
        m = np.array(j["nodes"][i].get("matrix", np.eye(4).T.flatten())).reshape(4, 4).T
        return world(parents[i]) @ m if i in parents else m

    best = max((i for i, n in enumerate(j["nodes"]) if "mesh" in n),
               key=lambda i: j["accessors"][j["meshes"][j["nodes"][i]["mesh"]]["primitives"][0]["attributes"]["POSITION"]]["count"])
    prim = j["meshes"][j["nodes"][best]["mesh"]]["primitives"][0]
    m = world(best)
    p, n = acc(prim["attributes"]["POSITION"]), acc(prim["attributes"]["NORMAL"])
    v = (m @ np.c_[p, np.ones(len(p))].T).T[:, :3]
    nw = (m[:3, :3] @ n.T).T
    return v, nw / np.linalg.norm(nw, axis=1)[:, None]


def schematic_places():
    js = ("global.window = {}; require(%s); require(%s);"
          "const out = {}; Object.keys(window.TCM_TX.points).forEach(id => out[id] = window.TCMBodyMap.place(id));"
          "console.log(JSON.stringify(out));") % (json.dumps(str(APP / "body_map.js")), json.dumps(str(APP / "treatment_kb.js")))
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
def interp(x, xs, ys):
    return float(np.interp(x, xs, ys))


# Schematic figure (200 x 420) -> model, measured on the model: heights of landmarks (head top, chin,
# shoulder, nipple, navel, pubis, crotch, knee, ankle, sole), widths of head and torso, leg and arm outlines.
Y2 = [18, 60, 80, 112, 165, 205, 222, 300, 385, 415]
YM = [0.01445, -0.0125, -0.0188, -0.0388, -0.0590, -0.0730, -0.0765, -0.1090, -0.1532, -0.1625]
HEAD_X, TORSO_X = 0.000419, 0.000545           # model units per figure unit across the head, the torso
# outer and inner edges of the figure's leg and arm by y (body_map.js HALF); model x of the arm joints
LEG_OUT = ([222, 232, 300, 370, 388, 406, 415], [63, 62, 67, 73, 72, 69, 72])
LEG_IN = ([222, 240, 300, 330, 392, 415], [100, 98, 94, 91, 92, 92])
ARM_Y = [90, 160, 228, 270]
ARM_XM = [-0.0209, -0.0547, -0.0814, -0.0996]
ARM_OUT = ([90, 125, 160, 226, 244, 262, 273], [56, 50, 40, 30, 22, 21, 26])
ARM_IN = ([104, 122, 165, 232, 250, 272], [70, 62, 54, 42, 40, 37])


def nearest(V, N, target, view, mask=None):
    """Vertex nearest to target in x,y among those facing the view (front +z / back -z)."""
    dz = 1 if view == "F" else -1
    ok = N[:, 2] * dz > -0.05
    if mask is not None: ok &= mask
    idx = np.where(ok)[0]
    dist = (V[idx, 0] - target[0]) ** 2 + (V[idx, 1] - target[1]) ** 2
    # among the nearest few, take the one on the viewed side (largest z toward the camera)
    near = idx[np.argsort(dist)[:6]]
    return near[np.argmax(V[near, 2] * dz)]


def arm_point(V, N, x2, y2, view):
    """Vertex on the T-pose arm: along the arm by the figure's height, around it by the side of the
    figure's arm the point is on (palm side for front-view points, back of the arm for back-view
    points; thumb side = forward, as the model's palms face down)."""
    y2 = min(max(y2, 90), 272)
    xm = interp(y2, ARM_Y, ARM_XM)
    out, inn = interp(y2, *ARM_OUT), interp(y2, *ARM_IN)
    c, hw = (out + inn) / 2, max((inn - out) / 2, 1)
    s = max(-1, min(1, (x2 - c) / hw))           # -1 radial (thumb side), +1 ulnar
    th = math.radians(70) * s
    n = np.array([0, -math.cos(th), -math.sin(th)]) if view == "F" else np.array([0, math.cos(th), -math.sin(th)])
    slab = np.where((abs(V[:, 0] - xm) < 0.0012) & (V[:, 0] < -0.015))[0]
    cy, cz = V[slab, 1].mean(), V[slab, 2].mean()
    dirs = np.c_[V[slab, 1] - cy, V[slab, 2] - cz]
    dirs /= np.linalg.norm(dirs, axis=1)[:, None] + 1e-12
    return slab[np.argmax(dirs @ n[1:])]


def head_point(V, x2, y2, view):
    """Vertex of the head in the direction the figure's point has from the centre of the figure's head
    (a circle of radius 20 at 100,38), on the front or back half."""
    dx, dy = (x2 - 100) / 20, (38 - y2) / 20
    dz = math.sqrt(max(0.0, 1 - dx * dx - dy * dy)) * (1 if view == "F" else -1)
    head = np.where((V[:, 1] > -0.0125) & (abs(V[:, 0]) < 0.012))[0]
    lo, hi = V[head].min(0), V[head].max(0)
    c = (lo + hi) / 2
    d = (V[head] - c) / ((hi - lo) / 2)
    d /= np.linalg.norm(d, axis=1)[:, None]
    want = np.array([dx, dy, dz]) / max(1e-9, math.sqrt(dx * dx + dy * dy + dz * dz))
    return head[np.argmax(d @ want)]


def build():
    V, N = load_mesh(GLB)
    out = {}
    for pid, p in sorted(schematic_places().items()):
        x2, y2, view = p["x"], p["y"], p["view"]
        if x2 < 64 and 95 < y2 < 275:                      # on the arm of the schematic figure
            i = arm_point(V, N, x2, y2, view)
        elif math.hypot(x2 - 100, y2 - 38) <= 21:          # on the head: same direction from the head's centre
            i = head_point(V, x2, y2, view)
        else:
            ym = interp(y2, Y2, YM)
            if y2 < 62:
                xm = (x2 - 100) * HEAD_X
            elif y2 <= 222:
                xm = (x2 - 100) * TORSO_X
            else:                                           # leg: same fraction of the leg's width
                o, n_ = interp(y2, *LEG_OUT), interp(y2, *LEG_IN)
                sl = V[(abs(V[:, 1] - ym) < 0.0015) & (V[:, 0] < -0.002) & (V[:, 0] > -0.04)]
                xm = sl[:, 0].min() + (x2 - o) / (n_ - o) * (sl[:, 0].max() - sl[:, 0].min())
            if abs(x2 - 100) < 0.5:
                xm = 0.0
            i = nearest(V, N, (xm, ym), view, None if y2 < 222 else V[:, 0] < -0.001)
        v, n = V[i].copy(), N[i]
        if pid[:2] in ("CV", "GV"):
            v[0] = 0.0
        out[pid] = [round(float(a), 5) for a in list(v) + list(n)]
    return out


def main():
    data = build()
    OUT.write_text("// Generated by tools/treatment/build_points3d.py. Do not edit by hand.\n"
                   "// Approximate point positions on app/interview/body.glb (patient's right side).\n"
                   "window.TCM_POINTS3D = " + json.dumps(data, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"{len(data)} points -> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    sys.exit(main())
