"""The camera in its own program (camera_process.py, #51), driven with the synthetic camera's test
switches: a hang file freezes one call once, a fail-open file makes opening fail."""

import os
import pickle
import threading
import time

import pytest

from npec_rig import camera_process, health
from npec_rig.camera import (
    MAIN_SIZE,
    AutofocusTimeoutError,
    CameraManager,
    CameraStuckError,
    CameraUnavailableError,
)
from npec_rig.camera_process import FRAME_DIR, FRAME_PREFIX, ProcessBackend
from npec_rig.captures import take_photo

pytestmark = pytest.mark.unit

# Short limits, so a hang is detected in under a second. Measured 2026-10-15 on the Pi: the
# synthetic program answers a call in about 1 ms and a full frame in about 10 ms (#169).
FAST = {"default_time_limit_s": 0.4, "time_limits": {"capture_full_res": 0.6}, "retry_s": 0.05}


@pytest.fixture(autouse=True)
def _fresh_health():
    health._reset_for_tests()
    yield
    health._reset_for_tests()


@pytest.fixture
def switches(tmp_path):
    return {"hang_file": str(tmp_path / "hang"), "fail_open_file": str(tmp_path / "fail_open")}


@pytest.fixture
def backend(switches):
    b = ProcessBackend("synthetic", switches, **FAST)
    yield b
    b.close()


def _wait_until(predicate, timeout_s=15.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def _own_frame_files():
    return [p for p in FRAME_DIR.glob(f"{FRAME_PREFIX}*.raw")]


def test_calls_and_frames_cross_to_the_app(backend):
    """A full frame comes back through shared memory, intact, and its file is removed."""
    before = set(_own_frame_files())
    array, metadata = backend.capture_full_res()
    assert array.shape == (MAIN_SIZE[1], MAIN_SIZE[0], 3)
    assert array[0, 0, 1] == 180
    assert set(metadata) >= {"LensPosition", "ExposureTime"}
    assert set(_own_frame_files()) == before
    backend.set_lens_position(6.04)
    assert backend.get_lens_position() == 6.04
    assert backend.capture_preview_array().shape[2] == 4


def test_a_stuck_call_restarts_the_camera(backend, switches):
    """The stuck call fails within its limit, the next call fails at once while the camera
    restarts, the fault is recorded, and the new camera answers."""
    restored = threading.Event()
    backend.set_restart_listener(restored.set)
    first_pid = backend.pid
    with open(switches["hang_file"], "w") as f:
        f.write("capture_full_res")

    started = time.monotonic()
    with pytest.raises(CameraStuckError, match="stopped responding"):
        backend.capture_full_res()
    assert time.monotonic() - started < 5.0
    assert health.camera_health()["state"] in (health.CAMERA_RESTARTING, health.CAMERA_OK)

    assert restored.wait(15.0), "the restart listener was not called"
    assert backend.pid != first_pid
    array, _ = backend.capture_full_res()
    assert array.shape[2] == 3
    state = health.camera_health()
    assert state["state"] == health.CAMERA_OK
    assert state["restarts_24h"] == 1
    assert state["photos_flagged"]


def test_calls_fail_at_once_while_restarting(backend, switches):
    with open(switches["hang_file"], "w") as f:
        f.write("get_lens_position")
    with pytest.raises(CameraStuckError):
        backend.get_lens_position()
    started = time.monotonic()
    with pytest.raises(CameraUnavailableError):
        backend.get_lens_position()
    assert time.monotonic() - started < 0.5


def test_a_camera_that_will_not_open_is_reported_and_retried(switches):
    """Never a silent switch to synthetic frames: the state says the camera did not open, calls
    fail at once, and once the camera can open again it is back."""
    with open(switches["fail_open_file"], "w") as f:
        f.write("fail")
    b = ProcessBackend("synthetic", switches, **FAST)
    try:
        assert health.camera_health()["state"] == health.CAMERA_FAILED_TO_REOPEN
        with pytest.raises(CameraUnavailableError, match="could not be opened"):
            b.get_lens_position()
        assert _wait_until(lambda: health.camera_health()["reboot_needed"])
        os.remove(switches["fail_open_file"])
        assert _wait_until(lambda: health.camera_health()["state"] == health.CAMERA_OK)
        assert not health.camera_health()["reboot_needed"]
        assert b.get_lens_position() == 1.0
    finally:
        b.close()


def test_no_camera_attached_is_reported_as_no_camera(switches):
    """#252: no camera attached is its own state, not "ok" and not "will not open"."""
    with open(switches["fail_open_file"], "w") as f:
        f.write("no_camera")
    b = ProcessBackend("synthetic", switches, **FAST)
    try:
        state = health.camera_health()
        assert state["state"] == health.CAMERA_NO_CAMERA
        assert "No camera attached" in state["detail"]
        with pytest.raises(CameraUnavailableError, match="No camera attached"):
            b.get_lens_position()
    finally:
        b.close()


def test_a_working_camera_is_reported_attached(backend):
    assert health.camera_health()["state"] == health.CAMERA_OK
    assert "attached" in health.camera_health()["detail"]


def test_missing_camera_software_raises_import_error(switches):
    """Only missing camera software lets camera._default_backend fall back to synthetic."""
    with open(switches["fail_open_file"], "w") as f:
        f.write("missing")
    with pytest.raises(ImportError):
        ProcessBackend("synthetic", switches, **FAST)


def test_autofocus_timeout_survives_the_trip():
    exc = pickle.loads(pickle.dumps(AutofocusTimeoutError(6.27, "did not finish", 55.0)))
    assert isinstance(exc, AutofocusTimeoutError)
    assert exc.lens_position == 6.27
    assert "Lens not responding" in str(exc)


def test_unpicklable_errors_arrive_as_runtime_errors():
    class Odd(Exception):
        def __init__(self, a, b):
            super().__init__(f"{a} {b}")

    out = camera_process._picklable(Odd(1, 2))
    assert type(out) is RuntimeError
    assert "Odd" in str(out)


def test_the_lock_is_restored_after_a_restart(switches):
    """After a restart the manager drives the lens back and keeps the lock, the way an app start
    does, and the next photo is flagged as taken after a camera fault."""
    b = ProcessBackend("synthetic", switches, **FAST)
    try:
        manager = CameraManager(b)
        manager.set_lens_position(6.04)
        manager.lock_focus()
        CameraManager.set_instance(manager)
        recovered = threading.Event()

        def recover():
            manager._recover_after_restart()
            recovered.set()

        b.set_restart_listener(recover)
        with open(switches["hang_file"], "w") as f:
            f.write("capture_full_res")
        with pytest.raises(CameraStuckError):
            take_photo("capture")
        assert recovered.wait(15.0), "the manager did not recover"
        assert manager.focus_status() == {"locked": True, "lens_position": 6.04}
        fault = next(e for e in health.camera_events() if e["kind"] == "fault")
        assert fault["purpose"] == "capture" and fault["lens_locked"] == 6.04
        _array, record = take_photo("capture")
        assert record["camera_fault"]["flagged"]
        assert any("camera-fault window" in reason for reason in record["flags"])
        assert record["lens_check"]["flagged"] is False
    finally:
        CameraManager.set_instance(None)
        b.close()


def test_no_fault_no_flag():
    check = health.camera_fault_check()
    assert check["flagged"] is False


def test_a_fault_before_this_boot_is_not_counted(monkeypatch):
    monkeypatch.setattr(health, "_boot_id", lambda: "an-earlier-boot")
    health.record_camera_event(health.EVENT_FAULT, call="capture_full_res", limit_s=30.0)
    health.record_camera_event(health.EVENT_RESTARTED, recovery_s=1.0)
    monkeypatch.setattr(health, "_boot_id", lambda: "this-boot")
    assert health.camera_fault_check()["flagged"] is False


def test_the_window_counts_from_the_restart_not_the_fault(monkeypatch):
    """A long outage: the photos after the camera comes back get the whole window."""
    uptime = {"s": 1000.0}
    monkeypatch.setattr(health, "_uptime_s", lambda: uptime["s"])
    health.record_camera_event(health.EVENT_FAULT, call="capture_full_res", limit_s=30.0)
    uptime["s"] += 2 * health.CAMERA_FAULT_WINDOW_S  # down for two windows
    assert health.camera_fault_check()["flagged"] is False  # no restart yet, no photo possible
    health.record_camera_event(health.EVENT_RESTARTED, recovery_s=7200.0)
    uptime["s"] += 60
    check = health.camera_fault_check()
    assert check["flagged"] and check["since_restart_s"] == 60


def test_a_leftover_program_of_a_running_app_is_left_alone(tmp_path):
    """The pid file of another app on this Pi that still runs is not a leftover."""
    import subprocess
    import sys

    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        pid_file = tmp_path / "camera-process.pid"
        pid_file.write_text(f"{child.pid} {camera_process._start_time(child.pid)}")
        camera_process.end_leftover_program(pid_file)  # its parent, this test, is alive
        time.sleep(0.2)
        assert child.poll() is None
    finally:
        child.kill()
        child.wait()


def test_times_are_stored_in_one_utc_format():
    from datetime import datetime, timedelta, timezone

    winter = datetime(2026, 12, 1, 9, 0, 0, tzinfo=timezone(timedelta(hours=1)))
    assert health.utc_now(winter) == "2026-12-01T08:00:00.000000+00:00"
    health.record_camera_event(health.EVENT_FAULT, call="get_controls")
    (row,) = health.camera_events()
    assert row["time_utc"].endswith("+00:00") and len(row["time_utc"]) == 32


def test_a_restart_writes_a_fault_row_and_a_restarted_row(backend, switches):
    restored = threading.Event()
    backend.set_restart_listener(restored.set)
    old_pid = backend.pid
    with open(switches["hang_file"], "w") as f:
        f.write("get_controls")
    with pytest.raises(CameraStuckError):
        backend.get_controls()
    assert restored.wait(15.0)
    restarted, fault = health.camera_events()[:2]
    assert fault["kind"] == "fault"
    assert fault["call"] == "get_controls" and fault["limit_s"] == FAST["default_time_limit_s"]
    assert fault["program_pid"] == old_pid
    assert fault["camera"] == "synthetic" and fault["rig"]
    assert restarted["kind"] == "restarted"
    assert restarted["program_pid"] == backend.pid
    assert 0 < restarted["recovery_s"] < 15
    assert restarted["reboot_needed"] == 0


def test_failed_opens_are_rows_and_say_when_a_reboot_is_needed(switches):
    with open(switches["fail_open_file"], "w") as f:
        f.write("fail")
    b = ProcessBackend("synthetic", switches, **FAST)
    try:
        assert _wait_until(lambda: health.camera_health()["reboot_needed"])
        failed = [e for e in health.camera_events() if e["kind"] == "open_failed"]
        assert len(failed) >= camera_process.FAILED_OPENS_BEFORE_REBOOT
        assert failed[0]["reboot_needed"] == 1 and failed[-1]["reboot_needed"] == 0
        assert "could not be opened" in failed[0]["detail"]
    finally:
        b.close()
