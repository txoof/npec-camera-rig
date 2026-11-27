"""(1) Histogram of the greenness margin m = (2G - R - B) - lower_cutoff * (R + G + B), in code levels,
of the pixels the app counts as plant: false plant in the emptied trays, leaf pixels of the reference
truth masks, and the pixels of dense-canopy trays. (2) Before/after pictures for log 46.
Writes data/margin_hist.csv and pictures to the output folder given as argv[1]."""
import csv, json, sys, os
import cv2
import numpy as np
from PIL import Image
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import rule
from npec_rig import images, segmentation as sg
from run_photos import trays_of, TAG_SHRINK  # noqa: E402  (run_photos runs main on import: guarded below)

R = "/home/txoof/temp.nobackup/rig-copies/ac-testing/497-dark-pots"
D = __file__.rsplit("/code/", 1)[0] + "/data"
REF = __file__.rsplit("/code/", 1)[0] + "/../round3-classifier/data"
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
BINS = np.arange(-20, 201)  # margin, levels; last bin collects everything above


def margin_of(box_rgb, mask, lc):
    r, g, b = [box_rgb[..., i].astype(np.int32) for i in range(3)]
    m = (2 * g - r - b) - lc * (r + g + b)
    return m[mask]


def hist(vals):
    v = np.clip(np.floor(vals), BINS[0], BINS[-1]).astype(int)
    return np.bincount(v - BINS[0], minlength=len(BINS))


def tray_boxes(photo, apij, which):
    api = json.load(open(apij)); rgb = images.decode_full(photo)
    out = []
    for tid, outline, tag, mm2, t in trays_of(api):
        if tid not in which:
            continue
        box = sg._box(np.zeros(rgb.shape[:2], bool), outline)
        x0, y0, x1, y1 = box
        inside = sg._inside(box, outline)
        tagc = []
        if tag:
            c = np.asarray(tag, float) - [x0, y0]; ctr = c.mean(axis=0); tagc = [ctr + TAG_SHRINK * (c - ctr)]
        out.append((tid, box, inside, tagc))
    return rgb, out


rows = []
def add(group, h):
    for m, n in zip(BINS, h):
        rows.append(dict(group=group, margin=int(m), count=int(n)))

# false plant: trays 4, 5, 6 of the emptied photos (fixed area under 100 mm2)
EMPT = [("2026-11-23/110053_651340", (4,)), ("2026-11-23/120053_763671", (4,)), ("2026-11-23/130053_611736", (4, 5)), ("2026-11-23/140053_650696", (4, 5, 6))]
hf = np.zeros(len(BINS), np.int64); hc = np.zeros(len(BINS), np.int64)
for name, which in EMPT:
    rgb, tb = tray_boxes(f"{R}/e18/{name}.jpg", f"{D}/api/e18_{name.replace('/', '_')}.json", which)
    for tid, box, inside, tagc in tb:
        x0, y0, x1, y1 = box
        _t, mask, soil, lc = next(rule.grow_sweep(rgb[y0:y1, x0:x1], inside, [None], tagc))
        hf += hist(margin_of(rgb[y0:y1, x0:x1], mask, lc))
add("false plant, emptied trays", hf)

# canopy trays 4-7 of full photos (fixed area 100 mm2 or more), non-empty
CAN = [("2026-11-20/130053_661727", (4, 5, 6, 7)), ("2026-11-22/130053_643712", (4, 5, 6, 7)), ("2026-11-22/090053_635081", (4, 5, 6, 7))]
for name, which in CAN:
    rgb, tb = tray_boxes(f"{R}/e18/{name}.jpg", f"{D}/api/e18_{name.replace('/', '_')}.json", which)
    for tid, box, inside, tagc in tb:
        x0, y0, x1, y1 = box
        _t, mask, soil, lc = next(rule.grow_sweep(rgb[y0:y1, x0:x1], inside, [None], tagc))
        hc += hist(margin_of(rgb[y0:y1, x0:x1], mask, lc))
add("app mask in dense canopy trays 4-7 (upper bound on leaf)", hc)

# reference cells: truth pixels the app also counts, and truth pixels the app misses
ht = np.zeros(len(BINS), np.int64); hm = np.zeros(len(BINS), np.int64)
for m in csv.DictReader(open(REF + "/manifest.csv")):
    name = m["file"].rsplit(".", 1)[0]
    rgb = np.asarray(Image.open(f"{REF}/crops/{name}.png").convert("RGB"))
    truth = np.asarray(Image.open(f"{REF}/truth/{name}_truth.png").convert("L")) > 127
    _t, mask, soil, lc = next(rule.grow_sweep(rgb, np.ones(rgb.shape[:2], bool), [None], lower_cutoff=float(m["cut_h"])))
    ht += hist(margin_of(rgb, mask & truth, float(m["cut_h"])))
add("reference leaf pixels (truth masks, also in the app mask)", ht)
with open(D + "/margin_hist.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["group", "margin", "count"]); w.writeheader(); w.writerows(rows)

# pictures: photo | app mask | after the rule (kept green, removed red)
N = 3.0
def picture(name, tray, label, scale, crop=None):
    rgb, tb = tray_boxes(f"{R}/e18/{name}.jpg" if not name.startswith("e20/") else f"{R}/{name}.jpg",
                         (f"{D}/api/e18_{name.replace('/', '_')}.json" if not name.startswith("e20/") else f"{D}/api/e20_{name[4:]}.json"), (tray,))
    tid, box, inside, tagc = tb[0]
    x0, y0, x1, y1 = box
    sub = rgb[y0:y1, x0:x1]
    res = list(rule.grow_sweep(sub, inside, [None, N], tagc, form="B"))
    base, after = res[0][1], res[1][1]
    h, w = sub.shape[:2]
    small = cv2.resize(sub, (w // scale, h // scale), interpolation=cv2.INTER_AREA)
    def over(mask_keep, mask_gone):
        o = small.copy()
        k = cv2.resize(mask_keep.view(np.uint8), (w // scale, h // scale), interpolation=cv2.INTER_NEAREST) > 0
        g = cv2.resize(mask_gone.view(np.uint8), (w // scale, h // scale), interpolation=cv2.INTER_NEAREST) > 0
        o[k] = (0.4 * o[k] + 0.6 * np.array([0, 230, 60])).astype(np.uint8)
        o[g] = (0.3 * o[g] + 0.7 * np.array([255, 0, 0])).astype(np.uint8)
        return o
    gone = base & ~after
    panels = [small, over(base, np.zeros_like(base)), over(after, gone)]
    sheet = np.concatenate([np.pad(p, ((0, 0), (0, 6), (0, 0)), constant_values=255) for p in panels], axis=1)
    Image.fromarray(sheet).save(f"{OUT}/{label}.jpg", quality=88)
    print(label, "app px", int(base.sum()), "after", int(after.sum()), "removed", int(gone.sum()))

picture("2026-11-23/130053_611736", 4, "tray4-emptied-2026-11-23T1300", 4)
picture("2026-11-22/090053_635081", 7, "tray7-canopy-2026-11-22T0900", 4)
picture("2026-11-22/200053_652827", 10, "tray10-target-2026-11-22T2000", 4)
