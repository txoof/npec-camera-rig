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
