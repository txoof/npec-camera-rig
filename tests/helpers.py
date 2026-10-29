"""Synthetic-detection builders shared across test modules -- exact-geometry fixtures, not photos,
same convention as test_tags.py/test_calibration.py.
"""

from __future__ import annotations

import json
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
    drawn tray (#331). The photo is grey with two 500 x 300 px rectangles
    of mint leaf colour, 50 x 30 mm = 1500 mm2 each: one inside the tray (x 1400 to 1900, y 2200 to
    2500), one outside it (x 3400 to 3900). Saves the calibration as the fixture's, so photos taken
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
            frame[:] = 128
            draw_tray(frame, 115, 554, 3165, 4214)
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
