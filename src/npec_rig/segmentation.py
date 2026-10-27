"""Plant masks: which pixels of a photo are plant (#74, PLAN.md M5).

Every segmenter takes an RGB image (channels R, G, B in that order, as `images.reduced_frame`
gives) and returns a boolean mask of the same height and width, True where it sees plant. Code
that turns masks into areas depends only on that, so a model can replace the green threshold
without changes elsewhere.
"""

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
    2026-10-23). A pixel inside one outline only stays with that tray."""
    boxes = [_box(mask, outline) for outline, _centre in trays]
    out = []
    for i, ((outline, centre), box) in enumerate(zip(trays, boxes, strict=True)):
        if box is None:
            out.append(PlantMeasure(0, None, 0.0))
            continue
        inside = _inside(box, outline)
        x0, y0, x1, y1 = box
        xs = np.arange(x0, x1) + 0.5
        ys = (np.arange(y0, y1) + 0.5)[:, None]
        own = (xs - centre[0]) ** 2 + (ys - centre[1]) ** 2
        for j, ((other, other_centre), other_box) in enumerate(zip(trays, boxes, strict=True)):
            if j == i or other_box is None or not _overlap(box, other_box):
                continue
            nearer_other = (xs - other_centre[0]) ** 2 + (ys - other_centre[1]) ** 2 < own
            inside &= ~(_inside(box, other) & nearer_other)
        out.append(_measure(mask, box, inside, scale_field))
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


def _overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


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


def mask_file(photo_path: str) -> Path:
    """Where the mask of gallery photo `photo_path` (as `rig/2026-10-23/083553_637710`) is kept."""
    return masks_root() / f"{photo_path}.png"


def save_mask(photo_path: str, mask: np.ndarray) -> Path:
    """Save `mask` as a 1-bit PNG beside any earlier one of the photo, replacing it."""
    target = mask_file(photo_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # A name of its own per thread: the background reader and Show tags can save one photo's mask
    # at the same time, and a shared name lets one thread's rename take the other's file.
    partial = target.with_name(f"{target.name}.{os.getpid()}.{threading.get_ident()}.partial")
    Image.fromarray(mask).convert("1").save(partial, format="PNG", optimize=False)
    partial.replace(target)
    return target


def load_mask(photo_path: str) -> np.ndarray | None:
    """The saved mask of photo `photo_path`, or None when it has none."""
    try:
        with Image.open(mask_file(photo_path)) as image:
            return np.asarray(image.convert("1"), dtype=bool)
    except FileNotFoundError:
        return None
