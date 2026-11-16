"""d-same-photo: per-crop features. Reads only the small crops. One core, numpy + PIL.

For each crop: the green score image e = ExG (same formula as segmentation.ExGSegmenter) where
G > R, else min(ExG, 0); box-smoothed over about 1 mm (peak) and 0.5 mm (hpeak) (geometric: from mm per px). Regions by normalised
Chebyshev distance d from the pot opening centre (d = 1 on the opening edge):
core d < 0.6, mid 0.6..0.8, wall 0.8..1.0 (inside the opening, against the wall).
"""
import csv, json, sys
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
OUT = Path(__file__).resolve().parent / "features.csv"
REG = {"core": (0.0, 0.6), "mid": (0.6, 0.8), "wall": (0.8, 1.0)}


def box(a, k):
    if k <= 1:
        return a
    c = np.cumsum(np.cumsum(np.pad(a, ((1, 0), (1, 0))), 0), 1)
    s = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    out = np.full(a.shape, -1.0, dtype=np.float32)
    h = k // 2
    out[h:h + s.shape[0], h:h + s.shape[1]] = s / (k * k)
    return out


def norm_dist(poly, shape):
    p = np.array(poly, float)
    c = p.mean(0)
    # two side directions from the polygon (works for any rotation)
    e1 = (p[1] - p[0] + p[2] - p[3]) / 2
    e2 = (p[3] - p[0] + p[2] - p[1]) / 2
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    v = np.stack([xx - c[0], yy - c[1]], -1)
    u1 = np.abs(v @ (e1 / np.linalg.norm(e1))) / (np.linalg.norm(e1) / 2)
    u2 = np.abs(v @ (e2 / np.linalg.norm(e2))) / (np.linalg.norm(e2) / 2)
    return np.maximum(u1, u2)


def main():
    rows = list(csv.DictReader(open(DATA / "index.csv")))
    fields = None
    with open(OUT, "w", newline="") as f:
        w = None
        for i, r in enumerate(rows):
            rgb = np.asarray(Image.open(DATA / r["rgb_png"]).convert("RGB"), dtype=np.float32)
            m = np.asarray(Image.open(DATA / r["mask_png"])) > 0
            R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
            exg = (2 * G - R - B) / (R + G + B + 1e-6)
            e = np.where(G > R, exg, np.minimum(exg, 0.0)).astype(np.float32)
            mpp = float(r["mm_per_px_calibration"])
            es = box(e, max(1, int(round(1.0 / mpp))))
            kh = max(1, int(round(0.5 / mpp)))
            eh = box(e, kh)
            eu = box(exg.astype(np.float32), kh)  # no G > R gate: day 0 seedlings are yellow-green
            ey = box(np.where(G > 0.9 * R, exg, np.minimum(exg, 0.0)).astype(np.float32), kh)
            d = norm_dist(json.loads(r["opening_polygon_crop_px"]), e.shape)
            out = {"key": "|".join([r["rig"], r["experiment_id"], r["tray_id"], r["cell"], r["taken_at_utc"]])}
            for name, (lo, hi) in REG.items():
                sel = (d >= lo) & (d < hi)
                out[f"{name}_peak"] = round(float(es[sel].max()), 4)
                out[f"{name}_hpeak"] = round(float(eh[sel].max()), 4)
                out[f"{name}_upeak"] = round(float(eu[sel].max()), 4)
                out[f"{name}_ypeak"] = round(float(ey[sel].max()), 4)
                out[f"{name}_p999"] = round(float(np.percentile(e[sel], 99.9)), 4)
                out[f"{name}_p99"] = round(float(np.percentile(e[sel], 99)), 4)
                out[f"{name}_mask"] = int(m[sel].sum())
                out[f"{name}_px"] = int(sel.sum())
            if w is None:
                w = csv.DictWriter(f, fieldnames=list(out))
                w.writeheader()
            w.writerow(out)
            if i % 500 == 0:
                print(i, flush=True)


if __name__ == "__main__":
    main()
