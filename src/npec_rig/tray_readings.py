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
import sqlite3
import threading
from collections import Counter
from datetime import UTC, datetime

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
    tray_outline_at,
)

logger = logging.getLogger(__name__)

# What makes each mask. One line to change for another segmenter: every area records its name.
SEGMENTER: segmentation.Segmenter = segmentation.ExGSegmenter()

# Each segmenter's floor, by its name: an area below it means nothing detected yet. Empty
# trays read up to 98 mm2 with the green threshold, mostly one light-blue mark per tray (metrology
# log 17.4). Reported with each area, never subtracted (Aaron). A decision (#288), checked in #293.
FLOORS_MM2 = {"green threshold, 0.1": 100}

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


def _calibration(path: str) -> tuple[str, object, list[dict] | None]:
    """Photo `path`'s status so far ("read", or "no calibration", "no slot layout"), its
    calibration's scale field and its slot layout's slots."""
    try:
        record = database.captures_by_path([path]).get(path)
    except (sqlite3.Error, RuntimeError):
        logger.exception("Could not read the capture row of %s", path)
        return "no calibration", None, None
    if record is None or not record.get("calibration"):
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


def found_trays(path: str, tags: list[TagDetection], saved: dict | None = None) -> tuple[str, list[TrayPlacement]]:
    """The trays of photo `path`: found in the photo from their blue plastic and named by the tag
    inside each, and each tray tag inside no outline seen where it lies, with the calibration the
    photo was taken under; no slot layout is needed (#331). The status: "read", "no calibration",
    "placement failed", or "no trays found" when the photo shows neither a tray nor a tag, as with
    the lights off. With the photo gone (Reprocess from its saved mask), the outlines of the saved
    reading `saved` are used again; with none saved, "photo not found"."""
    status, scale_field, _slots = _calibration(path)
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
    `reuse_mask`, a mask saved by the same segmenter is counted again instead of segmenting the
    photo: Reprocess, which then needs neither the photo nor the segmenter. With
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
    status, placed = found_trays(path, tags, saved)
    reuse = reuse_mask and _saved_by_this_segmenter(saved)
    # A tag seen with no tray found around it has no outline: nothing to measure (#331).
    outlined = [p for p in placed if p.outline is not None]
    calibration, measures, cells = _measures(path, record["calibration"], outlined, reuse, tags, record) if outlined else (None, [], [])
    size = _photo_size(path) if outlined else None
    # No area now, whether or not any tray was outlined (review of #334): a saved area is kept.
    _refuse_worse(path, saved, status, areas_lost=not measures)
    measured = dict(zip(map(id, outlined), measures, strict=True)) if measures else {}
    celled = dict(zip(map(id, outlined), cells, strict=True)) if measures else {}
    no_cells: tuple[list, None] = ([], None)
    trays = []
    for p in placed:
        m = measured.get(id(p))
        trays.append({
            "tray_id": p.tray_id, "slot": p.slot, "a1_corner": p.a1_corner, "placement": p.status,
            "centre_px": list(p.centre), "tilt_deg": p.tilt_deg, "margin_mm": p.margin_mm,
            "area_mm2": m.area_mm2 if m else None, "segmenter": SEGMENTER.name if m else None,
            "plant_px": m.plant_px if m else None,
            "plant_centre_px": list(m.centre_px) if m and m.centre_px else None,
            "calibration": calibration if m else None,
            "outside_mm": outside_mm(p, size) if size and p.outline is not None else None,
            "found": p.found, "warnings": list(p.warnings),
            "outline_px": None if p.outline is None else [list(c) for c in p.outline],
            "cells": [
                {
                    "cell": c.name, "holds": c.holds, "centre_px": list(c.centre), "corners_px": [list(k) for k in c.corners],
                    "plant_px": cm.plant_px, "area_mm2": cm.area_mm2,
                    "plant_centre_px": list(cm.centre_px) if cm.centre_px else None,
                    "over_other_cells": cm.over_other_cells, "segmenter": SEGMENTER.name, "cell_rule": CELL_RULE,
                }
                for c, cm in celled.get(id(p), no_cells)[0]
            ],
            "a1_bearing_deg": celled.get(id(p), no_cells)[1],
        })
    database.record_tray_readings(capture_id, read_at=datetime.now(UTC).isoformat(), status=status, trays=trays)
    exclusions.update(record)
    return capture_readings(record)


class ReadingWorse(RuntimeError):
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
    path: str, photo_calibration: str, placed: list[TrayPlacement], reuse_mask: bool = False,
    tags: list[TagDetection] = (), record: dict | None = None,
) -> tuple[str | None, list[segmentation.PlantMeasure], list[tuple[list[tuple[Cell, segmentation.CellMeasure]], float | None]]]:
    """The calibration used, each placed tray's plant measure and each one's cells with their
    plant and each 2 x 2 tray's A1 bearing (`_cells`), in the order of `placed` (two trays may carry the same tag, #302), from the
    full-size photo's mask: the saved one with `reuse_mask`, else a new one, saved for Reprocess.
    Empty when the photo cannot be segmented: the trays are still placed. Plant in the strip two
    touching trays share counts once, for the tray with the nearer centre
    (`segmentation.measure_trays`)."""
    try:
        stem = calibration_for_photos(photo_calibration)
        scale_field = load_saved_calibration(stem).scale_field
        mask = segmentation.load_mask(path) if reuse_mask else None
        if mask is None:
            mask = _segment(path)
        trays = [(p.outline, p.centre) for p in placed]
        measures = segmentation.measure_trays(mask, trays, scale_field)
    except Exception:
        logger.exception("Could not work out the plant areas of %s", path)
        return None, [], []
    return stem, measures, _measured_cells(path, mask, placed, tags, scale_field, record or {})


def _measured_cells(path, mask, placed, tags, scale_field, record) -> list:
    """Each placed tray's cells with their plant and its 2 x 2 bearing (`_cells`), measured tray by
    tray inside the tray's outline (`segmentation.measure_cells`). A tray whose cells cannot be
    worked out gets none, logged: its tray area and the other trays' cells are kept (review of
    #374)."""
    out = []
    for p in placed:
        try:
            [(cells, bearing)] = _cells([p], tags, scale_field, record)
            counted = segmentation.measure_cells(mask, cells, scale_field, outline_px=p.outline) if cells else []
            out.append((list(zip(cells, counted, strict=True)), bearing))
        except Exception:
            logger.exception("Could not work out the cells of tray %s in %s", p.tray_id, path)
            out.append(([], None))
    return out


def _cells(
    placed: list[TrayPlacement], tags: list[TagDetection], scale_field, record: dict
) -> list[tuple[list[Cell], float | None]]:
    """Each placed tray's cells (`tray_placement.place_cells`) and, for a 2 x 2 tray, where its A1
    lies from its tag, in the order of `placed`. No cells for a tray with no tag, or whose tag two
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
            out.append(([], None))
            continue
        tag = by_id[p.tray_id]
        if tray_type(p.tray_id).name != "2x2":
            out.append((place_cells(p, tag, scale_field), None))
            continue
        bearing = database.first_a1_bearing(record.get("experiment_id"), p.tray_id)
        cells = place_cells(p, tag, scale_field, a1_bearing_deg=bearing)
        out.append((cells, bearing if bearing is not None else a1_bearing_deg(p, tag, cells)))
    return out


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


def _segment(path: str) -> np.ndarray:
    """A new mask of photo `path`, saved for Reprocess."""
    # One full-size photo at a time, shared with the tag search (images.py, #348).
    with images.full_decode_slot():
        rgb = images.decode_full(photo_file(path))
        mask = SEGMENTER.segment(rgb)
        del rgb
    segmentation.save_mask(path, mask)
    return mask


def photo_readings(path: str) -> dict | None:
    """Photo `path`'s saved tray readings (`database.tray_readings`), None when not yet read, with
    its `exclusion` (`exclusions`, `GLOSSARY.md`) or None, `norm_pending` while its experiment has
    no light norm yet, each tray's `floor_mm2` (`FLOORS_MM2`, None for a segmenter without
    one) and `not_counted`: the reasons its area is left out, empty when it counts."""
    record = database.captures_by_path([path]).get(path)
    if record is None:
        raise LookupError(f"photo {path} has no record in rig.db")
    return capture_readings(record)


def capture_readings(capture: dict) -> dict | None:
    """`photo_readings` for a photo whose rig.db row `capture` is already at hand."""
    readings = database.tray_readings(capture["id"])
    if readings is not None:
        locations = dwell.LocationFinder()
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
            result = exclusions.light_exclusions([capture])
            saved = {"name": result["exclusions"][0], "norm_e": None}
        readings["exclusion"] = saved["name"]
        readings["norm_pending"] = saved["norm_e"] is None
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
            tray["floor_mm2"] = FLOORS_MM2.get(tray["segmenter"])
            for cell in tray["cells"]:
                cell["status"] = _cell_status(cell)
                if not cell["plant_px"] or cell["status"] == "tag":
                    cell["area_mm2"] = None
            tray["partly_outside"] = None if tray["outside_mm"] is None else tray["outside_mm"] > PAST_EDGE_MM
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
        except Exception:
            logger.exception("Could not read the trays of %s", path)
            try:
                # Saved as failed, so one bad photo is not tried again forever.
                database.record_tray_readings(
                    _capture_id(path), read_at=datetime.now(UTC).isoformat(), status="read failed", trays=[]
                )
            except Exception:
                logger.exception("Could not record the failed reading of %s", path)
                self._stop.wait(POLL_S)


# --- Reprocess (#75) ----------------------------------------------------------------------------
# One experiment at a time, in a thread of its own beside the background reader: every photo of
# the experiment read again, its areas worked out afresh. A photo that fails is counted and left
# as it was.

_reprocess_lock = threading.Lock()
_reprocess: dict = {"experiment_id": None, "running": False, "done": 0, "total": 0, "failed": 0}


class ReprocessRunning(RuntimeError):
    """Another Reprocess is still running."""


def reprocess_progress(experiment_id: int) -> dict:
    """How far Reprocess of `experiment_id` has got: running, done, total, failed. All zero when
    it has not been reprocessed since the app started."""
    with _reprocess_lock:
        if _reprocess["experiment_id"] != experiment_id:
            return {"experiment_id": experiment_id, "running": False, "done": 0, "total": 0, "failed": 0}
        return dict(_reprocess)


def start_reprocess(experiment_id: int) -> dict:
    """Start Reprocess of the experiment's photos taken as captures, oldest first, and return its
    progress. Raises ReprocessRunning while one is running."""
    paths = [c["path"] for c in database.captures_for_experiment(experiment_id) if c["purpose"] == "capture"]
    with _reprocess_lock:
        if _reprocess["running"]:
            raise ReprocessRunning(f"Reprocess of experiment {_reprocess['experiment_id']} is still running")
        _reprocess.update(experiment_id=experiment_id, running=True, done=0, total=len(paths), failed=0)
        progress = dict(_reprocess)
    threading.Thread(target=_run_reprocess, args=(paths,), name="reprocess", daemon=True).start()
    return progress


def _run_reprocess(paths: list[str]) -> None:
    try:
        for path in paths:
            try:
                read_photo(path, reuse_mask=True)
            except Exception:
                logger.exception("Reprocess could not read %s", path)
                with _reprocess_lock:
                    _reprocess["failed"] += 1
            with _reprocess_lock:
                _reprocess["done"] += 1
    finally:
        with _reprocess_lock:
            _reprocess["running"] = False
