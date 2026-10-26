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

from npec_rig import captures, photo_tags, tray_readings, validation_store
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
