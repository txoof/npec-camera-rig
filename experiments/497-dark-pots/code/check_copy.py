"""The experiment-side copy equals the app's grow_from_cores (rule off): pixels different, 0 expected."""
import sys
import numpy as np
from PIL import Image
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import rule
from npec_rig import segmentation as sg

p = sys.argv[1]
rgb = np.asarray(Image.open(p).convert("RGB"))[3000:4500, 2000:3500]
inside = np.ones(rgb.shape[:2], bool)
app = sg.grow_from_cores(rgb, inside)
mine = next(rule.grow_sweep(rgb, inside, [None]))[1]
print("pixels different:", int((app.mask != mine).sum()), "of", int(app.mask.sum()))
