"""Metrology log 38: crop a tray from a photo by its saved outline, outline drawn in magenta, a
label below the photo. python3 -I crop_tray.py LIST PHOTO_DIR OUT_DIR, LIST lines
id|taken_at|path|outline json|soil level|grown area|fixed area (from rig.db, read-only)."""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None
lst, photos, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
for line in Path(lst).read_text().splitlines():
    cid, taken, path, outline, soil, grown, fixed = line.split("|")
    pts = [tuple(p) for p in json.loads(outline)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    pad = 150
    box = (int(min(xs)) - pad, int(min(ys)) - pad, int(max(xs)) + pad, int(max(ys)) + pad)
    img = Image.open(photos / (Path(path).name + ".jpg")).convert("RGB").crop(box)
    d = ImageDraw.Draw(img)
    d.line([(x - box[0], y - box[1]) for x, y in pts + pts[:1]], fill=(255, 0, 255), width=8)
    img = img.resize((img.width // 2, img.height // 2))
    font = ImageFont.load_default(size=28)
    label = Image.new("RGB", (img.width, 110), "white")
    ImageDraw.Draw(label).multiline_text((10, 8), f"Tray 1, {taken[:16]} UTC (photo {cid})\nsoil level {float(soil):+.3f}\n"
                                         f"grow from leaf cores {float(grown):.0f} mm2, fixed cutoff {float(fixed):.0f} mm2",
                                         fill="black", font=font)
    page = Image.new("RGB", (img.width, img.height + 110), "white")
    page.paste(img, (0, 0)); page.paste(label, (0, img.height))
    page.save(out / f"tray1-{taken[:16].replace(':', '')}.jpg", quality=90)
    print(out / f"tray1-{taken[:16].replace(':', '')}.jpg")
