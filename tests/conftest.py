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
    else:
        # Set for the whole run at module load (below); a hardware test alone goes without it.
        monkeypatch.delenv("NPEC_RIG_SYNTHETIC_CAMERA", raising=False)


@pytest.fixture(autouse=True)
def _fresh_camera_manager(request: pytest.FixtureRequest):
    """Each test starts with a new default camera, as it does with a fresh DB. A test that locks
    focus and leaves it locked must not decide what a later test sees: with tests run in parallel
    (pytest -n), the order changes from run to run (#169). Not for hardware tests: dropping a real
    camera without closing it would leave the device held."""
    if "hardware" in request.keywords:
        yield
        return
    from npec_rig.camera import CameraManager

    CameraManager.set_instance(None)
    yield
    CameraManager.set_instance(None)


@pytest.hookimpl(tryfirst=True)
def pytest_cmdline_main(config: pytest.Config) -> None:
    """A bare `pytest` (the unit tier, every test) runs on the Pi's 4 cores: 20 s serially, about
    12 s in parallel (#169). Only then: the other tiers use the one camera or decode 64MP frames,
    and four at once would fight over the camera or run out of memory. `-n 0` runs serially."""
    if (
        config.pluginmanager.hasplugin("xdist")
        and config.option.numprocesses is None
        and config.option.markexpr == "unit"
        and config.args_source == pytest.Config.ArgsSource.TESTPATHS
        and "PYTEST_XDIST_WORKER" not in os.environ
    ):
        config.option.numprocesses = 4
        config.option.dist = "worksteal"


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

# The database and derived folder are set per test (isolated_settings_db), and monkeypatch removes them when the
# test ends. A thread that outlives its test (the app's scheduler or tray reader, stopped without
# waiting) then falls back to these, never to /var/lib/npec-rig: on 2026-10-21 one such thread
# migrated the live rig.db (#222).
_test_fallback_dir = tempfile.mkdtemp(prefix="npec-rig-tests-fallback-")
os.environ["NPEC_RIG_DB_PATH"] = os.path.join(_test_fallback_dir, "rig.db")
os.environ["NPEC_RIG_DERIVED_DIR"] = os.path.join(_test_fallback_dir, "derived")
atexit.register(shutil.rmtree, _test_fallback_dir, ignore_errors=True)
# Likewise the camera: a scheduler thread left over from a test, during a running experiment in
# the live rig.db, must never reach the real camera.
os.environ["NPEC_RIG_SYNTHETIC_CAMERA"] = "1"


@pytest.fixture(autouse=True)
def isolated_settings_db(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    # A fresh DB per test — CameraManager loads persisted settings on construction, so sharing
    # one DB across tests would leak state between them.
    monkeypatch.setenv("NPEC_RIG_DB_PATH", str(tmp_path / "rig.db"))
    # Derived images (images.py) go with the per-test DB that indexes them.
    monkeypatch.setenv("NPEC_RIG_DERIVED_DIR", str(tmp_path / "derived"))
