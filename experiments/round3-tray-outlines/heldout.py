"""Issue #328: the held-out test. The frozen finders (commit 49c868e) on stills not used for
tuning, with no known answer: Aaron inspects the pictures and gives the truth afterwards.

    python heldout.py OUT_NAME

Writes VIEW/OUT_NAME/: one sheet per still (four panels, one per finder; every outline numbered,
with its tray ID or "no tag" and any warning), outlines.csv (every outline), notes.txt.
"""

import csv
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import methods_blue  # noqa: E402
import methods_rims  # noqa: E402
from harness import Q, VIEW, stills  # noqa: E402

FINDERS = [("B blue, with tags", methods_blue.find), ("B blue, photo only", methods_blue.find_photo_only),
           ("D rims, with tags", methods_rims.find), ("D rims, tags hidden", methods_rims.find_blind)]
COLOURS = [(0, 220, 0), (255, 160, 0), (0, 200, 255), (255, 0, 255)]


def panel(still, found, title, colour):
    im = still.quarter.copy()
    for k, f in enumerate(found, 1):
        o = np.int32(np.asarray(f["outline"]) / Q)
        cv2.polylines(im, [o], True, colour, 5)
        cx, cy = o.mean(0)
        tid = "no tag" if f.get("tray_id") is None else f"tray {f['tray_id']}"
        warn = [w for w in f.get("warnings", []) if w != "no tag"]
        for line, dy in ((f"{k}: {tid}", 0), ("; ".join(warn)[:40], 34)):
            if not line:
                continue
            for col, th in (((0, 0, 0), 7), ((255, 255, 255), 2)):
                cv2.putText(im, line, (int(cx - 120), int(cy + dy)), cv2.FONT_HERSHEY_SIMPLEX, 1.0, col, th)
    cv2.rectangle(im, (0, 0), (im.shape[1], 50), (0, 0, 0), -1)
    cv2.putText(im, f"{title}: {len(found)} outlines", (10, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
    return cv2.resize(im, None, fx=0.4, fy=0.4, interpolation=cv2.INTER_AREA)


def main():
    out = VIEW / sys.argv[1]
    out.mkdir(parents=True, exist_ok=False)
    rows, secs = [], {t: [] for t, _ in FINDERS}
    for n, s in enumerate(stills("held"), 1):
        tiles = []
        for (title, find), colour in zip(FINDERS, COLOURS):
            t0 = time.perf_counter()
            found = find(s)
            secs[title].append(time.perf_counter() - t0)
            tiles.append(panel(s, found, title, colour))
            for k, f in enumerate(found, 1):
                c = np.asarray(f["outline"], float).mean(0)
                rows.append([n, s.stem, title, k, f.get("tray_id"), f.get("how", ""), "; ".join(f.get("warnings", [])),
                             round(c[0]), round(c[1])])
        sheet = cv2.vconcat([cv2.hconcat(tiles[:2]), cv2.hconcat(tiles[2:])])
        band = np.zeros((44, sheet.shape[1], 3), np.uint8)
        tags = sorted(t["id"] for t in s.tags if t["id"] < 300)
        cv2.putText(band, f"still {n}: {s.stem}  tray tags read: {tags if tags else 'none'}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.imwrite(str(out / f"{n:02d}-{s.stem}.jpg"), cv2.vconcat([band, sheet]), [cv2.IMWRITE_JPEG_QUALITY, 82])
        print(n, s.stem, flush=True)
    with open(out / "outlines.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["still_no", "still", "finder", "outline_no", "tray_id", "how", "warnings", "centre_x_px", "centre_y_px"])
        wr.writerows(rows)
    (out / "notes.txt").write_text(
        "328 held-out test: frozen finders (commit 49c868e) on 24 stills not used for tuning, both rigs.\n"
        "Each sheet: 4 finders. Each outline is numbered, with its tray tag (or 'no tag') and any warning.\n"
        "For Aaron: per still, how many trays are really there, and per finder which numbers are wrong or which trays are missed.\n"
        "Two stills are in the dark on purpose (no tray should be found).\n"
        + "".join(f"{t}: {np.mean(v):.1f} s per still\n" for t, v in secs.items()))


if __name__ == "__main__":
    main()
