"""Place the acupuncture points on the 3D body model used by the treatment plan.

Reads the model (app/interview/body.glb: "Male base muscular anatomy" by Harshit Prajapati, Sketchfab,
CC BY 4.0, T-pose, front = +z, palms down) and the AcuAtlas location text of every point (the "loc"
field of app/interview/treatment_kb.js), and writes app/interview/points3d.js:

    window.TCM_POINTS3D = {point_id: [x, y, z, nx, ny, nz]}      the patient's right side; the viewer
    window.TCM_PATHS3D = {channel: [[[x, y, z], ...], ...]}      mirrors them to the left

Method. Landmarks were measured on the model (umbilicus, nipple, suprasternal notch, xiphisternal
junction, pubic symphysis, C7 and the iliac crest for the vertebral levels, glabella and the hairlines,
axillary fold, cubital and wrist creases, knuckles, patella, popliteal crease, malleoli, heel and toes).
On them sits the proportional bone-cun system (B-cun): 8 cun from the xiphisternal junction to the
umbilicus, 5 cun from there to the pubic symphysis, 4 cun from the anterior midline to the nipple,
8 cun from the glabella over the head to GV20 (between the ear apices) and 7 more to the posterior
hairline, 9 cun from the axillary fold to the cubital crease, 12 cun from there to the wrist crease,
19 cun from the greater trochanter to the popliteal crease, 16 cun from the popliteal crease to the
lateral malleolus and 13 cun from below the medial tibial condyle to the medial malleolus. Each location text is parsed into a position in that
system: a level (cun above or below a landmark, an intercostal space, a vertebra, a sacral foramen) and
a place around the body or limb (cun from a midline measured along the skin, or the side of the limb
the text names: "posterior to the medial border of the tibia", "between palmaris longus and flexor
carpi radialis", ...). Texts that name a spot instead of a distance ("between the medial malleolus and
the Achilles tendon", "in the hollow between the 1st and 2nd metatarsal bones") take a position read
from the text by hand in manual() below. The position is then cast onto the mesh along the outward
direction of the body part. Points the text does not resolve keep the earlier placement: the
schematic anchors of app/interview/body_map.js, interpolated by point number and mapped onto the
model (schematic()).

The channel lines are the points of each channel in order, with samples in between snapped to the
skin (and a few waypoints, vias()), so they follow the surface instead of cutting through the body.

All of it is approximate: the model is one stylised body and the cun are proportions, not
measurements of a patient. The AcuAtlas text shown with every point stays the reference.

Usage:
    python3 tools/treatment/build_points3d.py            # writes app/interview/points3d.js
    python3 tools/treatment/build_points3d.py --report   # how each point was placed
"""

import json
import math
import re
import struct
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app" / "interview"
GLB = APP / "body.glb"
OUT = APP / "points3d.js"


# ---------------------------------------------------------------------------------------------- mesh

def load_mesh(path):
    """World-space vertices, normals and triangles of the body mesh (the largest mesh in the file)."""
    f = path.read_bytes()
    clen, _ = struct.unpack("<II", f[12:20])
    j = json.loads(f[20:20 + clen])
    off = 20 + clen
    blen, _ = struct.unpack("<II", f[off:off + 8])
    binary = f[off + 8:off + 8 + blen]

    def acc(i, as_float=True):
        a = j["accessors"][i]
        bv = j["bufferViews"][a["bufferView"]]
        n = {"VEC3": 3, "VEC2": 2, "SCALAR": 1, "VEC4": 4}[a["type"]]
        dt = {5126: np.float32, 5125: np.uint32, 5123: np.uint16}[a["componentType"]]
        start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        size = np.dtype(dt).itemsize * n
        stride = bv.get("byteStride") or size
        raw = np.frombuffer(binary, dtype=np.uint8, count=stride * (a["count"] - 1) + size, offset=start)
        rows = np.lib.stride_tricks.as_strided(raw, shape=(a["count"], size), strides=(stride, 1))
        out = np.ascontiguousarray(rows).view(dt).reshape(a["count"], n)
        return out.astype(float) if as_float else out.astype(np.int64)

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
    faces = acc(prim["indices"], as_float=False).reshape(-1, 3)
    return v, nw / np.linalg.norm(nw, axis=1)[:, None], faces


def unit(v):
    v = np.asarray(v, dtype=float)
    return v / (np.linalg.norm(v) + 1e-15)


class Surface:
    """Ray casts against the triangles of the mesh."""

    def __init__(self, V, N, F):
        self.V, self.N, self.F = V, N, F
        A, B, C = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
        self.A, self.E1, self.E2 = A, B - A, C - A
        self.lo, self.hi = np.minimum(np.minimum(A, B), C), np.maximum(np.maximum(A, B), C)

    def _hits(self, o, d, idx):
        """Intersections of the rays o + t d (o, d: R x 3) with triangles idx -> t (R x T), u, v (inf = miss)."""
        e1, e2, a = self.E1[idx], self.E2[idx], self.A[idx]
        p = np.cross(d[:, None, :], e2[None, :, :])
        det = np.einsum("tk,rtk->rt", e1, p)
        ok = np.abs(det) > 1e-14
        inv = np.where(ok, 1.0 / np.where(ok, det, 1), 0)
        s = o[:, None, :] - a[None, :, :]
        u = np.einsum("rtk,rtk->rt", s, p) * inv
        q = np.cross(s, e1[None, :, :])
        v = np.einsum("rk,rtk->rt", d, q) * inv
        t = np.einsum("tk,rtk->rt", e2, q) * inv
        ok &= (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9)
        return np.where(ok, t, np.inf), u, v

    def _normal(self, tri, u, v):
        f = self.F[tri]
        n = (1 - u - v) * self.N[f[0]] + u * self.N[f[1]] + v * self.N[f[2]]
        return unit(n)

    def line(self, o, d, t0, t1):
        """All hits of the segment o + t d, t in [t0, t1]: [(t, point, normal)] sorted by t."""
        o, d = np.asarray(o, float), unit(d)
        a, b = o + t0 * d, o + t1 * d
        lo, hi = np.minimum(a, b) - 1e-9, np.maximum(a, b) + 1e-9
        idx = np.where(np.all(self.hi >= lo, axis=1) & np.all(self.lo <= hi, axis=1))[0]
        if not len(idx):
            return []
        t, u, v = self._hits(o[None], d[None], idx)
        out = []
        for k in np.where(np.isfinite(t[0]) & (t[0] >= t0) & (t[0] <= t1))[0]:
            out.append((float(t[0, k]), o + t[0, k] * d, self._normal(idx[k], u[0, k], v[0, k])))
        return sorted(out, key=lambda h: h[0])

    def fan(self, c, dirs, plane_n, reach=0.06):
        """First hit outward from c along each direction (all in the plane through c normal to plane_n)."""
        c, dirs = np.asarray(c, float), np.asarray(dirs, float)
        s = (self.V - c) @ unit(plane_n)
        sf = s[self.F]
        near = np.linalg.norm(self.V - c, axis=1)[self.F].min(1) < reach
        idx = np.where((sf.min(1) <= 1e-12) & (sf.max(1) >= -1e-12) & near)[0]
        t, u, v = self._hits(np.repeat(c[None], len(dirs), 0), dirs, idx)
        t = np.where(t > 1e-9, t, np.inf)
        k = np.argmin(t, axis=1)
        res = []
        for r in range(len(dirs)):
            tr = t[r, k[r]]
            if not np.isfinite(tr) or tr > reach:
                res.append(None)
            else:
                res.append((c + tr * dirs[r], self._normal(idx[k[r]], u[r, k[r]], v[r, k[r]])))
        return res

    def out(self, c, d, reach=0.06):
        """First hit going outward from the interior point c along d."""
        h = [x for x in self.line(c, d, 1e-9, reach)]
        return (h[0][1], h[0][2]) if h else None

    def snap(self, p, n, reach=0.008):
        """Surface point nearest to p on the line through p along n, facing n."""
        n = unit(n)
        hs = [h for h in self.line(p, n, -reach, reach) if h[2] @ n > 0]
        if not hs:
            hs = self.line(p, n, -reach, reach)
        if not hs:
            return None
        h = min(hs, key=lambda h: abs(h[0]))
        return h[1], h[2]

    def outer(self, p, n, reach=0.03):
        """Outermost surface point along n on the line through p (cast from outside, toward -n)."""
        hs = [h for h in self.line(p, n, -reach, reach) if h[2] @ unit(n) > 0]
        if not hs:
            return None
        h = max(hs, key=lambda h: h[0])
        return h[1], h[2]


# ------------------------------------------------------------------------------------- landmarks
# Model units (the figure is 0.177 tall; 1 unit is about 10 m). Right side of the body = negative x.
# Measured on renders of the model (orthographic views with a grid) and checked with markers.

Y_TOP = 0.01445
# trunk, front
Y_SS = -0.0222            # suprasternal notch (CV22)
Y_XIPH = -0.0420          # xiphisternal junction (CV16)
Y_NAVEL = -0.0590         # centre of the umbilicus (CV8)
Y_PUBIS = -0.0697         # upper border of the pubic symphysis (CV2)
NIPPLE = (-0.01247, -0.0387)
Y_ICS1, Y_ICS4 = -0.0276, NIPPLE[1]     # 1st and 4th intercostal spaces near the sternum
Y_CLAV = -0.0242          # just below the clavicle
Y_SUPRACLAV = -0.0212     # just above the clavicle
ASIS = (-0.0150, -0.0655)
# back
Y_C7 = -0.0175            # C7 spinous process
Y_L4 = -0.0598            # L4 spinous process, level with the top of the iliac crests
# distance below C7 of each spinous process in a reference adult spine (cm), scaled to C7..L4
SPINE_CM = {"C7": 0, "T1": 2.4, "T2": 4.8, "T3": 7.2, "T4": 9.6, "T5": 12.0, "T6": 14.5, "T7": 17.0,
            "T8": 19.5, "T9": 22.0, "T10": 24.6, "T11": 27.3, "T12": 30.1, "L1": 33.1, "L2": 36.3,
            "L3": 39.6, "L4": 42.9, "L5": 46.0}
SACRAL = {1: -0.0654, 2: -0.0669, 3: -0.0684, 4: -0.0698}   # posterior sacral foramina
Y_HIATUS = -0.0708        # sacral hiatus (GV2)
Y_COCCYX = -0.0738        # tip of the coccyx
Y_EOP = -0.0030           # external occipital protuberance
Y_POST_HAIR = -0.0073     # posterior hairline on the midline
SCAP = {"spine_mid": (-0.0125, -0.0225), "spine_med": (-0.0080, -0.0240), "inf_angle": (-0.0095, -0.0435),
        "sup_angle": (-0.0085, -0.0205), "post_fold": (-0.0232, -0.0300)}
ACROMION = (-0.0248, -0.0168)            # lateral tip (x, y)
# head and face (x, y on the front; z found on the mesh)
Y_GLABELLA = 0.0025
FACE = {"pupil": (-0.00356, 0.00142), "inner_canthus": (-0.00205, 0.00130), "outer_canthus": (-0.00505, 0.00130),
        "brow_med": (-0.00215, 0.00270), "brow_lat": (-0.00590, 0.00290), "ala": (-0.00195, -0.00300),
        "ala_low": (-0.00150, -0.00370), "mouth": (-0.00277, -0.00650), "philtrum": (0.0, -0.00500),
        "lip": (0.0, -0.00590), "chin_groove": (0.0, -0.00850), "nose_tip": (0.0, -0.00270)}
# side of the head (y, z), cast from the right side
SIDE = {"ear_apex": (0.0028, -0.0040), "tragus": (-0.0014, -0.0023), "lobe": (-0.0045, -0.0032),
        "mastoid": (-0.0052, -0.0048), "jaw_angle": (-0.0089, -0.0002), "zygoma_mid": (-0.0004, 0.0012),
        "temple_hair": (0.0018, -0.0010)}
Y_THYROID, Y_CRICOID, Y_HYOID = -0.0143, -0.0162, -0.0130
# arm (x along the T-pose arm; proximal = larger x)
X_AXFOLD = -0.0265        # anterior axillary fold
X_ELBOW = -0.0480         # cubital crease
X_WRIST = -0.0778         # wrist crease
X_MCP = -0.0868           # 2nd/3rd metacarpophalangeal joints
FINGER = {  # (x, z) of the MCP joint and the tip; the thumb from its carpometacarpal joint
    "thumb": ((-0.0790, 0.0058), (-0.0835, 0.0095), (-0.0887, 0.0107)),
    "index": ((-0.0780, 0.0042), (-0.0866, 0.0062), (-0.0979, 0.0066)),
    "middle": ((-0.0780, 0.0022), (-0.0868, 0.0024), (-0.0996, 0.0023)),
    "ring": ((-0.0780, 0.0002), (-0.0866, -0.0012), (-0.0979, -0.0015)),
    "little": ((-0.0780, -0.0018), (-0.0860, -0.0042), (-0.0952, -0.0045)),
}
# leg (y)
Y_TROCH = -0.0770         # greater trochanter
Y_GLUT = -0.0797          # gluteal fold
Y_PAT_BASE = -0.1135      # base of the patella
Y_PAT_APEX = -0.1185
Y_POP = -0.1195           # popliteal crease
Y_ST35 = -0.1195          # lateral knee eye, level with the apex of the patella
Y_ANKLE_FRONT = -0.1495   # front of the ankle, where the shin turns into the dorsum
Y_SP9 = -0.1235           # below the medial tibial condyle
Y_MM = -0.1521            # medial malleolus prominence
Y_LM = -0.1523            # lateral malleolus prominence
Y_SOLE = -0.1625

CUN_V_UP = (Y_XIPH - Y_NAVEL) / 8
CUN_V_LO = (Y_NAVEL - Y_PUBIS) / 5
CUN_UPPER = (X_AXFOLD - X_ELBOW) / 9
CUN_FORE = (X_ELBOW - X_WRIST) / 12
CUN_THIGH = (Y_TROCH - Y_POP) / 19
CUN_LEG_LAT = (Y_POP - Y_LM) / 16
CUN_LEG_MED = (Y_SP9 - Y_MM) / 13
CUN_SPINE = (Y_C7 - Y_L4) / SPINE_CM["L4"]   # model units per reference cm


def spine_y(v, below=True):
    """y of the depression below (or the upper edge of) a spinous process, e.g. 'T3'."""
    order = list(SPINE_CM)
    cm = SPINE_CM[v]
    if below:
        nxt = SPINE_CM[order[order.index(v) + 1]] if v != "L5" else cm + 3.0
        cm = cm + 0.45 * (nxt - cm)
    else:
        cm -= 0.6
    return Y_C7 - cm * CUN_SPINE


def ics_y(n):
    return Y_ICS4 + (4 - n) * (Y_ICS1 - Y_ICS4) / 3


# ------------------------------------------------------------------------------------- the body

class Body:
    def __init__(self):
        V, N, F = load_mesh(GLB)
        self.V, self.N = V, N
        self.s = Surface(V, N, F)
        self._arm_fit()
        self._leg_fit()
        self.head_c = np.array([0.0, 0.0035, -0.0010])
        self.cun_h = self._trunk_arc_to_x(NIPPLE[1], NIPPLE[0]) / 4
        self._head_fit()

    # ---- trunk: horizontal slices, distances along the skin from the midline
    @lru_cache(maxsize=None)
    def contour(self, y, zc=None):
        y = float(y)
        if zc is None:
            f = self.s.outer((0, y, 0), (0, 0, 1))
            b = self.s.outer((0, y, 0), (0, 0, -1))
            zc = (f[0][2] + b[0][2]) / 2
        c = np.array([0.0, y, zc])
        phis = np.radians(np.arange(0, 180.5, 1.0))
        dirs = np.c_[-np.sin(phis), np.zeros_like(phis), np.cos(phis)]
        hits = self.s.fan(c, dirs, (0, 1, 0), reach=0.035)
        pts, nrm, ph = [], [], []
        for h, p in zip(hits, phis):
            if h is not None:
                pts.append(h[0]); nrm.append(h[1]); ph.append(p)
        pts, nrm = np.array(pts), np.array(nrm)
        arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
        return pts, nrm, np.array(ph), arc

    def trunk(self, y, u, side="F", zc=None):
        """Point u cun (along the skin) from the anterior (F) or posterior (B) midline at height y."""
        pts, nrm, ph, arc = self.contour(round(y, 6), zc)
        d = u * self.cun_h
        a = d if side == "F" else arc[-1] - d
        k = int(np.clip(np.searchsorted(arc, a), 1, len(arc) - 1))
        t = (a - arc[k - 1]) / max(arc[k] - arc[k - 1], 1e-12)
        p = pts[k - 1] + t * (pts[k] - pts[k - 1])
        n = unit(nrm[k - 1] + t * (nrm[k] - nrm[k - 1]))
        if u == 0:
            p = p.copy(); p[0] = 0.0
        return p, n

    def trunk_phi(self, y, phi_deg, zc=None):
        pts, nrm, ph, arc = self.contour(round(y, 6), zc)
        k = int(np.argmin(abs(ph - math.radians(phi_deg))))
        return pts[k], nrm[k]

    def midaxillary(self, y, forward_cun=0.0):
        pts, nrm, ph, arc = self.contour(round(y, 6))
        k = int(np.argmin(pts[:, 0]))
        return self.trunk(y, (arc[k] - forward_cun * self.cun_h) / self.cun_h, "F")

    def _trunk_arc_to_x(self, y, x, side="F"):
        pts, nrm, ph, arc = self.contour(round(y, 6))
        half = pts[:, 2] > np.median(pts[:, 2]) if side == "F" else pts[:, 2] <= np.median(pts[:, 2])
        k = np.where(half)[0][np.argmin(abs(pts[half, 0] - x))]
        return arc[k] if side == "F" else arc[-1] - arc[k]

    def trunk_x(self, y, x, side="F"):
        return self.trunk(y, self._trunk_arc_to_x(y, x, side) / self.cun_h, side)

    # ---- head: arcs over the skull from the glabella, and across from the midline
    def _sagittal(self):
        psi = np.radians(np.arange(-40, 245, 0.5))
        dirs = np.c_[np.zeros_like(psi), np.sin(psi), np.cos(psi)]
        hits = [h for h in self.s.fan(self.head_c, dirs, (1, 0, 0), reach=0.03) if h is not None]
        pts = np.array([h[0] for h in hits]); nrm = np.array([h[1] for h in hits])
        arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
        return pts, nrm, arc

    def _head_fit(self):
        pts, nrm, arc = self._sagittal()
        front = pts[:, 2] > 0
        g = np.where(front)[0][np.argmin(abs(pts[front, 1] - Y_GLABELLA))]
        top = (pts[:, 1] > 0.008) & (np.arange(len(pts)) > g)
        v = np.where(top)[0][np.argmin(abs(pts[top, 2] - SIDE["ear_apex"][1]))]
        back = (pts[:, 2] < 0) & (np.arange(len(pts)) > v)
        h = np.where(back)[0][np.argmin(abs(pts[back, 1] - Y_POST_HAIR))]
        self.sag = (pts, nrm, arc - arc[g])
        # GV20 (8 cun from the glabella) lies on the line joining the ear apices; the posterior
        # hairline is 7 cun further back
        self.cun_head_f = (arc[v] - arc[g]) / 8
        self.cun_head_b = (arc[h] - arc[v]) / 7
        self.cun_head = self.cun_head_f

    def _head_arc(self, s):
        return s * self.cun_head_f if s <= 8 else 8 * self.cun_head_f + (s - 8) * self.cun_head_b

    def head(self, s, u=0.0):
        """s cun along the midline from the glabella (anterior hairline = 3, vertex GV20 = 8, posterior
        hairline = 15), then u cun across toward the right side."""
        pts, nrm, arc = self.sag
        a = self._head_arc(s)
        k = int(np.clip(np.searchsorted(arc, a), 1, len(arc) - 1))
        t = (a - arc[k - 1]) / max(arc[k] - arc[k - 1], 1e-12)
        p = pts[k - 1] + t * (pts[k] - pts[k - 1])
        n = unit(nrm[k - 1] + t * (nrm[k] - nrm[k - 1]))
        if u <= 0:
            return p, n
        if s > 11:
            # the back of the head: across along a horizontal arc from the posterior midline
            return self.trunk(p[1], u * self.cun_head_b / self.cun_h, "B", zc=float(self.head_c[2]))
        uh = unit(p - self.head_c)
        al = np.radians(np.arange(0, 120.5, 0.5))
        dirs = np.cos(al)[:, None] * uh[None] + np.sin(al)[:, None] * np.array([-1.0, 0, 0])[None]
        hits = [h for h in self.s.fan(self.head_c, dirs, np.cross(uh, [-1.0, 0, 0]), reach=0.03) if h is not None]
        q = np.array([h[0] for h in hits]); qn = np.array([h[1] for h in hits])
        qa = np.r_[0, np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))]
        k = int(np.clip(np.searchsorted(qa, u * (self.cun_head_f if s <= 8 else self.cun_head_b)), 1, len(qa) - 1))
        return q[k], qn[k]

    def occ(self, y, u):
        """Back of the head or neck at height y, u cun (head cun) from the posterior midline."""
        return self.trunk(y, u * self.cun_head_b / self.cun_h, "B", zc=float(self.head_c[2]))

    def front(self, x, y, n=(0, 0, 1)):
        """Face point seen from the front at (x, y)."""
        z = self.s.outer((x, y, 0.0), (0, 0, 1))[0][2]
        return self.s.snap((x, y, z), n, reach=0.004) or self.s.outer((x, y, 0.0), (0, 0, 1))

    def side(self, y, z, n=(-1, 0, 0), x0=-0.004):
        """Point on the right side of the head or neck at (y, z), cast along n from outside."""
        return self.s.outer((x0, y, z), n, reach=0.02)

    # ---- arm: T-pose arm along -x; palms down
    def _section_centre(self, c, plane_n, e1, e2, reach):
        """Centre (middle of the extent along e1 and e2) of the cross-section around c."""
        c = np.asarray(c, float)
        for _ in range(2):
            a = np.radians(np.arange(0, 360, 10))
            dirs = np.cos(a)[:, None] * e1[None] + np.sin(a)[:, None] * e2[None]
            hs = np.array([h[0] for h in self.s.fan(c, dirs, plane_n, reach) if h is not None])
            u, v = (hs - c) @ e1, (hs - c) @ e2
            c = c + (u.min() + u.max()) / 2 * e1 + (v.min() + v.max()) / 2 * e2
        return c

    def _arm_fit(self):
        xs, cy, cz = [], [], []
        e1, e2 = np.array([0, 1.0, 0]), np.array([0, 0, 1.0])
        for x in np.arange(-0.031, -0.0745, -0.0015):
            m = (abs(self.V[:, 0] - x) < 0.0015) & (abs(self.V[:, 1] + 0.022) < 0.012)
            c = self._section_centre(self.V[m].mean(0) * [0, 1, 1] + [x, 0, 0], e1 * 0 + [1, 0, 0], e1, e2, 0.015)
            xs.append(x); cy.append(c[1]); cz.append(c[2])
        self.arm_py, self.arm_pz = np.polyfit(xs, cy, 2), np.polyfit(xs, cz, 2)

    def arm_frame(self, x):
        """(anterior, radial) unit vectors of the arm at x: elbow crease forward at the elbow, the forearm
        turned (pronated) so the palm faces down at the wrist."""
        t = float(np.clip((X_ELBOW - x) / (X_ELBOW - X_WRIST), 0, 1))
        b = math.radians(90 * t)
        return np.array([0, -math.sin(b), math.cos(b)]), np.array([0, math.cos(b), math.sin(b)])

    def arm_centre(self, x):
        xx = max(x, -0.0760)
        return np.array([x, np.polyval(self.arm_py, xx), np.polyval(self.arm_pz, xx)])

    def arm(self, x, theta):
        """Point at x on the arm, theta degrees around it: 0 anterior (flexor side), 90 radial/lateral,
        180 posterior (extensor side), -90 ulnar/medial."""
        a, r = self.arm_frame(x)
        th = math.radians(theta)
        d = math.cos(th) * a + math.sin(th) * r
        return self.s.fan(self.arm_centre(x), d[None], (1, 0, 0), reach=0.02)[0]

    def hand(self, x, z, d):
        """Point of the hand or a finger near (x, z), cast from its inside along d (+y = back of the hand,
        -y = palm, +z = radial/thumb side, -z = ulnar side). (x, z) moves toward the middle of the hand
        until it is inside."""
        for k in range(12):
            zz = z + (0.0012 - z) * k / 12
            hs = self.s.line((x, -0.01, zz), (0, -1, 0), 0, 0.03)
            if len(hs) >= 2:
                c = np.array([x, (hs[0][1][1] + hs[1][1][1]) / 2, zz])
                return self.s.out(c, unit(d), reach=0.01)
        return None

    def finger(self, name, f, d):
        """Point f of the way from the MCP joint (0) to the tip (1) of a finger (the thumb from its
        MCP joint), cast from inside along d."""
        a, b = np.array(FINGER[name][1]), np.array(FINGER[name][2])
        x, z = a + f * (b - a)
        return self.hand(x, z, d)

    # ---- leg: right leg along -y
    def _leg_fit(self):
        ys, cx, cz = [], [], []
        e1, e2 = np.array([1.0, 0, 0]), np.array([0, 0, 1.0])
        for y in np.arange(-0.086, -0.1465, -0.0015):
            m = (abs(self.V[:, 1] - y) < 0.0015) & (self.V[:, 0] < -0.003)
            c = self._section_centre(self.V[m].mean(0) * [1, 0, 1] + [0, y, 0], [0, 1, 0], e1, e2, 0.03)
            ys.append(y); cx.append(c[0]); cz.append(c[2])
        self.leg_px, self.leg_pz = np.polyfit(ys, cx, 3), np.polyfit(ys, cz, 3)

    def leg_centre(self, y):
        yy = min(max(y, -0.1470), -0.0860)
        return np.array([np.polyval(self.leg_px, yy), y, np.polyval(self.leg_pz, yy)])

    def leg(self, y, theta):
        """Point at height y on the right leg, theta degrees around it: 0 anterior, 90 lateral,
        180 posterior, -90 medial."""
        th = math.radians(theta)
        d = np.array([-math.sin(th), 0, math.cos(th)])
        return self.s.fan(self.leg_centre(y), d[None], (0, 1, 0), reach=0.03)[0]

    # ---- foot: fl from the back of the heel (0) to the tip of the 2nd toe (1), fw from the medial (0)
    # to the lateral (1) edge. On the model the front of the ankle is at fl 0.38, the
    # metatarsophalangeal joints at 0.75 and the webs of the toes at 0.83.
    @lru_cache(maxsize=None)
    def _foot_box(self):
        m = (self.V[:, 1] < -0.1500) & (self.V[:, 0] < 0) & (self.V[:, 0] > -0.040)
        return float(self.V[m, 2].min()), float(self.V[m, 2].max())

    def foot_xz(self, fl, fw):
        z0, z1 = self._foot_box()
        z = z0 + fl * (z1 - z0)
        m = (abs(self.V[:, 2] - z) < 0.0006) & (self.V[:, 1] < -0.1505) & (self.V[:, 0] < 0) & (self.V[:, 0] > -0.040)
        xs = self.V[m, 0]
        med, lat = xs.max(), xs.min()
        return med - fw * (med - lat), z

    def foot(self, fl, fw, face, fh=0.3, y=None):
        """face D (dorsum), S (sole), M (medial side), L (lateral side); fh = height on the side
        from the sole (0) to the dorsum (1), or y given."""
        if face in "ML":                      # inside the edge; on the toes, inside the great or little toe
            fw = (0.2 if fl < 0.8 else 0.07) if face == "M" else (0.8 if fl < 0.8 else 0.93)
        for k in range(8):
            x, z = self.foot_xz(fl, fw + (0.5 - fw) * k / 8)
            hs = self.s.line((x, -0.140, z), (0, -1, 0), 0, 0.03)
            hs = [h for h in hs if h[1][1] < -0.1490] or hs
            if len(hs) >= 2:
                break
        # at the heel and ankle the line starts inside the leg: only the sole is hit
        top, bot = (hs[0][1][1] if len(hs) >= 2 else -0.1500), hs[-1][1][1]
        if face == "D":
            return hs[0][1], hs[0][2]
        if face == "S":
            return hs[-1][1], hs[-1][2]
        yy = y if y is not None else bot + fh * (top - bot)
        c = np.array([x, yy, z])
        return self.s.out(c, (1, 0, 0) if face == "M" else (-1, 0, 0), reach=0.02)

    # ---- generic helpers
    def toward_nearest(self, p):
        """Surface point on the line from p toward the nearest vertex (or that vertex)."""
        i = int(np.argmin(np.sum((self.V - p) ** 2, axis=1)))
        d = self.V[i] - p
        if np.linalg.norm(d) > 1e-9:
            hs = self.s.line(p, d, -0.006, 0.006)
            if hs:
                h = min(hs, key=lambda h: abs(h[0]))
                n = h[2] if h[2] @ self.N[i] > 0 else -h[2]
                return h[1], n
        return self.V[i], self.N[i]

    def between(self, a, b, f, n=None):
        """Point f of the way from a to b (each (point, normal)), snapped to the skin."""
        p = a[0] + f * (b[0] - a[0])
        nn = unit(n if n is not None else a[1] + b[1])
        return self.s.snap(p, nn, reach=0.01) or (p, nn)


# ------------------------------------------------------------------------------------- the text

WORDNUM = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "one": 1,
           "two": 2, "three": 3, "four": 4, "five": 5}
NUM = r"(\d+(?:\.\d+)?)"


def norm_text(t):
    t = t.lower().replace("centre", "center")
    t = re.sub(r"\b(b|body|f|finger)-cun\b", "cun", t)
    t = re.sub(r"\b([a-z]{2})-(\d+)\b", lambda m: m.group(1).upper() + m.group(2), t)
    return t


# the side of a limb a phrase puts the point on (degrees, see Body.arm / Body.leg)
ARM_SIDES = [
    ("between the palmaris longus and flexor carpi radialis", 0), ("between the long and short heads of biceps", 0),
    ("radial to the flexor carpi ulnaris", -50), ("radial to flexor carpi ulnaris", -50),
    ("medial border of the ulna and flexor carpi ulnaris", -120), ("directly radial to the ulna", -158),
    ("midway between the radius and ulna", 180), ("olecranon to the acromial angle", 180),
    ("behind and below the deltoid", 160), ("anterior to the deltoid", 80), ("li5 to li11", 125),
    ("li5 and li11", 125), ("li11 to li15", 110), ("lu5 to lu9", 50), ("abductor pollicis longus and extensor pollicis brevis", 88),
    ("radial styloid process and radial artery", 55), ("lateral to the biceps brachii", 40),
    ("medial to biceps", -62), ("medial to the biceps", -62),
]
LEG_SIDES = [
    ("posterior to the medial border of the tibia", -108), ("behind the medial border of the tibia", -100),
    ("center of the medial tibial surface", -55), ("anterior to the fibula", 72), ("behind the fibula", 108),
    ("posterior to the fibula", 108), ("between the fibula and calcaneal tendon", 140),
    ("lateral border of tibialis anterior", 42), ("tibialis anterior", 24), ("st35 to st41", 24),
    ("immediately anterior to the achilles tendon", -150), ("between the soleus and achilles tendon", -150),
    ("between the two heads of gastrocnemius", 180), ("between the gastrocnemius bellies", 180),
    ("lateral gastrocnemius and calcaneal tendon", 150),
    ("between vastus lateralis and the lateral border of the rectus femoris", 40), ("lateral to the rectus femoris", 32),
    ("lateral patellar base to the anterior superior iliac spine", 25), ("prominence of vastus medialis", -48),
    ("between gracilis and sartorius", -105), ("behind the iliotibial band", 100), ("biceps femoris and semitendinosus", 180),
    ("medial to the biceps femoris tendon", 160),
]

ORDINAL = r"(first|second|third|fourth|fifth|sixth|seventh|\d)(?:st|nd|rd|th)?"


def parse(pid, text, body, P):
    """Spec of a point from its location text, or None. P(id) resolves another point."""
    t = norm_text(text)
    b = body

    def num(m, i=1):
        return float(m.group(i))

    lat = None
    m = re.search(NUM + r" cun (?:lateral to|from) the (?:anterior |posterior )?(?:midline|median sacral crest)", t)
    if m:
        lat = num(m)
    elif "on the anterior midline" in t or "on the posterior midline" in t or "on the midline" in t:
        lat = 0.0

    # ---- back: vertebral levels and sacral foramina
    m = re.search(r"(?:lower edge|inferior border) of the ([ctl]\d+) spinous process", t) or \
        re.search(r"below the spinous process of ([ctl]\d+)", t)
    if m and lat is not None:
        return b.trunk(spine_y(m.group(1).upper()), lat, "B")
    m = re.search(ORDINAL + r" posterior sacral foramen", t)
    if m:
        n = WORDNUM.get(m.group(1)) or int(m.group(1))
        return b.trunk(SACRAL[n], lat if lat is not None else 0.75 + 0.05 * n, "B")

    # ---- front of the trunk: cun from the umbilicus, intercostal spaces
    m = re.search(NUM + r" cun (above|below) the (?:center of the )?umbilicus", t)
    if m or "lateral to the center of the umbilicus" in t or "at the center of the umbilicus" in t:
        if m:
            v = num(m) * (CUN_V_UP if m.group(2) == "above" else -CUN_V_LO)
        else:
            v = 0.0
        if lat is None:
            mm = re.search(NUM + r" cun lateral to the center of the umbilicus", t)
            lat = num(mm) if mm else (0.0 if "at the center of the umbilicus" in t else None)
        if lat is not None:
            return b.trunk(Y_NAVEL + v, lat, "F")
    m = re.search(ORDINAL + r" intercostal space", t)
    if m:
        n = WORDNUM.get(m.group(1)) or int(m.group(1))
        y = ics_y(n)
        if "midaxillary line" in t:
            mm = re.search(NUM + r" cun anterior to the midaxillary line", t)
            return b.midaxillary(y, num(mm) if mm else 0.0)
        if lat is not None:
            return b.trunk(y, lat, "F")
    if "pubic symphysis" in t and lat is not None and "upper" in t:
        return b.trunk(Y_PUBIS, lat, "F")

    # ---- head: cun from the hairlines
    m = re.search(NUM + r" cun (?:above|behind|superior to) the anterior hairline", t)
    if m:
        s = 3 + num(m)
        mm = re.search(NUM + r" cun (?:from|lateral to) the midline", t)
        u = num(mm) if mm else (2.25 if "above the center of the pupil" in t or "directly above the pupil" in t else 0.0)
        return b.head(s, u)
    m = re.search(NUM + r" cun above the posterior hairline", t)
    if m:
        return b.head(15 - num(m), 0.0)

    # ---- arm
    side = next((v for k, v in ARM_SIDES if k in t.lower()), None)
    m = re.search(NUM + r" cun (?:above|proximal to) the (?:palmar |dorsal )?wrist crease", t)
    if m and side is not None:
        return b.arm(X_WRIST + num(m) * CUN_FORE, side)
    m = re.search(NUM + r" cun below the cubital crease", t)
    if m and side is not None:
        return b.arm(X_ELBOW - num(m) * CUN_FORE, side)
    m = re.search(NUM + r" cun above the cubital crease", t)
    if m:
        return b.arm(X_ELBOW + num(m) * CUN_UPPER, side if side is not None else (-62 if "medial" in t else 110))
    m = re.search(NUM + r" cun below the anterior axillary fold", t)
    if m and side is not None:
        return b.arm(X_AXFOLD - num(m) * CUN_UPPER, side)
    m = re.search(NUM + r" cun above the olecranon", t)
    if m:
        return b.arm(X_ELBOW + num(m) * CUN_UPPER, 180)
    m = re.search(NUM + r" cun below the tip of the olecranon", t)
    if m and side is not None:
        return b.arm(X_ELBOW - num(m) * CUN_FORE, side)
    m = re.search(NUM + r" cun below the acromial angle", t)
    if m:
        return b.arm(ACROMION[0] - num(m) * CUN_UPPER, side if side is not None else 165)
    m = re.search(NUM + r" cun above (LI11)", t)
    if m:
        return b.arm(X_ELBOW + num(m) * CUN_UPPER, side if side is not None else 95)

    # ---- leg
    side = next((v for k, v in LEG_SIDES if k in t.lower()), None)
    m = re.search(NUM + r" cun above the (?:prominence of the |tip of the )?(medial|lateral) malleolus", t)
    if m and side is not None:
        if m.group(2) == "medial":
            return b.leg(Y_MM + num(m) * CUN_LEG_MED, side)
        return b.leg(Y_LM + num(m) * CUN_LEG_LAT, side)
    m = re.search(NUM + r" cun below (ST35)", t)
    if m and side is not None:
        return b.leg(Y_ST35 - num(m) * CUN_LEG_LAT, side)
    m = re.search(NUM + r" cun below the popliteal crease", t)
    if m and side is not None:
        return b.leg(Y_POP - num(m) * CUN_LEG_LAT, side)
    m = re.search(NUM + r" cun above the popliteal crease", t)
    if m:
        return b.leg(Y_POP + num(m) * CUN_THIGH, side if side is not None else 150)
    m = re.search(NUM + r" cun above the (?:medial end of the |lateral )?(?:base of the patella|patellar base)", t)
    if m and side is not None:
        return b.leg(Y_PAT_BASE + num(m) * CUN_THIGH, side)
    m = re.search(NUM + r" cun below the gluteal fold", t)
    if m and side is not None:
        return b.leg(Y_GLUT - num(m) * CUN_THIGH, side)
    m = re.search(NUM + r" cun above (BL60)", t)
    if m and side is not None:
        return b.leg(Y_LM + num(m) * CUN_LEG_LAT, side)
    m = re.search(NUM + r" cun (above|below) ([A-Z]{2}\d+)", t)
    if m and side is not None and P(m.group(3)) is not None and P(m.group(3))[0][1] < -0.085:
        return b.leg(P(m.group(3))[0][1] + (1 if m.group(2) == "above" else -1) * num(m) * CUN_LEG_MED, side)
    m = re.search(NUM + r" cun distal to (ST30)", t)
    if m:
        return b.leg(Y_PUBIS - num(m) * CUN_THIGH, -72 if "femoral artery" in t else -60)
    return None


def landmark(name, b):
    """Named landmarks used by 'midway between ...' texts."""
    if name.startswith("c7 spinous"):
        return b.trunk(Y_C7, 0, "B")
    if "acromion" in name:
        return b.s.outer((ACROMION[0] + 0.0005, ACROMION[1], -0.001), (0, 1, 0))
    if "anterior superior iliac spine" in name:
        return b.trunk_x(ASIS[1], ASIS[0], "F")
    if "greater trochanter" in name:
        return b.leg(Y_TROCH, 90)
    if "sacral hiatus" in name:
        return b.trunk(Y_HIATUS, 0, "B")
    return None


def parse_between(pid, text, b, P):
    """'halfway between X and Y', 'at the upper-third point of the line from X to Y', ..."""
    t = norm_text(text)
    pat = [(r"(?:halfway|midway) (?:between|along the line from) (?:the )?([A-Za-z0-9 \-]+?) (?:and|to) (?:the )?([A-Za-z0-9 \-]+?)(?:[;,.]|$)", 0.5),
           (r"midpoint of the line (?:between|connecting) (?:the )?([A-Za-z0-9 \-]+?) and (?:the )?([A-Za-z0-9 \-]+?)(?:[;,.]|$)", 0.5),
           (r"upper-quarter point of the curved line joining ([A-Z]{2}\d+) and ([A-Z]{2}\d+)", 0.25),
           (r"lower-quarter point of the curved line connecting ([A-Z]{2}\d+) with ([A-Z]{2}\d+)", 0.75),
           (r"halfway along the curved line from ([A-Z]{2}\d+) to ([A-Z]{2}\d+)", 0.5),
           (r"upper-third point of the curved line running from ([A-Z]{2}\d+) to ([A-Z]{2}\d+)", 1 / 3),
           (r"lower-third point of the curved line between ([A-Z]{2}\d+) and ([A-Z]{2}\d+)", 2 / 3),
           (r"junction of the lower third and upper two thirds of the curved line from ([A-Z]{2}\d+) to ([A-Z]{2}\d+)", 1 / 3),
           (r"junction of the upper third and lower two thirds of the curved line from ([A-Z]{2}\d+) to ([A-Z]{2}\d+)", 2 / 3),
           (r"lateral-third point of the line from the ([a-z ]+?) to the ([a-z ]+?)(?:[;,.]|$)", 1 / 3)]
    t2 = re.sub(r"\b([a-z]{2})(\d+)\b", lambda m: m.group(1).upper() + m.group(2), t)
    for rx, f in pat:
        m = re.search(rx, t2)
        if not m:
            continue
        ends = []
        for g in (m.group(1), m.group(2)):
            g = g.strip()
            if re.fullmatch(r"[A-Z]{2}\d+", g):
                ends.append(P(g))
            else:
                ends.append(landmark(g, b))
        if all(e is not None for e in ends):
            return b.between(ends[0], ends[1], f)
    return None


def manual(b, P):
    """Positions read by hand from the AcuAtlas text, for texts that name a spot rather than a
    distance. Each entry quotes the words it follows."""
    cv, cl, cu, ct = CUN_V_UP, CUN_LEG_LAT, CUN_UPPER, CUN_THIGH
    F, S = FACE, SIDE
    return {
        # --- Lung
        "LU1": lambda: b.trunk(ics_y(1), 6, "F"),                         # 1st ICS, 6 cun lateral
        "LU2": lambda: b.trunk(Y_CLAV - 0.0006, 6, "F"),                   # infraclavicular fossa, 6 cun lateral
        "LU5": lambda: b.arm(X_ELBOW, 28),                                 # cubital crease, lateral to the biceps tendon
        "LU9": lambda: b.arm(X_WRIST, 48),                                 # radial side of the palmar wrist crease
        "LU10": lambda: b.hand(-0.0812, 0.0078, (0, -0.55, 0.85)),       # radial to the midpoint of the 1st metacarpal
        "LU11": lambda: b.finger("thumb", 0.82, (0, 0.55, 0.85)),         # radial corner of the thumbnail
        # --- Large intestine
        "LI1": lambda: b.finger("index", 0.86, (0, 0.55, 0.85)),          # radial corner of the index nail
        "LI2": lambda: b.finger("index", 0.12, (0, 0.2, 1)),              # distal to the 2nd MCP joint, radial side
        "LI3": lambda: b.hand(X_MCP + 0.0010, 0.0066, (0, 0.35, 1)),      # radial and proximal to the 2nd MCP joint
        "LI4": lambda: b.hand((X_WRIST + X_MCP) / 2, 0.0060, (0, 0.85, 0.5)),  # radial side of the midpoint of the 2nd metacarpal
        "LI5": lambda: b.arm(X_WRIST - 0.0004, 118),                      # anatomical snuffbox, radial end of the dorsal crease
        "LI11": lambda: b.arm(X_ELBOW + 0.0004, 78),                      # lateral end of the cubital crease
        "LI12": lambda: b.arm(X_ELBOW + 1.0 * cu, 118),                   # above the lateral epicondyle
        "LI15": lambda: b.s.snap((ACROMION[0] - 0.0012, ACROMION[1] - 0.0012, 0.0030), (0, 0.45, 1), 0.006),
        "LI16": lambda: b.s.outer((ACROMION[0] + 0.0060, -0.010, -0.0025), (0, 1, 0)),
        "LI17": lambda: b.trunk_phi(Y_CRICOID, 66),   # cricoid level, behind the SCM border
        "LI18": lambda: b.trunk_phi(Y_THYROID, 62),           # between the borders of the SCM
        "LI19": lambda: b.front(-0.0011, F["philtrum"][1]),
        "LI20": lambda: b.front(-0.0025, F["ala"][1], (-0.4, 0, 1)),     # nasolabial groove, level with the ala
        # --- Stomach
        "ST1": lambda: b.front(F["pupil"][0], -0.0006),
        "ST2": lambda: b.front(F["pupil"][0], -0.0014),
        "ST3": lambda: b.front(F["pupil"][0], F["ala_low"][1]),
        "ST4": lambda: b.front(F["mouth"][0] - 0.0008, F["mouth"][1]),
        "ST5": lambda: b.side(S["jaw_angle"][0] - 0.0004, S["jaw_angle"][1] + 0.0028, (-0.8, -0.3, 0.5)),
        "ST6": lambda: b.side(S["jaw_angle"][0] + 0.0016, S["jaw_angle"][1] + 0.0012, (-1, 0, 0.25)),
        "ST7": lambda: b.side(S["zygoma_mid"][0] - 0.0009, S["zygoma_mid"][1] - 0.0008),
        "ST8": lambda: b.head(3.5, 4.5),
        "ST9": lambda: b.trunk_phi(Y_THYROID, 42),
        "ST10": lambda: b.trunk_phi(Y_CRICOID, 42),
        "ST11": lambda: b.trunk_x(Y_SUPRACLAV, -0.0030, "F"),
        "ST12": lambda: b.trunk(Y_SUPRACLAV, 4, "F"),
        "ST13": lambda: b.trunk(Y_CLAV, 4, "F"),
        "ST17": lambda: b.trunk_x(NIPPLE[1], NIPPLE[0], "F"),
        "ST30": lambda: b.trunk(Y_PUBIS, 2, "F"),
        "ST31": lambda: b.leg(Y_PUBIS - 2.5 * ct, 32),                     # below the ASIS, triangle of the thigh
        "ST35": lambda: b.leg(Y_ST35, 32),                                 # lateral to the patellar ligament
        "ST41": lambda: b.leg(Y_ANKLE_FRONT, 4),                           # centre of the anterior ankle
        "ST42": lambda: b.foot(0.50, 0.38, "D"),
        "ST43": lambda: b.foot(0.71, 0.45, "D"),
        "ST44": lambda: b.foot(0.82, 0.44, "D"),
        "ST45": lambda: b.foot(0.96, 0.40, "D"),
        # --- Spleen
        "SP1": lambda: b.foot(0.94, 0, "M", fh=0.65),
        "SP2": lambda: b.foot(0.79, 0, "M", fh=0.30),
        "SP3": lambda: b.foot(0.71, 0, "M", fh=0.28),
        "SP4": lambda: b.foot(0.52, 0, "M", fh=0.28),
        "SP5": lambda: b.foot(0.30, 0, "M", fh=0.62),
        "SP9": lambda: b.leg(Y_SP9, -100),
        "SP11": lambda: b.leg(Y_PUBIS - (Y_PUBIS - Y_PAT_BASE) / 3, -62),
        "SP12": lambda: b.trunk(Y_PUBIS + 0.0004, 3.5, "F"),
        "SP15": lambda: b.trunk(Y_NAVEL, 4, "F"),
        "SP21": lambda: b.midaxillary(ics_y(6)),
        # --- Heart
        "HT1": lambda: b.s.snap((X_AXFOLD + 0.0025, -0.0300, -0.0005), (0, -1, 0), 0.01),
        "HT3": lambda: b.arm(X_ELBOW, -72),
        "HT7": lambda: b.arm(X_WRIST, -68),
        "HT8": lambda: b.hand(-0.0850, -0.0026, (0, -1, 0)),
        "HT9": lambda: b.finger("little", 0.86, (0, 0.55, 0.85)),
        # --- Small intestine
        "SI1": lambda: b.finger("little", 0.86, (0, 0.55, -0.85)),
        "SI2": lambda: b.finger("little", 0.12, (0, 0.1, -1)),
        "SI3": lambda: b.hand(-0.0848, -0.0036, (0, 0.1, -1)),
        "SI4": lambda: b.hand(X_WRIST - 0.0022, -0.0024, (0, 0.1, -1)),
        "SI5": lambda: b.arm(X_WRIST + 0.0002, -112),
        "SI6": lambda: b.arm(X_WRIST + CUN_FORE, -150),
        "SI8": lambda: b.arm(X_ELBOW, -140),
        "SI9": lambda: b.trunk_x(SCAP["post_fold"][1] + CUN_V_UP, SCAP["post_fold"][0], "B"),
        "SI10": lambda: b.trunk_x(SCAP["spine_mid"][1] + 0.0010, SCAP["post_fold"][0] + 0.0010, "B"),
        "SI11": lambda: b.trunk_x(SCAP["spine_mid"][1] + (SCAP["inf_angle"][1] - SCAP["spine_mid"][1]) / 3,
                                  SCAP["spine_mid"][0] + (SCAP["inf_angle"][0] - SCAP["spine_mid"][0]) / 3, "B"),
        "SI12": lambda: b.trunk_x(SCAP["spine_mid"][1] + 0.0018, SCAP["spine_mid"][0], "B"),
        "SI13": lambda: b.trunk_x(SCAP["spine_med"][1] + 0.0010, SCAP["spine_med"][0], "B"),
        "SI16": lambda: b.trunk_phi(Y_THYROID, 80),
        "SI17": lambda: b.side(S["jaw_angle"][0] - 0.0004, S["jaw_angle"][1] - 0.0016, (-1, -0.2, 0)),
        "SI18": lambda: b.front(F["outer_canthus"][0], -0.0024, (-0.5, 0, 1)),
        "SI19": lambda: b.side(S["tragus"][0], S["tragus"][1] + 0.0007),
        # --- Bladder
        "BL1": lambda: b.front(F["inner_canthus"][0] + 0.0002, F["inner_canthus"][1] + 0.0004, (0.5, 0, 1)),
        "BL2": lambda: b.front(F["brow_med"][0], F["brow_med"][1]),
        "BL3": lambda: b.head(3.5, 0.75),
        "BL9": lambda: b.head(12.5, 1.3),
        "BL10": lambda: b.head(14.6, 1.3),
        "BL31": lambda: b.trunk(SACRAL[1], 0.8, "B"),
        "BL32": lambda: b.trunk(SACRAL[2], 0.85, "B"),
        "BL33": lambda: b.trunk(SACRAL[3], 0.9, "B"),
        "BL34": lambda: b.trunk(SACRAL[4], 0.95, "B"),
        "BL35": lambda: b.trunk(Y_COCCYX, 0.5, "B"),
        "BL36": lambda: b.leg(Y_GLUT, 180),
        "BL37": lambda: b.leg(Y_GLUT - 6 * ct, 180),
        "BL38": lambda: b.leg(Y_POP + 1 * ct, 155),
        "BL39": lambda: b.leg(Y_POP, 152),
        "BL40": lambda: b.leg(Y_POP, 180),
        "BL57": lambda: b.leg(Y_POP - 8 * cl, 180),                        # where the gastrocnemius bellies meet the tendon
        "BL58": lambda: b.leg(Y_LM + 7 * cl, 150),
        "BL60": lambda: b.leg(Y_LM, 138),
        "BL61": lambda: b.foot(0.10, 0, "L", fh=0.22),
        "BL62": lambda: b.foot(0.25, 0, "L", y=Y_LM - 0.0019),
        "BL63": lambda: b.foot(0.41, 0, "L", fh=0.30),
        "BL64": lambda: b.foot(0.475, 0, "L", fh=0.25),
        "BL65": lambda: b.foot(0.66, 0, "L", fh=0.30),
        "BL66": lambda: b.foot(0.74, 0, "L", fh=0.30),
        "BL67": lambda: b.foot(0.88, 0, "L", fh=0.55),
        # --- Kidney
        "KI1": lambda: b.foot(0.56, 0.45, "S"),
        "KI2": lambda: b.foot(0.38, 0, "M", fh=0.30),
        "KI3": lambda: b.leg(Y_MM, -138),
        "KI4": lambda: b.foot(0.13, 0, "M", fh=0.62),
        "KI5": lambda: b.foot(0.15, 0, "M", fh=0.45),
        "KI6": lambda: b.foot(0.22, 0, "M", y=Y_MM - CUN_LEG_MED),
        "KI8": lambda: b.leg(Y_MM + 2 * CUN_LEG_MED, -118),
        "KI10": lambda: b.leg(Y_POP, -148),
        "KI16": lambda: b.trunk(Y_NAVEL, 0.5, "F"),
        "KI27": lambda: b.trunk(Y_CLAV, 2, "F"),
        # --- Pericardium
        "PC1": lambda: b.trunk(ics_y(4), 5, "F"),
        "PC3": lambda: b.arm(X_ELBOW, -14),
        "PC7": lambda: b.arm(X_WRIST, 0),
        "PC8": lambda: b.hand(-0.0848, 0.0040, (0, -1, 0)),
        "PC9": lambda: b.finger("middle", 0.97, (-1, 0, 0)),
        # --- Triple energizer
        "TE1": lambda: b.finger("ring", 0.86, (0, 0.55, -0.85)),
        "TE2": lambda: b.hand(-0.0884, -0.0028, (0, 1, 0)),
        "TE3": lambda: b.hand(-0.0852, -0.0026, (0, 1, 0)),
        "TE4": lambda: b.arm(X_WRIST, -168),
        "TE10": lambda: b.arm(X_ELBOW + 1 * cu, 180),
        "TE13": lambda: b.arm(ACROMION[0] - 3 * cu, 162),
        "TE14": lambda: b.s.snap((ACROMION[0] - 0.0012, ACROMION[1] - 0.0012, -0.0040), (0, 0.45, -1), 0.006),
        "TE16": lambda: b.side(S["jaw_angle"][0], S["jaw_angle"][1] - 0.0042, (-1, 0, -0.35)),
        "TE17": lambda: b.side(S["lobe"][0] - 0.0004, S["lobe"][1] - 0.0004, (-0.6, -0.2, -0.6)),
        "TE20": lambda: b.side(S["ear_apex"][0] + 0.0012, S["ear_apex"][1]),
        "TE21": lambda: b.side(S["tragus"][0] + 0.0010, S["tragus"][1] + 0.0008),
        "TE22": lambda: b.side(S["temple_hair"][0] - 0.0004, S["tragus"][1] + 0.0010),
        "TE23": lambda: b.front(F["brow_lat"][0], F["brow_lat"][1], (-0.5, 0, 1)),
        # --- Gall bladder
        "GB1": lambda: b.front(F["outer_canthus"][0] - 0.0011, F["outer_canthus"][1], (-0.8, 0, 0.6)),
        "GB2": lambda: b.side(S["tragus"][0] - 0.0010, S["tragus"][1] + 0.0007),
        "GB3": lambda: b.side(S["zygoma_mid"][0] + 0.0010, S["zygoma_mid"][1] - 0.0008),
        "GB7": lambda: b.side(S["ear_apex"][0], S["temple_hair"][1], (-1, 0.15, 0)),
        "GB8": lambda: b.side(S["ear_apex"][0] + 0.0012 + 1.5 * self_cun_head(b), S["ear_apex"][1]),
        "GB9": lambda: b.side(S["ear_apex"][0] + 0.0012 + 2 * self_cun_head(b), S["ear_apex"][1] - 0.0016 - 0.5 * self_cun_head(b)),
        "GB12": lambda: b.occ(S["mastoid"][0] - 0.0008, 3.0),                # behind and below the mastoid
        "GB14": lambda: b.front(F["pupil"][0], F["brow_med"][1] + self_cun_head(b)),
        "GB15": lambda: b.head(3.5, 2.25),
        "GB16": lambda: b.head(4.5, 2.25),
        "GB17": lambda: b.head(5.5, 2.25),
        "GB18": lambda: b.head(7.0, 2.25),
        "GB19": lambda: b.head(12.5, 1.8),                                   # above GB20, level with the EOP
        "GB20": lambda: b.head(14.0, 1.8),                                   # level with GV16, between SCM and trapezius
        "GB21": None,                                                        # parsed: midway C7 - acromion
        "GB22": lambda: b.midaxillary(ics_y(4)),
        "GB25": lambda: b.trunk_phi(Y_NAVEL + 1.5 * cv, 104),
        "GB26": lambda: b.trunk_phi(Y_NAVEL, 78),
        "GB27": lambda: b.trunk_x(Y_NAVEL - 3 * CUN_V_LO, ASIS[0] + 0.0012, "F"),
        "GB28": lambda: b.trunk_x(Y_NAVEL - 3.5 * CUN_V_LO, ASIS[0] + 0.0020, "F"),
        "GB29": None,                                                        # parsed: midpoint ASIS - greater trochanter
        "GB30": None,                                                        # parsed: lateral third trochanter - hiatus
        "GB31": lambda: b.leg(Y_POP + 9 * ct, 96),
        "GB33": lambda: b.leg(Y_PAT_BASE - 0.0012, 104),
        "GB34": lambda: b.leg(Y_POP - 2.2 * cl, 66),
        "GB40": lambda: b.leg(Y_LM - 0.0010, 58),
        "GB41": lambda: b.foot(0.56, 0.80, "D"),
        "GB42": lambda: b.foot(0.70, 0.79, "D"),
        "GB43": lambda: b.foot(0.81, 0.78, "D"),
        "GB44": lambda: b.foot(0.93, 0.76, "D"),
        # --- Liver
        "LR1": lambda: b.foot(0.95, 0.20, "D"),
        "LR2": lambda: b.foot(0.82, 0.24, "D"),
        "LR3": lambda: b.foot(0.585, 0.28, "D"),
        "LR4": lambda: b.leg(Y_MM - 0.0004, -32),
        "LR7": lambda: b.leg(Y_SP9, -128),
        "LR8": lambda: b.leg(Y_POP + 0.0004, -118),
        "LR9": lambda: b.leg(Y_PAT_BASE + 4 * ct, -105),
        "LR12": lambda: b.trunk(Y_PUBIS, 2.5, "F"),
        "LR13": lambda: b.trunk_phi(Y_NAVEL + 2 * cv, 76),
        # --- Conception vessel
        "CV1": lambda: b.s.outer((0, -0.080, -0.0005), (0, -1, 0), 0.02),
        "CV2": lambda: b.trunk(Y_PUBIS, 0, "F"),
        "CV15": lambda: b.trunk(Y_XIPH - CUN_V_UP, 0, "F"),
        "CV16": lambda: b.trunk(Y_XIPH, 0, "F"),
        "CV17": lambda: b.trunk(ics_y(4), 0, "F"),
        "CV21": lambda: b.trunk(Y_SS - CUN_V_UP, 0, "F"),
        "CV22": lambda: b.trunk(Y_SS, 0, "F"),
        "CV23": lambda: b.trunk(Y_HYOID, 0, "F"),
        "CV24": lambda: b.front(0, F["chin_groove"][1]),
        # --- Governing vessel
        "GV1": lambda: b.s.outer((0, -0.0790, -0.0040), (0, -0.6, -0.8), 0.02),
        "GV2": lambda: b.trunk(Y_HIATUS, 0, "B"),
        "GV15": lambda: b.head(14.5, 0),
        "GV16": lambda: b.head(14.0, 0),
        "GV17": lambda: b.head(12.5, 0),
        "GV19": lambda: b.head(9.5, 0),
        "GV20": lambda: b.head(8.0, 0),
        "GV21": lambda: b.head(6.5, 0),
        "GV25": lambda: b.front(0, F["nose_tip"][1]),
        "GV26": lambda: b.front(0, F["philtrum"][1]),
        "GV27": lambda: b.front(0, F["lip"][1]),
        "GV28": lambda: b.front(0, F["lip"][1] - 0.0002),
    }


def self_cun_head(b):
    return b.cun_head


# --------------------------------------------------------------------------------- the fallback
# The earlier placement: the schematic position of body_map.js mapped onto the model.

def schematic_places():
    js = ("global.window = {}; require(%s); require(%s);"
          "const out = {}; Object.keys(window.TCM_TX.points).forEach(id => out[id] = window.TCMBodyMap.place(id));"
          "console.log(JSON.stringify(out));") % (json.dumps(str(APP / "body_map.js")), json.dumps(str(APP / "treatment_kb.js")))
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)


def location_texts():
    text = (APP / "treatment_kb.js").read_text("utf-8")
    pts = json.loads(text.split("=", 1)[1].rstrip().rstrip(";"))["points"]
    return {k: v.get("loc", "") for k, v in pts.items()}


def interp(x, xs, ys):
    return float(np.interp(x, xs, ys))


Y2 = [18, 60, 80, 112, 165, 205, 222, 300, 385, 415]
YM = [0.01445, -0.0125, -0.0188, -0.0388, -0.0590, -0.0730, -0.0765, -0.1090, -0.1532, -0.1625]
HEAD_X, TORSO_X = 0.000419, 0.000545
LEG_OUT = ([222, 232, 300, 370, 388, 406, 415], [63, 62, 67, 73, 72, 69, 72])
LEG_IN = ([222, 240, 300, 330, 392, 415], [100, 98, 94, 91, 92, 92])
ARM_Y = [90, 160, 228, 270]
ARM_XM = [-0.0209, -0.0547, -0.0814, -0.0996]
ARM_OUT = ([90, 125, 160, 226, 244, 262, 273], [56, 50, 40, 30, 22, 21, 26])
ARM_IN = ([104, 122, 165, 232, 250, 272], [70, 62, 54, 42, 40, 37])


def schematic(b, p):
    V, N = b.V, b.N
    x2, y2, view = p["x"], p["y"], p["view"]

    def nearest(target, mask=None):
        dz = 1 if view == "F" else -1
        ok = N[:, 2] * dz > -0.05
        if mask is not None:
            ok &= mask
        idx = np.where(ok)[0]
        dist = (V[idx, 0] - target[0]) ** 2 + (V[idx, 1] - target[1]) ** 2
        near = idx[np.argsort(dist)[:6]]
        return near[np.argmax(V[near, 2] * dz)]

    if x2 < 64 and 95 < y2 < 275:
        y2 = min(max(y2, 90), 272)
        xm = interp(y2, ARM_Y, ARM_XM)
        out, inn = interp(y2, *ARM_OUT), interp(y2, *ARM_IN)
        c, hw = (out + inn) / 2, max((inn - out) / 2, 1)
        s = max(-1, min(1, (x2 - c) / hw))
        th = math.radians(70) * s
        n = np.array([0, -math.cos(th), -math.sin(th)]) if view == "F" else np.array([0, math.cos(th), -math.sin(th)])
        slab = np.where((abs(V[:, 0] - xm) < 0.0012) & (V[:, 0] < -0.015))[0]
        cy, cz = V[slab, 1].mean(), V[slab, 2].mean()
        dirs = np.c_[V[slab, 1] - cy, V[slab, 2] - cz]
        dirs /= np.linalg.norm(dirs, axis=1)[:, None] + 1e-12
        i = slab[np.argmax(dirs @ n[1:])]
    elif math.hypot(x2 - 100, y2 - 38) <= 21:
        dx, dy = (x2 - 100) / 20, (38 - y2) / 20
        dz = math.sqrt(max(0.0, 1 - dx * dx - dy * dy)) * (1 if view == "F" else -1)
        head = np.where((V[:, 1] > -0.0125) & (abs(V[:, 0]) < 0.012))[0]
        lo, hi = V[head].min(0), V[head].max(0)
        d = (V[head] - (lo + hi) / 2) / ((hi - lo) / 2)
        d /= np.linalg.norm(d, axis=1)[:, None]
        want = np.array([dx, dy, dz]) / max(1e-9, math.sqrt(dx * dx + dy * dy + dz * dz))
        i = head[np.argmax(d @ want)]
    else:
        ym = interp(y2, Y2, YM)
        if y2 < 62:
            xm = (x2 - 100) * HEAD_X
        elif y2 <= 222:
            xm = (x2 - 100) * TORSO_X
        else:
            o, n_ = interp(y2, *LEG_OUT), interp(y2, *LEG_IN)
            sl = V[(abs(V[:, 1] - ym) < 0.0015) & (V[:, 0] < -0.002) & (V[:, 0] > -0.04)]
            xm = sl[:, 0].min() + (x2 - o) / (n_ - o) * (sl[:, 0].max() - sl[:, 0].min())
        if abs(x2 - 100) < 0.5:
            xm = 0.0
        i = nearest((xm, ym), None if y2 < 222 else V[:, 0] < -0.001)
    return V[i].copy(), N[i]


# ------------------------------------------------------------------------------------- build

def place_all():
    """{point_id: (point, normal, method)}; method is 'text' (parsed from the location text),
    'manual' (read from the text by hand, MANUAL) or 'schematic' (the fallback)."""
    b = Body()
    texts = location_texts()
    man = manual(b, None)
    places = schematic_places()
    done = {}

    def P(pid):
        if pid not in done:
            done[pid] = None             # guards against cycles
            done[pid] = resolve(pid)
        return done[pid][:2] if done[pid] else None

    def resolve(pid):
        text = texts.get(pid, "")
        if man.get(pid):
            r = man[pid]()
            if r is not None:
                return r[0], r[1], "manual"
        for f in (parse, parse_between):
            r = f(pid, text, b, P)
            if r is not None:
                return r[0], r[1], "text"
        p = places.get(pid)
        if p:
            v, n = schematic(b, p)
            return v, n, "schematic"
        return None

    for pid in sorted(texts, key=sort_key):
        P(pid)
    out = {}
    for pid in sorted(texts, key=sort_key):
        r = done[pid]
        if r is None:
            continue
        v, n, how = np.array(r[0], float), unit(r[1]), r[2]
        if pid[:2] in ("CV", "GV"):
            v[0], n[0] = 0.0, 0.0
            n = unit(n)
        out[pid] = (v, n, how)
    return b, out


def sort_key(pid):
    m = re.match(r"([A-Z]+)(\d+)", pid)
    return (m.group(1), int(m.group(2))) if m else (pid, 0)


# the 3D course of each channel: its points in order, broken where the course leaves the skin path
# (the face part of the stomach channel, the sacral foramina and the outer line of the bladder channel)
BREAKS = {"ST": {9}, "BL": {31, 41}}
STEP = 0.0016             # spacing of the samples between two points


def vias(b):
    """Waypoints on the skin between a point and the next one of its channel, where the straight line
    between them would cut through the body or the armpit of the T-pose."""
    return {
        "LU2": [b.arm(-0.0262, 18)],                                   # over the front of the shoulder
        "PC1": [b.trunk(ics_y(3.4), 6.2, "F"), b.arm(-0.0262, 5)],     # along the anterior axillary fold
        "GB21": [b.trunk(Y_SUPRACLAV - 0.0004, 5.8, "F"), b.trunk(ics_y(2), 7.0, "F"), b.trunk(ics_y(3), 8.0, "F")],
        "GB20": [b.occ(-0.0080, 2.6)],                                 # down the back of the neck
        "SI15": [b.trunk_phi(-0.0175, 112)],                           # around the side of the neck
        "GV1": [b.trunk(Y_COCCYX - 0.0008, 0, "B")],                   # by the tip of the coccyx
        "PC8": [b.finger("middle", 0.0, (0, -1, 0)), b.finger("middle", 0.5, (0, -1, 0))],
        "HT8": [b.finger("little", 0.0, (0, -0.5, 0.6))],
        "LU10": [b.finger("thumb", 0.3, (0, -0.4, 1))],
    }
LIFT = 0.0007             # the line sits this far off the skin (body3d.js lifts the markers as much)


def paths(b, pts):
    """{channel: [[[x, y, z], ...], ...]}: polylines over the skin, lifted by LIFT."""
    out = {}
    chans = {}
    via = {k: [w for w in v if w is not None] for k, v in vias(b).items()}
    for pid in pts:
        m = re.match(r"([A-Z]+)(\d+)$", pid)
        chans.setdefault(m.group(1), []).append(int(m.group(2)))
    for ch, nums in sorted(chans.items()):
        nums.sort()
        runs, cur = [], []
        for n in nums:
            if n in BREAKS.get(ch, ()) and cur:
                runs.append(cur)
                cur = []
            cur.append(n)
        runs.append(cur)
        polylines = []
        for run in runs:
            if len(run) < 2:
                continue
            line = []
            for a, c in zip(run, run[1:]):
                stops = [pts[ch + str(a)]] + [(np.array(w[0]), unit(w[1])) for w in via.get(ch + str(a), [])] + [pts[ch + str(c)]]
                for (pa, na), (pc, nc) in zip(stops, stops[1:]):
                    line.append(pa + LIFT * na)
                    k = max(1, int(np.linalg.norm(pc - pa) / STEP))
                    for i in range(1, k):
                        f = i / k
                        nn = na + f * (nc - na)
                        nn = unit(nn if np.linalg.norm(nn) > 0.3 else na + nc + 1e-6)
                        p = pa + f * (pc - pa)
                        h = b.s.snap(p, nn, reach=0.006) or b.toward_nearest(p)
                        line.append(h[0] + LIFT * h[1])
            last = run[-1]
            line.append(pts[ch + str(last)][0] + LIFT * pts[ch + str(last)][1])
            clean = [line[0]]
            for p in line[1:]:
                if np.linalg.norm(p - clean[-1]) > 2e-4:
                    clean.append(p)
            polylines.append([[round(float(a), 5) for a in p] for p in clean])
        out[ch] = polylines
    return out


def build():
    """{point_id: [x, y, z, nx, ny, nz]} (the patient's right side)."""
    return build_all()[0]


def build_all():
    b, placed = place_all()
    pts = {pid: [round(float(a), 5) for a in list(v) + list(n)] for pid, (v, n, _) in placed.items()}
    rounded = {pid: (np.array(p[:3]), np.array(p[3:])) for pid, p in pts.items()}
    return pts, paths(b, rounded), {pid: how for pid, (_, _, how) in placed.items()}


def main():
    pts, lines, how = build_all()
    if "--report" in sys.argv:
        for pid in sorted(how, key=sort_key):
            print(pid, how[pid])
    counts = {k: sum(1 for v in how.values() if v == k) for k in ("text", "manual", "schematic")}
    OUT.write_text("// Generated by tools/treatment/build_points3d.py. Do not edit by hand.\n"
                   "// Point positions on app/interview/body.glb (patient's right side) from the AcuAtlas location text\n"
                   "// on a cun grid measured on the model; approximate. Channel lines follow the skin.\n"
                   "window.TCM_POINTS3D = " + json.dumps(pts, separators=(",", ":")) + ";\n"
                   "window.TCM_PATHS3D = " + json.dumps(lines, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"{len(pts)} points ({counts['text']} from the text, {counts['manual']} read by hand, "
          f"{counts['schematic']} schematic) -> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    sys.exit(main())
