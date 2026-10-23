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


def read_photo(path: str) -> dict:
    """Read gallery photo `path` for its trays, save the reading (replacing any earlier one) and
    return it as `photo_readings` would. The tags are searched once per photo (photo_tags)."""
    capture_id = _capture_id(path)
    tags = photo_tags.photo_tags_for(path)
    # No tag of any kind, as with the lights off (metrology log 15.5l): not trays missing.
    status, placed = placements(path, tags) if tags else ("no tags found", [])
    areas = _areas(path, placed) if placed else {}
    trays = [
        {
            "tray_id": p.tray_id, "slot": p.slot, "a1_corner": p.a1_corner, "placement": p.status,
            "centre_px": list(p.centre), "tilt_deg": p.tilt_deg, "margin_mm": p.margin_mm,
            "area_mm2": areas.get(p.tray_id), "segmenter": SEGMENTER.name if p.tray_id in areas else None,
        }
        for p in placed
    ]
    database.record_tray_readings(capture_id, read_at=datetime.now(UTC).isoformat(), status=status, trays=trays)
    return database.tray_readings(capture_id)


def _areas(path: str, placed: list[TrayPlacement]) -> dict[int, float]:
    """Each placed tray's plant area in mm2, by tray ID, from the full-size photo's mask, which is
    saved for Reprocess. Empty when the photo cannot be segmented: the trays are still placed."""
    try:
        record = database.captures_by_path([path])[path]
        scale_field = load_saved_calibration(record["calibration"]).scale_field
        with Image.open(photo_file(path)) as image:
            # One copy of the 64MP photo (about 190 MB): convert() would make a second.
            rgb = np.asarray(image if image.mode == "RGB" else image.convert("RGB"))
        mask = SEGMENTER.segment(rgb)
        del rgb
        segmentation.save_mask(path, mask)
        return {p.tray_id: segmentation.plant_area_mm2(mask, p.outline, scale_field) for p in placed}
    except Exception:
        logger.exception("Could not work out the plant areas of %s", path)
        return {}


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
