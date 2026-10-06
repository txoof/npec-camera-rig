import threading
import time
from concurrent.futures import TimeoutError as FutureTimeoutError

import numpy as np
import pytest

import npec_rig.camera as camera_module
from npec_rig.camera import (
    DEFAULT_LENS_POSITION,
    PEAKING_COLOR,
    SENSOR_METADATA_FIELDS,
    SIMULATED_AUTOFOCUS_POSITION,
    SYNTHETIC_CONTROL_RANGES,
    CameraBusyError,
    CameraManager,
    SyntheticBackend,
    array_to_jpeg,
    crop_roi,
    laplacian_variance,
    peaking_overlay,
    to_grayscale,
)
from npec_rig.settings import load_settings

pytestmark = pytest.mark.unit


class _RecordingPicamera2:
    """Stands in for picamera2.Picamera2: records configurations and control writes, so the real
    backend's capture sequence can be checked without a camera."""

    camera_controls: dict = {}

    def __init__(self) -> None:
        self.configured: list[dict] = []
        self.control_writes: list[dict] = []
        self.metadata_waits: list = []
        self.autofocus_waits: list = []
        self.autofocus_never_finishes = False
        self.metadata_never_arrives = False
        self.cancelled = 0
        self.closed = False

    def create_video_configuration(self, main=None, lores=None):
        return {"kind": "video"}

    def create_still_configuration(self, controls=None):
        return {"kind": "still", "controls": dict(controls or {})}

    def configure(self, config) -> None:
        self.configured.append(config)

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def set_controls(self, controls: dict) -> None:
        self.control_writes.append(dict(controls))

    def capture_array(self, _stream):
        return np.zeros((4, 4, 3), dtype=np.uint8)

    def capture_metadata(self, wait=None) -> dict:
        self.metadata_waits.append(wait)
        if self.metadata_never_arrives:
            raise FutureTimeoutError()
        return {"LensPosition": 0.0}

    def autofocus_cycle(self, wait=None):
        self.autofocus_waits.append(wait)
        if self.autofocus_never_finishes:
            raise FutureTimeoutError()
        return True

    def cancel_all_and_flush(self) -> None:
        self.cancelled += 1

    def close(self) -> None:
        self.closed = True


def _recording_backend() -> "camera_module.Picamera2Backend":
    backend = object.__new__(camera_module.Picamera2Backend)
    backend._new_picamera2 = _RecordingPicamera2
    backend._picam2 = _RecordingPicamera2()
    backend._video_config = {"kind": "video"}
    backend._control_cache = {}
    backend._lens_position = DEFAULT_LENS_POSITION
    return backend


def test_a_full_res_capture_reopens_the_camera_in_manual_focus_at_the_lens_position() -> None:
    # 2026-10-06: after switching back to the video configuration the camera accepted every lens
    # write and moved on none (Autofocus timed out too), even with manual focus re-applied.
    # Reopening the camera cleared it.
    backend = _recording_backend()
    backend._control_cache = {"AeEnable": True}
    backend.set_lens_position(6.44)
    before = backend._picam2

    backend.capture_full_res()
    assert before.configured == [{"kind": "still", "controls": {"AfMode": 0, "LensPosition": 6.44}}]
    assert before.closed
    after = backend._picam2
    assert after is not before and not after.closed
    assert after.configured == [{"kind": "video"}]
    assert after.control_writes[0] == {"AfMode": 0, "LensPosition": 6.44}
    assert {"AeEnable": True} in after.control_writes  # cached AE/AWB restored on the new one

    backend.set_lens_position(6.18)  # a later move is what the next capture uses
    backend.capture_full_res()
    assert after.configured[-1]["controls"] == {"AfMode": 0, "LensPosition": 6.18}


def test_an_autofocus_cycle_that_never_finishes_is_cancelled_and_leaves_the_lens_in_manual() -> None:
    # TODO.md "wedges the whole camera pipeline": picamera2 waited for the scan with no limit,
    # holding the camera lock, so every camera call hung until a restart.
    backend = _recording_backend()
    backend.set_lens_position(6.37)
    backend._picam2.autofocus_never_finishes = True

    with pytest.raises(camera_module.AutofocusTimeoutError) as exc:
        backend.autofocus()

    assert exc.value.lens_position == 6.37
    cycle_wait = camera_module.AUTOFOCUS_TIMEOUT_S - camera_module.AUTOFOCUS_METADATA_TIMEOUT_S
    assert backend._picam2.autofocus_waits == [cycle_wait]
    assert backend._picam2.cancelled == 1
    # AfTrigger 1 = Cancel: the latched scan must not start after the job is dropped.
    assert backend._picam2.control_writes[-1] == {
        "AfTrigger": 1, "AfMode": 0, "LensPosition": 6.37
    }
    assert backend._picam2.metadata_waits == []  # a metadata read could hang as well


def test_a_finished_autofocus_cycle_waits_a_bounded_time_for_everything() -> None:
    backend = _recording_backend()
    assert backend.autofocus() == (True, 0.0)
    # Scan and lens read together stay within AUTOFOCUS_TIMEOUT_S.
    assert sum(backend._picam2.autofocus_waits + backend._picam2.metadata_waits) == (
        camera_module.AUTOFOCUS_TIMEOUT_S
    )
    assert backend._picam2.metadata_waits == [camera_module.AUTOFOCUS_METADATA_TIMEOUT_S]
    assert backend._picam2.cancelled == 0
    assert backend._picam2.control_writes[-1] == {"AfMode": 0}


def test_a_finished_cycle_whose_lens_read_times_out_says_which_step_stalled() -> None:
    backend = _recording_backend()
    backend.set_lens_position(6.37)
    backend._picam2.metadata_never_arrives = True

    with pytest.raises(camera_module.AutofocusTimeoutError, match="did not report the lens"):
        backend.autofocus()
    assert backend._picam2.cancelled == 1
    assert backend._picam2.control_writes[-1]["LensPosition"] == 6.37


class _TimingOutAutofocusBackend(SyntheticBackend):
    def autofocus(self) -> tuple[bool, float]:
        raise camera_module.AutofocusTimeoutError(self._lens_position, "did not finish", 55.2)


def test_a_timed_out_autofocus_says_so_and_frees_the_camera() -> None:
    manager = CameraManager(_TimingOutAutofocusBackend())
    manager.set_lens_position(6.3)

    result = manager.autofocus()

    assert result["success"] is False
    assert result["lens_position"] == pytest.approx(6.3)
    assert result["timed_out"] == (
        "Lens not responding: restart the app (autofocus did not finish after 55 s)"
    )
    assert manager.focus_status()["locked"] is False
    assert manager._call_lock.acquire(blocking=False)  # the next camera call is not stuck
    manager._call_lock.release()


def test_the_startup_replay_of_a_persisted_lens_position_is_what_a_capture_re_applies() -> None:
    # Before 2026-10-01 the startup replay went through set_control, which left the remembered
    # position at the 1.0 default: the first capture after a restart would have commanded 1.0.
    backend = _recording_backend()
    first = backend._picam2

    backend.set_control("LensPosition", 6.18)
    backend.capture_full_res()
    assert first.configured[0]["controls"] == {"AfMode": 0, "LensPosition": 6.18}


class _RecordingSyntheticBackend(SyntheticBackend):
    """Synthetic camera that records lens writes, and can report a stale position for a while
    (as the real one does for up to about 45 s after a full-res capture)."""

    def __init__(self, stale_reads: int = 0) -> None:
        super().__init__()
        self.lens_writes: list[float] = []
        self.stale_reads = stale_reads

    def set_lens_position(self, value: float) -> None:
        self.lens_writes.append(value)
        super().set_lens_position(value)

    def get_lens_position(self) -> float:
        if self.stale_reads > 0:
            self.stale_reads -= 1
            return 1.0
        return super().get_lens_position()


class _ReopeningSyntheticBackend(_RecordingSyntheticBackend):
    """Synthetic camera that, like the real one, reopens on a full-res capture."""

    reopens_after_full_res = True


def test_after_a_full_res_capture_the_lens_is_driven_back_and_the_lock_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(camera_module, "LENS_APPROACH_PAUSE_S", 0.0)
    backend = _ReopeningSyntheticBackend()
    manager = CameraManager(backend)
    manager.set_lens_position(6.18)
    manager.lock_focus()
    backend.lens_writes.clear()

    manager.capture_full_res()
    assert backend.lens_writes == [pytest.approx(5.88), 6.18]  # the one consistent way
    assert manager.focus_status() == {"locked": True, "lens_position": 6.18}


def test_a_lens_that_does_not_come_back_after_a_capture_clears_the_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(camera_module, "LENS_APPROACH_PAUSE_S", 0.0)
    backend = _ReopeningSyntheticBackend()
    manager = CameraManager(backend)
    manager.set_lens_position(6.18)
    manager.lock_focus()
    monkeypatch.setattr(camera_module, "LENS_SETTLE_TIMEOUT_S", 0.0)
    backend.stale_reads = 10**6

    manager.capture_full_res()  # the photo itself is still returned
    assert manager.focus_status() == {"locked": False, "lens_position": None}
    assert load_settings()["FocusConfirmed"] is False


def test_a_camera_that_does_not_reopen_gets_no_lens_moves_from_a_capture() -> None:
    backend = _RecordingSyntheticBackend()
    manager = CameraManager(backend)
    manager.set_lens_position(6.18)
    backend.lens_writes.clear()

    manager.capture_full_res()
    assert backend.lens_writes == []


def test_locking_focus_drives_the_lens_from_below_and_waits_for_the_camera() -> None:
    backend = _RecordingSyntheticBackend()
    manager = CameraManager(backend)
    manager.set_lens_position(6.18)
    backend.lens_writes.clear()
    backend.stale_reads = 3  # the camera reports the old position for three reads

    status = manager.lock_focus()
    assert backend.lens_writes == [pytest.approx(5.88), 6.18]  # one way in: from 0.3 below
    assert status == {"locked": True, "lens_position": 6.18}  # what was set, confirmed
    assert backend.stale_reads == 0  # it waited until the camera agreed


def test_focus_stays_unlocked_when_the_camera_never_reports_the_lens_there(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(camera_module, "LENS_SETTLE_TIMEOUT_S", 0.0)
    backend = _RecordingSyntheticBackend()
    manager = CameraManager(backend)
    manager.set_lens_position(6.18)
    backend.stale_reads = 10**6

    with pytest.raises(camera_module.LensNotSettledError):
        manager.lock_focus()
    assert manager.focus_status() == {"locked": False, "lens_position": None}


def test_a_failed_lock_does_not_leave_an_older_lock_in_place(monkeypatch: pytest.MonkeyPatch) -> None:
    # Code review 2026-10-02: the lens moves during a lock, so an older lock must not survive
    # the new one failing.
    backend = _RecordingSyntheticBackend()
    manager = CameraManager(backend)
    manager.set_lens_position(6.18)
    manager.lock_focus()
    monkeypatch.setattr(camera_module, "LENS_SETTLE_TIMEOUT_S", 0.0)
    backend.stale_reads = 10**6

    with pytest.raises(camera_module.LensNotSettledError):
        manager.lock_focus()
    assert manager.focus_status() == {"locked": False, "lens_position": None}
    assert load_settings()["FocusConfirmed"] is False


def test_moving_the_lens_while_lock_focus_waits_locks_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Code review 2026-10-02: the slider moved during the up-to-60 s wait must not end in a lock
    # at the old position.
    manager = CameraManager(_RecordingSyntheticBackend())
    manager.set_lens_position(6.18)
    reads = []

    def report_while_the_operator_moves_the_slider() -> float:
        reads.append(True)
        if len(reads) == 1:
            manager.set_lens_position(6.40)  # another request, while the lock waits
            return 1.0  # the camera has not caught up yet
        if len(reads) == 2:
            return 6.40  # the slider move's own check sees it
        return 6.18  # then reports the lock's target

    monkeypatch.setattr(manager, "get_lens_position", report_while_the_operator_moves_the_slider)
    with pytest.raises(camera_module.LensMovedDuringLockError):
        manager.lock_focus()
    assert manager.focus_status() == {"locked": False, "lens_position": None}


class _StuckLensBackend(_RecordingSyntheticBackend):
    """Synthetic camera whose lens accepts every write and reports the same position forever,
    as the real one did after a full-res capture (TODO.md, "Lens stops responding")."""

    def __init__(self, stuck_at: float) -> None:
        super().__init__()
        self.stuck_at = stuck_at

    def get_lens_position(self) -> float:
        return self.stuck_at


def test_a_manual_move_the_lens_does_not_follow_says_restart_the_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(camera_module, "LENS_SETTLE_TIMEOUT_S", 0.0)
    manager = CameraManager(_StuckLensBackend(stuck_at=6.27))

    with pytest.raises(camera_module.LensNotSettledError) as error:
        manager.set_lens_position(4.77)
    assert str(error.value).startswith("Lens not responding: restart the app")


def test_a_manual_move_waits_until_the_camera_reports_it() -> None:
    backend = _RecordingSyntheticBackend()
    manager = CameraManager(backend)
    backend.stale_reads = 3

    manager.set_lens_position(4.77)
    assert backend.stale_reads == 0


def test_a_newer_slider_move_ends_the_wait_of_an_older_one_without_an_error() -> None:
    manager = CameraManager(_RecordingSyntheticBackend())
    reads = []

    def report_while_the_slider_moves_on(*_: object) -> float:
        reads.append(True)
        if len(reads) == 1:
            manager._commanded_lens_position = 5.00  # the next slider request arrived
        return 1.0

    manager._backend.get_lens_position = report_while_the_slider_moves_on
    manager.set_lens_position(4.77)  # no error: the newer move does its own check


def test_lock_focus_does_not_confirm_a_stuck_lens_that_already_reports_the_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Measured 2026-10-06 (run 3b): a stuck lens reporting 6.27 made Lock focus "confirm" 6.27.
    monkeypatch.setattr(camera_module, "LENS_SETTLE_TIMEOUT_S", 0.0)
    backend = _StuckLensBackend(stuck_at=6.27)
    manager = CameraManager(backend)
    manager.set_lens_position(6.27)  # passes: the camera reports the lens where it was asked
    backend.lens_writes.clear()

    with pytest.raises(camera_module.LensNotSettledError):
        manager.lock_focus()
    assert backend.lens_writes == [pytest.approx(5.97)]  # never reported there: no target write
    assert manager.focus_status() == {"locked": False, "lens_position": None}


def test_the_drive_keeps_its_fixed_pause_when_the_camera_reports_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The validation bands were measured with this sequence: waiting for the approach report must
    # not make the target write come any sooner.
    monkeypatch.setattr(camera_module, "LENS_APPROACH_PAUSE_S", 0.05)
    write_times = []

    class _TimedBackend(_RecordingSyntheticBackend):
        def set_lens_position(self, value: float) -> None:
            write_times.append(time.monotonic())
            super().set_lens_position(value)

    manager = CameraManager(_TimedBackend())
    manager.set_lens_position(6.18)
    write_times.clear()

    manager.lock_focus()
    assert write_times[1] - write_times[0] >= 0.05


def test_a_restart_drives_the_lens_back_the_same_way_and_keeps_the_lock() -> None:
    from npec_rig.settings import save_setting

    save_setting("LensPosition", 6.18)
    save_setting("FocusConfirmed", True)
    save_setting("FocusConfirmedLensPosition", 6.18)

    backend = _RecordingSyntheticBackend()
    manager = CameraManager(backend)
    assert backend.lens_writes == [pytest.approx(5.88), 6.18]
    assert manager.focus_status() == {"locked": True, "lens_position": 6.18}


def test_synthetic_backend_produces_expected_shape() -> None:
    backend = SyntheticBackend(width=64, height=48)
    frame = backend.capture_array()
    assert frame.shape == (48, 64, 3)


def test_synthetic_backend_preview_is_smaller_than_main() -> None:
    backend = SyntheticBackend(width=64, height=48, preview_width=16, preview_height=12)
    assert backend.capture_array().shape == (48, 64, 3)
    assert backend.capture_preview_array().shape == (12, 16, 3)


def test_synthetic_backend_lens_position_round_trips() -> None:
    backend = SyntheticBackend()
    assert backend.get_lens_position() == DEFAULT_LENS_POSITION
    backend.set_lens_position(6.3)
    assert backend.get_lens_position() == 6.3


def test_synthetic_backend_autofocus_reports_success_and_lens_position() -> None:
    backend = SyntheticBackend()
    success, lens_position = backend.autofocus()
    assert success is True
    assert lens_position == SIMULATED_AUTOFOCUS_POSITION
    assert backend.get_lens_position() == SIMULATED_AUTOFOCUS_POSITION


def test_synthetic_backend_capture_full_res_returns_array_and_metadata() -> None:
    backend = SyntheticBackend(width=64, height=48)
    array, metadata = backend.capture_full_res()
    assert array.shape == (48, 64, 3)
    # Same key set as Picamera2Backend reports, so code written against one behaves the same
    # against the other — the whole point of a synthetic backend.
    assert set(metadata) == set(SENSOR_METADATA_FIELDS)
    assert metadata["LensPosition"] == DEFAULT_LENS_POSITION


def test_array_to_jpeg_produces_jpeg_bytes() -> None:
    frame = SyntheticBackend(width=16, height=16).capture_array()
    data = array_to_jpeg(frame)
    assert data[:2] == b"\xff\xd8"


def test_array_to_jpeg_does_not_reorder_channels() -> None:
    # `frame`'s first 3 channels are literally R,G,B, verified directly against a known-color
    # real-world reference on 2026-09-21 -- despite picamera2 logging "BGR888"/"XBGR8888" for
    # these streams, it does not actually deliver that byte order. A previous fix attempt
    # assumed the log name was accurate and added a reversal; that was wrong and made colors
    # worse, not better (TODO.md has the full account). A pure red real-world pixel arrives as
    # (R=255, G=0, B=0); the saved JPEG must decode back to red, not blue.
    from io import BytesIO

    from PIL import Image

    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    frame[..., 0] = 255  # channel 0 is red, as delivered -- no reversal
    decoded = np.array(Image.open(BytesIO(array_to_jpeg(frame))).convert("RGB"))
    pixel = decoded[0, 0]
    assert pixel[0] > pixel[2]  # red channel dominant, not blue


def test_to_grayscale_weights_the_rgb_channels_correctly() -> None:
    # Pure red (channel 0) gets the 0.299 luminance weight; pure blue (channel 2) gets 0.114.
    red = np.zeros((1, 1, 3), dtype=np.uint8)
    red[..., 0] = 255
    blue = np.zeros((1, 1, 3), dtype=np.uint8)
    blue[..., 2] = 255
    assert to_grayscale(red)[0, 0] == pytest.approx(255 * 0.299)
    assert to_grayscale(blue)[0, 0] == pytest.approx(255 * 0.114)


def test_array_to_jpeg_handles_a_padding_channel() -> None:
    # The video config's "main"/"lores" streams deliver a 4th, unused padding channel
    # (confirmed 2026-09-21) -- array_to_jpeg must drop it, not treat it as a color channel.
    from io import BytesIO

    from PIL import Image

    frame = np.zeros((4, 4, 4), dtype=np.uint8)
    frame[..., 0] = 255  # channel 0 is red, as delivered
    frame[..., 3] = 0  # padding, as real captures report it
    decoded = np.array(Image.open(BytesIO(array_to_jpeg(frame))).convert("RGB"))
    pixel = decoded[0, 0]
    assert pixel[0] > pixel[2]  # red channel dominant, not blue


def test_peaking_overlay_handles_a_padding_channel() -> None:
    # Same 4-channel shape as capture_array() returns from the real video config -- the
    # padding channel must survive untouched, not raise or get clobbered by the 3-value color.
    crop = np.zeros((10, 10, 4), dtype=np.uint8)
    crop[3, 3] = (200, 10, 10, 0)  # one bright, isolated pixel to trip the edge threshold
    overlay = peaking_overlay(crop, threshold=5.0)
    assert overlay.shape == crop.shape
    assert overlay[..., 3].max() == 0  # padding channel untouched


def test_crop_roi_returns_requested_size_centered_on_point() -> None:
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    crop = crop_roi(frame, x=50, y=50, size=20)
    assert crop.shape == (20, 20, 3)


def test_crop_roi_clamps_to_frame_bounds_near_edges() -> None:
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    crop = crop_roi(frame, x=0, y=0, size=20)
    assert crop.shape == (20, 20, 3)
    crop = crop_roi(frame, x=99, y=99, size=20)
    assert crop.shape == (20, 20, 3)


def test_laplacian_variance_is_zero_on_flat_field() -> None:
    flat = np.full((50, 50), 128.0)
    assert laplacian_variance(flat) == 0.0


def test_laplacian_variance_is_higher_for_sharper_pattern() -> None:
    rng = np.random.default_rng(0)
    noisy = to_grayscale(rng.integers(0, 256, size=(50, 50, 3)).astype(np.uint8))
    flat = to_grayscale(np.full((50, 50, 3), 128, dtype=np.uint8))
    assert laplacian_variance(noisy) > laplacian_variance(flat)


def test_peaking_overlay_leaves_a_flat_field_untouched() -> None:
    flat = np.full((50, 50, 3), 128, dtype=np.uint8)
    overlay = peaking_overlay(flat)
    assert np.array_equal(overlay, flat)


def test_peaking_overlay_marks_a_sharp_edge() -> None:
    frame = np.zeros((50, 50, 3), dtype=np.uint8)
    frame[:, 25:] = 255  # a hard edge down the middle
    overlay = peaking_overlay(frame, threshold=10.0)
    assert (overlay == PEAKING_COLOR).any()
    assert not (overlay == PEAKING_COLOR).all()


def test_camera_manager_focus_score_and_roi_crop_do_not_touch_hardware() -> None:
    manager = CameraManager(SyntheticBackend(width=64, height=48))
    manager.set_roi(x=32, y=24, size=16)
    assert manager.get_roi() == {"x": 32, "y": 24, "size": 16}
    # SyntheticBackend's pattern is flat within any crop, so its Laplacian variance is exactly
    # zero, not just "some float" — deterministic, so pin the value, not just its type.
    assert manager.focus_score() == 0.0
    jpeg = manager.roi_crop_jpeg()
    assert jpeg[:2] == b"\xff\xd8"


def test_preview_jpeg_raises_camera_busy_when_lock_is_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(camera_module, "STREAM_LOCK_TIMEOUT", 0.05)
    manager = CameraManager(SyntheticBackend())
    manager._call_lock.acquire()  # simulate another in-progress camera call
    try:
        with pytest.raises(CameraBusyError):
            manager.preview_jpeg()
    finally:
        manager._call_lock.release()


def test_roi_crop_jpeg_raises_camera_busy_when_lock_is_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(camera_module, "STREAM_LOCK_TIMEOUT", 0.05)
    manager = CameraManager(SyntheticBackend())
    manager._call_lock.acquire()
    try:
        with pytest.raises(CameraBusyError):
            manager.roi_crop_jpeg()
    finally:
        manager._call_lock.release()


def test_preview_jpeg_succeeds_once_a_held_lock_is_released() -> None:
    # Contends the lock from another thread, released well before STREAM_LOCK_TIMEOUT --
    # preview_jpeg should block until it's free, then succeed, not raise.
    manager = CameraManager(SyntheticBackend())
    manager._call_lock.acquire()
    releaser = threading.Timer(0.05, manager._call_lock.release)
    releaser.start()
    try:
        jpeg = manager.preview_jpeg()
    finally:
        releaser.cancel()
    assert jpeg[:2] == b"\xff\xd8"


def test_camera_manager_lock_and_unlock_focus() -> None:
    manager = CameraManager(SyntheticBackend())
    assert manager.focus_status() == {"locked": False, "lens_position": None}

    manager.set_lens_position(6.3)
    status = manager.lock_focus()
    assert status == {"locked": True, "lens_position": 6.3}
    assert manager.focus_status() == status

    status = manager.unlock_focus()
    assert status == {"locked": False, "lens_position": None}


def test_a_locked_focus_refuses_a_manual_move_and_autofocus() -> None:
    # Aaron, 2026-10-06: while focus is locked no one at the rig can change it; Unlock focus first.
    backend = _RecordingSyntheticBackend()
    manager = CameraManager(backend)
    manager.set_lens_position(6.3)
    manager.lock_focus()
    backend.lens_writes.clear()

    with pytest.raises(camera_module.FocusLockedError):
        manager.set_lens_position(6.4)
    with pytest.raises(camera_module.FocusLockedError):
        manager.autofocus()
    assert backend.lens_writes == []
    assert manager.focus_status() == {"locked": True, "lens_position": 6.3}
    assert load_settings()["FocusConfirmed"] is True


def test_after_unlocking_the_lens_moves_again() -> None:
    manager = CameraManager(SyntheticBackend())
    manager.set_lens_position(6.3)
    manager.lock_focus()
    manager.unlock_focus()

    manager.set_lens_position(6.4)
    assert manager.get_lens_position() == pytest.approx(6.4)


# --- Focus confirmation persists across a restart (Aaron, 2026-09-28) -- verified for real on
# hardware: a kill+relaunch restart, sharpness score at the same LensPosition matched within 2%
# of its pre-restart value, so replaying the same number really does return the same focus.


def test_camera_manager_lock_focus_persists() -> None:
    manager = CameraManager(SyntheticBackend())
    manager.set_lens_position(6.3)
    manager.lock_focus()
    assert load_settings()["FocusConfirmed"] is True
    assert load_settings()["FocusConfirmedLensPosition"] == 6.3


def test_camera_manager_unlock_focus_persists() -> None:
    manager = CameraManager(SyntheticBackend())
    manager.set_lens_position(6.3)
    manager.lock_focus()
    manager.unlock_focus()
    assert load_settings()["FocusConfirmed"] is False


def test_camera_manager_restores_focus_confirmation_when_position_still_matches() -> None:
    from npec_rig.settings import save_setting

    save_setting("LensPosition", 6.3)
    save_setting("FocusConfirmed", True)
    save_setting("FocusConfirmedLensPosition", 6.3)

    manager = CameraManager(SyntheticBackend())
    assert manager.focus_status() == {"locked": True, "lens_position": 6.3}


def test_camera_manager_does_not_restore_focus_confirmation_when_position_mismatches() -> None:
    # Something moved the lens since the last confirm (or the two values were never in sync) --
    # the mismatch is exactly the case a restored confirmation must not be trusted for.
    from npec_rig.settings import save_setting

    save_setting("LensPosition", 3.0)
    save_setting("FocusConfirmed", True)
    save_setting("FocusConfirmedLensPosition", 6.3)

    manager = CameraManager(SyntheticBackend())
    assert manager.focus_status() == {"locked": False, "lens_position": None}


def test_camera_manager_does_not_restore_focus_confirmation_when_never_confirmed() -> None:
    from npec_rig.settings import save_setting

    save_setting("LensPosition", 6.3)
    # No FocusConfirmed key at all -- the common case (fresh rig, or focus never locked).

    manager = CameraManager(SyntheticBackend())
    assert manager.focus_status() == {"locked": False, "lens_position": None}


def test_camera_manager_peaking_toggle() -> None:
    manager = CameraManager(SyntheticBackend())
    assert manager.get_peaking() == {"enabled": False}

    assert manager.set_peaking(True) == {"enabled": True}
    assert manager.get_peaking() == {"enabled": True}

    # Peaking on a flat synthetic frame shouldn't error and should still produce a JPEG —
    # SyntheticBackend has no real edges, so the overlay is a no-op here, but the plumbing
    # (roi_crop_jpeg calling peaking_overlay when enabled) is what's under test.
    jpeg = manager.roi_crop_jpeg()
    assert jpeg[:2] == b"\xff\xd8"

    assert manager.set_peaking(False) == {"enabled": False}


def test_camera_manager_autofocus() -> None:
    manager = CameraManager(SyntheticBackend())
    result = manager.autofocus()
    assert result == {
        "success": True, "lens_position": SIMULATED_AUTOFOCUS_POSITION, "timed_out": None
    }
    assert manager.get_lens_position() == SIMULATED_AUTOFOCUS_POSITION


def test_synthetic_backend_controls_round_trip() -> None:
    backend = SyntheticBackend()
    assert backend.available_controls() == SYNTHETIC_CONTROL_RANGES
    assert backend.get_controls()["AnalogueGain"] == SYNTHETIC_CONTROL_RANGES["AnalogueGain"][2]

    # AnalogueGain only takes effect while AE is off — see set_control's guard.
    backend.set_control("AeEnable", False)
    backend.set_control("AnalogueGain", 4.0)
    assert backend.get_controls()["AnalogueGain"] == 4.0

    # LensPosition is tracked the same way through set_lens_position and set_control —
    # single source of truth, not two copies of the state.
    backend.set_control("LensPosition", 6.3)
    assert backend.get_lens_position() == 6.3


def test_camera_manager_set_control_persists_and_returns_current_values() -> None:
    manager = CameraManager(SyntheticBackend())
    manager.set_control("AeEnable", False)
    values = manager.set_control("AnalogueGain", 4.0)
    assert values["AnalogueGain"] == 4.0
    assert load_settings()["AnalogueGain"] == 4.0


def test_camera_manager_loads_persisted_settings_on_construction() -> None:
    from npec_rig.settings import save_setting

    save_setting("AeEnable", False)
    save_setting("AnalogueGain", 8.0)
    save_setting("LensPosition", 6.3)

    manager = CameraManager(SyntheticBackend())
    assert manager.get_controls()["AnalogueGain"] == 8.0
    assert manager.get_lens_position() == 6.3


def test_camera_manager_set_lens_position_persists() -> None:
    manager = CameraManager(SyntheticBackend())
    manager.set_lens_position(6.3)
    assert load_settings()["LensPosition"] == 6.3


def test_apply_persisted_settings_applies_ae_enable_before_dependent_controls() -> None:
    # On real hardware, AnalogueGain/ExposureTime writes are silently overridden by an active
    # auto-exposure algorithm — confirmed against the camera, not assumed. SyntheticBackend
    # doesn't model that interaction, so this locks in the *order* controls are applied in,
    # which is what actually avoids the race, rather than the hardware behavior itself.
    from npec_rig.settings import save_setting

    save_setting("AnalogueGain", 4.0)
    save_setting("AeEnable", False)

    calls: list[str] = []
    backend = SyntheticBackend()
    original_set_control = backend.set_control
    backend.set_control = lambda name, value: (calls.append(name), original_set_control(name, value))[1]

    CameraManager(backend)

    assert calls.index("AeEnable") < calls.index("AnalogueGain")


def test_apply_persisted_settings_does_not_replay_stale_manual_exposure_when_ae_is_on() -> None:
    # A persisted ExposureTime/AnalogueGain is only meaningful when AE was off when it was
    # saved. Replaying it on top of AeEnable=True re-arms picamera2's manual-exposure latch on
    # every restart — confirmed against a real stale value found in this rig's own DB.
    from npec_rig.settings import save_setting

    save_setting("AeEnable", True)
    save_setting("ExposureTime", 3064701)
    save_setting("AnalogueGain", 1.0)

    manager = CameraManager(SyntheticBackend())

    assert manager.get_controls()["AeEnable"] is True
    assert manager.get_controls()["ExposureTime"] == SYNTHETIC_CONTROL_RANGES["ExposureTime"][2]
    assert manager.get_controls()["AnalogueGain"] == SYNTHETIC_CONTROL_RANGES["AnalogueGain"][2]


def test_apply_persisted_settings_does_not_replay_stale_manual_exposure_when_ae_never_persisted() -> None:
    # AeEnable defaults on (see _apply_persisted_settings' own comment) when nothing ever wrote
    # it explicitly — e.g. only the exposure slider was ever touched. A missing persisted key
    # must not be treated as "AE is off": that was the exact gap a first version of this fix had.
    from npec_rig.settings import save_setting

    save_setting("ExposureTime", 3064701)
    save_setting("AnalogueGain", 1.0)

    manager = CameraManager(SyntheticBackend())

    assert manager.get_controls()["AeEnable"] is True
    assert manager.get_controls()["ExposureTime"] == SYNTHETIC_CONTROL_RANGES["ExposureTime"][2]


def test_set_control_ignores_manual_exposure_write_while_ae_is_on() -> None:
    # Guarded once, in the backend, so every caller (HTTP endpoint, persisted-settings replay,
    # the post-full-res-capture restore, a stale browser tab with sliders still enabled) is
    # covered by one rule instead of each needing to independently know it.
    backend = SyntheticBackend()
    backend.set_control("AeEnable", True)

    backend.set_control("ExposureTime", 3064701)

    assert backend.get_controls()["ExposureTime"] == SYNTHETIC_CONTROL_RANGES["ExposureTime"][2]


def test_apply_persisted_settings_replays_manual_exposure_when_ae_is_off() -> None:
    from npec_rig.settings import save_setting

    save_setting("AeEnable", False)
    save_setting("ExposureTime", 20000)
    save_setting("AnalogueGain", 4.0)

    manager = CameraManager(SyntheticBackend())

    assert manager.get_controls()["ExposureTime"] == 20000
    assert manager.get_controls()["AnalogueGain"] == 4.0
