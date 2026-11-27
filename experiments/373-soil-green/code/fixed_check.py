"""Metrology log 39: tray 1's photos through grow_from_cores at this branch (the floor when the soil
level lies in the top bin), against the app's saved reading. Tag corners not passed."""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from npec_rig import segmentation as s
Image.MAX_IMAGE_PIXELS = None
for line in Path(sys.argv[1]).read_text().splitlines():
    cid, taken, path, outline, soil, grown, fixed = line.split("|")
    pts = [tuple(p) for p in json.loads(outline)]
    x0, y0 = int(min(p[0] for p in pts)), int(min(p[1] for p in pts))
    x1, y1 = int(max(p[0] for p in pts)) + 1, int(max(p[1] for p in pts)) + 1
    rgb = np.ascontiguousarray(np.asarray(Image.open(Path(sys.argv[2]) / (Path(path).name + ".jpg")).convert("RGB").crop((x0, y0, x1, y1))))
    m = Image.new("L", (x1 - x0, y1 - y0)); ImageDraw.Draw(m).polygon([(x - x0, y - y0) for x, y in pts], fill=1)
    g = s.grow_from_cores(rgb, np.asarray(m).astype(bool))
    print(taken[:16], f"saved: soil {float(soil):+.3f}, {float(grown):.0f} mm2 | branch: soil {g.soil_level:+.3f}, cutoff {g.lower_cutoff:+.3f},",
          f"hidden {g.soil_hidden}, plant px {int(g.mask.sum())}")
