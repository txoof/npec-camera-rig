import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

import npec_rig.app as app_module
from npec_rig import focus_reference
from npec_rig.camera import CameraManager, SyntheticBackend
from npec_rig.tags import TagDetection

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(focus_reference, "_last_check", None)
    CameraManager.set_instance(CameraManager(SyntheticBackend()))


def _checkerboard(size: int = 1200, square: int = 20) -> np.ndarray:
    yy, xx = np.mgrid[0:size, 0:size]
    board = (((yy // square) + (xx // square)) % 2 * 255).astype(np.uint8)
    return np.repeat(board[..., None], 3, axis=2)


def _tag(tag_id: int, x: float, y: float) -> TagDetection:
    h = 140.0
    corners = ((x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h))
    return TagDetection(tag_id=tag_id, corners=corners, centre=(x, y))


def test_a_blurred_reference_square_is_reported_as_changed() -> None:
    sharp = _checkerboard()
    reference = focus_reference.set_reference(sharp, [_tag(500, 600, 600)], "2026-10-06/x")
    assert (reference["x"], reference["y"]) == (600, 600)

    assert focus_reference.check(sharp, reference)["verdict"] == "OK"
    blurred = cv2.GaussianBlur(sharp, (0, 0), 3)
    result = focus_reference.check(blurred, reference)
    assert result["verdict"] == "CHANGED"
    assert result["change_pct"] < -focus_reference.CHANGE_LIMIT_PCT


def test_a_change_within_the_limit_is_ok() -> None:
    frame = _checkerboard()
    reference = {"x": 600, "y": 600, "sharpness": focus_reference.sharpness_at(frame, 600, 600) * 1.05}
    result = focus_reference.check(frame, reference)
    assert result["verdict"] == "OK"
    assert result["change_pct"] == pytest.approx(100 * (1 / 1.05 - 1))


def test_without_a_reference_nothing_is_judged() -> None:
    assert focus_reference.check(_checkerboard(), None)["verdict"] == "NO REFERENCE"


def test_setting_a_reference_needs_tag_500_in_the_photograph() -> None:
    with pytest.raises(LookupError):
        focus_reference.set_reference(_checkerboard(), [_tag(450, 600, 600)], "2026-10-06/x")
    assert focus_reference.load_reference() is None


def test_the_square_is_clipped_at_the_frame_edge() -> None:
    frame = _checkerboard(size=600)
    assert focus_reference.sharpness_at(frame, 10, 10) > 0  # no error, a partial square


class _BoardBackend(SyntheticBackend):
    """Synthetic camera whose full-res photograph has detail (the default one is plain green)."""

    def capture_full_res(self) -> tuple[np.ndarray, dict]:
        _, metadata = super().capture_full_res()
        return _checkerboard(), metadata


def test_every_capture_is_checked_and_the_result_is_kept_with_the_photograph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    CameraManager.set_instance(CameraManager(_BoardBackend()))
    client = TestClient(app_module.app)
    assert client.get("/focus/reference").json()["reference"] is None

    monkeypatch.setattr(app_module, "detect_tags", lambda frame: [_tag(500, 300, 300)])
    r = client.post("/focus/reference")
    assert r.status_code == 200
    body = r.json()
    assert (body["reference"]["x"], body["reference"]["y"]) == (300, 300)
    assert body["last_check"]["verdict"] == "OK"  # the reference photograph against itself

    record = client.post("/capture").json()
    assert record["focus_reference"]["verdict"] == "OK"  # the same photograph again
    assert client.get("/focus/reference").json()["last_check"] == record["focus_reference"]


def test_a_reference_square_without_detail_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app_module.app)  # plain green synthetic photograph
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: [_tag(500, 300, 300)])
    r = client.post("/focus/reference")
    assert r.status_code == 409
    assert "no detail" in r.json()["detail"]
    assert client.get("/focus/reference").json()["reference"] is None


def test_setting_the_reference_without_tag_500_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app_module.app)
    monkeypatch.setattr(app_module, "detect_tags", lambda frame: [])
    r = client.post("/focus/reference")
    assert r.status_code == 409
    assert "tag 500 was not found" in r.json()["detail"]
    assert client.get("/focus/reference").json()["reference"] is None
