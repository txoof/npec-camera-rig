"""Plant masks: which pixels of a photo are plant (#74, PLAN.md M5).

Every segmenter takes an RGB image (channels R, G, B in that order, as `images.reduced_frame`
gives) and returns a boolean mask of the same height and width, True where it sees plant. Code
that turns masks into areas depends only on that, so a model can replace the green threshold
without changes elsewhere.
"""

import math
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image

# Normalised excess green (2g - r - b) / (r + g + b) above which a pixel is plant, with green
# above red so yellow does not pass. Carried over from round 1 (experiments/round1-benchy, metrology
# log 15.6a), where it took flat leaves on blue trays within 10% of their scanned area, 27 of 27.
# A choice that worked, not a measured optimum.
EXG_MIN = 0.1


class Segmenter(Protocol):
    name: str  # what made a mask, stored with every area: "green threshold, 0.1"

    def segment(self, rgb: np.ndarray) -> np.ndarray:
        """True where `rgb` (H x W x 3, R G B) shows plant, as an H x W boolean array."""
        ...


class ExGSegmenter:
    """Excess-green threshold. No model: the permanent baseline any model has to beat."""

    def __init__(self, exg_min: float = EXG_MIN) -> None:
        self.exg_min = exg_min
        self.name = f"green threshold, {exg_min:g}"

    def segment(self, rgb: np.ndarray) -> np.ndarray:
        # In strips of rows: a 64MP photo at once would need about 1 GB of working arrays.
        mask = np.empty(rgb.shape[:2], dtype=bool)
        for top in range(0, rgb.shape[0], _STRIP_ROWS):
            r, g, b = (rgb[top : top + _STRIP_ROWS, :, i].astype(np.float32) for i in range(3))
            exg = (2 * g - r - b) / (r + g + b + 1e-6)
            mask[top : top + _STRIP_ROWS] = (exg > self.exg_min) & (g > r)
        return mask


_STRIP_ROWS = 512


class SegmenterUnavailable(RuntimeError):
    """The segmenter cannot run on this rig."""


class HailoSegmenter:
    """A model on the Hailo-8, behind the same call as the green threshold. A stub: no model is
    chosen yet, and one is adopted only if it beats `ExGSegmenter` by a margin Aaron sets first
    (PLAN.md, Rounds)."""

    name = "Hailo model"

    def segment(self, rgb: np.ndarray) -> np.ndarray:
        raise SegmenterUnavailable("no Hailo segmentation model is installed; use the green threshold")


# --- Grow from leaf cores (#363) -------------------------------------------------------------------
# One tray at a time, beside the green threshold: leaf cores grown out into the paler leaf edges, down
# to a cutoff set above the tray's own soil (metrology log 24.8 and 33.1, reference implementation
# experiments/round3-classifier/code/ruleg402.py, its "H"). Every setting below was chosen in those
# investigations, not tuned here; the tuning study of metrology log 34 may change them.

GROWN_METHOD = "grow from leaf cores"
GROWN_CORE_MIN = 0.1  # greenness above which, with green above red, a pixel is a leaf core
GROWN_GAP = 0.07  # the lower cutoff lies this far above the tray's soil level
GROWN_FLOOR = -0.045  # and never below this
GROWN_SOIL_BIN = 0.01  # the soil level is the peak of the greenness histogram in bins this wide,
GROWN_SOIL_SMOOTH_TAPS = 13  # smoothed with a Gaussian of this many taps,
GROWN_SOIL_SMOOTH_SIGMA_BINS = 2.0  # this wide in bins,
GROWN_SOIL_MAX = 0.05  # taken over bin centres below this
GROWN_BLUE_MARGIN = 0  # blue plastic: blue above red and green by more than this (0 to 255 values)
GROWN_TAG_ENLARGE = 1.6  # the tray tag's square, enlarged this many times about its centre, is no plant
GROWN_WHITE_MIN = 140  # white paper: every channel above this,
GROWN_WHITE_SPREAD = 25  # channels within this of each other,
GROWN_WHITE_MIN_PX = 5000  # in pieces of at least this many pixels,
GROWN_WHITE_WIDEN_PX = 61  # widened by a square this many pixels wide, is no plant


@dataclass(frozen=True)
class GrownPlant:
    """One tray box's plant by `grow_from_cores`: the mask, the soil level found and the lower
    cutoff used (soil level None: no soil to find it from, the floor is used)."""

    mask: np.ndarray
    soil_level: float | None
    lower_cutoff: float


def grow_from_cores(rgb: np.ndarray, inside: np.ndarray, tag_corners=(), lower_cutoff: float | None = None) -> GrownPlant:
    """The plant in one tray box `rgb` (H x W x 3, R G B), counted only where `inside` (H x W, the
    tray outline) is True and away from the tray tag (`tag_corners`: each detection's four corners,
    in the box's pixels) and white paper. Pieces of pixels greener than the lower cutoff (joined
    side or corner, never through blue) count when they hold a leaf core. The lower cutoff is set
    from the soil level, the commonest greenness inside the tray below GROWN_SOIL_MAX, unless
    given."""
    import cv2

    r, g, b = (rgb[..., i].astype(np.float32) for i in range(3))
    exg = (2 * g - r - b) / (r + g + b + 1e-6)
    notblue = ~((b > r + GROWN_BLUE_MARGIN) & (b > g + GROWN_BLUE_MARGIN))
    core = (exg > GROWN_CORE_MIN) & (g > r)
    lo, hi = np.minimum(np.minimum(r, g), b), np.maximum(np.maximum(r, g), b)
    del r, g, b
    white = ((lo > GROWN_WHITE_MIN) & (hi - lo < GROWN_WHITE_SPREAD)).astype(np.uint8)
    del lo, hi
    _n, labels, stats, _ = cv2.connectedComponentsWithStats(white, connectivity=8)
    big = np.flatnonzero(stats[:, cv2.CC_STAT_AREA] >= GROWN_WHITE_MIN_PX)
    no_plant = cv2.dilate(np.isin(labels, big[big > 0]).astype(np.uint8), np.ones((GROWN_WHITE_WIDEN_PX,) * 2, np.uint8))
    del white, labels
    for corners in tag_corners:
        c = np.asarray(corners, dtype=np.float64)
        centre = c.mean(axis=0)
        cv2.fillPoly(no_plant, [np.round(centre + GROWN_TAG_ENLARGE * (c - centre)).astype(np.int32).reshape(-1, 1, 2)], 1)
    sel = inside & (no_plant == 0)
    del no_plant
    soil_level = _soil_level(exg[sel & notblue])
    if lower_cutoff is None:
        lower_cutoff = GROWN_FLOOR if soil_level is None else max(GROWN_FLOOR, soil_level + GROWN_GAP)
    low = ((exg > lower_cutoff) & notblue & sel).astype(np.uint8)
    del exg, notblue
    n, labels = cv2.connectedComponents(low, connectivity=8, ltype=cv2.CV_32S)
    keep = np.zeros(n, dtype=bool)
    keep[np.unique(labels[core & sel])] = True
    keep[0] = False
    return GrownPlant(keep[labels], soil_level, float(lower_cutoff))


def grow_trays(rgb: np.ndarray, trays) -> tuple[np.ndarray, list[tuple[float | None, float | None]]]:
    """`grow_from_cores` for each tray of full-size photo `rgb`, tray box by tray box: `trays` as
    (outline, tag corners) pairs in full-size pixels, the tag corners a list of each tray tag's
    four corners. The whole photo's mask, each tray's plant within its outline (touching trays'
    plant in one mask, counted once by `measure_trays`), and each tray's soil level and lower
    cutoff, in their order; (None, None) for a tray outside the photo."""
    mask = np.zeros(rgb.shape[:2], dtype=bool)
    levels = []
    for outline, tag_corners in trays:
        box = _box(mask, outline)
        if box is None:
            levels.append((None, None))
            continue
        x0, y0, x1, y1 = box
        own = [np.asarray(c, dtype=np.float64) - [x0, y0] for c in tag_corners]
        grown = grow_from_cores(rgb[y0:y1, x0:x1], _inside(box, outline), own)
        mask[y0:y1, x0:x1] |= grown.mask
        levels.append((grown.soil_level, grown.lower_cutoff))
    return mask, levels


def _soil_level(exg: np.ndarray) -> float | None:
    """The centre of the smoothed greenness histogram's highest bin below GROWN_SOIL_MAX."""
    if exg.size == 0:
        return None
    edges = np.arange(-0.5, 0.5 + GROWN_SOIL_BIN / 100, GROWN_SOIL_BIN)
    counts, _ = np.histogram(exg, bins=edges)
    half = GROWN_SOIL_SMOOTH_TAPS // 2
    kernel = np.exp(-0.5 * (np.arange(-half, half + 1) / GROWN_SOIL_SMOOTH_SIGMA_BINS) ** 2)
    smooth = np.convolve(counts.astype(float), kernel / kernel.sum(), mode="same")
    centres = (edges[:-1] + edges[1:]) / 2
    below = centres < GROWN_SOIL_MAX
    return float(centres[below][np.argmax(smooth[below])])


# --- Plant area from a mask ------------------------------------------------------------------------

# Side of the square blocks the scale is looked up in, in full-size pixels. The scale field is a
# fitted plane, smooth over thousands of pixels: across one 64 px block it changes by about
# 0.01% (worked out from the fitted coefficients of the calibration of 14 October, not measured),
# far below the field's 0.5% residual.
_SCALE_BLOCK_PX = 64


@dataclass(frozen=True)
class PlantMeasure:
    """The plant inside one outline: the raw measurement and its area.

    `plant_px` and `centre_px` are the raw measurement (Aaron, 2026-10-23): with them any
    calibration can be applied later, `plant_px * mm_per_px(centre)**2`, close to the per-pixel
    sum: across a tray the scale changes by about 0.5%, and taking it at the centre differs from
    the per-pixel sum by less than that squared."""

    plant_px: int
    centre_px: tuple[float, float] | None  # None when no plant pixel is inside
    area_mm2: float


def measure_plant(mask: np.ndarray, outline_px, scale_field) -> PlantMeasure:
    """The plant pixels inside the polygon `outline_px` (full-size pixel corners, any number) of
    full-size `mask`: their count, centre, and area in mm2 with each pixel weighted by the local
    scale (`ScaleField.mm_per_px`) at its block. Parts of the outline outside the photo count
    nothing. Any outline: a tray now, a cell later."""
    box = _box(mask, outline_px)
    if box is None:
        return PlantMeasure(0, None, 0.0)
    return _measure(mask, box, _inside(box, outline_px), scale_field)


def measure_trays(mask: np.ndarray, trays, scale_field) -> list[PlantMeasure]:
    """`measure_plant` for every tray of one photo, `trays` as (outline, centre) pairs in full-size
    pixels, in their order. Where outlines overlap, a plant pixel counts only for the tray whose
    centre is nearer its pixel centre, so touching trays never count it twice (Aaron,
    2026-10-23); at the same distance, for the tray listed first. A pixel inside one outline only
    stays with that tray."""
    boxes = [_box(mask, outline) for outline, _centre in trays]
    out = []
    for i, ((outline, centre), box) in enumerate(zip(trays, boxes, strict=True)):
        if box is None:
            out.append(PlantMeasure(0, None, 0.0))
            continue
        inside = _inside(box, outline)
        for j, ((other, other_centre), other_box) in enumerate(zip(trays, boxes, strict=True)):
            shared = _overlap(box, other_box) if j != i and other_box is not None else None
            if shared is None:
                continue
            # Only the part of the box both trays cover: a strip for trays side by side.
            x0, y0, x1, y1 = shared
            xs = np.arange(x0, x1) + 0.5
            ys = (np.arange(y0, y1) + 0.5)[:, None]
            own = (xs - centre[0]) ** 2 + (ys - centre[1]) ** 2
            theirs = (xs - other_centre[0]) ** 2 + (ys - other_centre[1]) ** 2
            lose = (theirs < own) | ((theirs == own) & (j < i))
            part = inside[y0 - box[1] : y1 - box[1], x0 - box[0] : x1 - box[0]]
            part &= ~(_inside(shared, other) & lose)
        out.append(_measure(mask, box, inside, scale_field))
    return out


# A piece counted for one cell marks it and another cell "leaves over other cells" when it covers at
# least this fraction of the other cell's opening (#364, Aaron, 2026-11-06: say so, do not hide
# it). A decision, not a measurement: a leaf edge or a few fringe pixels reaching a neighbour's
# opening should not mark it. To be checked on real photos.
OVER_OTHER_CELL_MIN = 0.01


@dataclass(frozen=True)
class CellMeasure:
    """The plant counted for one cell (`measure_cells`), as `PlantMeasure`, and whether its area
    is not one plant's own: a piece counted for it covers another cell's opening, or a piece
    counted for another cell covers its own."""

    plant_px: int
    centre_px: tuple[float, float] | None
    area_mm2: float
    over_other_cells: bool


def measure_cells(mask: np.ndarray, cells, scale_field, outline_px=None) -> list[CellMeasure]:
    """The plant of each cell in `cells` (`tray_placement.Cell`, full-size pixels) of full-size
    `mask`, in their order (#364). A piece of plant (pixels joined side or corner) counts wholly
    for the cell holding most of its pixels, so a leaf hanging over a wall or a neighbouring cell
    stays with its own cell; at a tie, for the cell listed first. A piece with no pixel in any cell
    lies on the walls only (the fringe along the cells' edges, metrology log 24.1) and counts for
    none. With `outline_px` (the tray's outline, full-size pixels), only plant inside it counts: a
    neighbouring tray's plant reaching into a cell brings nothing from outside (review of #374), and
    the pieces are labelled over that one tray only. Seen from above, a leaf's own pot can be hidden: where a piece counted for one cell covers
    another cell's opening (`OVER_OTHER_CELL_MIN`), both cells say `over_other_cells`. Pieces are
    followed as far as half a cell's side beyond the outermost cells: a piece
    reaching farther counts only its part within that."""
    import cv2

    if not cells:
        return []
    h, w = mask.shape
    corners = np.asarray([c for cell in cells for c in cell.corners], dtype=np.float64)
    reach = max(math.dist(cell.corners[0], cell.corners[1]) for cell in cells) / 2
    x0, y0 = np.clip(np.floor(corners.min(axis=0) - reach).astype(int), 0, [w, h])
    x1, y1 = np.clip(np.ceil(corners.max(axis=0) + reach).astype(int) + 1, 0, [w, h])
    if x1 <= x0 or y1 <= y0:
        return [CellMeasure(0, None, 0.0, False) for _ in cells]
    plant = np.ascontiguousarray(mask[y0:y1, x0:x1], dtype=np.uint8)
    if outline_px is not None:
        within = np.zeros(plant.shape, dtype=np.uint8)
        corners = np.asarray(outline_px, dtype=np.float64)
        cv2.fillPoly(within, [np.round(corners - [x0, y0]).astype(np.int32).reshape(-1, 1, 2)], 1)
        plant &= within
    n, labels, stats, _ = cv2.connectedComponentsWithStats(plant, connectivity=8)
    # Each piece's pixels in each cell: rows pieces, columns cells.
    counts = np.zeros((n, len(cells)), dtype=np.int64)
    opening_px = np.zeros(len(cells), dtype=np.int64)
    for k, cell in enumerate(cells):
        box = _box(mask, cell.corners)
        if box is None:
            continue
        bx0, by0, bx1, by1 = box
        inside = _inside(box, cell.corners)
        part = labels[by0 - y0 : by1 - y0, bx0 - x0 : bx1 - x0][inside]
        counts[:, k] = np.bincount(part, minlength=n)
        opening_px[k] = int(inside.sum())
    counts[0] = 0  # label 0 is no plant
    held = counts.sum(axis=1) > 0
    owner = np.where(held, counts.argmax(axis=1), -1)
    over = np.zeros(len(cells), dtype=bool)
    for piece in np.flatnonzero(held):
        covered = counts[piece] >= np.maximum(1, OVER_OTHER_CELL_MIN * opening_px)
        covered[owner[piece]] = False
        if covered.any():
            over[covered] = True
            over[owner[piece]] = True
    out = []
    for k in range(len(cells)):
        pieces = np.flatnonzero(owner == k)
        if len(pieces) == 0:
            out.append(CellMeasure(0, None, 0.0, bool(over[k])))
            continue
        px0 = int(stats[pieces, cv2.CC_STAT_LEFT].min())
        py0 = int(stats[pieces, cv2.CC_STAT_TOP].min())
        px1 = int((stats[pieces, cv2.CC_STAT_LEFT] + stats[pieces, cv2.CC_STAT_WIDTH]).max())
        py1 = int((stats[pieces, cv2.CC_STAT_TOP] + stats[pieces, cv2.CC_STAT_HEIGHT]).max())
        own = np.isin(labels[py0:py1, px0:px1], pieces)
        m = _measure(mask, (x0 + px0, y0 + py0, x0 + px1, y0 + py1), own, scale_field)
        out.append(CellMeasure(m.plant_px, m.centre_px, m.area_mm2, bool(over[k])))
    return out


def _box(mask: np.ndarray, outline_px) -> tuple[int, int, int, int] | None:
    """The part of `mask` around `outline_px`, x0, y0, x1, y1, or None when it is outside."""
    h, w = mask.shape
    corners = np.asarray(outline_px, dtype=np.float64)
    x0, y0 = np.clip(np.floor(corners.min(axis=0)).astype(int), 0, [w, h])
    x1, y1 = np.clip(np.ceil(corners.max(axis=0)).astype(int) + 1, 0, [w, h])
    if x1 <= x0 or y1 <= y0:
        return None
    return int(x0), int(y0), int(x1), int(y1)


def _overlap(a, b) -> tuple[int, int, int, int] | None:
    """The box two boxes share, or None."""
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    return (x0, y0, x1, y1) if x0 < x1 and y0 < y1 else None


def _inside(box, outline_px) -> np.ndarray:
    """Which pixels of `box` lie inside the polygon `outline_px`."""
    import cv2

    x0, y0, x1, y1 = box
    inside = np.zeros((y1 - y0, x1 - x0), dtype=np.uint8)
    corners = np.asarray(outline_px, dtype=np.float64)
    cv2.fillPoly(inside, [np.round(corners - [x0, y0]).astype(np.int32).reshape(-1, 1, 2)], 1)
    return inside.astype(bool)


def _measure(mask: np.ndarray, box, inside: np.ndarray, scale_field) -> PlantMeasure:
    x0, y0, x1, y1 = box
    plant = mask[y0:y1, x0:x1] & inside
    ys, xs = np.nonzero(plant)
    if len(xs) == 0:
        return PlantMeasure(0, None, 0.0)
    area = 0.0
    for by in range(0, plant.shape[0], _SCALE_BLOCK_PX):
        for bx in range(0, plant.shape[1], _SCALE_BLOCK_PX):
            count = int(np.count_nonzero(plant[by : by + _SCALE_BLOCK_PX, bx : bx + _SCALE_BLOCK_PX]))
            if count:
                cx = x0 + bx + min(_SCALE_BLOCK_PX, plant.shape[1] - bx) / 2
                cy = y0 + by + min(_SCALE_BLOCK_PX, plant.shape[0] - by) / 2
                area += count * scale_field.mm_per_px(cx, cy) ** 2
    # Pixel centres: pixel (0, 0) covers 0 to 1, so its centre is 0.5.
    return PlantMeasure(len(xs), (float(xs.mean()) + x0 + 0.5, float(ys.mean()) + y0 + 0.5), area)


# --- Masks on disk ----------------------------------------------------------------------------------


def masks_root() -> Path:
    """Directory plant masks are kept under. Read at call time, so tests can redirect it. Not
    derived images: Reprocess recomputes areas from these, so they are kept with the photos."""
    return Path(os.environ.get("NPEC_RIG_MASKS_DIR", "/var/lib/npec-rig/masks"))


# The file name ending of the masks by grow from leaf cores, beside the fixed cutoff's (#363).
GROWN_MASK = ".grown"


def mask_file(photo_path: str, kind: str = "") -> Path:
    """Where the mask of gallery photo `photo_path` (as `rig/2026-10-23/083553_637710`) is kept:
    the segmenter's, or with `kind` GROWN_MASK the one by grow from leaf cores."""
    return masks_root() / f"{photo_path}{kind}.png"


def save_mask(photo_path: str, mask: np.ndarray, kind: str = "") -> Path:
    """Save `mask` as a 1-bit PNG beside any earlier one of the photo, replacing it."""
    target = mask_file(photo_path, kind)
    target.parent.mkdir(parents=True, exist_ok=True)
    # A name of its own per thread: the background reader and Show tags can save one photo's mask
    # at the same time, and a shared name lets one thread's rename take the other's file.
    partial = target.with_name(f"{target.name}.{os.getpid()}.{threading.get_ident()}.partial")
    Image.fromarray(mask).convert("1").save(partial, format="PNG", optimize=False)
    partial.replace(target)
    return target


def load_mask(photo_path: str, kind: str = "") -> np.ndarray | None:
    """The saved mask of photo `photo_path` (`mask_file`), or None when it has none."""
    try:
        with Image.open(mask_file(photo_path, kind)) as image:
            return np.asarray(image.convert("1"), dtype=bool)
    except FileNotFoundError:
        return None
