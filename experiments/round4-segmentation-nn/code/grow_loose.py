"""#406 step 2: grow from leaf cores with the smallest seedlings kept (README, step 2, decision of
2026-11-20 on check sheet 01).

The app's grow_from_cores (segmentation.py) seeds a piece only where a pixel is greener than the
core cutoff AND its green is above its red. The smallest production seedlings (22 October, a few
pixels across) are olive in the photo: red equal to or a little above green (peak G - R from -8 to
0 in tray 5 of photo 2037), so they are never seeded. Here a piece is also seeded by a pixel
greener than the core cutoff with G - R above LOOSE_GR, but only a piece of at most LOOSE_MAX_PX
pixels: on the training reference cells a looser seed on large pieces grows into moss (development
experiment 3) and pale leaf edges past the truth.

Training reference cells (pooled IoU, grow on each crop, core G - R > -10):
    only pieces up to   0 px (the app):  production 0.9452, development 0.9785
                      200 px:            production 0.9496, development 0.9732
                      400 px:            production 0.9496, development 0.9711
                      600 px:            production 0.9496, development 0.9685
                     1000 px:            production 0.9496, development 0.9669
The missed shoots of photo 2037 tray 5 lie in pieces of 186 to 402 pixels (at the tray's lower
cutoff), so 200 kept none of them; 600 is the smallest step above them. Production gains the same from
200 to 1000; development's reference cells (experiment 3, moss on the soil) lose a little more at
each step. The development photos labelled are experiment 4 (brown soil, no moss seen).

`grow_trays(rgb, trays, loose_gr, loose_max_px)` returns what segmentation.grow_trays returns;
with loose_max_px 0 its mask is the app's, pixel for pixel (checked on every tray at each call)."""
import cv2
import numpy as np

from npec_rig import segmentation as S

LOOSE_GR = -10
LOOSE_MAX_PX = 600


def _grow(box, inside, tag_corners, loose_gr, loose_max_px):
    """grow_from_cores of segmentation.py, step for step, plus the loose seeds (docstring)."""
    box = box if box.dtype == np.uint8 and box.strides[1:] == (3, 1) else np.ascontiguousarray(box, dtype=np.uint8)
    r, g, b = cv2.split(box)
    red_green = cv2.max(r, g)
    lo, hi = cv2.min(cv2.min(r, g), b), cv2.max(red_green, b)
    white = cv2.bitwise_and(cv2.compare(lo, S.GROWN_WHITE_MIN, cv2.CMP_GT),
                            cv2.compare(cv2.subtract(hi, lo), S.GROWN_WHITE_SPREAD, cv2.CMP_LT))
    notblue = cv2.compare(cv2.subtract(b, red_green), S.GROWN_BLUE_MARGIN, cv2.CMP_LE)
    red_blue = cv2.add(r, b, dtype=cv2.CV_16U)
    greener = S._greener(g, red_blue, S.GROWN_CORE_MIN)
    core = cv2.bitwise_and(greener, cv2.compare(g, r, cv2.CMP_GT))
    loose = cv2.bitwise_and(greener, ((g.astype(np.int16) - r.astype(np.int16)) > loose_gr).view(np.uint8) * np.uint8(255))
    no_plant = np.zeros(white.shape, dtype=np.uint8)
    if cv2.countNonZero(white) >= S.GROWN_WHITE_MIN_PX:
        _n, labels, stats, _ = cv2.connectedComponentsWithStats(white, connectivity=8)
        big = [k for k in range(1, len(stats)) if stats[k, cv2.CC_STAT_AREA] >= S.GROWN_WHITE_MIN_PX]
        if big:
            no_plant = cv2.dilate(S._pieces(labels, stats, big), np.ones((S.GROWN_WHITE_WIDEN_PX,) * 2, np.uint8))
    for corners in tag_corners:
        c = np.asarray(corners, dtype=np.float64)
        centre = c.mean(axis=0)
        cv2.fillPoly(no_plant, [np.round(centre + S.GROWN_TAG_ENLARGE * (c - centre)).astype(np.int32).reshape(-1, 1, 2)], 1)
    sel = cv2.bitwise_and(cv2.compare(no_plant, 0, cv2.CMP_EQ), inside.view(np.uint8) * np.uint8(255))
    soil_level = S._soil_level(S._greenness_table(), S._counts(g, red_blue, cv2.bitwise_and(sel, notblue)))
    hidden = S.soil_hidden(soil_level, None)  # this script does not measure blue coverage (#486)
    lower_cutoff = S.GROWN_FLOOR if soil_level is None or hidden else max(S.GROWN_FLOOR, soil_level + S.GROWN_GAP)
    low = cv2.bitwise_and(cv2.bitwise_and(S._greener(g, red_blue, lower_cutoff), notblue), sel)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(low, connectivity=8, ltype=cv2.CV_32S)
    seeded = np.zeros(n, dtype=bool)
    seeded[labels[cv2.bitwise_and(core, sel) > 0]] = True
    strict = seeded.copy()
    small = stats[:, cv2.CC_STAT_AREA] <= loose_max_px
    extra = np.zeros(n, dtype=bool)
    extra[labels[cv2.bitwise_and(loose, sel) > 0]] = True
    seeded |= extra & small
    seeded[0] = strict[0] = False
    return (S._pieces(labels, stats, np.flatnonzero(seeded)) > 0, S._pieces(labels, stats, np.flatnonzero(strict)) > 0,
            soil_level, float(lower_cutoff))


def grow_trays(rgb, trays, loose_gr=LOOSE_GR, loose_max_px=LOOSE_MAX_PX):
    """As segmentation.grow_trays, with the loose seeds; also returns the app's own mask."""
    mask = np.zeros(rgb.shape[:2], dtype=bool)
    app = np.zeros(rgb.shape[:2], dtype=bool)
    levels = []
    for outline, tag_corners in trays:
        box = S._box(mask, outline)
        if box is None:
            levels.append((None, None))
            continue
        x0, y0, x1, y1 = box
        own = [np.asarray(c, dtype=np.float64) - [x0, y0] for c in tag_corners]
        inside = S._inside(box, outline)
        m, strict, soil, cut = _grow(rgb[y0:y1, x0:x1], inside, own, loose_gr, loose_max_px)
        ref = S.grow_from_cores(rgb[y0:y1, x0:x1], inside, own)
        assert np.array_equal(strict, ref.mask) and soil == ref.soil_level and cut == ref.lower_cutoff
        mask[y0:y1, x0:x1] |= m
        app[y0:y1, x0:x1] |= strict
        levels.append((soil, cut))
    return mask, levels, app
