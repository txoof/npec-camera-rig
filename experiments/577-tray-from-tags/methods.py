"""Methods B and C of metrology log 56, for comparison against the app's method A.

B places each tray from its own tag alone. C starts from B, nudges each tray onto the blue rim
beside it, and then accounts for the blue: plastic no tray covers, and trays that overlap, are
leftover and are flagged. Research code: it imports `npec_rig`, nothing imports it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from npec_rig.tray_placement import (
    A1_TAG_TO_CENTRE_MM,
    TRAY_ID_RANGE,
    TRAY_SIZE_MM,
    _blue_rim,
    _heading_deg,
    _tilt_deg,
    tray_outline_at,
)

# How far the nudge may move a tray from where its tag put it, mm. The tag places a tray to about
# 10 mm (metrology log 15.5l) and the blue rim to about 3 mm (log 20), so a move beyond this is
# not a correction, it is a different tray. A decision, not a measurement.
NUDGE_MM = 25.0
# Step of the nudge search, mm. Finer than the blue finder's own spread.
NUDGE_STEP_MM = 2.0
# The rim band drawn along each side of a tray's outline when scoring blue coverage, mm. The tray
# wall measures 11 to 13 mm (review of #281).
RIM_BAND_MM = 9.0
# Blue left over, as a share of one tray's area, before the photo is called unexplained. A
# decision, not a measurement.
LEFTOVER_TRAY_SHARE = 0.25
# Two placed trays overlapping by more than this share of a tray are flagged.
OVERLAP_SHARE = 0.10


@dataclass(frozen=True)
class Placed:
    tray_id: int | None
    centre: tuple[float, float]
    corners: tuple[tuple[float, float], ...]
    tilt_deg: float
    moved_mm: float
    ring: float


def _tray_tags(detections):
    return [t for t in detections if t.tag_id in TRAY_ID_RANGE]


def _centre_from_tag(tag, ppm, corner_sign=1):
    """Where the tray's centre lies from its tag, taking the tag to lie in cell A1 (4 x 5 trays).
    `corner_sign` -1 is the other corner, for a tray laid the other way round."""
    tilt = _tilt_deg(tag)
    t = math.radians(180 + tilt)
    right, up = (math.cos(t), math.sin(t)), (math.sin(t), -math.cos(t))
    dx = (A1_TAG_TO_CENTRE_MM[0] * right[0] + A1_TAG_TO_CENTRE_MM[1] * up[0]) * ppm
    dy = (A1_TAG_TO_CENTRE_MM[0] * right[1] + A1_TAG_TO_CENTRE_MM[1] * up[1]) * ppm
    return (tag.centre[0] + corner_sign * dx, tag.centre[1] + corner_sign * dy), tilt


def place_from_tags(detections, scale_field, factor, rim=None):
    """Method B: each tray placed from its own tag, in full-size photo pixels. The blue is not
    used to move anything, so a tray with no readable tag is not placed at all.

    The tag lies in one corner cell, but which one depends on how the tray was laid down, and the
    two readings put the tray's centre about 350 mm apart. The app settles it with the slot layout
    (`place_trays`); here there is no slot layout, so with `rim` the blue settles it -- the corner
    whose outline covers more blue -- and without `rim` the A1 reading is taken and the other is
    reported as the alternative. A tray placed on the wrong corner lands off the table entirely.
    """
    out = []
    for tag in sorted(_tray_tags(detections), key=lambda d: d.tag_id):
        ppm = scale_field.px_per_mm(*tag.centre)
        band = max(2.0, RIM_BAND_MM * ppm / factor)
        best = None
        for sign in (1, -1):
            centre, tilt = _centre_from_tag(tag, ppm, sign)
            corners = tray_outline_at(centre, tilt, ppm)
            score = (_ring_score(rim, np.asarray(corners, float) / factor, band)
                     if rim is not None else (1.0 if sign == 1 else 0.0))
            if best is None or score > best[0]:
                best = (score, centre, corners, tilt)
        score, centre, corners, tilt = best
        out.append(Placed(tag.tag_id, centre, corners, tilt, 0.0, score))
    return out


def _ring_mask(shape, corners, band_px):
    """A mask of the band just inside a tray's outline, where its lit rim shows."""
    outer = np.zeros(shape, np.uint8)
    cv2.fillConvexPoly(outer, np.round(corners).astype(np.int32), 1)
    inner = cv2.erode(outer, np.ones((3, 3), np.uint8), iterations=max(1, int(round(band_px / 2))))
    return outer - inner


def _ring_score(rim, corners, band_px):
    """How much of a tray's rim band is blue. Only the tray's own neighbourhood is touched: a mask
    the size of the whole photo, built once per offset, made the nudge search hundreds of times
    slower than it needs to be (#577)."""
    pts = np.asarray(corners, float)
    pad = int(band_px) + 3
    x0 = max(0, int(pts[:, 0].min()) - pad); y0 = max(0, int(pts[:, 1].min()) - pad)
    x1 = min(rim.shape[1], int(pts[:, 0].max()) + pad); y1 = min(rim.shape[0], int(pts[:, 1].max()) + pad)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    ring = _ring_mask((y1 - y0, x1 - x0), pts - (x0, y0), band_px)
    n = int(ring.sum())
    return 0.0 if n == 0 else float((rim[y0:y1, x0:x1] & ring.astype(bool)).sum()) / n


def side_scores(rim, corners, band_px):
    """How much of each of a tray's four sides is blue, worst side first.

    The whole rim loop taken together is not enough: a tray placed in the gangway between two rows
    picks up the rims of the real trays above and below it, scores two sides out of four and looks
    like a tray (metrology log 56.8, the still of 2026-11-09 where it scored 0.66). A tray has
    blue on all four of its sides.
    """
    pts = np.asarray(corners, float)
    out = []
    for i in range(4):
        a, c = pts[i], pts[(i + 1) % 4]
        mid = (pts.mean(axis=0) - (a + c) / 2)
        n = np.linalg.norm(mid)
        inward = mid / n if n else np.zeros(2)
        quad = np.array([a, c, c + inward * band_px, a + inward * band_px])
        x0 = max(0, int(quad[:, 0].min()) - 2); y0 = max(0, int(quad[:, 1].min()) - 2)
        x1 = min(rim.shape[1], int(quad[:, 0].max()) + 2); y1 = min(rim.shape[0], int(quad[:, 1].max()) + 2)
        if x1 <= x0 or y1 <= y0:
            out.append(0.0); continue
        m = np.zeros((y1 - y0, x1 - x0), np.uint8)
        cv2.fillConvexPoly(m, np.round(quad - (x0, y0)).astype(np.int32), 1)
        n_px = int(m.sum())
        out.append(0.0 if n_px == 0 else float((rim[y0:y1, x0:x1] & m.astype(bool)).sum()) / n_px)
    return sorted(out)


def nudge_onto_blue(placed, rim, scale_field, factor):
    """Method C's nudge: the tray moved, within `NUDGE_MM`, to where its rim band covers the most
    blue. `rim` is the blue rim mask of the small image; `factor` its scale to full size."""
    ppm_small = scale_field.px_per_mm(*placed.centre) / factor
    band = max(2.0, RIM_BAND_MM * ppm_small)
    step = max(1.0, NUDGE_STEP_MM * ppm_small)
    reach = NUDGE_MM * ppm_small
    small = np.asarray(placed.corners, float) / factor
    best, best_d = None, (0.0, 0.0)
    # Coarse pass over the whole reach, then a fine pass around the best offset: the same answer
    # as the full grid on every still tried, at a fraction of the cost.
    for scale in (4.0, 1.0):
        centre_d = best_d
        span = reach if scale > 1 else step * 3
        offsets = np.arange(-span, span + step * scale / 2, step * scale)
        for dy in offsets:
            for dx in offsets:
                ox, oy = centre_d[0] + dx, centre_d[1] + dy
                if math.hypot(ox, oy) > reach:
                    continue
                s = _ring_score(rim, small + (ox, oy), band)
                if best is None or s > best:
                    best, best_d = s, (ox, oy)
    moved = math.hypot(*best_d) / ppm_small
    corners = tuple((x + best_d[0] * factor, y + best_d[1] * factor) for x, y in placed.corners)
    centre = (placed.centre[0] + best_d[0] * factor, placed.centre[1] + best_d[1] * factor)
    return Placed(placed.tray_id, centre, corners, placed.tilt_deg, moved, best or 0.0)


def leftover(rim, placed_list, scale_field, factor):
    """Blue the placed trays do not account for, and trays that overlap, as shares of one tray."""
    covered = np.zeros(rim.shape, np.uint8)
    for p in placed_list:
        cv2.fillConvexPoly(covered, np.round(np.asarray(p.corners, float) / factor).astype(np.int32), 1)
    blue = rim.astype(bool)
    left = int((blue & ~covered.astype(bool)).sum())
    ppm_small = scale_field.px_per_mm(rim.shape[1] * factor / 2, rim.shape[0] * factor / 2) / factor
    tray_px = TRAY_SIZE_MM[0] * ppm_small * TRAY_SIZE_MM[1] * ppm_small
    overlaps = 0
    for i, a in enumerate(placed_list):
        for b in placed_list[i + 1:]:
            ca = np.round(np.asarray(a.corners, float) / factor).astype(np.float32)
            cb = np.round(np.asarray(b.corners, float) / factor).astype(np.float32)
            area, _ = cv2.intersectConvexConvex(ca, cb)
            if area > OVERLAP_SHARE * tray_px:
                overlaps += 1
    return {"leftover_blue_px": left, "leftover_share": left / tray_px if tray_px else 0.0,
            "overlapping_pairs": overlaps}


def place_tags_then_blue(detections, image, scale_field, factor, ring_floor=0.0, grow_mask_mm=0.0):
    """Method C: tags anchor, blue explains the rest.

    The blue chooses which corner each tag lies in and nudges each tray onto the rim beside it. A
    tag whose tray covers less blue than `ring_floor` is not a tray at all (a tag on a wall, a
    sheet or a crate) and is dropped. The blue those trays do not cover is then put through the
    app's own finder, so a tray whose tag was covered by leaves, or which never had one, is still
    found. What is left after that is reported as leftover.
    """
    from npec_rig.tray_placement import find_outlines

    rim = _blue_rim(image)
    first = place_from_tags(detections, scale_field, factor, rim=rim)
    moved = [nudge_onto_blue(p, rim, scale_field, factor) for p in first]
    kept = [p for p in moved if p.ring >= ring_floor]
    dropped = len(moved) - len(kept)

    # The blue no placed tray accounts for, given back to the app's finder as a picture of its own.
    rest = image.copy()
    for p in kept:
        pts = np.asarray(p.corners, float) / factor
        if grow_mask_mm:
            # Blank a little beyond the tray, or its own rim is left behind as a thin strip just
            # outside the mask and two such strips either side of a gangway merge into a tray
            # that is not there (#577, the validation still of 2026-10-27).
            c = pts.mean(axis=0)
            grow = grow_mask_mm * scale_field.px_per_mm(*p.centre) / factor
            pts = pts + (pts - c) / np.linalg.norm(pts - c, axis=1, keepdims=True) * grow
        cv2.fillConvexPoly(rest, np.round(pts).astype(np.int32), (0, 0, 0))
    extra = []
    for o in find_outlines(rest, scale_field, factor):
        if any(cv2.intersectConvexConvex(np.asarray(o.corners, np.float32),
                                         np.asarray(k.corners, np.float32))[0] > 0.25 *
               cv2.contourArea(np.asarray(o.corners, np.float32)) for k in kept):
            continue
        extra.append(Placed(None, o.centre, o.corners, o.tilt_deg, 0.0,
                            _ring_score(rim, np.asarray(o.corners, float) / factor,
                                        max(2.0, RIM_BAND_MM * scale_field.px_per_mm(*o.centre) / factor))))
    out = kept + extra
    report = leftover(rim, out, scale_field, factor)
    report.update({"from_tags": len(kept), "from_blue": len(extra), "dropped_low_ring": dropped,
                   "rings": [round(p.ring, 3) for p in out],
                   "tray_rings": [[round(p.ring, 3), "tag" if p.tray_id is not None else "blue"]
                                  for p in out]})
    return out, report


# --- Method D: the app everywhere, tags re-cut only a block that is short of tags -------------
# A, the app, is the better method on nearly every still of section 56; its one known failure is a
# tray lying off the grid of a touching block, which it splits across two outlines (section 55).
# A block short of tags is exactly the signal for that (#579). D therefore leaves A alone except
# inside such a block, and places a tray per tag there, with every tray required to sit inside
# that block's own blue. The gangway between two rows is not part of a blue block, so the phantom
# of 56.8 cannot be made.

# A tray placed in a re-cut block must have its centre inside the block's blue hull, grown by this
# much to allow for the tray at the edge of the block. A decision, not a measurement.
BLOCK_SLACK_MM = 40.0
# What is blanked around a placed tray before the leftover blue is given back to the app's finder:
# the outline alone leaves the tray's own rim behind as a strip (56.8 and the test of 2026-11-27).
MASK_GROW_MM = 5.0


def _hull_of(outlines, factor):
    pts = np.vstack([np.asarray(o.corners, float) / factor for o in outlines]).astype(np.float32)
    return cv2.convexHull(pts).reshape(-1, 2)


def place_recut_blocks(detections, image, scale_field, factor):
    """Method D. Returns (trays, report). Each tray is a `Placed`; `tray_id` None means the app's
    own outline, kept unchanged."""
    from npec_rig.tray_placement import BLOCK_SUSPECT, find_outlines, name_trays

    rim = _blue_rim(image)
    outlines = find_outlines(image, scale_field, factor)
    named = name_trays(outlines, detections)
    suspect = {o.block for o in outlines
               if any(BLOCK_SUSPECT in t.warnings and t.outline == o.corners for t in named)}
    out = [Placed(None, o.centre, o.corners, o.tilt_deg, 0.0, float("nan"))
           for o in outlines if o.block not in suspect]
    recut = 0
    for block in sorted(suspect):
        members = [o for o in outlines if o.block == block]
        hull = _hull_of(members, factor)
        ppm_small = scale_field.px_per_mm(*members[0].centre) / factor
        slack = BLOCK_SLACK_MM * ppm_small
        inside = [t for t in _tray_tags(detections)
                  if cv2.pointPolygonTest(hull.astype(np.float32),
                                          (t.centre[0] / factor, t.centre[1] / factor), True) >= -slack]
        if not inside:
            out += [Placed(None, o.centre, o.corners, o.tilt_deg, 0.0, float("nan")) for o in members]
            continue
        placed = []
        for tag in inside:
            ppm = scale_field.px_per_mm(*tag.centre)
            band = max(2.0, RIM_BAND_MM * ppm / factor)
            best = None
            for sign in (1, -1):
                centre, tilt = _centre_from_tag(tag, ppm, sign)
                if cv2.pointPolygonTest(hull.astype(np.float32),
                                        (centre[0] / factor, centre[1] / factor), True) < -slack:
                    continue  # outside this block's blue: not a tray of this block
                corners = tray_outline_at(centre, tilt, ppm)
                score = _ring_score(rim, np.asarray(corners, float) / factor, band)
                if best is None or score > best[0]:
                    best = (score, centre, corners, tilt)
            if best is None:
                continue
            placed.append(nudge_onto_blue(
                Placed(tag.tag_id, best[1], best[2], best[3], 0.0, best[0]), rim, scale_field, factor))
        if not placed:
            out += [Placed(None, o.centre, o.corners, o.tilt_deg, 0.0, float("nan")) for o in members]
            continue
        # Blue of this block that no placed tray covers keeps the app's own outline for it.
        for o in members:
            c = np.asarray(o.corners, np.float32)
            if any(cv2.intersectConvexConvex(c, np.asarray(p.corners, np.float32))[0] > 0.25 * cv2.contourArea(c)
                   for p in placed):
                continue
            placed.append(Placed(None, o.centre, o.corners, o.tilt_deg, 0.0, float("nan")))
        out += placed
        recut += 1
    return out, {"blocks_recut": recut, "app_outlines": len(outlines)}
