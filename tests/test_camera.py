import numpy as np
import pytest

from npec_rig.camera import (
    DEFAULT_LENS_POSITION,
    PEAKING_COLOR,
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
    assert isinstance(metadata, dict)


def test_array_to_jpeg_produces_jpeg_bytes() -> None:
    frame = SyntheticBackend(width=16, height=16).capture_array()
    data = array_to_jpeg(frame)
    assert data[:2] == b"\xff\xd8"


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
    score = manager.focus_score()
    assert isinstance(score, float)
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

    backend.set_control("AnalogueGain", 4.0)
    assert backend.get_controls()["AnalogueGain"] == 4.0

    # LensPosition is tracked the same way through set_lens_position and set_control —
    # single source of truth, not two copies of the state.
    backend.set_control("LensPosition", 6.3)
    assert backend.get_lens_position() == 6.3


def test_camera_manager_set_control_persists_and_returns_current_values() -> None:
    manager = CameraManager(SyntheticBackend())
    values = manager.set_control("AnalogueGain", 4.0)
    assert values["AnalogueGain"] == 4.0
    assert load_settings()["AnalogueGain"] == 4.0


def test_camera_manager_loads_persisted_settings_on_construction() -> None:
    from npec_rig.settings import save_setting

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
