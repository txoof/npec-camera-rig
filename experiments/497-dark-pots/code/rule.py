"""Noise-aware rule for grow from leaf cores (metrology log 46, issue #497).

An experiment-side copy of `segmentation.grow_from_cores` with one change: a pixel is a core, and
is grown into, only if it clears a margin of `thr` code levels. Form "A": its green exceeds its red by
more than `thr` (`G - R > thr`). Form "B": its greenness numerator clears the cutoff by more than `thr`
(`(2G - R - B) - cutoff * (R + G + B) > thr`, the core cutoff on cores, the lower cutoff on growth). The soil level and
lower cutoff are worked out exactly as the app does (the rule does not touch them). With
`thr=None` the copy gives the app's own mask; `check_copy` shows that on a box.
Imports the app, never the reverse.
"""
from __future__ import annotations

import cv2
import numpy as np

from npec_rig import segmentation as sg


def grow_sweep(rgb, inside, thrs, tag_corners=(), lower_cutoff=None, core_min=sg.GROWN_CORE_MIN, form="A"):
    """Yield (thr, mask, soil_level, lower_cutoff) for each thr in `thrs` (None = no rule).
    form "A": green must exceed red by more than thr levels (G - R > thr), as written in log 46.
    form "B": the greenness test keeps its cutoff, and its numerator must clear the cutoff by more
    than thr levels: (2G - R - B) - cutoff * (R + G + B) > thr, for the core cutoff on cores and the
    lower cutoff on the growth. Added after form A was measured (log 46.3)."""
    box = rgb if rgb.dtype == np.uint8 and rgb.strides[1:] == (3, 1) else np.ascontiguousarray(rgb, dtype=np.uint8)
    r, g, b = cv2.split(box)
    red_green = cv2.max(r, g)
    lo, hi = cv2.min(cv2.min(r, g), b), cv2.max(red_green, b)
    white = cv2.bitwise_and(cv2.compare(lo, sg.GROWN_WHITE_MIN, cv2.CMP_GT),
                            cv2.compare(cv2.subtract(hi, lo), sg.GROWN_WHITE_SPREAD, cv2.CMP_LT))
    notblue = cv2.compare(cv2.subtract(b, red_green), sg.GROWN_BLUE_MARGIN, cv2.CMP_LE)
    red_blue = cv2.add(r, b, dtype=cv2.CV_16U)
    core0 = cv2.bitwise_and(sg._greener(g, red_blue, core_min), cv2.compare(g, r, cv2.CMP_GT))
    d = cv2.subtract(g, r)  # green over red in code levels, 0 where red is the larger
    if form == "B":
        num = (2 * g.astype(np.int16) - r - b)  # 2G - R - B
        sumrgb = (r.astype(np.int16) + g + b)
    no_plant = np.zeros(white.shape, dtype=np.uint8)
    if cv2.countNonZero(white) >= sg.GROWN_WHITE_MIN_PX:
        _n, labels, stats, _ = cv2.connectedComponentsWithStats(white, connectivity=8)
        big = [k for k in range(1, len(stats)) if stats[k, cv2.CC_STAT_AREA] >= sg.GROWN_WHITE_MIN_PX]
        if big:
            no_plant = cv2.dilate(sg._pieces(labels, stats, big), np.ones((sg.GROWN_WHITE_WIDEN_PX,) * 2, np.uint8))
    for corners in tag_corners:
        c = np.asarray(corners, dtype=np.float64)
        centre = c.mean(axis=0)
        cv2.fillPoly(no_plant, [np.round(centre + sg.GROWN_TAG_ENLARGE * (c - centre)).astype(np.int32).reshape(-1, 1, 2)], 1)
    sel = cv2.bitwise_and(cv2.compare(no_plant, 0, cv2.CMP_EQ), inside.view(np.uint8) * np.uint8(255))
    soil_level = sg._soil_level(sg._greenness_table(), sg._counts(g, red_blue, cv2.bitwise_and(sel, notblue)))
    hidden = sg.soil_hidden(soil_level)
    lc = lower_cutoff
    if lc is None:
        lc = sg.GROWN_FLOOR if soil_level is None or hidden else max(sg.GROWN_FLOOR, soil_level + sg.GROWN_GAP)
    low0 = cv2.bitwise_and(cv2.bitwise_and(sg._greener(g, red_blue, lc), notblue), sel)
    for thr in thrs:
        if thr is None:
            low, core = low0, core0
        else:
            if form == "A":
                okl = okc = cv2.compare(d, float(thr), cv2.CMP_GT)
            else:
                okl = ((num - lc * sumrgb) > thr).view(np.uint8) * np.uint8(255)
                okc = ((num - core_min * sumrgb) > thr).view(np.uint8) * np.uint8(255)
            low, core = cv2.bitwise_and(low0, okl), cv2.bitwise_and(core0, okc)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(low, connectivity=8, ltype=cv2.CV_32S)
        seeded = np.zeros(n, dtype=bool)
        seeded[labels[cv2.bitwise_and(core, sel) > 0]] = True
        seeded[0] = False
        yield thr, sg._pieces(labels, stats, np.flatnonzero(seeded)) > 0, soil_level, float(lc)


def noise_arrays(rgb, sel, win=15, form="A"):
    """(residual, S) of the pixels in `sel`: form A, the residual of green-minus-red about the median
    of its `win` x `win` neighbourhood; form B, the residual of 2G - R - B about the mean of its
    neighbourhood (code levels); and R+G+B."""
    r, g, b = cv2.split(np.ascontiguousarray(rgb))
    s = r.astype(np.int16) + g + b
    if form == "A":
        d = g.astype(np.int16) - r.astype(np.int16)
        dm = cv2.medianBlur(np.clip(d + 128, 0, 255).astype(np.uint8), win).astype(np.int16)
        return (d + 128 - dm)[sel].astype(np.int8), s[sel]
    n = (2 * g.astype(np.int16) - r - b).astype(np.float32)
    res = n - cv2.blur(n, (win, win))
    return np.clip(np.round(res[sel]), -127, 127).astype(np.int8), s[sel]


def _mad(x):
    """Standard deviation of the residuals about 0 (they are already about the local median). The
    robust MAD was tried first and is 0 here: most dark pixels have a residual of exactly 0, and the
    few that do not are the noise this has to count."""
    return float(np.sqrt(np.mean(np.square(x.astype(np.float64)))))


def sigma_from(res, s, frac=0.10):
    """Noise of green-minus-red of a photo, in code levels, from the image itself: the root mean square
    of the residuals of the darkest `frac` of the
    pixels (by R+G+B rank within the photo, not by a fixed value). Also the spread over all pixels,
    and the number of pixels in the dark part."""
    cut = np.percentile(s, frac * 100)
    dark = res[s <= cut]
    return _mad(dark), _mad(res), int(dark.size)
