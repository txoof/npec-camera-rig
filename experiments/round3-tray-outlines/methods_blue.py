"""Method B (blue): a colour threshold on the blue plastic, no AI. Issue #328.

1. Loose blue mask on the quarter image, HSV (OpenCV ranges): hue 95..130, saturation >= 90,
   value >= 50. Sampled on prod, dev and hard stills: tray plastic hue 103..119 (1st..99th
   percentile), saturation 5th percentile 106..134. Table and white paper: saturation < 50; soil,
   paper shadows and the yellow card hue 0..30; plants and green squares hue 35..80.
2. Top-rim mask: of those, the pixels brighter than V_REL = 0.65 x the 75th percentile of the
   loose mask's value (per still, so it follows exposure: 120 to 125 on these stills). The top rim
   faces the lights (value 140..200); shaded side walls, the lower stacked trays and crate rims
   next to a dev tray are darker (value 60..110) and separated from the rim by a dark line. A
   sweep gave the same score from 0.60 to 0.70 and lost trays at 0.80. Opening 3 x 3.
3. Pieces (8-connected), holes filled, convex hull (restores rims under paper, squares, pots).
   Pieces under 0.3% of a tray's area are noise. Two pieces merge when not both are a whole tray
   (hull > 85% of a tray) and their joint hull still fits one tray with 12% slack (a leaf or a
   sheet across a rim splits it; dev S1 with its crate needs 9%).
4. A hull under 40% of a tray's area, or narrower than 60% of the tray's short side, is not a tray
   (blue bits of the ceiling, lower trays' strips).
5. Each hull: minimum-area rectangle; trays along each axis = round(extent / tray size) for the
   orientation that fits best; cut into cells of the known size 305 x 366 mm (scale from
   px_per_mm at the image centre). Along each axis the cells are centred on the hull, or aligned
   to its low or high end. Untagged: centred, or aligned away from a frame border the hull touches.
6. Largest hulls first; a cell lying more than 25% on an accepted cell is dropped (fragments of
   two touching trays merged into a false tray).
7. Tags: a tag takes the nearest cell within 30 mm (any alignment); of that cell's alignments the
   one nearest the tag's placement is used (the tag says which end of an occluded hull is
   real). No cell within 30 mm: the tag placement, warning "outline does not match tag".
   `find_photo_only` is the same without tags, to measure the photo alone.
"""

from __future__ import annotations

import cv2
import numpy as np

from harness import Q, TRAY_MM, Still

H_RANGE = (95, 130)
S_MIN = 90
V_LOOSE = 50  # loose mask: every blue pixel, shaded walls included
V_REL = 0.65  # top rim = blue pixels brighter than 0.65 x the 75th percentile of blue value
MIN_FRAC = 0.4  # a component under 0.4 of one tray's area is not a tray (strips, blue bits)
MATCH_MM = 30.0
OVERLAP_MAX = 0.25  # a cell overlapping an accepted one by more than a quarter is dropped
MIN_PIECE = 0.003  # pieces under 0.3% of a tray are noise (a broken thin rim piece is about 1%)
MERGE_TOL = 1.12  # two pieces merge when together they fit in one tray, 12% slack for side walls and crates (dev S1: 1.09)


def blue_mask(q):
    hsv = cv2.cvtColor(q, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    loose = (h >= H_RANGE[0]) & (h <= H_RANGE[1]) & (s >= S_MIN) & (v >= V_LOOSE)
    v_min = V_REL * np.percentile(v[loose], 75) if loose.any() else 130
    m = (loose & (v >= v_min)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return m


def fill_holes(m):
    h, w = m.shape
    ff = np.pad(m, 1).copy()
    mask = np.zeros((h + 4, w + 4), np.uint8)
    cv2.floodFill(ff, mask, (0, 0), 1)
    holes = ff[1:-1, 1:-1] == 0
    return (m | holes).astype(np.uint8)


def cells_from_hull(hull, ppm_q, shape):
    """Cut a hull into tray cells of the known size. Each cell comes with alternatives: along each
    axis the group of cells is centred on the hull, or aligned to its low or its high end. The
    default is centred, or aligned away from a frame border the hull touches."""
    rect = cv2.minAreaRect(hull.astype(np.float32))
    (cx, cy), (w, h), ang = rect
    ta, tb = TRAY_MM[0] * ppm_q, TRAY_MM[1] * ppm_q
    best = None
    for tu, tv in ((ta, tb), (tb, ta)):
        nu, nv = max(1, round(w / tu)), max(1, round(h / tv))
        err = abs(w - nu * tu) / tu + abs(h - nv * tv) / tv
        if best is None or err < best[0]:
            best = (err, nu, nv, tu, tv)
    err, nu, nv, tu, tv = best
    th = np.deg2rad(ang)
    u = np.array([np.cos(th), np.sin(th)])
    v = np.array([-np.sin(th), np.cos(th)])
    H, W = shape
    pu, pv = hull @ u, hull @ v
    border = (hull[:, 0] <= 2) | (hull[:, 1] <= 2) | (hull[:, 0] >= W - 3) | (hull[:, 1] >= H - 3)

    def offsets(p, n, t):
        lo, hi = p.min(), p.max()
        opts = {"centred": (lo + hi) / 2, "low": lo + n * t / 2, "high": hi - n * t / 2}
        lo_b = bool(np.any(border & (p <= lo + 4)))
        hi_b = bool(np.any(border & (p >= hi - 4)))
        default = "high" if lo_b and not hi_b else "low" if hi_b and not lo_b else "centred"
        return opts, default

    ou, du = offsets(pu, nu, tu)
    ov, dv = offsets(pv, nv, tv)
    out = []
    for i in range(nu):
        for j in range(nv):
            alts = {}
            for ku, cu in ou.items():
                for kv, cv_ in ov.items():
                    c = u * (cu + (i - (nu - 1) / 2) * tu) + v * (cv_ + (j - (nv - 1) / 2) * tv)
                    pts = [c + su * u * tu / 2 + sv * v * tv / 2 for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
                    alts[(ku, kv)] = np.array(pts) * Q
            out.append({"outline": alts[(du, dv)], "alts": alts, "edge": bool(border.any()), "err": err, "n": nu * nv})
    return out


def _fits(rect, ta, tb, tol):
    w, h = sorted(rect[1])
    return w <= min(ta, tb) * tol and h <= max(ta, tb) * tol


def outlines(still: Still):
    q = still.quarter
    m = blue_mask(q)
    n, lab, stats, cents = cv2.connectedComponentsWithStats(m, 8)
    H, W = m.shape
    ppm_q = still.px_per_mm(W * Q / 2, H * Q / 2) / Q  # scale only for sizes of pieces
    A = TRAY_MM[0] * TRAY_MM[1] * ppm_q ** 2
    ta, tb = TRAY_MM[0] * ppm_q, TRAY_MM[1] * ppm_q
    pieces = []
    for k in range(1, n):
        x, y, w, h, area = stats[k]
        if area < MIN_PIECE * A:
            continue
        comp = fill_holes((lab[y:y + h, x:x + w] == k).astype(np.uint8))
        cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        c = max(cnts, key=cv2.contourArea) + np.array([x, y])
        pieces.append(cv2.convexHull(c).reshape(-1, 2))
    # merge fragments of one tray (a leaf or a sheet across its rim splits the mask)
    merged = True
    while merged:
        merged = False
        for i in range(len(pieces)):
            for j in range(i + 1, len(pieces)):
                a, b = pieces[i], pieces[j]
                u = cv2.convexHull(np.vstack([a, b])).reshape(-1, 2)
                ra, rb = cv2.minAreaRect(a), cv2.minAreaRect(b)
                whole_a = cv2.contourArea(a) > 0.85 * A
                whole_b = cv2.contourArea(b) > 0.85 * A
                if whole_a and whole_b:
                    continue
                if _fits(cv2.minAreaRect(u), ta, tb, MERGE_TOL):
                    pieces[i] = u
                    del pieces[j]
                    merged = True
                    break
            if merged:
                break
    res = []
    pieces.sort(key=lambda h: -cv2.contourArea(h.astype(np.float32)))
    for hull in pieces:
        if cv2.contourArea(hull) < MIN_FRAC * A:
            continue
        rect = cv2.minAreaRect(hull)
        if min(rect[1]) < 0.6 * ta:
            continue
        for cell in cells_from_hull(hull.astype(float), ppm_q, (H, W)):
            # a cell lying mostly on a cell from a bigger piece is made of fragments of
            # touching trays (inner walls, broken rims), not a tray of its own
            a = np.float32(cell["outline"] / Q)
            if any(cv2.intersectConvexConvex(a, np.float32(r["outline"] / Q))[0] > OVERLAP_MAX * cv2.contourArea(a)
                   for r in res):
                continue
            res.append(cell)
    return res


def _centre(poly):
    return np.mean(np.asarray(poly, float), 0)


def find(still: Still) -> list[dict]:
    outs = outlines(still)
    used = set()
    found = []
    for p in still.tag_placements:
        pc = np.asarray(p.centre, float)
        ppm = still.px_per_mm(*pc)
        best = None
        for j, o in enumerate(outs):
            if j in used:
                continue
            d = min(np.hypot(*(_centre(a) - pc)) for a in o["alts"].values()) / ppm
            if d <= MATCH_MM and (best is None or d < best[0]):
                best = (d, j)
        if best:
            used.add(best[1])
            o = outs[best[1]]
            # among the photo's alignments (centred, or to either end), the one nearest the tag
            k = min(o["alts"], key=lambda k: np.hypot(*(_centre(o["alts"][k]) - pc)))
            found.append({"outline": o["alts"][k].tolist(), "tray_id": p.tray_id,
                          "how": f"blue mask, tag ({k[0]}/{k[1]})" + (f", cut from {o['n']}" if o["n"] > 1 else ""), "warnings": []})
        else:
            found.append({"outline": np.asarray(p.outline).tolist(), "tray_id": p.tray_id,
                          "how": "tag placement", "warnings": ["outline does not match tag"]})
    for j, o in enumerate(outs):
        if j in used:
            continue
        w = ["no tag"] + (["partly outside the photo"] if o["edge"] else [])
        found.append({"outline": o["outline"].tolist(), "tray_id": None, "how": "blue mask", "warnings": w})
    return found


def find_photo_only(still: Still) -> list[dict]:
    """Diagnostic: the photo's outlines with no tag help (every tray treated as untagged)."""
    return [{"outline": o["outline"].tolist(), "tray_id": None, "how": "blue mask",
             "warnings": ["no tag"] + (["partly outside the photo"] if o["edge"] else [])} for o in outlines(still)]
