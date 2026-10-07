import asyncio
import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

import npec_rig.app as app_module
from npec_rig.app import _mjpeg_frames, _saved_calibration_path, app, focus_roi_stream, preview
from npec_rig.calibration import CalibrationArtifact, ScaleField
from npec_rig.calibration_store import calibration_root, save_calibration
from npec_rig.camera import (
    SIMULATED_AUTOFOCUS_POSITION,
    CameraBusyError,
    CameraManager,
    SyntheticBackend,
    array_to_jpeg,
)
from npec_rig.captures import captures_root
from npec_rig.tags import ASSUMED_CALIBRATION_TAG_SIZE_MM, ASSUMED_CORNER_TAG_SIZE_MM
from npec_rig.tripwire import CornerBaseline
from tests.helpers import rotate_detection, sheet_detections, square_detection, tray_layout_detections

pytestmark = pytest.mark.unit


class _FakeRequest:
    """Minimal stand-in for fastapi.Request for tests driving _mjpeg_frames directly -- a real
    Request's is_disconnected() needs a live ASGI receive channel, which these tests aren't
    exercising. Only the one method _mjpeg_frames actually calls."""

    def __init__(self, disconnected: bool = False) -> None:
        self._disconnected = disconnected

    async def is_disconnected(self) -> bool:
        return self._disconnected


@pytest.fixture(autouse=True)
def synthetic_camera() -> None:
    CameraManager.set_instance(CameraManager(SyntheticBackend()))


# Captured once, at collection time, before the autouse fixture below ever patches the module
# attribute -- the small number of dedicated gate tests restore this to exercise the real
# function instead of the "always ready" default.
_REAL_CALIBRATION_READINESS = app_module._calibration_readiness


@pytest.fixture(autouse=True)
def calibration_gate_open_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Almost every /calibration/run test in this file is about calibration's own mechanics
    (tag size defaults, promote, table dims, history...), not the focus-lock/corner-tag
    readiness gate, and most use only 2 corner tags (`_CORNER_TAGS`) since that's already
    enough for a corner baseline -- fewer than the gate's own 4-tag minimum. Default the gate
    open so none of them need a real lock or a 4-tag fixture; the dedicated gate tests below
    restore the real function to exercise it properly."""
    monkeypatch.setattr(
        app_module,
        "_calibration_readiness",
        lambda: {
            "focus_locked": True,
            "corner_tags_detected": 4,
            "corner_tags_required": 4,
            "ready": True,
        },
    )


@pytest.fixture
def isolated_calibration_dir(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("NPEC_RIG_CALIBRATION_DIR", str(tmp_path / "calibration"))


@pytest.fixture(autouse=True)
def reset_frame_detection_cache() -> None:
    # Module-level state (the rank-plot/best-worst-photo OOM fix's one-entry cache), keyed by
    # frame_stem -- collision across tests is astronomically unlikely (microsecond timestamps),
    # but a test that monkeypatches detect_tags differently between two calls to the same
    # artifact (see test_rank_plot_refused_with_too_few_tags_in_the_saved_frame) must not read a
    # stale cache entry left by another test.
    app_module._cached_frame_detections = None


def test_root_redirects_to_gallery() -> None:
    client = TestClient(app, follow_redirects=False)
    response = client.get("/")
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/gallery"


@pytest.mark.parametrize(
    "path", ["/setup", "/setup/focus", "/setup/calibration", "/setup/health-check", "/gallery"]
)
def test_page_loads(path: str) -> None:
    client = TestClient(app)
    response = client.get(path)
    assert response.status_code == 200
    assert "NPEC Camera Rig" in response.text


def test_calibration_history_diagnostics_page_loads() -> None:
    # One static file serves any stem -- the page looks itself up in /calibration/list
    # client-side, so this route never 404s on an unknown stem the way the JSON endpoints do.
    client = TestClient(app)
    response = client.get("/setup/calibration-history/20260101T000000000000")
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
    frames = _mjpeg_frames(_FakeRequest(), manager.preview_jpeg, fps_limit=1000.0, name="test")

    async def _first_chunk() -> bytes:
        try:
            return await anext(frames)
        finally:
            await frames.aclose()

    chunk = asyncio.run(_first_chunk())
    assert b"Content-Type: image/jpeg" in chunk
    assert b"\xff\xd8" in chunk


def test_mjpeg_frames_stops_immediately_on_disconnected_client() -> None:
    manager = CameraManager(SyntheticBackend())
    frames = _mjpeg_frames(
        _FakeRequest(disconnected=True), manager.preview_jpeg, fps_limit=1000.0, name="test"
    )

    async def _collect() -> list[bytes]:
        return [chunk async for chunk in frames]

    assert asyncio.run(_collect()) == []


def test_mjpeg_frames_skips_a_busy_frame_without_raising() -> None:
    # A CameraBusyError (the lock-timeout path -- see camera.py) must not kill the stream; it
    # should be treated like "no frame yet" and retried next tick.
    calls = {"n": 0}

    def flaky_jpeg_source() -> bytes:
        calls["n"] += 1
        if calls["n"] == 1:
            raise CameraBusyError("test")
        return b"\xff\xd8fake-jpeg-bytes"

    frames = _mjpeg_frames(_FakeRequest(), flaky_jpeg_source, fps_limit=1000.0, name="test")

    async def _first_chunk() -> bytes:
        try:
            return await anext(frames)
        finally:
            await frames.aclose()

    chunk = asyncio.run(_first_chunk())
    assert b"fake-jpeg-bytes" in chunk
    assert calls["n"] == 2


def test_preview_route_returns_mjpeg_streaming_response() -> None:
    response = preview(_FakeRequest())
    assert isinstance(response, StreamingResponse)
    assert "multipart/x-mixed-replace" in response.media_type


def test_focus_roi_stream_route_returns_mjpeg_streaming_response() -> None:
    response = focus_roi_stream(_FakeRequest())
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


class _StuckLensBackend(SyntheticBackend):
    """Accepts every lens write and keeps reporting the same position."""

    def get_lens_position(self) -> float:
        return 6.27


def test_a_lens_that_does_not_follow_a_move_or_a_lock_returns_lens_not_responding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import npec_rig.camera as camera_module

    monkeypatch.setattr(camera_module, "LENS_SETTLE_TIMEOUT_S", 0.0)
    CameraManager.set_instance(CameraManager(_StuckLensBackend()))
    client = TestClient(app)

    response = client.post("/controls/lens-position", json={"value": 4.77})
    assert response.status_code == 503
    assert response.json()["detail"].startswith("Lens not responding: press Reset camera")

    response = client.post("/focus/lock")
    assert response.status_code == 503
    assert response.json()["detail"].startswith("Lens not responding: press Reset camera")


def test_a_locked_focus_refuses_lens_moves_and_autofocus_with_a_clear_message() -> None:
    client = TestClient(app)
    client.post("/controls/lens-position", json={"value": 6.3})
    client.post("/focus/lock")

    move = client.post("/controls/lens-position", json={"value": 4.77})
    autofocus = client.post("/focus/autofocus")
    for response in (move, autofocus):
        assert response.status_code == 409
        assert response.json()["detail"] == "Focus is locked: press Unlock focus to change it"
    assert client.get("/controls/lens-position").json() == {"value": 6.3}


def test_reset_camera_keeps_the_lock_and_says_where_the_lens_was_driven() -> None:
    client = TestClient(app)
    client.post("/controls/lens-position", json={"value": 6.3})
    client.post("/focus/lock")

    response = client.post("/camera/reset")
    assert response.status_code == 200
    assert response.json() == {"locked": True, "lens_position": 6.3, "lens_position_set": 6.3}


def test_a_reset_that_does_not_help_says_restart_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    import npec_rig.camera as camera_module

    monkeypatch.setattr(camera_module, "LENS_SETTLE_TIMEOUT_S", 0.0)
    manager = CameraManager(_StuckLensBackend())
    manager._commanded_lens_position = 4.77
    CameraManager.set_instance(manager)

    response = TestClient(app).post("/camera/reset")
    assert response.status_code == 503
    assert response.json()["detail"].startswith(
        "The camera reset did not help, the lens still does not follow: restart the app"
    )


def test_autofocus_endpoint() -> None:
    client = TestClient(app)
    response = client.post("/focus/autofocus")
    assert response.status_code == 200
    assert response.json() == {
        "success": True, "lens_position": SIMULATED_AUTOFOCUS_POSITION, "timed_out": None
    }


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
    # AnalogueGain only takes effect while AE is off — see Picamera2Backend.set_control's guard.
    client.post("/controls/AeEnable", json={"value": False})
    response = client.post("/controls/AnalogueGain", json={"value": 4.0})
    assert response.status_code == 200
    assert response.json()["AnalogueGain"] == 4.0

    response = client.get("/controls")
    assert response.json()["values"]["AnalogueGain"] == 4.0


def test_set_control_ignores_manual_exposure_while_ae_is_on() -> None:
    # A stale browser tab (or any client) posting a manual value while AE is on must not be
    # able to re-arm picamera2's manual-exposure latch behind AE's back — found by /code-review
    # as a gap in the AE-stuck-image fix (m2-auto-exposure-fix): the original fix only disabled
    # the sliders client-side, with nothing enforcing it server-side.
    client = TestClient(app)
    client.post("/controls/AeEnable", json={"value": True})

    response = client.post("/controls/AnalogueGain", json={"value": 4.0})

    assert response.status_code == 200
    assert response.json()["AnalogueGain"] != 4.0


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
    assert body["frame_url"] is not None
    assert body["heatmap_url"] is not None
    assert body["area_shape_heatmap_url"] is not None
    assert (calibration_root() / "heatmaps" / Path(body["area_shape_heatmap_url"]).name).exists()
    assert body["accuracy_shape_heatmap_url"] is not None
    assert (calibration_root() / "heatmaps" / Path(body["accuracy_shape_heatmap_url"]).name).exists()

    current = client.get("/calibration/current").json()
    assert current["exists"] is True
    assert current["corner_baseline_tags"] == [450, 451]
    assert current["residual_std_pct"] == body["residual_std_pct"]
    assert current["frame_url"] == body["frame_url"]
    assert current["heatmap_url"] == body["heatmap_url"]
    assert current["area_shape_heatmap_url"] == body["area_shape_heatmap_url"]
    assert current["accuracy_shape_heatmap_url"] == body["accuracy_shape_heatmap_url"]
    assert current["has_uncertainty_field"] is True

    listing = client.get("/calibration/list").json()
    assert listing[0]["area_shape_heatmap_url"] == body["area_shape_heatmap_url"]
    assert listing[0]["accuracy_shape_heatmap_url"] == body["accuracy_shape_heatmap_url"]
    assert body["table_view_url"] is None  # only 2 of 4 corner tags -- no table frame buildable
    assert body["table_view_shape_url"] is None


_FOUR_CORNER_TAGS = [
    square_detection(450, 30, 30, side_px=60.0),
    square_detection(451, 1500, 30, side_px=60.0),
    square_detection(452, 1500, 1100, side_px=60.0),
    square_detection(455, 30, 1100, side_px=60.0),
]


def test_run_calibration_builds_table_view_with_all_four_corner_tags(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(
        app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _FOUR_CORNER_TAGS
    )

    client = TestClient(app)
    response = client.post(
        "/calibration/run", params={"table_width_mm": 1000.0, "table_length_mm": 800.0}
    )
    assert response.status_code == 200
    body = response.json()

    assert body["corner_baseline_tags"] == [450, 451, 452, 455]
    assert body["table_width_mm"] == 1000.0
    assert body["table_length_mm"] == 800.0
    assert body["table_view_to_scale"] is True
    assert body["table_view_url"] is not None
    assert body["table_view_shape_url"] is not None
    assert (calibration_root() / "heatmaps" / Path(body["table_view_url"]).name).exists()
    assert (calibration_root() / "heatmaps" / Path(body["table_view_shape_url"]).name).exists()

    current = client.get("/calibration/current").json()
    assert current["table_view_url"] == body["table_view_url"]
    assert current["table_view_shape_url"] == body["table_view_shape_url"]

    listing = client.get("/calibration/list").json()
    assert listing[0]["table_view_url"] == body["table_view_url"]
    assert listing[0]["table_view_shape_url"] == body["table_view_shape_url"]


# --- Calibration readiness gate: focus locked, all 4 corner tags detected ---
# These tests restore the real `_calibration_readiness` (the other tests in this file default it
# open, see `calibration_gate_open_by_default`) to exercise the actual gate logic against real
# lock state and real `detect_tags` results.


def test_calibration_readiness_reports_not_ready_with_no_lock_and_no_corner_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_module, "_calibration_readiness", _REAL_CALIBRATION_READINESS)
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: [])

    client = TestClient(app)
    body = client.get("/calibration/readiness").json()
    assert body == {
        "focus_locked": False,
        "corner_tags_detected": 0,
        "corner_tags_required": 4,
        "ready": False,
    }


def test_calibration_readiness_reports_ready_once_locked_with_four_corner_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_module, "_calibration_readiness", _REAL_CALIBRATION_READINESS)
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _FOUR_CORNER_TAGS)

    client = TestClient(app)
    client.post("/controls/lens-position", json={"value": 6.3})
    client.post("/focus/lock")

    body = client.get("/calibration/readiness").json()
    assert body == {
        "focus_locked": True,
        "corner_tags_detected": 4,
        "corner_tags_required": 4,
        "ready": True,
    }


def test_run_calibration_refuses_without_a_lock_and_can_be_overridden(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "_calibration_readiness", _REAL_CALIBRATION_READINESS)
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _FOUR_CORNER_TAGS)

    client = TestClient(app)
    refused = client.post("/calibration/run").json()
    assert refused["gate_failed"] is True
    assert refused["focus_locked"] is False
    assert "Focus is not confirmed" in refused["error"]
    assert "artifact_path" not in refused  # no capture happened

    overridden = client.post("/calibration/run", params={"override_focus_gate": "true"}).json()
    assert "gate_failed" not in overridden
    assert "error" not in overridden


def test_run_calibration_refuses_with_too_few_corner_tags_and_can_be_overridden(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "_calibration_readiness", _REAL_CALIBRATION_READINESS)
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)

    client = TestClient(app)
    client.post("/controls/lens-position", json={"value": 6.3})
    client.post("/focus/lock")

    refused = client.post("/calibration/run").json()
    assert refused["gate_failed"] is True
    assert refused["corner_tags_detected"] == len(_CORNER_TAGS)
    assert "2 of 4 corner tags" in refused["error"]
    assert "artifact_path" not in refused

    overridden = client.post("/calibration/run", params={"override_focus_gate": "true"}).json()
    assert "gate_failed" not in overridden
    assert "error" not in overridden


def test_run_calibration_echoes_corner_tag_size_and_default_flag(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(
        app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _FOUR_CORNER_TAGS
    )
    client = TestClient(app)

    default_run = client.post("/calibration/run").json()
    assert default_run["corner_tag_size_mm"] == ASSUMED_CORNER_TAG_SIZE_MM
    assert default_run["corner_tag_size_mm_is_default"] is True

    measured_run = client.post(
        "/calibration/run", params={"corner_tag_size_mm": 49.87}
    ).json()
    assert measured_run["corner_tag_size_mm"] == 49.87
    assert measured_run["corner_tag_size_mm_is_default"] is False


def test_run_calibration_remembers_table_dims_across_runs(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    # Aaron, 2026-09-25: "the calibration doesn't remember the settings from previous runs so I
    # always get the NOT TO SCALE thing." A run that omits all three must reuse whatever was
    # last actually given, not fall back to NOT-TO-SCALE/the placeholder default.
    monkeypatch.setattr(
        app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _FOUR_CORNER_TAGS
    )
    client = TestClient(app)

    first = client.post(
        "/calibration/run",
        params={"table_width_mm": 1000.0, "table_length_mm": 800.0, "corner_tag_size_mm": 49.87},
    ).json()
    assert first["table_view_to_scale"] is True

    current = client.get("/calibration/current").json()
    assert current["table_width_mm"] == 1000.0
    assert current["table_length_mm"] == 800.0
    assert current["corner_tag_size_mm"] == 49.87

    second = client.post("/calibration/run").json()
    assert second["table_width_mm"] == 1000.0
    assert second["table_length_mm"] == 800.0
    assert second["corner_tag_size_mm"] == 49.87
    assert second["corner_tag_size_mm_is_default"] is False
    assert second["table_view_to_scale"] is True


def test_save_table_dims_persists_without_a_camera_capture(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    # Aaron, 2026-09-25: "There's no way to enter the table width and length in mm. There's no
    # submit button." Before this endpoint, the only way to persist these was as a side effect
    # of /calibration/run, which needs real tags in frame to succeed at all.
    def _fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("saving table dims must not touch the camera")

    monkeypatch.setattr(app_module.CameraManager, "instance", staticmethod(_fail_if_called))

    client = TestClient(app)
    response = client.post(
        "/calibration/table-dims",
        params={"table_width_mm": 1496.0, "table_length_mm": 1152.0, "corner_tag_size_mm": 50.0},
    )
    assert response.status_code == 200
    assert response.json() == {
        "table_width_mm": 1496.0,
        "table_length_mm": 1152.0,
        "corner_tag_size_mm": 50.0,
    }

    current = client.get("/calibration/current").json()
    assert current["table_width_mm"] == 1496.0
    assert current["table_length_mm"] == 1152.0
    assert current["corner_tag_size_mm"] == 50.0


def test_save_table_dims_leaves_unset_fields_alone(isolated_calibration_dir: None) -> None:
    client = TestClient(app)
    client.post("/calibration/table-dims", params={"table_width_mm": 1496.0})
    response = client.post("/calibration/table-dims", params={"corner_tag_size_mm": 50.0})
    assert response.json() == {
        "table_width_mm": 1496.0,
        "table_length_mm": None,
        "corner_tag_size_mm": 50.0,
    }


def test_save_table_dims_rejects_non_positive_values(isolated_calibration_dir: None) -> None:
    # Found by code review 2026-09-26: 0 used to pass straight through
    # _outer_edge_span_to_centre_distance_mm as "no tag-width correction needed" instead of
    # "invalid", and would have silently poisoned every future run's persisted default.
    client = TestClient(app)
    client.post(
        "/calibration/table-dims",
        params={"table_width_mm": 1496.0, "table_length_mm": 1152.0, "corner_tag_size_mm": 50.0},
    )
    response = client.post(
        "/calibration/table-dims",
        params={"table_width_mm": 0.0, "table_length_mm": -5.0, "corner_tag_size_mm": 0.0},
    )
    assert response.json() == {
        "table_width_mm": 1496.0,
        "table_length_mm": 1152.0,
        "corner_tag_size_mm": 50.0,
    }


def test_run_calibration_does_not_persist_table_dims_when_not_promoted(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    # Aaron's own "never overwrite with a guess" rule applied to promote=False (found by code
    # review 2026-09-26): a comparison run's own test values must not become the sticky default
    # for every real run after it, the same way promote=False already keeps current.json alone.
    monkeypatch.setattr(
        app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _FOUR_CORNER_TAGS
    )
    client = TestClient(app)

    client.post(
        "/calibration/run",
        params={"table_width_mm": 1496.0, "table_length_mm": 1152.0, "corner_tag_size_mm": 50.0},
    )
    comparison = client.post(
        "/calibration/run",
        params={
            "promote": False,
            "table_width_mm": 40.0,
            "table_length_mm": 30.0,
            "corner_tag_size_mm": 5.0,
        },
    ).json()
    # The comparison run's own table view still uses its own entered values...
    assert comparison["table_width_mm"] == 40.0
    assert comparison["table_length_mm"] == 30.0
    assert comparison["corner_tag_size_mm"] == 5.0

    # ...but the persisted defaults for the *next* run are untouched.
    current = client.get("/calibration/current").json()
    assert current["table_width_mm"] == 1496.0
    assert current["table_length_mm"] == 1152.0
    assert current["corner_tag_size_mm"] == 50.0


def test_run_calibration_gate_refusal_does_not_persist_table_dims(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    # Found by /code-review 2026-09-28: _resolve_table_dims used to persist before the
    # readiness gate check, so a refused run (no capture at all) still overwrote the sticky
    # table-dims defaults with whatever was typed in for that attempt.
    from npec_rig.settings import load_settings

    monkeypatch.setattr(
        app_module,
        "_calibration_readiness",
        lambda: {
            "focus_locked": False,
            "corner_tags_detected": 0,
            "corner_tags_required": 4,
            "ready": False,
        },
    )
    client = TestClient(app)

    refused = client.post(
        "/calibration/run",
        params={"table_width_mm": 999.0, "table_length_mm": 888.0, "corner_tag_size_mm": 77.0},
    ).json()
    assert refused["gate_failed"] is True

    persisted = load_settings()
    assert "table_width_mm" not in persisted
    assert "table_length_mm" not in persisted
    assert "corner_tag_size_mm" not in persisted


def test_run_calibration_converts_outer_edge_span_to_table_view(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    # table_width_mm/table_length_mm are the operator's outer-edge-to-outer-edge tape measurement
    # (see app_module._outer_edge_span_to_centre_distance_mm) -- too small relative to the corner
    # tag size (e.g. an inner-edge measurement typed in by mistake) must fall back to NOT-TO-SCALE
    # rather than rendering a nonsense aspect ratio, without failing the whole run.
    monkeypatch.setattr(
        app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _FOUR_CORNER_TAGS
    )
    client = TestClient(app)
    response = client.post(
        "/calibration/run",
        params={"table_width_mm": 40.0, "table_length_mm": 800.0, "corner_tag_size_mm": 50.0},
    )
    body = response.json()
    assert body["table_width_mm"] == 40.0  # still echoed as entered, not silently corrected
    assert body["table_view_to_scale"] is False  # the UI must say so, not just render a square
    assert body["table_view_url"] is not None  # still built -- just NOT-TO-SCALE for this run


def test_outer_edge_span_to_centre_distance_subtracts_one_tag_width() -> None:
    assert app_module._outer_edge_span_to_centre_distance_mm(1000.0, 50.0) == pytest.approx(950.0)


def test_outer_edge_span_to_centre_distance_passes_through_none() -> None:
    assert app_module._outer_edge_span_to_centre_distance_mm(None, 50.0) is None


def test_outer_edge_span_to_centre_distance_guards_against_undersized_span() -> None:
    # Smaller than (or equal to) the tag size itself -- almost certainly a data-entry mistake
    # (e.g. an inner-edge measurement) -- falls back to None (NOT-TO-SCALE) rather than a
    # non-positive or zero "distance".
    assert app_module._outer_edge_span_to_centre_distance_mm(50.0, 50.0) is None
    assert app_module._outer_edge_span_to_centre_distance_mm(30.0, 50.0) is None


def test_current_uncertainty_without_a_calibration_is_refused(isolated_calibration_dir: None) -> None:
    client = TestClient(app)
    response = client.get("/calibration/current/uncertainty", params={"x": 100, "y": 100})
    assert response.status_code == 409


def test_current_uncertainty_reports_a_real_value(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")

    response = client.get(
        "/calibration/current/uncertainty", params={"x": _CALIBRATION_TAGS[0].centre[0], "y": _CALIBRATION_TAGS[0].centre[1]}
    )
    assert response.status_code == 200
    assert response.json()["uncertainty_pct"] == pytest.approx(0.0, abs=1e-6)


def test_honesty_plot_without_a_calibration_is_refused(isolated_calibration_dir: None) -> None:
    client = TestClient(app)
    response = client.post("/calibration/honesty-plot", json=[{"x": 1, "y": 1, "actual_error_pct": 1.0}])
    assert response.status_code == 409


def test_honesty_plot_rejects_an_empty_point_list(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")

    response = client.post("/calibration/honesty-plot", json=[])
    assert response.status_code == 422


def test_honesty_plot_returns_a_jpeg(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")

    response = client.post(
        "/calibration/honesty-plot",
        json=[
            {"x": _CALIBRATION_TAGS[0].centre[0], "y": _CALIBRATION_TAGS[0].centre[1], "actual_error_pct": 1.5},
            {"x": _CALIBRATION_TAGS[1].centre[0], "y": _CALIBRATION_TAGS[1].centre[1], "actual_error_pct": 3.0},
        ],
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content[:2] == b"\xff\xd8"


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
    assert response.json() == {
        "exists": False,
        "table_width_mm": None,
        "table_length_mm": None,
        "corner_tag_size_mm": None,
    }


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


def test_run_calibration_has_no_delta_on_the_first_run(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)

    result = client.post("/calibration/run").json()
    assert result["previous_calibration_comparison"] is None


def test_run_calibration_delta_compares_against_the_previous_active_calibration(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)

    first = client.post("/calibration/run").json()
    assert first["previous_calibration_comparison"] is None

    second = client.post("/calibration/run", params={"calibration_tag_size_mm": 30.02}).json()
    cmp = second["previous_calibration_comparison"]
    assert cmp is not None
    assert cmp["previous_created_at"]  # a real ISO timestamp string, not asserting its exact value
    assert cmp["residual_std_pct"]["previous"] == first["residual_std_pct"]
    assert cmp["residual_std_pct"]["current"] == second["residual_std_pct"]
    assert cmp["residual_std_pct"]["delta"] == pytest.approx(
        second["residual_std_pct"] - first["residual_std_pct"]
    )
    assert cmp["corner_tags_detected"]["previous"] == len(first["corner_baseline_tags"])
    assert cmp["corner_tags_detected"]["current"] == len(second["corner_baseline_tags"])
    assert cmp["calibration_tag_size_mm"]["previous"] == first["calibration_tag_size_mm"]
    assert cmp["calibration_tag_size_mm"]["current"] == 30.02
    assert cmp["calibration_tag_size_mm"]["delta"] == pytest.approx(
        30.02 - first["calibration_tag_size_mm"]
    )
    assert cmp["lens_position"]["previous"] == first["lens_position"]
    assert cmp["lens_position"]["current"] == second["lens_position"]


def test_run_calibration_delta_present_even_when_not_promoted(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    # promote=False is explicitly a comparison run -- it should still see a delta against
    # whatever the live baseline currently is, that's the whole point of comparing.
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)

    client.post("/calibration/run")
    second = client.post("/calibration/run", params={"promote": "false"}).json()
    assert second["previous_calibration_comparison"] is not None


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
    assert entry["heatmap_url"] == run["heatmap_url"]

    artifact_response = client.get(entry["url"])
    assert artifact_response.status_code == 200
    assert artifact_response.json()["version"] == 3

    frame_response = client.get(entry["frame_url"])
    assert frame_response.status_code == 200
    assert frame_response.content[:2] == b"\xff\xd8"

    heatmap_response = client.get(entry["heatmap_url"])
    assert heatmap_response.status_code == 200
    assert heatmap_response.content[:2] == b"\xff\xd8"


# --- Calibration-history browser: per-entry stats, promote, delete ---


def test_calibration_list_includes_per_entry_stats_and_marks_the_active_one(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)

    first = client.post("/calibration/run").json()
    second = client.post("/calibration/run", params={"promote": "false"}).json()

    first_stem = Path(first["artifact_path"]).stem
    second_stem = Path(second["artifact_path"]).stem

    listing = client.get("/calibration/list").json()
    by_stem = {e["stem"]: e for e in listing}

    assert by_stem[first_stem]["is_current"] is True
    assert by_stem[first_stem]["residual_std_pct"] == first["residual_std_pct"]
    assert by_stem[first_stem]["calibration_tag_size_mm"] == first["calibration_tag_size_mm"]
    assert by_stem[first_stem]["corner_tag_count"] == len(first["corner_baseline_tags"])

    assert by_stem[second_stem]["is_current"] is False
    assert by_stem[second_stem]["residual_std_pct"] == second["residual_std_pct"]


def test_promote_calibration_makes_it_the_active_one(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)

    old = client.post("/calibration/run").json()
    client.post("/calibration/run")  # a second, newer run promotes over it

    old_stem = Path(old["artifact_path"]).stem
    old_entry = next(
        e for e in client.get("/calibration/list").json() if e["stem"] == old_stem
    )
    assert old_entry["is_current"] is False

    response = client.post(f"/calibration/{old_stem}/promote")
    assert response.status_code == 200
    assert response.json()["promoted"] == old_stem

    current_after = client.get("/calibration/current").json()
    assert current_after["created_at"] == old_entry["created_at"]

    listing_after = client.get("/calibration/list").json()
    assert next(e for e in listing_after if e["stem"] == old_stem)["is_current"] is True


def test_promote_unknown_stem_returns_404(isolated_calibration_dir: None) -> None:
    client = TestClient(app)
    response = client.post("/calibration/does-not-exist/promote")
    assert response.status_code == 404


def test_delete_calibration_removes_its_files(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)

    old = client.post("/calibration/run").json()
    client.post("/calibration/run")  # promotes a second run so `old` is no longer active

    old_stem = Path(old["artifact_path"]).stem
    assert Path(old["artifact_path"]).exists()
    assert Path(old["frame_path"]).exists()

    response = client.delete(f"/calibration/{old_stem}")
    assert response.status_code == 200
    assert response.json()["deleted"] == old_stem

    assert not Path(old["artifact_path"]).exists()
    assert not Path(old["frame_path"]).exists()
    assert not (calibration_root() / "heatmaps" / f"{old_stem}.jpg").exists()

    listing = client.get("/calibration/list").json()
    assert all(e["stem"] != old_stem for e in listing)


def test_delete_refuses_to_remove_the_active_calibration(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)
    run = client.post("/calibration/run").json()
    stem = Path(run["artifact_path"]).stem

    response = client.delete(f"/calibration/{stem}")
    assert response.status_code == 409
    assert Path(run["artifact_path"]).exists()


def test_delete_unknown_stem_returns_404(isolated_calibration_dir: None) -> None:
    client = TestClient(app)
    response = client.delete("/calibration/does-not-exist")
    assert response.status_code == 404


def test_saved_calibration_path_rejects_traversal_and_the_current_pointer(
    isolated_calibration_dir: None,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        _saved_calibration_path("../../../etc/passwd")
    assert exc_info.value.status_code == 404

    with pytest.raises(HTTPException) as exc_info:
        _saved_calibration_path("current")
    assert exc_info.value.status_code == 404


def _write_corrupt_calibration(stem: str) -> None:
    """A file that parses as JSON but fails `calibration_artifact_from_dict` with a TypeError,
    not the ValueError/KeyError the rest of this file's corrupt-artifact tests use -- exercises
    the same code path a genuinely malformed-but-version-matching artifact would hit."""
    root = calibration_root()
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{stem}.json").write_text(
        json.dumps({"version": 3, "created_at": "2026-01-01T00:00:00+00:00", "scale_field": None})
    )


def test_calibration_list_survives_a_structurally_malformed_entry(
    isolated_calibration_dir: None,
) -> None:
    _write_corrupt_calibration("20260101T000000000000")
    listing = TestClient(app).get("/calibration/list").json()
    assert len(listing) == 1
    assert listing[0]["stem"] == "20260101T000000000000"
    assert listing[0]["residual_std_pct"] is None
    assert listing[0]["is_current"] is False


def test_promote_unreadable_calibration_returns_422(isolated_calibration_dir: None) -> None:
    _write_corrupt_calibration("20260101T000000000000")
    client = TestClient(app)
    response = client.post("/calibration/20260101T000000000000/promote")
    assert response.status_code == 422


def test_delete_unreadable_calibration_succeeds_when_no_current_exists(
    isolated_calibration_dir: None,
) -> None:
    _write_corrupt_calibration("20260101T000000000000")
    client = TestClient(app)
    response = client.delete("/calibration/20260101T000000000000")
    assert response.status_code == 200
    assert not (calibration_root() / "20260101T000000000000.json").exists()


def test_delete_unreadable_calibration_is_refused_when_current_exists(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")  # a real, valid, promoted calibration

    _write_corrupt_calibration("20260101T000000000000")
    response = client.delete("/calibration/20260101T000000000000")
    assert response.status_code == 409
    assert (calibration_root() / "20260101T000000000000.json").exists()


def test_delete_refuses_everything_when_current_json_itself_is_corrupt(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)
    run = client.post("/calibration/run").json()
    stem = Path(run["artifact_path"]).stem

    (calibration_root() / "current.json").write_text(
        json.dumps({"version": 3, "created_at": "2026-01-01T00:00:00+00:00", "scale_field": None})
    )

    response = client.delete(f"/calibration/{stem}")
    assert response.status_code == 409
    assert Path(run["artifact_path"]).exists()


# --- Best-vs-worst-tag rank plot ---


def test_rank_plot_without_a_calibration_is_refused(isolated_calibration_dir: None) -> None:
    client = TestClient(app)
    response = client.get("/calibration/current/rank-plot")
    assert response.status_code == 409


def test_rank_plot_rejects_an_unknown_metric(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")

    response = client.get("/calibration/current/rank-plot", params={"metric": "bogus"})
    assert response.status_code == 422


def test_rank_plot_returns_a_jpeg_for_scale_residual(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")

    response = client.get("/calibration/current/rank-plot", params={"metric": "scale_residual"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content[:2] == b"\xff\xd8"


def test_rank_plot_returns_a_jpeg_for_shape_distortion(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")

    response = client.get("/calibration/current/rank-plot", params={"metric": "shape_distortion"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content[:2] == b"\xff\xd8"


def test_rank_plot_refused_with_too_few_tags_in_the_saved_frame(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    # The calibration that saved the frame had enough tags to build a field; re-detecting the
    # same saved frame for the rank plot finding fewer than 2 is its own, separate failure mode.
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")

    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS[:1] + _CORNER_TAGS)
    response = client.get("/calibration/current/rank-plot")
    assert response.status_code == 409


# --- Best/worst photo overlay ---


def test_best_worst_photo_without_a_calibration_is_refused(isolated_calibration_dir: None) -> None:
    client = TestClient(app)
    response = client.get("/calibration/current/best-worst-photo")
    assert response.status_code == 409


def test_best_worst_photo_returns_a_jpeg(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")

    for metric in ("scale_residual", "shape_distortion"):
        response = client.get("/calibration/current/best-worst-photo", params={"metric": metric})
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert response.content[:2] == b"\xff\xd8"


def test_best_worst_photo_rejects_an_unknown_metric(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")

    response = client.get("/calibration/current/best-worst-photo", params={"metric": "bogus"})
    assert response.status_code == 422


def test_rank_plot_and_best_worst_photo_share_one_detection_pass(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    # The OOM fix: re-detecting the full saved frame four times (2 metrics x 2 views) per page
    # load is what got the picamera2 worker killed (dmesg-confirmed, 2026-09-22). Four requests
    # against the same live calibration must call detect_tags at most once, not four times.
    call_count = 0

    def counting_detect_tags(frame):
        nonlocal call_count
        call_count += 1
        return _CALIBRATION_TAGS + _CORNER_TAGS

    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")

    monkeypatch.setattr(app_module, "detect_tags", counting_detect_tags)
    for metric in ("scale_residual", "shape_distortion"):
        assert client.get("/calibration/current/rank-plot", params={"metric": metric}).status_code == 200
        assert client.get(
            "/calibration/current/best-worst-photo", params={"metric": metric}
        ).status_code == 200
        assert client.get("/calibration/current/radial-plot", params={"metric": metric}).status_code == 200

    assert call_count == 1


# --- Radial residual plot ---


def test_radial_plot_without_a_calibration_is_refused(isolated_calibration_dir: None) -> None:
    client = TestClient(app)
    response = client.get("/calibration/current/radial-plot")
    assert response.status_code == 409


def test_radial_plot_returns_a_jpeg(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")

    for metric in ("scale_residual", "shape_distortion"):
        response = client.get("/calibration/current/radial-plot", params={"metric": metric})
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert response.content[:2] == b"\xff\xd8"


def test_radial_plot_rejects_an_unknown_metric(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")

    response = client.get("/calibration/current/radial-plot", params={"metric": "bogus"})
    assert response.status_code == 422


def test_radial_plot_refused_with_too_few_tags_in_the_saved_frame(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")

    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS[:1] + _CORNER_TAGS)
    response = client.get("/calibration/current/radial-plot")
    assert response.status_code == 409


# --- Certainty dome plot ---


def test_certainty_dome_plot_without_a_calibration_is_refused(isolated_calibration_dir: None) -> None:
    client = TestClient(app)
    response = client.get("/calibration/current/certainty-dome-plot")
    assert response.status_code == 409


def test_certainty_dome_plot_returns_a_jpeg(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")

    response = client.get("/calibration/current/certainty-dome-plot")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content[:2] == b"\xff\xd8"


# --- Stem-scoped diagnostics (calibration-history drill-down) ---


@pytest.mark.parametrize(
    "path",
    ["rank-plot", "best-worst-photo", "radial-plot", "certainty-dome-plot"],
)
def test_stem_diagnostics_unknown_stem_returns_404(path: str, isolated_calibration_dir: None) -> None:
    client = TestClient(app)
    response = client.get(f"/calibration/does-not-exist/{path}")
    assert response.status_code == 404


@pytest.mark.parametrize(
    "path",
    ["rank-plot", "best-worst-photo", "radial-plot", "certainty-dome-plot"],
)
def test_stem_diagnostics_unreadable_calibration_returns_422(
    path: str, isolated_calibration_dir: None
) -> None:
    _write_corrupt_calibration("20260101T000000000000")
    client = TestClient(app)
    response = client.get(f"/calibration/20260101T000000000000/{path}")
    assert response.status_code == 422


def test_stem_diagnostics_serve_an_old_run_not_whatever_is_current(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    # The whole point of the drill-down: an old, no-longer-active stem must still be viewable,
    # and must reflect *its own* saved frame, not whatever `current.json` now points at.
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)

    old = client.post("/calibration/run").json()
    client.post("/calibration/run")  # a second, newer run promotes over it
    old_stem = Path(old["artifact_path"]).stem

    for path in ("rank-plot", "best-worst-photo", "radial-plot", "certainty-dome-plot"):
        response = client.get(f"/calibration/{old_stem}/{path}")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert response.content[:2] == b"\xff\xd8"


def test_stem_diagnostics_actually_load_the_requested_stems_own_frame(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    # A weaker version of this test (same monkeyed detect_tags for both runs) would still pass
    # even if the stem route silently read load_current_calibration() instead of the requested
    # stem -- this spies on the actual frame load to catch exactly that regression.
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)

    old = client.post("/calibration/run").json()
    current = client.post("/calibration/run").json()
    old_stem = Path(old["artifact_path"]).stem
    current_stem = Path(current["artifact_path"]).stem
    assert old_stem != current_stem

    loaded_stems = []
    real_load_frame = app_module.load_calibration_frame
    monkeypatch.setattr(
        app_module,
        "load_calibration_frame",
        lambda frame_stem: (loaded_stems.append(frame_stem), real_load_frame(frame_stem))[1],
    )

    response = client.get(f"/calibration/{old_stem}/rank-plot")
    assert response.status_code == 200
    assert loaded_stems == [old_stem]


# --- Certainty map ---


def _write_capture(ref: str) -> None:
    """A capture JPEG on disk at `ref` ("YYYY-MM-DD/HHMMSS_ffffff"); its content is irrelevant
    because the tests monkeypatch `detect_tags`."""
    path = captures_root() / f"{ref}.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(array_to_jpeg(np.zeros((120, 160, 3), dtype=np.uint8)))


def test_certainty_map_without_a_calibration_is_refused(isolated_calibration_dir: None) -> None:
    response = TestClient(app).get(
        "/calibration/current/certainty-map", params={"captures": "2026-09-29/143629_456239"}
    )
    assert response.status_code == 409


def test_certainty_map_needs_at_least_one_capture(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: tray_layout_detections() + _CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")
    assert client.get("/calibration/current/certainty-map").status_code == 422


@pytest.mark.parametrize("ref", ["../../etc/passwd", "2026-09-29/143629", "143629_456239"])
def test_certainty_map_rejects_anything_but_a_capture_reference(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None, ref: str
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: tray_layout_detections() + _CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")
    response = client.get("/calibration/current/certainty-map", params={"captures": ref})
    assert response.status_code == 422


def test_certainty_map_missing_capture_is_not_found(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: tray_layout_detections() + _CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")
    response = client.get(
        "/calibration/current/certainty-map", params={"captures": "2000-01-01/000000_000000"}
    )
    assert response.status_code == 404


def test_certainty_map_returns_a_jpeg_for_current_and_by_stem(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: tray_layout_detections() + _CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")
    stem = client.get("/calibration/list").json()[0]["stem"]
    refs = ["2026-09-29/143629_456239", "2026-09-29/143756_789335"]
    for ref in refs:
        _write_capture(ref)

    for url in ("/calibration/current/certainty-map", f"/calibration/{stem}/certainty-map"):
        response = client.get(url, params={"captures": refs})
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert response.content[:2] == b"\xff\xd8"


def test_certainty_map_refuses_a_calibration_without_12_tray_sheets(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: _CALIBRATION_TAGS + _CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")
    _write_capture("2026-09-29/143629_456239")
    response = client.get(
        "/calibration/current/certainty-map", params={"captures": "2026-09-29/143629_456239"}
    )
    assert response.status_code == 409
    assert "expected 12" in response.json()["detail"]


def test_certainty_map_caps_the_number_of_captures(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: tray_layout_detections() + _CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")
    refs = [f"2026-09-29/1436{i:02d}_000000" for i in range(13)]
    response = client.get("/calibration/current/certainty-map", params={"captures": refs})
    assert response.status_code == 422


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
            tags[k * 30 : (k + 1) * 30] = sheet_detections(300, x0, y0, side_px=120.0 * 0.96)
        return tags[30 * scene["drop_sheets"] :] + _CORNER_TAGS

    monkeypatch.setattr(app_module, "detect_tags", detect)
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

    drawers = {name: getattr(app_module, name) for name in ("render_problem_frame", "render_certainty_map")}
    for name in drawers:
        monkeypatch.setattr(app_module, name, must_not_run)
    assert [client.get(url).content for url in urls] == [r.content for r in first]  # from disk

    # A restart: derived images gone. Tags come from the analysis store. (Only the two drawers are
    # restored: monkeypatch.undo() would also drop the per-test DB and folders.)
    for name, drawer in drawers.items():
        monkeypatch.setattr(app_module, name, drawer)
    monkeypatch.setattr(app_module, "detect_tags", must_not_run)
    for path in app_module.images.derived_root().rglob("*.bin"):
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
    monkeypatch.setattr(app_module, "_detect_tags_cached", lambda stem: pytest.fail("decoded again"))
    second = client.post("/validation/sessions")
    assert second.status_code == 200
    assert second.json()["results"] == [
        {**r, "n": 0, "p95_abs_pct": None, "median_pct": None} for r in first["results"]
    ]
    stem = first["calibration_stem"]
    client.post("/calibration/run")  # a newer calibration, so the first can be deleted
    assert client.delete(f"/calibration/{stem}").status_code == 200
    assert app_module.validation_store.load_slot_layout(stem) is None


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

    # A new session replaces the old one's status until it completes.
    newer = client.post("/validation/sessions").json()
    status = client.get("/validation/status").json()
    assert (status["state"], status["session_id"]) == ("not_validated", newer["id"])


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
