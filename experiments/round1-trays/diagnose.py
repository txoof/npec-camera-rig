"""Round 1 (issue #164): why some trays get no FastSAM tray mask.

For each tray with no mask in a fastsam.py results file, every raw FastSAM candidate in every
tile is followed through the stages of fastsam.py, and the furthest stage reached by a candidate
that could be that tray is reported:

    never proposed     no candidate box of about tray size near the tray's tag
    cut by the tile    tray-sized candidates exist only where the tile edge cuts the tray
    low score          the best such candidate scored below SCORE_MIN
    duplicate          it was removed as an overlap of a higher-scoring box
    mask test          its mask failed the area, fill or shape test (which one is given)

    PYTHONPATH=src python3 experiments/round1-trays/diagnose.py fastsam-small20.csv

Read only; writes diagnose-<name>.csv next to this file.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import cv2
import numpy as np

import fastsam
import trays

NEAR_MM = 60.0  # same as fastsam.LINK_MAX_MM: a candidate box this close to the tag could be its tray
BOX_EW_MM = (250.0, 360.0)  # a candidate box of about one tray (decision, for this diagnosis only)
BOX_NS_MM = (300.0, 430.0)
EDGE_PX = 3  # tile px: a box this close to the tile's crop edge is cut by it


def stage_of(c: dict) -> str:
    if c["cut"]:
        return "cut by the tile"
    if c["score"] < fastsam.SCORE_MIN:
        return "low score"
    if not c["kept"]:
        return "duplicate"
    return "mask test: " + c["mask_fail"] if c["mask_fail"] else "passed"


ORDER = ["passed", "mask test", "duplicate", "low score", "cut by the tile"]


def main(argv: list[str]) -> None:
    argv = trays.session_argv(argv)
    from npec_rig.calibration_store import load_calibration

    name = Path(argv[0]).stem
    res = list(csv.DictReader(open(trays.HERE / argv[0])))
    found = {}
    for m in csv.DictReader(open(trays.HERE / argv[0].replace(".csv", "-masks.csv"))):
        for t in m["trays"].split():
            found.setdefault(m["still"], set()).add(int(t))
    model = fastsam.FastSam(fastsam.HEF_PATH)
    out = []
    try:
        for r in res:
            still = r["still"]
            tags = trays.detect(still, None)
            a1 = [g for g in tags if g["id"] in trays.SESSION.trays]
            missing = [g for g in a1 if g["id"] not in found.get(still, set())]
            if not missing:
                continue
            sf = load_calibration(trays.RIG / "calibration" / f"{r['calibration']}.json").scale_field
            img = cv2.imread(str(trays.SESSION.stills_dir / f"{still}.jpg"))
            h, w = img.shape[:2]
            cands = []
            for t in fastsam.tiles_from_tags(tags):
                tile, s, ox, oy = fastsam.square_tile(img, t)
                boxes, scores, coefs, protos = fastsam.decode(model(cv2.cvtColor(tile, cv2.COLOR_BGR2RGB)))
                ppm = sf.px_per_mm(ox + fastsam.SIZE / 2 / s, oy + fastsam.SIZE / 2 / s) * s
                ew, ns = (boxes[:, 2] - boxes[:, 0]) / ppm, (boxes[:, 3] - boxes[:, 1]) / ppm
                sized = np.nonzero((ew >= BOX_EW_MM[0]) & (ew <= BOX_EW_MM[1])
                                   & (ns >= BOX_NS_MM[0]) & (ns <= BOX_NS_MM[1]))[0]
                sel = np.nonzero(scores >= fastsam.SCORE_MIN)[0]
                kept = set(sel[fastsam.nms(boxes[sel], scores[sel], fastsam.IOU_MAX)].tolist()) if len(sel) else set()
                # The crop edge in tile px (the rest of the square is grey padding).
                cw, ch = (min(w, t["x1"]) - ox) * s, (min(h, t["y1"]) - oy) * s
                edge = [0 if ox > 0 else -1e9, 0 if oy > 0 else -1e9,
                        cw if t["x1"] < w else 1e9, ch if t["y1"] < h else 1e9]
                for i in sized:
                    x0, y0, x1, y1 = boxes[i]
                    cut = (x0 <= edge[0] + EDGE_PX or y0 <= edge[1] + EDGE_PX
                           or x1 >= edge[2] - EDGE_PX or y1 >= edge[3] - EDGE_PX)
                    fail = ""
                    if i in kept:
                        m = fastsam.masks_for(boxes[i : i + 1], coefs[i : i + 1], protos)[0]
                        ys, xs = np.nonzero(m)
                        if len(xs):
                            (_, _), (rw, rh), _ = cv2.minAreaRect(np.column_stack([xs, ys]).astype(np.float32))
                            area = m.sum() / (trays.TRAY_EW_MM * trays.TRAY_NS_MM * ppm**2)
                            fill = m.sum() / max(rw * rh, 1)
                            mew, mns = (xs.max() - xs.min() + 1) / ppm, (ys.max() - ys.min() + 1) / ppm
                            asp = mns / mew
                            fails = []
                            if not fastsam.TRAY_AREA[0] <= area <= fastsam.TRAY_AREA[1]:
                                fails.append(f"area {area:.2f}")
                            if fill < fastsam.TRAY_FILL_MIN:
                                fails.append(f"fill {fill:.2f}")
                            if not fastsam.TRAY_ASPECT[0] <= asp <= fastsam.TRAY_ASPECT[1]:
                                fails.append(f"shape {asp:.2f}")
                            fail = ", ".join(fails)
                        else:
                            fail = "empty mask"
                    cands.append({"tile": t["name"], "box_full": (ox + x0 / s, oy + y0 / s, ox + x1 / s, oy + y1 / s),
                                  "score": float(scores[i]), "kept": i in kept, "cut": bool(cut),
                                  "mask_fail": fail, "ew_mm": float(ew[i]), "ns_mm": float(ns[i])})
            ppm_full = sf.px_per_mm(w / 2, h / 2)
            for g in missing:
                near = []
                for c in cands:
                    x0, y0, x1, y1 = c["box_full"]
                    dx = max(x0 - g["cx"], 0, g["cx"] - x1)
                    dy = max(y0 - g["cy"], 0, g["cy"] - y1)
                    if np.hypot(dx, dy) / ppm_full <= NEAR_MM:
                        near.append(c)
                if not near:
                    out.append({"still": still, "step": r["step"], "tray": g["id"], "stage": "never proposed",
                                "candidates": 0, "best_score": "", "detail": ""})
                    continue
                best = min(near, key=lambda c: (ORDER.index(stage_of(c).split(":")[0]), -c["score"]))
                out.append({"still": still, "step": r["step"], "tray": g["id"], "stage": stage_of(best),
                            "candidates": len(near), "best_score": round(best["score"], 3),
                            "detail": f"{best['tile']} box {best['ew_mm']:.0f} x {best['ns_mm']:.0f} mm"})
                print(out[-1], flush=True)
    finally:
        model.close()
    trays.write_csv(trays.HERE / f"diagnose-{name}.csv", out)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
