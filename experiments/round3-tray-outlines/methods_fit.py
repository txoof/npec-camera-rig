"""Method E: fit tray-sized rectangles to the whole evidence map (a global fit, not blob by blob).

Evidence: a blue mask at 1/8 size (HSV hue 95..130, saturation >= 90, value >= 50 of 255: the
tray plastic measured 103..118 hue, saturation 94..250, value 52..223 on one still of each rig;
soil, pots, paper, table and plants fall outside it).

Score of a rectangle of the known tray shape (305 x 366 mm at the scale where it sits, portrait or
landscape, turned by a few degrees): for each side, the blue fraction of a strip just inside the
side (the top rim, RIM_MM deep) minus the blue fraction of a thin strip just outside it (the gap,
seam or table, GAP_MM wide); the score is the mean of the sides that lie in the frame. A rim that
is covered on one side (paper, cards) or a seam that does not show still leaves three sides.

Size: the scale field holds at tray-top height on the table. A tray standing on a lower tray or in
a crate is nearer the camera and looks larger, so the size may grow by up to SIZES[-1] (a tray
60 mm higher looks about 4% larger at 1.5 m); never smaller than SIZES[0].

Search: a coarse pass (COARSE angles and sizes, both orientations, every STRIDE px) gives local
peaks; each of the best peaks is refined over every angle of ANGLES, every size of SIZES and
+-REFINE px. Tagged trays first, each searched only near its tag's two candidate centres (A1 at
the south-west or north-east) within TAG_WINDOW_MM; the best non-overlapping (tag, candidate)
wins. Then every other refined peak, best first, accepted when it overlaps no accepted rectangle by
more than OVERLAP_MAX of a tray, until the score falls below SCORE_MIN. The number of trays comes
from that stopping rule, never from a count.
"""

from __future__ import annotations

import cv2
import numpy as np

from harness import TRAY_MM, Still

F = 8  # evidence at 1/8 of full size
ANGLES = (-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0)  # deg; trays lie square to the table within a few degrees
COARSE_ANGLES = (-2.0, 0.0, 2.0)
SIZES = (0.98, 1.0, 1.02, 1.04, 1.06, 1.08, 1.10)
COARSE_SIZES = (1.0, 1.06)
RIM_MM = 9.0  # depth of the inner strip: about the width of the top rim seen from above
GAP_MM = 5.0  # width of the outer strip
CORNER_MM = 25.0  # strips stop this far short of the corners (round corners, bumps)
STRIDE = 3  # px at 1/8 between coarse candidate centres (5 mm)
REFINE = 4  # px at 1/8 searched around a coarse peak
REFINE_STEPS = 3  # refinement repeated around the best so far, while it improves
N_REFINE = 80  # coarse peaks refined per orientation, best first
SCORE_MIN = 0.35  # decision: below this a rectangle explains too little to be a tray
OVERLAP_MAX = 0.06  # of a tray area: touching trays with a few mm of error each
INTERIOR_MARGIN_MM = 30.0  # interior seam lines are looked for this far inside the sides
INTERIOR_FREE = 0.55  # a two-tray boundary inside reads 0.63-0.88 (wrong rectangles, hard still
#                       121231); correct rectangles read 0.23-0.52, 0.59 on one partly outside
INTERIOR_W = 2.0  # score lost per unit of interior seam above INTERIOR_FREE
TAG_WINDOW_MM = 30.0  # the harness's own match radius for a tag
INSIDE_MIN = 0.6  # an untagged rectangle needs this much of itself in the frame
BRIGHT = True  # evidence is the bright (lit top) blue only
BRIGHT_K = 81  # px at 1/8 (about 130 mm): neighbourhood for the local rim brightness
BRIGHT_FRAC = 0.6  # rim V about 190, shaded walls and lower trays about 80 (ratio 0.42)
KNOWN_FULL = 0.6  # a side whose strips are this much seen (not leaves) counts in full
FRAME_KNOWN = 0.5  # beyond the frame counts as not-blue with half weight: a tray side on the
#                    frame edge has some support, a tray running out of the frame is not ruled out
IGNORE_GREEN = True  # plants (and green cards) count as unknown, not as not-blue
GREEN_H = (30, 90)  # OpenCV hue of leaves; the blue plastic is 103..118
SEAM_W = 0.3  # weight of the seam term in each side's contrast
SEAM_K = 15  # black-hat kernel at 1/4 (12 mm): wider than the gap between a top rim and what lies under it
SEAM_MM = 2.0  # half width of the strip on the border line where a seam is looked for
SEAM_T = 20  # black-hat (9 px at 1/4) of V at or above this is a thin dark line: the shadow line or
#              gap round a top rim, a seam between touching trays (median 6, 90th percentile 34-42)


def _blue(q):
    small = cv2.resize(q, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    blue = (h >= 95) & (h <= 130) & (s >= 90) & (v >= 50)
    if not BRIGHT:
        return blue.astype(np.float32)
    # top rim: the brightest blue nearby. Side walls and lower trays are in shade (V about 80
    # against 190 on the rim, development still 083005), so they count as not-rim.
    vb = np.where(blue, v, 0).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (BRIGHT_K, BRIGHT_K))
    ref = cv2.GaussianBlur(cv2.dilate(vb, k).astype(np.float32), (0, 0), BRIGHT_K / 2)
    return (blue & (v >= BRIGHT_FRAC * ref)).astype(np.float32)


def _known(q):
    """1 where the colour says something about tray or not tray; 0 on plants (green), which may
    lie over a rim or over the table alike."""
    small = cv2.resize(q, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    green = (h >= GREEN_H[0]) & (h <= GREEN_H[1]) & (s >= 60) & (v >= 40)
    if not IGNORE_GREEN:
        green[:] = False
    return (~green).astype(np.float32)


def _seam(q):
    v = cv2.cvtColor(q, cv2.COLOR_BGR2HSV)[..., 2]
    bh = cv2.morphologyEx(v, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (SEAM_K, SEAM_K)))
    bh = cv2.dilate(bh, np.ones((2, 2), np.uint8))[::2, ::2]
    return (bh >= SEAM_T).astype(np.float32)


def _ppm_grid(still, shape):
    """Full px per mm at every 1/8 px, interpolated from a coarse grid."""
    h, w = shape
    xs, ys = np.linspace(0, w * F, 12), np.linspace(0, h * F, 10)
    g = np.float32([[still.px_per_mm(x, y) for x in xs] for y in ys])
    return cv2.resize(g, (w, h), interpolation=cv2.INTER_LINEAR)


class _Map:
    """Evidence turned by one angle, with integral images of blue and of valid (in-frame) px."""

    def __init__(self, blue, seam, known, angle):
        h, w = blue.shape
        self.A = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        self.Ainv = cv2.invertAffineTransform(self.A)
        b = cv2.warpAffine(blue, self.A, (w, h), flags=cv2.INTER_LINEAR, borderValue=0)
        v = cv2.warpAffine(known, self.A, (w, h), flags=cv2.INTER_LINEAR, borderValue=FRAME_KNOWN)
        self.pad = 400
        self.Ib = cv2.integral(np.pad(b, self.pad))
        self.Iv = cv2.integral(np.pad(v, self.pad, constant_values=FRAME_KNOWN))
        fr = cv2.warpAffine(np.ones_like(blue), self.A, (w, h), flags=cv2.INTER_LINEAR, borderValue=0)
        self.If = cv2.integral(np.pad(fr, self.pad))
        e = cv2.warpAffine(seam, self.A, (w, h), flags=cv2.INTER_LINEAR, borderValue=0)
        self.Ie = cv2.integral(np.pad(e, self.pad))

    def _box(self, I, x0, y0, x1, y1):
        p = self.pad
        hh, ww = I.shape
        x0 = np.clip(np.rint(x0 + p).astype(int), 0, ww - 1)
        x1 = np.clip(np.rint(x1 + p).astype(int), 0, ww - 1)
        y0 = np.clip(np.rint(y0 + p).astype(int), 0, hh - 1)
        y1 = np.clip(np.rint(y1 + p).astype(int), 0, hh - 1)
        x1 = np.maximum(x1, x0)
        y1 = np.maximum(y1, y0)
        return I[y1, x1] - I[y0, x1] - I[y1, x0] + I[y0, x0]

    def frac(self, x0, y0, x1, y1, I=None):
        b, v = self._box(self.Ib if I is None else I, x0, y0, x1, y1), self._box(self.Iv, x0, y0, x1, y1)
        area = np.maximum((x1 - x0) * (y1 - y0), 1)
        ok = v >= 0.5 * area
        return np.where(ok, b / np.maximum(v, 1e-6), np.nan), v / area

    def score(self, cx, cy, hw, hh, ppm8, seam_w=None):
        """Score of axis-aligned rectangles (in this turned map) centred (cx, cy), half sizes hw, hh."""
        rim, gap, cor = RIM_MM * ppm8, GAP_MM * ppm8, CORNER_MM * ppm8
        x0, x1, y0, y1 = cx - hw, cx + hw, cy - hh, cy + hh
        sides = [
            (self.frac(x0 + cor, y0, x1 - cor, y0 + rim), self.frac(x0 + cor, y0 - gap, x1 - cor, y0)),
            (self.frac(x0 + cor, y1 - rim, x1 - cor, y1), self.frac(x0 + cor, y1, x1 - cor, y1 + gap)),
            (self.frac(x0, y0 + cor, x0 + rim, y1 - cor), self.frac(x0 - gap, y0 + cor, x0, y1 - cor)),
            (self.frac(x1 - rim, y0 + cor, x1, y1 - cor), self.frac(x1, y0 + cor, x1 + gap, y1 - cor)),
        ]
        sw = SEAM_W if seam_w is None else seam_w
        e, E = SEAM_MM * ppm8, self.Ie
        seams = [self.frac(x0 + cor, y0 - e, x1 - cor, y0 + e, E), self.frac(x0 + cor, y1 - e, x1 - cor, y1 + e, E),
                 self.frac(x0 - e, y0 + cor, x0 + e, y1 - cor, E), self.frac(x1 - e, y0 + cor, x1 + e, y1 - cor, E)]
        # each side weighted by how much of its strips is known (in frame, not under leaves): a side
        # nobody can see counts 0, never drops out of the mean
        c = np.stack([np.nan_to_num((1 - sw) * (i[0] - o[0]) + sw * sm[0]) * np.clip(np.minimum(i[1], o[1]) / KNOWN_FULL, 0, 1)
                      for (i, o), sm in zip(sides, seams)])
        s = c.sum(axis=0) / 4
        a = np.maximum((x1 - x0) * (y1 - y0), 1)
        inside = self._box(self.If, x0, y0, x1, y1) / a
        return s, inside

    def interior(self, cx, cy, hw, hh, ppm8):
        """The strongest line inside the rectangle, parallel to a side, that looks like the
        boundary between two touching trays: a seam with bright blue rim on both sides of it
        (fraction of its length, the weakest of the three). Cup and cell edges have soil or a
        pot on one side, so they do not count."""
        m, cor, E, r = INTERIOR_MARGIN_MM * ppm8, CORNER_MM * ppm8, self.Ie, RIM_MM * ppm8
        xs = np.arange(cx - hw + m, cx + hw - m, 1.0)
        ys = np.arange(cy - hh + m, cy + hh - m, 1.0)
        ya, yb = np.full_like(xs, cy - hh + cor), np.full_like(xs, cy + hh - cor)
        xa, xb = np.full_like(ys, cx - hw + cor), np.full_like(ys, cx + hw - cor)
        vx = np.minimum.reduce([self.frac(xs - 1, ya, xs + 1, yb, E)[0],
                                self.frac(xs - 1 - r, ya, xs - 1, yb)[0], self.frac(xs + 1, ya, xs + 1 + r, yb)[0]])
        vy = np.minimum.reduce([self.frac(xa, ys - 1, xb, ys + 1, E)[0],
                                self.frac(xa, ys - 1 - r, xb, ys - 1)[0], self.frac(xa, ys + 1, xb, ys + 1 + r)[0]])
        return float(np.nanmax(np.concatenate([vx, vy, [0.0]])))

    def to_map(self, x8, y8):
        return self.A[0, 0] * x8 + self.A[0, 1] * y8 + self.A[0, 2], self.A[1, 0] * x8 + self.A[1, 1] * y8 + self.A[1, 2]

    def from_map(self, x, y):
        a = self.Ainv
        return a[0, 0] * x + a[0, 1] * y + a[0, 2], a[1, 0] * x + a[1, 1] * y + a[1, 2]

    def corners(self, cx, cy, hw, hh):
        pts = np.float64([[cx - hw, cy - hh], [cx + hw, cy - hh], [cx + hw, cy + hh], [cx - hw, cy + hh]])
        return (pts @ self.Ainv[:, :2].T + self.Ainv[:, 2]) * F


def _half(ppm8, landscape, size):
    w, h = TRAY_MM if not landscape else TRAY_MM[::-1]
    return w / 2 * ppm8 * size, h / 2 * ppm8 * size


def _overlap(a, b):
    area, _ = cv2.intersectConvexConvex(np.float32(a), np.float32(b))
    return area / cv2.contourArea(np.float32(a))


class _Fit:
    def __init__(self, still):
        self.blue = _blue(still.quarter)
        self.h, self.w = self.blue.shape
        self.ppm = _ppm_grid(still, self.blue.shape)
        self.seam = _seam(still.quarter)
        self.known = _known(still.quarter)
        self.maps = {a: _Map(self.blue, self.seam, self.known, a) for a in ANGLES}

    def p8(self, x8, y8):
        return self.ppm[np.clip(np.asarray(y8).astype(int), 0, self.h - 1), np.clip(np.asarray(x8).astype(int), 0, self.w - 1)] / F

    def best_near(self, x8, y8, r, angles, lands, sizes=SIZES):
        """Best rectangle with its centre within r px (1/8) of (x8, y8), original frame."""
        g = np.arange(-r, r + 1e-6, 1.0)
        dx, dy = [a.ravel() for a in np.meshgrid(g, g)]
        keep = np.hypot(dx, dy) <= r + 1e-6
        dx, dy = dx[keep], dy[keep]
        p8 = float(self.p8(x8, y8))
        best = (-9.0, None)
        sz = np.asarray(sizes, float)
        DX, SZ = np.meshgrid(dx, sz)  # every position at every size, one call per angle and orientation
        DY = np.meshgrid(dy, sz)[0]
        DX, DY, SZ = DX.ravel(), DY.ravel(), SZ.ravel()
        for ang in angles:
            m = self.maps[ang]
            mx, my = m.to_map(x8, y8)
            for land in lands:
                hw, hh = _half(p8, land, SZ)
                s, inside = m.score(mx + DX, my + DY, hw, hh, p8)
                j = int(np.argmax(s))
                if s[j] <= best[0]:
                    continue  # the penalty only lowers a score
                it = m.interior(mx + DX[j], my + DY[j], hw[j], hh[j], p8)
                sj = float(s[j]) - INTERIOR_W * max(0.0, it - INTERIOR_FREE)
                if sj > best[0]:
                    best = (sj, dict(interior=it, poly=m.corners(mx + DX[j], my + DY[j], hw[j], hh[j]), inside=float(inside[j]),
                                     ang=ang, land=land, size=float(SZ[j]), rect=(mx + DX[j], my + DY[j], hw[j], hh[j], p8)))
        return best

    def coarse_peaks(self, floor):
        cand = []
        ys, xs = np.mgrid[0:self.h:STRIDE, 0:self.w:STRIDE].astype(float)
        for ang in COARSE_ANGLES:
            m = self.maps[ang]
            ox, oy = m.from_map(xs, ys)
            p8 = self.p8(ox, oy)
            for land in (False, True):
                for size in COARSE_SIZES:
                    hw, hh = _half(p8, land, size)
                    s, inside = m.score(xs, ys, hw, hh, p8, seam_w=0.0)  # seams too thin for the coarse grid
                    s = np.where(inside >= INSIDE_MIN, s, -1.0).astype(np.float32)
                    mx = cv2.dilate(s, np.ones((5, 5), np.uint8))
                    pk = (s >= mx - 1e-6) & (s >= floor)
                    for i, j in zip(*np.nonzero(pk)):
                        cand.append((float(s[i, j]), float(ox[i, j]), float(oy[i, j]), ang, land))
        cand.sort(key=lambda c: -c[0])
        out = []  # per orientation: drop peaks near a better one, keep the best N_REFINE
        for land in (False, True):
            kept = []
            for c in cand:
                if c[4] == land and all(np.hypot(c[1] - o[1], c[2] - o[2]) > 12 for o in kept):
                    kept.append(c)
                if len(kept) >= N_REFINE:
                    break
            out += kept
        return out


def find_notags(still: Still) -> list[dict]:
    """Diagnostic only: the global fit with the tags ignored (how far the photo alone gets)."""
    return find(still, use_tags=False)


def find(still: Still, use_tags: bool = True) -> list[dict]:
    fit = _Fit(still)
    accepted = []

    def ok(poly):
        return all(_overlap(poly, a["outline"]) <= OVERLAP_MAX for a in accepted)

    # --- tagged trays: search near both candidate centres of each tag
    tag_opts = []
    for p in still.tag_placements if use_tags else []:
        tag = next(t for t in still.tags if t["id"] == p.tray_id)
        tc = np.float64(tag["centre"])
        near = min(ANGLES, key=lambda a: abs(a - p.tilt_deg))
        angs = [a for a in ANGLES if abs(a - near) <= 1.01]
        for k, c in enumerate((np.float64(p.centre), 2 * tc - np.float64(p.centre))):
            x8, y8 = c / F
            r = TAG_WINDOW_MM * float(fit.p8(x8, y8))
            s, d = fit.best_near(x8, y8, r, angs, (False,))
            tag_opts.append((s, p.tray_id, k, d))
    tag_opts.sort(key=lambda t: -t[0])
    done = set()
    for s, tid, k, d in tag_opts:
        if tid in done or s < SCORE_MIN or not ok(d["poly"]):
            continue
        done.add(tid)
        accepted.append({"outline": d["poly"], "tray_id": tid, "warnings": [], "score": s,
                         "how": f"fit near tag, A1 at the {'other' if k else 'rig'} corner, score {s:.2f}, size {d['size']:.2f}"})
    for p in still.tag_placements if use_tags else []:
        if p.tray_id not in done:
            accepted.append({"outline": np.float64(p.outline), "tray_id": p.tray_id, "how": "tag placement",
                             "warnings": ["outline does not match tag"], "score": 0.0})

    # --- untagged trays: coarse peaks anywhere, refined, best first
    refined = []
    for s0, x8, y8, ang, land in fit.coarse_peaks(SCORE_MIN * 0.6):
        s, d = fit.best_near(x8, y8, REFINE, ANGLES, (land,))
        for _ in range(REFINE_STEPS - 1):  # climb: search again around the best so far
            c = np.asarray(d["poly"]).mean(0) / F
            s2, d2 = fit.best_near(c[0], c[1], REFINE, ANGLES, (land,))
            if s2 <= s + 1e-6:
                break
            s, d = s2, d2
        if s >= SCORE_MIN and d["inside"] >= INSIDE_MIN:
            refined.append((s, d))
    refined.sort(key=lambda t: -t[0])
    for s, d in refined:
        if not ok(d["poly"]):
            continue
        w = ["no tag"] + (["partly outside the photo"] if d["inside"] < 0.98 else [])
        accepted.append({"outline": d["poly"], "tray_id": None, "warnings": w, "score": s,
                         "how": f"global fit, score {s:.2f}, size {d['size']:.2f}, {d['ang']:+.0f} deg"})
    return [{k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in a.items() if k != "score"} for a in accepted]
