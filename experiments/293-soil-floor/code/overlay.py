"""Draw a stored grow-from-leaf-cores mask over one tray of a rig photo (#293).

Read only: takes copies of a photo (JPEG) and its stored `.grown.png` mask, and a tray outline
(four corners in full-size photo pixels, from `tray_reading.outline`). Writes one PNG: the tray
crop with the outline in red and the mask's pixels in magenta, at full resolution or scaled down.

    python3 overlay.py PHOTO.jpg MASK.png 'OUTLINE_JSON' OUT.png [--scale 0.5] [--margin 150]
"""

import argparse
import json

import numpy as np
from PIL import Image, ImageDraw

Image.MAX_IMAGE_PIXELS = None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("photo")
    ap.add_argument("mask")
    ap.add_argument("outline")
    ap.add_argument("out")
    ap.add_argument("--scale", type=float, default=0.5)
    ap.add_argument("--margin", type=int, default=150)
    a = ap.parse_args()

    corners = np.array(json.loads(a.outline), dtype=float)
    photo = Image.open(a.photo).convert("RGB")
    mask = Image.open(a.mask)
    w, h = photo.size
    x0, y0 = np.maximum(np.floor(corners.min(axis=0)) - a.margin, 0).astype(int)
    x1, y1 = np.minimum(np.ceil(corners.max(axis=0)) + a.margin, [w, h]).astype(int)
    crop = np.array(photo.crop((x0, y0, x1, y1)))
    m = np.array(mask.crop((x0, y0, x1, y1))) > 0
    if m.ndim == 3:
        m = m.any(axis=2)
    crop[m] = (255, 0, 255)
    img = Image.fromarray(crop)
    draw = ImageDraw.Draw(img)
    pts = [(x - x0, y - y0) for x, y in corners]
    draw.line(pts + pts[:1], fill=(255, 0, 0), width=6)
    if a.scale != 1:
        img = img.resize((round(img.width * a.scale), round(img.height * a.scale)), Image.LANCZOS)
    img.save(a.out)
    print(f"{a.out}: {int(m.sum())} mask pixels in the crop")


if __name__ == "__main__":
    main()
