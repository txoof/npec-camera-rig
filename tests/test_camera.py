import numpy as np
import pytest

from npec_rig.camera import (
    DEFAULT_LENS_POSITION,
    PEAKING_COLOR,
    SENSOR_METADATA_FIELDS,
    SIMULATED_AUTOFOCUS_POSITION,
    SYNTHETIC_CONTROL_RANGES,
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


def test_camera_manager_lock_and_unlock_focus() -> None:
    manager = CameraManager(SyntheticBackend())
    assert manager.focus_status() == {"locked": False, "lens_position": None}

    manager.set_lens_position(6.3)
    status = manager.lock_focus()
    assert status == {"locked": True, "lens_position": 6.3}
    assert manager.focus_status() == status

    status = manager.unlock_focus()
    assert status == {"locked": False, "lens_position": None}


def test_camera_manager_lock_is_cleared_by_a_later_manual_move() -> None:
    # A lock only means something if a later, unconfirmed move can't hide behind it (TODO.md,
    # "Give Lock focus a real function") -- invalidate on change, no tolerance comparison needed.
    manager = CameraManager(SyntheticBackend())
    manager.set_lens_position(6.3)
    manager.lock_focus()
    assert manager.focus_status()["locked"] is True

    manager.set_lens_position(6.4)
    assert manager.focus_status() == {"locked": False, "lens_position": None}


def test_camera_manager_lock_is_cleared_by_autofocus() -> None:
    manager = CameraManager(SyntheticBackend())
    manager.set_lens_position(6.3)
    manager.lock_focus()
    assert manager.focus_status()["locked"] is True

    manager.autofocus()
    assert manager.focus_status() == {"locked": False, "lens_position": None}


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


def test_camera_manager_set_lens_position_clears_persisted_confirmation() -> None:
    manager = CameraManager(SyntheticBackend())
    manager.set_lens_position(6.3)
    manager.lock_focus()

    manager.set_lens_position(6.4)
    assert load_settings()["FocusConfirmed"] is False


def test_camera_manager_autofocus_clears_persisted_confirmation() -> None:
    manager = CameraManager(SyntheticBackend())
    manager.set_lens_position(6.3)
    manager.lock_focus()

    manager.autofocus()
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
    assert result == {"success": True, "lens_position": SIMULATED_AUTOFOCUS_POSITION}
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
