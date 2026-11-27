"""Readings per tray per photo (#222): each photo read once for its trays, and saved.

The tags are the real detections of still 080357_563754 (layout 2 of 20 October, metrology log
15.5l) with their calibration's scale field and slot layout; the expected slots and corners are
the printed shuffle map, as in tests/test_tray_placement.py.
"""

import json
import logging
import threading
import time
from pathlib import Path

import pytest
from PIL import Image
from fastapi.testclient import TestClient

from npec_rig import captures, database, photo_tags, settings, tray_readings, validation_store
from npec_rig.app import app
from npec_rig.calibration import CalibrationArtifact, scale_field_from_dict
from npec_rig.calibration_store import save_calibration
from npec_rig.tags import TagDetection
from tests.helpers import (
    DARK_SOIL_RGB, MINT_LEAF_RGB, TABLE_RGB, banded_validation, draw_tray, lock_held,
    table_calibration, table_photo,
)

pytestmark = pytest.mark.unit

# Every scene below is drawn at 5 px/mm, half the 10 px/mm the rig works at, so a photo holds a
# quarter of the pixels and the segmentation these tests drive 77 times does a quarter of the
# work (#547). Each scene saves its own calibration at SCENE_PX_PER_MM, so every **millimetre**
# value in this file is the same as it was at 10 px/mm; a **pixel** coordinate is half of what it
# was and a **pixel count** a quarter. The one exception is `_matted_tray_scene`, whose soil and
# mat blocks were moved onto the JPEG 8 x 8 grid and so are not exactly a quarter: see the comment
# there and metrology log 53.
#
# The sizes were checked against the fixed pixel thresholds the code has: GROWN_WHITE_MIN_PX and
# GROWN_WHITE_WIDEN_PX (no scene here holds white), the 3 x 3 opening of the tray finder's rim
# mask (no rim: trays are drawn as flat blue) and segmentation._SCALE_BLOCK_PX (every scale field
# here is uniform). Every other threshold in segmentation.py and tray_placement.py is a fraction
# of the tray's own size, so it scales with the scene. The tray finder still works on a
# quarter-size copy (tray_readings.FINDER_FACTOR), so its 4-pixel step is 0.8 mm here instead of
# 0.4 mm: the two tolerances written in millimetres are doubled; those written in pixels, and all
# the areas, are unchanged.
SCENE_PX_PER_MM = 5.0

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "trays" / "shuffles-2026-10-20.json").read_text())

LAYOUT_2 = {
    3: ("North 1", "SW"), 10: ("North 2", "SW"), 6: ("North 3", "SW"), 1: ("North 4", "NE"),
    4: ("North 5", "SW"), 12: ("North 6", "NE"), 9: ("South 1", "NE"), 11: ("South 2", "SW"),
    7: ("South 3", "NE"), 8: ("South 4", "SW"), 5: ("South 5", "SW"), 2: ("South 6", "SW"),
}


@pytest.fixture(autouse=True)
def isolated_photos_and_calibration(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("NPEC_RIG_PHOTOS_DIR", str(tmp_path / "rig"))
    monkeypatch.setenv("NPEC_RIG_CALIBRATION_DIR", str(tmp_path / "calibration"))


def _calibrate(with_layout: bool = True) -> None:
    stem = FIXTURE["calibration"]
    save_calibration(
        CalibrationArtifact(created_at="2026-10-14T11:11:47+00:00", scale_field=scale_field_from_dict(FIXTURE["scale_field"]),
                            frame_stem=stem, lens_position=6.05),
        stem=stem,
    )
    if with_layout:
        validation_store.save_slot_layout(stem, FIXTURE["slots"], [])


def _finds(monkeypatch: pytest.MonkeyPatch, still: str | None) -> None:
    tags = [
        TagDetection(t["id"], tuple(tuple(c) for c in t["corners"]),
                     (sum(c[0] for c in t["corners"]) / 4, sum(c[1] for c in t["corners"]) / 4))
        for t in (FIXTURE["stills"][still] if still else [])
    ]
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: tags)


def _photo() -> str:
    _array, record = captures.take_photo("capture")
    del _array
    return record["path"]


def _save_scene_calibration(
    px_per_mm: float = SCENE_PX_PER_MM, stem: str | None = None,
    created_at: str = "2026-10-14T11:11:47+00:00", **kwargs,
) -> None:
    """The fixture's calibration saved at `px_per_mm`, the scale every scene here is drawn at."""
    stem = stem or FIXTURE["calibration"]
    save_calibration(
        CalibrationArtifact(
            created_at=created_at, frame_stem=stem, lens_position=6.05,
            scale_field=scale_field_from_dict(
                {"coeffs": [1.0, 0.0, 0.0], "mean_px_per_mm": px_per_mm, "residual_std_pct": 0.0}),
            **kwargs,
        ),
        stem=stem,
    )


def _plant_scene(monkeypatch) -> None:
    """One tray at an even SCENE_PX_PER_MM, for plant areas worked out by hand (#75).

    This file's own half-scale twin of `tests.helpers.one_tray_plant_scene`, which other test
    files still use at 10 px/mm; every millimetre below is the same as that one's.

    Tray 5's 40 mm tag (200 px) lies in cell A1 at the south-west of a blue tray drawn at x 57 to
    1582, y 277 to 2107 (305 x 366 mm) in a 2000 x 2200 photo, so the tray finder's outline is the
    drawn tray (#331). The photo is the table colour (TABLE_RGB) with two 250 x 150 px rectangles
    of mint leaf colour, 50 x 30 mm = 1500 mm2 each: one inside the tray (x 700 to 950, y 1100 to
    1250), one outside it (x 1700 to 1950); a patch of soil (x 900 to 1400, y 1500 to 1800,
    greenness -0.106), so grow from leaf cores finds a soil level, as on a real tray. Saves the
    calibration as the fixture's, so photos taken after this are read with it.
    """
    from npec_rig.camera import CameraManager, SyntheticBackend

    class Scene(SyntheticBackend):
        def capture_full_res(self):
            frame, metadata = super().capture_full_res()
            frame[:] = TABLE_RGB
            draw_tray(frame, 57, 277, 1582, 2107)
            frame[1500:1800, 900:1400] = DARK_SOIL_RGB  # soil showing in the tray (#373)
            frame[1100:1250, 700:950] = MINT_LEAF_RGB
            frame[1100:1250, 1700:1950] = MINT_LEAF_RGB
            return frame, metadata

    _save_scene_calibration()
    validation_store.save_slot_layout(
        FIXTURE["calibration"], [{"name": "North 1", "centre": [820, 1192], "box": [50, 250, 1600, 2150]}], [])
    tag = TagDetection(5, ((200, 1800), (400, 1800), (400, 2000), (200, 2000)), (300, 1900))
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: [tag])
    CameraManager.set_instance(CameraManager(Scene(width=2000, height=2200)))


def test_a_photo_is_read_for_its_trays_and_the_reading_is_saved(monkeypatch) -> None:
    _calibrate()
    _finds(monkeypatch, "080357_563754")
    path = _photo()

    readings = tray_readings.read_photo(path)
    assert readings["status"] == "read"
    # A grey photo, no tray found in it (#331): each tray tag is seen where it lies.
    assert sorted(t["tray_id"] for t in readings["trays"]) == sorted(LAYOUT_2)
    assert {(t["found"], t["slot"], t["outline_px"], t["area_mm2"]) for t in readings["trays"]} == {("tag only", None, None, None)}
    assert tray_readings.photo_readings(path) == readings


def test_a_photo_without_a_calibration_is_read_with_no_trays_and_says_why(monkeypatch) -> None:
    _finds(monkeypatch, "080357_563754")
    path = _photo()

    readings = tray_readings.read_photo(path)
    assert (readings["status"], readings["trays"]) == ("no calibration", [])


def test_a_photo_is_read_with_a_calibration_alone_with_no_slot_layout(monkeypatch) -> None:
    """Trays can lie anywhere on the table; slots will not always exist (Aaron, #331)."""
    tag = TagDetection(5, ((1400, 300), (1600, 300), (1600, 500), (1400, 500)), (1500, 400))
    _blue_tray_scene(monkeypatch, [tag])
    # A newer calibration at the same scale, never given a slot layout: the photo's own.
    _save_scene_calibration(stem="20261029T100000000000", created_at="2026-10-29T10:00:00+00:00")

    readings = tray_readings.read_photo(_photo())
    assert readings["status"] == "read"
    assert [(t["tray_id"], t["found"], t["slot"]) for t in readings["trays"]] == [(5, "photo + tag", None)]


def test_a_photo_not_yet_read_has_no_readings(monkeypatch) -> None:
    _calibrate()
    assert tray_readings.photo_readings(_photo()) is None


def _wait_for(condition, timeout_s: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.02)


def test_the_background_reader_reads_new_photos_and_the_running_experiments_but_not_older_ones(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(tray_readings, "POLL_S", 0.05)
    monkeypatch.setenv("NPEC_RIG_EXPERIMENTS_DIR", str(tmp_path / "experiments"))
    _calibrate()
    _finds(monkeypatch, "080357_563754")
    older = _photo()  # a rig photo from before the reader: read only when asked
    client = TestClient(app)  # not started as a context: no reader or scheduler of its own
    experiment = client.post("/api/experiments", json={}).json()
    client.post(f"/api/experiments/{experiment['id']}/start")
    before = _photo()  # before the reader, but its experiment is running

    reader = tray_readings.TrayReader()
    reader.start()
    try:
        after = _photo()
        _wait_for(lambda: all(tray_readings.photo_readings(p) for p in (before, after)))
    finally:
        reader.stop(timeout_s=5)
    assert all(len(tray_readings.photo_readings(p)["trays"]) == 12 for p in (before, after))
    assert tray_readings.photo_readings(older) is None


def test_a_photo_with_no_tray_and_no_tag_says_so(monkeypatch) -> None:
    """As with the lights off (metrology log 15.5l, 20.1): not every tray missing (#331)."""
    _calibrate()
    _finds(monkeypatch, None)

    assert tray_readings.read_photo(_photo())["status"] == "no trays found"


def test_each_tray_gets_its_plant_area_in_mm2_and_the_segmenter_that_made_it(monkeypatch) -> None:
    """A worked example, not the code's own sum (`_plant_scene`): a 250 x 150 px mint rectangle
    inside the tray at 5 px/mm is 50 x 30 mm = 1500 mm2. The one outside the tray must not
    count."""
    _plant_scene(monkeypatch)

    tray = tray_readings.read_photo(_photo())["trays"][0]
    assert tray["tray_id"] == 5
    assert tray["area_mm2"] == pytest.approx(1500, rel=0.01)  # 1%: JPEG blurs the rectangle's edge
    assert tray["segmenter"] == "green threshold, 0.1"


def test_each_trays_area_keeps_its_plant_pixel_count_centre_and_calibration(monkeypatch) -> None:
    """The raw measurement under the mm2 (Aaron, 2026-10-23), so another calibration can be applied
    later: `_plant_scene`'s rectangle inside the tray is 250 x 150 = 37,500 px, centred at
    x 825, y 1175 (from its corners, x 700 to 950 and y 1100 to 1250)."""
    _plant_scene(monkeypatch)

    tray = tray_readings.read_photo(_photo())["trays"][0]
    assert tray["plant_px"] == pytest.approx(37_500, rel=0.01)  # 1%: JPEG blurs the edge
    assert tray["plant_centre_px"] == pytest.approx([825, 1175], abs=2)
    assert tray["calibration"] == FIXTURE["calibration"]


@pytest.mark.parametrize(("width", "height", "past_mm", "partly_outside"), [(1507, 2200, 15, True), (2000, 2082, 5, False)])
def test_a_tray_more_than_13_mm_past_the_photo_edge_is_marked_partly_outside(
    monkeypatch, width, height, past_mm, partly_outside
) -> None:
    """#282 item 1: `_plant_scene`'s tray outline reaches x 1582 and y 2107 at 5 px/mm.
    In a photo 1507 px wide its east side is 75 px (15 mm) past the edge; in one 2082 px high
    its south side is 25 px (5 mm) past. Marked only beyond 13 mm, the widest measured outer wall:
    up to there only wall is outside, beyond it plants can be (a decision, Aaron, 2026-10-27)."""
    from npec_rig.camera import CameraManager, SyntheticBackend

    _plant_scene(monkeypatch)

    class Scene(SyntheticBackend):
        def capture_full_res(self):
            frame, metadata = super().capture_full_res()
            frame[:] = 128
            draw_tray(frame, 57, 277, 1582, 2107)
            frame[1100:1250, 700:950] = MINT_LEAF_RGB
            return frame, metadata

    CameraManager.set_instance(CameraManager(Scene(width=width, height=height)))

    tray = tray_readings.read_photo(_photo())["trays"][0]
    # 1 mm: the tray finder works on a quarter-size copy, so its outline sits to about 4 px, which
    # is 0.8 mm at this scene's 5 px/mm (it was 0.5 mm, 4 px at 10 px/mm, before #547).
    assert tray["outside_mm"] == pytest.approx(past_mm, abs=1.0)
    assert tray["partly_outside"] is partly_outside


def test_a_tray_read_before_the_photo_edge_was_checked_is_not_marked_either_way(monkeypatch) -> None:
    """#282 item 1: a reading saved without `outside_mm`, as every photo read before it, says
    nothing about the photo edge (None), not that the tray lies inside (False)."""
    _calibrate()
    path = _photo()
    tray = {"tray_id": 5, "slot": "North 1", "a1_corner": "SW", "placement": "placed",
            "centre_px": [820, 1192], "tilt_deg": 0.0, "margin_mm": 300.0, "area_mm2": 1500.0,
            "segmenter": "green threshold, 0.1"}
    database.record_tray_readings(
        database.captures_by_path([path])[path]["id"], read_at="2026-10-27T12:00:00+00:00", status="read", trays=[tray]
    )

    saved = tray_readings.photo_readings(path)["trays"][0]
    assert (saved["outside_mm"], saved["partly_outside"]) == (None, None)


def _two_touching_trays_scene(monkeypatch) -> None:
    """Two trays touching, in a 3200 x 2200 photo, with plant on the strip their outlines share.

    The blue tops are drawn as two blocks, x 272 to 1372 and x 1472 to 2572, both y 276 to 2108,
    with 100 px (20 mm) of table colour between them: the two trays' rims, as a photo of touching
    trays shows them. Every edge is a multiple of 4, the tray finder's
    `tray_readings.FINDER_FACTOR`, so the quarter-size copy the finder works on holds whole blue
    columns and no part-blue column, and each block's centre lands with nothing rounded away:
    (272 + 1372 - 4) / 2 = x 820.0 and (1472 + 2572 - 4) / 2 = x 2020.0, both at
    (276 + 2108 - 4) / 2 = y 1190.0.

    Placement gives every tray the measured outside size, 305 x 366 mm (`TRAY_SIZE_MM`), which at
    this file's 5 px/mm is 1525 x 1830 px, around the centre found for it. The blue tops are
    narrower than that -- 1100 px of blue and 100 px of rim is a pitch of 1200 px where 1525 px is
    the tray's outside width -- so the two outlines overlap: tray 5's is x 57.5 to 1582.5 and
    tray 7's x 1257.5 to 2782.5, sharing the strip x 1257.5 to 1582.5 (325 px, 65 mm). This is
    what `segmentation.measure_trays` is written for: a pixel in the strip lies inside both
    outlines, and must be counted once.

    A 250 x 150 px mint rectangle at x 1270 to 1520, y 1100 to 1250 (50 x 30 mm, 1500 mm2) lies
    wholly inside that strip, so every one of its pixels is disputed. The rule is that a pixel
    goes to the tray whose centre is nearer its middle, x + 0.5; the point midway between the
    centres is (820 + 2020) / 2 = x 1420.0, so

        tray 5: columns 1270 to 1419, 150 x 150 px = 22,500 px / 25 px2 per mm2 = 900 mm2
        tray 7: columns 1420 to 1519, 100 x 150 px = 15,000 px / 25 px2 per mm2 = 600 mm2

    (column 1419's middle, 1419.5, is west of 1420). The 60/40 split is deliberate: a rule that
    gave each tray the far half of the strip instead would return 600/900, which neither 1% band
    admits and the ordering assertion rejects. With the plant inside the strip the whole 1500 mm2
    is decided by the rule, not by where the outlines end (#547 review).

    Tag 5 lies at x 300 and tag 7 at x 2545, each inside its own tray's outline and outside the
    other's, so the two trays are named apart and neither is read as carrying both tags."""
    from npec_rig.camera import CameraManager, SyntheticBackend

    _plant_scene(monkeypatch)

    class Scene(SyntheticBackend):
        def capture_full_res(self):
            frame, metadata = super().capture_full_res()
            frame[:] = 128
            draw_tray(frame, 272, 276, 1372, 2108)  # tray 5's blue top
            draw_tray(frame, 1472, 276, 2572, 2108)  # tray 7's, 100 px of rim away
            frame[1100:1250, 1270:1520] = MINT_LEAF_RGB  # wholly inside the strip the outlines share
            return frame, metadata

    stem = FIXTURE["calibration"]
    validation_store.save_slot_layout(
        stem,
        [{"name": "North 1", "centre": [820, 1190], "box": [50, 270, 1590, 2110]},
         {"name": "North 2", "centre": [2020, 1190], "box": [1250, 270, 2790, 2110]}],
        [],
    )
    tags = [TagDetection(5, ((200, 1800), (400, 1800), (400, 2000), (200, 2000)), (300, 1900)),
            TagDetection(7, ((2445, 1800), (2645, 1800), (2645, 2000), (2445, 2000)), (2545, 1900))]
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: tags)
    CameraManager.set_instance(CameraManager(Scene(width=3200, height=2200)))


def test_plant_in_the_strip_touching_trays_share_is_counted_once_for_the_nearer_tray(monkeypatch) -> None:
    """#282, the rule of 2026-10-23 (Aaron): the two trays' areas add up to the plant, 1500 mm2,
    not more, and each tray has its own part (`_two_touching_trays_scene`)."""
    _two_touching_trays_scene(monkeypatch)

    trays = {t["tray_id"]: t for t in tray_readings.read_photo(_photo())["trays"]}
    assert trays[5]["area_mm2"] + trays[7]["area_mm2"] == pytest.approx(1500, rel=0.01)  # 1%: JPEG blur
    assert trays[5]["area_mm2"] == pytest.approx(900, rel=0.01)  # see `_two_touching_trays_scene`
    assert trays[7]["area_mm2"] == pytest.approx(600, rel=0.01)
    # The nearer tray gets the larger share: this is the half of the test its name is for.
    assert trays[5]["area_mm2"] > trays[7]["area_mm2"]


def test_a_photo_takes_its_area_from_the_rebuilt_twin_of_its_calibration(monkeypatch) -> None:
    """Part B, test point 2 (#286). `_plant_scene`: 37,500 plant px under a calibration of
    5.0 px/mm, 1500 mm2. A twin rebuilt from that calibration at 5.0 x 5.00 / 4.90 px/mm (the
    ratio of tag spacing to tag edges agreed for this test) gives 1500 x (4.90 / 5.00)^2 =
    1440.6 mm2. The photo's own record still names the original calibration."""
    from npec_rig.calibration import CalibrationArtifact, ScaleField

    _plant_scene(monkeypatch)
    path = _photo()
    stem = FIXTURE["calibration"]
    assert tray_readings.read_photo(path)["trays"][0]["area_mm2"] == pytest.approx(1500, rel=0.01)

    save_calibration(
        CalibrationArtifact(
            created_at="2026-10-26T15:00:00+00:00",
            scale_field=ScaleField((1.0, 0.0, 0.0), SCENE_PX_PER_MM * 5.00 / 4.90, 0.0),
            frame_stem=stem, lens_position=6.05, rebuilt_from=stem,
        ),
        stem="20261026T150000000000", promote=False,
    )
    tray = tray_readings.read_photo(path)["trays"][0]

    assert tray["area_mm2"] == pytest.approx(1440.6, rel=0.01)  # 1%: JPEG blurs the edge
    assert database.captures_by_path([path])[path]["calibration"] == stem


def _camera_reports(monkeypatch, exposure_us: int, gain: float, ae_state: int = 2) -> None:
    """The synthetic camera, reporting the exposure and gain of a real photo, and its
    auto-exposure state (libcamera's AeState, 2 converged, 1 searching; #382)."""
    from npec_rig.camera import CameraManager, SyntheticBackend

    class Reports(SyntheticBackend):
        def capture_full_res(self):
            frame, metadata = super().capture_full_res()
            return frame, {**metadata, "ExposureTime": exposure_us, "AnalogueGain": gain, "AeState": ae_state}

    CameraManager.set_instance(CameraManager(Reports()))


def test_a_photo_taken_with_the_lights_off_is_excluded_from_its_exposure_and_gain(monkeypatch) -> None:
    """Exposure and gain of real photos of experiment 18 (rig.db, 2026-10-26): lights off at
    23:28:53 UTC on 22 October, 64,022 us at gain 4.0; lit at 08:41:20, 5,404 us at gain 1.0.
    The dark one as the camera reports it since #382: auto-exposure still searching, as every
    dark photo on the development rig (metrology log 29.3)."""
    _calibrate()
    _finds(monkeypatch, None)
    _camera_reports(monkeypatch, 64_022, 4.0, ae_state=1)
    dark = _photo()
    _camera_reports(monkeypatch, 5_404, 1.0)
    lit = _photo()

    for path in (dark, lit):
        tray_readings.read_photo(path)
    assert tray_readings.photo_readings(dark)["exclusion"] == "lights off"
    assert tray_readings.photo_readings(lit)["exclusion"] is None


def test_a_photo_with_auto_exposure_off_is_counted_but_says_the_lights_were_not_checked(monkeypatch) -> None:
    """#507: with auto exposure off libcamera reports AeState 0, idle, and the rig cannot tell a
    lights-off photo. Aaron's decision (question 1): its areas stay counted, with a warning. A
    searching or converged camera was checking the light, and a photo with no recorded state
    gets no warning (it keeps the rule from its exposure and gain)."""
    _calibrate()
    _finds(monkeypatch, None)
    paths = {}
    for name, state in (("idle", 0), ("searching", 1), ("converged", 2), ("none", None)):
        _camera_reports(monkeypatch, 5_404, 1.0, ae_state=state)
        paths[name] = _photo()
        tray_readings.read_photo(paths[name])

    readings = {name: tray_readings.photo_readings(path) for name, path in paths.items()}
    assert {name: r["lights_checked"] for name, r in readings.items()} == {
        "idle": False, "searching": True, "converged": True, "none": True}
    assert readings["idle"]["exclusion"] is None


def test_each_trays_area_carries_the_floor_below_which_it_means_nothing_detected(monkeypatch) -> None:
    """100 mm2 for the green threshold: Aaron's starting value (2026-10-26), from empty trays
    reading up to 98 mm2 (metrology log 17.4); checked in #293."""
    _plant_scene(monkeypatch)

    tray = tray_readings.read_photo(_photo())["trays"][0]
    assert tray["floor_mm2"] == 100


def test_each_photos_exclusion_is_stored_and_earlier_photos_are_checked_again_as_new_ones_come(
    monkeypatch, tmp_path
) -> None:
    """#288, #382: photos read at 5,000, 6,000 and then 7,000 us. While 6,000 is the newest it has
    no photo after it and no exclusion; once 7,000 is read, 6,000 lies between its neighbours, so
    the auto-exposure is still moving: "light changing", as the Gallery and export get it."""
    monkeypatch.setenv("NPEC_RIG_EXPERIMENTS_DIR", str(tmp_path / "experiments"))
    _calibrate()
    _finds(monkeypatch, None)
    client = TestClient(app)
    experiment = client.post("/api/experiments", json={}).json()
    client.post(f"/api/experiments/{experiment['id']}/start")

    def taken(exposure_us: int) -> str:
        _camera_reports(monkeypatch, exposure_us, 1.0)
        path = _photo()
        tray_readings.read_photo(path)
        return path

    taken(5_000)
    middle = taken(6_000)
    assert tray_readings.photo_readings(middle)["exclusion"] is None
    taken(7_000)
    assert tray_readings.photo_readings(middle)["exclusion"] == "light changing"


def _two_trays_with_one_tag_scene(monkeypatch) -> None:
    """`_plant_scene` with three trays side by side in a 4800 x 2200 photo, at 5 px/mm: two carry
    tag 1, the third tag 7. Tag centres x 300, 1812.5 and 3325, so the outlines are x 57 to 1582,
    1570 to 3095 and 3082.5 to 4607.5, 1512.5 px apart. Each
    holds a mint rectangle 150 px tall, clear of the strips the outlines share: 250 px wide in the
    first (1500 mm2), 125 px in the second (750 mm2), 250 px in the third (1500 mm2)."""
    from npec_rig.camera import CameraManager, SyntheticBackend

    _plant_scene(monkeypatch)

    class Scene(SyntheticBackend):
        def capture_full_res(self):
            frame, metadata = super().capture_full_res()
            frame[:] = 128
            draw_tray(frame, 57, 277, 4607, 2107)  # three trays touching: one blue piece
            frame[1100:1250, 700:950] = MINT_LEAF_RGB
            frame[1100:1250, 2200:2325] = MINT_LEAF_RGB
            frame[1100:1250, 3725:3975] = MINT_LEAF_RGB
            return frame, metadata

    validation_store.save_slot_layout(
        FIXTURE["calibration"],
        [{"name": "North 1", "centre": [820, 1192], "box": [50, 250, 1600, 2150]},
         {"name": "North 2", "centre": [2332.5, 1192], "box": [1562.5, 250, 3112.5, 2150]},
         {"name": "North 3", "centre": [3845, 1192], "box": [3075, 250, 4625, 2150]}],
        [],
    )
    tags = [TagDetection(tag_id, ((x - 100, 1800), (x + 100, 1800), (x + 100, 2000), (x - 100, 2000)), (x, 1900))
            for tag_id, x in ((1, 300), (1, 1812.5), (7, 3325))]
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: tags)
    CameraManager.set_instance(CameraManager(Scene(width=4800, height=2200)))


def test_two_trays_with_the_same_tag_each_keep_their_own_area_and_neither_is_counted(monkeypatch) -> None:
    """#302, decided by Aaron 2026-10-27: both trays' areas are saved and marked not counted, with
    the reason; the other trays count as normal (`_two_trays_with_one_tag_scene`)."""
    _two_trays_with_one_tag_scene(monkeypatch)

    trays = tray_readings.read_photo(_photo())["trays"]
    ones = sorted((t for t in trays if t["tray_id"] == 1), key=lambda t: t["area_mm2"])
    assert [t["area_mm2"] for t in ones] == [pytest.approx(750, rel=0.01), pytest.approx(1500, rel=0.01)]
    assert [t["not_counted"] for t in ones] == [["2 trays carry tag 1"]] * 2
    (seven,) = [t for t in trays if t["tray_id"] == 7]
    assert seven["not_counted"] == []


def test_a_tag_two_trays_carry_is_left_out_of_the_photos_areas_for_chamber_activity(monkeypatch) -> None:
    """#302: the areas the visit check judges (`exclusions.visits`) hold only the trays that count:
    tray 7, not either tray 1 (`_two_trays_with_one_tag_scene`)."""
    _two_trays_with_one_tag_scene(monkeypatch)
    experiment = captures.start_experiment(captures.create_experiment()["id"])
    path = _photo()
    tray_readings.read_photo(path)

    capture_id = database.captures_by_path([path])[path]["id"]
    areas = database.experiment_tray_areas(experiment["id"])
    assert list(areas) == [capture_id]
    assert areas[capture_id] == {7: pytest.approx(1500, rel=0.01)}


def _two_trays_in_one_slot_scene(monkeypatch) -> None:
    """`_two_trays_with_one_tag_scene` with tags 5 and 13 in place of the two tag 1s, tag 13 lying
    150 px (30 mm) east of tag 5: a loose tag on tray 5 (metrology log 17.12). Both tags lie in the
    first tray's outline (#331); tray 7 is alone in the third."""
    _two_trays_with_one_tag_scene(monkeypatch)
    tags = [TagDetection(tag_id, ((x - 100, 1800), (x + 100, 1800), (x + 100, 2000), (x - 100, 2000)), (x, 1900))
            for tag_id, x in ((5, 300), (13, 450), (7, 3325))]
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: tags)


def test_two_tags_in_one_tray_outline_are_both_marked_not_counted(monkeypatch) -> None:
    """#315, decided by Aaron 2026-10-28, for trays found in the photo (#331): two tags in one
    outline give it to two trays, which would count its plant twice, so neither counts, in this
    photo; the other trays count as normal."""
    _two_trays_in_one_slot_scene(monkeypatch)

    trays = {t["tray_id"]: t for t in tray_readings.read_photo(_photo())["trays"]}
    assert trays[5]["not_counted"] == ["2 tags in one tray outline"]
    assert trays[13]["not_counted"] == ["2 tags in one tray outline"]
    assert trays[7]["not_counted"] == []


def test_a_photo_with_two_tags_in_one_tray_outline_is_left_out_whole_as_chamber_activity(monkeypatch) -> None:
    """#315, decided by Aaron 2026-10-28: a loose tag on a tray, or a tray carried over the table
    (metrology log 17.12), is too abnormal to measure, so the whole photo is a visit, as for any
    chamber activity; with trays found in the photo, two tags in one outline (#331)."""
    _two_trays_in_one_slot_scene(monkeypatch)
    captures.start_experiment(captures.create_experiment()["id"])
    path = _photo()
    tray_readings.read_photo(path)

    assert tray_readings.photo_readings(path)["exclusion"] == "visit"


# --- Trays found in the photo (#331) -------------------------------------------------------------
TRAY_BLUE = (40, 90, 200)  # OpenCV hue 110, saturation 204, value 200: the sampled tray plastic


def _blue_tray_scene(monkeypatch, tags: list[TagDetection], box=(150, 200, 1675, 2030), size=(2000, 2200)) -> None:
    """`_plant_scene` (5 px/mm, North 1) with a blue tray 1525 x 1830 px (305 x 366 mm) drawn at
    `box`, the mint rectangle inside it (x 700 to 950, y 1100 to 1250, 1500 mm2) and the one
    outside it at x 1700 to 1950 beyond the tray's east side."""
    from npec_rig.camera import CameraManager, SyntheticBackend

    _plant_scene(monkeypatch)
    x0, y0, x1, y1 = box

    class Scene(SyntheticBackend):
        def capture_full_res(self):
            frame, metadata = super().capture_full_res()
            frame[:] = 128
            frame[y0:y1, x0:x1] = TRAY_BLUE
            frame[1100:1250, 700:950] = MINT_LEAF_RGB
            frame[1100:1250, 1700:1950] = MINT_LEAF_RGB
            return frame, metadata

    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: tags)
    CameraManager.set_instance(CameraManager(Scene(width=size[0], height=size[1])))


def _flat(corners) -> list[float]:
    return [v for corner in sorted(corners) for v in corner]


def test_a_tray_found_in_the_photo_is_named_by_its_tag_and_measured_inside_its_outline(monkeypatch) -> None:
    """Tag 5 lies in the tray's north-east corner, not in cell A1: its placement from the tag
    would put the tray somewhere else, the photo puts it where it was drawn."""
    tag = TagDetection(5, ((1400, 300), (1600, 300), (1600, 500), (1400, 500)), (1500, 400))
    _blue_tray_scene(monkeypatch, [tag])

    readings = tray_readings.read_photo(_photo())
    assert readings["status"] == "read"
    [tray] = readings["trays"]
    assert (tray["tray_id"], tray["found"], tray["warnings"], tray["slot"]) == (5, "photo + tag", [], None)
    assert _flat(tray["outline_px"]) == pytest.approx(_flat([(150, 200), (1675, 200), (1675, 2030), (150, 2030)]), abs=10)
    assert tray["area_mm2"] == pytest.approx(1500, rel=0.01)  # 1%: JPEG blurs the rectangle's edge


def test_a_tray_lying_sideways_past_the_photo_edge_is_measured_past_it_at_the_calibrations_scale(monkeypatch) -> None:
    """A tray turned 90 degrees, 1830 x 1525 px, from x 250: it would end at x 2080, 80 px
    (16 mm at 5 px/mm) past the east edge of a 2000 px photo. Its outline is the full tray from
    its west side, so it reaches 16 mm past."""
    tag = TagDetection(5, ((400, 400), (600, 400), (600, 600), (400, 600)), (500, 500))
    _blue_tray_scene(monkeypatch, [tag], box=(250, 300, 2000, 1825))

    [tray] = tray_readings.read_photo(_photo())["trays"]
    # 2 mm: the finder's 4-pixel step is 0.8 mm at 5 px/mm (it was 1 mm, 4 px at 10 px/mm, before
    # #547). Still far inside the 13 mm that decides `partly_outside`.
    assert tray["outside_mm"] == pytest.approx(16, abs=2)
    assert tray["partly_outside"] is True
    assert tray["warnings"] == ["partly outside the photo"]


def test_two_trays_with_no_tag_are_each_kept_and_never_said_to_share_a_tag(monkeypatch) -> None:
    """Two untagged trays side by side, 3050 x 1830 px in a 3500 x 2200 photo."""
    _blue_tray_scene(monkeypatch, [], box=(150, 200, 3200, 2030), size=(3500, 2200))

    trays = tray_readings.read_photo(_photo())["trays"]
    assert [(t["tray_id"], t["found"], t["warnings"]) for t in trays] == [(None, "photo, no tag", ["no tag"])] * 2
    assert [t["not_counted"] for t in trays] == [[], []]


def test_reading_again_never_turns_saved_areas_into_none_when_no_tray_is_found_now(monkeypatch) -> None:
    """Review of #334, the #287 guard: a photo read before #331 by tag placement, with an area,
    read again now that the finder finds no blue in it (a black tray, sheets, dim light) while its
    tray tag is still seen. The saved reading is kept."""
    _calibrate()
    _finds(monkeypatch, "080357_563754")
    path = _photo()
    capture_id = database.captures_by_path([path])[path]["id"]
    database.record_tray_readings(capture_id, read_at="2026-10-28T10:00:00+00:00", status="read", trays=[{
        "tray_id": 3, "slot": "North 1", "a1_corner": "SW", "placement": "placed", "centre_px": [500.0, 500.0],
        "tilt_deg": 0.0, "margin_mm": 200.0, "area_mm2": 1500.0, "segmenter": "green threshold, 0.1",
    }])

    with pytest.raises(tray_readings.ReadingWorse):
        tray_readings.read_photo(path)
    assert [(t["tray_id"], t["area_mm2"]) for t in tray_readings.photo_readings(path)["trays"]] == [(3, 1500.0)]


def test_a_photo_with_no_tray_and_only_a_corner_tag_says_no_trays_found(monkeypatch) -> None:
    """Review of #334: in dim light a bright corner tag (ID 452, 450 to 499) can still be read
    when no tray is found. That says nothing about the trays: the photo is "no trays found", not
    read with every tray missing."""
    _calibrate()
    corner = TagDetection(452, ((50, 50), (250, 50), (250, 250), (50, 250)), (150, 150))
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: [corner])

    readings = tray_readings.read_photo(_photo())
    assert (readings["status"], readings["trays"]) == ("no trays found", [])


def test_a_photo_is_read_with_its_calibration_whatever_the_calibrations_name(monkeypatch) -> None:
    """Review of #334: only the scale field is needed to find trays. A calibration saved under a
    name a slot layout cannot have (not a timestamp) made the slot layout lookup fail and the
    photo read as having no calibration."""
    tag = TagDetection(5, ((1400, 300), (1600, 300), (1600, 500), (1400, 500)), (1500, 400))
    _blue_tray_scene(monkeypatch, [tag])
    _save_scene_calibration(stem="bench-check", created_at="2026-10-29T10:00:00+00:00")

    readings = tray_readings.read_photo(_photo())
    assert readings["status"] == "read"
    assert [(t["tray_id"], t["found"]) for t in readings["trays"]] == [(5, "photo + tag")]


def test_a_photo_stored_as_png_is_searched_for_trays_as_a_jpeg_is(monkeypatch) -> None:
    """Review of #334: JPEG draft mode shrinks a photo for the finder; a PNG does not shrink, and
    the finder ran on the full-size photo with parameters tuned at a quarter. The tray drawn at
    x 150 to 1675, y 200 to 2030 is found there either way."""
    from npec_rig.captures import photo_file

    tag = TagDetection(5, ((1400, 300), (1600, 300), (1600, 500), (1400, 500)), (1500, 400))
    _blue_tray_scene(monkeypatch, [tag])
    path = _photo()
    file = photo_file(path)
    with Image.open(file) as image:
        rgb = image.convert("RGB")
    rgb.save(file, format="PNG")

    [tray] = tray_readings.read_photo(path)["trays"]
    assert tray["found"] == "photo + tag"
    assert _flat(tray["outline_px"]) == pytest.approx(_flat([(150, 200), (1675, 200), (1675, 2030), (150, 2030)]), abs=10)

# --- Table locations, not slots (#332) -----------------------------------------------------------


def _table_experiment() -> int:
    table_calibration()
    experiment = database.create_experiment(uuid="u-332", created_at="2027-01-01T00:00:00+00:00")
    database.start_experiment(experiment["id"], now="2027-01-01T00:00:00+00:00", folder="experiments/x")
    return experiment["id"]


def _at(minute: int):
    from datetime import UTC, datetime

    return datetime(2027, 1, 1, 7, minute, tzinfo=UTC)


def test_a_tray_not_found_names_the_table_location_it_was_last_found_in() -> None:
    experiment_id = _table_experiment()
    table_photo(experiment_id, _at(0), {7: "NW", 8: "NW"})
    table_photo(experiment_id, _at(1), {7: "NW", 8: "SE"})
    path = table_photo(experiment_id, _at(2), {7: "NW"})

    assert tray_readings.photo_readings(path)["not_found"] == [
        {"tray_id": 8, "location": "SE", "since": _at(2).isoformat(), "photos": 1, "last_seen": _at(1).isoformat()}
    ]


def test_a_tray_counts_as_moved_when_its_centre_leaves_its_location_not_when_it_is_nudged_or_turned() -> None:
    """Aaron, 2026-10-30: only a centre leaving its location is a move. Tray 8 nudged 100 px inside NW,
    and tray 9 turned (its centre stays where it was), have not moved."""
    experiment_id = _table_experiment()
    first = table_photo(experiment_id, _at(0), {7: "NW", 8: "NW", 9: "SE"})
    second = table_photo(experiment_id, _at(1), {7: "SM", 9: "SE"})
    capture_id = database.captures_by_path([second])[second]["id"]
    saved = database.tray_readings(capture_id)["trays"]
    nudged = {**saved[0], "tray_id": 8, "centre_px": [250.0, 250.0]}  # (150, 150) moved 100 px, x and y
    turned = {**saved[1], "a1_corner": "NE", "tilt_deg": 90.0}
    database.record_tray_readings(capture_id, read_at="t", status="read", trays=[saved[0], nudged, turned])

    assert tray_readings.photo_readings(first)["moved"] == []
    assert tray_readings.photo_readings(second)["moved"] == [{"tray_id": 7, "from": "NW", "to": "SM"}]


def test_two_trays_placed_in_one_slot_before_331_are_still_not_counted_without_naming_the_slot() -> None:
    """Readings saved before #331 can hold two trays placed in one slot (a loose tag, #315); they
    still do not count, and the reason no longer names a slot (#332)."""
    experiment_id = _table_experiment()
    path = table_photo(experiment_id, _at(0), {5: "NW", 13: "NW", 7: "SE"})
    capture_id = database.captures_by_path([path])[path]["id"]
    old = [{**t, "slot": "North 1" if t["tray_id"] != 7 else "South 3",
            "placement": "two trays in one slot" if t["tray_id"] != 7 else "placed"}
           for t in database.tray_readings(capture_id)["trays"]]
    database.record_tray_readings(capture_id, read_at="t", status="read", trays=old)

    assert {t["tray_id"]: t["not_counted"] for t in tray_readings.photo_readings(path)["trays"]} == {
        5: ["2 trays in one place"], 7: [], 13: ["2 trays in one place"]
    }


def test_each_tray_found_in_a_photo_names_the_table_location_it_lies_in() -> None:
    """The Gallery names a tray's table location, not a slot (#332)."""
    experiment_id = _table_experiment()
    path = table_photo(experiment_id, _at(0), {3: "NE", 7: "SW"})

    assert {t["tray_id"]: t["location"] for t in tray_readings.photo_readings(path)["trays"]} == {3: "NE", 7: "SW"}


# --- Each reading's uncertainty from its slot's validation band (#76) -----------------------------
# Two slots, North 1 and South 6, reading within ±2.0 % and ±4.5 % (tests/helpers.banded_validation).
SESSION = "20270101T010000000000"
TWO_SLOTS = {"North 1": ((150, 150), 2.0), "South 6": ((750, 450), 4.5)}


def test_each_tray_takes_the_band_of_the_validation_slot_nearest_its_centre() -> None:
    """Trays are not tied to slots (#331): the nearest slot centre wins (Aaron, 2026-11-05)."""
    from datetime import datetime, timezone

    table_calibration()
    banded_validation(SESSION, TWO_SLOTS)
    # Tray 3 lies nearer North 1 (150, 150), tray 7 nearer South 6 (750, 450).
    path = table_photo(None, datetime(2027, 1, 2, tzinfo=timezone.utc), {3: "NW", 7: "SE"},
                       validation=SESSION, centres={3: (400, 250), 7: (500, 350)})

    assert {t["tray_id"]: t["uncertainty"] for t in tray_readings.photo_readings(path)["trays"]} == {
        3: {"band_pct": 2.0, "slot": "North 1", "reason": None},
        7: {"band_pct": 4.5, "slot": "South 6", "reason": None},
    }


def test_a_photo_taken_with_no_validation_gives_each_tray_the_reason_and_no_band() -> None:
    from datetime import datetime, timezone

    table_calibration()
    path = table_photo(None, datetime(2027, 1, 2, tzinfo=timezone.utc), {3: "NW"})

    assert [t["uncertainty"] for t in tray_readings.photo_readings(path)["trays"]] == [
        {"band_pct": None, "slot": None, "reason": "not validated"},
    ]


def test_a_photo_taken_under_a_validation_not_consistent_claims_no_band() -> None:
    """A not-consistent validation is named on the photo but its bands are not claimed (#54)."""
    from datetime import datetime, timezone

    table_calibration()
    banded_validation(SESSION, TWO_SLOTS, inconsistent=True)
    path = table_photo(None, datetime(2027, 1, 2, tzinfo=timezone.utc), {3: "NW"}, validation=SESSION)

    assert [t["uncertainty"] for t in tray_readings.photo_readings(path)["trays"]] == [
        {"band_pct": None, "slot": None, "reason": "validation not consistent"},
    ]


def test_a_tray_nearest_a_slot_with_too_few_tags_says_the_slot_was_not_measured() -> None:
    from datetime import datetime, timezone

    table_calibration()
    banded_validation(SESSION, {"North 1": ((150, 150), 2.0), "South 6": ((750, 450), None)})
    path = table_photo(None, datetime(2027, 1, 2, tzinfo=timezone.utc), {7: "SE"}, validation=SESSION)

    assert [t["uncertainty"] for t in tray_readings.photo_readings(path)["trays"]] == [
        {"band_pct": None, "slot": "South 6", "reason": "slot not measured"},
    ]


def test_a_photo_whose_validation_file_is_gone_still_shows_its_trays_and_says_why() -> None:
    """Deleting a calibration deletes its validations (validation_store)."""
    from datetime import datetime, timezone

    table_calibration()
    path = table_photo(None, datetime(2027, 1, 2, tzinfo=timezone.utc), {3: "NW"}, validation=SESSION)

    assert [t["uncertainty"] for t in tray_readings.photo_readings(path)["trays"]] == [
        {"band_pct": None, "slot": None, "reason": "validation not found"},
    ]


def test_a_photo_flagged_as_not_covered_by_the_bands_claims_no_band_under_a_good_validation() -> None:
    """A flag is a reason the photo is not covered by the validation bands (captures.take_photo),
    for example a lens that moved from its lock, while the validation is still named."""
    from datetime import datetime, timezone

    table_calibration()
    banded_validation(SESSION, TWO_SLOTS)
    path = table_photo(None, datetime(2027, 1, 2, tzinfo=timezone.utc), {3: "NW"}, validation=SESSION,
                       flags=["lens moved from its lock"])

    assert [t["uncertainty"] for t in tray_readings.photo_readings(path)["trays"]] == [
        {"band_pct": None, "slot": None, "reason": "photo not covered"},
    ]


def test_a_damaged_validation_with_no_slots_never_hides_the_areas() -> None:
    from datetime import datetime, timezone

    table_calibration()
    session = banded_validation(SESSION, TWO_SLOTS)
    validation_store.save_session({**session, "slots": []})
    path = table_photo(None, datetime(2027, 1, 2, tzinfo=timezone.utc), {3: "NW"}, validation=SESSION)

    assert [t["uncertainty"] for t in tray_readings.photo_readings(path)["trays"]] == [
        {"band_pct": None, "slot": None, "reason": "validation not found"},
    ]


# --- Plant per cell (#364) ------------------------------------------------------------------------
# The blue tray of `_blue_tray_scene` (x 150 to 1675, y 200 to 2030 at 5 px/mm) is centred at
# (912.5, 1115). Its 4 x 5 cells (reference/trays.md: openings 59.5 mm, centres 69.7 mm apart),
# worked by hand from A1 at the south-west: A1 at (389.75, 1812), B3 at (738.25, 1115), C4 at
# (1086.75, 766.5), D4 at (1435.25, 766.5).


def _cells_scene(monkeypatch, tags: list[TagDetection], squares) -> None:
    """A grey photo with the blue tray of `_blue_tray_scene` and mint squares at `squares`
    (x0, y0, x1, y1), the calibration at 5 px/mm."""
    from npec_rig.camera import CameraManager, SyntheticBackend

    _plant_scene(monkeypatch)

    class Scene(SyntheticBackend):
        def capture_full_res(self):
            frame, metadata = super().capture_full_res()
            frame[:] = 128
            frame[200:2030, 150:1675] = TRAY_BLUE
            for x0, y0, x1, y1 in squares:
                frame[y0:y1, x0:x1] = MINT_LEAF_RGB
            return frame, metadata

    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: tags)
    CameraManager.set_instance(CameraManager(Scene(width=2000, height=2200)))


def _a1_tag(tag_id: int, x: float, y: float) -> TagDetection:
    """A 40 mm tag, 200 px at this file's 5 px/mm, centred on (x, y)."""
    return TagDetection(tag_id, ((x - 100, y - 100), (x + 100, y - 100), (x + 100, y + 100), (x - 100, y + 100)), (x, y))


def test_each_cell_of_a_tray_gets_its_plant_area_and_an_empty_cell_reads_missing_not_0(monkeypatch) -> None:
    # A 150 x 150 px square inside B3's opening (297.5 px): 22,500 px, 900 mm2.
    _cells_scene(monkeypatch, [_a1_tag(5, 389.75, 1812.0)], [(663, 1040, 813, 1190)])
    path = _photo()

    readings = tray_readings.read_photo(path)
    [tray] = readings["trays"]
    cells = {c["cell"]: c for c in tray["cells"]}
    assert len(cells) == 20
    assert cells["A1"]["status"] == "tag"
    assert cells["B3"]["status"] == "plant"
    assert cells["B3"]["area_mm2"] == pytest.approx(900, rel=0.01)  # 1%: JPEG blurs the square's edge
    assert {c["status"] for name, c in cells.items() if name not in ("A1", "B3")} == {"missing"}
    assert {c["area_mm2"] for name, c in cells.items() if name not in ("A1", "B3")} == {None}
    assert tray_readings.photo_readings(path) == readings


def test_a_leaf_across_two_cells_counts_for_the_one_holding_more_and_marks_both(monkeypatch) -> None:
    # C4's opening is x 938 to 1235.5, D4's x 1286.5 to 1584, both y 618 to 915.5. A 200 x 100 px
    # leaf at x 1150 to 1350, y 700 to 800: 86 columns over C4, 64 over D4. All 800 mm2 count for C4.
    _cells_scene(monkeypatch, [_a1_tag(5, 389.75, 1812.0)], [(1150, 700, 1350, 800)])

    [tray] = tray_readings.read_photo(_photo())["trays"]
    cells = {c["cell"]: c for c in tray["cells"]}
    assert (cells["C4"]["status"], cells["D4"]["status"]) == ("leaves over other cells", "leaves over other cells")
    assert cells["C4"]["area_mm2"] == pytest.approx(800, rel=0.01)
    assert cells["D4"]["area_mm2"] is None


def _turned_tag(tag_id: int, x: float, y: float, deg: float) -> TagDetection:
    """A 40 mm tag, 200 px at this file's 5 px/mm, at (x, y), turned `deg` clockwise from lying
    with its top north."""
    import math

    t = math.radians(deg)
    corners = tuple(
        (x + dx * math.cos(t) - dy * math.sin(t), y + dx * math.sin(t) + dy * math.cos(t))
        for dx, dy in ((-100, -100), (100, -100), (100, 100), (-100, 100))
    )
    return TagDetection(tag_id, corners, (x, y))


def test_a_2x2_trays_cells_keep_their_names_when_the_tray_is_turned_round_between_photos(monkeypatch) -> None:
    """Aaron, 2026-11-06: 2 x 2 tags are glued at any angle; A1 is the south-west pot in the
    tray's first photo of the experiment. Pots of the tray centred at (912.5, 1115): south-west at
    (567.5, 1526.25), north-east at (1257.5, 703.75) (69 and 82.25 mm from the centre). A 150 x 150
    px plant, 900 mm2, in the south-west pot; then the tray turned round, the plant in the
    north-east."""
    experiment = database.create_experiment(uuid="u-364", created_at="2026-11-06T00:00:00+00:00")
    database.start_experiment(experiment["id"], now="2026-11-06T00:00:00+00:00", folder="u-364")

    _cells_scene(monkeypatch, [_turned_tag(80, 912.5, 1115.0, 45.0)], [(492, 1451, 642, 1601)])
    first = {c["cell"]: c for c in tray_readings.read_photo(_photo())["trays"][0]["cells"]}
    assert first["A1"]["status"] == "plant"
    assert first["A1"]["centre_px"] == pytest.approx([567.5, 1526.25], abs=10)  # the finder works at quarter size
    assert first["A1"]["area_mm2"] == pytest.approx(900, rel=0.01)

    _cells_scene(monkeypatch, [_turned_tag(80, 912.5, 1115.0, 225.0)], [(1182, 628, 1332, 778)])
    second = {c["cell"]: c for c in tray_readings.read_photo(_photo())["trays"][0]["cells"]}
    assert second["A1"]["centre_px"] == pytest.approx([1257.5, 703.75], abs=10)
    assert second["A1"]["status"] == "plant"
    assert second["A1"]["area_mm2"] == pytest.approx(900, rel=0.01)
    assert second["B2"]["status"] == "missing"


def test_a_2x2_trays_cells_have_the_same_names_whatever_order_its_photos_are_read_in(monkeypatch) -> None:
    """Review of #374: photos are read out of order (older ones on demand, Reprocess). The tag is
    glued to the tray, so its A1 bearing is the tray's own: once any photo of the experiment has
    set it, every photo follows it. As the test above: the plant in the south-west pot, then the
    tray turned round. Read the second photo first."""
    experiment = database.create_experiment(uuid="u-364b", created_at="2026-11-06T00:00:00+00:00")
    database.start_experiment(experiment["id"], now="2026-11-06T00:00:00+00:00", folder="u-364b")
    _cells_scene(monkeypatch, [_turned_tag(80, 912.5, 1115.0, 45.0)], [(492, 1451, 642, 1601)])
    first = _photo()
    _cells_scene(monkeypatch, [_turned_tag(80, 912.5, 1115.0, 225.0)], [(1182, 628, 1332, 778)])
    second = _photo()
    # Tags are searched when a photo is read: each photo gets its own tag, told apart by where its
    # plant lies (the south-west pot in the first).
    tags = {True: [_turned_tag(80, 912.5, 1115.0, 45.0)], False: [_turned_tag(80, 912.5, 1115.0, 225.0)]}
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: tags[bool(frame[1526, 567] > 150)])  # grey: mint bright, tray blue about 88

    planted = []
    for path in (second, first):
        cells = tray_readings.read_photo(path)["trays"][0]["cells"]
        planted.append([c["cell"] for c in cells if c["status"] == "plant"])
    assert planted[0] == planted[1]
    assert len(planted[0]) == 1


def _readings_of(path: str, tray_id: int) -> dict:
    return next(t for t in tray_readings.read_photo(path)["trays"] if t["tray_id"] == tray_id)


def test_a_2x2_tag_turned_on_its_tray_marks_its_names_as_maybe_swapped_from_that_photo(monkeypatch) -> None:
    """#385, tray 81 of development experiment 3: its tag turned 83 degrees on the tray, which
    stayed put. Tags that stayed put changed by 2 degrees at most (metrology log 32.2); the cut-off
    is 10 degrees (Aaron, 2026-11-09). The first two photos keep the tag as laid; the third has it
    turned 83 degrees about its centre."""
    experiment = database.create_experiment(uuid="u-385", created_at="2026-11-09T00:00:00+00:00")
    database.start_experiment(experiment["id"], now="2026-11-09T00:00:00+00:00", folder="u-385")
    _cells_scene(monkeypatch, [_turned_tag(80, 912.5, 1115.0, 45.0)], [])
    first, second = _photo(), _photo()
    first_warnings = _readings_of(first, 80)["warnings"]
    second_warnings = _readings_of(second, 80)["warnings"]

    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: [_turned_tag(80, 912.5, 1115.0, 128.0)])
    third = _photo()
    taken = database.captures_by_path([third])[third]["taken_at"]
    third_warnings = _readings_of(third, 80)["warnings"]

    unsure = [w for w in first_warnings + second_warnings if w.startswith("names may be swapped")]
    assert unsure == []
    assert f"names may be swapped since {taken[:10]} {taken[11:16]} UTC" in third_warnings


def test_a_2x2_trays_names_stay_marked_for_the_rest_of_the_experiment_whatever_order_photos_are_read_in(monkeypatch) -> None:
    """#385: once a tray's tag has turned on it, its names stay marked as maybe swapped for the
    rest of the experiment, even when the tag is turned back (Aaron, 2026-11-07). Photos are read
    out of order (older ones on demand, Reprocess): here the photo with the tag turned is read
    last. Tags are searched when a photo is read, so each photo gets the tag set at its reading."""
    experiment = database.create_experiment(uuid="u-385b", created_at="2026-11-09T00:00:00+00:00")
    database.start_experiment(experiment["id"], now="2026-11-09T00:00:00+00:00", folder="u-385b")
    _cells_scene(monkeypatch, [_turned_tag(80, 912.5, 1115.0, 45.0)], [])
    photos = [_photo() for _ in range(4)]
    for path in (photos[0], photos[1], photos[3]):
        tray_readings.read_photo(path)
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: [_turned_tag(80, 912.5, 1115.0, 128.0)])
    tray_readings.read_photo(photos[2])

    taken = database.captures_by_path([photos[2]])[photos[2]]["taken_at"]
    label = f"names may be swapped since {taken[:10]} {taken[11:16]} UTC"
    marked = []
    for path in photos:
        tray = next(t for t in tray_readings.photo_readings(path)["trays"] if t["tray_id"] == 80)
        marked.append(label in tray["warnings"])
    assert marked == [False, False, True, True]


def _warning_searches(monkeypatch) -> list[str]:
    """Every SQL statement run from here on that searches tray readings by their warnings (a
    `warnings` column after WHERE), from SQLite's own trace of each connection."""
    import sqlite3

    searches, connect = [], sqlite3.connect

    def traced(*args, **kwargs):
        conn = connect(*args, **kwargs)
        conn.set_trace_callback(lambda sql: searches.append(sql) if "warnings" in sql.partition("WHERE")[2] else None)
        return conn

    monkeypatch.setattr(sqlite3, "connect", traced)
    return searches


def test_an_hour_of_photos_searches_the_experiments_warnings_once_not_once_per_tray_per_photo(monkeypatch) -> None:
    """#408: the Gallery hour took 13 to 17 s on development experiment 3 because each tray of each
    photo searched every earlier photo's warnings for a turned tag (531 searches, 22 ms each, and
    longer every day). Six photos of trays 7, 8 and 9, tray 8's tag turned in the third: tray 8 is
    marked from that photo on, trays 7 and 9 never, as before, with one search for the hour."""
    experiment_id = _table_experiment()
    photos = [table_photo(experiment_id, _at(minute), {7: "NW", 8: "SM", 9: "SE"}) for minute in range(6)]
    capture_id = database.captures_by_path([photos[2]])[photos[2]]["id"]
    trays = database.tray_readings(capture_id)["trays"]
    database.record_tray_readings(capture_id, read_at="t", status="read", trays=[
        {**t, "warnings": [tray_readings.TAG_TURNED]} if t["tray_id"] == 8 else t for t in trays])

    searches = _warning_searches(monkeypatch)
    since = [{t["tray_id"]: t["names_unsure_since"] for t in tray_readings.photo_readings(p)["trays"]} for p in photos]

    turned = _at(2).isoformat()
    assert since == [{7: None, 8: None, 9: None}] * 2 + [{7: None, 8: turned, 9: None}] * 4
    assert len(searches) == 1


def test_a_turned_tag_saved_after_the_gallery_was_shown_marks_the_tray_at_the_next_showing() -> None:
    """#408: the search is kept between Gallery requests. Photos are read out of order (older ones
    on demand, Reprocess), so a turned tag saved for an earlier photo after a later photo was shown
    marks that later photo the next time it is shown."""
    experiment_id = _table_experiment()
    photos = [table_photo(experiment_id, _at(minute), {7: "NW", 8: "SM"}) for minute in range(4)]

    def since(path: str) -> str | None:
        return next(t for t in tray_readings.photo_readings(path)["trays"] if t["tray_id"] == 8)["names_unsure_since"]

    assert since(photos[3]) is None
    capture_id = database.captures_by_path([photos[1]])[photos[1]]["id"]
    trays = database.tray_readings(capture_id)["trays"]
    database.record_tray_readings(capture_id, read_at="t", status="read", trays=[
        {**t, "warnings": [tray_readings.TAG_TURNED]} if t["tray_id"] == 8 else t for t in trays])

    assert since(photos[3]) == _at(1).isoformat()


# Grow from leaf cores beside the fixed green cutoff (#363). The tray of `_cells_scene` filled with
# soil inside a 50 px blue rim; a mint leaf in B3 with a pale edge the fixed cutoff does not take.
SOIL_RGB = (115, 100, 100)  # greenness -0.048: soil level -0.045, lower cutoff 0.025
PALE_EDGE_RGB = (125, 135, 115)  # greenness 0.080: above the lower cutoff, below the fixed cutoff's 0.1


def _soil_tray_scene(monkeypatch) -> None:
    """The leaf's own area is asserted to 2%, not 1%, wherever this scene is read. The measured
    edge of the leaf sits about a pixel outside the drawn one, because the step from the leaf
    (greenness 0.196) to its pale edge (0.080) crosses the fixed cutoff (0.1) within the first
    pixel. That one pixel is 1.3% of a 150 px square where it was 0.7% of the 300 px square this
    scene was drawn at before #547, and it is measured at +1.4%. The grown area, whose edge is the
    outside of the pale border against the soil, is unaffected and still asserted to 1%."""
    from npec_rig.camera import CameraManager, SyntheticBackend

    _plant_scene(monkeypatch)

    class Scene(SyntheticBackend):
        def capture_full_res(self):
            frame, metadata = super().capture_full_res()
            frame[:] = 128
            frame[200:2030, 150:1675] = TRAY_BLUE
            frame[250:1980, 200:1625] = SOIL_RGB
            frame[1030:1200, 653:823] = PALE_EDGE_RGB  # 10 px around the leaf
            frame[1040:1190, 663:813] = MINT_LEAF_RGB  # 150 x 150 px inside B3's opening: 900 mm2
            return frame, metadata

    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: [_a1_tag(5, 389.75, 1812.0)])
    CameraManager.set_instance(CameraManager(Scene(width=2000, height=2200)))


def test_each_tray_and_cell_gets_its_area_by_both_methods_each_named(monkeypatch) -> None:
    """The fixed green cutoff takes the leaf, 150 x 150 px = 900 mm2 at 5 px/mm, as before. Grow
    from leaf cores also takes its pale edge: 170 x 170 px = 28,900 px = 1156 mm2."""
    _soil_tray_scene(monkeypatch)
    path = _photo()

    readings = tray_readings.read_photo(path)
    [tray] = readings["trays"]
    assert (tray["segmenter"], tray["area_mm2"]) == ("green threshold, 0.1", pytest.approx(900, rel=0.02))
    assert tray["grown_method"] == "grow from leaf cores, core 0.07"
    assert tray["grown_area_mm2"] == pytest.approx(1156, rel=0.01)  # 1%: JPEG blurs the edges
    assert tray["grown_plant_px"] == pytest.approx(28_900, rel=0.01)
    assert tray["grown_plant_centre_px"] == pytest.approx([738, 1115], abs=2)
    assert (tray["grown_soil_level"], tray["grown_lower_cutoff"]) == (pytest.approx(-0.045), pytest.approx(0.025))
    cells = {c["cell"]: c for c in tray["cells"]}
    assert (cells["B3"]["status"], cells["B3"]["area_mm2"]) == ("plant", pytest.approx(900, rel=0.02))
    assert cells["B3"]["grown_area_mm2"] == pytest.approx(1156, rel=0.01)
    assert cells["B3"]["grown_over_other_cells"] is False
    assert {c["grown_area_mm2"] for name, c in cells.items() if name != "B3"} == {None}
    assert (cells["A1"]["grown_status"], cells["B3"]["grown_status"]) == ("tag", "plant")
    assert {c["grown_status"] for name, c in cells.items() if name not in ("A1", "B3")} == {"missing"}
    assert tray_readings.photo_readings(path) == readings


def _rebuilt_twin() -> None:
    """The calibration's twin rebuilt at 5.0 x 5.00 / 4.90 px/mm, as in tests/test_experiments.py
    at 10.0 x 5.00 / 4.90: the same ratio, so the same millimetres."""
    from npec_rig.calibration import ScaleField

    stem = FIXTURE["calibration"]
    save_calibration(
        CalibrationArtifact(created_at="2026-10-26T15:00:00+00:00",
                            scale_field=ScaleField((1.0, 0.0, 0.0), SCENE_PX_PER_MM * 5.00 / 4.90, 0.0),
                            frame_stem=stem, lens_position=6.05, rebuilt_from=stem),
        stem="20261026T150000000001", promote=False,
    )


def _saved(path: str) -> dict:
    return database.tray_readings(database.captures_by_path([path])[path]["id"])


def test_reprocess_counts_both_methods_again_from_their_saved_masks_without_the_photo(monkeypatch) -> None:
    """With the photo gone and nothing else changed, both areas come from the saved masks: 900 mm2
    by the fixed green cutoff, 1156 mm2 by grow from leaf cores (170 x 170 px at 5 px/mm), whose
    soil level and cutoff are kept from the first reading (#483: the fast path)."""
    from npec_rig.captures import photo_file

    _soil_tray_scene(monkeypatch)
    path = _photo()
    tray_readings.read_photo(path)
    photo_file(path).unlink()

    [tray] = tray_readings.read_photo(path, reuse_mask=True)["trays"]
    assert tray["area_mm2"] == pytest.approx(900, rel=0.02)  # 2%: the leaf's edge, see `_soil_tray_scene`
    assert tray["grown_area_mm2"] == pytest.approx(1156, rel=0.01)
    assert tray["grown_method"] == "grow from leaf cores, core 0.07"
    assert (tray["grown_soil_level"], tray["grown_lower_cutoff"]) == (pytest.approx(-0.045), pytest.approx(0.025))
    cells = {c["cell"]: c for c in tray["cells"]}
    assert (cells["B3"]["area_mm2"], cells["B3"]["grown_area_mm2"]) == (pytest.approx(900, rel=0.02), pytest.approx(1156, rel=0.01))


def test_reprocess_gives_the_same_areas_under_a_rebuilt_twin_when_the_photo_is_there(monkeypatch) -> None:
    """The twin rebuilt at 5.0 x 5.00 / 4.90 px/mm: 900 x (4.90 / 5.00)^2 = 864.4 mm2 by the fixed
    green cutoff, 1156 x (4.90 / 5.00)^2 = 1110.2 mm2 by grow from leaf cores, cells too, whether
    the saved masks are counted again or the photo is grown again (#483)."""
    _soil_tray_scene(monkeypatch)
    path = _photo()
    tray_readings.read_photo(path)
    _rebuilt_twin()

    [tray] = tray_readings.read_photo(path, reuse_mask=True)["trays"]
    assert tray["area_mm2"] == pytest.approx(864.4, rel=0.02)  # 2%: the leaf's edge, see `_soil_tray_scene`
    assert tray["grown_area_mm2"] == pytest.approx(1110.2, rel=0.01)
    assert (tray["grown_soil_level"], tray["grown_lower_cutoff"]) == (pytest.approx(-0.045), pytest.approx(0.025))
    cells = {c["cell"]: c for c in tray["cells"]}
    assert (cells["B3"]["area_mm2"], cells["B3"]["grown_area_mm2"]) == (pytest.approx(864.4, rel=0.02), pytest.approx(1110.2, rel=0.01))


def test_reprocess_counts_the_saved_masks_again_under_a_rebuilt_twin_when_the_photo_is_gone(monkeypatch) -> None:
    """The masks do not depend on the calibration and the outlines are the saved ones, so with the
    twin rebuilt at 5.0 x 5.00 / 4.90 px/mm and the photo gone the photo is counted again from its
    masks under it: 900 x (4.90 / 5.00)^2 = 864.4 mm2 by the fixed green cutoff, 1156 x (4.90 / 5.00)^2
    = 1110.2 mm2 by grow from leaf cores, cells too (#483, Aaron 2026-11-24)."""
    from npec_rig.captures import photo_file

    _soil_tray_scene(monkeypatch)
    path = _photo()
    tray_readings.read_photo(path)
    photo_file(path).unlink()
    _rebuilt_twin()

    [tray] = tray_readings.read_photo(path, reuse_mask=True)["trays"]
    assert tray["area_mm2"] == pytest.approx(864.4, rel=0.02)  # 2%: the leaf's edge, see `_soil_tray_scene`
    assert tray["grown_area_mm2"] == pytest.approx(1110.2, rel=0.01)
    cells = {c["cell"]: c for c in tray["cells"]}
    assert (cells["B3"]["area_mm2"], cells["B3"]["grown_area_mm2"]) == (pytest.approx(864.4, rel=0.02), pytest.approx(1110.2, rel=0.01))


def test_reprocess_of_a_photo_read_before_grow_from_leaf_cores_leaves_its_reading_as_it_was_with_the_photo_gone(monkeypatch) -> None:
    """Saved with the fixed cutoff's mask only and no grown mask, as before #363 (here made by
    deleting the grown mask), the photo gone: nothing can be redone completely. The reading stays as
    it was, with its saved areas, and Reprocess says why (#483)."""
    from npec_rig import segmentation
    from npec_rig.captures import photo_file

    _soil_tray_scene(monkeypatch)
    path = _photo()
    tray_readings.read_photo(path)
    photo_file(path).unlink()
    segmentation.mask_file(path, segmentation.GROWN_MASK).unlink()
    before = _saved(path)

    with pytest.raises(tray_readings.NotReprocessed, match="saved mask"):
        tray_readings.read_photo(path, reuse_mask=True)
    assert _saved(path) == before
    assert before["trays"][0]["area_mm2"] == pytest.approx(900, rel=0.02)  # the saved values are still there


# Blue mats over the soil (#373, metrology log 39): the pixels left beside the mats outnumber the
# soil, so the soil level found lies in the histogram's top bin and is no soil level.
MAT_EDGE_RGB = (100, 105, 96)  # greenness (210 - 196) / 301 = 0.0465: the top bin, centre 0.045, after JPEG too


def _matted_tray_scene(monkeypatch) -> None:
    from npec_rig.camera import CameraManager, SyntheticBackend

    _plant_scene(monkeypatch)

    class Scene(SyntheticBackend):
        def capture_full_res(self):
            frame, metadata = super().capture_full_res()
            frame[:] = (110, 90, 90)  # the table, greenness (180 - 200) / 290 = -0.069: below the floor, as the
            # outline takes in a pixel or two of it
            frame[200:2030, 150:1675] = TRAY_BLUE  # tray and mats
            # Both blocks lie on the JPEG's 8 x 8 grid. Halved exactly they do not, and an edge
            # inside a block rings: the ringing reached greenness 0.226 there, over the 0.07
            # leaf-core cutoff (GROWN_CORE_MIN), so the mats seeded themselves and counted as
            # plant. On the grid the highest greenness inside the mats is 0.054 and no pixel is a
            # core. At 10 px/mm, off the grid, it was 0.061: under the cutoff by 0.009, which is
            # why halving the scene was enough to cross it. Measured 2026-11-26, metrology log 53.
            # Moving them onto the grid also changed their size, so these two blocks alone are not
            # a quarter of the 10 px/mm scene's 150,000 and 660,000 px.
            frame[1504:1648, 1304:1552] = DARK_SOIL_RGB  # 35,712 px of soil left between the mats
            frame[304:600, 1000:1552] = MAT_EDGE_RGB  # 163,392 px, touching no leaf
            frame[1030:1200, 653:823] = PALE_EDGE_RGB  # 10 px around the leaf
            frame[1040:1190, 663:813] = MINT_LEAF_RGB  # 150 x 150 px inside B3's opening: 900 mm2
            return frame, metadata

    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: [_a1_tag(5, 389.75, 1812.0)])
    CameraManager.set_instance(CameraManager(Scene(width=2000, height=2200)))


# Issue #486: soil as green as under mats (MAT_EDGE_RGB, the top bin), but no mats: a 50 px blue
# rim only, as `_soil_tray_scene`, so the tray's outline is still found by its colour.
def _green_soil_tray_scene(monkeypatch) -> None:
    from npec_rig.camera import CameraManager, SyntheticBackend

    _plant_scene(monkeypatch)

    class Scene(SyntheticBackend):
        def capture_full_res(self):
            frame, metadata = super().capture_full_res()
            frame[:] = 128
            frame[200:2030, 150:1675] = TRAY_BLUE
            frame[250:1980, 200:1625] = MAT_EDGE_RGB  # the soil, a 50 px blue rim left showing
            frame[1030:1200, 653:823] = PALE_EDGE_RGB  # 10 px around the leaf
            frame[1040:1190, 663:813] = MINT_LEAF_RGB  # 150 x 150 px inside B3's opening: 900 mm2
            return frame, metadata

    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: [_a1_tag(5, 389.75, 1812.0)])
    CameraManager.set_instance(CameraManager(Scene(width=2000, height=2200)))


def test_a_tray_whose_soil_looks_green_with_no_mats_keeps_the_soil_cutoff_and_is_marked(monkeypatch) -> None:
    """The soil-based cutoff (0.045 + 0.07 = 0.115) is kept, above the pale edge's 0.08: only the
    leaf counts, 150 x 150 px = 900 mm2, not the whole tray as it did before this fix."""
    from npec_rig import segmentation

    _green_soil_tray_scene(monkeypatch)
    [tray] = tray_readings.read_photo(_photo())["trays"]

    assert (tray["grown_soil_level"], tray["grown_lower_cutoff"]) == (pytest.approx(0.045), pytest.approx(0.115))
    assert tray["grown_blue_coverage"] < segmentation.GROWN_BLUE_COVERAGE_MIN  # the 50 px rim only
    assert tray["grown_area_mm2"] == pytest.approx(900, rel=0.01)  # 1%: JPEG blurs the edges
    assert segmentation.SOIL_GREEN in tray["warnings"]
    assert segmentation.SOIL_HIDDEN not in tray["warnings"]


def test_reprocess_keeps_counting_a_soil_looks_green_reading_without_the_photo(monkeypatch) -> None:
    """A reading whose soil read green with no mats (its blue coverage saved, #486) is not shaped
    like a reading saved before #373 with its leaves cut short: with the photo gone, its saved mask
    is counted again, not blocked into a regrow it cannot do."""
    from npec_rig import segmentation
    from npec_rig.captures import photo_file

    _green_soil_tray_scene(monkeypatch)
    path = _photo()
    tray_readings.read_photo(path)
    photo_file(path).unlink()

    [tray] = tray_readings.read_photo(path, reuse_mask=True)["trays"]
    assert tray["grown_area_mm2"] == pytest.approx(900, rel=0.01)
    assert segmentation.SOIL_GREEN in tray["warnings"]


# #486 review (2026-11-26): an empty cell's bottom is the tray's own blue plastic, and so are the
# walls between cells — neither is a mat. A 2 x 2 tray (tag 80, type "2x2"), green soil (no mats)
# in three of its four cells, the fourth (B1) genuinely empty (no pot, the bare blue tray bottom).
# Cell corners here are `tray_placement.place_cells`'s own answer for this exact outline and tag,
# worked out once by hand and fixed in the comments below, not recomputed by the test.
# A1 x 202.5 to 747.5, y 1331 to 1875.5 (planted, a leaf). A2 x 202.5 to 747.5, y 508.5 to 1053
# (soil only). B1 x 892.5 to 1437.5, y 1331 to 1875.5 (empty: left blue). B2 x 892.5 to 1437.5,
# y 508.5 to 1053 (soil only).
def _tray_with_an_empty_cell_scene(monkeypatch) -> None:
    from npec_rig.camera import CameraManager, SyntheticBackend

    _plant_scene(monkeypatch)

    class Scene(SyntheticBackend):
        def capture_full_res(self):
            frame, metadata = super().capture_full_res()
            frame[:] = 128
            frame[277:2107, 57:1582] = TRAY_BLUE  # the whole tray: walls, rim, and B1, stay blue
            frame[1341:1865, 212:737] = MAT_EDGE_RGB  # A1: soil, a little green, inset 10 px
            frame[518:1043, 212:737] = MAT_EDGE_RGB  # A2: soil, no leaf
            frame[1341:1865, 902:1427] = MAT_EDGE_RGB  # B2: soil, no leaf
            frame[1450:1600, 400:550] = MINT_LEAF_RGB  # A1's leaf, 150 x 150 px inside it
            return frame, metadata

    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: [_a1_tag(80, 820.0, 1192.0)])
    CameraManager.set_instance(CameraManager(Scene(width=2000, height=2200)))


def test_a_2x2_trays_empty_cell_does_not_read_as_a_mat(monkeypatch) -> None:
    """Without the cell fix, B1's blue bottom and the walls push blue coverage above the threshold
    and the tray is wrongly marked soil hidden; the leaf's area then comes from the wrong (floor)
    cutoff. With it, only A1 (the cell holding the leaf's core) counts towards blue coverage, which
    has no blue in it at all: the tray is correctly marked soil looks green, its cutoff kept."""
    from npec_rig import segmentation

    _tray_with_an_empty_cell_scene(monkeypatch)
    [tray] = tray_readings.read_photo(_photo())["trays"]

    assert tray["grown_blue_coverage"] < segmentation.GROWN_BLUE_COVERAGE_MIN
    assert segmentation.SOIL_GREEN in tray["warnings"]
    assert segmentation.SOIL_HIDDEN not in tray["warnings"]
    # The leaf alone, 150 x 150 px = 900 mm2: no pale edge drawn around it here, so JPEG ringing
    # at its sharp border adds more than the usual 1% (other tests draw a pale edge to absorb
    # this). The ringing is a fixed width in pixels, so halving the scene (#547) grew its share of
    # the area: measured 962.59 mm2 (+6.95%) at 10 px/mm and 975.48 mm2 (+8.39%) at 5 px/mm, a
    # factor of 1.21, not the 2 a fixed pixel width would suggest. 11% is that 8.39% with room to
    # spare: 999 mm2 is the band's top, 23.5 mm2 above what is measured. What the assertion is for
    # is untouched -- without the cell fix the whole tray's soil counts, tens of thousands of mm2.
    assert tray["grown_area_mm2"] == pytest.approx(900, rel=0.11)


def test_a_tray_whose_soil_is_hidden_under_mats_is_grown_from_the_floor_and_marked(monkeypatch) -> None:
    """The leaf with its pale edge, 170 x 170 px = 1156 mm2 at 5 px/mm, as on bare soil. A cutoff
    0.07 above the top bin (0.115) would leave the edge out: 900 mm2."""
    from npec_rig.segmentation import SOIL_HIDDEN

    _matted_tray_scene(monkeypatch)

    [tray] = tray_readings.read_photo(_photo())["trays"]
    assert tray["grown_area_mm2"] == pytest.approx(1156, rel=0.01)  # 1%: JPEG blurs the edges
    assert (tray["grown_soil_level"], tray["grown_lower_cutoff"]) == (pytest.approx(0.045), pytest.approx(-0.045))
    assert SOIL_HIDDEN in tray["warnings"]
    assert SOIL_HIDDEN == "mats covering soil; area measured with a less precise fallback"


def test_reprocess_segments_again_a_photo_read_with_its_cutoff_in_the_leaves(monkeypatch) -> None:
    """A reading saved before #373 on a matted tray: soil level 0.045, lower cutoff 0.115 and a
    mask of the leaf without its pale edge (150 x 150 px, 900 mm2). Reprocess does not count that
    mask again: it grows the photo from the floor, 1156 mm2, and marks the tray."""
    import numpy as np

    from npec_rig import segmentation

    _matted_tray_scene(monkeypatch)
    path = _photo()
    tray_readings.read_photo(path)
    capture_id = database.captures_by_path([path])[path]["id"]
    old = np.zeros((2200, 2000), dtype=bool)
    old[1040:1190, 663:813] = True
    segmentation.save_mask(path, old, segmentation.GROWN_MASK)
    trays = database.tray_readings(capture_id)["trays"]
    database.record_tray_readings(capture_id, read_at="t", status="read", trays=[
        {**t, "grown_lower_cutoff": 0.115, "grown_blue_coverage": None, "warnings": []} for t in trays])

    [tray] = tray_readings.read_photo(path, reuse_mask=True)["trays"]
    assert tray["grown_area_mm2"] == pytest.approx(1156, rel=0.01)  # 1%: JPEG blurs the edges
    assert tray["grown_lower_cutoff"] == pytest.approx(-0.045)
    assert segmentation.SOIL_HIDDEN in tray["warnings"]


def _cut_short_reading(monkeypatch, *, change) -> str:
    """The matted tray read, then its reading saved as it was before #373: soil level 0.045, lower
    cutoff 0.115 and a grown mask of the leaf without its pale edge (150 x 150 px, 900 mm2).
    `change` edits each saved tray (a shifted centre, a shifted outline, another ID)."""
    import numpy as np

    from npec_rig import segmentation

    _matted_tray_scene(monkeypatch)
    path = _photo()
    tray_readings.read_photo(path)
    capture_id = database.captures_by_path([path])[path]["id"]
    old = np.zeros((2200, 2000), dtype=bool)
    old[1040:1190, 663:813] = True
    segmentation.save_mask(path, old, segmentation.GROWN_MASK)
    trays = database.tray_readings(capture_id)["trays"]
    database.record_tray_readings(capture_id, read_at="t", status="read", trays=[
        change({**t, "grown_lower_cutoff": 0.115, "grown_blue_coverage": None, "warnings": []}) for t in trays])
    return path


def test_reprocess_grows_again_a_cut_short_reading_whose_saved_centre_is_1_px_away(monkeypatch) -> None:
    """The reading saved before #373 above, saved with the tray's centre 1 px from where the photo
    puts it now (#483, finding 5). Its levels are matched by tray, not by the centre to the pixel:
    grown again from the floor, 1156 mm2, and marked."""
    from npec_rig import segmentation

    path = _cut_short_reading(monkeypatch, change=lambda t: {**t, "centre_px": [t["centre_px"][0] + 1.0, t["centre_px"][1]]})

    [tray] = tray_readings.read_photo(path, reuse_mask=True)["trays"]
    assert (tray["grown_soil_level"], tray["grown_lower_cutoff"]) == (pytest.approx(0.045), pytest.approx(-0.045))
    assert tray["grown_area_mm2"] == pytest.approx(1156, rel=0.01)  # 1%: JPEG blurs the edges
    assert segmentation.SOIL_HIDDEN in tray["warnings"]


def test_reprocess_grows_again_a_tray_whose_saved_outline_is_not_where_the_photo_puts_it_now(monkeypatch) -> None:
    """A grown mask holds plant only inside the outlines found when it was made (#483, finding 7).
    The saved outline here lies 2.5 px (0.5 mm) from the one found now, and the saved mask is the
    leaf cut short (900 mm2) though its levels are fine: the photo is grown again, 1156 mm2."""
    def shifted(t: dict) -> dict:
        return {**t, "grown_soil_level": -0.045, "grown_lower_cutoff": 0.025,
                "outline_px": [[x + 2.5, y] for x, y in t["outline_px"]]}

    path = _cut_short_reading(monkeypatch, change=shifted)

    [tray] = tray_readings.read_photo(path, reuse_mask=True)["trays"]
    assert tray["grown_area_mm2"] == pytest.approx(1156, rel=0.01)  # 1%: JPEG blurs the edges


def test_reprocess_grows_again_a_tray_the_saved_reading_does_not_have(monkeypatch) -> None:
    """A tray outlined only now has no saved levels and its saved mask was made without it: the
    photo is grown again, 1156 mm2, not counted inside the old mask (900 mm2)."""
    path = _cut_short_reading(
        monkeypatch, change=lambda t: {**t, "tray_id": 99, "grown_soil_level": -0.045, "grown_lower_cutoff": 0.025})

    [tray] = tray_readings.read_photo(path, reuse_mask=True)["trays"]
    assert tray["grown_area_mm2"] == pytest.approx(1156, rel=0.01)  # 1%: JPEG blurs the edges


def test_reprocess_counts_the_saved_mask_again_for_a_matched_tray_when_the_photo_is_gone(monkeypatch) -> None:
    """With the photo gone, a tray that is matched to its saved tray (same tag, same outline) has
    its saved grown mask counted again: 900 mm2, the leaf without its pale edge (#483)."""
    from npec_rig.captures import photo_file

    path = _cut_short_reading(
        monkeypatch, change=lambda t: {**t, "grown_soil_level": -0.045, "grown_lower_cutoff": 0.025})
    photo_file(path).unlink()

    [tray] = tray_readings.read_photo(path, reuse_mask=True)["trays"]
    assert tray["grown_area_mm2"] == pytest.approx(900, rel=0.01)  # 1%: JPEG blurs the edges


def test_reprocess_leaves_the_reading_as_it_was_when_a_tray_cannot_be_matched_with_the_photo_gone(monkeypatch) -> None:
    """The saved tray carries tag 99, the stored tags put tag 5 in its outline now, and the photo
    is gone: the old grown mask is not counted inside that outline and nothing is saved (#483)."""
    from npec_rig.captures import photo_file

    path = _cut_short_reading(
        monkeypatch, change=lambda t: {**t, "tray_id": 99, "grown_soil_level": -0.045, "grown_lower_cutoff": 0.025})
    photo_file(path).unlink()
    before = _saved(path)

    with pytest.raises(tray_readings.NotReprocessed, match="same outline"):
        tray_readings.read_photo(path, reuse_mask=True)
    assert _saved(path) == before


def test_a_reading_saved_before_373_keeps_its_mark_and_values_when_reprocess_cannot_grow_it_again(monkeypatch) -> None:
    """Saved before #373 (soil 0.045, cutoff 0.115, the leaf without its pale edge, 900 mm2) with
    the mark "soil hidden: usual leaf cutoff used" it carried, the photo gone: it cannot be counted
    again from its mask (the cutoff is in the leaves) and cannot be grown again. Nothing changes:
    values and mark stay (#483, third review finding 2)."""
    from npec_rig import segmentation
    from npec_rig.captures import photo_file

    path = _cut_short_reading(monkeypatch, change=lambda t: {**t, "warnings": [segmentation.SOIL_HIDDEN]})
    photo_file(path).unlink()
    before = _saved(path)

    with pytest.raises(tray_readings.NotReprocessed, match="before #373"):
        tray_readings.read_photo(path, reuse_mask=True)
    assert _saved(path) == before
    assert before["trays"][0]["warnings"] == [segmentation.SOIL_HIDDEN]


def test_reprocess_matches_a_reading_saved_before_331_by_tag_and_centre(monkeypatch) -> None:
    """#483, review finding 4: a reading saved before #331 has no outline. Its trays are matched by
    tag and centre, as they were: the mask (900 mm2, the leaf without its pale edge, levels fine)
    is counted again; a regrown mask would read 1156 mm2."""
    path = _cut_short_reading(
        monkeypatch, change=lambda t: {**t, "outline_px": None, "grown_soil_level": -0.045, "grown_lower_cutoff": 0.025})

    [tray] = tray_readings.read_photo(path, reuse_mask=True)["trays"]
    assert tray["grown_area_mm2"] == pytest.approx(900, rel=0.01)  # 1%: JPEG blurs the edges
    assert (tray["grown_soil_level"], tray["grown_lower_cutoff"]) == (pytest.approx(-0.045), pytest.approx(0.025))


def test_reprocess_recounts_no_tray_while_a_touching_neighbour_is_not_matched(monkeypatch) -> None:
    """Plant in the strip two touching trays share counts for the tray with the nearer centre, so a
    tray is recounted only with every tray matched. Tray 7's saved reading carries tag 8, so it is
    not matched; with the photo gone nothing is saved for either tray (#483, `_two_touching_trays_scene`)."""
    from npec_rig.captures import photo_file

    _two_touching_trays_scene(monkeypatch)
    path = _photo()
    tray_readings.read_photo(path)
    capture_id = database.captures_by_path([path])[path]["id"]
    saved = database.tray_readings(capture_id)["trays"]
    database.record_tray_readings(capture_id, read_at="t", status="read", trays=[
        {**t, "tray_id": 8} if t["tray_id"] == 7 else t for t in saved])
    photo_file(path).unlink()
    before = _saved(path)

    with pytest.raises(tray_readings.NotReprocessed, match="same outline"):
        tray_readings.read_photo(path, reuse_mask=True)
    assert _saved(path) == before


def test_reprocess_recounts_touching_trays_from_their_masks_when_every_tray_is_matched(monkeypatch) -> None:
    """The same photo with its trays unchanged, the photo gone: both trays are recounted, and the
    plant in the strip they share is counted once, 1500 mm2 in all, 900 and 600 mm2 (the numbers of
    `test_plant_in_the_strip_touching_trays_share_is_counted_once_for_the_nearer_tray`)."""
    from npec_rig.captures import photo_file

    _two_touching_trays_scene(monkeypatch)
    path = _photo()
    tray_readings.read_photo(path)
    photo_file(path).unlink()

    trays = {t["tray_id"]: t for t in tray_readings.read_photo(path, reuse_mask=True)["trays"]}
    assert trays[5]["area_mm2"] == pytest.approx(900, rel=0.01)  # see `_two_touching_trays_scene`
    assert trays[7]["area_mm2"] == pytest.approx(600, rel=0.01)
    assert trays[5]["area_mm2"] > trays[7]["area_mm2"]  # the nearer tray keeps the larger share
    assert trays[5]["grown_area_mm2"] + trays[7]["grown_area_mm2"] == pytest.approx(1500, rel=0.02)


def test_reprocess_grows_a_photo_again_whose_saved_tray_says_its_grown_area_was_not_worked_out(monkeypatch) -> None:
    """A reading saved with "grown area not worked out" and no grown values is not recounted from
    its masks, so a second Reprocess does not repeat the first one's gap: with the photo there it
    is grown again, 1156 mm2, and the mark is gone (#483, third review finding 1)."""
    _soil_tray_scene(monkeypatch)
    path = _photo()
    tray_readings.read_photo(path)
    capture_id = database.captures_by_path([path])[path]["id"]
    trays = database.tray_readings(capture_id)["trays"]
    unset = {"grown_method": None, "grown_area_mm2": None, "grown_plant_px": None, "grown_plant_centre_px": None,
             "grown_soil_level": None, "grown_lower_cutoff": None}
    database.record_tray_readings(capture_id, read_at="t", status="read", trays=[
        {**t, **unset, "warnings": ["grown area not worked out"]} for t in trays])

    [tray] = tray_readings.read_photo(path, reuse_mask=True)["trays"]
    assert tray["grown_area_mm2"] == pytest.approx(1156, rel=0.01)  # 1%: JPEG blurs the edges
    assert "grown area not worked out" not in tray["warnings"]


def test_reprocess_counts_a_reading_with_its_cutoff_at_the_floor_again_and_marks_it_once(monkeypatch) -> None:
    """The matted tray read with the cutoff at the floor, the photo gone: counted again from its
    masks, 1156 mm2, with the mark "usual leaf cutoff used" once."""
    from npec_rig import segmentation
    from npec_rig.captures import photo_file

    _matted_tray_scene(monkeypatch)
    path = _photo()
    tray_readings.read_photo(path)
    photo_file(path).unlink()

    [tray] = tray_readings.read_photo(path, reuse_mask=True)["trays"]
    assert tray["grown_area_mm2"] == pytest.approx(1156, rel=0.01)  # 1%: JPEG blurs the edges
    assert tray["warnings"].count(segmentation.SOIL_HIDDEN) == 1


def test_reprocess_that_grows_again_and_then_meets_a_locked_rig_db_leaves_the_reading_and_no_half_pair_of_masks(monkeypatch) -> None:
    """Fifth review of #483: the reading and its masks must never be a mixed pair. The reading saved
    before #373 is grown again from the photo and the new reading cannot be saved because rig.db is
    locked for writing. The saved reading stays. Both old masks are deleted before the save, so
    neither is left to be counted against it: a Reprocess with the photo gone says "a saved mask is
    missing" and changes nothing, and no temporary file is left."""
    import sqlite3

    from npec_rig import segmentation
    from npec_rig.captures import photo_file

    path = _cut_short_reading(monkeypatch, change=lambda t: t)
    files = [segmentation.mask_file(path), segmentation.mask_file(path, segmentation.GROWN_MASK)]
    before = _saved(path)
    monkeypatch.setattr(settings, "LOCK_WAIT_S", 0.3)

    # 2 s, not the helper's default 5: the reading gives up after 0.57 s (measured), and the rest
    # of the 5 s was the holder thread sleeping on, 4 s of this file's run (#547).
    with lock_held(2.0), pytest.raises(sqlite3.OperationalError, match="locked"):
        tray_readings.read_photo(path, reuse_mask=True)
    assert _saved(path) == before
    assert [f.exists() for f in files] == [False, False]
    assert not list(files[0].parent.glob("*.staged"))
    photo_file(path).unlink()
    with pytest.raises(tray_readings.NotReprocessed, match="saved mask"):
        tray_readings.read_photo(path, reuse_mask=True)
    assert _saved(path) == before


def test_a_read_that_cannot_delete_an_old_mask_leaves_no_temporary_files(monkeypatch) -> None:
    """Sixth review of #483: if an old mask cannot be deleted (here its place holds a folder), the
    error is raised and the new masks written to temporary files before it are removed."""
    from npec_rig import segmentation

    _soil_tray_scene(monkeypatch)
    path = _photo()
    blocked = segmentation.mask_file(path)
    (blocked).mkdir(parents=True)
    (blocked / "in-the-way").write_bytes(b"x")

    with pytest.raises(OSError):
        tray_readings.read_photo(path)
    assert not list(blocked.parent.glob("*.staged"))


def test_a_recount_with_the_photo_gone_leaves_both_saved_masks_in_place_byte_for_byte(monkeypatch) -> None:
    """With the photo gone the saved masks are all that is left of it: counting them again saves the
    reading and never deletes, rewrites or renames a mask (#483)."""
    from npec_rig import segmentation
    from npec_rig.captures import photo_file

    _soil_tray_scene(monkeypatch)
    path = _photo()
    tray_readings.read_photo(path)
    photo_file(path).unlink()
    files = [segmentation.mask_file(path), segmentation.mask_file(path, segmentation.GROWN_MASK)]
    stamps = [(f.read_bytes(), f.stat().st_mtime_ns, f.stat().st_ino) for f in files]

    tray_readings.read_photo(path, reuse_mask=True)
    assert [(f.read_bytes(), f.stat().st_mtime_ns, f.stat().st_ino) for f in files] == stamps
    assert not list(files[0].parent.glob("*.staged"))


def test_reprocess_grows_the_photo_again_when_a_saved_mask_cannot_be_read(monkeypatch) -> None:
    """A saved mask truncated or corrupt: with the photo there, it is grown again, 1156 mm2 (the
    matted tray's leaf and its pale edge, 170 x 170 px at 5 px/mm), as a new read (#483)."""
    from npec_rig import segmentation

    _matted_tray_scene(monkeypatch)
    path = _photo()
    tray_readings.read_photo(path)
    segmentation.mask_file(path).write_bytes(b"not a png")

    [tray] = tray_readings.read_photo(path, reuse_mask=True)["trays"]
    assert tray["grown_area_mm2"] == pytest.approx(1156, rel=0.01)  # 1%: JPEG blurs the edges
    assert tray["area_mm2"] is not None


def test_reprocess_does_not_count_a_reading_saved_with_its_cells_not_worked_out(monkeypatch) -> None:
    """A tray saved with "cells not worked out" has no cells to count again: with the photo gone
    nothing is saved (#483, fifth review)."""
    from npec_rig.captures import photo_file

    _soil_tray_scene(monkeypatch)
    path = _photo()
    tray_readings.read_photo(path)
    capture_id = database.captures_by_path([path])[path]["id"]
    saved = database.tray_readings(capture_id)["trays"]
    database.record_tray_readings(capture_id, read_at="t", status="read", trays=[
        {**t, "warnings": ["cells not worked out"]} for t in saved])
    photo_file(path).unlink()
    before = _saved(path)

    with pytest.raises(tray_readings.NotReprocessed, match="not worked out"):
        tray_readings.read_photo(path, reuse_mask=True)
    assert _saved(path) == before


def test_starting_reprocess_removes_only_old_temporary_mask_files(monkeypatch) -> None:
    """A kill between writing a new mask and renaming it leaves `*.staged` beside the masks. When
    Reprocess starts one older than an hour (STAGED_MAX_AGE_S: no commit takes more than seconds) is
    removed, whatever process left it; a fresh one, which may be a reading in progress in another
    process, stays; a file named in no usual way neither crashes the sweep nor is removed if fresh."""
    import os
    import time

    from npec_rig import segmentation

    _soil_tray_scene(monkeypatch)
    path = _photo()
    folder = segmentation.mask_file(path).parent
    folder.mkdir(parents=True, exist_ok=True)
    old = folder / f"{Path(path).name}.png.4242.1.staged"
    fresh = folder / f"{Path(path).name}.png.4243.1.staged"
    odd = folder / "x.staged"
    for f in (old, fresh, odd):
        f.write_bytes(b"x")
    two_hours_ago = time.time() - 2 * 3600
    os.utime(old, (two_hours_ago, two_hours_ago))
    experiment = database.create_experiment(uuid="u-483s", created_at="2026-11-06T00:00:00+00:00")

    tray_readings.start_reprocess(experiment["id"])
    assert (old.exists(), fresh.exists(), odd.exists()) == (False, True, True)


def test_reprocess_does_not_count_a_matched_saved_tray_that_has_no_levels(monkeypatch) -> None:
    """Fourth review of #483: tray 7 was saved with no areas and no levels (a reading made when its
    outline could not be measured), tray 5 is complete. With the photo gone the masks are not
    counted again for tray 7: its grown area would be saved with no cutoff. Nothing is saved."""
    from npec_rig.captures import photo_file

    _two_touching_trays_scene(monkeypatch)
    path = _photo()
    tray_readings.read_photo(path)
    capture_id = database.captures_by_path([path])[path]["id"]
    saved = database.tray_readings(capture_id)["trays"]
    empty = {"area_mm2": None, "plant_px": None, "plant_centre_px": None, "segmenter": None, "calibration": None,
             "grown_method": None, "grown_area_mm2": None, "grown_plant_px": None, "grown_plant_centre_px": None,
             "grown_soil_level": None, "grown_lower_cutoff": None}
    database.record_tray_readings(capture_id, read_at="t", status="read", trays=[
        {**t, **empty, "cells": []} if t["tray_id"] == 7 else t for t in saved])
    photo_file(path).unlink()
    before = _saved(path)

    with pytest.raises(tray_readings.NotReprocessed, match="levels"):
        tray_readings.read_photo(path, reuse_mask=True)
    assert _saved(path) == before


def test_a_locked_rig_db_in_a_2x2_trays_cells_fails_the_reading_instead_of_saving_none(monkeypatch) -> None:
    """#483, finding 6: the lock is met when the tray's A1 bearing is looked up for its cells, then
    ends. The reading must fail with the lock error, so the caller retries (#464); it must not be
    saved with no cells and no mark. The lock stops reads too, as the rollback journal's does.

    The bearing has to be the query that meets the lock, and the reading reads rig.db four times
    before it (#561): the capture row for itself, its own saved reading (`database.tray_readings`),
    the stored tags, and the capture row again in `found_trays`, for the photo's calibration. So
    the lock is taken while the reading is segmenting the photo, which is after all four and
    before the bearing. The reading says when
    that is itself: it holds `images.full_decode_slot()` for the whole of its segmentation, and it
    can only take that slot once the tag search has let go of it and the tags are stored."""
    import sqlite3
    import time

    from npec_rig import images

    experiment = database.create_experiment(uuid="u-483", created_at="2026-11-06T00:00:00+00:00")
    database.start_experiment(experiment["id"], now="2026-11-06T00:00:00+00:00", folder="u-483")
    tag = _turned_tag(80, 912.5, 1115.0, 45.0)
    _cells_scene(monkeypatch, [tag], [(492, 1451, 642, 1601)])
    path = _photo()

    gave_up = threading.Event()
    met: list[str] = []
    reading_thread = threading.current_thread().name  # the reading runs here, the locker does not

    class LockMet(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            # This test's own thread only. The lock is BEGIN EXCLUSIVE on a journal_mode=DELETE
            # file, so for the ~460 ms it is up every rig.db access anywhere in this process fails
            # and logs. A background thread left by a neighbouring test (a reprocess thread
            # writing its run row, say) would otherwise land in `met` and fail the list below with
            # a confusing message.
            if record.threadName != reading_thread:
                return
            message = record.getMessage()
            if "rig.db was locked" in message:
                met.append(message.split(":")[0])  # the query that met it (database._connect)
                if message.startswith("first_a1_bearing:"):
                    gave_up.set()  # the lock ends as the bearing lookup gives up, not before

    locker_failed: list[BaseException] = []

    def lock_once_segmenting() -> None:
        try:
            slot = images.full_decode_slot()
            # The tags are stored after the tag search lets the slot go, so from here the next
            # thread to take it is this reading's own segmentation.
            while images.stored_tag_detections(path.removeprefix("rig/")) is None:
                time.sleep(0.001)
            deadline = time.monotonic() + 15
            while slot.acquire(timeout=0.01):  # free: the reading is not segmenting yet
                slot.release()
                if gave_up.is_set():
                    return  # the test has already ended: do not hold up its join for 15 s
                if time.monotonic() > deadline:
                    raise RuntimeError("the reading never took the full-decode slot to segment")
                time.sleep(0.005)
            # The reading holds the slot: it is segmenting, past the capture row it reads for the
            # calibration, and it reads rig.db next for the A1 bearing.
            #
            # The margin, measured over ten instrumented runs under load: the segmentation holds
            # the slot 172 to 192 ms, this loop notices it is taken within 15 ms at worst
            # (sleep(0.005) + acquire(timeout=0.01), both fixed constants), and lock_held takes
            # 1.7 to 5.1 ms to enter. So the lock is up at most about 20 ms after the slot is
            # taken, against a 172 ms budget: about 10x. A slower box makes this safer, not
            # riskier -- the 20 ms is wall-clock and fixed, while the budget grows with the CPU
            # (about 570 ms at a third of this speed, about 25x). Only a faster box or cheaper
            # segmentation narrows it, and then the test fails loudly on `met` below.
            with lock_held(until=gave_up, readers_too=True):
                gave_up.wait(10)
        except BaseException as exc:  # the test fails on it below: a locker that could not
            # take the lock must not leave the reading to pass quietly
            locker_failed.append(exc)
            gave_up.set()

    locker = threading.Thread(target=lock_once_segmenting)

    def detect_then_lock(frame):
        if not locker.is_alive() and locker.ident is None:  # once: the tags are searched once per photo
            locker.start()
        return [tag]

    handler = LockMet()
    logging.getLogger("npec_rig.database").addHandler(handler)
    monkeypatch.setattr(settings, "LOCK_WAIT_S", 0.3)
    monkeypatch.setattr(photo_tags, "detect_tags", detect_then_lock)
    try:
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            tray_readings.read_photo(path)
    finally:
        gave_up.set()
        locker.join(timeout=15)
        logging.getLogger("npec_rig.database").removeHandler(handler)
        if locker_failed:
            # Here, not after the try: a locker that could not take the lock leaves the reading to
            # run unlocked and return normally, and pytest.raises then reports DID NOT RAISE and
            # hides the real cause -- which is the very race this test was rewritten to remove.
            raise locker_failed[0]
    assert met == ["first_a1_bearing"]  # no earlier query met the lock (#561)
    assert tray_readings.photo_readings(path) is None


def test_a_photo_whose_reading_met_a_locked_rig_db_is_read_again(monkeypatch, tmp_path) -> None:
    """#439: on production a photo's reading could not be saved while another writer held rig.db,
    the lock was gone a moment later, and the photo was saved as "read failed" for good."""
    monkeypatch.setattr(tray_readings, "POLL_S", 0.05)
    monkeypatch.setenv("NPEC_RIG_EXPERIMENTS_DIR", str(tmp_path / "experiments"))
    _calibrate()
    _finds(monkeypatch, "080357_563754")
    client = TestClient(app)  # not started as a context: no reader or scheduler of its own
    experiment = client.post("/api/experiments", json={}).json()
    client.post(f"/api/experiments/{experiment['id']}/start")
    path = _photo()
    photo_tags.photo_tags_for(path)  # its tags found and kept before the lock (images.py waits 10 s)

    gave_up = threading.Event()

    class FirstLockFailure(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if "was locked" in record.getMessage():
                gave_up.set()

    handler = FirstLockFailure()
    logging.getLogger("npec_rig.database").addHandler(handler)
    monkeypatch.setattr(settings, "LOCK_WAIT_S", 0.1)
    reader = tray_readings.TrayReader()
    try:
        with lock_held(until=gave_up):  # the lock ends just after the reading fails to be saved
            reader.start()
        _wait_for(lambda: (tray_readings.photo_readings(path) or {}).get("status") == "read", timeout_s=5)
    finally:
        reader.stop(timeout_s=5)
        logging.getLogger("npec_rig.database").removeHandler(handler)
    assert len(tray_readings.photo_readings(path)["trays"]) == 12


def test_a_locked_rig_db_at_the_photos_calibration_leaves_it_unread_not_no_calibration(monkeypatch, tmp_path) -> None:
    """#564: the trays were looked for with the photo's calibration read from the capture row a
    second time, and a momentary rig.db lock on that read was swallowed into the status
    "no calibration". There is no saved reading to refuse (`_refuse_worse` returns early), so the
    photo was then saved for good as "no calibration" with no trays, `database.unread_photos`
    never offered it again, and the caller's retry (#464) never happened: the photo was lost from
    the readings with nothing on any page to say why. A photo whose reading meets a locked rig.db
    must be read again, as #439 and #483 settled for every other query the reading makes.

    The lock is placed with no polling and no timing margin (#561). The reading stores the
    photo's tags in rig.db (`images._store_tags`) and then takes `images._key_locks_guard` to
    forget that photo's tag lock. This test holds that guard, from inside the tag search, so the
    reading parks there: after its tags are stored, and before the capture row is read again.
    The hand-over is exact rather than timed, in both directions. The reading releases the
    photo's own tag lock as the last thing it does before the park, so the locker waits on that
    lock instead of watching for a side effect, and at the park the reading holds no rig.db
    connection, which is what `lock_held(readers_too=True)` needs. The lock goes up while the
    reading cannot move, so no query it made earlier can have met it.

    With the row read once, nothing reads rig.db between the park and the save, so the query that
    meets the lock here is now the save itself (`record_tray_readings`). It raises, as every
    other locked query in a reading does, and the reader reads the photo again.
    """
    from npec_rig import images

    monkeypatch.setattr(tray_readings, "POLL_S", 0.05)
    monkeypatch.setenv("NPEC_RIG_EXPERIMENTS_DIR", str(tmp_path / "experiments"))
    _calibrate()
    _finds(monkeypatch, "080357_563754")
    fixture_tags = photo_tags.detect_tags
    client = TestClient(app)  # not started as a context: no reader or scheduler of its own
    experiment = client.post("/api/experiments", json={}).json()
    client.post(f"/api/experiments/{experiment['id']}/start")
    path = _photo()
    source = path.removeprefix("rig/")  # what images.py files the photo's tags under

    armed = threading.Event()  # the guard is held: the reading will park on it
    gave_up = threading.Event()  # the reading has met the lock, which can now end
    lock_over = threading.Event()  # rig.db is free and back in WAL: this thread may read it again
    met: list[str] = []
    locker_failed: list[BaseException] = []

    def lock_once_the_tags_are_stored() -> None:
        guard = images._key_locks_guard
        holding = False
        try:
            tag_lock = images._key_locks[f"tags:{source}"]  # held by the reading until it stores
            guard.acquire()
            holding = True
            armed.set()
            if not tag_lock.acquire(timeout=15):
                raise RuntimeError("the reading never stored the photo's tags")
            # The reading has stored its tags and closed that connection, and its next step is the
            # guard above, so it is standing still with nothing open on rig.db.
            with lock_held(until=gave_up, readers_too=True):
                guard.release()
                holding = False
                gave_up.wait(10)
        except BaseException as exc:  # the test fails on it below: a locker that could not take
            # the lock must not leave the reading to pass quietly
            locker_failed.append(exc)
        finally:
            if holding:
                guard.release()  # never leave the reading parked for ever
            armed.set()
            gave_up.set()
            lock_over.set()

    locker = threading.Thread(target=lock_once_the_tags_are_stored)

    def detect_then_arm(frame):
        if locker.ident is None:  # once: the tags are searched once per photo
            locker.start()
            assert armed.wait(15), "the locker never took images' key-lock guard"
        return fixture_tags(frame)

    class LockMet(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            # The reading's thread only: the lock stops every rig.db access in this process while
            # it is up, and a thread left running by a neighbouring test would otherwise end it.
            if record.threadName != "tray-reader":
                return
            if "rig.db was locked" in record.getMessage():
                met.append(record.getMessage().split(":")[0])  # the query that met it
                gave_up.set()  # the lock ends as the reading gives up on it, not before

    handler = LockMet()
    logging.getLogger("npec_rig.database").addHandler(handler)
    monkeypatch.setattr(settings, "LOCK_WAIT_S", 0.3)
    monkeypatch.setattr(photo_tags, "detect_tags", detect_then_arm)
    reader = tray_readings.TrayReader()
    try:
        reader.start()
        assert lock_over.wait(30), "the reading never reached the lock"
        _wait_for(lambda: tray_readings.photo_readings(path) is not None, timeout_s=15)
    finally:
        gave_up.set()
        locker.join(timeout=15)
        reader.stop(timeout_s=15)
        logging.getLogger("npec_rig.database").removeHandler(handler)
        if locker_failed:
            raise locker_failed[0]
    assert met, "the reading never met the lock: it was not held where this test meant to hold it"
    reading = tray_readings.photo_readings(path)
    assert reading["status"] == "read"
    assert len(reading["trays"]) == 12


# --- A cell where grow from leaf cores reads far above the fixed cutoff is flagged (#484) ---------
def _cells_read(*pairs) -> dict:
    """A tray 7 whose cells hold plant (fixed area, grown area) mm2 for each pair, read back by
    `capture_readings`. A fixed area of 0 is a cell with no plant by the fixed cutoff."""
    experiment_id = _table_experiment()
    path = table_photo(experiment_id, _at(0), {7: "NW"})
    capture = database.captures_by_path([path])[path]
    [tray] = database.tray_readings(capture["id"])["trays"]
    tray["cells"] = [
        {"cell": f"B{i}", "holds": "plant", "centre_px": [0.0, 0.0], "corners_px": [[0, 0]] * 4,
         "plant_px": int(fixed * 10), "area_mm2": fixed, "plant_centre_px": None, "over_other_cells": False,
         "segmenter": "green threshold, 0.1", "cell_rule": "rule",
         "grown_plant_px": None if grown is None else int(grown * 10), "grown_area_mm2": grown,
         "grown_plant_centre_px": None, "grown_over_other_cells": None if grown is None else False}
        for i, (fixed, grown) in enumerate(pairs, 1)
    ]
    tray["area_mm2"], tray["grown_area_mm2"] = 500.0, 900.0
    database.record_tray_readings(capture["id"], read_at="t", status="read", trays=[tray])
    [out] = tray_readings.capture_readings(capture)["trays"]
    return out


def test_a_cell_grown_over_5_times_and_100_mm2_above_the_fixed_cutoff_is_flagged() -> None:
    assert [c["flagged"] for c in _cells_read((54.0, 600.0))["cells"]] == [True]


def test_a_cell_exactly_5_times_the_fixed_cutoff_is_not_flagged() -> None:
    assert [c["flagged"] for c in _cells_read((200.0, 1000.0))["cells"]] == [False]


def test_a_cell_is_flagged_from_a_difference_of_100_mm2_not_99() -> None:
    # 10 -> 109 is x10.9 but only +99; 20 -> 120 is x6 and +100.
    assert [c["flagged"] for c in _cells_read((10.0, 109.0), (20.0, 120.0))["cells"]] == [False, True]


def test_a_cell_with_no_plant_by_the_fixed_cutoff_is_flagged_from_100_mm2_grown() -> None:
    assert [c["flagged"] for c in _cells_read((0.0, 100.0), (0.0, 99.0))["cells"]] == [True, False]


def test_an_ordinary_cell_is_not_flagged() -> None:
    assert [c["flagged"] for c in _cells_read((120.0, 180.0))["cells"]] == [False]


def test_a_cell_with_no_grown_area_is_not_flagged() -> None:
    assert [c["flagged"] for c in _cells_read((120.0, None))["cells"]] == [False]


def test_the_tray_says_how_many_cells_are_flagged_and_their_grown_area_together() -> None:
    tray = _cells_read((54.0, 600.0), (120.0, 180.0), (10.0, 1500.0), (0.0, 2100.0))
    assert ("3 cells where grown and fixed areas disagree (4,200 mm² in total). "
            "Usually an empty pot. Check the cells.") in tray["warnings"]
    assert tray["area_mm2"] == 500.0


def test_the_tray_line_for_one_flagged_cell_is_singular() -> None:
    assert ("1 cell where grown and fixed areas disagree (600 mm²). "
            "Usually an empty pot. Check the cell.") in _cells_read((54.0, 600.0), (120.0, 180.0))["warnings"]


def test_a_tray_with_no_flagged_cell_has_no_flag_line() -> None:
    assert not [w for w in _cells_read((120.0, 180.0))["warnings"] if "disagree" in w]


def test_a_tray_with_no_cells_is_flagged_by_the_same_rule_on_its_whole_area() -> None:
    experiment_id = _table_experiment()
    path = table_photo(experiment_id, _at(0), {7: "NW"})
    capture = database.captures_by_path([path])[path]
    [tray] = database.tray_readings(capture["id"])["trays"]
    tray.update(cells=[], area_mm2=500.0, grown_area_mm2=2700.0)
    database.record_tray_readings(capture["id"], read_at="t", status="read", trays=[tray])
    [out] = tray_readings.capture_readings(capture)["trays"]
    assert ("1 cell where grown and fixed areas disagree (2,700 mm²). "
            "Usually an empty pot. Check the cell.") in out["warnings"]
