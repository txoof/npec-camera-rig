"""Method D (rims), v1: blue blobs say roughly where trays are; the top rims say exactly where.

1. Blue mask at quarter size: hue 95 to 130 (OpenCV 0 to 180), saturation >= 90, value >= 60,
   the saturated blue of every tray type, not the grey table, white paper or brown soil.
2. Seeds. With tags: each tag's placement (the rig's place_trays) is a seed with its tray_id.
   The blue left over outside the tag seeds is closed, holes filled, split into blobs; a blob of
   at least half a tray's area is tiled by tray-sized rectangles (the orientation and count that
   fit the blob's min-area rectangle best), each a seed with no tray_id.
3. Rims. Each seed is warped to its own axis-aligned frame. The feature is "bright blue" (V on
   blue pixels, 0 elsewhere): the lit top rim is the brightest blue; outside it come a dark seam,
   a shadowed side wall, a lower tray's darker edge or the grey table. Profiles of the feature
   across each pair of opposite sides (mean over the middle 60% of the side) give edge
   candidates (drops of the feature going outward). The pair of opposite candidates whose
   distance is the known tray size (305 or 366 mm, within SIZE_TOL_MM) with the strongest sum
   sets the centre on that axis; that is the least-squares fit of a known-size rectangle to the
   two edges. With no pair, the stronger single edge sets it. Search +-SEARCH_MM around the seed.
4. Tag rule: a refined outline within 30 mm of its tag placement is returned, otherwise the tag
   placement with "outline does not match tag".
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from harness import Q, TRAY_MM, Still

HUE = (95, 130)  # OpenCV hue of the blue trays
SAT_MIN, VAL_MIN = 90, 60
SEARCH_MM = 40.0  # how far a seed's edge may move: blob tiling errors are up to ~1/2 wall height
SIZE_TOL_MM = 12.0  # opposite rims must be the tray size apart within this (4%)
SLACK_MM = 6.0  # comb teeth may miss a seam by this much (scale drift along a row)
import os
LAMBDA = float(os.environ.get("RIMS_LAMBDA", 2.0))  # edge units per mm the centre moves from its seed
AGG = os.environ.get("RIMS_AGG", "mean")
K = 2  # quarter px either side for the edge difference (~2.5 mm)


def _blue(q):
    hsv = cv2.cvtColor(q, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    m = (h >= HUE[0]) & (h <= HUE[1]) & (s >= SAT_MIN) & (v >= VAL_MIN)
    return m.astype(np.uint8), v


def _rect_pts(cx, cy, ang, a, b):
    """Corners (quarter px) of an a (along angle ang) by b rectangle."""
    c, s = math.cos(ang), math.sin(ang)
    u, w = np.array([c, s]), np.array([-s, c])
    return np.array([[cx, cy] + i * a / 2 * u + j * b / 2 * w for i, j in ((-1, -1), (1, -1), (1, 1), (-1, 1))])


def _profile_edges(p, lo_exp, hi_exp, search, size, tol, ppm):
    """Choose the low and high edge on a 1D profile. Returns (centre, n_edges_used, strength)."""
    n = len(p)
    e_lo = np.full(n, -np.inf)
    e_hi = np.full(n, -np.inf)
    for t in range(K, n - K):
        if np.isnan(p[t - K]) or np.isnan(p[t + K]):
            continue
        e_lo[t] = p[t + K] - p[t - K]  # inside (higher t) minus outside
        e_hi[t] = p[t - K] - p[t + K]
    def cands(e, centre):
        lo, hi = int(max(K, centre - search)), int(min(n - K - 1, centre + search))
        out = []
        for t in range(lo, hi + 1):
            if e[t] > 15 and e[t] >= e[t - 1] and e[t] >= e[t + 1]:
                out.append((t, e[t]))
        return out
    cl, ch = cands(e_lo, lo_exp), cands(e_hi, hi_exp)
    best = None
    for tl, sl in cl:
        for th, sh in ch:
            sc = sl + sh - LAMBDA * abs((tl + th) / 2 - (lo_exp + hi_exp) / 2) / ppm
            if abs(th - tl - size) <= tol and (best is None or sc > best[2]):
                best = ((tl + th) / 2, 2, sc)
    if best:
        return best
    mid = (lo_exp + hi_exp) / 2
    singles = [(tl + size / 2, 1, sl - LAMBDA * abs(tl + size / 2 - mid) / ppm) for tl, sl in cl] + \
              [(th - size / 2, 1, sh - LAMBDA * abs(th - size / 2 - mid) / ppm) for th, sh in ch]
    if singles:
        return max(singles, key=lambda x: x[2])
    return ((lo_exp + hi_exp) / 2, 0, 0.0)


def _refine(feat, seed, ppm):
    cx, cy, ang, a, b = seed
    m = int(SEARCH_MM * ppm + 3 * K + 4)
    W, H = int(a + 2 * m), int(b + 2 * m)
    c, s = math.cos(ang), math.sin(ang)
    # output (x, y) -> input: centre + (x - W/2) u + (y - H/2) w
    M = np.array([[c, -s, cx - c * W / 2 + s * H / 2], [s, c, cy - s * W / 2 - c * H / 2]])
    crop = cv2.warpAffine(feat, M, (W, H), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=np.nan)
    search = SEARCH_MM * ppm
    tol = SIZE_TOL_MM * ppm
    rows = crop[int(m + 0.2 * b): int(m + 0.8 * b)]
    cols = crop[:, int(m + 0.2 * a): int(m + 0.8 * a)]
    with np.errstate(all="ignore"):
        agg = np.nanmedian if AGG == "median" else np.nanmean
        px = agg(rows, axis=0)
        py = agg(cols, axis=1)
    ux, nx, sx = _profile_edges(px, m, m + a, search, a, tol, ppm)
    uy, ny, sy = _profile_edges(py, m, m + b, search, b, tol, ppm)
    du, dv = ux - W / 2, uy - H / 2
    ncx = cx + du * c - dv * s
    ncy = cy + du * s + dv * c
    return (ncx, ncy, ang, a, b), nx + ny


def _seed_from_outline(outline):
    o = np.asarray(outline, float) / Q
    d1, d2 = o[1] - o[0], o[3] - o[0]
    ang = math.atan2(d1[1], d1[0])
    c = o.mean(0)
    return (c[0], c[1], ang, float(np.hypot(*d1)), float(np.hypot(*d2)))


def _comb(p, inside, size, ppm):
    """Tray centres along one axis of a blob: the comb of tray-size steps whose teeth best meet
    rim edges or seams (a dark valley between two bright rims). p: bright-blue profile, inside:
    where the blob is."""
    idx = np.flatnonzero(inside)
    if len(idx) == 0:
        return [], 0.0
    lo, hi = idx[0], idx[-1]
    n = len(p)
    r = max(3, int(10 * ppm))
    B = np.zeros(n)
    for t in range(r, n - r):
        seam = min(p[t - r:t].max(), p[t + 1:t + r + 1].max()) - p[t]
        B[t] = max(seam, p[t + K] - p[t - K], p[t - K] - p[t + K], 0)
    slack = max(2, int(SLACK_MM * ppm))
    Bd = np.array([B[max(0, t - slack):t + slack + 1].max() for t in range(n)])
    bg = float(np.median(Bd[lo:hi + 1]))
    best = None
    for t0 in np.arange(lo - size / 2, lo + size / 2, 1.0):
        ks = range(0, int((hi - t0) / size) + 2)
        teeth = [Bd[int(round(t0 + k * size))] for k in ks
                 if lo - 3 <= t0 + k * size <= hi + 3 and 0 <= int(round(t0 + k * size)) < n]
        sc = sum(teeth)
        if best is None or sc > best[0]:
            best = (sc, t0, sc - bg * len(teeth))
    t0 = best[1]
    out = []
    for k in range(-1, int((hi - t0) / size) + 2):
        a0, a1 = t0 + k * size, t0 + (k + 1) * size
        if min(a1, hi) - max(a0, lo) >= 0.5 * size:
            out.append((a0 + a1) / 2)
    return out, best[2]


def _blob_seeds(mask, feat, still, taken):
    rest = mask.copy()
    for sd in taken:
        cv2.fillPoly(rest, [np.int32(_rect_pts(*sd))], 0)
    rest = cv2.morphologyEx(rest, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    cnts, _ = cv2.findContours(rest, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(rest)
    cv2.drawContours(filled, cnts, -1, 1, -1)
    filled = cv2.morphologyEx(filled, cv2.MORPH_OPEN, np.ones((15, 15), np.uint8))
    cnts, _ = cv2.findContours(filled, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    seeds = []
    for cn in cnts:
        (bx, by), (rw, rh), deg = cv2.minAreaRect(cn)
        ppm = still.px_per_mm(bx * Q, by * Q) / Q
        A, B = TRAY_MM[0] * ppm, TRAY_MM[1] * ppm
        if cv2.contourArea(cn) < 0.5 * A * B:
            continue
        ang = math.radians(deg)
        if rw < rh:  # make the rectangle's first side the one nearer the x axis
            pass
        an = math.radians(deg)
        L1, L2 = rw, rh
        u = np.array([math.cos(an), math.sin(an)])
        w = np.array([-math.sin(an), math.cos(an)])
        mg = int(0.6 * max(A, B))
        W, H = int(L1 + 2 * mg), int(L2 + 2 * mg)
        M = np.array([[u[0], w[0], bx - u[0] * W / 2 - w[0] * H / 2], [u[1], w[1], by - u[1] * W / 2 - w[1] * H / 2]])
        fc = cv2.warpAffine(feat, M, (W, H), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderValue=0)
        one = np.zeros_like(filled)
        cv2.drawContours(one, [cn], -1, 1, -1)
        mc = cv2.warpAffine(one, M, (W, H), flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP, borderValue=0)
        r1, r2 = slice(int(mg + 0.1 * L2), int(mg + 0.9 * L2)), slice(int(mg + 0.1 * L1), int(mg + 0.9 * L1))
        p1, i1 = fc[r1].mean(0), mc[r1].max(0)
        p2, i2 = fc[:, r2].mean(1), mc[:, r2].max(1)
        best = None
        for a, b in ((A, B), (B, A)):  # which way round the trays lie: the better comb fit
            (t1, s1), (t2, s2) = _comb(p1, i1, a, ppm), _comb(p2, i2, b, ppm)
            if t1 and t2 and (best is None or s1 + s2 > best[0]):
                best = (s1 + s2, a, b, t1, t2)
        if best is None:
            continue
        _, a, b, t1, t2 = best
        for c1 in t1:
            for c2 in t2:
                off = (c1 - W / 2) * u + (c2 - H / 2) * w
                seeds.append((bx + off[0], by + off[1], an, a, b))
    return seeds


def find(still: Still) -> list[dict]:
    q = still.quarter
    mask, v = _blue(q)
    feat = (v.astype(np.float32) * mask).astype(np.float32)
    feat = cv2.GaussianBlur(feat, (3, 3), 0)
    h, w = mask.shape
    out = []
    tag_seeds = []
    for p in still.tag_placements:
        sd = _seed_from_outline(p.outline)
        tag_seeds.append(sd)
        ppm = still.px_per_mm(sd[0] * Q, sd[1] * Q) / Q
        r, n = _refine(feat, sd, ppm)
        d_mm = math.hypot(r[0] - sd[0], r[1] - sd[1]) / ppm
        if d_mm <= 30:
            out.append({"outline": (_rect_pts(*r) * Q).tolist(), "tray_id": p.tray_id,
                        "how": f"tag seed, rims ({n} edges)", "warnings": []})
        else:
            out.append({"outline": [list(x) for x in p.outline], "tray_id": p.tray_id,
                        "how": "tag only", "warnings": ["outline does not match tag"]})
    for sd in _blob_seeds(mask, feat, still, tag_seeds):
        ppm = still.px_per_mm(sd[0] * Q, sd[1] * Q) / Q
        r, n = _refine(feat, sd, ppm)
        pts = _rect_pts(*r)
        warn = ["no tag"]
        if (pts[:, 0] < 0).any() or (pts[:, 1] < 0).any() or (pts[:, 0] >= w).any() or (pts[:, 1] >= h).any():
            warn.append("partly outside the photo")
        out.append({"outline": (pts * Q).tolist(), "tray_id": None, "how": f"blob seed, rims ({n} edges)",
                    "warnings": warn})
    return out


class _Blind:
    """A still with its tags hidden: tests the photo-only path on the tagged rigs."""

    def __init__(self, still):
        self._s = still
        self.tag_placements = []

    def __getattr__(self, k):
        return getattr(self._s, k)


def find_blind(still: Still) -> list[dict]:
    """Diagnostic: the finder with no tags (every tray from blobs and rims, tray_id None)."""
    return find(_Blind(still))
