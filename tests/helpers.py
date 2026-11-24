"""Synthetic-detection builders shared across test modules -- exact-geometry fixtures, not photos,
same convention as test_tags.py/test_calibration.py.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from npec_rig.tags import TagDetection


def square_detection(tag_id: int, cx: float, cy: float, side_px: float) -> TagDetection:
    """A synthetic axis-aligned tag of exact known pixel size, centred at (cx, cy)."""
    half = side_px / 2
    corners = (
        (cx - half, cy - half),
        (cx + half, cy - half),
        (cx + half, cy + half),
        (cx - half, cy + half),
    )
    return TagDetection(tag_id=tag_id, corners=corners, centre=(cx, cy))


_LAYOUT_30MM = Path(__file__).parent.parent / "reference/calibration-sheets/apriltags-36h11-30mm-a4-300-449.manifest.json"


def printed_sheet(
    page: int, x0: float, y0: float, px_per_mm: float, *, edge_scale: float = 1.0
) -> list[TagDetection]:
    """One printed 30 mm tag sheet as the camera would see it: every tag of `page` of the print
    layout file at its printed position times `px_per_mm`, the page's bottom-left corner at pixel
    (x0, y0) (page y is up, image y is down). `edge_scale` draws every tag edge that much too long
    or short, the fault the real photos show (metrology log 18), without moving the centres."""
    tags = json.loads(_LAYOUT_30MM.read_text())["tags"]
    return [
        printed_tag(
            t["id"], x0 + t["center_x_mm"] * px_per_mm, y0 - t["center_y_mm"] * px_per_mm,
            t["size_mm"] * px_per_mm * edge_scale,
        )
        for t in tags
        if t["page"] == page
    ]


def printed_tag(tag_id: int, cx: float, cy: float, side_px: float) -> TagDetection:
    """A tag on an upright printed page, its corners in the tag detector's order: the page's x
    direction runs from corner 1 to corner 0 (checked on real photos, `calibration.spacing_pairs`)."""
    half = side_px / 2
    corners = ((cx + half, cy - half), (cx - half, cy - half), (cx - half, cy + half), (cx + half, cy + half))
    return TagDetection(tag_id=tag_id, corners=corners, centre=(cx, cy))


def rotate_point(point: tuple[float, float], pivot: tuple[float, float], angle_deg: float) -> tuple[float, float]:
    """`point` rotated `angle_deg` clockwise in image coordinates (x right, y down) about `pivot`.

    Sign convention verified against a known synthetic rotation in test_tripwire.py, not assumed.
    """
    theta = np.radians(angle_deg)
    rotation = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    rotated = rotation @ (np.array(point) - np.array(pivot)) + np.array(pivot)
    return (float(rotated[0]), float(rotated[1]))


def rotate_detection(detection: TagDetection, pivot: tuple[float, float], angle_deg: float) -> TagDetection:
    """`detection` rigidly rotated `angle_deg` about an external `pivot` -- moves both the tag's
    position and its own orientation, as a whole-scene rotation (e.g. simulated camera roll)
    would. Use `pivot == detection.centre` to rotate a tag in place instead.
    """
    corners = tuple(rotate_point(p, pivot, angle_deg) for p in detection.corners)
    centre = rotate_point(detection.centre, pivot, angle_deg)
    return TagDetection(tag_id=detection.tag_id, corners=corners, centre=centre)


def sheet_detections(
    first_id: int, x0: float, y0: float, *, side_px: float = 120.0, columns: int = 5, rows: int = 6,
) -> list[TagDetection]:
    """One printed tag sheet as laid out in the print layout file: the page holding `first_id`,
    its first `rows` rows of `columns` tags, every tag `side_px` wide and spaced as printed at the
    same scale (side_px / 30 px/mm), its top-left tag centred at (x0, y0). Page 2 (IDs 325 to
    354) is the full 5 x 6 page."""
    tags = json.loads(_LAYOUT_30MM.read_text())["tags"]
    page = next(t["page"] for t in tags if t["id"] == first_id)
    on_page = [t for t in tags if t["page"] == page]
    xs = sorted({t["center_x_mm"] for t in on_page})
    ys = sorted({t["center_y_mm"] for t in on_page}, reverse=True)
    px_per_mm = side_px / 30.0
    return [
        printed_tag(
            t["id"], x0 + (t["center_x_mm"] - xs[0]) * px_per_mm, y0 + (ys[0] - t["center_y_mm"]) * px_per_mm, side_px
        )
        for t in on_page
        if xs.index(t["center_x_mm"]) < columns and ys.index(t["center_y_mm"]) < rows
    ]


def tray_layout_detections(
    *, shift: tuple[float, float] = (0.0, 0.0), side_px: float = 120.0
) -> list[TagDetection]:
    """12 sheets on 12 trays, 2 rows of 6 -- the tray-calibration layout. Sheets reuse the same 30
    IDs, as real reprinted sheets do; `shift` moves every sheet, as a validation round does."""
    dx, dy = shift
    return [
        d
        for row_y in (1000.0, 3500.0)
        for col in range(6)
        for d in sheet_detections(325, 800.0 + col * 1300.0 + dx, row_y + dy, side_px=side_px)
    ]


def stored_validation(
    session_id: str,
    calibration_stem: str,
    *,
    rounds: int = 3,
    inconsistent: bool = False,
    ended: bool = False,
) -> dict:
    """A validation session saved by validation_store, `rounds` counted rounds of three slots that
    read true size. `inconsistent` makes North 1 read 6 points large in the second round, past the
    2.5-point limit. `session_id` (YYYYMMDDTHHMMSSffffff) is also its start; a session with
    ROUNDS_REQUIRED rounds completes one hour after it."""
    from datetime import datetime, timedelta, timezone

    from npec_rig import validation_store

    started = datetime.strptime(session_id, "%Y%m%dT%H%M%S%f").replace(tzinfo=timezone.utc)
    names = ["North 1", "North 2", "North 3"]
    session = {
        "version": validation_store.SESSION_VERSION,
        "id": session_id,
        "calibration_stem": calibration_stem,
        "started_at": started.isoformat(),
        "completed_at": None,
        "ended_at": started.isoformat() if ended else None,
        "slots": [{"name": name} for name in names],
        "calibration_centres": [],
        "rounds": [
            {
                "capture": f"{started:%Y-%m-%d}/{i:06d}_000000",
                "captured_at": (started + timedelta(minutes=15 * i)).isoformat(),
                "counted": True,
                "slot_errors": {
                    name: [6.0 if inconsistent and i == 1 and name == "North 1" else 0.0] * 30
                    for name in names
                },
            }
            for i in range(rounds)
        ],
        "results": [],
    }
    validation_store.refresh_results(session)
    if session["completed_at"] is not None:
        session["completed_at"] = (started + timedelta(hours=1)).isoformat()
    validation_store.save_session(session)
    return session


# The benchmark plant's mint leaf colour, measured in the potato run still of 23 October 2026
# 08:35:53 UTC (tests/test_segmentation.py).
MINT_LEAF_RGB = (156, 228, 188)
# The table round the tray, below grow from leaf cores' lower cutoff: the tray finder's outline takes
# in a pixel of it, and JPEG ringing at the drawn tray's sharp corners leaves leaf-core pixels there
# (121, 145, 109) that would grow along a table of greenness 0 (#373).
TABLE_RGB = (110, 90, 90)  # greenness (180 - 200) / 290 = -0.069
DARK_SOIL_RGB = (100, 70, 65)  # greenness (140 - 165) / 235 = -0.106: well below the floor, as production's soil (#373)
# Tray plastic as the blue finder sees it (#331): OpenCV hue 110, saturation 204, value 200, inside
# the sampled tray plastic (metrology log 20).
TRAY_BLUE_RGB = (40, 90, 200)


def draw_tray(frame, x0: int, y0: int, x1: int, y1: int) -> None:
    """A blue tray top over full-size photo pixels x0 to x1, y0 to y1, for the tray finder."""
    frame[y0:y1, x0:x1] = TRAY_BLUE_RGB


def one_tray_plant_scene(monkeypatch) -> None:
    """One tray at an even 10 px/mm, for plant areas worked out by hand (#75).

    Tray 5's 40 mm tag (400 px) lies in cell A1 at the south-west of a blue tray drawn at x 115 to
    3165, y 554 to 4214 (305 x 366 mm) in a 4000 x 4400 photo, so the tray finder's outline is the
    drawn tray (#331). The photo is the table colour (TABLE_RGB) with two 500 x 300 px rectangles
    of mint leaf colour, 50 x 30 mm = 1500 mm2 each: one inside the tray (x 1400 to 1900, y 2200 to
    2500), one outside it (x 3400 to 3900); a patch of soil (x 1800 to 2800, y 3000 to 3600,
greenness -0.106), so grow from leaf cores finds a soil level, as on a real tray. Saves the calibration as the fixture's, so photos taken
    after this are read with it.
    """
    import json
    from pathlib import Path

    from npec_rig import photo_tags, validation_store
    from npec_rig.calibration import CalibrationArtifact, scale_field_from_dict
    from npec_rig.calibration_store import save_calibration
    from npec_rig.camera import CameraManager, SyntheticBackend

    class Scene(SyntheticBackend):
        def capture_full_res(self):
            frame, metadata = super().capture_full_res()
            frame[:] = TABLE_RGB
            draw_tray(frame, 115, 554, 3165, 4214)
            frame[3000:3600, 1800:2800] = DARK_SOIL_RGB  # soil showing in the tray (#373)
            frame[2200:2500, 1400:1900] = MINT_LEAF_RGB
            frame[2200:2500, 3400:3900] = MINT_LEAF_RGB
            return frame, metadata

    stem = json.loads((Path(__file__).parent / "fixtures" / "trays" / "shuffles-2026-10-20.json").read_text())["calibration"]
    save_calibration(
        CalibrationArtifact(
            created_at="2026-10-14T11:11:47+00:00",
            scale_field=scale_field_from_dict({"coeffs": [1.0, 0.0, 0.0], "mean_px_per_mm": 10.0, "residual_std_pct": 0.0}),
            frame_stem=stem, lens_position=6.05,
        ),
        stem=stem,
    )
    validation_store.save_slot_layout(stem, [{"name": "North 1", "centre": [1640, 2384], "box": [100, 500, 3200, 4300]}], [])
    tag = TagDetection(5, ((400, 3600), (800, 3600), (800, 4000), (400, 4000)), (600, 3800))
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: [tag])
    CameraManager.set_instance(CameraManager(Scene(width=4000, height=4400)))


def record_light_photos(experiment_id: int, start, series, folder: str) -> None:
    """Photos of the experiment at `start` plus each (offset, E) of `series`, exposure E at gain
    1.0, saved under `folder`, then its exclusions worked out as the rig does after a read."""
    from npec_rig import database, exclusions

    for i, (offset, e) in enumerate(series):
        database.record_capture(
            taken_at=(start + offset).isoformat(), path=f"{folder}/{i}.jpg", purpose="capture",
            experiment_id=experiment_id, calibration=None, validation=None, lens_position=None,
            focus_locked_at=None, exposure_us=e, analogue_gain=1.0, flags=[],
        )
    exclusions.update(database.captures_for_experiment(experiment_id)[-1])


# --- Trays in the table locations (#332) ----------------------------------------------------------
# A 900 x 600 photo with its corner tags at x 100 and 800, y 100 and 500: the rows of locations meet at
# y 300, the columns at x 300 and 600. TABLE_CENTRES: a point well inside each location.
TABLE_STEM = "20270101T000000000000"
TABLE_CENTRES = {"NW": (150, 150), "NM": (450, 150), "NE": (750, 150), "SW": (150, 450), "SM": (450, 450),
                 "SE": (750, 450)}


def table_calibration(px_per_mm: float = 1.0) -> None:
    """Save calibration TABLE_STEM: `px_per_mm` (1 by default), its four corner tags at the corners above."""
    from npec_rig.calibration import CalibrationArtifact, scale_field_from_dict
    from npec_rig.calibration_store import save_calibration
    from npec_rig.tripwire import CornerBaseline

    corners = {450: (100, 100), 451: (800, 100), 452: (800, 500), 453: (100, 500)}
    save_calibration(
        CalibrationArtifact(
            created_at="2027-01-01T00:00:00+00:00", frame_stem=TABLE_STEM,
            scale_field=scale_field_from_dict({"coeffs": [1.0, 0.0, 0.0], "mean_px_per_mm": px_per_mm, "residual_std_pct": 0.0}),
            corner_baseline=CornerBaseline(corners_by_id={
                i: ((x - 5, y - 5), (x + 5, y - 5), (x + 5, y + 5), (x - 5, y + 5)) for i, (x, y) in corners.items()
            }),
        ),
        stem=TABLE_STEM,
    )


def table_photo(
    experiment_id: int | None, taken, trays: dict[int, str], *, validation: str | None = None,
    centres: dict[int, tuple[float, float]] | None = None, areas: dict[int, float] | None = None,
    flags: list[str] | None = None,
) -> str:
    """A 900 x 600 photo taken at `taken` (a datetime) under TABLE_STEM, read with each tray of
    `trays` (tray ID: location) found at that location's centre, or at `centres[tray ID]` when
    given, with plant area `areas[tray ID]` mm2 by the green threshold when given; taken under
    validation session `validation`, flagged with `flags`. Its path."""
    from PIL import Image

    from npec_rig import captures, database

    day, stem = f"{taken:%Y-%m-%d}", f"{taken:%H%M%S}_{taken:%f}"
    file = captures.photos_root() / day / f"{stem}.jpg"
    file.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (900, 600)).save(file)
    capture_id = database.record_capture(
        taken_at=taken.isoformat(), path=f"rig/{day}/{stem}", purpose="capture", experiment_id=experiment_id,
        calibration=TABLE_STEM, validation=validation, lens_position=None, focus_locked_at=None, exposure_us=None,
        analogue_gain=None, flags=flags or [],
    )
    database.record_tray_readings(capture_id, read_at=taken.isoformat(), status="read", trays=[
        {"tray_id": tray_id, "slot": None, "a1_corner": None, "placement": "placed",
         "centre_px": list((centres or {}).get(tray_id, TABLE_CENTRES[location])), "tilt_deg": 0.0, "margin_mm": None, "found": "photo + tag",
         "warnings": [], "outline_px": None,
         **({"area_mm2": areas[tray_id], "segmenter": "green threshold, 0.1"} if tray_id in (areas or {}) else {})}
        for tray_id, location in trays.items()
    ])
    return f"rig/{day}/{stem}"


def banded_validation(session_id: str, bands: dict[str, tuple[tuple[float, float], float | None]], *,
                      inconsistent: bool = False) -> dict:
    """A complete validation of TABLE_STEM, saved, with one slot per entry of `bands` (slot name:
    its centre in photo pixels, and the band it reads, %). Each of its 3 rounds has 30 tags per
    slot, half reading `band` % large and half `band` % small, so each slot reads within exactly
    ±band % and its median is 0. A band of None gives the slot 3 tags a round, 9 in all, too few to be measured.
    `inconsistent` makes the first slot read 6 points large in the second round."""
    from datetime import datetime, timedelta, timezone

    from npec_rig import validation_store

    started = datetime.strptime(session_id, "%Y%m%dT%H%M%S%f").replace(tzinfo=timezone.utc)
    first = next(iter(bands))

    def errors(name: str, band: float | None, i: int) -> list[float]:
        if band is None:
            return [0.0] * 3
        shift = 6.0 if inconsistent and i == 1 and name == first else 0.0
        return [band + shift] * 15 + [-band + shift] * 15

    session = {
        "version": validation_store.SESSION_VERSION, "id": session_id, "calibration_stem": TABLE_STEM,
        "started_at": started.isoformat(), "completed_at": None, "ended_at": None,
        "slots": [{"name": name, "centre": list(centre), "box": [centre[0] - 50, centre[1] - 50, centre[0] + 50, centre[1] + 50]}
                  for name, (centre, _band) in bands.items()],
        "calibration_centres": [],
        "rounds": [
            {"capture": f"{started:%Y-%m-%d}/{i:06d}_000000",
             "captured_at": (started + timedelta(minutes=15 * i)).isoformat(), "counted": True,
             "slot_errors": {name: errors(name, band, i) for name, (_centre, band) in bands.items()}}
            for i in range(3)
        ],
        "results": [],
    }
    validation_store.refresh_results(session)
    validation_store.save_session(session)
    return session


def export_built(client, experiment_id: int, choice: dict | None = None, timeout_s: float = 60) -> dict:
    """Export through the page's route and wait, as the page does, until its data file is built
    in the background (#437): the export with its parts."""
    import time

    started = client.post(f"/api/experiments/{experiment_id}/export", json=choice)
    assert started.status_code == 200, started.text
    export_id = started.json()["id"]
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        export = client.get(f"/api/exports/{export_id}").json()
        if export["finished_at"]:
            return export
        time.sleep(0.02)
    raise AssertionError(f"export {export_id} not built in {timeout_s} s")


# --- Time lapse frames (#64) -----------------------------------------------------------------
def turned_tray_photo(experiment_id: int, taken, tray_id: int = 4, calibration: str | None = None) -> None:
    """A 1000 x 1000 photo of tray 4 lying turned 180 degrees, at 2 px/mm: its 610 x 732 px outline
    at x 100 to 710, y 100 to 832, its 4 x 5 cells read, a red patch on cell A1, a blue one on D5
    (time lapse frames, #64). `taken` is a datetime."""
    from PIL import Image

    from npec_rig import captures, database

    def cell(name: str, holds: str, x: float, y: float) -> dict:
        return {"cell": name, "holds": holds, "centre_px": [x, y],
                "corners_px": [[x - 60, y - 60], [x + 60, y - 60], [x + 60, y + 60], [x - 60, y + 60]],
                "plant_px": 100, "area_mm2": 100.0, "over_other_cells": False}

    def in_photo(ux: float, uy: float) -> tuple[float, float]:  # upright frame pixels to the photo
        return 710 - ux, 832 - uy

    cells = []
    for i, col in enumerate("ABCD"):
        for j in range(5):
            x, y = in_photo((i + 0.5) * 152.5, 732 - (j + 0.5) * 146.4)
            cells.append(cell(f"{col}{j + 1}", "tag" if (col, j) == ("A", 0) else "plant", x, y))
    image = Image.new("RGB", (1000, 1000), (128, 128, 128))
    a1, d5 = in_photo(76.25, 658.8), in_photo(533.75, 73.2)
    image.paste((255, 0, 0), (int(a1[0]) - 20, int(a1[1]) - 20, int(a1[0]) + 20, int(a1[1]) + 20))
    image.paste((0, 0, 255), (int(d5[0]) - 20, int(d5[1]) - 20, int(d5[0]) + 20, int(d5[1]) + 20))
    day, stem = f"{taken:%Y-%m-%d}", f"{taken:%H%M%S}_{taken:%f}"
    (captures.photos_root() / day).mkdir(parents=True, exist_ok=True)
    image.save(captures.photos_root() / day / f"{stem}.jpg", quality=95)
    capture_id = database.record_capture(
        taken_at=taken.isoformat(), path=f"rig/{day}/{stem}", purpose="capture", experiment_id=experiment_id,
        calibration=calibration, validation=None, lens_position=None, focus_locked_at=None, exposure_us=None,
        analogue_gain=None, flags=[],
    )
    database.record_tray_readings(capture_id, read_at=taken.isoformat(), status="read", trays=[{
        "tray_id": tray_id, "slot": None, "a1_corner": "NE", "placement": "placed", "centre_px": [405, 466],
        "tilt_deg": 180.0, "margin_mm": None, "found": "photo + tag", "warnings": [],
        "outline_px": [[100, 100], [710, 100], [710, 832], [100, 832]], "area_mm2": 1000.0,
        "segmenter": "green threshold, 0.1", "cells": cells,
    }])
    database.record_exclusions([{"capture_id": capture_id, "name": None, "norm_e": None, "limit_fraction": None}],
                               worked_out_at=taken.isoformat())


@contextmanager
def lock_held(seconds: float = 5.0, *, until: threading.Event | None = None, readers_too: bool = False) -> Iterator[None]:
    """Another connection holds rig.db's write lock for `seconds`, or until `until` is set, as
    Reprocess or a purge does (#439). With `readers_too`, reads wait as well (the lock at a commit)."""
    from npec_rig import database
    from npec_rig.settings import db_path

    database.list_experiments()  # the file exists and is migrated before the lock is taken
    taken = threading.Event()

    def hold() -> None:
        conn = sqlite3.connect(db_path(), isolation_level=None)
        if readers_too:
            # rig.db is in WAL mode (images.py), where nothing blocks a reader: the rollback journal does.
            conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("BEGIN EXCLUSIVE" if readers_too else "BEGIN IMMEDIATE")
        taken.set()
        if until is None:
            time.sleep(seconds)
        else:
            until.wait(seconds)
        conn.execute("COMMIT")
        if readers_too:
            conn.execute("PRAGMA journal_mode=WAL")
        conn.close()

    thread = threading.Thread(target=hold)
    thread.start()
    taken.wait(5)
    try:
        yield
    finally:
        if until is None:
            thread.join()
