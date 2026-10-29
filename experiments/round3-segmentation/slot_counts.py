"""Issue #297: plants per slot on a still with no tray tags (the development rig's 2x2 trays), by
the green threshold in use joined at 3, 5 and 10 mm and by FastSAM point (compare.py's methods).

Each plant goes to the nearest slot centre of the calibration's slot layout. Truth per slot is
given on the command line.

    PYTHONPATH=~/npec_camera_rig/src:DIR python3 DIR/slot_counts.py STILL --fastsam-hef H \
        --calibration C --slots S --truth "North 2=2,North 3=3,South 1=3" --default 4 --out NEW
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import cv2
import numpy as np

import fastsam_plants as fp
from npec_rig.calibration_store import load_calibration
from npec_rig.tags import detect_tags

METHODS = ("exg_join3", "exg_join5", "exg_join10", "fastsam_point")


def nearest(slots, x, y):
    return min(slots, key=lambda s: (s["centre"][0] - x) ** 2 + (s["centre"][1] - y) ** 2)["name"]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("still", type=Path)
    for a_ in ("--fastsam-hef", "--calibration", "--slots", "--out"):
        ap.add_argument(a_, type=Path, required=True)
    ap.add_argument("--truth", default="", help='"slot=n,slot=n"; other slots get --default')
    ap.add_argument("--default", type=int, default=4)
    ap.add_argument("--cv-threads", type=int, default=2)
    a = ap.parse_args()
    cv2.setNumThreads(a.cv_threads)
    fp.BLOB_MIN_MM2 = 0.5
    out = a.out / a.still.stem
    out.mkdir(parents=True, exist_ok=False)
    sf = load_calibration(a.calibration).scale_field
    slots = json.loads(a.slots.read_text())["slots"]
    truth = {s["name"]: a.default for s in slots}
    for kv in filter(None, a.truth.split(",")):
        k, v = kv.split("=")
        truth[k.strip()] = int(v)

    secs = {}
    t0 = time.perf_counter()
    full = cv2.imread(str(a.still))
    tags = detect_tags(cv2.cvtColor(full, cv2.COLOR_BGR2GRAY))
    bgr, crop, n = fp.crop_to_corner_tags(full, tags)
    del full
    if bgr is None:
        raise SystemExit(f"{n} corner tags, not 4")
    oy = crop[1]
    secs["shared"] = time.perf_counter() - t0

    found = {}
    blobs3 = None
    for j in (3, 5, 10):
        fp.JOIN_MM = j
        t = time.perf_counter()
        _, blobs = fp.exg_blobs(bgr)
        secs[f"exg_join{j}"] = time.perf_counter() - t
        found[f"exg_join{j}"] = [(b["cx"], b["cy"], b["area_px"], None, (b["x0"], b["y0"], b["x1"], b["y1"])) for b in blobs]
        if j == 3:
            blobs3 = blobs
    t = time.perf_counter()
    model = fp.FastSam(a.fastsam_hef)
    try:
        dets, _ = fp.fastsam_all(bgr, model)
    finally:
        model.close()
    uniq = {id(d): d for d in fp.prompted(dets, blobs3) if d is not None}.values()
    found["fastsam_point"] = []
    for d in uniq:
        m = cv2.moments(d["contour"])
        cx, cy = (m["m10"] / m["m00"], m["m01"] / m["m00"]) if m["m00"] else (d["x0"], d["y0"])
        found["fastsam_point"].append((cx, cy, d["area_px"], d["contour"], None))
    secs["fastsam_point"] = time.perf_counter() - t

    names = [s["name"] for s in slots]
    counts = {m: {k: 0 for k in names} for m in METHODS}
    areas = {m: {k: 0.0 for k in names} for m in METHODS}
    for m in METHODS:
        for cx, cy, apx, _, _ in found[m]:
            k = nearest(slots, cx, cy + oy)
            counts[m][k] += 1
            areas[m][k] += apx / sf.px_per_mm(cx, cy + oy) ** 2

    f = 1 / fp.VIEW_REDUCE
    for i, m in enumerate(METHODS, 1):
        im = cv2.resize(bgr, (bgr.shape[1] // fp.VIEW_REDUCE, bgr.shape[0] // fp.VIEW_REDUCE), interpolation=cv2.INTER_AREA)
        for cx, cy, _, cnt, box in found[m]:
            if cnt is not None:
                cv2.drawContours(im, [(cnt * f).astype(np.int32)], -1, (0, 255, 0), 2)
            else:
                cv2.rectangle(im, (int(box[0] * f), int(box[1] * f)), (int(box[2] * f), int(box[3] * f)), (255, 0, 255), 2)
        for s in slots:
            x0, y0, x1, y1 = s["box"]
            cv2.rectangle(im, (int(x0 * f), int((y0 - oy) * f)), (int(x1 * f), int((y1 - oy) * f)), (255, 255, 0), 2)
            lab = f"{s['name']}: {counts[m][s['name']]} (true {truth[s['name']]})"
            org = (int(x0 * f), int((y0 - oy) * f) - 8)
            cv2.putText(im, lab, org, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 5)
            cv2.putText(im, lab, org, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        tot = sum(counts[m].values())
        cv2.rectangle(im, (0, 0), (im.shape[1], 30), (0, 0, 0), -1)
        cv2.putText(im, f"{a.still.stem}  {m}: {tot} plants (true {sum(truth.values())}), slot = nearest slot centre, "
                    f"{secs[m]:.1f} s", (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        cv2.imwrite(str(out / f"{i:02d}_{m}.jpg"), im, [cv2.IMWRITE_JPEG_QUALITY, 85])

    with open(out / "per_slot.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["slot", "true", *[f"{m}_plants" for m in METHODS], *[f"{m}_mm2" for m in METHODS]])
        for k in names:
            wr.writerow([k, truth[k], *[counts[m][k] for m in METHODS], *[round(areas[m][k], 1) for m in METHODS]])
    summary = {m: {"plants": sum(counts[m].values()), "true": sum(truth.values()),
                   "mean_abs_error_per_slot": round(float(np.mean([abs(counts[m][k] - truth[k]) for k in names])), 2),
                   "seconds": round(secs[m], 1)} for m in METHODS}
    (out / "summary.json").write_text(json.dumps({"still": str(a.still), "truth": truth, "methods": summary,
                                                  "shared_seconds": round(secs["shared"], 1)}, indent=1))
    print("slot".ljust(9), "true", *[m[:12].rjust(13) for m in METHODS])
    for k in names:
        print(k.ljust(9), str(truth[k]).rjust(4), *[str(counts[m][k]).rjust(13) for m in METHODS])
    for m, s in summary.items():
        print(m, s)


if __name__ == "__main__":
    main()
