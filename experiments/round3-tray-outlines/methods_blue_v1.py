"""Method B (blue), v1: a colour threshold on the blue plastic, no AI.

1. Blue mask on the quarter image, HSV (OpenCV ranges): hue 95..130, saturation >= 90,
   value >= V_MIN. Sampled tray plastic on all three sets: hue 103..119 (1st..99th percentile),
   saturation 5th percentile 106..134. Table (grey/white) has saturation < 40, soil and paper hue
   0..20, plants hue 35..80. V_MIN keeps the sunlit top rim (value 130..200) and drops the shaded
   side walls and lower stacked trays (value 60..95, dev crops).
2. Components, holes filled, convex hull (restores rims under paper and squares).
3. Each component: minimum-area rectangle; the number of trays along each axis is
   round(extent / tray size); cut into cells of the known tray size 305 x 366 mm.
4. Tags: a tag placement takes the outline whose centre is within 30 mm, else its own placement.
"""

from __future__ import annotations

import cv2
import numpy as np

from harness import Q, TRAY_MM, Still

H_RANGE = (95, 130)
S_MIN = 90
V_MIN = 100
MIN_FRAC = 0.4  # a component under 0.4 of one tray's area is not a tray (strips, blue bits)
MATCH_MM = 30.0


def blue_mask(q):
    hsv = cv2.cvtColor(q, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    m = ((h >= H_RANGE[0]) & (h <= H_RANGE[1]) & (s >= S_MIN) & (v >= V_MIN)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return m


def fill_holes(m):
    h, w = m.shape
    ff = np.pad(m, 1).copy()
    mask = np.zeros((h + 4, w + 4), np.uint8)
    cv2.floodFill(ff, mask, (0, 0), 1)
    holes = ff[1:-1, 1:-1] == 0
    return (m | holes).astype(np.uint8)


def cells_from_rect(rect, ppm_q):
    """Cut a component's min-area rectangle into tray cells of the known size."""
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
    out = []
    for i in range(nu):
        for j in range(nv):
            c = np.array([cx, cy]) + u * (i - (nu - 1) / 2) * tu + v * (j - (nv - 1) / 2) * tv
            pts = [c + su * u * tu / 2 + sv * v * tv / 2 for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            out.append(np.array(pts))
    return out, err


def outlines(still: Still):
    q = still.quarter
    m = blue_mask(q)
    n, lab, stats, cents = cv2.connectedComponentsWithStats(m, 8)
    res = []
    H, W = m.shape
    for k in range(1, n):
        x, y, w, h, area = stats[k]
        cx, cy = cents[k]
        ppm_q = still.px_per_mm(cx * Q, cy * Q) / Q
        A = TRAY_MM[0] * TRAY_MM[1] * ppm_q ** 2
        if area < MIN_FRAC * A * 0.3:
            continue
        comp = fill_holes((lab[y:y + h, x:x + w] == k).astype(np.uint8))
        cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        c = max(cnts, key=cv2.contourArea) + np.array([x, y])
        hull = cv2.convexHull(c)
        if cv2.contourArea(hull) < MIN_FRAC * A:
            continue
        rect = cv2.minAreaRect(hull)
        if min(rect[1]) < 0.6 * TRAY_MM[0] * ppm_q:
            continue
        edge = x <= 2 or y <= 2 or x + w >= W - 2 or y + h >= H - 2
        cells, err = cells_from_rect(rect, ppm_q)
        for cell in cells:
            res.append({"outline": cell * Q, "edge": edge, "err": err})
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
            d = np.hypot(*(_centre(o["outline"]) - pc)) / ppm
            if d <= MATCH_MM and (best is None or d < best[0]):
                best = (d, j)
        if best:
            used.add(best[1])
            found.append({"outline": outs[best[1]]["outline"].tolist(), "tray_id": p.tray_id,
                          "how": "blue mask, tag", "warnings": []})
        else:
            found.append({"outline": np.asarray(p.outline).tolist(), "tray_id": p.tray_id,
                          "how": "tag placement", "warnings": ["outline does not match tag"]})
    for j, o in enumerate(outs):
        if j in used:
            continue
        w = ["no tag"] + (["partly outside the photo"] if o["edge"] else [])
        found.append({"outline": o["outline"].tolist(), "tray_id": None, "how": "blue mask", "warnings": w})
    return found
