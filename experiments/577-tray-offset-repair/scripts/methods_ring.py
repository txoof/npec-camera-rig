"""Scratch prototype for #? (tray boundaries): tray-sized rectangles placed by how much of their
outer rim loop the blue rim covers. Photo only. Interface of experiments/round3-tray-outlines."""
import cv2
import numpy as np

SCORE_MIN = 0.55
MAX_OVERLAP = 0.15
BAND_MM = 9.0
TRAY = (305.0, 366.0)


def _evidence(still):
    # same evidence as the app's finder (tray_placement._blue_rim), harness stills are BGR
    from npec_rig import tray_placement as tp
    return tp._blue_rim(cv2.cvtColor(still.quarter, cv2.COLOR_BGR2RGB)).astype(np.float32)


def find(still):
    rim = _evidence(still)
    H, W = rim.shape
    F = 4
    ppm = still.px_per_mm(W * F / 2, H * F / 2) / F
    band = max(3, int(round(BAND_MM * ppm)))
    out = []
    cands = []
    pad = int(max(TRAY) * ppm / 2)
    padded = cv2.copyMakeBorder(rim, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    maps = []
    for (tw_mm, th_mm) in (TRAY, TRAY[::-1]):
        tw, th = int(round(tw_mm * ppm)), int(round(th_mm * ppm))
        ring = np.ones((th, tw), np.float32); ring[band:-band, band:-band] = 0
        sc = cv2.matchTemplate(padded, ring, cv2.TM_CCORR) / ring.sum()
        maps.append((sc, tw, th))
    accepted = []
    while True:
        best = None
        for k, (sc, tw, th) in enumerate(maps):
            _, mx, _, loc = cv2.minMaxLoc(sc)
            if best is None or mx > best[0]:
                best = (mx, loc, k)
        mx, loc, k = best
        if mx < SCORE_MIN:
            break
        _, tw, th = maps[k]
        x0, y0 = loc[0] - pad, loc[1] - pad
        accepted.append((mx, (x0, y0, tw, th)))
        for sc, tw2, th2 in maps:
            # overlap of a tray of this map's size at (x, y) with the accepted one, as a share of a tray
            xs = np.arange(sc.shape[1]) - pad; ys = np.arange(sc.shape[0]) - pad
            ox = np.clip(np.minimum(xs + tw2, x0 + tw) - np.maximum(xs, x0), 0, None)
            oy = np.clip(np.minimum(ys + th2, y0 + th) - np.maximum(ys, y0), 0, None)
            ov = (oy[:, None] * ox[None, :]) / (tw2 * th2)
            sc[ov > MAX_OVERLAP] = 0
        if len(accepted) > 40:
            break
    for mx, (x0, y0, tw, th) in accepted:
        corners = np.float64([[x0, y0], [x0 + tw, y0], [x0 + tw, y0 + th], [x0, y0 + th]]) * F
        edge = x0 <= 2 or y0 <= 2 or x0 + tw >= W - 2 or y0 + th >= H - 2
        out.append({"outline": corners, "tray_id": None, "how": f"ring {mx:.2f}",
                    "warnings": ["no tag"] + (["partly outside the photo"] if edge else [])})
    return out
