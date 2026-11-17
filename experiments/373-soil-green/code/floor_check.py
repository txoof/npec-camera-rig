"""Metrology log 38: tray 1's plant pixels by grow from leaf cores as the app sets the cutoff, and
with the cutoff held at its floor (GROWN_FLOOR). Tag corners not passed (the white-paper rule
still takes the tag sheet out), so pixel counts differ slightly from the app's."""
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
    inside = np.asarray(m).astype(bool)
    auto = s.grow_from_cores(rgb, inside)
    floor = s.grow_from_cores(rgb, inside, lower_cutoff=s.GROWN_FLOOR)
    print(taken[:16], f"app: soil {soil}, {grown} mm2 |", f"here auto: soil {auto.soil_level:+.3f} cutoff {auto.lower_cutoff:+.3f} px {int(auto.mask.sum())}",
          f"| floor {s.GROWN_FLOOR}: px {int(floor.mask.sum())}")
