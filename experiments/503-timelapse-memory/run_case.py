#!/usr/bin/env python3
"""Run one time-lapse memory case on the development rig (#503, log 52.3).

Standard library only, never imports npec_rig. Run it ON the rig. Reads rig.db read only.
It checks free memory, waits until about 20 s before the next scheduled photo, starts
sample.py on the app, starts the video through the app's own API, polls it, and writes
<out>/<case>-<n>.csv (the sampler) and <out>/<case>-<n>.json (the result).

    python3 run_case.py --case A --out ~/scratch/503/data
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

DB = "/var/lib/npec-rig/rig.db"
BASE = "http://localhost:8000"
EXPERIMENT = 4
INTERVAL_S = 300  # the photo interval of experiment 4
MIN_AVAILABLE_MB = 5000  # log 52.4: start only with about 5 GiB available
# case: tray ("all" or a number), photos an hour, mask (log 52.3)
CASES = {
    "A": (8, 1, False),
    "B": (8, 2, True),
    "C": ("all", 1, False),
    "D": (8, 5, False),
    # Added after A to D: the mask had the highest child VmPeak (B), the stand-in rate had the
    # most frames (D), so F combines them. Not in the method as first written (log 52.3).
    "F": (8, 5, True),
}


def call(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def available_mb():
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable"):
            return int(line.split()[1]) // 1024


def app_pid():
    out = subprocess.run(["systemctl", "show", "npec-rig", "-p", "MainPID", "--value"],
                         capture_output=True, text=True, check=True).stdout
    return int(out.strip())


def nrestarts():
    return subprocess.run(["systemctl", "show", "npec-rig", "-p", "NRestarts", "--value"],
                          capture_output=True, text=True, check=True).stdout.strip()


def latest_photo():
    con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
    return datetime.fromisoformat(con.execute("SELECT max(taken_at) FROM capture").fetchone()[0])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--case", choices=sorted(CASES), required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--run", type=int, default=1, help="1, or 2 for the repeat")
    args = p.parse_args()
    tray, per_hour, mask = CASES[args.case]
    os.makedirs(args.out, exist_ok=True)
    name = "%s-%d" % (args.case, args.run)

    avail = available_mb()
    if avail < MIN_AVAILABLE_MB:
        print("only %d MB available, need %d: not starting" % (avail, MIN_AVAILABLE_MB))
        return 4
    restarts_before = nrestarts()
    pid = app_pid()

    # Start about 20 s before the next photo is due, so its tray reading overlaps the video.
    due = latest_photo() + timedelta(seconds=INTERVAL_S)
    while due - datetime.now(timezone.utc) < timedelta(seconds=25):
        due += timedelta(seconds=INTERVAL_S)
    sampler = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample.py"),
                                "--app-pid", str(pid), "--out", os.path.join(args.out, name + ".csv")],
                               stdout=subprocess.PIPE, text=True)
    wait = (due - timedelta(seconds=20) - datetime.now(timezone.utc)).total_seconds()
    print("case %s run %d: next photo due %s, starting in %.0f s" % (args.case, args.run, due.isoformat(), wait))
    time.sleep(max(wait, 0))

    first = call("GET", "/api/experiments")[1]
    first = first if isinstance(first, list) else first.get("experiments", first)
    first = [e for e in first if e["id"] == EXPERIMENT][0]["periods"][0]["started_at"]
    now = datetime.now(timezone.utc)
    request = {"experiment_id": EXPERIMENT, "tray_id": tray, "start": first, "end": now.isoformat(),
               "per_hour": per_hour, "method": "grown", "mask": mask}
    started_at = time.monotonic()
    status, reply = call("POST", "/api/data/timelapse", request)
    print("start:", status, reply)
    result = {"case": args.case, "run": args.run, "request": request, "start_status": status,
              "available_mb_before": avail, "nrestarts_before": restarts_before,
              "sampler_pid_app": pid}
    if status == 200:
        video_id = reply["id"] if "id" in reply else reply.get("video_id")
        while True:
            state = call("GET", "/api/data/timelapse/%s" % video_id)[1]
            if state.get("state") not in ("choosing", "drawing"):
                break
            time.sleep(2)
        result["video_id"] = video_id
        result["final"] = state
    result["seconds"] = round(time.monotonic() - started_at, 1)
    try:
        summary, _ = sampler.communicate(timeout=120)
    except subprocess.TimeoutExpired:
        sampler.terminate()
        summary, _ = sampler.communicate()
    result["sampler_exit"] = sampler.returncode
    result["sampler_summary"] = (summary or "").strip()
    result["nrestarts_after"] = nrestarts()
    result["last_photo_after"] = latest_photo().isoformat()
    result["photo_due"] = due.isoformat()
    with open(os.path.join(args.out, name + ".json"), "w") as fh:
        json.dump(result, fh, indent=1, default=str)
    keep = {k: result.get("final", {}).get(k) for k in ("state", "frames", "done", "skipped", "unreadable", "error")}
    print(json.dumps({"final": keep, "seconds": result["seconds"], "sampler": result["sampler_summary"],
                      "restarts": (restarts_before, result["nrestarts_after"])}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
