"""Method A (#328): tray outlines from FastSAM objects (Hailo-10H, three tile scales).

Steps
1. Every FastSAM object at every scale ("whole", "large", "medium") is measured on the quarter
   image: its minimum-area rectangle, how well the contour fills it, its size in trays (area over
   the known 305 x 366 mm at the local scale) and how blue its rim is (blue fraction of a band
   just inside the contour: a tray's rim is blue even when its cells hold soil, pots or paper).
2. Tray-like objects: size 0.75 to 1.35 trays, fill >= FILL_MIN, rim blue >= RIM_BLUE_MIN, long
   to short side ratio within ASPECT_TOL of 366/305. Merged objects (touching trays): size about
   n trays (n >= 2), one side about one tray side, the other about n tray sides; cut into n equal
   parts along the long axis.
3. Each candidate rectangle is set to the known tray size. Where the photo rectangle is longer
   than a tray along an axis, the edge nearer the image centre is kept: the side walls show only
   on the side away from the centre (camera about 1.5 m up), so the outer edge of the top rim is
   the near edge.
4. Candidates from all scales are grouped by centre (within GROUP_MM); a group's outline is the
   median of its members' corners, weighted to the best-supported one (votes = scales agreeing).
5. Tags (IDs 0 to 299): a tray outline containing the tag's centre gives the tray its ID when its
   centre lies within CENTRE_MM of one of the tag's two candidate placements (A1 at SW or NE);
   else the candidate placement better covered by tray-like FastSAM area is returned with
   "outline does not match tag". Outlines without a tag get "no tag".

Parameters (general, not per still)
- BLUE: hue 95 to 130 (OpenCV 0 to 180), saturation >= 60, value >= 30: the tray plastic measured
  on one still of each rig at hue 104 to 120 (5th to 95th percentile), saturation >= 72.
- SINGLE = (0.75, 1.35) trays: FastSAM objects of one tray measured 0.99 to 1.10 on a development
  still, the upper end allows side walls (up to about 50 mm at the frame edge).
- FILL_MIN = 0.80: a tray object fills its rectangle at 0.91 to 0.99; plants and sheets less.
- RIM_BLUE_MIN = 0.35, rim band RIM_MM = 15 mm wide: the rim is about 10 to 15 mm of blue.
- ASPECT_TOL = 0.18 on log ratio.
- GROUP_MM = 60: half the smallest gap between tray centres is about 150 mm.
- CENTRE_MM = 30: decision 2 of #328.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from harness import Q, TRAY_MM, Still

BLUE_LO, BLUE_HI, SAT_MIN, VAL_MIN = 95, 130, 60, 30
SINGLE = (0.75, 1.35)
FILL_MIN = 0.80
RIM_BLUE_MIN = 0.35
RIM_MM = 15.0
ASPECT_TOL = 0.18
GROUP_MM = 60.0
CENTRE_MM = 30.0
BRIGHT_FRAC = 0.7
REFINE_MM = 70.0
EDGE_MIN = 0.15
SEAM_MM = 4.0
OVERLAP_MAX = 0.2
COVER_MIN = 0.6
SCALES = ("whole", "large", "medium")
A1_TAG_TO_CENTRE_MM = (-104.0, -141.6)  # same as tray_placement (the rig's own placement)


def _blue(q):
    hsv = cv2.cvtColor(q, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    return ((h >= BLUE_LO) & (h <= BLUE_HI) & (s >= SAT_MIN) & (v >= VAL_MIN)).astype(np.uint8)


def _rect_corners(cx, cy, u, lu, lv):
    """Four corners of a rectangle centred (cx, cy), axis u (unit) of length lu, the other lv."""
    v = np.array([-u[1], u[0]])
    c = np.array([cx, cy])
    return np.array([c - u * lu / 2 - v * lv / 2, c + u * lu / 2 - v * lv / 2,
                     c + u * lu / 2 + v * lv / 2, c - u * lu / 2 + v * lv / 2])


def _fit_size(c, u, mu, mv, eu, ev, img_c):
    """Rectangle centre c, axis u, measured lengths (mu, mv), set to expected (eu, ev): where
    measured is longer, keep the edge nearer the image centre."""
    v = np.array([-u[1], u[0]])
    c = np.array(c, float)
    for ax, m, e in ((u, mu, eu), (v, mv, ev)):
        if m > e:
            side = np.sign(np.dot(np.array(img_c) - c, ax)) or 1.0
            c = c + ax * side * (m - e) / 2
    return _rect_corners(c[0], c[1], u, eu, ev), c


def _candidates(still, blue, ppm_c, img_c):
    out = []
    H, W = blue.shape
    union = np.zeros((H, W), np.uint8)
    for scale in SCALES:
        for o in still.fastsam(scale):
            cont = np.float32(o["contour"])
            if len(cont) < 3:
                continue
            (cx, cy), (rw, rh), ang = cv2.minAreaRect(cont)
            ppm = ppm_c(cx, cy)
            tl, ts = TRAY_MM[1] * ppm, TRAY_MM[0] * ppm
            n = o["area_px"] / (tl * ts)
            if n < SINGLE[0] or n > 14:
                continue
            fill = cv2.contourArea(cont) / max(1.0, rw * rh)
            if fill < FILL_MIN:
                continue
            m = np.zeros((H, W), np.uint8)
            cq = np.int32(cont / Q)
            cv2.fillPoly(m, [cq], 1)
            band = max(2, int(RIM_MM * ppm / Q))
            inner = cv2.erode(m, np.ones((2 * band + 1, 2 * band + 1), np.uint8))
            ring = (m > 0) & (inner == 0)
            if not ring.any():
                continue
            rim = float(blue[ring].mean())
            if rim < RIM_BLUE_MIN:
                continue
            union |= m
            a = math.radians(ang)
            u = np.array([math.cos(a), math.sin(a)])
            if rw < rh:  # u along the long side
                u, rw, rh = np.array([-u[1], u[0]]), rh, rw
            if u[0] < 0 or (u[0] == 0 and u[1] < 0):
                u = -u
            # Which tray side lies along the row? Compare the cross length with both sides.
            cross_long = abs(math.log(rh / tl)) < abs(math.log(rh / ts))
            along = ts if cross_long else tl
            cross = tl if cross_long else ts
            k = max(1, int(round(rw / along)))
            if k == 1:
                if not (SINGLE[0] <= n <= SINGLE[1]) or abs(math.log((rw / rh) / (tl / ts))) > ASPECT_TOL:
                    continue
                # the long side is the tray's long side
                corners, c = _fit_size((cx, cy), u, rw, rh, tl, ts, img_c)
                out.append({"corners": corners, "centre": c, "scale": scale, "score": o["score"],
                            "rim": rim, "merged": 1, "ppm": ppm})
                continue
            if abs(math.log(rh / cross)) > ASPECT_TOL or abs(math.log(rw / (k * along))) > ASPECT_TOL or abs(n / k - 1) > 0.3:
                continue
            step = rw / k
            for i in range(k):
                pc = np.array([cx, cy]) + u * (-rw / 2 + step * (i + 0.5))
                corners, c = _fit_size(pc, u, step, rh, along, cross, img_c)
                out.append({"corners": corners, "centre": c, "scale": scale, "score": o["score"],
                            "rim": rim, "merged": k, "ppm": ppm})
    return out, union


def _order(corners):
    """Corners ordered by angle round their centre, starting nearest the top-left."""
    c = corners.mean(0)
    ang = np.arctan2(corners[:, 1] - c[1], corners[:, 0] - c[0])
    oc = corners[np.argsort(ang)]
    k = int(np.argmin(oc[:, 0] + oc[:, 1]))
    return np.roll(oc, -k, axis=0)


def _group(cands):
    cands = sorted(cands, key=lambda c: -(c["score"] * c["rim"]))
    groups = []
    for c in cands:
        for g in groups:
            if np.hypot(*(g[0]["centre"] - c["centre"])) / c["ppm"] < GROUP_MM:
                g.append(c)
                break
        else:
            groups.append([c])
    trays = []
    for g in groups:
        scales = {c["scale"] for c in g}
        pts = np.median(np.stack([_order(c["corners"]) for c in g]), axis=0)
        trays.append({"corners": pts, "centre": pts.mean(0), "votes": len(scales), "members": g,
                      "ppm": g[0]["ppm"], "how": "fastsam " + "+".join(sorted(scales))})
    return trays


def _bright_blue(q, blue):
    """Blue pixels lit like a top surface: value above BRIGHT_FRAC of the still's median blue
    value. Side walls and lower trays are the same hue but darker (development S1: rim value
    about 180, wall 65 to 120)."""
    v = cv2.cvtColor(q, cv2.COLOR_BGR2HSV)[..., 2]
    med = float(np.median(v[blue > 0])) if blue.any() else 128.0
    return (blue > 0) & (v >= BRIGHT_FRAC * med)


def _refine(corners, bb, ppm):
    """Move each pair of opposite edges (tray size kept) to where the bright-blue profile steps
    from inside to outside most strongly, within REFINE_MM of where they are."""
    c = corners.mean(0) / Q
    o = _order(corners) / Q
    ex = o[1] - o[0]
    lx = float(np.hypot(*ex)); ux = ex / lx
    ly = float(np.hypot(*(o[3] - o[0])))
    uy = np.array([-ux[1], ux[0]])
    if np.dot(uy, o[3] - o[0]) < 0:
        uy = -uy
    pq = ppm / Q
    search, r = int(REFINE_MM * pq), max(2, int(RIM_MM * pq))
    g = max(2, int(round(SEAM_MM * pq)))
    shift = np.zeros(2)
    for k, (u, lu, v, lv) in enumerate(((ux, lx, uy, ly), (uy, ly, ux, lx))):
        half = lu / 2 + search + r + 2
        ts = np.arange(-half, half + 1)
        ss = np.linspace(-0.3 * lv, 0.3 * lv, 25)
        X = c[0] + ts[:, None] * u[0] + ss[None, :] * v[0]
        Y = c[1] + ts[:, None] * u[1] + ss[None, :] * v[1]
        ok = (X >= 0) & (Y >= 0) & (X < bb.shape[1] - 1) & (Y < bb.shape[0] - 1)
        vals = np.where(ok, bb[np.clip(Y.astype(int), 0, bb.shape[0] - 1), np.clip(X.astype(int), 0, bb.shape[1] - 1)], np.nan)
        cnt = ok.sum(1)
        prof = np.where(cnt > 0, np.nansum(vals, axis=1) / np.maximum(cnt, 1), 0.0)
        cs = np.concatenate([[0], np.cumsum(prof)])
        mean = lambda a, b: (cs[b] - cs[a]) / max(1, b - a)  # noqa: E731
        i0 = int(round(half - lu / 2))
        L = int(round(lu))
        best, bd = None, 0
        for d in range(-search, search + 1):
            a = i0 + d
            if a - r < 0 or a + L + r >= len(prof):
                continue
            # inside the rim bright, a narrow band just outside dark: holds for a free edge
            # (table), a side wall or lower tray (darker blue), and a seam between touching trays
            e = mean(a, a + r) - mean(a - g, a) + mean(a + L - r, a + L) - mean(a + L, a + L + g)
            e -= abs(d) / max(1, search) * 0.05
            if best is None or e > best:
                best, bd = e, d
        if best is not None and best >= EDGE_MIN:
            shift = shift + u * bd
    return corners + shift * Q


def _tag_candidates(still, tag):
    c = tag["corners"]
    up_x = (c[0][0] + c[1][0] - c[2][0] - c[3][0]) / 2
    up_y = (c[0][1] + c[1][1] - c[2][1] - c[3][1]) / 2
    tilt = (math.degrees(math.atan2(up_x, -up_y)) + 45) % 90 - 45
    ppm = still.px_per_mm(*tag["centre"])
    t = math.radians(180 + tilt)
    right, up = (math.cos(t), math.sin(t)), (math.sin(t), -math.cos(t))
    dx = (A1_TAG_TO_CENTRE_MM[0] * right[0] + A1_TAG_TO_CENTRE_MM[1] * up[0]) * ppm
    dy = (A1_TAG_TO_CENTRE_MM[0] * right[1] + A1_TAG_TO_CENTRE_MM[1] * up[1]) * ppm
    tr = math.radians(tilt)
    u = np.array([math.cos(tr), math.sin(tr)])
    out = []
    for sign in (1, -1):
        cc = (tag["centre"][0] + sign * dx, tag["centre"][1] + sign * dy)
        out.append(_rect_corners(cc[0], cc[1], u, TRAY_MM[0] * ppm, TRAY_MM[1] * ppm))
    return out, ppm


def _overlap(a, b):
    """Area of a inside b, as a fraction of a's area."""
    inter, _ = cv2.intersectConvexConvex(np.float32(a), np.float32(b))
    return inter / max(1.0, cv2.contourArea(np.float32(a)))


def _inside(poly, p):
    return cv2.pointPolygonTest(np.float32(poly), (float(p[0]), float(p[1])), False) >= 0


def find_photo(still: Still) -> list[dict]:
    """The photo alone: tags ignored, every outline from FastSAM (for comparison)."""
    return find(still, use_tags=False)


def find(still: Still, use_tags: bool = True) -> list[dict]:
    try:
        still.fastsam("whole")
    except FileNotFoundError:
        return []
    q = still.quarter
    blue = _blue(q)
    W, H = still.size
    img_c = (W / 2, H / 2)
    cands, union = _candidates(still, blue, still.px_per_mm, img_c)
    trays = _group(cands)
    # weak groups: a single scale and a single merged-cut member only when nothing better overlaps
    # singles before cuts of merged objects, then by scales agreeing, then by FastSAM support
    trays.sort(key=lambda t: (-t["votes"], min(m["merged"] for m in t["members"]),
                              -max(m["score"] * m["rim"] for m in t["members"])))
    kept = []
    for t in trays:
        if any(_overlap(t["corners"], k["corners"]) > OVERLAP_MAX for k in kept):
            continue
        kept.append(t)
    trays = kept
    bb = _bright_blue(q, blue).astype(np.float32)
    for t in trays:
        t["corners"] = _refine(t["corners"], bb, t["ppm"])
        t["centre"] = t["corners"].mean(0)


    out, used = [], set()
    for tag in sorted((t for t in still.tags if t["id"] < 300 and use_tags), key=lambda t: t["id"]):
        cand, ppm = _tag_candidates(still, tag)
        best = None
        for i, t in enumerate(trays):
            if i in used or not _inside(t["corners"], tag["centre"]):
                continue
            d = min(np.hypot(*(t["centre"] - cc.mean(0))) / ppm for cc in cand)
            if best is None or d < best[0]:
                best = (d, i)
        if best is not None and best[0] <= CENTRE_MM:
            used.add(best[1])
            t = trays[best[1]]
            out.append({"outline": t["corners"].tolist(), "tray_id": tag["id"], "how": t["how"], "warnings": []})
            continue
        if best is not None:
            used.add(best[1])
        # No single-tray outline: cut the tray from the tray-like FastSAM area, starting from the
        # tag. The candidate placement better covered by that area is taken, then its edges are
        # moved to the rim edges of the photo.
        cover = []
        for cc in cand:
            m = np.zeros(blue.shape, np.uint8)
            cv2.fillPoly(m, [np.int32(cc / Q)], 1)
            cover.append(float(union[m > 0].mean()) if m.any() else 0.0)
        cc = cand[int(np.argmax(cover))]
        if max(cover) >= COVER_MIN:
            rc = _refine(cc, bb, ppm)
            if np.hypot(*(rc.mean(0) - cc.mean(0))) / ppm <= CENTRE_MM:
                out.append({"outline": rc.tolist(), "tray_id": tag["id"], "how": "fastsam area cut from tag",
                            "warnings": []})
                continue
        out.append({"outline": cc.tolist(), "tray_id": tag["id"], "how": "tag placement",
                    "warnings": ["outline does not match tag"]})
    for i, t in enumerate(trays):
        if i in used:
            continue
        w = ["no tag"]
        if (t["corners"][:, 0].min() < 0 or t["corners"][:, 1].min() < 0 or t["corners"][:, 0].max() > W
                or t["corners"][:, 1].max() > H):
            w.append("partly outside the photo")
        out.append({"outline": t["corners"].tolist(), "tray_id": None, "how": t["how"], "warnings": w})
    return out
