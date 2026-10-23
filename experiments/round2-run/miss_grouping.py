"""Metrology log 16.8: for each tray tag missed in the potato run's first day, the full photo with the
tray settings, the larger rejected shape near the tag, and minMarkerDistanceRate 0.08 and 0.05.
Reads the photos and a copy of rig.db (read_photos.py) only.

    python miss_grouping.py   # the copy in ~/scratch/223-analysis/exp18
"""
import sqlite3
from pathlib import Path

import read_photos
W = Path.home()/'scratch/223-analysis/exp18'
read_photos.use_copy(W)
import cv2, numpy as np
from npec_rig import images, tags
from npec_rig.tags import to_grayscale
D = cv2.aruco.getPredefinedDictionary(tags.TAG_DICTIONARY)
c = sqlite3.connect(f"file:{W/'rig.db'}?mode=ro", uri=True)
misses = [("2026-10-22T08:55:53", 2), ("2026-10-22T09:30:53", 2), ("2026-10-22T10:02:53", 6),
          ("2026-10-22T11:23:55", 10), ("2026-10-22T13:33:54", 8), ("2026-10-22T13:53:55", 12),
          ("2026-10-22T14:12:55", 8), ("2026-10-22T17:20:53", 8), ("2026-10-22T18:49:53", 8),
          ("2026-10-22T20:05:53", 10), ("2026-10-22T20:17:53", 8), ("2026-10-22T22:50:53", 7)]
def avgdist(a, b):
    return min(np.mean(np.linalg.norm(a - np.roll(b, k, axis=0), axis=1)) for k in range(4))
def run(gray, rate=None):
    p = tags._tray_detector_parameters()
    if rate is not None:
        p.minMarkerDistanceRate = rate
    cs, ids, rej = cv2.aruco.ArucoDetector(D, p).detectMarkers(gray)
    return cs, ([] if ids is None else [int(i) for i in ids.flatten()]), rej
print("time UTC | tray | default | larger shape near tag (avg corner distance, px) | threshold px | 0.08 | 0.05 | other tray tags 0.05 vs default")
for t, tray in misses:
    cid, path = c.execute("select id, path from capture where experiment_id=18 and taken_at like ?", (t + "%",)).fetchone()
    # The tag's corners from the latest earlier photo of the same experiment that found it.
    earlier = c.execute("select path from capture where experiment_id=18 and taken_at < ? order by taken_at desc",
                        (t,)).fetchall()
    ref = next(x for (p,) in earlier for x in (images.stored_tag_detections(p) or []) if x.tag_id == tray)
    true = np.array(ref.corners)
    per = sum(np.linalg.norm(true[i] - true[(i + 1) % 4]) for i in range(4))
    gray = to_grayscale(cv2.imread(f"/var/lib/npec-rig/{path}.jpg")[:, :, ::-1]).astype(np.uint8)
    _, ids0, rej = run(gray)
    big = [round(float(avgdist(r.reshape(4, 2), true)), 1) for r in rej
           if np.linalg.norm(r.reshape(4, 2).mean(0) - true.mean(0)) < 150 and cv2.arcLength(r.reshape(4, 2), True) > 1.2 * per]
    _, ids8, _ = run(gray, 0.08)
    _, ids5, _ = run(gray, 0.05)
    tray0, tray5 = sorted(i for i in ids0 if i < 300), sorted(i for i in ids5 if i < 300)
    print(f"{t[11:]} | {tray} | {'found' if tray in ids0 else 'missed'} | {big} | {0.125 * per:.1f} | "
          f"{'found' if tray in ids8 else 'missed'} | {'found' if tray in ids5 else 'missed'} | "
          f"{len(tray5)} vs {len(tray0)}, {'same IDs plus this tray' if set(tray5) - set(tray0) <= {tray} and set(tray0) <= set(tray5) else 'DIFFERENT'}",
          flush=True)
