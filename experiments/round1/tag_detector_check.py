"""Tray tag detector check, metrology log section 15.3e (issue #156).

Runs setting A (the rig's detector, tags._detector_parameters) and setting C (A with finer bit
sampling) on the 53 tag-test stills and the saved calibration stills. Writes, beside this script:

- tag-detector-stills.csv: per still, the IDs each setting found and each timed run in seconds
- tag-detector-corners.json: per calibration still, corners of tags 300 to 499 for A and C
- tag-detector-run.json: commit id, OpenCV version and threads, load average before and after

Run from the repo root: PYTHONPATH=src python3 experiments/round1/tag_detector_check.py
"""

import csv
import glob
import json
import os
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from npec_rig import tags
from npec_rig.camera import to_grayscale

HERE = Path(__file__).resolve().parent
RIG = Path("/var/lib/npec-rig")
SESSION_DIR = RIG / "experiments/2026-10-15_44a9e96e/stills/2026-10-15"
RUNS = 3


def setting_a():
    return tags._detector_parameters()


def setting_c():
    p = tags._detector_parameters()
    p.perspectiveRemovePixelPerCell = 8
    p.perspectiveRemoveIgnoredMarginPerCell = 0.2
    return p


def grey(path):
    with Image.open(path) as image:
        image.load()
        frame = np.asarray(image if image.mode == "RGB" else image.convert("RGB"))
    return to_grayscale(frame).astype(np.uint8)


def detect(gray, params):
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(tags.TAG_DICTIONARY), params)
    t = time.perf_counter()
    corners, ids, _ = detector.detectMarkers(gray)
    dt = time.perf_counter() - t
    found = {}
    if ids is not None:
        for c, i in zip(corners, ids.flatten()):
            found[int(i)] = c.reshape(4, 2).tolist()
    return found, dt


def stills():
    """(group, step, still name, path, timed) for every still in the check."""
    rows = list(csv.reader(open(HERE / "session-2026-10-15.csv")))[1:]
    out = []
    for step, _title, _uuid, _dir, still in rows:
        if step == "R3":
            continue
        group = "round2" if step.startswith("R2-") else "session1"
        out.append((group, step, still, SESSION_DIR / f"{still}.jpg", group == "round2"))
    for side in sorted(glob.glob(str(RIG / "rig/*/*.json"))):
        if json.load(open(side)).get("purpose") == "calibration":
            p = Path(side)
            out.append(("calibration", "", f"{p.parent.name}/{p.stem}", p.with_suffix(".jpg"), True))
    return out


def main():
    run = {
        "commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=HERE).stdout.strip(),
        "opencv": cv2.__version__,
        "opencv_threads": cv2.getNumThreads(),
        "loadavg_start": os.getloadavg(),
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    corners = {}
    with open(HERE / "tag-detector-stills.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["group", "step", "still", "found_A", "found_C"]
                   + [f"secs_{s}{k}" for k in range(1, RUNS + 1) for s in "AC"] + ["loadavg_1min"])
        for group, step, still, path, timed in stills():
            g = grey(path)
            secs = []
            found_a = found_c = None
            for _ in range(RUNS if timed else 1):
                fa, ta = detect(g, setting_a())
                fc, tc = detect(g, setting_c())
                secs += [round(ta, 4), round(tc, 4)]
                found_a = found_a or fa
                found_c = found_c or fc
                # Every run must find the same IDs, or the timed runs are not comparable.
                assert set(fa) == set(found_a) and set(fc) == set(found_c), still
            del g
            if group == "calibration":
                corners[still] = {"A": {i: c for i, c in found_a.items() if i >= 300},
                                  "C": {i: c for i, c in found_c.items() if i >= 300}}
            secs += [""] * (2 * RUNS - len(secs))
            w.writerow([group, step, still, " ".join(map(str, sorted(found_a))),
                        " ".join(map(str, sorted(found_c)))] + secs + [round(os.getloadavg()[0], 2)])
            f.flush()
            print(group, step, still, len(found_a), len(found_c), flush=True)
    json.dump(corners, open(HERE / "tag-detector-corners.json", "w"), indent=1)
    run["loadavg_end"] = os.getloadavg()
    run["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    json.dump(run, open(HERE / "tag-detector-run.json", "w"), indent=1)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
