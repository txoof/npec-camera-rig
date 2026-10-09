import atexit
import os
import shutil
import tempfile

import pytest


def _camera_hardware_present() -> bool:
    """True if picamera2 can see a real camera, without opening/locking the device."""
    try:
        from picamera2 import Picamera2
    except ImportError:
        return False
    try:
        return bool(Picamera2.global_camera_info())
    except Exception:
        return False


@pytest.fixture(autouse=True)
def _no_lens_drive_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    """The lens drive path pauses and polls for a real camera; the synthetic one answers at
    once, so tests run it without the waits (see camera.LENS_APPROACH_OFFSET)."""
    import npec_rig.camera as camera_module

    monkeypatch.setattr(camera_module, "LENS_APPROACH_PAUSE_S", 0.0)
    monkeypatch.setattr(camera_module, "LENS_POLL_INTERVAL_S", 0.0)


@pytest.fixture(autouse=True)
def _synthetic_camera_unless_hardware(request: pytest.FixtureRequest, monkeypatch) -> None:
    """Only a hardware-marked test may reach the real camera. Any other test that builds the
    default camera (CameraManager.instance) gets the synthetic one: since #51 a real camera that
    does not open (a live server holds it) is a reported fault, not a silent switch to synthetic,
    so without this such a test would try the camera and fail."""
    if "hardware" not in request.keywords:
        monkeypatch.setenv("NPEC_RIG_SYNTHETIC_CAMERA", "1")


def _hailo_present() -> bool:
    return shutil.which("hailortcli") is not None


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip hardware/hailo-marked tests when the device isn't there, instead of hard-failing.

    `trylast` runs this after pytest's own `-m` marker filtering, so `items` already reflects
    deselection. Only probes the real camera/accelerator if a hardware/hailo-marked test actually
    survived that filtering -- a plain `pytest` (unit tier, the default) never touches the camera,
    so it can't collide with a live server using it.
    """
    hardware_items = [item for item in items if "hardware" in item.keywords]
    hailo_items = [item for item in items if "hailo" in item.keywords]

    if hardware_items and not _camera_hardware_present():
        skip_hardware = pytest.mark.skip(reason="no camera hardware detected")
        for item in hardware_items:
            item.add_marker(skip_hardware)

    if hailo_items and not _hailo_present():
        skip_hailo = pytest.mark.skip(reason="no Hailo accelerator detected")
        for item in hailo_items:
            item.add_marker(skip_hailo)

# app.py reads NPEC_RIG_PHOTOS_DIR, NPEC_RIG_EXPERIMENTS_DIR and NPEC_RIG_CALIBRATION_DIR at *import* time (each mounts a
# StaticFiles directory as a module-level side effect), before any per-test fixture can run — so
# this has to be set here, at conftest module load, not in a fixture. Unconditional (not
# setdefault): a real value already in the environment must not cause tests to write into
# /var/lib/npec-rig/{rig,experiments,calibration}.
_test_photos_dir = tempfile.mkdtemp(prefix="npec-rig-tests-")
os.environ["NPEC_RIG_PHOTOS_DIR"] = _test_photos_dir
atexit.register(shutil.rmtree, _test_photos_dir, ignore_errors=True)

_test_experiments_dir = tempfile.mkdtemp(prefix="npec-rig-tests-experiments-")
os.environ["NPEC_RIG_EXPERIMENTS_DIR"] = _test_experiments_dir
atexit.register(shutil.rmtree, _test_experiments_dir, ignore_errors=True)

_test_calibration_dir = tempfile.mkdtemp(prefix="npec-rig-tests-calibration-")
os.environ["NPEC_RIG_CALIBRATION_DIR"] = _test_calibration_dir
atexit.register(shutil.rmtree, _test_calibration_dir, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_settings_db(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    # A fresh DB per test — CameraManager loads persisted settings on construction, so sharing
    # one DB across tests would leak state between them.
    monkeypatch.setenv("NPEC_RIG_DB_PATH", str(tmp_path / "rig.db"))
    # Derived images (images.py) go with the per-test DB that indexes them.
    monkeypatch.setenv("NPEC_RIG_DERIVED_DIR", str(tmp_path / "derived"))
