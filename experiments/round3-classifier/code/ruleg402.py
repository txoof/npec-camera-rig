"""Copy of experiments/352-green-threshold/code/ruleg.py for #402, the hard-coded sys.path removed (npec_rig from PYTHONPATH).
#352, metrology log 24.7: grow from soil-relative cores (rule G), and grow from cores (rule F) for
comparison, on one tray's RGB box. Tag area from the app's tray-tag detector plus a white backup."""
import sys
import numpy as np, cv2
from npec_rig.tags import detect_tags

TAG_K = np.ones((61, 61), np.uint8)
BINS = np.arange(-0.5, 0.5001, 0.01); CTR = (BINS[:-1] + BINS[1:]) / 2
GAP, WARN_CUT, CORE = 0.115, 0.05, 0.1
H_GAP, H_FLOOR, H_WARN = 0.07, -0.045, 0.1
_k = np.exp(-0.5 * (np.arange(-6, 7) / 2.0) ** 2); KERNEL = _k / _k.sum()


def tag_mask(rgb, tray_id=None, tags=None):
    """True on the tray tag's square enlarged 1.6x, and on large colourless white pieces widened 30 px.
    `tags`: detections to reuse (in this box's coordinates); found here when None."""
    h, w = rgb.shape[:2]
    m = np.zeros((h, w), np.uint8)
    dets = detect_tags(rgb) if tags is None else tags
    for d in dets:
        if tray_id is not None and d.tag_id != tray_id:
            continue
        c = np.asarray(d.corners, float); cen = c.mean(0)
        cv2.fillPoly(m, [np.round(cen + 1.6 * (c - cen)).astype(np.int32).reshape(-1, 1, 2)], 1)
    r, g, b = (rgb[..., i].astype(np.float32) for i in range(3))
    mn, mx = np.minimum(np.minimum(r, g), b), np.maximum(np.maximum(r, g), b)
    white = ((mn > 140) & (mx - mn < 25)).astype(np.uint8)
    n, wl, st, _ = cv2.connectedComponentsWithStats(white, connectivity=8)
    big = np.isin(wl, [k for k in range(1, n) if st[k, cv2.CC_STAT_AREA] >= 5000]).astype(np.uint8)
    return (m > 0) | (cv2.dilate(big, TAG_K) > 0), dets


def soil_peak(exg, sel):
    h, _ = np.histogram(exg[sel], bins=BINS)
    sm = np.convolve(h.astype(float), KERNEL, mode='same')
    below = CTR < 0.05
    return float(CTR[below][np.argmax(sm[below])])


def grow(exg, g, r, notblue, sel, low_cut):
    core = (exg > CORE) & (g > r) & sel
    low = ((exg > low_cut) & notblue & sel).astype(np.uint8)
    n, lab = cv2.connectedComponents(low, connectivity=8, ltype=cv2.CV_32S)
    keep = np.zeros(n, bool); keep[np.unique(lab[core])] = True; keep[0] = False
    return keep[lab]


def rules(rgb, ins, tray_id=None, tags=None):
    """rgb: tray box (R G B); ins: tray outline mask. Returns masks F and G, the soil peak, the cutoff,
    the warning, and the tag detections used."""
    r, g, b = (rgb[..., i].astype(np.float32) for i in range(3))
    exg = (2 * g - r - b) / (r + g + b + 1e-6)
    notblue = ~((b > r) & (b > g))
    tag, dets = tag_mask(rgb, tray_id, tags)
    sel = ins & ~tag
    peak = soil_peak(exg, sel & notblue)
    cut = peak + GAP
    cut_h = max(H_FLOOR, peak + H_GAP)
    return dict(F=grow(exg, g, r, notblue, sel, -0.045), G=grow(exg, g, r, notblue, sel, cut), soil_peak=peak,
                cut=round(cut, 3), warn=cut > WARN_CUT, H=grow(exg, g, r, notblue, sel, cut_h), cut_h=round(cut_h, 3), warn_h=cut_h >= H_WARN, current=(exg > CORE) & (g > r) & ins, dets=dets)
