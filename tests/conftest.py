import atexit
import os
import re
import shutil
import tempfile

import pytest

# Tests read the real free space of the disk their temporary files are on: the time lapse video
# check and the About page refuse below health.DISK_YELLOW_BYTES (5 GB, #512). pytest puts
# tmp_path under the system temp folder, and on the controller that is a 2 GB tmpfs, so 21 tests
# failed there although / had 41 GB free (#543). When the system temp folder has less than this
# free, temporary files go to a folder under the home directory instead. 10 GB is twice the
# 5 GB floor, a test setup choice with room for a video, not a measurement. This must run before
# anything calls tempfile (the mkdtemp call below) and before pytest makes its base folder.
_MIN_TEMP_FREE_BYTES = 10_000_000_000
if shutil.disk_usage(tempfile.gettempdir()).free < _MIN_TEMP_FREE_BYTES:
    _roomier_temp_dir = os.path.join(os.path.expanduser("~"), ".cache", "npec-rig-tests-tmp")
    try:
        os.makedirs(_roomier_temp_dir, exist_ok=True)
    except OSError:
        pass  # No such folder: keep the system one and let the disk tests say why they fail.
    else:
        tempfile.tempdir = _roomier_temp_dir


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
    """A bare `pytest` (the unit tier, every test) runs on 4 cores. Measured 2026-11-26 on an
    8-core/16-thread AMD Ryzen 7 5700X: 151 s serially, 47 s in parallel, 1067 tests. Before #547
    the same suite was 254 s and 83 s. On the Arm64 CI runner (#546), 50 s. The Pi
    controller is slower still and was over 300 s in parallel before #547; it has not been
    re-measured since, so no Pi figure is quoted here. The 20 s and
    12 s of #169 were measured when tests/ was 5,565 lines, a third of today's, and were stale by
    13x and 7.4x when #547 replaced them. Only then: the other tiers use the one camera or decode
    64MP frames, and four at once would fight over the camera or run out of memory. `-n 0` runs
    serially."""
    if (
        config.pluginmanager.hasplugin("xdist")
        and config.option.numprocesses is None
        # Any selection of the unit tier, not the exact string: the default became
        # `unit and not timing` when the `timing` marker was added, an exact match stopped
        # recognising it, and the suite silently ran serially -- 150 s against 50 s on x86 (#576).
        and config.option.markexpr.startswith("unit")
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
#
# All four folders live in one folder per run, named with the run's process ID. A run that is
# killed (timeout, out of memory, kill -9) skips its exit hook and leaves that folder, so each
# run first removes the folders of runs whose process has gone (#558). A folder of a run that is
# still going, in this or another session, is left alone, so no time limit is needed. Made here,
# at module load, and not in pytest's own temp folder: that folder exists only after pytest has
# started, and an import of app.py before it would read /var/lib/npec-rig.
_RUN_DIR_PREFIX = "npec-rig-tests-"


def _remove_folders_of_dead_runs(root: str) -> None:
    try:
        names = os.listdir(root)
    except OSError:
        return
    for name in names:
        match = re.match(rf"{_RUN_DIR_PREFIX}(\d+)-", name)
        if match is None:
            continue
        try:
            os.kill(int(match.group(1)), 0)  # signal 0 only asks whether the process exists
        except ProcessLookupError:
            shutil.rmtree(os.path.join(root, name), ignore_errors=True)
        except PermissionError:
            pass  # a process of another user: it is still running
        except OverflowError:
            pass  # a name that is not one of ours: a number too large for a process ID


_remove_folders_of_dead_runs(tempfile.gettempdir())
_test_run_dir = tempfile.mkdtemp(prefix=f"{_RUN_DIR_PREFIX}{os.getpid()}-")
atexit.register(shutil.rmtree, _test_run_dir, ignore_errors=True)


def _make_test_dir(name: str) -> str:
    path = os.path.join(_test_run_dir, name)
    os.makedirs(path)
    return path


os.environ["NPEC_RIG_PHOTOS_DIR"] = _make_test_dir("photos")
os.environ["NPEC_RIG_EXPERIMENTS_DIR"] = _make_test_dir("experiments")
os.environ["NPEC_RIG_CALIBRATION_DIR"] = _make_test_dir("calibration")

# The database and derived folder are set per test (isolated_settings_db), and monkeypatch removes them when the
# test ends. A thread that outlives its test (the app's scheduler or tray reader, stopped without
# waiting) then falls back to these, never to /var/lib/npec-rig: on 2026-10-21 one such thread
# migrated the live rig.db (#222).
_test_fallback_dir = _make_test_dir("fallback")
os.environ["NPEC_RIG_DB_PATH"] = os.path.join(_test_fallback_dir, "rig.db")
os.environ["NPEC_RIG_DERIVED_DIR"] = os.path.join(_test_fallback_dir, "derived")
os.environ["NPEC_RIG_MASKS_DIR"] = os.path.join(_test_fallback_dir, "masks")
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
    # Plant masks (segmentation.py) likewise.
    monkeypatch.setenv("NPEC_RIG_MASKS_DIR", str(tmp_path / "masks"))


# How long a test's teardown waits for a background thread it started to end. A reader asked to
# stop ends within one POLL_S of finishing the photo it is on; this only has to cover the photo,
# which is a full-size decode and a segmentation. Absolute, in whole seconds, because it is real
# work on an unknown machine, and it is a backstop: the usual wait is milliseconds (#576).
_THREAD_HANDOVER_S = 30.0


def _started_by_a_test(name: str) -> bool:
    """Whether a thread of this name holds rig.db connections of its own and so must not outlive
    the test that started it. The scheduler and the tray reader are started by `app.py`'s
    lifespan; a Reprocess run (`tray_readings`) and an export (`exports`) are started by a
    request and end when their work runs out, but both write to rig.db the whole way through, so
    one still running when the next test begins is on that test's database (/code-review on
    #576)."""
    return name in ("tray-reader", "scheduler", "reprocess") or name.startswith("export-")


@pytest.fixture(autouse=True)
def _no_background_thread_outlives_its_test():
    """No scheduler or tray reader started by a test is still running when the next one starts.

    `app.py`'s lifespan stops both with `stop(timeout_s=0)`: the thread is asked to stop and not
    waited for, which is right in production, where the process is on its way out anyway. Under
    pytest the process does not exit. The next test starts, `isolated_settings_db` points
    `NPEC_RIG_DB_PATH` at that test's own file, and `database._connect` looks `db_path()` up fresh
    on every query -- so a reader left over from an earlier test goes on polling, against the new
    test's database.

    That is not only noise. `lock_held(readers_too=True)` (three tests in `test_tray_readings.py`)
    switches rig.db out of WAL to make readers wait too, and the switch needs the file to itself:
    a leftover reader's open connection makes it raise `sqlite3.OperationalError: database is
    locked` before the lock is ever taken. Measured 2026-11-27 on x86, 8 full runs of `pytest` at
    `origin/main` (8e48548): 5 red, every one of them this (#576).

    Joining is all that is needed, because every one of these threads either has already been
    asked to stop (the lifespan and the tests both set the stop event) or ends by itself when the
    work it was given runs out. A thread that does neither sits here until the backstop and then
    fails the test that left it, by name, which is what should happen: it would otherwise fail
    some later test instead.

    The threads already running are held as objects, not as `ident`s. A thread's `ident` is
    reused: it is freed when that thread ends and CPython hands the same number to a later one
    (six short-lived threads in a row shared one `ident` on the controller). A thread alive at
    setup that ends during the test would free its number for the reader or scheduler the test
    then starts, and keying on the number would skip exactly the leftover this exists to catch
    (/code-review on #576)."""
    import threading
    import time

    before = set(threading.enumerate())  # the objects: `ident` is reused, see above
    yield
    deadline = time.monotonic() + _THREAD_HANDOVER_S
    left_running = []
    for thread in threading.enumerate():
        if thread in before or not _started_by_a_test(thread.name):
            continue
        thread.join(max(0.0, deadline - time.monotonic()))
        if thread.is_alive():
            left_running.append(thread.name)
    assert not left_running, (
        f"still running {_THREAD_HANDOVER_S} s after the test ended: {', '.join(left_running)}. "
        "A thread that outlives its test reads and writes the next test's rig.db.")
