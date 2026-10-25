"""Profiles across the four edges of the flat green target (metrology log 17.5) in one stored still:
brightness, the green index and the mask, to see where the mask edge falls against the
half-brightness edge. Read only.

    PYTHONPATH=src python experiments/round2-tagedge/target_edges.py PHOTO.jpg CX CY OUT_DIR [EXPECTED_PX]

EXPECTED_PX: the target's calliper side times the spacing scale of tags beside it, at its height.
"""

import sys
from pathlib import Path

import cv2
import numpy as np

from npec_rig.segmentation import ExGSegmenter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import svgchart  # noqa: E402

HALF = 480  # crop half-size, px; the target is about 740 px across
BAND = 200  # rows (or columns) averaged across the middle of each edge


def main(photo, cx, cy, out, expected_px=None):
    out = Path(out)
    bgr = cv2.imread(photo)
    cx, cy = int(float(cx)), int(float(cy))
    rgb = cv2.cvtColor(bgr[cy - HALF : cy + HALF, cx - HALF : cx + HALF], cv2.COLOR_BGR2RGB)
    mask = ExGSegmenter().segment(rgb)
    f = rgb.astype(float)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    exg = (2 * g - r - b) / (r + g + b + 1e-6)
    ys, xs = np.nonzero(mask)
    # The target is the largest blob; its extent along the middle row and column.
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8))
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    blob = labels == big
    x0, y0, w, h = stats[big, :4]
    print(f"mask blob {w} x {h} px (bounding box), {blob.sum()} px")
    mid_y, mid_x = y0 + h // 2, x0 + w // 2
    rows = slice(mid_y - BAND // 2, mid_y + BAND // 2)
    cols = slice(mid_x - BAND // 2, mid_x + BAND // 2)
    profiles = {
        "west to east": (g[rows].mean(0), exg[rows].mean(0), blob[rows].mean(0)),
        "north to south": (g[:, cols].mean(1), exg[:, cols].mean(1), blob[:, cols].mean(1)),
    }
    for name, (_, _, inmask) in profiles.items():
        width = inmask.sum()
        extra = f", {width - float(expected_px):+.1f} px against the expected {float(expected_px):.1f}" if expected_px else ""
        print(f"mask across the middle {BAND} px, {name}: {width:.1f} px{extra}")
    panels, results = [], []
    for name, (green, index, inmask) in profiles.items():
        inside = np.median(green[np.nonzero(inmask > 0.99)[0]])
        outside = np.median(np.r_[green[:40], green[-40:]])
        halfway = (inside + outside) / 2
        idx = np.nonzero(inmask > 0.5)[0]
        for first, edge in ((True, idx[0]), (False, idx[-1])):
            x = np.arange(edge - 25, edge + 26)
            seg = green[x]
            above = seg > halfway
            k = int(np.nonzero(above[1:] != above[:-1])[0][0])
            cross = x[k] + (halfway - seg[k]) / (seg[k + 1] - seg[k])
            mask_edge = edge - 0.5 if first else edge + 0.5
            grow = (cross - mask_edge) if first else (mask_edge - cross)
            side = "first" if first else "second"
            results.append((name, side, grow))
            scale = max(seg) or 1
            panels.append(svgchart.panel(
                [
                    {"label": "green channel / its maximum", "points": list(zip(x, seg / scale)), "line": True},
                    {"label": "green index (mask where above 0.1)", "points": list(zip(x, index[x])), "line": True, "colour": svgchart.SERIES[2]},
                ],
                title=f"{name}, {side} edge: mask {grow:+.1f} px out",
                xlabel="pixel in crop", ylabel="value", ylim=(-0.1, 1.05),
                hlines=[(halfway / scale, "half brightness"), (0.1, "threshold 0.1")],
                vlines=[(cross, "half brightness"), (mask_edge, "mask edge")],
            ))
    svgchart.to_png(panels, out / "target_edges.png", heading=f"Flat green target: profiles across its edges, {Path(photo).name}")
    cv2.imwrite(str(out / "target_crop.jpg"), bgr[cy - HALF : cy + HALF, cx - HALF : cx + HALF])
    for name, side, grow in results:
        print(f"{name:15} {side:6} mask edge {grow:+.2f} px outside the half-brightness edge")


if __name__ == "__main__":
    main(*sys.argv[1:6])
