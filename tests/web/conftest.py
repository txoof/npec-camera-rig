"""Fixtures for every web test: the synthetic camera, a Pi up past the cold-start window,
and the calibration readiness gate open by default."""

import pytest

import npec_rig.routes.calibration as calibration_routes
from npec_rig import captures
from npec_rig.camera import CameraManager, SyntheticBackend


@pytest.fixture(autouse=True)
def pi_up_past_the_cold_start_window(monkeypatch: pytest.MonkeyPatch) -> None:
    # Photos taken inside the cold-start window are flagged and validation rounds held back, so
    # the tests must not depend on how long the machine running them has been up.
    monkeypatch.setattr(captures, "read_uptime_s", lambda: captures.COLD_START_WINDOW_S + 1000)
    monkeypatch.setattr(captures, "_app_start", None)


@pytest.fixture(autouse=True)
def synthetic_camera() -> None:
    CameraManager.set_instance(CameraManager(SyntheticBackend()))


@pytest.fixture(autouse=True)
def calibration_gate_open_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Almost every /calibration/run test in these files is about calibration's own mechanics
    (tag size defaults, promote, table dims, history...), not the focus-lock/corner-tag
    readiness gate, and most use only 2 corner tags (`_CORNER_TAGS`) since that's already
    enough for a corner baseline -- fewer than the gate's own 4-tag minimum. Default the gate
    open so none of them need a real lock or a 4-tag fixture; the dedicated gate tests below
    restore the real function to exercise it properly."""
    monkeypatch.setattr(
        calibration_routes,
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
