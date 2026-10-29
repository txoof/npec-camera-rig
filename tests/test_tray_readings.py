"""Readings per tray per photo (#222): each photo read once for its trays, and saved.

The tags are the real detections of still 080357_563754 (layout 2 of 20 October, metrology log
15.5l) with their calibration's scale field and slot layout; the expected slots and corners are
the printed shuffle map, as in tests/test_tray_placement.py.
"""

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from npec_rig import captures, database, photo_tags, tray_readings, validation_store
from npec_rig.app import app
from npec_rig.calibration import CalibrationArtifact, scale_field_from_dict
from npec_rig.calibration_store import save_calibration
from npec_rig.tags import TagDetection
from tests.helpers import one_tray_plant_scene

pytestmark = pytest.mark.unit

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


def test_a_photo_is_read_for_its_trays_and_the_reading_is_saved(monkeypatch) -> None:
    _calibrate()
    _finds(monkeypatch, "080357_563754")
    path = _photo()

    readings = tray_readings.read_photo(path)
    assert readings["status"] == "read"
    assert {t["tray_id"]: (t["slot"], t["a1_corner"]) for t in readings["trays"]} == LAYOUT_2
    assert tray_readings.photo_readings(path) == readings


def test_a_photo_without_a_calibration_is_read_with_no_trays_and_says_why(monkeypatch) -> None:
    _finds(monkeypatch, "080357_563754")
    path = _photo()

    readings = tray_readings.read_photo(path)
    assert (readings["status"], readings["trays"]) == ("no calibration", [])


def test_a_calibration_without_a_slot_layout_says_so(monkeypatch) -> None:
    _calibrate(with_layout=False)
    _finds(monkeypatch, "080357_563754")
    path = _photo()

    assert tray_readings.read_photo(path)["status"] == "no slot layout"


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


def test_a_photo_with_no_tags_at_all_says_so(monkeypatch) -> None:
    _calibrate()
    _finds(monkeypatch, None)

    assert tray_readings.read_photo(_photo())["status"] == "no tags found"


def test_each_tray_gets_its_plant_area_in_mm2_and_the_segmenter_that_made_it(monkeypatch) -> None:
    """A worked example, not the code's own sum (`one_tray_plant_scene`): a 500 x 300 px mint
    rectangle inside the tray at 10 px/mm is 50 x 30 mm = 1500 mm2. The one outside the tray must
    not count."""
    one_tray_plant_scene(monkeypatch)

    tray = tray_readings.read_photo(_photo())["trays"][0]
    assert tray["tray_id"] == 5
    assert tray["area_mm2"] == pytest.approx(1500, rel=0.01)  # 1%: JPEG blurs the rectangle's edge
    assert tray["segmenter"] == "green threshold, 0.1"


def test_each_trays_area_keeps_its_plant_pixel_count_centre_and_calibration(monkeypatch) -> None:
    """The raw measurement under the mm2 (Aaron, 2026-10-23), so another calibration can be applied
    later: `one_tray_plant_scene`'s rectangle inside the tray is 500 x 300 = 150,000 px, centred at
    x 1650, y 2350 (from its corners, x 1400 to 1900 and y 2200 to 2500)."""
    one_tray_plant_scene(monkeypatch)

    tray = tray_readings.read_photo(_photo())["trays"][0]
    assert tray["plant_px"] == pytest.approx(150_000, rel=0.01)  # 1%: JPEG blurs the edge
    assert tray["plant_centre_px"] == pytest.approx([1650, 2350], abs=2)
    assert tray["calibration"] == FIXTURE["calibration"]


@pytest.mark.parametrize(("width", "height", "past_mm", "partly_outside"), [(3015, 4400, 15, True), (4000, 4164, 5, False)])
def test_a_tray_more_than_13_mm_past_the_photo_edge_is_marked_partly_outside(
    monkeypatch, width, height, past_mm, partly_outside
) -> None:
    """#282 item 1: `one_tray_plant_scene`'s tray outline reaches x 3165 and y 4214 at 10 px/mm.
    In a photo 3015 px wide its east side is 150 px (15 mm) past the edge; in one 4164 px high
    its south side is 50 px (5 mm) past. Marked only beyond 13 mm, the widest measured outer wall:
    up to there only wall is outside, beyond it plants can be (a decision, Aaron, 2026-10-27)."""
    from npec_rig.camera import CameraManager, SyntheticBackend
    from tests.helpers import MINT_LEAF_RGB

    one_tray_plant_scene(monkeypatch)

    class Scene(SyntheticBackend):
        def capture_full_res(self):
            frame, metadata = super().capture_full_res()
            frame[:] = 128
            frame[2200:2500, 1400:1900] = MINT_LEAF_RGB
            return frame, metadata

    CameraManager.set_instance(CameraManager(Scene(width=width, height=height)))

    tray = tray_readings.read_photo(_photo())["trays"][0]
    assert tray["outside_mm"] == pytest.approx(past_mm, abs=0.1)
    assert tray["partly_outside"] is partly_outside


def test_a_tray_read_before_the_photo_edge_was_checked_is_not_marked_either_way(monkeypatch) -> None:
    """#282 item 1: a reading saved without `outside_mm`, as every photo read before it, says
    nothing about the photo edge (None), not that the tray lies inside (False)."""
    _calibrate()
    path = _photo()
    tray = {"tray_id": 5, "slot": "North 1", "a1_corner": "SW", "placement": "placed",
            "centre_px": [1640, 2384], "tilt_deg": 0.0, "margin_mm": 300.0, "area_mm2": 1500.0,
            "segmenter": "green threshold, 0.1"}
    database.record_tray_readings(
        database.captures_by_path([path])[path]["id"], read_at="2026-10-27T12:00:00+00:00", status="read", trays=[tray]
    )

    saved = tray_readings.photo_readings(path)["trays"][0]
    assert (saved["outside_mm"], saved["partly_outside"]) == (None, None)


def _two_touching_trays_scene(monkeypatch) -> None:
    """`one_tray_plant_scene` with a second tray touching it on the east, in a 6400 x 4400 photo.

    Tray 5's outline is x 115 to 3165 (as in `one_tray_plant_scene`), centre x 1640. Tray 7's tag
    lies 3025 px east of tray 5's, so its outline is x 3140 to 6190, centre x 4665: the outlines
    share x 3140 to 3165, and the point midway between the centres is x 3152.5. A 500 x 300 px mint
    rectangle at x 2900 to 3400, y 2200 to 2500 (1500 mm2) crosses the strip: columns 2900 to 3152
    (253 x 300 px, 759 mm2) are nearer tray 5, columns 3153 to 3399 (247 x 300 px, 741 mm2) nearer
    tray 7."""
    from npec_rig.camera import CameraManager, SyntheticBackend
    from tests.helpers import MINT_LEAF_RGB

    one_tray_plant_scene(monkeypatch)

    class Scene(SyntheticBackend):
        def capture_full_res(self):
            frame, metadata = super().capture_full_res()
            frame[:] = 128
            frame[2200:2500, 2900:3400] = MINT_LEAF_RGB
            return frame, metadata

    stem = FIXTURE["calibration"]
    validation_store.save_slot_layout(
        stem,
        [{"name": "North 1", "centre": [1640, 2384], "box": [100, 500, 3200, 4300]},
         {"name": "North 2", "centre": [4665, 2384], "box": [3125, 500, 6225, 4300]}],
        [],
    )
    tags = [TagDetection(5, ((400, 3600), (800, 3600), (800, 4000), (400, 4000)), (600, 3800)),
            TagDetection(7, ((3425, 3600), (3825, 3600), (3825, 4000), (3425, 4000)), (3625, 3800))]
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: tags)
    CameraManager.set_instance(CameraManager(Scene(width=6400, height=4400)))


def test_plant_in_the_strip_touching_trays_share_is_counted_once_for_the_nearer_tray(monkeypatch) -> None:
    """#282, the rule of 2026-10-23 (Aaron): the two trays' areas add up to the plant, 1500 mm2,
    not more, and each tray has its own part (`_two_touching_trays_scene`)."""
    _two_touching_trays_scene(monkeypatch)

    trays = {t["tray_id"]: t for t in tray_readings.read_photo(_photo())["trays"]}
    assert trays[5]["area_mm2"] + trays[7]["area_mm2"] == pytest.approx(1500, rel=0.01)  # 1%: JPEG blur
    assert trays[5]["area_mm2"] == pytest.approx(759, rel=0.01)
    assert trays[7]["area_mm2"] == pytest.approx(741, rel=0.01)


def test_a_photo_takes_its_area_from_the_rebuilt_twin_of_its_calibration(monkeypatch) -> None:
    """Part B, test point 2 (#286). `one_tray_plant_scene`: 150,000 plant px under a calibration of
    10.0 px/mm, 1500 mm2. A twin rebuilt from that calibration at 10.0 x 5.00 / 4.90 px/mm (the
    ratio of tag spacing to tag edges agreed for this test) gives 1500 x (4.90 / 5.00)^2 =
    1440.6 mm2. The photo's own record still names the original calibration."""
    from npec_rig.calibration import CalibrationArtifact, ScaleField

    one_tray_plant_scene(monkeypatch)
    path = _photo()
    stem = FIXTURE["calibration"]
    assert tray_readings.read_photo(path)["trays"][0]["area_mm2"] == pytest.approx(1500, rel=0.01)

    save_calibration(
        CalibrationArtifact(
            created_at="2026-10-26T15:00:00+00:00", scale_field=ScaleField((1.0, 0.0, 0.0), 10.0 * 5.00 / 4.90, 0.0),
            frame_stem=stem, lens_position=6.05, rebuilt_from=stem,
        ),
        stem="20261026T150000000000", promote=False,
    )
    tray = tray_readings.read_photo(path)["trays"][0]

    assert tray["area_mm2"] == pytest.approx(1440.6, rel=0.01)  # 1%: JPEG blurs the edge
    assert database.captures_by_path([path])[path]["calibration"] == stem


def _camera_reports(monkeypatch, exposure_us: int, gain: float) -> None:
    """The synthetic camera, reporting the exposure and gain of a real photo."""
    from npec_rig.camera import CameraManager, SyntheticBackend

    class Reports(SyntheticBackend):
        def capture_full_res(self):
            frame, metadata = super().capture_full_res()
            return frame, {**metadata, "ExposureTime": exposure_us, "AnalogueGain": gain}

    CameraManager.set_instance(CameraManager(Reports()))


def test_a_photo_taken_with_the_lights_off_is_excluded_from_its_exposure_and_gain(monkeypatch) -> None:
    """Exposure and gain of real photos of experiment 18 (rig.db, 2026-10-26): lights off at
    23:28:53 UTC on 22 October, 64,022 us at gain 4.0; lit at 08:41:20, 5,404 us at gain 1.0."""
    _calibrate()
    _finds(monkeypatch, None)
    _camera_reports(monkeypatch, 64_022, 4.0)
    dark = _photo()
    _camera_reports(monkeypatch, 5_404, 1.0)
    lit = _photo()

    for path in (dark, lit):
        tray_readings.read_photo(path)
    assert tray_readings.photo_readings(dark)["exclusion"] == "lights off"
    assert tray_readings.photo_readings(lit)["exclusion"] is None


def test_each_trays_area_carries_the_floor_below_which_it_means_nothing_detected(monkeypatch) -> None:
    """100 mm2 for the green threshold: Aaron's starting value (2026-10-26), from empty trays
    reading up to 98 mm2 (metrology log 17.4); checked in #293."""
    one_tray_plant_scene(monkeypatch)

    tray = tray_readings.read_photo(_photo())["trays"][0]
    assert tray["floor_mm2"] == 100


def test_each_photos_exclusion_is_stored_and_earlier_photos_are_checked_again_as_new_ones_come(
    monkeypatch, tmp_path
) -> None:
    """#288: the experiment's first "day" (shortened to 0.3 s, a timing constant) is 5,000 and
    5,100 us: norm 5,050, largest swing 1%, limit 3%. A photo at 4,000 is off the norm; while it
    is the newest it is "light off norm", and once the next photo is back at 5,000 it is a short
    run that returned: "light disturbed"."""
    from datetime import timedelta

    from npec_rig import exclusions

    monkeypatch.setenv("NPEC_RIG_EXPERIMENTS_DIR", str(tmp_path / "experiments"))
    monkeypatch.setattr(exclusions, "FIRST_DAY", timedelta(seconds=0.3))
    monkeypatch.setattr(exclusions, "NEAR_LIGHTS_OFF", timedelta(0))
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
    taken(5_100)
    time.sleep(0.35)
    taken(5_000)
    dip = taken(4_000)
    assert tray_readings.photo_readings(dip)["exclusion"] == "light off norm"
    taken(5_000)
    assert tray_readings.photo_readings(dip)["exclusion"] == "light disturbed"


def _two_trays_with_one_tag_scene(monkeypatch) -> None:
    """`one_tray_plant_scene` with three trays side by side in a 9600 x 4400 photo, at 10 px/mm:
    two carry tag 1, the third tag 7. Tag centres x 600, 3625 and 6650, so the outlines are x 115 to
    3165, 3140 to 6190 and 6165 to 9215 (3025 px apart, as in `_two_touching_trays_scene`). Each
    holds a mint rectangle 300 px tall, clear of the strips the outlines share: 500 px wide in the
    first (1500 mm2), 250 px in the second (750 mm2), 500 px in the third (1500 mm2)."""
    from npec_rig.camera import CameraManager, SyntheticBackend
    from tests.helpers import MINT_LEAF_RGB

    one_tray_plant_scene(monkeypatch)

    class Scene(SyntheticBackend):
        def capture_full_res(self):
            frame, metadata = super().capture_full_res()
            frame[:] = 128
            frame[2200:2500, 1400:1900] = MINT_LEAF_RGB
            frame[2200:2500, 4400:4650] = MINT_LEAF_RGB
            frame[2200:2500, 7450:7950] = MINT_LEAF_RGB
            return frame, metadata

    validation_store.save_slot_layout(
        FIXTURE["calibration"],
        [{"name": "North 1", "centre": [1640, 2384], "box": [100, 500, 3200, 4300]},
         {"name": "North 2", "centre": [4665, 2384], "box": [3125, 500, 6225, 4300]},
         {"name": "North 3", "centre": [7690, 2384], "box": [6150, 500, 9250, 4300]}],
        [],
    )
    tags = [TagDetection(tag_id, ((x - 200, 3600), (x + 200, 3600), (x + 200, 4000), (x - 200, 4000)), (x, 3800))
            for tag_id, x in ((1, 600), (1, 3625), (7, 6650))]
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: tags)
    CameraManager.set_instance(CameraManager(Scene(width=9600, height=4400)))


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
    300 px (30 mm) east of tag 5: a loose tag on tray 5 (metrology log 17.12). Both trays' centres
    (x 1640 and 1940) are nearest North 1; tray 7 is alone in North 3."""
    _two_trays_with_one_tag_scene(monkeypatch)
    tags = [TagDetection(tag_id, ((x - 200, 3600), (x + 200, 3600), (x + 200, 4000), (x - 200, 4000)), (x, 3800))
            for tag_id, x in ((5, 600), (13, 900), (7, 6650))]
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: tags)


def test_two_trays_in_one_slot_are_both_marked_not_counted_with_the_slot(monkeypatch) -> None:
    """#315, decided by Aaron 2026-10-28: a second outline over a tray takes part of its plant, so
    neither tray in the slot counts, in this photo; the other trays count as normal."""
    _two_trays_in_one_slot_scene(monkeypatch)

    trays = {t["tray_id"]: t for t in tray_readings.read_photo(_photo())["trays"]}
    assert trays[5]["not_counted"] == ["2 trays in North 1"]
    assert trays[13]["not_counted"] == ["2 trays in North 1"]
    assert trays[7]["not_counted"] == []


def test_a_photo_with_two_trays_in_one_slot_is_left_out_whole_as_chamber_activity(monkeypatch) -> None:
    """#315, decided by Aaron 2026-10-28: two outlines in one slot mean a tray carried over the
    table or a loose tag on a tray (metrology log 17.12), too abnormal to measure, so the whole
    photo is a visit, as for any chamber activity (`_two_trays_in_one_slot_scene`)."""
    _two_trays_in_one_slot_scene(monkeypatch)
    captures.start_experiment(captures.create_experiment()["id"])
    path = _photo()
    tray_readings.read_photo(path)

    assert tray_readings.photo_readings(path)["exclusion"] == "visit"
