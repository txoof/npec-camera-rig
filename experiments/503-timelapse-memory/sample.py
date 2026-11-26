#!/usr/bin/env python3
"""Sample the memory of a time-lapse video job on the Pi (#503).

Standard library only, reads /proc only, never imports npec_rig.
See README.md. Exit status: 0 done, 2 video child never appeared, 3 aborted.
"""
import argparse
import csv
import os
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

KEYS = ("vmpeak", "vmhwm", "vmrss")
COLUMNS = (
    ["time_utc", "elapsed_s", "app_vmpeak_kb", "app_vmhwm_kb"]
    + ["child_" + k + "_kb" for k in KEYS]
    + ["ffmpeg_" + k + "_kb" for k in KEYS]
    + ["mem_total_kb", "mem_available_kb", "used_kb", "note"]
)
POLL_S = 0.25
ROW_EVERY = 4  # polls per CSV row, one row per second


# ---- /proc parsing -------------------------------------------------------

def read_status(pid):
    """VmPeak, VmHWM, VmRSS in kB and the state letter, or None if gone."""
    try:
        with open("/proc/%d/status" % pid) as f:
            text = f.read()
    except OSError:
        return None
    out = {"state": ""}
    for line in text.splitlines():
        name, _, rest = line.partition(":")
        if name == "State":
            out["state"] = rest.strip()[:1]
        elif name in ("VmPeak", "VmHWM", "VmRSS"):
            out[name.lower()] = int(rest.split()[0])
    return out


def read_meminfo():
    vals = {}
    with open("/proc/meminfo") as f:
        for line in f:
            name, _, rest = line.partition(":")
            if name in ("MemTotal", "MemAvailable"):
                vals[name] = int(rest.split()[0])
    return vals["MemTotal"], vals["MemAvailable"]


def read_stat(pid):
    """(comm, ppid) from /proc/<pid>/stat; comm may hold spaces and brackets."""
    try:
        with open("/proc/%d/stat" % pid) as f:
            text = f.read()
    except OSError:
        return None
    left, right = text.find("("), text.rfind(")")
    return text[left + 1:right], int(text[right + 2:].split()[1])


def read_cmdline(pid):
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as f:
            return f.read().replace(b"\0", b" ").decode("utf-8", "replace")
    except OSError:
        return ""


def list_pids():
    return [int(n) for n in os.listdir("/proc") if n.isdigit()]


def children_of(ppid):
    """Direct children of ppid, with their comm, by scanning /proc/*/stat."""
    found = []
    for pid in list_pids():
        st = read_stat(pid)
        if st and st[1] == ppid:
            found.append((pid, st[0]))
    return found


def is_alive(pid):
    st = read_status(pid)
    return st is not None and st["state"] != "Z"


# ---- finding the job's processes ------------------------------------------

def baseline_children(app_pid):
    return {pid for pid, _ in children_of(app_pid)}


def find_video_child(app_pid, baseline):
    """A child of the app with spawn_main in its cmdline, not in the baseline."""
    for pid, _ in children_of(app_pid):
        if pid not in baseline and "spawn_main" in read_cmdline(pid):
            return pid
    return None


def find_ffmpeg(video_pid):
    for pid, comm in children_of(video_pid):
        if comm == "ffmpeg":
            return pid
    return None


# ---- sampling ---------------------------------------------------------------

class Track:
    """Highest VmPeak/VmHWM seen and the last values read for one role."""

    def __init__(self):
        self.vals = {k: None for k in KEYS}
        self.pid = None

    def update(self, pid):
        if pid is None:
            return
        self.pid = pid
        st = read_status(pid)
        if st is None:
            return
        for k in KEYS:
            if k not in st:
                continue
            if k == "vmrss":
                self.vals[k] = st[k]
            else:
                self.vals[k] = max(self.vals[k] or 0, st[k])

    def get(self, k):
        v = self.vals[k]
        return "" if v is None else v


def make_row(t0, app, child, ffm, note=""):
    total, avail = read_meminfo()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return [
        now, "%.1f" % (time.monotonic() - t0), app.get("vmpeak"), app.get("vmhwm"),
        child.get("vmpeak"), child.get("vmhwm"), child.get("vmrss"),
        ffm.get("vmpeak"), ffm.get("vmhwm"), ffm.get("vmrss"),
        total, avail, total - avail, note,
    ]


def abort_reason(args):
    total, avail = read_meminfo()
    used_gib = (total - avail) / 1048576
    avail_gib = avail / 1048576
    if used_gib > args.abort_used_gib:
        return "used %.2f GiB > %.2f GiB" % (used_gib, args.abort_used_gib)
    if avail_gib < args.abort_avail_gib:
        return "available %.2f GiB < %.2f GiB" % (avail_gib, args.abort_avail_gib)
    return None


def terminate(pid, parent=None):
    """SIGTERM to pid, but only while its parent is still `parent` (when given), so a reused pid
    or a restarted camera process is never signalled by mistake."""
    if parent is not None:
        st = read_stat(pid)
        if st is None or st[1] != parent:
            return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


def run(args):
    if not is_alive(args.app_pid):
        print("app pid %d is not running" % args.app_pid, file=sys.stderr)
        return 2
    baseline = baseline_children(args.app_pid)
    stop = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.append(sig))
    app, child, ffm = Track(), Track(), Track()
    rows = 0
    min_avail = None
    t0 = time.monotonic()
    child_seen = False
    status = 0
    with open(args.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNS)

        def emit(note=""):
            nonlocal rows, min_avail
            w.writerow(make_row(t0, app, child, ffm, note))
            fh.flush()
            rows += 1

        poll = 0
        while True:
            poll += 1
            app.update(args.app_pid)
            if child.pid is None:
                child.pid = find_video_child(args.app_pid, baseline)
            child.update(child.pid)
            if child.pid is not None:
                child_seen = True
                found = find_ffmpeg(child.pid)
                if found is not None:
                    ffm.pid = found
                ffm.update(ffm.pid)
            avail = read_meminfo()[1]
            min_avail = avail if min_avail is None else min(min_avail, avail)

            reason = abort_reason(args)
            if reason:
                for pid, parent in ((ffm.pid, child.pid), (child.pid, args.app_pid)):
                    if pid is not None and is_alive(pid):
                        terminate(pid, parent)
                print("ABORT: " + reason, file=sys.stderr)
                emit("ABORT " + reason)
                status = 3
                break
            gone = child_seen and not is_alive(child.pid)
            elapsed = time.monotonic() - t0
            if stop or gone or elapsed > args.max_seconds:
                emit("")
                break
            if not child_seen and elapsed > args.wait_seconds:
                print("video child did not appear in %d s" % args.wait_seconds,
                      file=sys.stderr)
                status = 2
                break
            if poll % ROW_EVERY == 0:
                emit("")
            time.sleep(POLL_S)

    def peak(t, k):
        return t.vals[k] if t.vals[k] is not None else 0
    print("max app VmPeak %d VmHWM %d kB; child VmPeak %d VmHWM %d kB; "
          "ffmpeg VmPeak %d VmHWM %d kB; min MemAvailable %s kB; rows %d" % (
              peak(app, "vmpeak"), peak(app, "vmhwm"), peak(child, "vmpeak"),
              peak(child, "vmhwm"), peak(ffm, "vmpeak"), peak(ffm, "vmhwm"),
              min_avail, rows))
    return status


# ---- selftest ---------------------------------------------------------------

FAKE_APP = r"""
import subprocess, sys, os
cam = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "spawn_main"])
print("ready", flush=True)
sys.stdin.readline()
fake_ffmpeg, = sys.argv[1:]
vid_code = (
    "import os, subprocess, sys, time; b = bytearray(int(os.environ.get('ALLOC_MB', '50'))*1024*1024); "
    "b[::4096] = b'x' * len(b[::4096]); "
    "p = subprocess.Popen([sys.argv[1], '3']); time.sleep(3); p.wait()"
)
vid = subprocess.Popen([sys.executable, "-c", vid_code, fake_ffmpeg, "spawn_main"])
vid.wait()
import time; time.sleep(2)
cam.terminate()
"""


def selftest():
    selftest_case(abort=False)
    selftest_case(abort=True)
    selftest_kill()
    return 0


def selftest_kill():
    """The abort fires while the video child and ffmpeg are alive: both are killed, the app
    and the camera child are not."""
    with tempfile.TemporaryDirectory() as d:
        fake_ffmpeg = os.path.join(d, "ffmpeg")
        os.symlink("/bin/sleep", fake_ffmpeg)
        out = os.path.join(d, "out.csv")
        env = dict(os.environ, ALLOC_MB="400")
        app = subprocess.Popen([sys.executable, "-c", FAKE_APP, fake_ffmpeg], env=env,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            assert app.stdout.readline().strip() == "ready"
            cam = children_of(app.pid)[0][0]
            total, avail = read_meminfo()
            limit = (total - avail) / 1048576 + 0.2  # the 400 MB child pushes past this
            sampler = subprocess.Popen([sys.executable, os.path.abspath(__file__),
                                        "--app-pid", str(app.pid), "--out", out,
                                        "--abort-used-gib", "%.3f" % limit,
                                        "--abort-avail-gib", "0", "--wait-seconds", "20"],
                                       stdout=subprocess.PIPE, text=True)
            time.sleep(1.5)
            app.stdin.write("go\n")
            app.stdin.flush()
            summary, _ = sampler.communicate(timeout=40)
            assert sampler.returncode == 3, "sampler exit %s" % sampler.returncode
            time.sleep(0.5)
            assert app.poll() is None, "the app was killed"
            assert is_alive(cam), "the camera child was killed"
            left = [pid for pid, _ in children_of(app.pid) if pid != cam and is_alive(pid)]
            assert not left, "video child still alive: %s" % left
            with open(out) as f:
                rows = list(csv.DictReader(f))
            assert rows[-1]["note"].startswith("ABORT") and rows[-1]["child_vmhwm_kb"]
            print("selftest kill ok: video child and ffmpeg ended, app and camera child alive")
        finally:
            for pid, _ in children_of(app.pid):
                for sub, _ in children_of(pid):
                    terminate(sub)
                terminate(pid)
            app.kill()
            app.wait()


def selftest_case(abort):
    with tempfile.TemporaryDirectory() as d:
        fake_ffmpeg = os.path.join(d, "ffmpeg")
        os.symlink("/bin/sleep", fake_ffmpeg)
        out = os.path.join(d, "out.csv")
        app = subprocess.Popen([sys.executable, "-c", FAKE_APP, fake_ffmpeg],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            assert app.stdout.readline().strip() == "ready"
            sampler = subprocess.Popen([sys.executable, os.path.abspath(__file__),
                                        "--app-pid", str(app.pid), "--out", out,
                                        "--wait-seconds", "20", "--max-seconds", "60"]
                                       + (["--abort-avail-gib", "100000"] if abort
                                          else ["--abort-avail-gib", "0", "--abort-used-gib", "100000"]),
                                       stdout=subprocess.PIPE, text=True)
            time.sleep(1.5)
            app.stdin.write("go\n")
            app.stdin.flush()
            summary, _ = sampler.communicate(timeout=40)
            want = 3 if abort else 0
            assert sampler.returncode == want, "sampler exit %s" % sampler.returncode
        finally:
            for pid, _ in children_of(app.pid):
                for sub, _ in children_of(pid):
                    terminate(sub)
                terminate(pid)
            app.kill()
            app.wait()
        with open(out) as f:
            rows = list(csv.DictReader(f))
        print(summary.strip())
        if abort:
            assert rows[-1]["note"].startswith("ABORT"), "no ABORT note"
            print("selftest abort ok: %d rows, note %r" % (len(rows), rows[-1]["note"]))
            return
        hwm = max(int(r["child_vmhwm_kb"]) for r in rows if r["child_vmhwm_kb"])
        assert hwm > 40000, "child_vmhwm_kb %d too small" % hwm
        assert any(r["ffmpeg_vmhwm_kb"] for r in rows), "ffmpeg never seen"
        assert rows[-1]["child_vmhwm_kb"], "last row blank after child exit"
        assert rows[0]["child_vmhwm_kb"] == "" or len(rows) > 1
        print("selftest ok: %d rows, child_vmhwm max %d kB" % (len(rows), hwm))


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--app-pid", type=int)
    p.add_argument("--out")
    p.add_argument("--abort-used-gib", type=float, default=3.0)
    p.add_argument("--abort-avail-gib", type=float, default=1.0)
    p.add_argument("--max-seconds", type=float, default=7200)
    p.add_argument("--wait-seconds", type=float, default=600)
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()
    if args.selftest:
        return selftest()
    if args.app_pid is None or not args.out:
        p.error("--app-pid and --out are required")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
