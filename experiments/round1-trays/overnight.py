"""Round 2 (issue #236): tag detection, placement and steadiness of layout 20b by window, overnight (15.5l).

Method: docs/metrology-log.md section 15.5l, "Overnight analysis", decided before the overnight stills
were looked at. Reads the output of shuffle_day.py (run with the same --until), the stills and the
calibration. Windows in chamber time (UTC+2): day to 17:00, quiet 17:00 to 23:00, dark 23:00 to
09:00, light coming up 09:00 to 09:30.

    cd experiments/round1-trays
    PYTHONPATH=<worktree>/src <venv python> overnight.py shuffle-day-2026-10-20_57f74959.csv

Writes overnight-<folder>.csv (one row per still) here and a timeline picture to
~/scratch/round2-shuffles/.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime

import cv2
import numpy as np

import trays
from shuffle import TRAY_TAGS

LAYOUT = "20b"
WINDOWS = [  # (name, start UTC, end UTC)
    ("day", "2026-10-20T00:00", "2026-10-20T15:00"),
    ("quiet", "2026-10-20T15:00", "2026-10-20T21:00"),
    ("dark", "2026-10-20T21:00", "2026-10-21T07:00"),
    ("light coming up", "2026-10-21T07:00", "2026-10-21T07:30"),
]
OUT = trays.SCRATCH.parent / "round2-shuffles"


def window(taken_at: str) -> str:
    t = taken_at[:16]
    return next((name for name, a, b in WINDOWS if a <= t < b), "after")


def brightness(path) -> float:
    img = cv2.imread(str(path), cv2.IMREAD_REDUCED_GRAYSCALE_8)
    return float(img.mean())


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("results", help="shuffle-day-<folder>.csv")
    args = ap.parse_args(argv)
    from npec_rig.calibration_store import load_calibration

    with open(args.results) as f:
        rows = [r for r in csv.DictReader(f) if r["layout"] == LAYOUT]
    folder = args.results.removeprefix("shuffle-day-").removesuffix(".csv")
    by_still = defaultdict(list)
    for r in rows:
        by_still[r["still"]].append(r)
    stills = sorted(by_still, key=lambda s: by_still[s][0]["taken_at_utc"])
    day_dir = {s: by_still[s][0]["taken_at_utc"][:10] for s in stills}
    sf = None
    per_still, centres = [], defaultdict(list)
    for s in stills:
        rs = by_still[s]
        path = trays.RIG / "experiments" / folder / "stills" / day_dir[s] / f"{s}.jpg"
        w = window(rs[0]["taken_at_utc"])
        found = [r for r in rs if r["found"] == "True"]
        per_still.append({"still": s, "taken_at_utc": rs[0]["taken_at_utc"], "window": w,
                          "brightness": round(brightness(path), 1), "tags_found": len(found),
                          "settled": rs[0]["settled"], "right": sum(r["right"] == "True" for r in found),
                          "missing": " ".join(r["tray"] for r in rs if r["found"] != "True")})
        if rs[0]["settled"] != "True":
            continue
        if sf is None:
            import sqlite3
            db = sqlite3.connect(f"file:{trays.RIG / 'rig.db'}?mode=ro", uri=True)
            stem = db.execute("select calibration from capture where path like ?", (f"%/{s}",)).fetchone()[0]
            sf = load_calibration(trays.RIG / "calibration" / f"{stem}.json").scale_field
        for r in found:
            x, y = float(r["x_px"]), float(r["y_px"])
            centres[(w, int(r["tray"]))].append(np.array([x, y]) / sf.px_per_mm(x, y))
    trays.write_csv(trays.HERE / f"overnight-{folder}.csv", per_still)

    names = [n for n, _, _ in WINDOWS] + ["after"]
    print(f"layout {LAYOUT}: {len(stills)} stills, {stills[0]} to {stills[-1]}\n")
    print("window            stills  brightness (min-max)  all 12 found  tags per still (min, median)  "
          "settled  right  wrong  not found")
    for n in names:
        ps = [p for p in per_still if p["window"] == n]
        if not ps:
            continue
        b = [p["brightness"] for p in ps]
        k = [p["tags_found"] for p in ps]
        st = [p for p in ps if p["settled"] == "True"]
        right = sum(p["right"] for p in st)
        found = sum(p["tags_found"] for p in st)
        print(f"  {n:16s} {len(ps):5d}   {min(b):6.1f} - {max(b):6.1f}      {sum(x == 12 for x in k):5d}"
              f"           {min(k):2d}, {np.median(k):4.1f}               {len(st):5d}  {right:5d}  {found - right:5d}"
              f"  {12 * len(st) - found:5d}")
        misses = defaultdict(int)
        for p in ps:
            for t in p["missing"].split():
                misses[int(t)] += 1
        if misses:
            print(f"      misses by tray (all stills): {dict(sorted(misses.items()))}")
    print("\nsteadiness of each tray's placed centre within a window, settled stills, mm")
    means = {}
    for n in names:
        sp = []
        for t in TRAY_TAGS:
            cs = centres.get((n, t))
            if not cs or len(cs) < 2:
                continue
            m = np.mean(cs, axis=0)
            means[(n, t)] = m
            d = np.linalg.norm(np.array(cs) - m, axis=1)
            sp.append((t, float(np.sqrt(np.mean(d ** 2))), float(d.max()), len(cs)))
        if sp:
            worst = max(sp, key=lambda x: x[2])
            print(f"  {n:16s} {len(sp)} trays: rms median {np.median([x[1] for x in sp]):.2f}, "
                  f"max {max(x[1] for x in sp):.2f}; largest single {worst[2]:.2f} (tray {worst[0]}, {worst[3]} stills)")
    print("\nlargest shift of a tray's mean centre between consecutive windows, mm")
    present = [n for n in names if any((n, t) in means for t in TRAY_TAGS)]
    for a, b in zip(present, present[1:]):
        d = [(t, float(np.linalg.norm(means[(a, t)] - means[(b, t)]))) for t in TRAY_TAGS
             if (a, t) in means and (b, t) in means]
        if d:
            t, v = max(d, key=lambda x: x[1])
            print(f"  {a} to {b}: max {v:.2f} (tray {t}), median {np.median([x[1] for x in d]):.2f}, {len(d)} trays")

    # timeline: brightness and tags found per still
    ts = [datetime.fromisoformat(p["taken_at_utc"]).timestamp() for p in per_still]
    h, wpx = 600, 1600
    img = np.full((h, wpx, 3), 255, np.uint8)
    t0, t1 = ts[0], ts[-1] if ts[-1] > ts[0] else ts[0] + 1
    for p, t in zip(per_still, ts):
        x = int(40 + (wpx - 80) * (t - t0) / (t1 - t0))
        cv2.circle(img, (x, int(280 - 240 * p["brightness"] / 255)), 2, (0, 0, 0), -1)
        cv2.circle(img, (x, int(560 - 240 * p["tags_found"] / 12)), 2, (200, 0, 0) if p["tags_found"] == 12 else (0, 0, 220), -1)
    cv2.putText(img, "brightness 0-255", (45, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
    cv2.putText(img, "tags found 0-12 (blue: all 12, red: fewer)", (45, 315), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
    for name, a, _ in WINDOWS:
        t = datetime.fromisoformat(a + ":00+00:00").timestamp()
        if t0 <= t <= t1:
            x = int(40 + (wpx - 80) * (t - t0) / (t1 - t0))
            cv2.line(img, (x, 0), (x, h), (150, 150, 150), 1)
            cv2.putText(img, name, (x + 4, 590), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (80, 80, 80), 1)
    OUT.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUT / f"overnight-timeline-{folder}.png"), img)
    print(f"\ntimeline: {OUT / f'overnight-timeline-{folder}.png'}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
