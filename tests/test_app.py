from pathlib import Path

import pytest
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

import npec_rig.app as app_module
from npec_rig.app import _mjpeg_frames, app, focus_roi_stream, preview
from npec_rig.calibration import CalibrationArtifact, ScaleField
from npec_rig.calibration_store import save_calibration
from npec_rig.camera import SIMULATED_AUTOFOCUS_POSITION, CameraManager, SyntheticBackend
from npec_rig.tags import ASSUMED_CALIBRATION_TAG_SIZE_MM
from npec_rig.tripwire import CornerBaseline
from tests.helpers import rotate_detection, square_detection

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def synthetic_camera() -> None:
    CameraManager.set_instance(CameraManager(SyntheticBackend()))


@pytest.fixture
def isolated_calibration_dir(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("NPEC_RIG_CALIBRATION_DIR", str(tmp_path / "calibration"))


@pytest.fixture(autouse=True)
def reset_live_orientation_zero() -> None:
    # Module-level state (TODO.md's "Live reorientation guidance" -- in-memory by design, not
    # persisted), so it must not leak a zero point set by one test into the next.
    app_module._live_orientation_baseline = None


def test_index_page_loads() -> None:
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "NPEC Camera Rig" in response.text


def test_snapshot_returns_jpeg() -> None:
    client = TestClient(app)
    response = client.get("/snapshot.jpg")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content[:2] == b"\xff\xd8"


def test_mjpeg_frames_yields_a_jpeg_chunk() -> None:
    # The generator runs forever by design (it's a live stream), so it's tested directly
    # rather than through a real HTTP round trip — an infinite response body has no place
    # in the unit tier.
    manager = CameraManager(SyntheticBackend())
    frames = _mjpeg_frames(manager.preview_jpeg, fps_limit=1000.0)
    try:
        chunk = next(frames)
    finally:
        frames.close()
    assert b"Content-Type: image/jpeg" in chunk
    assert b"\xff\xd8" in chunk


def test_preview_route_returns_mjpeg_streaming_response() -> None:
    response = preview()
    assert isinstance(response, StreamingResponse)
    assert "multipart/x-mixed-replace" in response.media_type


def test_focus_roi_stream_route_returns_mjpeg_streaming_response() -> None:
    response = focus_roi_stream()
    assert isinstance(response, StreamingResponse)
    assert "multipart/x-mixed-replace" in response.media_type


def test_lens_position_get_and_set() -> None:
    client = TestClient(app)
    response = client.post("/controls/lens-position", json={"value": 6.3})
    assert response.status_code == 200
    assert response.json() == {"value": 6.3}

    response = client.get("/controls/lens-position")
    assert response.status_code == 200
    assert response.json() == {"value": 6.3}


def test_autofocus_endpoint() -> None:
    client = TestClient(app)
    response = client.post("/focus/autofocus")
    assert response.status_code == 200
    assert response.json() == {"success": True, "lens_position": SIMULATED_AUTOFOCUS_POSITION}


def test_lens_position_rejects_out_of_range() -> None:
    client = TestClient(app)
    response = client.post("/controls/lens-position", json={"value": 99})
    assert response.status_code == 422


def test_list_controls_returns_available_and_current_values() -> None:
    client = TestClient(app)
    response = client.get("/controls")
    assert response.status_code == 200
    body = response.json()
    assert "AnalogueGain" in body["available"]
    assert "AnalogueGain" in body["values"]


def test_set_control_updates_value() -> None:
    client = TestClient(app)
    response = client.post("/controls/AnalogueGain", json={"value": 4.0})
    assert response.status_code == 200
    assert response.json()["AnalogueGain"] == 4.0

    response = client.get("/controls")
    assert response.json()["values"]["AnalogueGain"] == 4.0


def test_set_control_rejects_unknown_name() -> None:
    client = TestClient(app)
    response = client.post("/controls/NotARealControl", json={"value": 1})
    assert response.status_code == 404


def test_set_control_rejects_lens_position_by_name() -> None:
    # LensPosition has its own dedicated endpoint; not reachable through the generic one.
    client = TestClient(app)
    response = client.post("/controls/LensPosition", json={"value": 6.3})
    assert response.status_code == 404


def test_set_control_rejects_out_of_range() -> None:
    client = TestClient(app)
    response = client.post("/controls/AnalogueGain", json={"value": 999})
    assert response.status_code == 422


def test_set_control_updates_a_bool_control() -> None:
    # AwbEnable/AeEnable take the isinstance(min_value, bool) branch in set_control, distinct
    # from the float branch every other control test exercises — untested until now.
    client = TestClient(app)
    response = client.post("/controls/AwbEnable", json={"value": False})
    assert response.status_code == 200
    assert response.json()["AwbEnable"] is False

    response = client.get("/controls")
    assert response.json()["values"]["AwbEnable"] is False


def test_roi_get_and_set() -> None:
    client = TestClient(app)
    response = client.post("/focus/roi", json={"x": 100, "y": 80, "size": 50})
    assert response.status_code == 200
    assert response.json() == {"x": 100, "y": 80, "size": 50}

    response = client.get("/focus/roi")
    assert response.status_code == 200
    assert response.json() == {"x": 100, "y": 80, "size": 50}


def test_roi_rejects_negative_coordinates() -> None:
    client = TestClient(app)
    response = client.post("/focus/roi", json={"x": -1, "y": 0, "size": 50})
    assert response.status_code == 422


def test_roi_rejects_non_positive_size() -> None:
    client = TestClient(app)
    response = client.post("/focus/roi", json={"x": 0, "y": 0, "size": 0})
    assert response.status_code == 422


def test_peaking_get_and_set() -> None:
    client = TestClient(app)
    response = client.get("/focus/peaking")
    assert response.status_code == 200
    assert response.json() == {"enabled": False}

    response = client.post("/focus/peaking", json={"enabled": True})
    assert response.status_code == 200
    assert response.json() == {"enabled": True}

    response = client.get("/focus/peaking")
    assert response.json() == {"enabled": True}


def test_focus_score_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/focus/score")
    assert response.status_code == 200
    # SyntheticBackend's pattern is flat, so the score is deterministically zero, not just "a
    # float" — pin the value.
    assert response.json()["score"] == 0.0


def test_focus_lock_and_unlock() -> None:
    client = TestClient(app)
    client.post("/controls/lens-position", json={"value": 6.3})

    response = client.post("/focus/lock")
    assert response.status_code == 200
    assert response.json() == {"locked": True, "lens_position": 6.3}

    response = client.get("/focus/status")
    assert response.json() == {"locked": True, "lens_position": 6.3}

    response = client.post("/focus/unlock")
    assert response.json() == {"locked": False, "lens_position": None}


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


# --- Calibration ---
# SyntheticBackend's frame has no real tags drawn into it, so `detect_tags` finds nothing on a
# plain capture -- exercising the "not enough tags" path for free. The happy path monkeypatches
# `detect_tags` with `square_detection`-built fixtures (same synthetic-geometry convention as
# test_calibration.py/test_tripwire.py), since drawing a real detectable tag into the frame isn't
# needed to test this module's own wiring.

_CALIBRATION_TAGS = [
    square_detection(300 + i, cx, cy, side_px=40.0)
    for i, (cx, cy) in enumerate(
        [(200, 200), (1300, 200), (200, 950), (1300, 950), (750, 575), (500, 400)]
    )
]
_CORNER_TAGS = [
    square_detection(450, 30, 30, side_px=60.0),
    square_detection(451, 1500, 30, side_px=60.0),
]


def test_run_calibration_reports_insufficient_tags(isolated_calibration_dir: None) -> None:
    client = TestClient(app)
    response = client.post("/calibration/run")
    assert response.status_code == 200
    body = response.json()
    assert body["calibration_tags_detected"] == 0
    assert body["corner_tags_detected"] == 0
    assert "error" in body


def test_run_calibration_builds_field_and_saves_artifact_and_frame(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(
        app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS
    )

    client = TestClient(app)
    response = client.post("/calibration/run")
    assert response.status_code == 200
    body = response.json()

    assert "error" not in body
    assert body["calibration_tags_detected"] == len(_CALIBRATION_TAGS)
    assert body["corner_tags_detected"] == len(_CORNER_TAGS)
    assert body["corner_baseline_tags"] == [450, 451]
    assert body["report"]
    assert isinstance(body["residual_std_pct"], float)

    assert Path(body["frame_path"]).exists()
    assert Path(body["artifact_path"]).exists()

    current = client.get("/calibration/current").json()
    assert current["exists"] is True
    assert current["corner_baseline_tags"] == [450, 451]
    assert current["residual_std_pct"] == body["residual_std_pct"]


def test_run_calibration_accepts_a_measured_tag_size_override(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    # The point of the override: a reprint of the calibration sheets can come out at a different
    # physical size, and that's the operator's callipers to measure, not a source-code constant.
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)

    client = TestClient(app)
    response = client.post("/calibration/run", params={"calibration_tag_size_mm": 30.02})
    assert response.status_code == 200
    body = response.json()
    assert body["calibration_tag_size_mm"] == 30.02
    assert body["calibration_tag_size_mm_is_default"] is False

    current = client.get("/calibration/current").json()
    assert current["calibration_tag_size_mm"] == 30.02


def test_run_calibration_without_override_uses_the_placeholder_default(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)

    client = TestClient(app)
    response = client.post("/calibration/run")
    assert response.status_code == 200
    body = response.json()
    assert body["calibration_tag_size_mm"] == ASSUMED_CALIBRATION_TAG_SIZE_MM
    assert body["calibration_tag_size_mm_is_default"] is True


def test_current_calibration_before_any_run(isolated_calibration_dir: None) -> None:
    client = TestClient(app)
    response = client.get("/calibration/current")
    assert response.status_code == 200
    assert response.json() == {"exists": False}


def test_tripwire_check_without_baseline_is_refused(isolated_calibration_dir: None) -> None:
    client = TestClient(app)
    response = client.post("/calibration/tripwire/check")
    assert response.status_code == 409


def test_tripwire_check_against_saved_baseline(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    baseline = CornerBaseline(corners_by_id={d.tag_id: d.corners for d in _CORNER_TAGS})
    artifact = CalibrationArtifact(
        created_at="2026-09-20T12:00:00+00:00",
        scale_field=ScaleField(_coeffs=(1.0, 0.0, 0.0), _mean_px_per_mm=4.0, residual_std_pct=1.0),
        corner_baseline=baseline,
        lens_position=6.3,
    )
    save_calibration(artifact)

    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CORNER_TAGS)

    client = TestClient(app)
    response = client.post("/calibration/tripwire/check")
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "OK"
    assert body["roll_deg"] == pytest.approx(0.0)


def test_tripwire_check_reports_a_real_roll_through_the_json_round_trip(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    # Unlike the zero-motion case above, this proves roll_deg/scale_delta_pct survive the
    # endpoint's dict-building and JSON encoding with real (non-zero, non-default) values, not
    # just that the wiring doesn't crash -- what Aaron will actually be reading off the screen
    # during the roll-camera acceptance test.
    baseline = CornerBaseline(corners_by_id={d.tag_id: d.corners for d in _CORNER_TAGS})
    artifact = CalibrationArtifact(
        created_at="2026-09-20T12:00:00+00:00",
        scale_field=ScaleField(_coeffs=(1.0, 0.0, 0.0), _mean_px_per_mm=4.0, residual_std_pct=1.0),
        corner_baseline=baseline,
        lens_position=6.3,
    )
    save_calibration(artifact)

    pivot = (750, 500)
    rolled = [rotate_detection(d, pivot, 5.0) for d in _CORNER_TAGS]
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: rolled)

    client = TestClient(app)
    response = client.post("/calibration/tripwire/check")
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "DRIFT"
    assert body["roll_deg"] == pytest.approx(5.0, abs=0.01)
    assert set(body["scale_delta_pct"].keys()) == {"450", "451"}


def test_live_orientation_without_zero_is_refused() -> None:
    client = TestClient(app)
    response = client.get("/calibration/orientation/live")
    assert response.status_code == 409


def test_zero_live_orientation_refuses_with_no_corner_tags() -> None:
    # SyntheticBackend's preview frame has no real tags drawn -- same "nothing detected" path
    # as /calibration/run's insufficient-tags case.
    client = TestClient(app)
    response = client.post("/calibration/orientation/zero")
    assert response.status_code == 409


def test_zero_live_orientation_builds_baseline_from_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CORNER_TAGS)

    client = TestClient(app)
    response = client.post("/calibration/orientation/zero")
    assert response.status_code == 200
    assert response.json() == {"corner_tags": [450, 451]}


def test_live_orientation_is_ok_at_the_zero_point(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CORNER_TAGS)

    client = TestClient(app)
    assert client.post("/calibration/orientation/zero").status_code == 200

    response = client.get("/calibration/orientation/live")
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "OK"
    assert body["roll_deg"] == pytest.approx(0.0)


def test_live_orientation_reports_roll_after_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    # Same convention as test_tripwire_check_reports_a_real_roll_through_the_json_round_trip:
    # proves roll_deg survives this endpoint's own dict-building and JSON encoding with a real,
    # non-zero value -- what Aaron reads off the screen while nudging the rig by hand.
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CORNER_TAGS)

    client = TestClient(app)
    assert client.post("/calibration/orientation/zero").status_code == 200

    pivot = (750, 500)
    rolled = [rotate_detection(d, pivot, 5.0) for d in _CORNER_TAGS]
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: rolled)

    response = client.get("/calibration/orientation/live")
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "DRIFT"
    assert body["roll_deg"] == pytest.approx(5.0, abs=0.01)


def test_run_calibration_with_promote_false_does_not_replace_current(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)

    first = client.post("/calibration/run").json()
    assert first["promoted_to_current"] is True

    second = client.post("/calibration/run", params={"promote": "false"}).json()
    assert second["promoted_to_current"] is False
    assert second["artifact_path"] != first["artifact_path"]

    current = client.get("/calibration/current").json()
    assert current["created_at"] != second.get("created_at")  # unaffected by the second run
    # Both runs still landed on disk -- promote=False only skips the current.json pointer.
    assert Path(first["artifact_path"]).exists()
    assert Path(second["artifact_path"]).exists()


def test_calibration_list_and_files_are_downloadable(monkeypatch: pytest.MonkeyPatch) -> None:
    # Deliberately not isolated_calibration_dir: /calibration/files is a StaticFiles mount bound
    # to a fixed directory at app import time (same pattern as /captures), so it serves whatever
    # NPEC_RIG_CALIBRATION_DIR conftest.py set at import -- a per-test env override wouldn't be
    # visible to it.
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)
    run = client.post("/calibration/run").json()

    listing = client.get("/calibration/list").json()
    entry = next(e for e in listing if e["url"] == f"/calibration/files/{Path(run['artifact_path']).name}")
    assert entry["frame_url"] == f"/calibration/files/frames/{Path(run['frame_path']).name}"

    artifact_response = client.get(entry["url"])
    assert artifact_response.status_code == 200
    assert artifact_response.json()["version"] == 2

    frame_response = client.get(entry["frame_url"])
    assert frame_response.status_code == 200
    assert frame_response.content[:2] == b"\xff\xd8"
