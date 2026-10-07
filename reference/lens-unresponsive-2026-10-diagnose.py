"""Does the lens follow commands after a full-res capture? Diagnosis for the 2026-10-05 bug
(TODO.md, "Lens stops responding after a full-res capture").

Runs one case per process, so every case starts from a fresh camera, the same as an app restart.
The app's server must be stopped first (it holds the camera). Uses Picamera2Backend directly, the
shipped code path, and never calls save_setting: the persisted LensPosition and focus lock are
left as they are, so the app's own start-up drives the lens back afterwards.

For every lens write it records, for OBSERVE_S seconds: the LensPosition the camera reports, the
frame's SensorTimestamp (are frames flowing?) and a sharpness score of the central third of the
main stream (did the lens physically move?). Needs the chamber lights on: in the dark the
sharpness score barely changes with focus.

The two lens positions used are the persisted one (the experimenter's) and a defocused one
DEFOCUS below it, chosen only so the sharpness change is large. Neither is a recommendation.

Usage (from the repo root, server stopped):
    PYTHONPATH=src python3 reference/lens-unresponsive-2026-10-diagnose.py --case baseline
Cases: baseline, one_capture, lock_then_capture, quick_writes, many_captures, autofocus,
       cure_reopen, cure_video_controls
Output: /home/pi/scratch/lens-diagnose-<UTC>/<case>.csv and <case>.json
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from npec_rig.camera import (
    LENS_APPROACH_OFFSET,
    LENS_APPROACH_PAUSE_S,
    Picamera2Backend,
    laplacian_variance,
    to_grayscale,
)
from npec_rig.settings import load_settings

OBSERVE_S = 90.0
POLL_S = 0.5
DEFOCUS = 1.5
REPORT_TOLERANCE = 0.005
MANY_CAPTURES = 13  # occurrence 1 had 13 full-res captures before the first lens command


def sample(backend: Picamera2Backend) -> dict:
    request = backend._picam2.capture_request()
    try:
        metadata = request.get_metadata()
        frame = request.make_array("main")
    finally:
        request.release()
    gray = to_grayscale(frame[..., :3].astype(np.float32))
    h, w = gray.shape
    return {
        "reported": metadata.get("LensPosition"),
        "sensor_ts": metadata.get("SensorTimestamp"),
        "exposure_us": metadata.get("ExposureTime"),
        "sharpness": laplacian_variance(gray[h // 3 : 2 * h // 3, w // 3 : 2 * w // 3]),
    }


class Recorder:
    def __init__(self, out_dir: Path, case: str) -> None:
        self.case = case
        self.out_dir = out_dir
        self.rows: list[dict] = []
        self.steps: list[dict] = []
        self.t0 = time.monotonic()

    def observe(self, backend: Picamera2Backend, step: str, target: float) -> None:
        """Write nothing; watch for OBSERVE_S after a write to `target` made just before."""
        start = time.monotonic()
        first = None
        reached_s = None
        rows = []
        while time.monotonic() - start < OBSERVE_S:
            s = sample(backend)
            s.update(step=step, target=target, t=round(time.monotonic() - self.t0, 2))
            rows.append(s)
            first = first or s
            if (
                reached_s is None
                and s["reported"] is not None
                and abs(s["reported"] - target) <= REPORT_TOLERANCE
            ):
                reached_s = round(time.monotonic() - start, 2)
            time.sleep(POLL_S)
        last = rows[-1]
        timestamps = [r["sensor_ts"] for r in rows if r["sensor_ts"] is not None]
        self.steps.append(
            {
                "step": step,
                "target": target,
                "reported_first": first["reported"],
                "reported_last": last["reported"],
                "reported_reached_s": reached_s,
                "sharpness_first": round(first["sharpness"], 1),
                "sharpness_last": round(last["sharpness"], 1),
                "frames": len(rows),
                "frames_flowing": len(set(timestamps)) > 1,
                "exposure_us_last": last["exposure_us"],
            }
        )
        self.rows.extend(rows)
        print(json.dumps(self.steps[-1]))

    def save(self) -> None:
        with open(self.out_dir / f"{self.case}.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(self.rows[0]))
            writer.writeheader()
            writer.writerows(self.rows)
        (self.out_dir / f"{self.case}.json").write_text(json.dumps(self.steps, indent=1))


def approach(backend: Picamera2Backend, value: float) -> None:
    """The app's one consistent lens drive (CameraManager._drive_lens), without persisting."""
    backend.set_lens_position(max(0.0, value - LENS_APPROACH_OFFSET))
    time.sleep(LENS_APPROACH_PAUSE_S)
    backend.set_lens_position(value)


def move_and_watch(rec: Recorder, backend: Picamera2Backend, step: str, value: float) -> None:
    backend.set_lens_position(value)
    rec.observe(backend, step, value)


def full_res(backend: Picamera2Backend, n: int = 1) -> None:
    for _ in range(n):
        backend.capture_full_res()


def run(case: str, out_dir: Path) -> None:
    persisted = float(load_settings().get("LensPosition"))
    defocused = round(persisted - DEFOCUS, 2)
    rec = Recorder(out_dir, case)
    backend = Picamera2Backend()
    approach(backend, persisted)
    rec.observe(backend, "start, driven to persisted", persisted)
    try:
        if case == "baseline":
            move_and_watch(rec, backend, "defocus, no capture", defocused)
            move_and_watch(rec, backend, "back, no capture", persisted)
        elif case == "one_capture":
            full_res(backend)
            move_and_watch(rec, backend, "defocus after 1 capture", defocused)
            move_and_watch(rec, backend, "back", persisted)
        elif case == "lock_then_capture":
            approach(backend, persisted)
            rec.observe(backend, "lock drive", persisted)
            full_res(backend)
            move_and_watch(rec, backend, "defocus after lock + capture", defocused)
            move_and_watch(rec, backend, "back", persisted)
        elif case == "quick_writes":
            full_res(backend)
            for i in range(10):
                backend.set_lens_position(defocused if i % 2 == 0 else persisted)
                time.sleep(0.2)
            move_and_watch(rec, backend, "defocus after capture + 10 quick writes", defocused)
            move_and_watch(rec, backend, "back", persisted)
        elif case == "many_captures":
            full_res(backend, MANY_CAPTURES)
            move_and_watch(rec, backend, f"defocus after {MANY_CAPTURES} captures", defocused)
            move_and_watch(rec, backend, "back", persisted)
        elif case == "autofocus":
            full_res(backend)
            started = time.monotonic()
            try:
                ok, position = backend.autofocus()
                print(json.dumps({"autofocus_ok": ok, "position": position,
                                  "took_s": round(time.monotonic() - started, 1)}))
            except Exception as exc:  # AutofocusTimeoutError is the case of interest
                print(json.dumps({"autofocus_error": repr(exc)}))
            rec.observe(backend, "after autofocus", backend._lens_position)
            move_and_watch(rec, backend, "back", persisted)
        elif case == "cure_reopen":
            full_res(backend)
            backend._picam2.close()
            backend = Picamera2Backend()
            approach(backend, persisted)
            rec.observe(backend, "reopened camera, driven to persisted", persisted)
            move_and_watch(rec, backend, "defocus after capture + reopen", defocused)
            move_and_watch(rec, backend, "back", persisted)
        elif case == "cure_video_controls":
            # Candidate: manual focus in the video configuration itself, as the still path does.
            backend._video_config["controls"].update(
                {"AfMode": 0, "LensPosition": backend._lens_position}
            )
            full_res(backend)
            move_and_watch(rec, backend, "defocus after capture, focus in video config", defocused)
            move_and_watch(rec, backend, "back", persisted)
        else:
            raise SystemExit(f"unknown case {case}")
    finally:
        approach(backend, persisted)
        rec.save()
        backend._picam2.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", required=True)
    parser.add_argument("--out", default=None, help="output directory (default: new one in scratch)")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out_dir = Path(args.out or f"/home/pi/scratch/lens-diagnose-{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)
    run(args.case, out_dir)
    print(f"saved to {out_dir}")


if __name__ == "__main__":
    main()
