"""Readings per tray per photo (#222): each photo read once for its trays, and the result saved in
`rig.db` (`database.record_tray_readings`).

A reading is the trays found in the photo from their blue plastic, each named by the tag inside
it, and each tray tag inside no outline seen where it lies, with no outline and no area
(`tray_placement.find_outlines`, `name_trays`, #331); no slot layout is needed. Each outlined tray
is read with the calibration the photo was taken under, and with its plant area:
the segmenter's mask of the full-size photo, saved to disk, summed inside the tray outline at the
local scale (#75). A tray not found is never stored: `database.tray_readings` works it out from
the experiment's earlier photos when the readings are shown.
"""

import json
import logging
import math
import os
import sqlite3
import threading
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PIL import Image

from npec_rig import database, dwell, exclusions, images, photo_tags, segmentation, validation_store
from npec_rig.captures import photo_file
from npec_rig.calibration_store import (
    CalibrationNotFoundError,
    CalibrationUnreadableError,
    calibration_for_photos,
    load_saved_calibration,
)
from npec_rig.tags import TRAY_ID_RANGE, TagDetection
from npec_rig.tray_placement import (
    TRAY_SIZE_MM,
    Cell,
    TrayOutline,
    TrayPlacement,
    find_outlines,
    name_trays,
    nearest_slot,
    a1_bearing_deg,
    place_cells,
    tag_on_tray,
    tray_outline_at,
)

logger = logging.getLogger(__name__)

# What makes each mask. One line to change for another segmenter: every area records its name.
SEGMENTER: segmentation.Segmenter = segmentation.ExGSegmenter()

# Each segmenter's floor, by its name: an area below it means nothing detected yet. Empty
# trays read up to 98 mm2 with the green threshold, mostly one light-blue mark per tray (metrology
# log 17.4). Reported with each area, never subtracted (Aaron). A decision (#288) on production's
# soil only. Grow from leaf cores has none: soil-only trays read at most 64 mm2 with it, on two
# soils (metrology log 42, #293).
FLOORS_MM2 = {"green threshold, 0.1": 100}

# Each segmenter's method in words, for the page beside grow from leaf cores (#363).
METHODS = {"green threshold, 0.1": "fixed green cutoff"}

# Each plant area method a reading can hold, for the Gallery's choice (#363, Aaron, 2026-11-11),
# in the order offered, the first the default. `stored`: the tray field set when the method was
# run; `area`, `cell_area`, `cell_status`: where its numbers are; `floor`: the tray field of its
# floor (#288), None without one. A new method is one more entry.
AREA_METHODS = (
    {"key": "grown", "name": "Grow from leaf cores", "stored": "grown_method", "area": "grown_area_mm2",
     "cell_area": "grown_area_mm2", "cell_status": "grown_status", "floor": None,
     "warning": "leaf edges on blue mats read a little small, and algae or green soil can count as plant."},
    {"key": "fixed", "name": "Fixed green cutoff", "stored": "segmenter", "area": "area_mm2",
     "cell_area": "area_mm2", "cell_status": "status", "floor": "floor_mm2",
     # Against hand outlines it counts 0.31 of the leaf area on average, 0.07 on the smallest
     # plants (metrology log 24, #352).
     "warning": "the fixed green cutoff reads low. It counts about a third of each leaf, and less on small plants."},
)

# How far a tray's outline may reach past the photo edge, mm, before its area is marked partly
# outside the photo: the widest measured outer wall, 11 to 13 mm (review of #281), where no plant
# grows. Trays 8 and 9 of the potato run reach 8.4 to 11.9 mm past at their farthest corner, and
# outlines are placed to within about 10 mm (metrology log 15.5l), so the mark is approximate. A
# decision, not a measurement (Aaron, 2026-10-27).
PAST_EDGE_MM = 13.0

# How plant pieces are given to cells (segmentation.measure_cells), stored with every cell's area
# so a change of rule shows in the data (#364).
CELL_RULE = "piece to the cell holding most of it, over other cells at 1%"

# The photo is searched for trays at this fraction of its size: the blue finder's parameters were
# tuned on quarter-size stills (metrology log 20).
FINDER_FACTOR = 4

# Seconds between looks for photos not yet read, when there are none. One reading took 9.6 s to
# 12.5 s (metrology log 15.5m), so a photo a minute leaves the reader idle most of the time.
POLL_S = 5.0

# A 2 x 2 tray's tag turned on its tray by more than this, from where it lay in the tray's first
# photo, marks the tray's cell names as maybe swapped from that photo on (#385). Tags that stayed
# put changed by up to 2.0 degrees, tray 81's moved tag by 83 (metrology log 32.2). A decision
# (Aaron, 2026-11-09), not a measurement: 5 times the largest change of a tag that stayed put.
TAG_TURNED_DEG = 10.0
TAG_TURNED = "tag turned on tray"
GROWN_NOT_WORKED_OUT = "grown area not worked out"
CELLS_NOT_WORKED_OUT = "cells not worked out"


def _calibration(record: dict) -> tuple[str, object, list[dict] | None]:
    """The photo's status so far ("read", or "no calibration", "no slot layout"), its
    calibration's scale field and its slot layout's slots, from the capture row `record` its
    caller has already read.

    The row used to be read again here, and a rig.db lock on that read was swallowed into "no
    calibration": the photo was saved for good as having no calibration and no trays, and was
    never offered for reading again (#564). The row is now read once, in `_read_photo`, where a
    lock raises and the caller reads the photo again (#439, #464, #483)."""
    if not record.get("calibration"):
        return "no calibration", None, None
    try:
        stem = calibration_for_photos(record["calibration"])
        artifact = load_saved_calibration(stem)
    except (CalibrationNotFoundError, CalibrationUnreadableError):
        return "no calibration", None, None
    try:
        # Only a layout already worked out: working it out decodes the 64MP calibration frame.
        # A twin has its original's slots. Optional: trays are found without one (review of #334).
        layout = validation_store.load_slot_layout(stem) or validation_store.load_slot_layout(record["calibration"])
    except validation_store.SessionNotFoundError:
        layout = None
    if layout is None:
        return "no slot layout", artifact.scale_field, None
    return "read", artifact.scale_field, layout["slots"]


def _small_copy(path: str) -> tuple[np.ndarray, float] | None:
    """Photo `path` decoded at about 1 / FINDER_FACTOR of its size (JPEG draft mode: the 64MP
    photo is never decoded whole for this), and how many times smaller it is; None when the
    photo is gone."""
    file = photo_file(path)
    if file is None:
        return None
    with Image.open(file) as image:
        width = image.size[0]
        image.draft("RGB", (image.size[0] // FINDER_FACTOR, image.size[1] // FINDER_FACTOR))
        small = np.asarray(image.convert("RGB"))
    return small, width / small.shape[1]


def _saved_outlines(saved: dict | None) -> list[TrayOutline]:
    """The outlines a saved reading found in the photo, once each (two tags may share one)."""
    out: dict[tuple, TrayOutline] = {}
    for tray in (saved or {}).get("trays", []):
        if tray.get("outline_px") and tray.get("found", "").startswith("photo"):
            corners = tuple(tuple(c) for c in tray["outline_px"])
            out[corners] = TrayOutline(
                corners=corners, centre=tuple(tray["centre_px"]), tilt_deg=tray["tilt_deg"],
                edge="partly outside the photo" in tray["warnings"],
            )
    return list(out.values())


def found_trays(
    path: str, tags: list[TagDetection], saved: dict | None = None, *, record: dict,
) -> tuple[str, list[TrayPlacement]]:
    """The trays of photo `path`: found in the photo from their blue plastic and named by the tag
    inside each, and each tray tag inside no outline seen where it lies, with the calibration the
    photo was taken under; no slot layout is needed (#331). The status: "read", "no calibration",
    "placement failed", or "no trays found" when the photo shows neither a tray nor a tag, as with
    the lights off. With the photo gone (Reprocess from its saved mask), the outlines of the saved
    reading `saved` are used again; with none saved, "photo not found". `record` is the photo's
    capture row, which the caller has read already (#564)."""
    status, scale_field, _slots = _calibration(record)
    if scale_field is None:
        return status, []
    try:
        small = _small_copy(path)
        if small is not None:
            outlines = find_outlines(small[0], scale_field, small[1])
        elif outlines := _saved_outlines(saved):
            pass
        else:
            return "photo not found", []
        # Only tray tags say anything about trays: a corner or calibration tag read in dim light
        # does not (review of #334).
        if not outlines and not any(t.tag_id in TRAY_ID_RANGE for t in tags):
            return "no trays found", []
        return "read", name_trays(outlines, tags)
    except (ValueError, KeyError, TypeError, OSError):
        logger.exception("Could not find the trays of %s", path)
        return "placement failed", []


def _capture_id(path: str) -> int:
    record = database.captures_by_path([path]).get(path)
    if record is None:
        raise LookupError(f"photo {path} has no record in rig.db")
    return record["id"]


def read_photo(path: str, *, reuse_mask: bool = False, unless_measured: bool = False) -> dict:
    """Read gallery photo `path` for its trays, save the reading (replacing any earlier one) and
    return it as `photo_readings` would. The tags are searched once per photo (photo_tags). With
    `reuse_mask`, Reprocess: the whole photo is done in one of two ways, never a mix of old and new
    values. Counted again from its saved masks (no photo and no segmenter needed) when
    `_recount_blocker` finds nothing against it; otherwise grown again from the photo as a new
    read; and when neither can be done completely (the photo is gone, anything fails) nothing is
    saved: the saved reading stays as it was and `NotReprocessed` is raised (#483). With
    `unless_measured`, a saved reading with plant areas from the same segmenter is kept and
    returned as it is: Show tags, which would otherwise segment the photo on every tap (#282)."""
    try:
        return _read_photo(path, reuse_mask=reuse_mask, unless_measured=unless_measured)
    finally:
        images.release_freed_memory()  # a full-size photo may have been decoded (#348)


def _read_photo(path: str, *, reuse_mask: bool, unless_measured: bool) -> dict:
    record = database.captures_by_path([path]).get(path)
    if record is None:
        raise LookupError(f"photo {path} has no record in rig.db")
    capture_id = record["id"]
    saved = database.tray_readings(capture_id)
    if unless_measured and _saved_by_this_segmenter(saved):
        return capture_readings(record)
    tags = photo_tags.photo_tags_for(path)
    status, placed = found_trays(path, tags, saved, record=record)
    # A tag seen with no tray found around it has no outline: nothing to measure (#331).
    outlined = [p for p in placed if p.outline is not None]
    recount = False
    if reuse_mask and outlined:
        blocker = _recount_blocker(path, saved, outlined)
        recount = blocker is None
        if blocker is not None and not (photo_file(path) or Path()).is_file():
            raise NotReprocessed(f"{path}: the photo is gone and its saved masks cannot be counted again: {blocker}")
    calibration, measures, cells, grown, new_masks = (
        _measures(path, record["calibration"], outlined, recount, tags, record, saved, strict=reuse_mask)
        if outlined else (None, [], [], [], None))
    size = _photo_size(path) if outlined else None
    # No area now, whether or not any tray was outlined (review of #334): a saved area is kept.
    _refuse_worse(path, saved, status, areas_lost=not measures)
    measured = dict(zip(map(id, outlined), measures, strict=True)) if measures else {}
    celled = dict(zip(map(id, outlined), cells, strict=True)) if measures else {}
    grew = dict(zip(map(id, outlined), grown, strict=True)) if grown else {}
    no_cells: tuple[list, None, bool, bool] = ([], None, False, False)
    trays = []
    for p in placed:
        m = measured.get(id(p))
        g, soil_level, lower_cutoff, blue_coverage = grew.get(id(p)) or (None, None, None, None)
        trays.append({
            "tray_id": p.tray_id, "slot": p.slot, "a1_corner": p.a1_corner, "placement": p.status,
            "centre_px": list(p.centre), "tilt_deg": p.tilt_deg, "margin_mm": p.margin_mm,
            "area_mm2": m.area_mm2 if m else None, "segmenter": SEGMENTER.name if m else None,
            "plant_px": m.plant_px if m else None,
            "plant_centre_px": list(m.centre_px) if m and m.centre_px else None,
            "calibration": calibration if m else None,
            "outside_mm": outside_mm(p, size) if size and p.outline is not None else None,
            "found": p.found,
            "warnings": list(p.warnings) + ([TAG_TURNED] if celled.get(id(p), no_cells)[2] else [])
            + ([segmentation.SOIL_HIDDEN] if g and _at_the_floor(soil_level, lower_cutoff) else [])
            + ([segmentation.SOIL_GREEN] if g and _soil_reads_green(soil_level, lower_cutoff) else [])
            + ([segmentation.SOIL_NOT_SEEN] if g and _no_soil_seen(soil_level, lower_cutoff) else [])
            + ([GROWN_NOT_WORKED_OUT] if m and not g else [])
            + ([CELLS_NOT_WORKED_OUT] if m and celled.get(id(p), no_cells)[3] else []),
            "outline_px": None if p.outline is None else [list(c) for c in p.outline],
            "cells": [
                {
                    "cell": c.name, "holds": c.holds, "centre_px": list(c.centre), "corners_px": [list(k) for k in c.corners],
                    "plant_px": cm.plant_px, "area_mm2": cm.area_mm2,
                    "plant_centre_px": list(cm.centre_px) if cm.centre_px else None,
                    "over_other_cells": cm.over_other_cells, "segmenter": SEGMENTER.name, "cell_rule": CELL_RULE,
                    "grown_plant_px": gm.plant_px if gm else None, "grown_area_mm2": gm.area_mm2 if gm else None,
                    "grown_plant_centre_px": list(gm.centre_px) if gm and gm.centre_px else None,
                    "grown_over_other_cells": gm.over_other_cells if gm else None,
                }
                for c, cm, gm in celled.get(id(p), no_cells)[0]
            ],
            "a1_bearing_deg": celled.get(id(p), no_cells)[1],
            "grown_method": segmentation.GROWN_METHOD if g else None,
            "grown_area_mm2": g.area_mm2 if g else None, "grown_plant_px": g.plant_px if g else None,
            "grown_plant_centre_px": list(g.centre_px) if g and g.centre_px else None,
            "grown_soil_level": soil_level, "grown_lower_cutoff": lower_cutoff,
            "grown_blue_coverage": blue_coverage,
        })
    _commit(path, record, capture_id, status, trays, new_masks)
    return capture_readings(record)


# One commit at a time: the background reader, Reprocess and Show tags may read one photo together.
_commit_lock = threading.Lock()


def _commit(path: str, record: dict, capture_id: int, status: str, trays: list[dict], new_masks) -> None:
    """Save a reading and, for a photo grown from the photo, its new masks, so that a failure or a
    kill at any point never leaves masks that belong to another reading (#483). In this order:
    (1) the new masks are written to `.staged` files; (2) both old masks are deleted; (3) the
    reading is saved; (4) the staged files are renamed to their places. A failure after (2) leaves
    "a saved mask is missing", which blocks a recount (`_recount_blocker`): the next Reprocess
    grows the photo again, or, with the photo gone, changes nothing. A failure at (3) is raised
    (a locked rig.db is retried by the caller); one at (4) is logged only: the reading is saved and
    masks that are missing force a regrow. A recount (no new masks) leaves the masks as they are."""
    with _commit_lock:
        staged = _stage_masks(path, new_masks)
        try:
            if new_masks is not None:
                for kind in ("", segmentation.GROWN_MASK):
                    segmentation.mask_file(path, kind).unlink(missing_ok=True)
            database.record_tray_readings(capture_id, read_at=datetime.now(UTC).isoformat(), status=status, trays=trays)
        except BaseException:
            for partial, _target in staged:
                partial.unlink(missing_ok=True)
            raise
        try:
            for partial, target in staged:
                partial.replace(target)
        except OSError:
            logger.exception("Could not put the new masks of %s in place; they are left out", path)
            for partial, target in staged:
                partial.unlink(missing_ok=True)
                target.unlink(missing_ok=True)
    exclusions.update(record)


# A `.staged` file older than this is left by a kill and is removed. A decision, not a measurement:
# a commit takes seconds (rig.db waits at most settings.LOCK_WAIT_S), so no reading in progress,
# in this process or another, has one this old.
STAGED_MAX_AGE_S = 3600.0


def _sweep_staged_masks() -> None:
    """Remove the `.staged` mask files (`_commit`) older than STAGED_MAX_AGE_S that a kill left."""
    try:
        old = time.time() - STAGED_MAX_AGE_S
        for f in segmentation.masks_root().rglob("*.staged"):
            try:
                if f.stat().st_mtime < old:
                    f.unlink(missing_ok=True)
            except OSError:
                logger.exception("Could not remove the leftover temporary mask file %s", f)
    except OSError:
        logger.exception("Could not look for leftover temporary mask files")


def _stage_masks(path: str, masks: tuple[np.ndarray, np.ndarray | None] | None) -> list[tuple[Path, Path]]:
    """Write a photo's new masks (the fixed cutoff's, and grow from leaf cores' when it worked) to
    temporary files beside their places: (temporary, place) pairs, renamed by the caller."""
    staged: list[tuple[Path, Path]] = []
    try:
        for kind, mask in zip(("", segmentation.GROWN_MASK), masks or (), strict=False):
            if mask is None:
                continue
            target = segmentation.mask_file(path, kind)
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_name(f"{target.name}.{os.getpid()}.{threading.get_ident()}.staged")
            Image.fromarray(mask).convert("1").save(partial, format="PNG", optimize=False)
            staged.append((partial, target))
    except BaseException:
        for partial, _target in staged:
            partial.unlink(missing_ok=True)
        raise
    return staged


class NotReprocessed(RuntimeError):
    """Reprocess could not redo the photo completely: nothing is saved, the saved reading stays as
    it was. The message says why."""


class ReadingWorse(NotReprocessed):
    """Reading the photo again would replace a saved reading with less: nothing is saved."""


def _refuse_worse(path: str, saved: dict | None, status: str, *, areas_lost: bool) -> None:
    """Raise ReadingWorse when a saved reading had trays placed, or areas, and this one has not:
    the photo, its mask or its calibration may be gone, and the saved values are kept (review of
    #287: Reprocess and Show tags must never turn saved areas into none)."""
    if not saved or saved["status"] != "read":
        return
    if status != "read":
        raise ReadingWorse(f"{path}: read as {status!r} now, kept the saved reading")
    if areas_lost and any(t["area_mm2"] is not None for t in saved["trays"]):
        raise ReadingWorse(f"{path}: plant areas could not be worked out now, kept the saved ones")


def _saved_by_this_segmenter(saved: dict | None) -> bool:
    """Whether the photo's saved reading, and so its saved mask, came from `SEGMENTER`."""
    return bool(saved) and any(t["segmenter"] == SEGMENTER.name for t in saved["trays"])


def _measures(
    path: str, photo_calibration: str, placed: list[TrayPlacement], recount: bool = False,
    tags: list[TagDetection] = (), record: dict | None = None, saved: dict | None = None, strict: bool = False,
) -> tuple[str | None, list[segmentation.PlantMeasure], list, list, tuple | None]:
    """The calibration used, each placed tray's plant measure, each one's cells with their plant
    by both methods and each 2 x 2 tray's A1 bearing (`_measured_cells`), and each tray's plant by
    grow from leaf cores with its soil level and lower cutoff, in the order of `placed` (two trays
    may carry the same tag, #302), from the full-size photo's masks: the saved ones with
    `recount` (their saved levels from `saved`), else new ones from the photo, handed back as the
    last item (the fixed cutoff's, grow from leaf cores' or None) for the caller to save with the
    reading; None for a recount.
    Plant in the strip two touching trays share counts once, for the tray with the nearer centre
    (`segmentation.measure_trays`).

    Not strict (a new read): empty when the photo cannot be segmented, the trays are still placed;
    no grown plant (an empty last list) when grow from leaf cores fails, the fixed green cutoff's
    areas are kept and the tray says so. Strict (Reprocess): anything that fails but a locked rig.db
    raises `NotReprocessed`, never a part of a reading (#483)."""
    try:
        stem = calibration_for_photos(photo_calibration)
        scale_field = load_saved_calibration(stem).scale_field
        if recount:
            try:
                mask = segmentation.load_mask(path)
                grown = segmentation.load_mask(path, segmentation.GROWN_MASK)
            except Exception as exc:  # a truncated or corrupt mask file
                if _rig_db_locked(exc) or not (photo_file(path) or Path()).is_file():
                    raise
                logger.exception("A saved mask of %s cannot be read: growing the photo again", path)
                recount = False
        if recount:
            levels = _saved_levels(saved, placed)
            if mask is None or grown is None or any(level is None or level[1] is None for level in levels):
                raise NotReprocessed(f"{path}: a saved mask or the saved levels are missing")
        else:
            mask, grown, levels = _segment(path, placed, tags, scale_field, strict=strict)
        # A tray with no cutoff (its box lay outside the photo) has no grown area (#483).
        if grown is not None and any(level[1] is None for level in levels):
            if strict:
                raise NotReprocessed(f"{path}: a tray lies outside the photo, its grown area cannot be worked out")
        trays = [(p.outline, p.centre) for p in placed]
        measures = segmentation.measure_trays(mask, trays, scale_field)
    except Exception as exc:
        if _rig_db_locked(exc):
            raise  # the caller retries (#464); a locked rig.db is not "no areas" (#483)
        if strict:
            if isinstance(exc, NotReprocessed):
                raise
            raise NotReprocessed(f"{path}: plant areas not worked out: {exc!r}") from exc
        logger.exception("Could not work out the plant areas of %s", path)
        return None, [], [], [], None
    try:
        by_cores = segmentation.measure_trays(grown, trays, scale_field) if grown is not None else []
        grew = [(m, *level) if level[1] is not None else None for m, level in zip(by_cores, levels, strict=True)] if by_cores else []
    except Exception as exc:
        if strict:
            raise NotReprocessed(f"{path}: plant areas by grow from leaf cores not worked out: {exc!r}") from exc
        logger.exception("Could not work out the plant areas of %s by grow from leaf cores", path)
        grown, grew = None, []
    with_grown = [g is not None for g in grew] if grew else [True] * len(placed)
    cells = _measured_cells(path, mask, grown, placed, tags, scale_field, record or {}, strict, with_grown)
    return stem, measures, cells, grew, None if recount else (mask, grown)


def _recount_blocker(path: str, saved: dict | None, outlined: list[TrayPlacement]) -> str | None:
    """Why the photo cannot be counted again from its saved masks, None when it can. All of these
    hold, else its whole reading is made again (#483): the saved reading is of a read photo from
    this segmenter; every outlined tray is one saved tray (same tag, same outline,
    `_saved_match`) and every saved tray with areas is one of them; every saved tray with areas has
    its grown area and levels, is not a reading made before #373 with the cutoff in the leaves and
    is not marked "grown area not worked out" or "cells not worked out"; both saved masks are on
    disk. The calibration is
    not asked: the masks do not depend on it and the outline match guards the geometry, so a
    changed calibration is counted again from the masks under the new one (Aaron, 2026-11-24)."""
    if not saved or saved["status"] != "read" or not _saved_by_this_segmenter(saved):
        return "no saved reading from this segmenter"
    matches = _saved_match(saved, outlined)
    if any(m is None for m in matches):
        return "a tray is not in the saved reading in the same outline"
    if any(m.get("grown_lower_cutoff") is None for m in matches):
        return "no grown levels saved for a tray"
    measured = [t for t in saved["trays"] if t["area_mm2"] is not None]
    if any(not any(t is m for m in matches) for t in measured):
        return "a saved tray is not found now"
    for t in measured:
        if t.get("grown_area_mm2") is None or t.get("grown_lower_cutoff") is None:
            return "no grown area or levels saved"
        if _grown_into_leaves(t.get("grown_soil_level"), t.get("grown_lower_cutoff"), t.get("grown_blue_coverage")):
            return "saved with the cutoff in the leaves (before #373)"
        if GROWN_NOT_WORKED_OUT in t["warnings"] or CELLS_NOT_WORKED_OUT in t["warnings"]:
            return "its grown area or its cells were not worked out"
    if not (segmentation.mask_file(path).is_file() and segmentation.mask_file(path, segmentation.GROWN_MASK).is_file()):
        return "a saved mask is missing"
    return None


def _at_the_floor(soil_level: float | None, lower_cutoff: float | None) -> bool:
    """Whether a reading's leaf cutoff was set to the floor because the soil counted as hidden:
    the mark SOIL_HIDDEN is true of it. Works from the cutoff a tray's mask was actually grown
    with, not from `blue_coverage` and today's GROWN_BLUE_COVERAGE_MIN, so retuning that threshold
    later never disagrees with a mask already grown (#486, review of #486). Not true of a mask
    grown before #373 with the cutoff in the leaves, kept with the photo gone (#483, finding 8)."""
    return (
        segmentation.soil_reads_high(soil_level) and lower_cutoff is not None
        and lower_cutoff <= segmentation.GROWN_FLOOR + 1e-9
    )


def _soil_reads_green(soil_level: float | None, lower_cutoff: float | None) -> bool:
    """Whether a reading's soil level lies in the top bin while its cutoff was kept above the
    floor: soil that only looked like it might be hidden, marked SOIL_GREEN instead (#486). Never
    true together with `_at_the_floor`: one requires the cutoff at the floor, the other above it."""
    return (
        segmentation.soil_reads_high(soil_level) and lower_cutoff is not None
        and lower_cutoff > segmentation.GROWN_FLOOR + 1e-9
    )


def _no_soil_seen(soil_level: float | None, lower_cutoff: float | None) -> bool:
    """Whether a tray was grown with no soil level found: canopy over the whole tray, nothing
    countable to read a soil level from, so the floor was the cutoff (#522). A tray never grown has
    no cutoff either, and is not this."""
    return soil_level is None and lower_cutoff is not None


def _grown_into_leaves(soil_level: float | None, lower_cutoff: float | None, blue_coverage: float | None) -> bool:
    """Whether a saved reading's soil level lies in the top bin while its lower cutoff was set
    above the floor from it, with no blue coverage saved for it: a reading made before #373, its
    leaves cut short — not a #486 "soil looks green" reading, which always has a blue coverage
    saved alongside its soil level (#486)."""
    return blue_coverage is None and _soil_reads_green(soil_level, lower_cutoff)


# Two outlines of one tray are the same when no corner of one lies more than this from a corner of
# the other. Reprocess finds the outlines of the same photo again, so with the same code, tags and
# calibration they are identical to the float: JSON keeps a float exactly. A decision, not a
# measurement, backed by metrology log 47: 0.01 px is far above float noise (below 1e-9 px) and
# far below a shift that changes the tray's area (1 px, log 47).
OUTLINE_SAME_PX = 0.01


def _same_outline(a, b) -> bool:
    return all(min(math.dist(p, q) for q in b) <= OUTLINE_SAME_PX for p in a) and all(
        min(math.dist(p, q) for q in a) <= OUTLINE_SAME_PX for p in b)


def _saved_match(saved: dict | None, placed: list[TrayPlacement]) -> list[dict | None]:
    """Each placed tray's tray in the saved reading `saved`: the one with the same tag in the same
    outline (`OUTLINE_SAME_PX`); a saved tray with no outline (read before #331) by the same tag at
    the same centre to the pixel, as before. None for a tray with no such saved tray: it was not
    there, or lay in another outline, and what was saved for it was worked out for something
    else (#483)."""
    old = (saved or {}).get("trays", [])
    out: list[dict | None] = []
    for p in placed:
        found = None
        for t in old if p.outline is not None else []:
            if t["tray_id"] != p.tray_id:
                continue
            if t.get("outline_px"):
                same = _same_outline(t["outline_px"], p.outline)
            else:
                same = tuple(round(v) for v in t["centre_px"]) == tuple(round(v) for v in p.centre)
            if same:
                found = t
                break
        out.append(found)
    return out


def _saved_levels(saved: dict | None, placed: list[TrayPlacement]) -> list[tuple[float | None, float | None, float | None] | None]:
    """Each placed tray's soil level, lower cutoff and blue coverage from the saved reading
    `saved` (`_saved_match`); None for a tray with no saved match. Blue coverage is None for a
    tray saved before #486."""
    return [
        None if t is None else (t.get("grown_soil_level"), t.get("grown_lower_cutoff"), t.get("grown_blue_coverage"))
        for t in _saved_match(saved, placed)
    ]


def _measured_cells(path, mask, grown, placed, tags, scale_field, record, strict=False, with_grown=None) -> list:
    """Each placed tray's cells with their plant by the fixed green cutoff (`mask`) and by grow from
    leaf cores (`grown`, None for none), and its 2 x 2 bearing (`_cells`), measured tray by tray
    inside the tray's outline (`segmentation.measure_cells`). A tray whose cells cannot be worked
    out gets none, logged: its tray area and the other trays' cells are kept (review of #374). The
    fourth item of each is whether its cells, or their grown values, could not be worked out
    (the tray then says CELLS_NOT_WORKED_OUT); `with_grown` False for a tray whose grown
    values are left out. With
    `strict` (Reprocess) such a tray raises `NotReprocessed` instead (#483)."""
    out = []
    for p, wanted in zip(placed, with_grown or [True] * len(placed), strict=True):
        try:
            [(cells, bearing, turned)] = _cells([p], tags, scale_field, record)
            counted = segmentation.measure_cells(mask, cells, scale_field, outline_px=p.outline) if cells else []
            by_cores = [None] * len(cells)
            failed = False
            if cells and grown is not None and wanted:
                try:
                    by_cores = segmentation.measure_cells(grown, cells, scale_field, outline_px=p.outline)
                except Exception as exc:
                    if _rig_db_locked(exc) or strict:
                        raise
                    logger.exception("Could not work out the cells of tray %s in %s by grow from leaf cores", p.tray_id, path)
                    failed = True
            out.append((list(zip(cells, counted, by_cores, strict=True)), bearing, turned, failed))
        except Exception as exc:
            if _rig_db_locked(exc):
                raise
            if strict:  # Reprocess: nothing of a reading is saved without its cells (#483)
                if isinstance(exc, NotReprocessed):
                    raise
                raise NotReprocessed(f"{path}: the cells of tray {p.tray_id} not worked out: {exc!r}") from exc
            logger.exception("Could not work out the cells of tray %s in %s", p.tray_id, path)
            out.append(([], None, False, True))
    return out


def _cells(
    placed: list[TrayPlacement], tags: list[TagDetection], scale_field, record: dict
) -> list[tuple[list[Cell], float | None, bool]]:
    """Each placed tray's cells (`tray_placement.place_cells`) and, for a 2 x 2 tray, where its A1
    lies from its tag and whether its tag has turned on the tray (`_tag_turned`), in the order of
    `placed`. No cells for a tray with no tag, or whose tag two
    trays carry, whose cells could belong to either (#302). A 2 x 2 tray's A1 bearing is the one
    stored for it in the photo's experiment (`record`, its rig.db row,
    `database.first_a1_bearing`); with none yet, this photo sets it: A1 its south-west pot
    (Aaron, 2026-11-06)."""
    from npec_rig.randomization import tray_type

    carried = Counter(t.tag_id for t in tags)
    by_id = {t.tag_id: t for t in tags}
    out = []
    for p in placed:
        if p.tray_id is None or carried[p.tray_id] != 1 or p.status != "placed":
            out.append(([], None, False))
            continue
        tag = by_id[p.tray_id]
        if tray_type(p.tray_id).name != "2x2":
            out.append((place_cells(p, tag, scale_field), None, False))
            continue
        bearing = database.first_a1_bearing(record.get("experiment_id"), p.tray_id)
        cells = place_cells(p, tag, scale_field, a1_bearing_deg=bearing)
        turned = bearing is not None and _tag_turned(p, tag, scale_field, record)
        out.append((cells, bearing if bearing is not None else a1_bearing_deg(p, tag, cells), turned))
    return out


def _tag_turned(tray: TrayPlacement, tag: TagDetection, scale_field, record: dict) -> bool:
    """Whether a 2 x 2 tray's tag lies turned on the tray, by more than TAG_TURNED_DEG, from where
    it lay in the photo that set the tray's A1 bearing (`database.first_a1_reading`): its cell
    names may then be swapped (#385). Only the angle: where the tray's centre lies from the tag
    moves by up to 22 mm with the outline found in each photo (metrology log 32.2). False when that
    photo's tag or outline cannot be read."""
    first = database.first_a1_reading(record.get("experiment_id"), tray.tray_id)
    if first is None or first["path"] == record.get("path"):
        return False
    try:
        then = next((t for t in photo_tags.photo_tags_for(first["path"]) if t.tag_id == tray.tray_id), None)
    except (photo_tags.CaptureNotFoundError, photo_tags.CaptureRefError):
        return False
    if then is None:
        return False
    corners = [tuple(c) for c in first["outline_px"]]
    centre = (sum(x for x, _ in corners) / 4, sum(y for _, y in corners) / 4)
    [before] = [t for t in name_trays([TrayOutline(tuple(corners), centre, 0.0, False)], [then]) if t.tray_id == tray.tray_id]
    was, now = tag_on_tray(before, then, scale_field), tag_on_tray(tray, tag, scale_field)
    return abs((now.long_side_deg - was.long_side_deg + 90) % 180 - 90) > TAG_TURNED_DEG


def _photo_size(path: str) -> tuple[int, int] | None:
    """Photo `path`'s width and height in pixels, from its file's header, or from its saved
    full-size mask when the photo is gone (Reprocess); None without either."""
    for file in (photo_file(path), segmentation.mask_file(path)):
        if file is None:  # photo_file: no such photo
            continue
        try:
            with Image.open(file) as image:
                return image.size
        except OSError:
            continue
    return None


def outside_mm(p: TrayPlacement, size: tuple[int, int]) -> float:
    """How far tray `p`'s outline reaches past the edge of a photo of `size` (width, height), at
    its farthest corner, in mm; 0 when it lies inside. Converted at the scale the outline was
    drawn with: its short side is the tray's 305 mm (`TRAY_SIZE_MM`), whichever way it lies."""
    w, h = size
    sides = [math.dist(p.outline[i], p.outline[(i + 1) % 4]) for i in range(2)]
    px_per_mm = min(sides) / TRAY_SIZE_MM[0]
    return max(max(-x, x - w, -y, y - h, 0.0) for x, y in p.outline) / px_per_mm


def _blue_coverage_cells(p: TrayPlacement, tags: list[TagDetection], scale_field) -> list:
    """Each of `p`'s cells to count blue coverage over, the tag's own left out (#486, review of
    #486): its own, lighter geometry, not `_cells`'s — no A1 bearing, no rig.db lookup, no
    cross-photo tag check, only which squares exist and whether each holds a plant or the tag
    (`tray_placement.place_cells` with no bearing gives the same squares as with one, differently
    named only). Kept separate from `_measured_cells` so a failure placing them here, or in one
    tray, costs only that tray's blue coverage (the whole tray as before, #486), never the fixed
    cutoff's area this same photo still has to produce. Empty for a tray with no tag, one two trays
    carry (#302), or whose cells cannot be placed."""
    if p.tray_id is None or Counter(t.tag_id for t in tags)[p.tray_id] != 1:
        return []
    tag = next(t for t in tags if t.tag_id == p.tray_id)
    try:
        cells = place_cells(p, tag, scale_field)
    except Exception:
        logger.exception("Could not place tray %s's cells for blue coverage", p.tray_id)
        return []
    return [c.corners for c in cells if c.holds != "tag"]


def _segment(
    path: str, placed: list[TrayPlacement], tags: list[TagDetection], scale_field, strict: bool = False,
) -> tuple[np.ndarray, np.ndarray | None, list[tuple[float | None, float | None, float | None]] | None]:
    """New masks of photo `path`: the segmenter's and the one by grow from leaf cores of the trays
    `placed`, each tray's tags from `tags`, with each tray's soil level, lower cutoff and blue
    coverage. Not saved here: the caller saves both with the reading (`_stage_masks`, #483). No
    grown mask (None) when grow from leaf cores fails; with `strict` (Reprocess) that raises
    `NotReprocessed`."""
    file = photo_file(path)
    if file is None:
        raise NotReprocessed(f"{path}: the photo is gone")
    # One full-size photo at a time, shared with the tag search (images.py, #348).
    with images.full_decode_slot():
        rgb = images.decode_full(file)
        mask = SEGMENTER.segment(rgb)
        try:
            corners = [[t.corners for t in tags if p.tray_id is not None and t.tag_id == p.tray_id] for p in placed]
            cells = [_blue_coverage_cells(p, tags, scale_field) for p in placed]
            grown, levels = segmentation.grow_trays(
                rgb, [(p.outline, c) for p, c in zip(placed, corners, strict=True)], cells=cells)
        except Exception as exc:
            if strict:
                raise NotReprocessed(f"{path}: could not grow the plant from leaf cores: {exc!r}") from exc
            logger.exception("Could not grow the plant from leaf cores in %s", path)
            grown, levels = None, None
        del rgb
    return mask, grown, levels


def photo_readings(path: str) -> dict | None:
    """Photo `path`'s saved tray readings (`database.tray_readings`), None when not yet read, with
    its `exclusion` (`exclusions`, `GLOSSARY.md`) or None, each tray's `floor_mm2` (`FLOORS_MM2`,
    None for a segmenter without one) and `not_counted`: the reasons its area is left out, empty
    when it counts."""
    record = database.captures_by_path([path]).get(path)
    if record is None:
        raise LookupError(f"photo {path} has no record in rig.db")
    return capture_readings(record)


# A cell is flagged when grow from leaf cores reads more than this many times the fixed green
# cutoff's area and more than this far above it (a dark empty pot read as plant, #484). Decisions
# of Aaron's, not measurements.
FLAG_TIMES = 5
FLAG_MIN_DIFFERENCE_MM2 = 100.0


def _grown_far_above_fixed(grown: float | None, fixed: float | None) -> bool:
    """Whether a cell's grown area is flagged against its fixed-cutoff area (None is no plant: 0).
    `grown > 5 * fixed`, so a fixed area of 0 works. Never flagged with no grown area."""
    if grown is None:
        return False
    fixed = fixed or 0.0
    return grown > FLAG_TIMES * fixed and grown - fixed >= FLAG_MIN_DIFFERENCE_MM2


def capture_readings(capture: dict, *, history: bool = True, locations: dwell.LocationFinder | None = None) -> dict | None:
    """`photo_readings` for a photo whose rig.db row `capture` is already at hand. `history` False
    leaves out the trays not found and moved since earlier photos (`database.tray_readings`), and
    `locations` is one finder kept for many photos: an export of every photo needs neither the
    history nor a new finder per photo (#437)."""
    readings = database.tray_readings(capture["id"], history=history)
    if readings is not None:
        locations = locations or dwell.LocationFinder()
        for tray in readings["not_found"]:
            seen_in = tray.pop("seen_in")
            tray["location"] = locations.location(seen_in["path"], seen_in["calibration"], seen_in["centre_px"])
        # A move is a tray's centre leaving its table location; a nudge or a turn is not
        # (Aaron, 2026-10-30, #332).
        readings["moved"] = []
        for tray in readings.pop("in_both"):
            before = locations.location(tray["before"]["path"], tray["before"]["calibration"], tray["before"]["centre_px"])
            now = locations.location(capture["path"], capture["calibration"], tray["centre_px"])
            if before is not None and now is not None and before != now:
                readings["moved"].append({"tray_id": tray["tray_id"], "from": before, "to": now})
        saved = database.exclusion(capture["id"])
        if saved is None:
            # Read before exclusions were stored: lights off needs only the photo itself.
            saved = {"name": exclusions.light_exclusions([capture])["exclusions"][0]}
        readings["exclusion"] = saved["name"]
        # Auto exposure off (AeState idle): areas stay counted, the page warns (#507).
        readings["lights_checked"] = exclusions.lights_checked(capture)
        _outline_old_rows(capture, readings["trays"])
        # A tray with no tag (#331) carries no tag another tray could share.
        carried = Counter(tray["tray_id"] for tray in readings["trays"] if tray["tray_id"] is not None)
        bands = _validation_bands(capture)
        for tray in readings["trays"]:
            tray["uncertainty"] = bands(tray["centre_px"])
            # The table location the tray lies in, for the Gallery (#332); None when the
            # photo's size cannot be known.
            tray["location"] = locations.location(capture["path"], capture["calibration"], tray["centre_px"])
            # Neither area counts, in this photo only: a misprint can give two trays one tag, and
            # their areas cannot be told apart (Aaron, 2026-10-27, #302); a second outline in a
            # slot, from a loose tag, takes part of the real tray's plant (2026-10-28, #315). Two
            # trays placed in one slot are found in readings saved before #331 only; the reason
            # names no slot (#332).
            n_tag = carried[tray["tray_id"]]
            tray["not_counted"] = [
                *([f"{n_tag} trays carry tag {tray['tray_id']}"] if n_tag > 1 else []),
                *(["2 trays in one place"] if tray["placement"] == "two trays in one slot" else []),
                # The same rule for trays found in the photo (#331): one outline, two trays' tags.
                *(["2 tags in one tray outline"] if tray["placement"] == "two tags in one outline" else []),
            ]
            # From the first photo whose tag lay turned on the tray, for the rest of the experiment,
            # whichever photos were read first (Aaron, 2026-11-07, #385).
            since = None if tray["tray_id"] is None else database.first_warning_at(
                capture.get("experiment_id"), tray["tray_id"], TAG_TURNED, capture["taken_at"])
            tray["names_unsure_since"] = since
            tray["warnings"] = [w for w in tray["warnings"] if w != TAG_TURNED] + (
                [f"names may be swapped since {since[:10]} {since[11:16]} UTC"] if since else [])
            tray["floor_mm2"] = FLOORS_MM2.get(tray["segmenter"])
            tray["method"] = METHODS.get(tray["segmenter"], tray["segmenter"])
            for cell in tray["cells"]:
                cell["status"] = _cell_status(cell)
                if not cell["plant_px"] or cell["status"] == "tag":
                    cell["area_mm2"] = None
                # The same words by grow from leaf cores (#363); None when it was not run.
                cell["grown_status"] = None if cell["grown_plant_px"] is None else _cell_status({
                    "holds": cell["holds"], "over_other_cells": cell["grown_over_other_cells"], "plant_px": cell["grown_plant_px"]})
                if not cell["grown_plant_px"] or cell["holds"] == "tag":
                    cell["grown_area_mm2"] = None
                cell["flagged"] = _grown_far_above_fixed(cell["grown_area_mm2"], cell["area_mm2"])
            # A tray with no cells (1 x 1) is one cell: the same rule on its whole area (#484).
            flagged = [c["grown_area_mm2"] for c in tray["cells"] if c["flagged"]] if tray["cells"] else (
                [tray.get("grown_area_mm2")] if _grown_far_above_fixed(tray.get("grown_area_mm2"), tray.get("area_mm2")) else [])
            tray["cells_flagged"], tray["cells_flagged_grown_area_mm2"] = len(flagged), sum(flagged)
            if flagged:
                n, total = len(flagged), sum(flagged)
                tray["warnings"].append(
                    (f"{n} cells where grown and fixed areas disagree ({total:,.0f} mm² in total). "
                     "Usually an empty pot. Check the cells.")
                    if n > 1 else
                    (f"1 cell where grown and fixed areas disagree ({total:,.0f} mm²). "
                     "Usually an empty pot. Check the cell."))
            tray["partly_outside"] = None if tray["outside_mm"] is None else tray["outside_mm"] > PAST_EDGE_MM
        readings["area_methods"] = [
            {k: v for k, v in m.items() if k != "stored"} for m in AREA_METHODS
            if any(tray.get(m["stored"]) for tray in readings["trays"])
        ]
    return readings


# Each validation file read once while unchanged, by its id and modification time: the Gallery and
# an export ask for the same validation for every photo taken under it.
_validations: dict[tuple[str, int], tuple[str, list[dict], dict] | str] = {}
_validations_lock = threading.Lock()


def _validation(session_id: str) -> tuple[str, list[dict], dict] | str:
    """Validation `session_id`'s state, its slots and their bands by name, or the reason no band
    can come from it."""
    try:
        mtime = validation_store.validations_root().joinpath(f"{session_id}.json").stat().st_mtime_ns
    except OSError:
        mtime = 0
    with _validations_lock:
        if (session_id, mtime) in _validations:
            return _validations[(session_id, mtime)]
    try:
        session = validation_store.load_session(session_id)
        state = validation_store.status(session)["state"]
        slots = [{"name": s["name"], "centre": s["centre"]} for s in session["slots"]]
        bands = {r["name"]: r["p95_abs_pct"] for r in session["results"]}
        result = (state, slots, bands) if slots else "validation not found"
    except validation_store.SessionNotFoundError:
        result = "validation not found"
    except Exception:  # noqa: BLE001 -- a damaged session file never hides the areas
        logger.exception("Could not read validation %s", session_id)
        result = "validation not found"
    with _validations_lock:
        _validations[(session_id, mtime)] = result
    return result


def _validation_bands(capture: dict):
    """A function giving the uncertainty of a tray centred at a point of photo `capture`: the band
    of the slot of the photo's validation whose centre is nearest (Aaron, 2026-11-05, #76), "within
    ±band_pct %" for flat objects at tray-top height, 95 times in 100. No band is claimed, and
    the reason says why, when the photo has no validation, its validation is gone, damaged or not
    consistent, when the photo is flagged as not covered, or when the slot had too few tags."""
    def none(reason: str):
        return lambda centre_px: {"band_pct": None, "slot": None, "reason": reason}

    if not capture.get("validation"):
        return none("not validated")
    validation = _validation(capture["validation"])
    if isinstance(validation, str):
        return none(validation)
    state, slots, bands = validation
    if state != "validated":
        return none("validation not consistent" if state == "not_consistent" else "not validated")
    # After the validation's own state, the more exact reason. Each flag is a reason the photo is
    # not covered by the bands (captures.take_photo), such as a lens moved from its lock; some
    # callers pass the column as stored, as JSON text.
    flags = capture.get("flags") or []
    if isinstance(flags, str):
        flags = json.loads(flags)
    if flags:
        return none("photo not covered")

    def band(centre_px) -> dict:
        slot, _distance = nearest_slot(*centre_px, slots)
        band_pct = bands.get(slot)
        return {"band_pct": band_pct, "slot": slot, "reason": None if band_pct is not None else "slot not measured"}

    return band


def _cell_status(cell: dict) -> str:
    """What a cell's reading says, in words for the page (#364): "tag" (the tray tag's cell, no
    plant), "missing" (no plant seen: a plant lost in this photo or never there, never an area of
    0), "leaves over other cells" (its area is not one plant's own, Aaron, 2026-11-06), or
    "plant"."""
    if cell["holds"] == "tag":
        return "tag"
    # Before "missing": a neighbour's leaves over a cell may hide its own plant.
    if cell["over_other_cells"]:
        return "leaves over other cells"
    return "plant" if cell["plant_px"] else "missing"


def _outline_old_rows(capture: dict, trays: list[dict]) -> None:
    """Give each tray read before #331 (placed from its tag, no outline stored) the outline its
    placement had: the tray's outside size around its stored centre, turned by its tilt, at its
    calibration's scale (review of #334). Left without one when the calibration cannot be read."""
    scales: dict[str, object] = {}
    for tray in trays:
        if tray["outline_px"] is not None or tray["found"] is not None:
            continue
        try:
            stem = tray["calibration"] or calibration_for_photos(capture["calibration"])
            if stem not in scales:
                scales[stem] = load_saved_calibration(stem).scale_field
            ppm = scales[stem].px_per_mm(*tray["centre_px"])
        except (CalibrationNotFoundError, CalibrationUnreadableError, TypeError, ValueError):
            continue
        tray["outline_px"] = [list(c) for c in tray_outline_at(tuple(tray["centre_px"]), tray["tilt_deg"], ppm)]


class TrayReader:
    """One background thread that reads each photo for its trays after it is saved, newest first:
    every photo taken since it started, and every photo of the running experiment. Older photos
    are read only when asked, by Show tags (Aaron, 2026-10-22)."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._since = ""

    def start(self) -> None:
        _sweep_staged_masks()
        self._stop.clear()
        self._since = datetime.now(UTC).isoformat()
        self._thread = threading.Thread(target=self._run, name="tray-reader", daemon=True)
        self._thread.start()

    def stop(self, timeout_s: float | None = None) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout_s)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                paths = database.unread_photos(limit=1, since=self._since)
            except Exception:
                logger.exception("Could not look for unread photos; trying again")
                paths = []
            if not paths:
                self._stop.wait(POLL_S)
                continue
            self._read(paths[0])

    def _read(self, path: str) -> None:
        try:
            read_photo(path)
        except Exception as exc:
            if _rig_db_locked(exc):
                # Another writer held rig.db (#439): nothing is saved, so the photo stays unread
                # and is read again once the lock is gone, instead of "read failed" for good.
                logger.warning("rig.db was locked while the trays of %s were read; reading it again", path)
                self._stop.wait(POLL_S)
                return
            logger.exception("Could not read the trays of %s", path)
            try:
                # Saved as failed, so one bad photo is not tried again forever.
                database.record_tray_readings(
                    _capture_id(path), read_at=datetime.now(UTC).isoformat(), status="read failed", trays=[]
                )
            except Exception:
                logger.exception("Could not record the failed reading of %s", path)
                self._stop.wait(POLL_S)


def _rig_db_locked(exc: BaseException | None) -> bool:
    """Whether `exc`, or an error it was raised from, is SQLite's "database is locked"."""
    seen: set[int] = set()  # a cycle of causes must never hang this (#483)
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, sqlite3.OperationalError) and "locked" in str(exc):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


# --- Reprocess (#75, #483) ----------------------------------------------------------------------
# One experiment at a time, in a thread of its own beside the background reader: every photo of
# the experiment read again, its areas worked out afresh, whole photo or nothing (`read_photo`,
# #483). A photo that cannot be redone completely is counted as failed and left as it was, with
# why. Progress and the failed photos are kept in rig.db (`reprocess_run`, `reprocess_failure`), so
# they are there after a restart; a run the app's stop cut off is marked "interrupted" at the next
# start and never resumed. A Stop ends the run after the photo being read.
#
# Take a copy of rig.db first; the app does not. Reprocess replaces the saved readings of every
# photo it can redo and keeps no copy of the old ones (docs/operator-guide.md, *Reprocessing areas
# (developers and scripts)*).

# A photo that meets a locked rig.db is read again after a wait, this many tries in all. The
# numbers are decisions: the longest a write waits on its own is settings.LOCK_WAIT_S (10 s), so
# five tries with a 5 s pause give a lock that long to end, many times over, without a photo ever
# holding the run up for ever.
REPROCESS_LOCK_TRIES = 5
REPROCESS_LOCK_WAIT_S = 5.0

# The run this process is running, if any: guarded by `_reprocess_lock`. A `running` row in rig.db
# with no live thread here (its last write failed, or the app was killed) is an orphan: it is
# marked interrupted, so it can neither block a new run nor answer a Stop (#483).
_reprocess_lock = threading.Lock()
_live: dict | None = None  # {"run_id", "experiment_id", "thread", "stop": Event of this run alone}


class ReprocessRunning(RuntimeError):
    """Another Reprocess is still running, or a time lapse video is being made: one job that reads
    every photo at a time (#503). The reason, in words."""


class NoReprocessRunning(RuntimeError):
    """There is no Reprocess of the experiment to stop."""


def _progress(run: dict | None, experiment_id: int, *, failures: bool = True) -> dict:
    if run is None:
        none = {"experiment_id": experiment_id, "run_id": None, "state": "none", "running": False, "done": 0, "total": 0,
                "failed": 0, "started_at": None, "finished_at": None, "message": None}
        return {**none, "failures": []} if failures else none
    message = {"stopped": "stopped at", "interrupted": "interrupted at"}.get(run["state"])
    progress = {
        "experiment_id": experiment_id, "run_id": run["id"], "state": run["state"], "running": run["state"] == "running",
        "done": run["done"], "total": run["total"], "failed": run["failed"],
        "started_at": run["started_at"], "finished_at": run["finished_at"],
        "message": None if message is None else f"{message} {run['done']} of {run['total']}",
    }
    if "failures" in run:
        progress["failures"] = run["failures"]
    return progress


def _live_run() -> dict | None:
    """The run whose thread is alive, with `_reprocess_lock` held by the caller; any `running` row
    without one is marked interrupted first."""
    global _live
    if _live is not None and not _live["thread"].is_alive():
        _live = None
    if _live is None and database.running_reprocess_run() is not None:
        try:
            mark_interrupted_reprocesses()
        except Exception as exc:  # the orphan exists because rig.db was locked: the mark may meet the lock too
            if not _rig_db_locked(exc):
                raise
            logger.warning("Could not mark an orphaned Reprocess interrupted: rig.db is locked; a later call will")
    return _live


def reprocess_progress(experiment_id: int, *, failures: bool = True) -> dict:
    """How far the newest Reprocess of `experiment_id` has got, from rig.db: its state (`none`,
    `running`, `finished`, `stopped`, `interrupted`), done, total, failed, the failed photos with
    their reasons, and a message for a stopped or interrupted run ("interrupted at 3 of 10")."""
    with _reprocess_lock:
        live = _live_run()
    run = database.latest_reprocess_run(experiment_id, failures=failures)
    if run is not None and run["state"] == "running" and (live is None or live["run_id"] != run["id"]):
        run = {**run, "state": "interrupted"}  # no thread runs it; the mark is saved by a later call
    return _progress(run, experiment_id, failures=failures)


def _reprocess_paths(experiment_id: int) -> list[str]:
    return [c["path"] for c in database.captures_for_experiment(experiment_id) if c["purpose"] == "capture"]


def reprocess_plan(experiment_id: int) -> dict:
    """What a Reprocess of `experiment_id` would do, changing nothing: the photos it would read and
    an estimate of the time, from the newest finished Reprocess on this rig (its seconds per photo,
    named in `estimate_from`); None, with the reason, when there is none: no time is guessed."""
    photos = len(_reprocess_paths(experiment_id))
    rate = database.last_finished_reprocess_rate()
    if rate is None:
        return {"experiment_id": experiment_id, "photos": photos, "estimated_seconds": None,
                "estimate_from": "no earlier Reprocess has finished on this rig"}
    return {
        "experiment_id": experiment_id, "photos": photos, "estimated_seconds": round(rate["seconds"] / rate["photos"] * photos),
        "estimate_from": f"Reprocess {rate['run']}: {rate['photos']} photos in {round(rate['seconds'])} s",
    }


def start_reprocess(experiment_id: int) -> dict:
    """Start Reprocess of the experiment's photos taken as captures, oldest first, and return its
    progress. Raises ReprocessRunning while one is running or a time lapse video is being made. The
    caller has made the copy of rig.db and has the experiment's ID confirmed (`routes/experiments.py`)."""
    from npec_rig import timelapse  # here, not at the top: timelapse imports this module

    if timelapse.being_made() is not None:
        raise ReprocessRunning("A time lapse video is being made. Reprocess when it is done.")
    paths = _reprocess_paths(experiment_id)
    _sweep_staged_masks()
    global _live
    with _reprocess_lock:
        if _live_run() is not None:
            raise ReprocessRunning("a Reprocess is still running")
        if database.running_reprocess_run() is not None:  # an orphan that could not be marked ended
            raise ReprocessRunning("an earlier Reprocess could not be marked ended while rig.db was locked: try again")
        run_id = database.create_reprocess_run(experiment_id, total=len(paths), started_at=datetime.now(UTC).isoformat())
        stop = threading.Event()
        thread = threading.Thread(target=_run_reprocess, args=(run_id, paths, stop), name="reprocess", daemon=True)
        _live = {"run_id": run_id, "experiment_id": experiment_id, "thread": thread, "stop": stop}
        thread.start()
    return reprocess_progress(experiment_id)


def stop_reprocess(experiment_id: int) -> dict:
    """Ask the running Reprocess of `experiment_id` to end after the photo it is reading, and
    return its progress. Raises NoReprocessRunning when there is none."""
    with _reprocess_lock:
        live = _live_run()
        if live is None or live["experiment_id"] != experiment_id:
            raise NoReprocessRunning(f"no Reprocess of experiment {experiment_id} is running")
        live["stop"].set()  # this run's own: a later run is not touched
    return reprocess_progress(experiment_id)


def mark_interrupted_reprocesses() -> int:
    """At the app's start: a Reprocess still `running` in rig.db was cut off when the app stopped
    under it, no thread of this process runs it. It is marked `interrupted` and never resumed (the
    researcher decides, from its progress). Returns how many."""
    return database.interrupt_running_reprocesses(finished_at=datetime.now(UTC).isoformat())


def _locked_retry(action, what: str):
    """`action()`, again after REPROCESS_LOCK_WAIT_S while rig.db is locked, REPROCESS_LOCK_TRIES in
    all; the last lock error is raised. Any other error is raised at once."""
    for attempt in range(1, REPROCESS_LOCK_TRIES + 1):
        try:
            return action()
        except Exception as exc:
            # A NotReprocessed is a real answer, even if a lock error lies behind it in the chain.
            if isinstance(exc, NotReprocessed) or not _rig_db_locked(exc) or attempt == REPROCESS_LOCK_TRIES:
                raise
            logger.warning("%s met a locked rig.db (try %d of %d)", what, attempt, REPROCESS_LOCK_TRIES)
            time.sleep(REPROCESS_LOCK_WAIT_S)


def _run_reprocess(run_id: int, paths: list[str], stop: threading.Event) -> None:
    done = failed = 0
    state = "finished"
    try:
        for path in paths:
            if stop.is_set():
                state = "stopped"
                break
            try:
                _locked_retry(lambda: read_photo(path, reuse_mask=True), f"Reprocess of {path}")
            except Exception as exc:
                logger.exception("Reprocess could not read %s", path)
                failed += 1
                reason = str(exc) if isinstance(exc, NotReprocessed) else (
                    f"rig.db stayed locked after {REPROCESS_LOCK_TRIES} tries" if _rig_db_locked(exc) else f"{type(exc).__name__}: {exc}")
                try:
                    _locked_retry(lambda: database.add_reprocess_failure(
                        run_id, path=path, reason=reason, failed_at=datetime.now(UTC).isoformat()), "Saving a failed photo")
                except Exception:
                    logger.exception("Could not save why %s failed", path)
            done += 1
            try:
                _locked_retry(lambda: database.update_reprocess_run(run_id, done=done, failed=failed), "Saving Reprocess progress")
            except Exception:
                logger.exception("Could not save the progress of Reprocess %s", run_id)
    finally:
        try:
            _locked_retry(lambda: database.update_reprocess_run(
                run_id, done=done, failed=failed, state=state, finished_at=datetime.now(UTC).isoformat()), "Ending Reprocess")
        except Exception:
            logger.exception("Could not save the end of Reprocess %s: it stays 'running' until the app starts again", run_id)
