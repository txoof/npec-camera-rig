from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from npec_rig import captures, database, photo_tags
from npec_rig.app import app
from tests.helpers import draw_tray, one_tray_plant_scene, record_light_photos, square_detection

pytestmark = pytest.mark.unit


def test_capture_saves_jpeg_and_sidecar_and_appears_in_gallery() -> None:
    client = TestClient(app)
    response = client.post("/capture")
    assert response.status_code == 200
    record = response.json()
    assert record["filename"].endswith(".jpg")
    assert "timestamp" in record

    response = client.get(record["url"])
    assert response.status_code == 200
    assert response.content[:2] == b"\xff\xd8"

    response = client.get("/api/captures")
    assert response.status_code == 200
    filenames = [item["filename"] for item in response.json()]
    assert record["filename"] in filenames


def test_api_captures_respects_a_non_default_limit() -> None:
    client = TestClient(app)
    for _ in range(3):
        assert client.post("/capture").status_code == 200

    response = client.get("/api/captures", params={"limit": 2})
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_gallery_thumb_and_screen_are_reduced_copies_made_once() -> None:
    from PIL import Image
    import io

    client = TestClient(app)
    path = client.post("/capture").json()["path"]
    thumb = client.get(f"/gallery/image/thumb/{path}")
    screen = client.get(f"/gallery/image/screen/{path}")
    assert thumb.status_code == screen.status_code == 200
    assert thumb.headers["content-type"] == "image/jpeg"
    original = client.get(client.get("/api/captures", params={"limit": 1}).json()[0]["url"]).content
    full_width = Image.open(io.BytesIO(original)).width
    assert Image.open(io.BytesIO(thumb.content)).width == min(480, full_width)
    assert Image.open(io.BytesIO(screen.content)).width == min(1600, full_width)
    assert client.get(f"/gallery/image/thumb/{path}").content == thumb.content


def test_gallery_image_rejects_bad_paths_and_sizes() -> None:
    client = TestClient(app)
    path = client.post("/capture").json()["path"]
    assert client.get(f"/gallery/image/huge/{path}").status_code == 404
    assert client.get("/gallery/image/thumb/rig/2020-01-01/000000_000000").status_code == 404
    assert client.get("/gallery/image/thumb/rig/../etc/passwd").status_code in (404, 422)
    assert client.get("/gallery/image/thumb/etc/2026-10-14/000000_000000").status_code == 422


def test_api_captures_pages_back_with_before() -> None:
    client = TestClient(app)
    for _ in range(3):
        assert client.post("/capture").status_code == 200
    newest = client.get("/api/captures", params={"limit": 2}).json()
    older = client.get("/api/captures", params={"limit": 2, "before": newest[-1]["key"]}).json()
    assert older and older[0]["key"] < newest[-1]["key"]
    assert client.get("/api/captures", params={"before": "yesterday"}).status_code == 422
    hours = client.get("/api/captures/hours").json()
    assert hours and all(set(h) == {"hour", "count", "first"} for h in hours)


def _experiment_with_photos(client: TestClient, photos: int) -> tuple[dict, list[str]]:
    """Start an experiment, take `photos` Capture photos into it, stop it."""
    experiment = client.post("/api/experiments", json={}).json()
    client.post(f"/api/experiments/{experiment['id']}/start", params={"stop_running": True})
    paths = [client.post("/capture").json()["path"] for _ in range(photos)]
    client.post(f"/api/experiments/{experiment['id']}/stop")
    return experiment, paths


def test_api_captures_shows_only_one_experiments_photos_and_pages_within_it() -> None:
    client = TestClient(app)
    chosen, chosen_paths = _experiment_with_photos(client, 3)
    client.post("/capture")  # a rig photo, newer than the chosen experiment's
    _experiment_with_photos(client, 1)  # another experiment's photo, newer still

    first = client.get("/api/captures", params={"experiment": chosen["id"], "limit": 2}).json()
    rest = client.get(
        "/api/captures",
        params={"experiment": chosen["id"], "limit": 2, "before": first[-1]["key"]},
    ).json()
    assert [p["path"] for p in first + rest] == chosen_paths[::-1]


def test_go_to_date_counts_only_the_chosen_experiments_photos() -> None:
    client = TestClient(app)
    chosen, chosen_paths = _experiment_with_photos(client, 2)
    client.post("/capture")
    _experiment_with_photos(client, 1)

    hours = client.get("/api/captures/hours", params={"experiment": chosen["id"]}).json()
    assert sum(h["count"] for h in hours) == len(chosen_paths)


def test_each_hour_gives_its_earliest_photo_for_the_day_and_week_tiles() -> None:
    client = TestClient(app)
    client.post("/capture")  # a rig photo, earlier than the experiment's, in the same hour
    chosen, chosen_paths = _experiment_with_photos(client, 3)

    hours = client.get("/api/captures/hours", params={"experiment": chosen["id"]}).json()
    # The hour the first photo was taken in (two entries if the test crosses an hour).
    day, stem = chosen_paths[0].split("/")[-2:]
    first_hour = next(h for h in hours if h["hour"] == f"{day}T{stem[:2]}")
    assert first_hour["first"] == chosen_paths[0]


def test_the_hour_view_asks_for_photos_before_an_on_the_hour_time() -> None:
    from datetime import datetime, timedelta

    client = TestClient(app)
    path = client.post("/capture").json()["path"]
    day, stem = path.split("/")[-2:]
    hour_start = datetime.strptime(f"{day}T{stem[:2]}", "%Y-%m-%dT%H")
    key = lambda t: t.strftime("%Y-%m-%dT%H0000_000000")  # noqa: E731

    before_next = client.get("/api/captures", params={"before": key(hour_start + timedelta(hours=1))})
    before_this = client.get("/api/captures", params={"before": key(hour_start)})
    assert before_next.status_code == before_this.status_code == 200
    assert path in [p["path"] for p in before_next.json()]
    assert path not in [p["path"] for p in before_this.json()]


def test_an_unknown_experiment_is_not_found_and_one_never_started_has_no_photos() -> None:
    client = TestClient(app)
    client.post("/capture")
    never_started = client.post("/api/experiments", json={}).json()

    for url in ("/api/captures", "/api/captures/hours"):
        assert client.get(url, params={"experiment": 999999}).status_code == 404
        assert client.get(url, params={"experiment": never_started["id"]}).json() == []


def _fake_tag_search(monkeypatch: pytest.MonkeyPatch, detections: list) -> list[int]:
    """Replace the tag detector with one that finds `detections`; returns the list of frame
    widths it was run on, one entry per search."""
    searches: list[int] = []

    def detect(frame):
        searches.append(frame.shape[1])
        return detections

    monkeypatch.setattr(photo_tags, "detect_tags", detect)
    return searches


def test_photo_tags_lists_each_tag_with_its_role_and_is_searched_once(monkeypatch) -> None:
    searches = _fake_tag_search(
        monkeypatch,
        [square_detection(7, 400, 300, 40), square_detection(310, 900, 500, 30), square_detection(452, 60, 60, 50)],
    )
    client = TestClient(app)
    path = client.post("/capture").json()["path"]

    response = client.get(f"/api/captures/tags/{path}")
    assert response.status_code == 200
    # Roles from the ID allocation of 2026-09-20: trays 0 to 299, calibration 300 to 449,
    # corners 450 to 499.
    assert response.json() == [
        {"id": 7, "role": "tray", "centre_px": [400, 300], "placement": None},  # no calibration
        {"id": 310, "role": "calibration", "centre_px": [900, 500]},
        {"id": 452, "role": "corner", "centre_px": [60, 60]},
    ]
    assert client.get(f"/api/captures/tags/{path}").json() == response.json()
    assert len(searches) == 1


def test_photo_tags_reads_an_experiment_still_and_refuses_bad_paths(monkeypatch) -> None:
    searches = _fake_tag_search(monkeypatch, [square_detection(12, 500, 500, 40)])
    client = TestClient(app)
    _experiment, [path] = _experiment_with_photos(client, 1)
    assert path.startswith("experiments/")

    assert client.get(f"/api/captures/tags/{path}").json() == [
        {"id": 12, "role": "tray", "centre_px": [500, 500], "placement": None}
    ]
    assert len(searches) == 1
    assert client.get("/api/captures/tags/rig/2020-01-01/000000_000000").status_code == 404
    assert client.get("/api/captures/tags/etc/2026-10-14/000000_000000").status_code == 422


def test_tags_image_is_a_marked_screen_copy_made_once(monkeypatch) -> None:
    from PIL import Image
    import io

    searches = _fake_tag_search(monkeypatch, [square_detection(7, 400, 300, 80)])
    client = TestClient(app)
    path = client.post("/capture").json()["path"]

    marked = client.get(f"/gallery/image/tags/{path}")
    assert marked.status_code == 200
    assert marked.headers["content-type"] == "image/jpeg"
    plain = client.get(f"/gallery/image/screen/{path}").content
    assert Image.open(io.BytesIO(marked.content)).size == Image.open(io.BytesIO(plain)).size
    assert marked.content != plain
    assert client.get(f"/gallery/image/tags/{path}").content == marked.content
    assert len(searches) == 1
    assert client.get("/gallery/image/tags/rig/2020-01-01/000000_000000").status_code == 404


def test_tags_image_is_drawn_again_when_the_photos_stored_tags_change(monkeypatch) -> None:
    from npec_rig import images

    _fake_tag_search(monkeypatch, [square_detection(7, 400, 300, 80)])
    client = TestClient(app)
    path = client.post("/capture").json()["path"]
    before = client.get(f"/gallery/image/tags/{path}").content

    # A calibration run stores the tags it fitted to, in place of the earlier search.
    images.store_tag_detections(path.removeprefix("rig/"), [square_detection(9, 800, 600, 80)])
    assert client.get(f"/api/captures/tags/{path}").json()[0]["id"] == 9
    assert client.get(f"/gallery/image/tags/{path}").content != before


def test_photo_tags_without_a_tray_around_them_are_seen_and_not_placed(monkeypatch, isolated_calibration_dir) -> None:
    """The real tags of layout 2 of 20 October (still 080357_563754) on the synthetic camera's
    photo, which has no blue tray: each tray tag is seen, its tray not found, and nothing is
    placed from the slots any more (#331, Aaron 2026-10-29)."""
    _layout_2_calibration(monkeypatch)
    client = TestClient(app)
    path = client.post("/capture").json()["path"]

    found = {t["id"]: t for t in client.get(f"/api/captures/tags/{path}").json()}
    seen = {"found": "tag only", "warnings": ["tag seen, tray not found in the photo"]}
    assert {i: t["placement"] for i, t in found.items() if t["role"] == "tray"} == {i: seen for i in TRAYS_1_TO_12}
    assert "placement" not in found[450]  # a corner tag is not a tray


def test_photo_tags_say_how_each_tray_tag_was_found_in_the_photo(monkeypatch) -> None:
    """#331: a tray tag names the outline found from the blue plastic around it, wherever it lies
    in the tray; no slot. `one_tray_plant_scene`: tray 5's tag inside a drawn blue tray."""
    from tests.helpers import one_tray_plant_scene

    one_tray_plant_scene(monkeypatch)
    client = TestClient(app)
    path = client.post("/capture").json()["path"]

    [tag] = client.get(f"/api/captures/tags/{path}").json()
    assert tag["placement"] == {"found": "photo + tag", "warnings": []}


def test_photo_tags_need_no_slot_layout(monkeypatch, isolated_calibration_dir) -> None:
    """Trays can lie anywhere on the table (Aaron, 2026-10-29, #331): a calibration whose slot
    layout is empty still reads the photo, and the tray tag is seen."""
    from npec_rig import validation_store
    from npec_rig.calibration import CalibrationArtifact, ScaleField
    from npec_rig.calibration_store import save_calibration

    stem = "20261014T111147292361"
    save_calibration(CalibrationArtifact(created_at="2026-10-14T11:11:47+00:00", scale_field=ScaleField((1.0, 0.0, 0.0), 4.0, 0.0),
                                         frame_stem=stem), stem=stem)
    validation_store.save_slot_layout(stem, [], [])  # a layout with no slots
    _fake_tag_search(monkeypatch, [square_detection(7, 400, 300, 40)])
    client = TestClient(app)
    path = client.post("/capture").json()["path"]

    response = client.get(f"/api/captures/tags/{path}")
    assert response.status_code == 200
    seen = {"found": "tag only", "warnings": ["tag seen, tray not found in the photo"]}
    assert response.json() == [{"id": 7, "role": "tray", "centre_px": [400, 300], "placement": seen}]
    assert client.get(f"/gallery/image/tags/{path}").status_code == 200


def _layout_2_calibration(monkeypatch: pytest.MonkeyPatch) -> None:
    """The 14 October calibration with its slot layout, and a tag search that finds the real tags
    of layout 2 of 20 October (metrology log 15.5l, still 080357_563754)."""
    import json
    from pathlib import Path

    from npec_rig import validation_store
    from npec_rig.calibration import CalibrationArtifact, scale_field_from_dict
    from npec_rig.calibration_store import save_calibration
    from npec_rig.tags import TagDetection

    fixture = json.loads((Path(__file__).parent.parent / "fixtures" / "trays" / "shuffles-2026-10-20.json").read_text())
    stem = fixture["calibration"]
    save_calibration(
        CalibrationArtifact(created_at="2026-10-14T11:11:47+00:00", scale_field=scale_field_from_dict(fixture["scale_field"]),
                            frame_stem=stem, lens_position=6.05),
        stem=stem,
    )
    validation_store.save_slot_layout(stem, fixture["slots"], [])
    _fake_tag_search(monkeypatch, [
        TagDetection(t["id"], tuple(tuple(c) for c in t["corners"]),
                     (sum(c[0] for c in t["corners"]) / 4, sum(c[1] for c in t["corners"]) / 4))
        for t in fixture["stills"]["080357_563754"]
    ])


TRAYS_1_TO_12 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]


def test_each_photo_in_the_list_carries_its_tray_readings_once_read(monkeypatch, isolated_calibration_dir) -> None:
    """Readings per tray per photo (#222): the 12 trays found are the 12 of the printed shuffle map."""
    from npec_rig import tray_readings

    _layout_2_calibration(monkeypatch)
    client = TestClient(app)
    read = client.post("/capture").json()["path"]
    unread = client.post("/capture").json()["path"]
    tray_readings.read_photo(read)

    items = {i["path"]: i for i in client.get("/api/captures").json()}
    assert items[unread]["trays"] is None
    trays = items[read]["trays"]
    assert trays["status"] == "read"
    assert sorted(t["tray_id"] for t in trays["trays"]) == TRAYS_1_TO_12


def test_show_tags_also_reads_an_older_photo_for_its_trays(monkeypatch, isolated_calibration_dir) -> None:
    """Older photos are read on demand (Aaron, 2026-10-22): Show tags saves the photo's reading."""
    _layout_2_calibration(monkeypatch)
    client = TestClient(app)
    path = client.post("/capture").json()["path"]
    assert client.get(f"/api/captures/trays/{path}").json() is None

    client.get(f"/api/captures/tags/{path}")
    trays = client.get(f"/api/captures/trays/{path}").json()
    assert trays["status"] == "read"
    assert sorted(t["tray_id"] for t in trays["trays"]) == TRAYS_1_TO_12


def test_show_tags_again_keeps_a_reading_that_has_areas(monkeypatch, isolated_calibration_dir) -> None:
    """Each Show tags segmented the 64MP photo again, about 2 s and 250 MB (review of #281, #282):
    a photo whose saved reading has plant areas from the same segmenter is not read again."""
    one_tray_plant_scene(monkeypatch)
    client = TestClient(app)
    path = client.post("/capture").json()["path"]
    client.get(f"/api/captures/tags/{path}")
    first = client.get(f"/api/captures/trays/{path}").json()
    assert any(t["area_mm2"] is not None for t in first["trays"])

    client.get(f"/api/captures/tags/{path}")
    assert client.get(f"/api/captures/trays/{path}").json()["read_at"] == first["read_at"]


def test_show_tags_reads_again_a_photo_whose_areas_were_not_worked_out(monkeypatch, isolated_calibration_dir) -> None:
    """A reading saved with trays placed but no plant areas (segmenting failed) is read again."""
    one_tray_plant_scene(monkeypatch)
    client = TestClient(app)
    path = client.post("/capture").json()["path"]
    capture_id = database.captures_by_path([path])[path]["id"]
    tray = {"tray_id": 1, "slot": "North 1", "a1_corner": "SW", "placement": "placed", "centre_px": [0.0, 0.0],
            "tilt_deg": 0.0, "margin_mm": 0.0, "area_mm2": None, "segmenter": None, "plant_px": None,
            "plant_centre_px": None, "calibration": None}
    database.record_tray_readings(capture_id, read_at="2026-10-23T11:34:53+00:00", status="read", trays=[tray])

    client.get(f"/api/captures/tags/{path}")
    trays = client.get(f"/api/captures/trays/{path}").json()
    assert trays["read_at"] != "2026-10-23T11:34:53+00:00"
    assert any(t["area_mm2"] is not None for t in trays["trays"])


class _MintSquareBackend:
    """Synthetic camera whose photo is grey with one square of the benchmark plant's mint leaf
    colour (RGB 156, 228, 188, measured in the still of 23 October 2026 08:35:53 UTC, as
    tests/test_segmentation.py), in the middle of the left half."""

    @staticmethod
    def build():
        import numpy as np

        from npec_rig.camera import SyntheticBackend

        class Backend(SyntheticBackend):
            def capture_full_res(self):
                frame, metadata = super().capture_full_res()
                h, w = frame.shape[:2]
                frame[:] = 128
                frame[h * 3 // 8 : h * 5 // 8, w // 8 : w * 3 // 8] = (156, 228, 188)
                return frame, metadata

        return Backend()


def test_green_image_marks_the_plant_square_and_leaves_the_rest() -> None:
    import io

    import numpy as np
    from PIL import Image

    from npec_rig.camera import CameraManager

    CameraManager.set_instance(CameraManager(_MintSquareBackend.build()))
    client = TestClient(app)
    path = client.post("/capture").json()["path"]

    marked = client.get(f"/gallery/image/green/{path}")
    assert marked.status_code == 200
    assert marked.headers["content-type"] == "image/jpeg"
    green = np.asarray(Image.open(io.BytesIO(marked.content)).convert("RGB")).astype(int)
    plain = np.asarray(Image.open(io.BytesIO(client.get(f"/gallery/image/screen/{path}").content)).convert("RGB")).astype(int)
    assert green.shape == plain.shape
    h, w = green.shape[:2]
    inside = (slice(h * 7 // 16, h * 9 // 16), slice(w * 3 // 16, w * 5 // 16))
    outside = (slice(h * 7 // 16, h * 9 // 16), slice(w * 11 // 16, w * 13 // 16))
    assert np.abs(green[inside] - plain[inside]).mean() > 40
    assert np.abs(green[outside] - plain[outside]).mean() < 8
    assert client.get("/gallery/image/green/rig/2020-01-01/000000_000000").status_code == 404
    assert client.get("/gallery/image/green/not-a-photo").status_code == 422


def test_tray_readings_give_each_trays_plant_area_and_segmenter(monkeypatch) -> None:
    """`one_tray_plant_scene`: 1500 mm2 of plant inside tray 5, worked out by hand."""
    from tests.helpers import one_tray_plant_scene

    one_tray_plant_scene(monkeypatch)
    client = TestClient(app)
    path = client.post("/capture").json()["path"]
    client.get(f"/api/captures/tags/{path}")  # Show tags reads the photo for its trays

    tray = client.get(f"/api/captures/trays/{path}").json()["trays"][0]
    assert tray["area_mm2"] == pytest.approx(1500, rel=0.01)
    assert tray["segmenter"] == "green threshold, 0.1"


def test_each_photo_in_the_list_carries_its_exclusion_and_each_area_its_floor(monkeypatch, isolated_calibration_dir) -> None:
    """#288: a photo taken with the lights off (64,022 us at gain 4.0, a real photo of experiment
    18) is excluded as such, and each tray area shows the green threshold's floor, 100 mm2
    (Aaron, 2026-10-26)."""
    from npec_rig import tray_readings
    from npec_rig.camera import CameraManager, SyntheticBackend

    class Dark(SyntheticBackend):
        def capture_full_res(self):
            frame, metadata = super().capture_full_res()
            frame[:] = 128
            draw_tray(frame, 115, 554, 3165, 4214)  # one_tray_plant_scene's tray
            return frame, {**metadata, "ExposureTime": 64_022, "AnalogueGain": 4.0}

    one_tray_plant_scene(monkeypatch)
    CameraManager.set_instance(CameraManager(Dark(width=4000, height=4400)))
    client = TestClient(app)
    path = client.post("/capture").json()["path"]
    tray_readings.read_photo(path)

    trays = {i["path"]: i for i in client.get("/api/captures").json()}[path]["trays"]
    assert trays["exclusion"] == "lights off"
    assert [t["floor_mm2"] for t in trays["trays"]] == [100]


def test_the_light_warning_is_shown_until_dismissed_and_the_dismissal_is_saved() -> None:
    """A first day steady at 5,000, then 5 photos at 4,000 (-20%) 30 minutes apart from 25 h and
    one back: 2.5 hours off norm (#288). Dismiss saves when, and the warning is gone."""
    start = datetime.fromisoformat("2026-10-22T08:00:00+00:00")
    series = [(timedelta(hours=h), 5000) for h in range(25)]
    series[5] = (timedelta(hours=5), 5300)
    series += [(timedelta(hours=25, minutes=30 * i), 4000) for i in range(5)]
    series += [(timedelta(hours=27, minutes=30), 5000)]
    experiment_id = captures.create_experiment(name="Light")["id"]
    record_light_photos(experiment_id, start, series, "light")
    client = TestClient(app)

    response = client.get("/api/captures/light-warning", params={"experiment": experiment_id})
    assert response.status_code == 200
    assert response.json() == {
        "hours": 2.5, "first": "2026-10-23T09:00:00+00:00", "last": "2026-10-23T11:30:00+00:00",
    }

    before = datetime.now().astimezone()
    assert client.post(
        "/api/captures/light-warning/dismiss",
        params={"experiment": experiment_id, "until": "2026-10-23T11:30:00+00:00"},
    ).status_code == 200
    assert client.get("/api/captures/light-warning", params={"experiment": experiment_id}).json() is None
    [dismissal] = database.light_warning_dismissals(experiment_id)
    assert dismissal["covers_until"] == "2026-10-23T11:30:00+00:00"
    assert before <= datetime.fromisoformat(dismissal["dismissed_at"]) <= datetime.now().astimezone()


def test_a_reading_saved_before_trays_were_found_in_the_photo_keeps_its_trays_outline(monkeypatch) -> None:
    """Review of #334: a photo read before #331 (tray 5 placed from its tag, with an area) has no
    stored outline. Its tray is shown as the old placement drew it, the tray's outside size
    305 x 366 mm around the stored centre at the calibration's 10 px/mm: x 115 to 3165, y 554 to
    4214 (`one_tray_plant_scene`), and its tag is taken as inside it, not as a tray not read."""
    import json
    from pathlib import Path

    one_tray_plant_scene(monkeypatch)
    stem = json.loads((Path(__file__).parent.parent / "fixtures" / "trays" / "shuffles-2026-10-20.json").read_text())["calibration"]
    client = TestClient(app)
    path = client.post("/capture").json()["path"]
    capture_id = database.captures_by_path([path])[path]["id"]
    database.record_tray_readings(capture_id, read_at="2026-10-28T10:00:00+00:00", status="read", trays=[{
        "tray_id": 5, "slot": "North 1", "a1_corner": "SW", "placement": "placed", "centre_px": [1640.0, 2384.0],
        "tilt_deg": 0.0, "margin_mm": 200.0, "area_mm2": 1500.0, "segmenter": "green threshold, 0.1", "calibration": stem,
    }])

    [tag] = client.get(f"/api/captures/tags/{path}").json()
    assert tag["placement"] is not None
    [tray] = client.get(f"/api/captures/trays/{path}").json()["trays"]
    corners = sorted(tray["outline_px"])
    assert [v for c in corners for v in c] == pytest.approx([115, 554, 115, 4214, 3165, 554, 3165, 4214], abs=1)


def test_the_tags_image_never_reads_the_photo_for_trays_and_draws_them_once_read(monkeypatch) -> None:
    """Review of #334: Tags asks for the tag list and the image at once; both reading the 64MP
    photo meant two decodes and two segmentations side by side. The tag list reads it; the image
    draws only a reading already saved, and is drawn again once there is one."""
    one_tray_plant_scene(monkeypatch)
    client = TestClient(app)
    path = client.post("/capture").json()["path"]

    before = client.get(f"/gallery/image/tags/{path}")
    assert before.status_code == 200
    assert client.get(f"/api/captures/trays/{path}").json() is None

    client.get(f"/api/captures/tags/{path}")
    assert client.get(f"/api/captures/trays/{path}").json()["status"] == "read"
    assert client.get(f"/gallery/image/tags/{path}").content != before.content


def test_a_photo_taken_before_the_clock_had_the_network_time_is_marked_in_the_list(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(captures, "CLOCK_SYNC_MARKER", tmp_path / "synchronized")  # not there
    client = TestClient(app)
    unset = client.post("/capture").json()
    (tmp_path / "synchronized").touch()
    synced = client.post("/capture").json()

    items = {item["filename"]: item for item in client.get("/api/captures").json()}

    assert items[unset["filename"]]["clock"] == {
        "synchronized": False, "reason": "time may be wrong: clock not set"}
    assert items[synced["filename"]]["clock"]["synchronized"] is True
