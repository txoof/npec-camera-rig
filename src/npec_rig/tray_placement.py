"""Trays found in a photo from their blue plastic and named by the tag inside them (#331).

Found in the photo (`find_outlines`, metrology log 20 and 20.1): the blue finder of
`experiments/round3-tray-outlines/methods_blue.py`, photo only, tags never used for where a tray
is. Named (`name_trays`): a tray tag names the outline its centre lies inside, wherever it lies
in the tray. A tray tag inside no outline is only seen: a tray is never placed from its tag for a
reading, because that assumed the tag lay in cell A1 and put trays about 176 mm off for tags
lying elsewhere (metrology log 21.1).

Placed from the tag (`place_trays`, #220): kept for the certainty map only
(`certainty_map.py`), which places trays on a calibration's slot layout. Not for tray readings:

The method of metrology log 15.5h to 15.5l, written fresh from `experiments/round1-trays/shuffle.py`
(`place_any_rotation`): geometry on the tag detections, no image segmentation.

1. The tray's tag lies in cell A1, any way round. Its centre gives cell A1.
2. With 12 trays (4 x 5, portrait), A1 is at the south-west or the north-east corner. The two
   candidate tray centres are the tag centre plus and minus one offset common to every tray,
   turned by the tray's tilt and converted with the calibration's scale at the tag.
3. The candidate nearer a slot centre of the calibration's slot layout is taken; its slot and
   corner are the result.
4. The outline is the tray's measured outside size around that centre, turned by the tilt.

The tag's heading is never used for which way the tray faces, only for its tilt.
"""

import math
from collections import Counter
from dataclasses import dataclass, replace

import cv2
import numpy as np

from npec_rig.calibration import ScaleField
from npec_rig.tags import TRAY_ID_RANGE, TagDetection

# From the tag centre to the tray centre, mm, (right, up) in the frame of a tag lying with its top
# to the south (heading 180) on a tray with A1 at the south-west, turned by the tilt only. The median over 12 trays of 40 mm tags in cell A1, learned from the
# layout 1 stills of 20 October (metrology log 15.5l; every tray within 9.6 mm of it).
A1_TAG_TO_CENTRE_MM = (-104.0, -141.6)

# Outside size of a 4 x 5 tray in portrait, lip included, east-west by north-south, mm
# (tape measure, reference/trays.md).
TRAY_SIZE_MM = (305.0, 366.0)

# Below this difference between the two candidates' distances to their nearest slot, the corner
# is reported as a close call. A decision, not a measurement: the smallest difference seen over
# the 20 October shuffles was 103.4 mm (metrology log 15.5l).
CLOSE_CALL_MM = 50.0


@dataclass(frozen=True)
class TrayPlacement:
    """One tray, placed from its tag or found in the photo (#331). Positions in full-size photo
    pixels. What is not known is None: the tray ID of an outline with no tag, the outline of a tag
    whose tray was not found, the slot, A1 corner and margin of every tray not placed by
    `place_trays`."""

    tray_id: int | None
    centre: tuple[float, float]
    slot: str | None
    a1_corner: str | None  # "SW", or "NE" (tray turned 180)
    tilt_deg: float
    outline: tuple[tuple[float, float], ...] | None  # four outside corners; None: a tag seen, no tray found
    margin_mm: float | None  # how much nearer a slot the chosen candidate is than the other
    status: str = "placed"  # or "close call", "two trays in one slot" (place_trays), "two tags in one outline"
    found: str = "tag only"  # or "photo + tag", "photo, no tag"
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class TrayOutline:
    """One tray found in the photo from its blue plastic (`find_outlines`), in full-size photo
    pixels."""

    corners: tuple[tuple[float, float], ...]  # four outside corners
    centre: tuple[float, float]
    tilt_deg: float
    edge: bool  # the blue piece it was cut from touches the photo's edge


def _tilt_deg(tag: TagDetection) -> float:
    """The tray's turn off the image axes, clockwise: the tag's heading off the nearest right
    angle, taking the tag to lie square in its cell. The corners run top-left, top-right,
    bottom-right, bottom-left in the tag's own frame."""
    return (_heading_deg(tag) + 45) % 90 - 45


def tray_outline_at(centre: tuple[float, float], tilt_deg: float, ppm: float) -> tuple[tuple[float, float], ...]:
    """A tray's four outside corners (`TRAY_SIZE_MM`) around `centre`, turned by `tilt_deg`, at
    `ppm` pixels per mm: how a tray placed from its tag was outlined."""
    t = math.radians(tilt_deg)
    half_w, half_h = TRAY_SIZE_MM[0] / 2 * ppm, TRAY_SIZE_MM[1] / 2 * ppm
    across, down = (math.cos(t), math.sin(t)), (-math.sin(t), math.cos(t))
    return tuple(
        (centre[0] + a * half_w * across[0] + b * half_h * down[0], centre[1] + a * half_w * across[1] + b * half_h * down[1])
        for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))
    )


def nearest_slot(x: float, y: float, slots: list[dict]) -> tuple[str, float]:
    """The name of the slot of `slots` (dicts with "name" and "centre") whose centre is nearest
    the point (x, y), and the distance to it, in pixels."""
    return min(((s["name"], math.hypot(s["centre"][0] - x, s["centre"][1] - y)) for s in slots), key=lambda s: s[1])


def place_trays(detections: list[TagDetection], scale_field: ScaleField, slots: list[dict]) -> list[TrayPlacement]:
    """Every tray tag in `detections` placed in a slot of `slots` (the calibration's slot layout,
    as `validation.slot_layout` gives it), in tag ID order."""
    out = []
    for tag in sorted(detections, key=lambda d: d.tag_id):
        if tag.tag_id not in TRAY_ID_RANGE:
            continue
        tilt = _tilt_deg(tag)
        ppm = scale_field.px_per_mm(*tag.centre)
        # The offset's frame in image pixels (y down): heading 180 turned by the tilt.
        t = math.radians(180 + tilt)
        right, up = (math.cos(t), math.sin(t)), (math.sin(t), -math.cos(t))
        dx = (A1_TAG_TO_CENTRE_MM[0] * right[0] + A1_TAG_TO_CENTRE_MM[1] * up[0]) * ppm
        dy = (A1_TAG_TO_CENTRE_MM[0] * right[1] + A1_TAG_TO_CENTRE_MM[1] * up[1]) * ppm
        candidates = []
        for corner, sign in (("SW", 1), ("NE", -1)):
            centre = (tag.centre[0] + sign * dx, tag.centre[1] + sign * dy)
            slot, distance = nearest_slot(*centre, slots)
            candidates.append((distance, corner, centre, slot))
        (near, corner, centre, slot), (far, *_) = sorted(candidates)
        margin = (far - near) / ppm
        out.append(TrayPlacement(
            tray_id=tag.tag_id, centre=centre, slot=slot, a1_corner=corner, tilt_deg=tilt,
            outline=tray_outline_at(centre, tilt, ppm), margin_mm=margin,
            status="close call" if margin < CLOSE_CALL_MM else "placed",
        ))
    per_slot = Counter(p.slot for p in out)
    return [replace(p, status="two trays in one slot") if per_slot[p.slot] > 1 else p for p in out]


def _inside(point: tuple[float, float], corners: tuple[tuple[float, float], ...]) -> bool:
    """Whether `point` lies inside the convex outline `corners` (either winding)."""
    signs = set()
    for (x0, y0), (x1, y1) in zip(corners, corners[1:] + corners[:1], strict=True):
        cross = (x1 - x0) * (point[1] - y0) - (y1 - y0) * (point[0] - x0)
        if cross:
            signs.add(cross > 0)
    return len(signs) < 2


def name_trays(outlines: list[TrayOutline], detections: list[TagDetection]) -> list[TrayPlacement]:
    """Each outline found in the photo named by the tray tag whose centre lies inside it, wherever
    the tag lies in the tray (#331): its place in the tray is never used. A tray tag inside no
    outline is reported where it lies, with no outline: the tray was not found in the photo (not
    blue, under a sheet), and a tray placed from the tag assumed it lay in cell A1, putting edge
    tags and second tags about 176 mm off (#331). Trays can lie anywhere on the table: no slot."""
    tags = [t for t in detections if t.tag_id in TRAY_ID_RANGE]
    # Accepted outlines may overlap a little (`MAX_OVERLAP`): a tag in the strip two share names
    # only the one whose centre is nearer, never both (review of #334).
    home: dict[int, int] = {}
    for k, tag in enumerate(tags):
        holding = [i for i, o in enumerate(outlines) if _inside(tag.centre, o.corners)]
        if holding:
            home[k] = min(holding, key=lambda i: math.dist(tag.centre, outlines[i].centre))
    out = []
    for i, outline in enumerate(outlines):
        named = [t for k, t in enumerate(tags) if home.get(k) == i]
        edge = ("partly outside the photo",) if outline.edge else ()
        if not named:
            out.append(TrayPlacement(
                tray_id=None, centre=outline.centre, slot=None, a1_corner=None, tilt_deg=outline.tilt_deg,
                outline=outline.corners, margin_mm=None, found="photo, no tag", warnings=("no tag", *edge),
            ))
        # A merge the cut did not split, or two tags on one tray: both trays keep the outline.
        shared = len(named) > 1
        warnings = (*(("two tags in one tray outline",) if shared else ()), *edge)
        for tag in named:
            out.append(TrayPlacement(
                tray_id=tag.tag_id, centre=outline.centre, slot=None, a1_corner=None, tilt_deg=outline.tilt_deg,
                outline=outline.corners, margin_mm=None, status="two tags in one outline" if shared else "placed",
                found="photo + tag", warnings=warnings,
            ))
    for k, tag in enumerate(tags):
        if k not in home:
            out.append(TrayPlacement(
                tray_id=tag.tag_id, centre=tag.centre, slot=None, a1_corner=None, tilt_deg=_tilt_deg(tag),
                outline=None, margin_mm=None, found="tag only", warnings=("tag seen, tray not found in the photo",),
            ))
    return out


# --- Found in the photo: the blue finder (#331) ------------------------------------------------
# Parameters of `find_photo_only` in experiments/round3-tray-outlines/methods_blue.py, frozen
# before the held-out test (commit 49c868e, metrology log 20.1), tuned on quarter-size stills.

# Tray plastic, HSV in OpenCV's ranges. Sampled on both rigs: hue 103 to 119 (1st to 99th
# percentile), saturation 5th percentile 106 to 134. Table and white paper: saturation under 50;
# soil, paper shadows and the yellow card hue 0 to 30; plants and green squares hue 35 to 80.
BLUE_HUE = (95, 130)
BLUE_SAT_MIN = 90
BLUE_VALUE_MIN = 50  # every blue pixel, shaded walls included
# The lit top rim: blue pixels brighter than this times the photo's 75th percentile of blue value,
# so it follows exposure. The rim faces the lights (value 140 to 200); shaded side walls, lower
# stacked trays and crate rims are darker (60 to 110). Scored the same from 0.60 to 0.70, lost
# trays at 0.80.
RIM_VALUE_REL = 0.65
# Pieces under this share of one tray's area are noise (a broken thin rim piece is about 1%).
MIN_PIECE = 0.003
# Two pieces merge when together they fit one tray with this slack (a leaf or a sheet across a rim
# splits a tray; a development tray with its crate needs 1.09), unless both are a whole tray
# (hull over 85% of a tray).
MERGE_SLACK = 1.12
WHOLE_TRAY = 0.85
# A hull under this share of a tray's area, or narrower than this share of its short side, is not
# a tray (blue bits of the ceiling, strips of lower trays).
MIN_TRAY_AREA = 0.4
MIN_TRAY_WIDTH = 0.6
# A cell lying more than this share on a cell already accepted (from a bigger piece) is dropped:
# fragments of two touching trays merged into a false tray.
MAX_OVERLAP = 0.25


def _blue_rim(image: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    h, s, v = cv2.split(hsv)
    loose = (h >= BLUE_HUE[0]) & (h <= BLUE_HUE[1]) & (s >= BLUE_SAT_MIN) & (v >= BLUE_VALUE_MIN)
    if not loose.any():
        return np.zeros(h.shape, np.uint8)
    rim = (loose & (v >= RIM_VALUE_REL * np.percentile(v[loose], 75))).astype(np.uint8)
    return cv2.morphologyEx(rim, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))


def _fill_holes(piece: np.ndarray) -> np.ndarray:
    flood = np.pad(piece, 1).copy()
    cv2.floodFill(flood, np.zeros((flood.shape[0] + 2, flood.shape[1] + 2), np.uint8), (0, 0), 1)
    return piece | (flood[1:-1, 1:-1] == 0).astype(np.uint8)


def _tray_px(hull: np.ndarray, scale_field: ScaleField, factor: float) -> tuple[float, float]:
    """A tray's short and long side in image pixels at the scale where `hull` lies."""
    cx, cy = hull.mean(axis=0)
    ppm = scale_field.px_per_mm(cx * factor, cy * factor) / factor
    return TRAY_SIZE_MM[0] * ppm, TRAY_SIZE_MM[1] * ppm


def _fits_one_tray(hull: np.ndarray, short: float, long: float, slack: float) -> bool:
    w, h = sorted(cv2.minAreaRect(hull.astype(np.float32))[1])
    return w <= short * slack and h <= long * slack


def _cells(hull: np.ndarray, short: float, long: float, shape: tuple[int, int]) -> tuple[list[np.ndarray], bool]:
    """`hull` cut into tray cells of the known size: its minimum-area rectangle, trays along each
    axis = round(extent / tray size) for the orientation that fits best. Along each axis the cells
    are centred on the hull, or aligned away from a frame edge the hull touches (the tray there
    may reach past the photo). Also whether the hull touches the frame edge."""
    (_cx, _cy), (w, h), angle = cv2.minAreaRect(hull.astype(np.float32))
    best = None
    for tu, tv in ((short, long), (long, short)):
        nu, nv = max(1, round(w / tu)), max(1, round(h / tv))
        err = abs(w - nu * tu) / tu + abs(h - nv * tv) / tv
        if best is None or err < best[0]:
            best = (err, nu, nv, tu, tv)
    _err, nu, nv, tu, tv = best
    t = math.radians(angle)
    u, v = np.array([math.cos(t), math.sin(t)]), np.array([-math.sin(t), math.cos(t)])
    height, width = shape
    border = (hull[:, 0] <= 2) | (hull[:, 1] <= 2) | (hull[:, 0] >= width - 3) | (hull[:, 1] >= height - 3)

    def start(p: np.ndarray, n: int, size: float) -> float:
        lo, hi = p.min(), p.max()
        at_lo, at_hi = bool(np.any(border & (p <= lo + 4))), bool(np.any(border & (p >= hi - 4)))
        if at_lo and not at_hi:
            return hi - n * size / 2
        if at_hi and not at_lo:
            return lo + n * size / 2
        return (lo + hi) / 2

    cu, cv_ = start(hull @ u, nu, tu), start(hull @ v, nv, tv)
    cells = []
    for i in range(nu):
        for j in range(nv):
            c = u * (cu + (i - (nu - 1) / 2) * tu) + v * (cv_ + (j - (nv - 1) / 2) * tv)
            cells.append(np.array([c + a * u * tu / 2 + b * v * tv / 2 for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]))
    return cells, bool(border.any())


def _tray_outline(cell: np.ndarray, factor: float, edge: bool) -> TrayOutline:
    """A cell in image pixels as a TrayOutline in full-size pixels: corners clockwise on the photo
    from the one nearest its top-left, tilt the turn of its sides off the image axes."""
    full = cell * factor
    centre = full.mean(axis=0)
    order = np.argsort(np.arctan2(full[:, 1] - centre[1], full[:, 0] - centre[0]))
    full = full[order]
    first = int(np.argmin(full.sum(axis=1)))
    full = np.roll(full, -first, axis=0)
    dx, dy = full[1] - full[0]
    tilt = (math.degrees(math.atan2(dy, dx)) + 45) % 90 - 45
    return TrayOutline(
        corners=tuple((float(x), float(y)) for x, y in full), centre=(float(centre[0]), float(centre[1])),
        tilt_deg=tilt, edge=edge,
    )


def find_outlines(image: np.ndarray, scale_field: ScaleField, factor: float) -> list[TrayOutline]:
    """Every tray in `image` (RGB, `factor` times smaller than the full-size photo; the parameters
    were tuned at 4) found from its blue plastic, as outlines in full-size photo pixels. Tags are
    not used. Every tray is taken to be 305 x 366 mm (`TRAY_SIZE_MM`), at the calibration's scale
    where it lies."""
    rim = _blue_rim(image)
    n, labels, stats, _centres = cv2.connectedComponentsWithStats(rim, connectivity=8)
    pieces = []
    for k in range(1, n):
        x, y, w, h, area = stats[k]
        piece = _fill_holes((labels[y:y + h, x:x + w] == k).astype(np.uint8))
        contours, _ = cv2.findContours(piece, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        hull = cv2.convexHull(max(contours, key=cv2.contourArea) + np.array([x, y])).reshape(-1, 2).astype(float)
        short, long = _tray_px(hull, scale_field, factor)
        if area >= MIN_PIECE * short * long:
            pieces.append(hull)
    merged = True
    while merged:
        merged = False
        for i in range(len(pieces)):
            for j in range(i + 1, len(pieces)):
                a, b = pieces[i], pieces[j]
                joint = cv2.convexHull(np.vstack([a, b]).astype(np.float32)).reshape(-1, 2).astype(float)
                short, long = _tray_px(joint, scale_field, factor)
                whole = [cv2.contourArea(p.astype(np.float32)) > WHOLE_TRAY * short * long for p in (a, b)]
                if not all(whole) and _fits_one_tray(joint, short, long, MERGE_SLACK):
                    pieces[i] = joint
                    del pieces[j]
                    merged = True
                    break
            if merged:
                break
    accepted: list[np.ndarray] = []
    out = []
    for hull in sorted(pieces, key=lambda p: -cv2.contourArea(p.astype(np.float32))):
        short, long = _tray_px(hull, scale_field, factor)
        if cv2.contourArea(hull.astype(np.float32)) < MIN_TRAY_AREA * short * long:
            continue
        if min(cv2.minAreaRect(hull.astype(np.float32))[1]) < MIN_TRAY_WIDTH * short:
            continue
        cells, edge = _cells(hull, short, long, rim.shape)
        for cell in cells:
            c = cell.astype(np.float32)
            if any(cv2.intersectConvexConvex(c, a)[0] > MAX_OVERLAP * cv2.contourArea(c) for a in accepted):
                continue
            accepted.append(c)
            out.append(_tray_outline(cell, factor, edge))
    return out


# --- Cells placed from the tray's outline and tag (#364) ----------------------------------------


@dataclass(frozen=True)
class CellGrid:
    """Where a tray type's cells lie, mm, the grid centred in the tray. `pitch_mm` is the distance
    between cell centres (across the short side, along the long side); `opening_mm` the side of
    the square a cell shows from above."""

    columns: int
    rows: int
    pitch_mm: tuple[float, float]
    opening_mm: float
    tag_cell: str | None  # the cell the tray tag lies in, which holds no plant


CELL_GRIDS = {
    # reference/trays.md: opening 59.5 mm (callipers), walls 10.1 to 10.3 mm, so centres 69.7 mm
    # apart (59.5 + 10.2). The tag lies in A1, which holds no plant (Aaron, 2026-10-21).
    "4x5": CellGrid(columns=4, rows=5, pitch_mm=(69.7, 69.7), opening_mm=59.5, tag_cell="A1"),
    # Aaron, 2026-11-06: holes 106 mm (tape measure), central divisions 32 mm across the short side
    # and 58.5 mm along the long side, so centres 138 and 164.5 mm apart, the grid taken to be
    # centred in the tray (a decision, as on the 4 x 5). From above a cell shows its pot's rim,
    # 108.93 mm (callipers, mean of 4: 108.83 to 109.18). The tag lies in the middle, on no cell.
    "2x2": CellGrid(columns=2, rows=2, pitch_mm=(138.0, 164.5), opening_mm=108.93, tag_cell=None),
}


@dataclass(frozen=True)
class Cell:
    """One cell of a tray, in full-size photo pixels: its name ("B3"), centre, the four corners of
    the square it shows from above, and what it holds: "plant", or "tag" for the tag's cell."""

    name: str
    centre: tuple[float, float]
    corners: tuple[tuple[float, float], ...]
    holds: str


def _heading_deg(tag: TagDetection) -> float:
    """Which way the tag's top faces on the photo, degrees clockwise from north (up). The corners
    run top-left, top-right, bottom-right, bottom-left in the tag's own frame (OpenCV's ArUco
    order; on a printed tag the ID is engraved at its top corners)."""
    c = tag.corners
    up_x = (c[0][0] + c[1][0] - c[2][0] - c[3][0]) / 2
    up_y = (c[0][1] + c[1][1] - c[2][1] - c[3][1]) / 2
    return math.degrees(math.atan2(up_x, -up_y))


def a1_bearing_deg(tray: TrayPlacement, tag: TagDetection, cells: list[Cell]) -> float:
    """Where cell A1 of `cells` lies from the tray's centre, degrees clockwise from the top of the
    tray's tag. Taken from a 2 x 2 tray's first photo (`place_cells` with no bearing) and given to
    `place_cells` for every later photo: the tag is glued at whatever angle the researcher left it
    (Aaron, 2026-11-06) but turns with the tray, so A1 keeps its bearing from it."""
    a1 = next(c for c in cells if c.name == "A1")
    centre = np.asarray(tray.outline, dtype=np.float64).mean(axis=0)
    dx, dy = a1.centre[0] - centre[0], a1.centre[1] - centre[1]
    return (math.degrees(math.atan2(dx, -dy)) - _heading_deg(tag)) % 360


def place_cells(
    tray: TrayPlacement, tag: TagDetection, scale_field: ScaleField, a1_bearing_deg: float | None = None
) -> list[Cell]:
    """The cells of `tray` (named by `tag`, an outline found in the photo), placed around the
    outline's centre along its sides, at the scale at that centre (it changes by about 0.5% across
    a tray). Columns run across the tray's short side, rows along its long side, from cell A1. A
    4 x 5 tray's A1 is the corner nearest its tag. A 2 x 2 tray's tag lies in the middle at any
    angle: in the tray's first photo A1 is the pot at the photo's south-west, and in every later
    photo the pot at `a1_bearing_deg` from the tag (`a1_bearing_deg()` of the first photo), so the
    names follow the tray when it is turned (Aaron, 2026-11-06). Only the outline's centre and turn are used:
    its length reads about 2% long north-south (reference/trays.md). Empty for a tray with no
    outline, or of a type whose cells are not measured (1 x 1, black, other)."""
    from npec_rig.randomization import tray_type  # randomization imports this module

    grid = CELL_GRIDS.get(tray_type(tray.tray_id).name) if tray.tray_id is not None else None
    if grid is None or tray.outline is None:
        return []
    corners = np.asarray(tray.outline, dtype=np.float64)
    centre = corners.mean(axis=0)
    first, second = corners[1] - corners[0], corners[2] - corners[1]
    across, along = sorted((first, second), key=lambda s: float(np.linalg.norm(s)))
    across, along = across / np.linalg.norm(across), along / np.linalg.norm(along)
    if grid.tag_cell == "A1":
        # From A1 outwards: away from the side the tag lies on.
        to_tag = np.asarray(tag.centre) - centre
        across = -across if np.dot(to_tag, across) > 0 else across
        along = -along if np.dot(to_tag, along) > 0 else along
    elif a1_bearing_deg is not None:
        # A1 on the side the bearing from the tag's top points to.
        t = math.radians(_heading_deg(tag) + a1_bearing_deg)
        to_a1 = np.array([math.sin(t), -math.cos(t)])
        across = -across if np.dot(to_a1, across) > 0 else across
        along = -along if np.dot(to_a1, along) > 0 else along
    else:
        # The tray's first photo: A1 is the cell nearest the photo's south-west diagonal (y grows
        # southwards), whichever way the tray lies: a per-axis sign test flips on a fraction of a
        # degree when the tray lies landscape (review of #374).
        to_sw = np.array([-1.0, 1.0])
        across = -across if np.dot(to_sw, across) > 0 else across
        along = -along if np.dot(to_sw, along) > 0 else along
    ppm = scale_field.px_per_mm(float(centre[0]), float(centre[1]))
    half = grid.opening_mm / 2 * ppm
    out = []
    for i in range(grid.columns):
        for j in range(grid.rows):
            c = (
                centre
                + across * (i - (grid.columns - 1) / 2) * grid.pitch_mm[0] * ppm
                + along * (j - (grid.rows - 1) / 2) * grid.pitch_mm[1] * ppm
            )
            square = tuple(
                (float(x), float(y))
                for x, y in (c + a * half * across + b * half * along for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1)))
            )
            name = f"{'ABCDEFGH'[i]}{j + 1}"
            out.append(Cell(name, (float(c[0]), float(c[1])), square, "tag" if name == grid.tag_cell else "plant"))
    return out
