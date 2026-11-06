"""#352: time and peak memory per full 64MP still for each rule. Usage: bench.py <rule> <jpg> [repeats]
rules: decode (JPEG decode only), current (the app's ExGSegmenter), fixed_low, grow_cores."""
import sys, time, resource
import numpy as np
from PIL import Image
import cv2
Image.MAX_IMAGE_PIXELS = None
rule, jpg = sys.argv[1], sys.argv[2]; reps = int(sys.argv[3]) if len(sys.argv) > 3 else 3
STRIP = 512


def low_and_core(rgb):
    H, W = rgb.shape[:2]
    low = np.empty((H, W), np.uint8); core = np.empty((H, W), bool)
    for t in range(0, H, STRIP):
        r, g, b = (rgb[t:t + STRIP, :, i].astype(np.float32) for i in range(3))
        exg = (2 * g - r - b) / (r + g + b + 1e-6)
        low[t:t + STRIP] = (exg > -0.045) & ~((b > r) & (b > g))
        core[t:t + STRIP] = (exg > 0.1) & (g > r)
    return low, core


t0 = time.perf_counter(); rgb = np.asarray(Image.open(jpg).convert('RGB')); t_dec = time.perf_counter() - t0
times = []
for _ in range(reps):
    t0 = time.perf_counter()
    if rule == 'current':
        sys.path.insert(0, '/home/pi/wt/npec-352-green-threshold/src')
        from npec_rig.segmentation import ExGSegmenter
        m = ExGSegmenter().segment(rgb)
    elif rule == 'fixed_low':
        m = low_and_core(rgb)[0].astype(bool)
    elif rule == 'grow_cores':
        low, core = low_and_core(rgb)
        n, lab = cv2.connectedComponents(low, connectivity=8, ltype=cv2.CV_32S)
        keep = np.zeros(n, bool); keep[np.unique(lab[core])] = True; keep[0] = False
        m = keep[lab]
    elif rule == 'decode':
        m = None
    times.append(time.perf_counter() - t0)
peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
print(f'{rule}: decode {t_dec:.2f} s, rule {np.median(times):.2f} s (runs {", ".join(f"{x:.2f}" for x in times)}), '
      f'peak memory {peak:.0f} MB, plant px {int(m.sum()) if m is not None else "-"}')
