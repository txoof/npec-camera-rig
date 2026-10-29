import re
import threading
import time

import pytest
from fastapi.testclient import TestClient

import npec_rig.app as app_module
from npec_rig.app import app
from npec_rig.camera import CameraManager, SyntheticBackend

pytestmark = pytest.mark.unit


def test_root_redirects_to_gallery() -> None:
    client = TestClient(app, follow_redirects=False)
    response = client.get("/")
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/gallery"


# Every page route. The diagnostics page serves any stem (see the test below), so one stands in.
PAGE_ROUTES = [
    "/setup",
    "/setup/focus",
    "/setup/calibration",
    "/setup/calibration-history",
    "/setup/calibration-history/20260101T000000000000",
    "/setup/calibration/diagnostics",
    "/setup/validation",
    "/setup/health-check",
    "/gallery",
    "/experiments",
    "/ui",
]


@pytest.mark.parametrize("path", PAGE_ROUTES)
def test_page_loads(path: str) -> None:
    client = TestClient(app)
    response = client.get(path)
    assert response.status_code == 200
    assert "NPEC Camera Rig" in response.text


# Shared scripts that look up ids in the page that includes their panel.
PANEL_SCRIPTS = {
    "/setup/focus": ["squareness-guides.js"],
    "/setup/calibration": ["squareness-guides.js"],
}


@pytest.mark.parametrize("path", PAGE_ROUTES)
def test_every_id_a_page_script_looks_up_is_on_the_page_once(path: str) -> None:
    # A literal getElementById("x") with no id="x" on the page, or two of them, is a page that
    # breaks in the browser while every other test passes. Ids that a script writes into the
    # page itself count, since the check reads the whole response, scripts included. An id a
    # script builds from a template (id="control-${name}") cannot be counted, only matched.
    html = TestClient(app).get(path).text
    # $("x") is the getElementById shorthand some page scripts define (the /ui page does).
    lookup = r"(?:getElementById|\$)\(\s*[\"'`]([^\"'`$]+)[\"'`]\s*\)"
    wanted = set(re.findall(lookup, html))
    for script in PANEL_SCRIPTS.get(path, []):
        wanted |= set(re.findall(lookup, TestClient(app).get(f"/static/{script}").text))
    built = re.findall(r'id="([^"$]*)\$\{', html)
    wrong = {}
    for name in sorted(wanted):
        n = html.count(f'id="{name}"')
        if n != 1 and not (n == 0 and any(name.startswith(prefix) for prefix in built if prefix)):
            wrong[name] = n
    assert wrong == {}


def test_calibration_history_diagnostics_page_loads() -> None:
    # One template serves any stem -- the page looks itself up in /calibration/list
    # client-side, so this route never 404s on an unknown stem the way the JSON endpoints do.
    client = TestClient(app)
    response = client.get("/setup/calibration-history/20260101T000000000000")
    assert response.status_code == 200
    assert "NPEC Camera Rig" in response.text


class _StuckCaptureBackend(SyntheticBackend):
    """A camera whose full-res capture timed out in the camera program (camera_process.py)."""

    def capture_full_res(self):
        from npec_rig.camera import CameraStuckError

        raise CameraStuckError(
            "The camera stopped responding (capture_full_res did not finish within 30 s) and is "
            "being restarted. Try again in a minute."
        )


def test_a_stuck_camera_answers_503_with_the_reason() -> None:
    CameraManager.set_instance(CameraManager(_StuckCaptureBackend()))
    response = TestClient(app).post("/capture")
    assert response.status_code == 503
    assert "stopped responding" in response.json()["detail"]


def test_camera_health_reports_the_camera_state() -> None:
    from npec_rig import health

    health._reset_for_tests()
    try:
        health.record_camera_state(health.CAMERA_FAILED_TO_REOPEN, "could not be opened", True)
        body = TestClient(app).get("/camera/health").json()
        assert body["state"] == "failed_to_reopen"
        assert body["reboot_needed"] is True
        assert body["photos_flagged"] is False
    finally:
        health._reset_for_tests()


def test_a_camera_program_that_cannot_start_answers_503() -> None:
    from npec_rig import health
    from npec_rig.camera import UnavailableBackend

    health._reset_for_tests()
    try:
        CameraManager.set_instance(CameraManager(UnavailableBackend("spawn failed")))
        response = TestClient(app).post("/capture")
        assert response.status_code == 503
        assert "spawn failed" in response.json()["detail"]
        assert health.camera_health()["state"] == "failed_to_reopen"
    finally:
        health._reset_for_tests()


def test_every_page_has_the_camera_status_line() -> None:
    page = TestClient(app).get("/setup").text
    assert 'id="camera-status"' in page


class _ClosingBackend(SyntheticBackend):
    """Records when close() runs, to check the app's shutdown waits for an in-flight call."""

    def __init__(self) -> None:
        super().__init__()
        self.closed_at: float | None = None

    def close(self) -> None:
        self.closed_at = time.monotonic()


def test_shutdown_closes_the_camera_only_after_an_in_flight_call(monkeypatch) -> None:
    # A live stream cut off by --timeout-graceful-shutdown can leave a frame grab running in its
    # worker thread; closing the camera under it would read as a camera fault (#139).
    backend = _ClosingBackend()
    manager = CameraManager(backend)
    CameraManager.set_instance(manager)
    released_at: list[float] = []

    def hold_the_call_lock() -> None:
        with manager._call_lock:
            started.set()
            time.sleep(0.3)
            released_at.append(time.monotonic())

    started = threading.Event()
    grab = threading.Thread(target=hold_the_call_lock)
    grab.start()
    started.wait()
    with TestClient(app):
        pass
    grab.join()
    assert backend.closed_at is not None
    assert backend.closed_at >= released_at[0]


def test_shutdown_closes_the_camera_even_if_a_call_never_finishes(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "SHUTDOWN_CAMERA_IDLE_WAIT_S", 0.1)
    backend = _ClosingBackend()
    manager = CameraManager(backend)
    CameraManager.set_instance(manager)
    manager._call_lock.acquire()
    try:
        with TestClient(app):
            pass
    finally:
        manager._call_lock.release()
    assert backend.closed_at is not None


# --- Gallery images and paging (#56, #165) ---


# The development rig shows a red leaf in the browser tab, so it can't be taken for production (#320).
def test_development_rig_links_the_red_favicon(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NPEC_RIG_ENVIRONMENT", "development")
    response = TestClient(app).get("/gallery")
    assert '<link rel="icon" href="/static/favicon-dev.svg"' in response.text


def test_production_keeps_the_green_favicon(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NPEC_RIG_ENVIRONMENT", raising=False)
    response = TestClient(app).get("/gallery")
    assert '<link rel="icon" href="/static/favicon.svg"' in response.text


def test_red_favicon_is_served() -> None:
    response = TestClient(app).get("/static/favicon-dev.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
