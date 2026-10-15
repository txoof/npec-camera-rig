"""Round 1 (issue #164): FastSAM on the Hailo-8, on tray crops placed from the tray tags.

fast_sam_s.hef (Hailo Model Zoo v2.17.0, Hailo-8) is a YOLOv8 instance segmentation network with
one class, "object". Its outputs are decoded here: per grid cell a box (4 x 16 distance bins),
a score and 32 mask coefficients, on 80, 40 and 20 cell grids; 32 base masks of 160 x 160.

    PYTHONPATH=src python3 experiments/round1-trays/fastsam.py STILL [STILL ...]

Crops: each row of trays (North, South, from the A1 tags) is cut into tiles of 2 neighbouring
trays, padded to a square and resized to 640 x 640. Stills are read only; overlays and the HEF are
in ~/scratch/round1-trays/.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np

import trays

HEF_PATH = trays.SCRATCH / "hailo" / "fast_sam_s.hef"
OUT = trays.SCRATCH / "fastsam"
SIZE = 640
STRIDES = (8, 16, 32)
SCORE_MIN = 0.25  # decision: FastSAM's usual default confidence
IOU_MAX = 0.7  # decision: FastSAM's usual default for removing duplicates
TRAY_W_PX = 1480  # tray east-west at full resolution (305 mm at about 4.86 px/mm)
TRAY_H_PX = 1780  # north-south (366 mm)
TRAYS_PER_TILE = 2
# Which masks are trays (decisions, not measurements).
TRAY_AREA = (0.8, 1.2)  # mask area in trays
TRAY_FILL_MIN = 0.85  # mask area over its rotated rectangle's area
TRAY_ASPECT = (366 / 305 / 1.15, 366 / 305 * 1.15)  # north-south over east-west


# ---------------------------------------------------------------- pure functions (unit tested)


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def dfl_distances(bins: np.ndarray) -> np.ndarray:
    """(N, 64) box bins to (N, 4) distances left, top, right, bottom in grid cells."""
    b = bins.reshape(-1, 4, 16)
    b = np.exp(b - b.max(axis=2, keepdims=True))
    b /= b.sum(axis=2, keepdims=True)
    return (b * np.arange(16)).sum(axis=2)


def decode(outputs: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Boxes (x0, y0, x1, y1 in input px), scores, coefficients, base masks from raw outputs.

    Outputs are told apart by shape: channels 64 (box), 1 (score), 32 (coefficients), and the
    160 x 160 base masks."""
    by_grid: dict[int, dict[int, np.ndarray]] = {}
    protos = None
    for a in outputs.values():
        a = a.reshape(a.shape[-3:])
        h, _, c = a.shape
        if h == SIZE // 4 and c == 32:
            protos = a
        else:
            by_grid.setdefault(h, {})[c] = a
    boxes, scores, coefs = [], [], []
    for stride in STRIDES:
        g = by_grid[SIZE // stride]
        n = SIZE // stride
        ys, xs = np.mgrid[0:n, 0:n]
        cx, cy = (xs.ravel() + 0.5), (ys.ravel() + 0.5)
        d = dfl_distances(g[64].reshape(-1, 64))
        boxes.append(np.stack([cx - d[:, 0], cy - d[:, 1], cx + d[:, 2], cy + d[:, 3]], 1) * stride)
        s = g[1].reshape(-1)
        scores.append(s if (s.min() >= 0 and s.max() <= 1) else sigmoid(s))
        coefs.append(g[32].reshape(-1, 32))
    return np.concatenate(boxes), np.concatenate(scores), np.concatenate(coefs), protos


def nms(boxes: np.ndarray, scores: np.ndarray, iou_max: float) -> list[int]:
    keep = cv2.dnn.NMSBoxes(
        [[float(x0), float(y0), float(x1 - x0), float(y1 - y0)] for x0, y0, x1, y1 in boxes],
        scores.astype(float).tolist(), 0.0, iou_max)
    return [int(i) for i in np.array(keep).ravel()]


def is_tray_mask(area_trays: float, fill: float, ew_mm: float, ns_mm: float) -> bool:
    aspect = ns_mm / ew_mm if ew_mm else 0
    return (TRAY_AREA[0] <= area_trays <= TRAY_AREA[1] and fill >= TRAY_FILL_MIN
            and TRAY_ASPECT[0] <= aspect <= TRAY_ASPECT[1])


def masks_for(boxes, coefs, protos) -> np.ndarray:
    """Masks at input size (K, 640, 640), each cut to its box."""
    m = sigmoid(np.einsum("kc,hwc->khw", coefs, protos))
    out = np.zeros((len(boxes), SIZE, SIZE), bool)
    for k, (x0, y0, x1, y1) in enumerate(boxes):
        up = cv2.resize(m[k], (SIZE, SIZE), interpolation=cv2.INTER_LINEAR) > 0.5
        bx0, by0 = max(0, int(x0)), max(0, int(y0))
        bx1, by1 = min(SIZE, int(np.ceil(x1))), min(SIZE, int(np.ceil(y1)))
        out[k, by0:by1, bx0:bx1] = up[by0:by1, bx0:bx1]
    return out


def tiles_from_tags(tags: list[dict], per_tile: int = TRAYS_PER_TILE) -> list[dict]:
    """Full-resolution crop boxes, one per run of `per_tile` neighbouring trays in a row.

    Row and order from the A1 tags (North is the 6 with the smallest y). A tag sits at the south-
    west or north-east corner of its tray, so the crop reaches 0.75 of a tray past the outer tags
    on every side, which holds the trays at either orientation."""
    a1 = sorted((t for t in tags if t["id"] in trays.A1_TAGS), key=lambda t: t["cy"])
    if len(a1) != 12:
        return []
    out = []
    for row, sel in (("North", a1[:6]), ("South", a1[6:])):
        sel = sorted(sel, key=lambda t: t["cx"])
        for k in range(0, 6, per_tile):
            grp = sel[k : k + per_tile]
            xs, ys = [t["cx"] for t in grp], [t["cy"] for t in grp]
            out.append({
                "name": f"{row} {k + 1}-{k + len(grp)}", "trays": [t["id"] for t in grp],
                "x0": int(min(xs) - 0.75 * TRAY_W_PX), "x1": int(max(xs) + 0.75 * TRAY_W_PX),
                "y0": int(min(ys) - 0.75 * TRAY_H_PX), "y1": int(max(ys) + 0.75 * TRAY_H_PX),
            })
    return out


def square_tile(img: np.ndarray, t: dict) -> tuple[np.ndarray, float, int, int]:
    """The crop padded to a square with grey and resized to 640; (tile, scale, x origin, y origin)."""
    h, w = img.shape[:2]
    x0, y0 = max(0, t["x0"]), max(0, t["y0"])
    crop = img[y0 : min(h, t["y1"]), x0 : min(w, t["x1"])]
    side = max(crop.shape[:2])
    sq = np.full((side, side, 3), 114, np.uint8)
    sq[: crop.shape[0], : crop.shape[1]] = crop
    scale = SIZE / side
    return cv2.resize(sq, (SIZE, SIZE), interpolation=cv2.INTER_AREA), scale, x0, y0


# ---------------------------------------------------------------- Hailo


class FastSam:
    def __init__(self, hef_path: Path):
        from hailo_platform import (HEF, ConfigureParams, FormatType, HailoStreamInterface,
                                    InferVStreams, InputVStreamParams, OutputVStreamParams, VDevice)

        self.hef = HEF(str(hef_path))
        self.device = VDevice()
        cp = ConfigureParams.create_from_hef(self.hef, interface=HailoStreamInterface.PCIe)
        self.group = self.device.configure(self.hef, cp)[0]
        self.ivp = InputVStreamParams.make(self.group, format_type=FormatType.UINT8)
        self.ovp = OutputVStreamParams.make(self.group, format_type=FormatType.FLOAT32)
        self.input_name = self.hef.get_input_vstream_infos()[0].name
        self._infer = InferVStreams(self.group, self.ivp, self.ovp)
        self._pipe = self._infer.__enter__()
        self._active = self.group.activate(self.group.create_params())
        self._active.__enter__()

    def __call__(self, rgb640: np.ndarray) -> dict[str, np.ndarray]:
        return self._pipe.infer({self.input_name: rgb640[None].astype(np.uint8)})

    def close(self):
        self._active.__exit__(None, None, None)
        self._infer.__exit__(None, None, None)
        self.device.release()


# ---------------------------------------------------------------- run


def run_still(still: str, model: FastSam, scale_field, rows: list[dict], det) -> None:
    tags = trays.detect(still, det)  # cached in scratch after the first time
    img = cv2.imread(str(trays.EXPERIMENT / f"{still}.jpg"))
    for t in tiles_from_tags(tags):
        tile, s, ox, oy = square_tile(img, t)
        raw = model(cv2.cvtColor(tile, cv2.COLOR_BGR2RGB))
        boxes, scores, coefs, protos = decode(raw)
        sel = np.nonzero(scores >= SCORE_MIN)[0]
        keep = sel[nms(boxes[sel], scores[sel], IOU_MAX)] if len(sel) else sel
        masks = masks_for(boxes[keep], coefs[keep], protos) if len(keep) else np.zeros((0, SIZE, SIZE), bool)
        cxf, cyf = ox + SIZE / 2 / s, oy + SIZE / 2 / s
        ppm = scale_field.px_per_mm(cxf, cyf) * s  # tile px per mm
        tray_px = trays.TRAY_EW_MM * trays.TRAY_NS_MM * ppm**2
        vis = tile.copy()
        for k, m in enumerate(masks):
            area = m.sum() / tray_px
            ys, xs = np.nonzero(m)
            if len(xs) == 0:
                continue
            (rx, ry), (rw, rh), _ = cv2.minAreaRect(np.column_stack([xs, ys]).astype(np.float32))
            fill = m.sum() / max(rw * rh, 1)
            ew, ns = (xs.max() - xs.min() + 1) / ppm, (ys.max() - ys.min() + 1) / ppm  # trays are axis-aligned portrait
            tray_like = is_tray_mask(area, fill, ew, ns)
            ids = []
            if tray_like:
                cnts, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                c = max(cnts, key=cv2.contourArea)
                local = [{"id": g["id"], "cx": (g["cx"] - ox) * s, "cy": (g["cy"] - oy) * s} for g in tags]
                ids = trays.tags_in_shape(c, local, trays.TAG_NEAR_MM * ppm)
            verdict, tray_ids = trays.judge_shape(ids, 1.0) if tray_like else ("not a tray", [])  # size checked above
            rows.append({"still": still, "tile": t["name"], "mask": k, "score": round(float(scores[keep][k]), 3),
                         "area_trays": round(float(area), 2), "fill": round(float(fill), 2),
                         "ew_mm": round(float(ew), 1), "ns_mm": round(float(ns), 1),
                         "tray_like": tray_like, "tags_inside": " ".join(map(str, ids)),
                         "verdict": verdict, "trays": " ".join(map(str, tray_ids)),
                         "cx_full": round(ox + rx / s), "cy_full": round(oy + ry / s)})
            if not tray_like:
                continue
            col = {"one tray": (0, 200, 0), "several trays": (0, 0, 255)}.get(verdict, (0, 165, 255))
            vis[m] = (0.6 * vis[m] + 0.4 * np.array(col)).astype(np.uint8)
            cv2.drawContours(vis, [c], -1, col, 2)
            label = f"tray {','.join(map(str, tray_ids))}" if tray_ids else "NO TAG"
            for j, line in enumerate((label, f"{ew:.0f} x {ns:.0f} mm")):
                org = (int(rx) - 50, int(ry) + 22 * j)
                cv2.putText(vis, line, org, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
                cv2.putText(vis, line, org, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        cv2.rectangle(vis, (0, 0), (SIZE, 24), (0, 0, 0), -1)
        cv2.putText(vis, f"{still} {t['name']} trays {t['trays']}: {len(masks)} masks", (6, 17),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        out = OUT / still / f"{t['name'].replace(' ', '_')}.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out), np.hstack([tile, vis]), [cv2.IMWRITE_JPEG_QUALITY, 85])
        mine = [r for r in rows if r["still"] == still and r["tile"] == t["name"] and r["tray_like"]]
        print(f"{still} {t['name']} trays {t['trays']}: {len(masks)} masks, tray-like {len(mine)}: "
              + "; ".join(f"{r['verdict']} [{r['trays']}] {r['area_trays']}" for r in mine), flush=True)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("stills", nargs="+")
    args = ap.parse_args(argv)
    from npec_rig.calibration_store import load_calibration

    det = trays.detector()
    model = FastSam(HEF_PATH)
    rows: list[dict] = []
    try:
        for still in args.stills:
            stem = trays.capture_info(still)["calibration"]
            sf = load_calibration(trays.RIG / "calibration" / f"{stem}.json").scale_field
            run_still(still, model, sf, rows, det)
    finally:
        model.close()
    trays.write_csv(trays.HERE / "fastsam-masks.csv", rows)


if __name__ == "__main__":
    sys.exit(main())
