"""Issue #328: every FastSAM object in a still, at three tile scales, for the tray finders.

Runs on a rig with a Hailo (development, npec-rig-01, Hailo-10H). Stills are read only; one
JSON per still is written to a new folder under --out. The tray finders (methods_*.py) read
these on the controller, so the accelerator runs once per still.

    python3 fastsam_objects.py --hef fast_sam_s_h10_v5.1.0.hef --out DIR still.jpg [...]

Decoding and the Hailo wrapper are round 3's (experiments/round3-segmentation/fastsam_plants.py).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "round3-segmentation"))
from fastsam_plants import SIZE, FastSam, decode, masks_for, nms, starts  # noqa: E402

# Tile side and step at full resolution. A tray is about 1500 x 1800 full px, so "whole" holds
# every tray small (about 105 x 128 model px), "large" holds whole trays (about 234 x 286) and
# "medium" holds about one tray per tile. Decisions for a first look, not measured optima.
SCALES = {"whole": (None, None), "large": (4096, 2560), "medium": (2560, 1600)}
# Round 1 found one-tray boxes scoring only 0.10 to 0.20 (metrology log 15.5f), so keep low ones;
# the finders choose their own cut.
SCORE_MIN = 0.05
IOU_MAX = 0.7
EDGE_PX = 4  # a box this close to an inner tile edge is cut by the tile and dropped


def objects(bgr, model, tile, step):
    h, w = bgr.shape[:2]
    if tile is None:  # the whole still, padded grey to a square
        side = max(h, w)
        tiles = [(0, 0, side)]
    else:
        tiles = [(x0, y0, tile) for y0 in starts(h, tile, step) for x0 in starts(w, tile, step)]
    out = []
    for x0, y0, side in tiles:
        crop = np.full((side, side, 3), 114, np.uint8)
        part = bgr[y0 : y0 + side, x0 : x0 + side]
        crop[: part.shape[0], : part.shape[1]] = part
        s = SIZE / side
        rgb = cv2.cvtColor(cv2.resize(crop, (SIZE, SIZE), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
        boxes, scores, coefs, protos = decode(model(rgb))
        sel = np.nonzero(scores >= SCORE_MIN)[0]
        if not len(sel):
            continue
        keep = sel[nms(boxes[sel], scores[sel], IOU_MAX)]
        b = boxes[keep]
        cut = (((b[:, 0] < EDGE_PX) & (x0 > 0)) | ((b[:, 1] < EDGE_PX) & (y0 > 0))
               | ((b[:, 2] > SIZE - EDGE_PX) & (x0 + side < w))
               | ((b[:, 3] > SIZE - EDGE_PX) & (y0 + side < h)))
        keep = keep[~cut]
        # One mask at a time: all at once is about 1000 x 640 x 640 at this score cut, and the
        # first run was killed at a 1.5 GB memory cap.
        for k in keep:
            m = masks_for(boxes[k : k + 1], coefs[k : k + 1], protos)[0]
            cnts, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not cnts:
                continue
            c = max(cnts, key=cv2.contourArea)
            c = cv2.approxPolyDP(c, 1.0, True).reshape(-1, 2).astype(np.float64)
            out.append({"score": round(float(scores[k]), 4),
                        "area_px": round(float(m.sum()) / s**2),
                        "box": [round(x0 + boxes[k][0] / s), round(y0 + boxes[k][1] / s),
                                round(x0 + boxes[k][2] / s), round(y0 + boxes[k][3] / s)],
                        "contour": (c / s + [x0, y0]).round().astype(int).tolist()})
    if out:  # duplicates from overlapping tiles
        b = np.array([o["box"] for o in out], float)
        out = [out[i] for i in nms(b, np.array([o["score"] for o in out]), IOU_MAX)]
    return out, len(tiles)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("stills", nargs="+", type=Path)
    ap.add_argument("--hef", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True, help="new folder")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    a.stills = [s for s in a.stills if not (a.out / f"{s.stem}.json").exists()]  # resume
    model = FastSam(a.hef)
    try:
        for still in a.stills:
            t0 = time.perf_counter()
            bgr = cv2.imread(str(still))
            rec = {"still": still.stem, "size_px": [bgr.shape[1], bgr.shape[0]], "hef": a.hef.name,
                   "score_min": SCORE_MIN, "iou_max": IOU_MAX, "scales": {}}
            for name, (tile, step) in SCALES.items():
                objs, n = objects(bgr, model, tile, step)
                rec["scales"][name] = {"tile_px": tile, "step_px": step, "tiles": n, "objects": objs}
            rec["seconds"] = round(time.perf_counter() - t0, 1)
            (a.out / f"{still.stem}.json").write_text(json.dumps(rec))
            print(still.stem, {k: len(v["objects"]) for k, v in rec["scales"].items()}, rec["seconds"], "s", flush=True)
    finally:
        model.close()


if __name__ == "__main__":
    main()
