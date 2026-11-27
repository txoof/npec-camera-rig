"""Scratch prototype: keep the lattice cut (tray_placement.find_outlines); repair cells the blue rim does not support.
core(rim, ppm_q, F, lattice_corners_fullpx) -> list of (corners_fullpx, how)"""
import cv2, numpy as np

SUSPECT = 0.45      # a lattice cell whose in-frame rim loop is covered less than this is suspect
ACCEPT = 0.60       # a repaired tray needs at least this
MAX_OVERLAP = 0.15
MIN_MOVE = 0.25     # a repair must move the tray by this share of its size (a decision, not a measurement)
BAND_MM = 9.0
TRAY = (305.0, 366.0)


def _maps(rim, ppm):
    H, W = rim.shape
    band = max(3, int(round(BAND_MM * ppm)))
    pad = int(max(TRAY) * ppm)
    padded = cv2.copyMakeBorder(rim, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    valid = cv2.copyMakeBorder(np.ones_like(rim), pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    out = []
    for tw_mm, th_mm in (TRAY, TRAY[::-1]):
        tw, th = int(round(tw_mm * ppm)), int(round(th_mm * ppm))
        ring = np.ones((th, tw), np.float32); ring[band:-band, band:-band] = 0
        num = cv2.matchTemplate(padded, ring, cv2.TM_CCORR)
        den = cv2.matchTemplate(valid, ring, cv2.TM_CCORR)
        sc = np.where(den >= 0.5 * ring.sum(), num / np.maximum(den, 1), 0).astype(np.float32)
        out.append((sc, tw, th))
    return out, pad


def core(rim, ppm, F, lattice):
    maps, pad = _maps(rim, ppm)
    cells = []
    for corners in lattice:
        c = np.asarray(corners) / F
        x0, y0, x1, y1 = c[:, 0].min(), c[:, 1].min(), c[:, 0].max(), c[:, 1].max()
        portrait = (y1 - y0) >= (x1 - x0)
        sc, tw, th = maps[0] if portrait else maps[1]
        xi, yi = int(round(x0)) + pad, int(round(y0)) + pad
        win = sc[max(0, yi - 6): yi + 7, max(0, xi - 6): xi + 7]
        cells.append((float(win.max()) if win.size else 0.0, (x0, y0, x1 - x0, y1 - y0), corners))
    trusted = [c for c in cells if c[0] >= SUSPECT]
    suspects = [c for c in cells if c[0] < SUSPECT]
    out = [(c[2], f"lattice {c[0]:.2f}") for c in trusted]
    if not suspects:
        return out
    # repair: ring peaks near a suspect cell, away from trusted trays (search window only, to save memory)
    boxes = [(x0, y0, w, h) for _, (x0, y0, w, h), _ in trusted]
    accepted = []
    for _ in range(len(suspects) + 3):
        best = None
        for k, (sc, tw, th) in enumerate(maps):
            cands = np.zeros(sc.shape, bool)
            for _, (sx, sy, sw, sh), _ in suspects:
                cx, cy = sx + sw / 2, sy + sh / 2
                xa, xb = int(cx - tw * 0.75 - tw / 2) + pad, int(cx + tw * 0.75 - tw / 2) + pad
                ya, yb = int(cy - th * 0.75 - th / 2) + pad, int(cy + th * 0.75 - th / 2) + pad
                cands[max(0, ya):max(0, yb), max(0, xa):max(0, xb)] = True
            ys_i, xs_i = np.where(cands)
            if len(xs_i) == 0:
                continue
            ya0, ya1, xa0, xa1 = ys_i.min(), ys_i.max() + 1, xs_i.min(), xs_i.max() + 1
            s = np.where(cands[ya0:ya1, xa0:xa1], sc[ya0:ya1, xa0:xa1], 0).astype(np.float32)
            xs = np.arange(xa0, xa1) - pad; ys = np.arange(ya0, ya1) - pad
            for bx, by, bw, bh in boxes + [(a, b, w2, h2) for _, (a, b, w2, h2) in accepted]:
                ox = np.clip(np.minimum(xs + tw, bx + bw) - np.maximum(xs, bx), 0, None)
                oy = np.clip(np.minimum(ys + th, by + bh) - np.maximum(ys, by), 0, None)
                s[(oy[:, None] * ox[None, :]) / (tw * th) > MAX_OVERLAP] = 0
            _, mx, _, loc = cv2.minMaxLoc(s)
            if best is None or mx > best[0]:
                best = (mx, (loc[0] + xa0, loc[1] + ya0), tw, th)
        if best is None:
            break
        mx, loc, tw, th = best
        if mx < ACCEPT:
            break
        px, py = loc[0] - pad + tw / 2, loc[1] - pad + th / 2
        if min(max(abs(px - (sx + sw / 2)) / tw, abs(py - (sy + sh / 2)) / th) for _, (sx, sy, sw, sh), _ in suspects) < MIN_MOVE:
            break
        accepted.append((mx, (loc[0] - pad, loc[1] - pad, tw, th)))
    for mx, (x0, y0, tw, th) in accepted:
        corners = np.float64([[x0, y0], [x0 + tw, y0], [x0 + tw, y0 + th], [x0, y0 + th]]) * F
        out.append((corners, f"repaired {mx:.2f}"))
    # a suspect cell stays only if blue rim lies in it that no trusted or repaired tray explains
    kept = [(a, b, w, h) for _, (a, b, w, h), _ in trusted] + [b for _, b in accepted]
    for sc_, (sx, sy, sw, sh), corners in suspects:
        x0, y0, x1, y1 = (max(0, int(sx)), max(0, int(sy)), min(rim.shape[1], int(sx + sw)), min(rim.shape[0], int(sy + sh)))
        inside = rim[y0:y1, x0:x1] > 0
        n = inside.sum()
        if n < 0.02 * sw * sh:
            continue                      # almost no blue: bare table, not a tray
        covered = np.zeros(inside.shape, bool)
        for a, b, w, h in kept:
            covered[max(0, int(b) - y0):max(0, int(b + h) - y0), max(0, int(a) - x0):max(0, int(a + w) - x0)] = True
        if (inside & ~covered).sum() > 0.3 * n:
            out.append((corners, f"weak {sc_:.2f}"))
    return out
