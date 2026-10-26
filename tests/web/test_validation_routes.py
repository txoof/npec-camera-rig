import io

import pytest
from PIL import Image
from fastapi.testclient import TestClient

import npec_rig.photo_tags as photo_tags
import npec_rig.routes.validation as validation_routes
from npec_rig import captures, images, validation_store
from npec_rig.app import app
from tests.helpers import sheet_detections, tray_layout_detections
from tests.web.tag_scenes import CORNER_TAGS

pytestmark = pytest.mark.unit


# --- Validation sessions ---
# `detect_tags` returns whatever layout the test last set: the calibration frame, then each
# round's shuffled sheets. The synthetic camera's frames have no real tags in them.


@pytest.fixture
def tray_scene(monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None) -> dict:
    # bad_sheet: index (0-11, North 1..6 then South 1..6) of a sheet printed at 96%, or None.
    scene = {"shift": (0.0, 0.0), "drop_sheets": 0, "bad_sheet": None}

    def detect(frame):
        tags = tray_layout_detections(shift=scene["shift"])
        k = scene["bad_sheet"]
        if k is not None:
            dx, dy = scene["shift"]
            x0, y0 = 800.0 + (k % 6) * 1300.0 + dx, (1000.0, 3500.0)[k // 6] + dy
            tags[k * 30 : (k + 1) * 30] = sheet_detections(325, x0, y0, side_px=120.0 * 0.96)
        return tags[30 * scene["drop_sheets"] :] + CORNER_TAGS

    monkeypatch.setattr(photo_tags, "detect_tags", detect)
    return scene


def _calibrate_and_start(client: TestClient, lock_focus: bool = True) -> dict:
    client.post("/calibration/run")
    if lock_focus:
        client.post("/focus/lock")
    response = client.post("/validation/sessions")
    assert response.status_code == 200
    return response.json()


def test_a_moving_bad_sheet_is_named_with_a_full_frame_image_per_round(tray_scene: dict) -> None:
    client = TestClient(app)
    session = _calibrate_and_start(client)
    # North 2 (index 1), South 5 (10), North 5 (4): the chamber fault test's moving case.
    for shift, bad in (((200, -150), 1), ((-250, 100), 10), ((100, 230), 4)):
        tray_scene["shift"], tray_scene["bad_sheet"] = shift, bad
        body = client.post(f"/validation/sessions/{session['id']}/rounds").json()
    assert body["inconsistent_slots"] == ["North 2", "North 5", "South 5"]
    assert [(p["round"], p["slot"]) for p in body["problems"]] == [(1, "North 2"), (2, "South 5"), (3, "North 5")]

    image = client.get(f"/validation/sessions/{session['id']}/rounds/2/problems")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(image.content)) as frame:
        assert frame.width == 2000  # the full frame, not a crop
    assert client.get(f"/validation/sessions/{session['id']}/rounds/9/problems").status_code == 404
    assert client.get(f"/validation/sessions/{session['id']}/offsets").status_code == 404


def test_validation_images_are_made_once_and_need_no_tag_search_after_a_restart(
    tray_scene: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 2026-10-02: after a restart the validation page asked for 10 images, each decoding a 64MP
    # capture again (about 7 s each, one after another).
    client = TestClient(app)
    session = _calibrate_and_start(client)
    for shift, bad in (((200, -150), 1), ((-250, 100), 10), ((100, 230), 4)):
        tray_scene["shift"], tray_scene["bad_sheet"] = shift, bad
        client.post(f"/validation/sessions/{session['id']}/rounds")
    urls = [f"/validation/sessions/{session['id']}/rounds/2/problems", f"/validation/sessions/{session['id']}/map"]
    first = [client.get(url) for url in urls]
    assert [r.status_code for r in first] == [200, 200]
    assert first[0].headers["cache-control"] == "no-cache"

    def must_not_run(*_args, **_kwargs):
        raise AssertionError("drawn again")

    drawers = {name: getattr(validation_routes, name) for name in ("render_problem_frame", "render_certainty_map")}
    for name in drawers:
        monkeypatch.setattr(validation_routes, name, must_not_run)
    assert [client.get(url).content for url in urls] == [r.content for r in first]  # from disk

    # A restart: derived images gone. Tags come from the analysis store. (Only the two drawers are
    # restored: monkeypatch.undo() would also drop the per-test DB and folders.)
    for name, drawer in drawers.items():
        monkeypatch.setattr(validation_routes, name, drawer)
    monkeypatch.setattr(photo_tags, "detect_tags", must_not_run)
    for path in images.derived_root().rglob("*.bin"):
        path.unlink()
    assert [client.get(url).status_code for url in urls] == [200, 200]


def test_a_bad_sheet_that_never_moves_is_flagged_with_an_image(tray_scene: dict) -> None:
    client = TestClient(app)
    session = _calibrate_and_start(client)
    tray_scene["bad_sheet"] = 1  # North 2, every round
    for shift in ((200, -150), (-250, 100), (100, 230)):
        tray_scene["shift"] = shift
        body = client.post(f"/validation/sessions/{session['id']}/rounds").json()
    assert body["problems"] == []
    assert [p["slot"] for p in body["offset_problems"]] == ["North 2"]
    assert body["flagged_slots"] == ["North 2"]
    assert not body["validated"]
    image = client.get(f"/validation/sessions/{session['id']}/offsets")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"


def test_validation_page_loads() -> None:
    response = TestClient(app).get("/setup/validation")
    assert response.status_code == 200
    assert "Capture round" in response.text


def test_validation_needs_an_active_calibration(isolated_calibration_dir: None) -> None:
    assert TestClient(app).post("/validation/sessions").status_code == 409


def test_three_shuffled_rounds_complete_a_validation(tray_scene: dict) -> None:
    client = TestClient(app)
    session = _calibrate_and_start(client)
    assert session["rounds_counted"] == 0 and session["map_url"] is None
    assert client.get(f"/validation/sessions/{session['id']}/map").status_code == 409

    for shift in ((200, -150), (-250, 100), (100, 230)):
        tray_scene["shift"] = shift
        response = client.post(f"/validation/sessions/{session['id']}/rounds")
        assert response.status_code == 200
        body = response.json()
        assert body["rounds"][-1]["counted"], body["rounds"][-1]["reason"]

    assert body["rounds_counted"] == 3
    assert body["completed_at"] is not None
    assert [r["n"] for r in body["results"]] == [90] * 12
    assert body["certainty_range_pct"] == pytest.approx([0.0, 0.0])
    response = client.get(body["map_url"])
    assert response.status_code == 200
    assert response.content[:2] == b"\xff\xd8"
    listed = client.get("/validation/sessions").json()
    assert [s["id"] for s in listed] == [session["id"]]
    assert listed[0]["is_current_calibration"]


def test_an_unmoved_round_is_held_back_until_overridden(tray_scene: dict) -> None:
    client = TestClient(app)
    session = _calibrate_and_start(client)
    body = client.post(f"/validation/sessions/{session['id']}/rounds").json()
    held = body["rounds"][0]
    assert not held["counted"] and held["overridable"]
    assert held["moved_pct"] == 0.0
    assert "moved" in held["reason"]

    body = client.post(f"/validation/sessions/{session['id']}/rounds/0/count").json()
    assert body["rounds"][0]["counted"] and body["rounds"][0]["overridden"]
    assert body["rounds_counted"] == 1
    again = client.post(f"/validation/sessions/{session['id']}/rounds/0/count")
    assert again.status_code == 409


def test_a_round_without_focus_locked_is_held_back(tray_scene: dict) -> None:
    client = TestClient(app)
    session = _calibrate_and_start(client, lock_focus=False)
    tray_scene["shift"] = (200, -150)
    held = client.post(f"/validation/sessions/{session['id']}/rounds").json()["rounds"][0]
    assert not held["counted"] and held["overridable"]
    assert "focus is not locked" in held["reason"]


def test_a_round_inside_the_cold_start_window_is_held_back_until_overridden(
    tray_scene: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(app)
    session = _calibrate_and_start(client)
    tray_scene["shift"] = (200, -150)
    monkeypatch.setattr(captures, "read_uptime_s", lambda: 1200.0)
    held = client.post(f"/validation/sessions/{session['id']}/rounds").json()["rounds"][0]
    assert not held["counted"] and held["overridable"]
    assert "cold-start window" in held["reason"]
    body = client.post(f"/validation/sessions/{session['id']}/rounds/0/count").json()
    assert body["rounds"][0]["counted"]


def test_a_round_after_a_camera_fault_is_held_back_until_overridden(tray_scene: dict) -> None:
    from npec_rig import health

    client = TestClient(app)
    session = _calibrate_and_start(client)
    tray_scene["shift"] = (200, -150)
    health.record_camera_event(
        health.EVENT_FAULT, call="capture_full_res", limit_s=30.0, detail="test fault"
    )
    health.record_camera_event(health.EVENT_RESTARTED, recovery_s=1.1)
    held = client.post(f"/validation/sessions/{session['id']}/rounds").json()["rounds"][0]
    assert not held["counted"] and held["overridable"]
    assert "camera-fault window" in held["reason"]
    body = client.post(f"/validation/sessions/{session['id']}/rounds/0/count").json()
    assert body["rounds"][0]["counted"]


def test_a_round_missing_a_sheet_cannot_be_overridden(tray_scene: dict) -> None:
    client = TestClient(app)
    session = _calibrate_and_start(client)
    tray_scene["shift"], tray_scene["drop_sheets"] = (200, -150), 1
    held = client.post(f"/validation/sessions/{session['id']}/rounds").json()["rounds"][0]
    assert not held["counted"] and not held["overridable"]
    assert "found 11 calibration sheets, expected 12" in held["reason"]
    assert client.post(f"/validation/sessions/{session['id']}/rounds/0/count").status_code == 409


def test_a_round_at_the_wrong_focus_says_so_even_when_no_sheets_are_found(tray_scene: dict) -> None:
    # Aaron, 2026-09-30: an out-of-focus round finds no sheets, and the message blamed only the
    # sheets. Focus is now named first.
    client = TestClient(app)
    session = _calibrate_and_start(client, lock_focus=False)
    tray_scene["drop_sheets"] = 12
    held = client.post(f"/validation/sessions/{session['id']}/rounds").json()["rounds"][0]
    assert not held["counted"]
    assert held["reason"].startswith("focus is not locked; found 0 calibration sheets")


def test_a_calibrations_slot_layout_is_worked_out_once_and_kept(
    tray_scene: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 2026-10-02: "Start validation" froze for about 15 s after a restart, decoding the 64MP
    # calibration frame again. The layout is now saved, so a later start does not decode.
    client = TestClient(app)
    first = _calibrate_and_start(client)
    monkeypatch.setattr(photo_tags, "calibration_tags", lambda stem: pytest.fail("decoded again"))
    second = client.post("/validation/sessions")
    assert second.status_code == 200
    assert second.json()["results"] == [
        {**r, "n": 0, "p95_abs_pct": None, "median_pct": None} for r in first["results"]
    ]
    stem = first["calibration_stem"]
    client.post("/calibration/run")  # a newer calibration, so the first can be deleted
    assert client.delete(f"/calibration/{stem}").status_code == 200
    assert validation_store.load_slot_layout(stem) is None


def test_rounds_refused_once_the_calibration_is_replaced(tray_scene: dict) -> None:
    client = TestClient(app)
    session = _calibrate_and_start(client)
    client.post("/calibration/run")
    response = client.post(f"/validation/sessions/{session['id']}/rounds")
    assert response.status_code == 409
    assert not client.get(f"/validation/sessions/{session['id']}").json()["is_current_calibration"]


def test_deleting_a_session_and_its_calibration(tray_scene: dict) -> None:
    client = TestClient(app)
    first = _calibrate_and_start(client)
    kept = client.post("/validation/sessions").json()
    assert client.delete(f"/validation/sessions/{kept['id']}").status_code == 200
    assert client.get(f"/validation/sessions/{kept['id']}").status_code == 404
    assert client.get("/validation/sessions/not-an-id").status_code == 404

    client.post("/calibration/run")  # a newer calibration becomes active
    assert client.delete(f"/calibration/{first['calibration_stem']}").status_code == 200
    assert client.get(f"/validation/sessions/{first['id']}").status_code == 404


def test_a_session_reports_each_rounds_figures_and_how_far_medians_moved(tray_scene: dict) -> None:
    client = TestClient(app)
    session = _calibrate_and_start(client)
    for shift in ((200, -150), (-250, 100)):
        tray_scene["shift"] = shift
        body = client.post(f"/validation/sessions/{session['id']}/rounds").json()
    assert [sorted(r["slots"]) for r in body["rounds"]] == [sorted(r["name"] for r in body["results"])] * 2
    assert body["rounds"][0]["slots"]["North 1"]["n"] == 30
    assert body["median_range_pct"]["North 1"] == pytest.approx(0.0)
    assert body["median_disagreement_pct"] > 0
    assert body["inconsistent_slots"] == []
    assert body["problems"] == []
    assert not body["validated"]  # 2 of 3 rounds: consistent so far, not yet validated


def test_no_override_once_the_calibration_is_replaced(tray_scene: dict) -> None:
    client = TestClient(app)
    session = _calibrate_and_start(client)
    client.post(f"/validation/sessions/{session['id']}/rounds")  # unmoved: held back, overridable
    client.post("/calibration/run")
    assert client.post(f"/validation/sessions/{session['id']}/rounds/0/count").status_code == 409


def test_ending_a_validation_stops_rounds(tray_scene: dict) -> None:
    client = TestClient(app)
    session = _calibrate_and_start(client)
    assert session["is_open"] and session["ended_at"] is None
    ended = client.post(f"/validation/sessions/{session['id']}/end").json()
    assert not ended["is_open"] and ended["ended_at"] is not None
    tray_scene["shift"] = (200, -150)
    assert client.post(f"/validation/sessions/{session['id']}/rounds").status_code == 409


def test_starting_a_validation_ends_the_open_one(tray_scene: dict) -> None:
    client = TestClient(app)
    first = _calibrate_and_start(client)
    second = client.post("/validation/sessions").json()
    assert client.get(f"/validation/sessions/{first['id']}").json()["ended_at"] is not None
    assert client.get(f"/validation/sessions/{second['id']}").json()["is_open"]


def test_validation_status_follows_the_newest_session_of_the_active_calibration(tray_scene: dict) -> None:
    client = TestClient(app)
    assert client.get("/validation/status").json()["state"] == "no_calibration"
    client.post("/calibration/run")
    client.post("/focus/lock")
    status = client.get("/validation/status").json()
    assert status == {
        "state": "not_validated",
        "text": "Not validated: no validation of this calibration yet",
        "session_id": None,
    }

    session = client.post("/validation/sessions").json()
    for shift in ((200, -150), (-250, 100), (100, 230)):
        tray_scene["shift"] = shift
        client.post(f"/validation/sessions/{session['id']}/rounds")
        status = client.get("/validation/status").json()
        if shift != (100, 230):
            assert status["state"] == "not_validated" and "so far" in status["text"]
    assert status["state"] == "validated" and status["session_id"] == session["id"]
    assert status["text"].startswith("Validated ")
    # The three rounds here are seconds apart: the status says they were spread too little.
    assert "under the recommended 20" in status["text"]
    summary = client.get(f"/validation/sessions/{session['id']}").json()
    assert summary["short_span"] is True and summary["min_span_minutes"] == 20
    assert summary["min_round_gap_minutes"] == 10
    assert summary["short_gap"] is True and summary["shortest_gap_minutes"] < 1
    assert "apart, under the recommended 10" in status["text"]
    assert summary["first_counted_at"] <= summary["last_counted_at"]
    assert summary["round_span_minutes"] < 1

    # A newer session does not replace the complete one until it completes itself (Aaron,
    # 2026-10-16, #183): the status line keeps the current one and names the newer one.
    client.post("/validation/sessions")
    status = client.get("/validation/status").json()
    assert (status["state"], status["session_id"]) == ("validated", session["id"])
    assert status["text"].endswith("; a newer validation is in progress, 0 of 3 rounds")


def test_validation_status_names_a_slot_that_is_not_consistent(tray_scene: dict) -> None:
    client = TestClient(app)
    session = _calibrate_and_start(client)
    for shift, bad in (((200, -150), 1), ((-250, 100), 10)):
        tray_scene["shift"], tray_scene["bad_sheet"] = shift, bad
        client.post(f"/validation/sessions/{session['id']}/rounds")
    status = client.get("/validation/status").json()
    assert status["state"] == "not_consistent"
    assert status["text"] == "Not consistent: North 2, South 5"


def test_validation_status_does_not_apply_at_another_focus(tray_scene: dict) -> None:
    client = TestClient(app)
    _calibrate_and_start(client)
    client.post("/focus/unlock")
    status = client.get("/validation/status").json()
    assert status["state"] == "focus_mismatch"
    assert status["text"] == "Not validated at this focus: focus is not locked"
