import pytest
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from npec_rig.app import _mjpeg_frames, app, focus_roi_stream, preview
from npec_rig.camera import SIMULATED_AUTOFOCUS_POSITION, CameraManager, SyntheticBackend

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def synthetic_camera() -> None:
    CameraManager.set_instance(CameraManager(SyntheticBackend()))


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


def test_roi_get_and_set() -> None:
    client = TestClient(app)
    response = client.post("/focus/roi", json={"x": 100, "y": 80, "size": 50})
    assert response.status_code == 200
    assert response.json() == {"x": 100, "y": 80, "size": 50}

    response = client.get("/focus/roi")
    assert response.status_code == 200
    assert response.json() == {"x": 100, "y": 80, "size": 50}


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
    assert isinstance(response.json()["score"], float)


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
