"""Per-piece features for #375 (e-colour-shape). One row per connected green piece inside the
pot opening, from the RGB crop and the mask crop only. Writes pieces.csv.

Geometry used: the opening polygon (crop px). Everything else is relative to the crop's own
soil/background pixels, so no absolute size or colour constant is needed for the features."""
import csv, json, sys
from pathlib import Path
import numpy as np, cv2

ROOT = Path.home() / "scratch/375-cell-floor"
OUT = ROOT / "solutions/e-colour-shape/pieces.csv"

def exg(a):
    s = a.sum(2) + 1e-6
    r, g, b = a[..., 0] / s, a[..., 1] / s, a[..., 2] / s
    return 2 * g - r - b

def main():
    rows = list(csv.DictReader(open(ROOT / "data/index.csv")))
    f = open(OUT, "w", newline="")
    w = None
    for i, r in enumerate(rows):
        a = cv2.cvtColor(cv2.imread(str(ROOT / "data" / r["rgb_png"])), cv2.COLOR_BGR2RGB).astype(np.float32)
        m = cv2.imread(str(ROOT / "data" / r["mask_png"]), cv2.IMREAD_GRAYSCALE) > 0
        poly = np.array(json.loads(r["opening_polygon_crop_px"]), np.float32)
        op = np.zeros(m.shape, np.uint8)
        cv2.fillPoly(op, [poly.round().astype(np.int32)], 1)
        op = op.astype(bool)
        side = float(np.sqrt(op.sum()))  # opening side in px (geometric)
        # distance of each opening pixel to the opening edge, in units of the side
        dist = cv2.distanceTransform(op.astype(np.uint8), cv2.DIST_L2, 3) / side
        E = exg(a)
        blue = (a[..., 2] > a[..., 0] + 30) & (a[..., 2] > a[..., 1] + 10)
        bg = op & ~m
        soil_exg = float(np.median(E[bg])) if bg.any() else 0.0
        soil_exg_mad = float(np.median(np.abs(E[bg] - soil_exg))) + 1e-4 if bg.any() else 1e-2
        bright = a.mean(2)
        soil_bright = float(np.median(bright[bg])) if bg.any() else 1.0
        mo = (m & op).astype(np.uint8)
        n, lab, stats, cent = cv2.connectedComponentsWithStats(mo, 8)
        base = dict(rig=r["rig"], experiment_id=r["experiment_id"], tray_id=r["tray_id"], cell=r["cell"],
                    taken_at_utc=r["taken_at_utc"], side_px=round(side, 1), n_pieces=n - 1,
                    soil_exg=round(soil_exg, 4), soil_exg_mad=round(soil_exg_mad, 4))
        k5 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        for j in range(1, n):
            x, y, ww, hh, area = stats[j]
            x0, y0 = max(x - 6, 0), max(y - 6, 0)
            x1, y1 = min(x + ww + 6, m.shape[1]), min(y + hh + 6, m.shape[0])
            pc = (lab[y0:y1, x0:x1] == j)
            ring = cv2.dilate(pc.astype(np.uint8), k5).astype(bool) & ~m[y0:y1, x0:x1]
            ys, xs = np.nonzero(pc)
            if area >= 3:
                cov = np.cov(np.vstack([xs, ys]).astype(float)) + np.eye(2) * (1 / 12)
                ev = np.sort(np.linalg.eigvalsh(cov))
                elong = float(np.sqrt(ev[1] / ev[0]))
            else:
                elong = 1.0
            Ep = E[y0:y1, x0:x1]
            ring_exg = float(np.median(Ep[ring])) if ring.any() else soil_exg
            ap = a[y0:y1, x0:x1]
            pr = ap[pc]
            hsv = cv2.cvtColor(ap.astype(np.uint8)[None] if False else ap.astype(np.uint8), cv2.COLOR_RGB2HSV)
            d = dist[y0:y1, x0:x1][pc]
            row = dict(base, piece=j, area_px=int(area), area_frac=area / side**2,
                       len_frac=max(ww, hh) / side, elong=round(elong, 2),
                       edge_min=round(float(d.min()), 4), edge_mean=round(float(d.mean()), 4),
                       exg=round(float(Ep[pc].mean()), 4), exg_max=round(float(Ep[pc].max()), 4),
                       exg_vs_ring=round(float(Ep[pc].mean()) - ring_exg, 4),
                       exg_z=round((float(Ep[pc].mean()) - soil_exg) / soil_exg_mad, 2),
                       hue=round(float(np.median(hsv[..., 0][pc])), 1),
                       sat=round(float(np.median(hsv[..., 1][pc])), 1),
                       bright_rel=round(float(pr.mean()) / soil_bright, 3),
                       b_over_g=round(float(pr[:, 2].mean() / (pr[:, 1].mean() + 1e-6)), 3),
                       ring_blue=round(float(blue[y0:y1, x0:x1][ring].mean()) if ring.any() else 0.0, 3))
            if w is None:
                w = csv.DictWriter(f, fieldnames=list(row)); w.writeheader()
            w.writerow(row)
        if i % 1000 == 0:
            print(i, file=sys.stderr)
    f.close()

main()
