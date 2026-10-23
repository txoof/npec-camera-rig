"""Readings per tray per photo (#222): each photo read once for its trays, and the result saved in
`rig.db` (`database.record_tray_readings`).

A reading is the trays whose tag was found, each placed in a slot with the calibration the photo
was taken under (`tray_placement.place_trays`), with its plant area: the segmenter's mask of the
full-size photo, saved to disk, summed inside the tray outline at the local scale (#75). A
tray not found is never stored: `database.tray_readings` works it out from the experiment's
earlier photos when the readings are shown.
"""

import logging
import sqlite3
import threading
from datetime import UTC, datetime

import numpy as np
from PIL import Image

from npec_rig import database, photo_tags, segmentation, validation_store
from npec_rig.captures import photo_file
from npec_rig.calibration_store import CalibrationNotFoundError, CalibrationUnreadableError, load_saved_calibration
from npec_rig.tags import TagDetection
from npec_rig.tray_placement import TrayPlacement, place_trays

logger = logging.getLogger(__name__)

# What makes each mask. One line to change for another segmenter: every area records its name.
SEGMENTER: segmentation.Segmenter = segmentation.ExGSegmenter()

# Seconds between looks for photos not yet read, when there are none. One reading took 9.6 s to
# 12.5 s (metrology log 15.5m), so a photo a minute leaves the reader idle most of the time.
POLL_S = 5.0


def placements(path: str, tags: list[TagDetection]) -> tuple[str, list[TrayPlacement]]:
    """Each tray tag of photo `path` placed with the calibration the photo was taken under, and
    the status: "read", or why nothing could be placed ("no calibration", "no slot layout",
    "placement failed"). Reads only: nothing is worked out from the photo or stored."""
    try:
        record = database.captures_by_path([path]).get(path)
    except (sqlite3.Error, RuntimeError):
        logger.exception("Could not read the capture row of %s", path)
        return "no calibration", []
    if record is None or not record.get("calibration"):
        return "no calibration", []
    try:
        artifact = load_saved_calibration(record["calibration"])
        # Only a layout already worked out: working it out decodes the 64MP calibration frame.
        layout = validation_store.load_slot_layout(record["calibration"])
    except (CalibrationNotFoundError, CalibrationUnreadableError, validation_store.SessionNotFoundError):
        return "no calibration", []
    if layout is None:
        return "no slot layout", []
    try:
        return "read", place_trays(tags, artifact.scale_field, layout["slots"])
    except (ValueError, KeyError, TypeError, OSError):
        logger.exception("Could not place the trays of %s", path)
        return "placement failed", []


def _capture_id(path: str) -> int:
    record = database.captures_by_path([path]).get(path)
    if record is None:
        raise LookupError(f"photo {path} has no record in rig.db")
    return record["id"]


def read_photo(path: str, *, reuse_mask: bool = False) -> dict:
    """Read gallery photo `path` for its trays, save the reading (replacing any earlier one) and
    return it as `photo_readings` would. The tags are searched once per photo (photo_tags). With
    `reuse_mask`, a mask saved by the same segmenter is counted again instead of segmenting the
    photo: Reprocess, which then needs neither the photo nor the segmenter."""
    capture_id = _capture_id(path)
    tags = photo_tags.photo_tags_for(path)
    # No tag of any kind, as with the lights off (metrology log 15.5l): not trays missing.
    status, placed = placements(path, tags) if tags else ("no tags found", [])
    calibration, measures = _measures(path, placed, reuse_mask and _saved_by_this_segmenter(capture_id)) if placed else (None, {})
    trays = []
    for p in placed:
        m = measures.get(p.tray_id)
        trays.append({
            "tray_id": p.tray_id, "slot": p.slot, "a1_corner": p.a1_corner, "placement": p.status,
            "centre_px": list(p.centre), "tilt_deg": p.tilt_deg, "margin_mm": p.margin_mm,
            "area_mm2": m.area_mm2 if m else None, "segmenter": SEGMENTER.name if m else None,
            "plant_px": m.plant_px if m else None,
            "plant_centre_px": list(m.centre_px) if m and m.centre_px else None,
            "calibration": calibration if m else None,
        })
    database.record_tray_readings(capture_id, read_at=datetime.now(UTC).isoformat(), status=status, trays=trays)
    return database.tray_readings(capture_id)


def _saved_by_this_segmenter(capture_id: int) -> bool:
    """Whether the photo's saved reading, and so its saved mask, came from `SEGMENTER`."""
    saved = database.tray_readings(capture_id)
    return bool(saved) and any(t["segmenter"] == SEGMENTER.name for t in saved["trays"])


def _measures(
    path: str, placed: list[TrayPlacement], reuse_mask: bool = False
) -> tuple[str | None, dict[int, segmentation.PlantMeasure]]:
    """The calibration used and each placed tray's plant measure, by tray ID, from the full-size
    photo's mask: the saved one with `reuse_mask`, else a new one, saved for Reprocess. Empty when
    the photo cannot be segmented: the trays are still placed."""
    try:
        record = database.captures_by_path([path])[path]
        scale_field = load_saved_calibration(record["calibration"]).scale_field
        mask = segmentation.load_mask(path) if reuse_mask else None
        if mask is not None:
            return record["calibration"], {p.tray_id: segmentation.measure_plant(mask, p.outline, scale_field) for p in placed}
        with Image.open(photo_file(path)) as image:
            # One copy of the 64MP photo (about 190 MB): convert() would make a second.
            rgb = np.asarray(image if image.mode == "RGB" else image.convert("RGB"))
        mask = SEGMENTER.segment(rgb)
        del rgb
        segmentation.save_mask(path, mask)
        return record["calibration"], {p.tray_id: segmentation.measure_plant(mask, p.outline, scale_field) for p in placed}
    except Exception:
        logger.exception("Could not work out the plant areas of %s", path)
        return None, {}


def photo_readings(path: str) -> dict | None:
    """Photo `path`'s saved tray readings (`database.tray_readings`), None when not yet read."""
    return database.tray_readings(_capture_id(path))


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
