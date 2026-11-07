"""Per-crop geometric features for the 'solid part away from the walls' rule (a-centre-core).

Uses only the mask crop, the pot opening polygon and its size. No labels are read here.
Writes features.csv (one row per index.csv row).
"""
import csv, json, sys
from collections import deque
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
OUT = Path(__file__).resolve().parent / "features.csv"
SCALES = (0.4, 0.5, 0.6, 0.7, 0.8)   # inner window, linear fraction of the opening about its centre
MAXDEPTH = 12


def poly_mask(shape, poly):
    im = Image.new("1", (shape[1], shape[0]), 0)
    ImageDraw.Draw(im).polygon([tuple(p) for p in poly], fill=1)
    return np.array(im, dtype=bool)


def scaled(poly, s):
    p = np.array(poly, float)
    c = p.mean(0)
    return c + (p - c) * s


def depth_map(m):
    """Chessboard erosion depth: number of 3x3 erosions a pixel survives (+1), capped."""
    d = np.zeros(m.shape, np.int16)
    cur = m.copy()
    for k in range(1, MAXDEPTH + 1):
        d[cur] = k
        p = np.pad(cur, 1)
        e = cur.copy()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                e &= p[1 + dy:1 + dy + m.shape[0], 1 + dx:1 + dx + m.shape[1]]
        cur = e
        if not cur.any():
            break
    return d


def components(m):
    """8-connected labelling by BFS over mask pixels only."""
    lab = np.zeros(m.shape, np.int32)
    ys, xs = np.nonzero(m)
    H, W = m.shape
    n = 0
    for y0, x0 in zip(ys, xs):
        if lab[y0, x0]:
            continue
        n += 1
        lab[y0, x0] = n
        q = deque([(y0, x0)])
        while q:
            y, x = q.popleft()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < H and 0 <= xx < W and m[yy, xx] and not lab[yy, xx]:
                        lab[yy, xx] = n
                        q.append((yy, xx))
    return lab, n


def features(row):
    mask = np.array(Image.open(DATA / row["mask_png"]).convert("L")) > 127
    poly = json.loads(row["opening_polygon_crop_px"])
    opening = poly_mask(mask.shape, poly)
    m = mask & opening
    side = float(np.sqrt(opening.sum()))
    f = {"side_px": round(side, 1), "px": int(m.sum())}
    inner = {s: poly_mask(mask.shape, scaled(poly, s)) for s in SCALES}
    for s in SCALES:
        f[f"in{int(s*100)}"] = int((m & inner[s]).sum())
    if not m.any():
        f.update(maxdepth=0, best=json.dumps([]))
        return f
    d = depth_map(m)
    f["maxdepth"] = int(d.max())
    for s in SCALES:
        f[f"depth_in{int(s*100)}"] = int(d[inner[s]].max())
    # per piece: size, max depth, share inside each inner window; keep the 5 largest
    if m.sum() > 200000:
        pieces = []
    else:
        lab, n = components(m)
        pieces = []
        sizes = np.bincount(lab.ravel())
        order = np.argsort(-sizes[1:])[:5] + 1
        for i in order:
            pm = lab == i
            p = {"n": int(sizes[i]), "depth": int(d[pm].max())}
            for s in SCALES:
                p[f"sh{int(s*100)}"] = round(float((pm & inner[s]).sum()) / sizes[i], 3)
            pieces.append(p)
    f["best"] = json.dumps(pieces)
    return f


def main():
    rows = list(csv.DictReader(open(DATA / "index.csv")))
    keys = ["rig", "experiment_id", "tray_id", "cell", "taken_at_utc"]
    out = []
    for i, r in enumerate(rows):
        f = features(r)
        out.append({**{k: r[k] for k in keys}, **f})
        if i % 500 == 0:
            print(i, file=sys.stderr)
    cols = sorted({k for o in out for k in o}, key=lambda k: (k not in keys, k))
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, cols)
        w.writeheader()
        w.writerows(out)


if __name__ == "__main__":
    main()
