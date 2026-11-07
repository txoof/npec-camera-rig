"""Resample every crop's mask and ExG into pot coordinates (u, v in [0, 1] = the pot opening).

Writes features.npz: for each index row, a G x G grid over u, v in [LO, HI] holding the
fraction of mask pixels per bin and the mean ExG per bin. Reads only small crops.
"""
import csv, json, sys
import numpy as np
from PIL import Image
from pathlib import Path

DATA = Path.home() / "scratch/375-cell-floor/data"
OUT = Path(__file__).resolve().parent / "features.npz"
LO, HI, G = -0.2, 1.2, 70   # bin = 0.02 of the pot side


def homography(src, dst):
    A = []
    for (x, y), (u, v) in zip(src, dst):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y, -u])
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y, -v])
    _, _, vt = np.linalg.svd(np.array(A))
    return vt[-1].reshape(3, 3)


def order(poly):
    # unit square corners by position: (0,0) top-left in crop px, u to the right, v down
    p = np.array(poly)
    c = p.mean(0)
    ang = np.arctan2(p[:, 1] - c[1], p[:, 0] - c[0])
    tl = p[np.argmin(p[:, 0] + p[:, 1])]
    tr = p[np.argmin(-p[:, 0] + p[:, 1])]
    br = p[np.argmax(p[:, 0] + p[:, 1])]
    bl = p[np.argmax(-p[:, 0] + p[:, 1])]
    return [tl, tr, br, bl]


S = 4
_t = (np.arange(G * S) + 0.5) / (G * S) * (HI - LO) + LO
_vv, _uu = np.meshgrid(_t, _t, indexing="ij")
UV = np.stack([_uu.ravel(), _vv.ravel(), np.ones(_uu.size)])
rows = list(csv.DictReader(open(DATA / "index.csv")))
frac = np.zeros((len(rows), G, G), np.float32)
exg_mean = np.zeros((len(rows), G, G), np.float32)
for i, r in enumerate(rows):
    poly = order(json.loads(r["opening_polygon_crop_px"]))
    H = homography(poly, [(0, 0), (1, 0), (1, 1), (0, 1)])
    m = np.array(Image.open(DATA / r["mask_png"]).convert("L")) > 0
    rgb = np.asarray(Image.open(DATA / r["rgb_png"]).convert("RGB"), dtype=np.float32)
    h, w = m.shape
    Hi = np.linalg.inv(H)
    P = Hi @ UV
    xf = P[0] / P[2]; yf = P[1] / P[2]
    x = np.clip(np.round(xf).astype(int), 0, w - 1)
    y = np.clip(np.round(yf).astype(int), 0, h - 1)
    inside = (xf >= 0) & (xf < w) & (yf >= 0) & (yf < h)
    mv = m[y, x].reshape(G, S, G, S).mean((1, 3))
    px = rgb[y, x]
    R, Gc, B = px[:, 0], px[:, 1], px[:, 2]
    e = ((2 * Gc - R - B) / (R + Gc + B + 1e-6)).reshape(G, S, G, S).mean((1, 3))
    ins = inside.reshape(G, S, G, S).mean((1, 3)) > 0.5
    frac[i] = np.where(ins, mv, np.nan)
    exg_mean[i] = np.where(ins, e, np.nan)
    if i % 250 == 0:
        print(i, flush=True)
np.savez_compressed(OUT, frac=frac, exg=exg_mean, lo=LO, hi=HI, g=G)
print("done")
