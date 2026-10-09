"""The camera in its own program (#51, option (b), decided by Aaron 2026-10-08).

Every camera call used to wait for the camera with no time limit, holding the one camera lock: a
call that never returned stopped every photo, with nothing shown in the browser. Here the camera
code (`Picamera2Backend`, unchanged) runs in a separate process, and `ProcessBackend` stands in
for it in the app, with the same interface (`CameraBackend`). Each call has a time limit. When one
runs out, the camera program is ended and a new one started; the app keeps running, the fault is
recorded (health.py) and photos after it are flagged (captures.take_photo). A camera that cannot
be reopened is reported, never replaced by synthetic frames.

What this cannot fix: if the camera driver in the Linux kernel hangs, the camera cannot be
reopened until the Pi restarts. Then the state stays `failed_to_reopen` with `reboot_needed`, and
the rig keeps trying. The rig never reboots itself (#82).
"""

from __future__ import annotations

import ctypes
import itertools
import logging
import multiprocessing
import os
import pickle
import queue
import signal
import threading
from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path

import numpy as np

from npec_rig import health
from npec_rig.camera import (
    AUTOFOCUS_TIMEOUT_S,
    CameraBackend,
    CameraStuckError,
    CameraUnavailableError,
)
from npec_rig.settings import db_path

logger = logging.getLogger(__name__)

# Time limits per call. Decisions, not measurements: several times the longest call measured on
# the rig (a full-res photo 2.7 to 2.8 s, metrology-log 8.2 step 3; Reset camera 2.3 to 2.5 s,
# #49), because a false alarm costs more than a late one: it restarts the camera, which moves the
# lens, and flags an hour of photos (health.CAMERA_FAULT_WINDOW_S), while a late one costs a photo.
# Autofocus stays above the backend's own 60 s limit, so its own cancel runs first.
CALL_TIME_LIMITS_S = {
    "capture_full_res": 30.0,
    "autofocus": AUTOFOCUS_TIMEOUT_S + 30.0,
    "reset": 20.0,
    "prepare_lens": 20.0,
}
DEFAULT_CALL_TIME_LIMIT_S = 10.0  # frames, lens and control reads and writes
OPEN_TIME_LIMIT_S = 30.0  # start the program and open the camera
KILL_WAIT_S = 5.0  # for an ended program to be gone before a new one opens the camera
REOPEN_RETRY_S = 60.0  # between attempts to reopen a camera that did not open
FAILED_OPENS_BEFORE_REBOOT = 3  # then `reboot_needed` is reported; the attempts go on

# Frames of at least this size go through a file in shared memory, not the pipe. A full-res
# still is about 190 MB.
FRAME_FILE_MIN_BYTES = 1 << 20
FRAME_DIR = Path("/dev/shm")
FRAME_PREFIX = "npec-cam-"

_METHODS = frozenset(
    {
        "prepare_lens",
        "reset",
        "capture_array",
        "capture_preview_array",
        "capture_full_res",
        "set_lens_position",
        "get_lens_position",
        "autofocus",
        "available_controls",
        "get_controls",
        "set_control",
    }
)

_PR_SET_PDEATHSIG = 1


# The camera program. Everything below up to ProcessBackend runs in the child process.


def _die_with_parent(parent_pid: int) -> None:
    """End this program when the app ends, even by SIGKILL, so it never keeps the camera from
    the next app start. The signal follows the thread that started this program, which is why
    ProcessBackend starts every one from the same long-lived thread."""
    try:
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(_PR_SET_PDEATHSIG, signal.SIGKILL)
    except (OSError, AttributeError):
        logger.warning("Could not tie the camera program to the app")
    if os.getppid() != parent_pid:
        os._exit(0)  # the app already ended


def _start_time(pid: int) -> str | None:
    """The process's start time in clock ticks since boot (/proc/<pid>/stat, field 22), so a PID
    reused by another program is never mistaken for ours."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    return stat.rsplit(")", 1)[1].split()[19]


def _make_backend(name: str, kwargs: dict) -> CameraBackend:
    from npec_rig.camera import Picamera2Backend, SyntheticBackend

    if name == "picamera2":
        return Picamera2Backend()
    if name == "synthetic":
        return SyntheticBackend(**kwargs)
    raise ValueError(f"unknown camera backend {name!r}")


def _encode(value: object, req_id: int, index: int = 0) -> tuple:
    if isinstance(value, np.ndarray) and value.nbytes >= FRAME_FILE_MIN_BYTES:
        path = FRAME_DIR / f"{FRAME_PREFIX}{os.getpid()}-{req_id}-{index}.raw"
        value.tofile(path)
        return ("frame", str(path), value.shape, value.dtype.str)
    if isinstance(value, tuple):
        return ("tuple", tuple(_encode(v, req_id, i) for i, v in enumerate(value)))
    return ("value", value)


def _picklable(exc: BaseException) -> BaseException:
    """`exc` if it survives the trip to the app intact, otherwise a RuntimeError with its text."""
    try:
        pickle.loads(pickle.dumps(exc))
        return exc
    except Exception:
        return RuntimeError(f"{type(exc).__name__}: {exc}")


def _child_main(conn, parent_pid: int, name: str, kwargs: dict, pid_file: str | None) -> None:
    _die_with_parent(parent_pid)
    if pid_file:
        try:
            Path(pid_file).write_text(f"{os.getpid()} {_start_time(os.getpid())}")
        except OSError:
            pass
    try:
        backend = _make_backend(name, kwargs)
    except ImportError as exc:
        conn.send(("missing", str(exc)))
        return
    except BaseException as exc:
        conn.send(("open_failed", f"{type(exc).__name__}: {exc}"))
        return
    conn.send(("ready", None))
    while True:
        try:
            req_id, method, args = conn.recv()
        except EOFError:
            return
        try:
            if method not in _METHODS:
                raise ValueError(f"not a camera call: {method!r}")
            result = getattr(backend, method)(*args)
            conn.send((req_id, "ok", _encode(result, req_id)))
        except Exception as exc:
            conn.send((req_id, "err", _picklable(exc)))


# The app side.


def _decode(payload: tuple) -> object:
    kind = payload[0]
    if kind == "frame":
        _, path, shape, dtype = payload
        try:
            return np.fromfile(path, dtype=np.dtype(dtype)).reshape(shape)
        finally:
            Path(path).unlink(missing_ok=True)
    if kind == "tuple":
        return tuple(_decode(p) for p in payload[1])
    return payload[1]


def _pid_alive(pid: int) -> bool:
    return Path(f"/proc/{pid}").exists()


def sweep_frame_files() -> None:
    """Remove frame files left by a camera program that no longer runs (ended mid-transfer). A
    file of a program still running belongs to another app on this Pi and is left alone."""
    if not FRAME_DIR.is_dir():
        return
    for path in FRAME_DIR.glob(f"{FRAME_PREFIX}*.raw"):
        try:
            pid = int(path.name[len(FRAME_PREFIX) :].split("-")[0])
        except ValueError:
            continue
        if not _pid_alive(pid):
            path.unlink(missing_ok=True)


def end_leftover_program(pid_file: Path) -> None:
    """End a camera program an earlier app left running, if the parent-death signal did not."""
    try:
        pid_text, started = pid_file.read_text().split()
        pid = int(pid_text)
    except (OSError, ValueError):
        return
    if pid != os.getpid() and _start_time(pid) == started:
        logger.warning("Ending camera program %d left by an earlier app", pid)
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


class _Launcher:
    """One long-lived thread that starts and ends every camera program. The parent-death signal
    (see _die_with_parent) fires when the starting thread ends, so a request thread, which the
    server ends when idle, must never start one."""

    def __init__(self) -> None:
        self._jobs: queue.Queue = queue.Queue()
        threading.Thread(target=self._run, name="camera-launcher", daemon=True).start()

    def _run(self) -> None:
        while True:
            fn, future = self._jobs.get()
            if fn is None:
                return
            try:
                future.set_result(fn())
            except BaseException as exc:
                logger.exception("camera launcher job failed")
                future.set_exception(exc)

    def submit(self, fn: Callable[[], object]) -> Future:
        future: Future = Future()
        self._jobs.put((fn, future))
        return future

    def stop(self) -> None:
        self._jobs.put((None, None))


class ProcessBackend(CameraBackend):
    """Stands in for a camera backend running in its own program. Raises ImportError when the
    camera software is not installed (camera._default_backend falls back to synthetic then);
    every other failure to open is reported in health.py and retried."""

    def __init__(
        self,
        backend_name: str = "picamera2",
        backend_kwargs: dict | None = None,
        time_limits: dict[str, float] | None = None,
        default_time_limit_s: float = DEFAULT_CALL_TIME_LIMIT_S,
        open_time_limit_s: float = OPEN_TIME_LIMIT_S,
        retry_s: float = REOPEN_RETRY_S,
    ) -> None:
        self._name = backend_name
        self._kwargs = dict(backend_kwargs or {})
        self._limits = {**CALL_TIME_LIMITS_S, **(time_limits or {})}
        self._default_limit = default_time_limit_s
        self._open_limit = open_time_limit_s
        self._retry_s = retry_s
        self._ctx = multiprocessing.get_context("spawn")  # never fork a threaded server
        self._pid_file = db_path().parent / "camera-process.pid"
        # One request at a time on the pipe, whatever lock the caller holds: not every backend
        # call is under CameraManager's _call_lock (_drive_lens_once, the settings replay).
        self._request_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._ids = itertools.count(1)
        self._proc = None
        self._conn = None
        self._ready = False
        self._unavailable = "The camera is starting."
        self._failed_opens = 0
        self._constructed = False
        self._closed = False
        self._restart_listener: Callable[[], None] | None = None
        self._retry_timer: threading.Timer | None = None
        self._launcher = _Launcher()
        sweep_frame_files()
        end_leftover_program(self._pid_file)
        outcome = self._launcher.submit(self._start).result()
        self._constructed = True
        if outcome == "missing":
            self.close()
            raise ImportError(self._unavailable)

    def set_restart_listener(self, listener: Callable[[], None]) -> None:
        """Called, on its own thread, each time a new camera program is ready after a fault or a
        failed open."""
        self._restart_listener = listener

    @property
    def pid(self) -> int | None:
        """The camera program's process ID, for a hang test on the rig (`kill -STOP <pid>`)."""
        proc = self._proc
        return proc.pid if proc is not None else None

    # Runs on the launcher thread.

    def _start(self) -> str:
        if self._closed:
            return "closed"
        parent_conn, child_conn = self._ctx.Pipe()
        proc = self._ctx.Process(
            target=_child_main,
            args=(child_conn, os.getpid(), self._name, self._kwargs, str(self._pid_file)),
            name="npec-camera",
            daemon=True,
        )
        proc.start()
        child_conn.close()
        kind, detail = "open_failed", f"the camera did not open within {self._open_limit:.0f} s"
        if parent_conn.poll(self._open_limit):
            try:
                kind, detail = parent_conn.recv()
            except EOFError:
                detail = "the camera program ended while opening the camera"
        if kind == "ready":
            with self._state_lock:
                self._proc, self._conn, self._ready = proc, parent_conn, True
            self._failed_opens = 0
            health.record_camera_state(health.CAMERA_OK)
            logger.info("camera program %d ready", proc.pid)
            if self._constructed and self._restart_listener is not None:
                threading.Thread(
                    target=self._restart_listener, name="camera-restore", daemon=True
                ).start()
            return "ready"
        parent_conn.close()
        if not self._end(proc):
            self._report_unkillable()
            return "failed"
        if kind == "missing" and not self._constructed:
            self._unavailable = f"No camera software installed: {detail}"
            return "missing"
        self._failed_opens += 1
        self._unavailable = (
            f"The camera could not be opened ({detail}). The rig tries again every "
            f"{self._retry_s:.0f} s. If this stays, the Pi needs a restart."
        )
        health.record_camera_state(
            health.CAMERA_FAILED_TO_REOPEN,
            self._unavailable,
            reboot_needed=self._failed_opens >= FAILED_OPENS_BEFORE_REBOOT,
        )
        self._schedule(self._start)
        return "failed"

    def _end(self, proc) -> bool:
        """End a camera program and wait until it is gone. False if it will not end, which happens
        when it is stuck inside the kernel driver."""
        if proc.is_alive():
            proc.kill()
        proc.join(KILL_WAIT_S)
        return not proc.is_alive()

    def _end_and_restart(self, proc, conn) -> str:
        if conn is not None:
            conn.close()
        if proc is not None and not self._end(proc):
            self._report_unkillable()
            self._schedule(lambda: self._end_and_restart(proc, None))
            return "failed"
        return self._start()

    def _report_unkillable(self) -> None:
        self._unavailable = (
            "The camera stopped responding and its program could not be ended, so the camera "
            "cannot be reopened. The Pi needs a restart."
        )
        health.record_camera_state(
            health.CAMERA_FAILED_TO_REOPEN, self._unavailable, reboot_needed=True
        )

    def _schedule(self, fn: Callable[[], object]) -> None:
        if self._closed:
            return
        timer = threading.Timer(self._retry_s, lambda: self._launcher.submit(fn))
        timer.daemon = True
        self._retry_timer = timer
        timer.start()

    # Runs on the caller's thread.

    def _fault(self, reason: str) -> CameraStuckError:
        with self._state_lock:
            proc, conn = self._proc, self._conn
            self._proc, self._conn, self._ready = None, None, False
        self._unavailable = (
            "The camera is restarting after it stopped responding. Try again in a minute."
        )
        health.record_camera_fault(reason)
        health.record_camera_state(
            health.CAMERA_RESTARTING, f"The camera stopped responding ({reason}); restarting it."
        )
        self._launcher.submit(lambda: self._end_and_restart(proc, conn))
        return CameraStuckError(
            f"The camera stopped responding ({reason}) and is being restarted. "
            "Try again in a minute."
        )

    def _call(self, method: str, *args: object) -> object:
        limit = self._limits.get(method, self._default_limit)
        with self._request_lock:
            with self._state_lock:
                conn, ready = self._conn, self._ready
            if not ready or conn is None:
                raise CameraUnavailableError(self._unavailable)
            req_id = next(self._ids)
            try:
                conn.send((req_id, method, args))
                if not conn.poll(limit):
                    raise self._fault(f"{method} did not finish within {limit:.0f} s")
                got_id, kind, payload = conn.recv()
            except (EOFError, OSError) as exc:
                raise self._fault(f"the camera program ended during {method}") from exc
            if got_id != req_id:
                raise self._fault(f"{method} got the answer to another call")
        if kind == "err":
            raise payload
        return _decode(payload)

    def close(self) -> None:
        """End the camera program (tests, app shutdown)."""
        self._closed = True
        if self._retry_timer is not None:
            self._retry_timer.cancel()
        with self._state_lock:
            proc, conn = self._proc, self._conn
            self._proc, self._conn, self._ready = None, None, False
        if conn is not None:
            conn.close()
        if proc is not None:
            self._end(proc)
        self._launcher.stop()

    # CameraBackend, forwarded.

    def prepare_lens(self) -> None:
        self._call("prepare_lens")

    def reset(self) -> None:
        self._call("reset")

    def capture_array(self) -> np.ndarray:
        return self._call("capture_array")

    def capture_preview_array(self) -> np.ndarray:
        return self._call("capture_preview_array")

    def capture_full_res(self) -> tuple[np.ndarray, dict]:
        return self._call("capture_full_res")

    def set_lens_position(self, value: float) -> None:
        self._call("set_lens_position", value)

    def get_lens_position(self) -> float:
        return self._call("get_lens_position")

    def autofocus(self) -> tuple[bool, float]:
        return self._call("autofocus")

    def available_controls(self) -> dict[str, tuple]:
        return self._call("available_controls")

    def get_controls(self) -> dict:
        return self._call("get_controls")

    def set_control(self, name: str, value: object) -> None:
        self._call("set_control", name, value)
