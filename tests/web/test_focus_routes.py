import asyncio

import pytest
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from npec_rig.app import app
from npec_rig.camera import (
    CameraBusyError,
    CameraManager,
    SIMULATED_AUTOFOCUS_POSITION,
    SyntheticBackend,
)
from npec_rig.routes.focus import _mjpeg_frames, focus_roi_stream, preview

pytestmark = pytest.mark.unit


class _FakeRequest:
    """Minimal stand-in for fastapi.Request for tests driving _mjpeg_frames directly -- a real
    Request's is_disconnected() needs a live ASGI receive channel, which these tests aren't
    exercising. Only the one method _mjpeg_frames actually calls."""

    def __init__(self, disconnected: bool = False) -> None:
        self._disconnected = disconnected

    async def is_disconnected(self) -> bool:
        return self._disconnected


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


def test_capture_sidecar_lens_check_follows_the_lock() -> None:
    client = TestClient(app)
    unlocked = client.post("/capture").json()["lens_check"]
    assert unlocked["flagged"] is True
    assert unlocked["reason"] == "focus not locked"

    client.post("/focus/lock")
    record = client.post("/capture").json()
    client.post("/focus/unlock")
    assert record["lens_check"]["flagged"] is False
    assert record["lens_check"]["reported"] == record["lens_check"]["locked"]
    assert "focus not locked" not in record["flags"]
    assert set(record["uptime"]) >= {"boot_id", "pi_up_s", "app_up_s", "app_start", "flagged"}


def test_health_says_opening_until_the_app_start_has_opened_the_camera() -> None:
    """#252: a camera nothing has opened is never reported "ok". Starting the app opens it, in the
    background, and health then reports it working. Health itself only reads the state."""
    import time

    from npec_rig import health

    CameraManager.set_instance(None)
    health._reset_for_tests()
    try:
        # No app start (TestClient without `with` runs no lifespan): the camera stays unopened.
        assert TestClient(app).get("/camera/health").json()["state"] == "opening"
        assert TestClient(app).get("/camera/health").json()["state"] == "opening"
        with TestClient(app) as client:
            deadline = time.monotonic() + 10
            body = client.get("/camera/health").json()
            while body["state"] == "opening" and time.monotonic() < deadline:
                time.sleep(0.05)
                body = client.get("/camera/health").json()
            assert body["state"] == "ok"
    finally:
        CameraManager.wait_for_open(10)
        health._reset_for_tests()


def test_health_reports_an_attached_camera_that_will_not_open(tmp_path) -> None:
    """#252: a camera that is attached but will not open stays "failed_to_reopen"."""
    from npec_rig import health
    from npec_rig.camera_process import ProcessBackend

    fail = tmp_path / "fail_open"
    fail.write_text("fail")
    health._reset_for_tests()
    backend = ProcessBackend("synthetic", {"fail_open_file": str(fail)}, retry_s=60)
    try:
        CameraManager.set_instance(CameraManager(backend))
        body = TestClient(app).get("/camera/health").json()
        assert body["state"] == "failed_to_reopen"
        assert "could not be opened" in body["detail"]
    finally:
        backend.close()
        health._reset_for_tests()


def test_health_reports_disk_headroom_from_the_data_folder(tmp_path) -> None:
    """#307: the status line's data carries the disk's days left, from files in the data folder
    (the folder holding rig.db, a temporary folder in tests)."""
    (tmp_path / "rig").mkdir()
    (tmp_path / "rig" / "photo.jpg").write_bytes(b"x" * 1000)
    disk = TestClient(app).get("/camera/health").json()["disk"]
    assert disk["bytes_per_day"] >= 1000
    assert disk["days_left"] > 0
    assert disk["level"] in ("ok", "yellow", "red")
