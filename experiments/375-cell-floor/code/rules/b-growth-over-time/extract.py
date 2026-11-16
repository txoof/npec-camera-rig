"""Map every crop's mask into the pot's own coordinates (unit square of the opening).

Writes features.npz: for each index row, a G x G grid of mask pixel counts inside the opening
(the opening mapped to [0,1] x [0,1] by the homography of its 4 corners), plus the opening size.
Only the small crop masks are read.
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path.home() / "scratch/375-cell-floor/data"
OUT = Path(__file__).resolve().parent / "features.npz"
G = 32


def homography(src, dst):
    a = []
    for (x, y), (u, v) in zip(src, dst):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y, -u])
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y, -v])
    _, _, vt = np.linalg.svd(np.array(a, float))
    return vt[-1].reshape(3, 3) / vt[-1][-1]


def main():
    rows = list(csv.DictReader(open(ROOT / "index.csv")))
    grids = np.zeros((len(rows), G, G), np.float32)
    for i, r in enumerate(rows):
        poly = json.loads(r["opening_polygon_crop_px"])
        h = homography(poly, [(0, 0), (1, 0), (1, 1), (0, 1)])
        m = np.array(Image.open(ROOT / r["mask_png"]).convert("L")) > 127
        ys, xs = np.nonzero(m)
        if len(xs):
            p = h @ np.vstack([xs + 0.5, ys + 0.5, np.ones(len(xs))])
            u, v = p[0] / p[2], p[1] / p[2]
            ok = (u >= 0) & (u < 1) & (v >= 0) & (v < 1)
            np.add.at(grids[i], ((v[ok] * G).astype(int), (u[ok] * G).astype(int)), 1)
        if i % 500 == 0:
            print(i, file=sys.stderr)
    np.savez_compressed(OUT, grids=grids)


if __name__ == "__main__":
    main()
