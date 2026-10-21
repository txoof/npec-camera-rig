import pytest
from fastapi.testclient import TestClient

from npec_rig import photo_tags
from npec_rig.app import app
from tests.helpers import square_detection

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
    assert hours and all(set(h) == {"hour", "count"} for h in hours)


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


def test_photo_tags_place_each_tray_tag_with_the_photos_calibration(monkeypatch, isolated_calibration_dir) -> None:
    """Layout 2 of 20 October (metrology log 15.5l), the real tags of still 080357_563754 with
    their calibration's scale and slot layout. The expected slots and corners are the printed
    shuffle map, as in tests/test_tray_placement.py."""
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
    tags = [TagDetection(t["id"], tuple(tuple(c) for c in t["corners"]),
                         (sum(c[0] for c in t["corners"]) / 4, sum(c[1] for c in t["corners"]) / 4))
            for t in fixture["stills"]["080357_563754"]]
    _fake_tag_search(monkeypatch, tags)
    client = TestClient(app)
    path = client.post("/capture").json()["path"]

    found = {t["id"]: t for t in client.get(f"/api/captures/tags/{path}").json()}
    placed = {i: (t["placement"]["slot"], t["placement"]["a1_corner"], t["placement"]["status"])
              for i, t in found.items() if t["role"] == "tray"}
    assert placed == {
        3: ("North 1", "SW", "placed"), 10: ("North 2", "SW", "placed"), 6: ("North 3", "SW", "placed"),
        1: ("North 4", "NE", "placed"), 4: ("North 5", "SW", "placed"), 12: ("North 6", "NE", "placed"),
        9: ("South 1", "NE", "placed"), 11: ("South 2", "SW", "placed"), 7: ("South 3", "NE", "placed"),
        8: ("South 4", "SW", "placed"), 5: ("South 5", "SW", "placed"), 2: ("South 6", "SW", "placed"),
    }
    assert "placement" not in found[450]  # a corner tag is not a tray


def test_photo_tags_still_list_the_tags_when_the_saved_slot_layout_is_unusable(monkeypatch, isolated_calibration_dir) -> None:
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
    assert response.json() == [{"id": 7, "role": "tray", "centre_px": [400, 300], "placement": None}]
    assert client.get(f"/gallery/image/tags/{path}").status_code == 200
