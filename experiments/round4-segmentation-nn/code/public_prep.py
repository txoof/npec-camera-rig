"""#406 stage D0: the 7 allowed public plant sets made ready for pre-training, and the D1u unseen-species check.

    public_prep.py widths                    # plant-part width in px, ours (half resolution) and each set (native)
    public_prep.py cache --set NAME          # cut one set to 320 px patches (256 tiles, +-32 jitter margin)
    public_prep.py relabel_sheet             # d0-aradeepopsis-relabel.png and the relabel table
    public_prep.py samples                   # d0-public-samples.png: tiles of every set
    public_prep.py summary                   # results/public_tiles.csv and the D0 part of stage-D1.md's inputs
    public_prep.py d1u                       # stage D1u: score on ARADEEPOPSIS (stage-D1u.md, stage-D1u.png)
    public_prep.py d2u                       # stage D2: D2 scored on ARADEEPOPSIS, seen in training (results/d2u_table.md)
  (drivers: analysis/train/run_d.sh, run_de.sh, resumable)

Method (written before the run, 2026-11-20).

Sets and our convention. Labels become 0 not plant, 1 plant, 255 ignore (not scored, not trained on).
  VegAnn (CC BY 4.0): nadir images only (`Orientation == Nadir`, 2364 of 3775; 45 degree and hemispherical views
    are far from our top-down camera). Annotation 255 -> 1, 0 -> 0.
  ARADEEPOPSIS (CC BY 4.0): our label from the authors' own per-pixel classes (SegmentationClassRaw), decided by
    Aaron 2026-11-21: 1 healthy -> 1 plant; 3 anthocyanin-rich (purple, living leaf) -> 1 plant (living tissue;
    stressed potatoes also turn purple, and those must count); 2 senescent (yellowing, dying) -> 0 not plant (our
    truths count yellow and dying leaf as not plant); 0 -> 0; 255 (the unlabelled ring the authors left at leaf edges)
    and the stray values 248 to 254 -> 255 ignore. ("Original": classes 1 to 3 all plant, for comparison.) A first
    try with a colour rule (hue band) was dropped: it turned whole living purple rosettes into not plant.
    The three subsets overlap (decoded pixels compared, results/public_ara_photos.csv): senescentSet and anthoSet
    are mostly the same photos numbered differently (1557 shared; e.g. senescentSet 526 = anthoSet 378), labelled two
    ways (senescentSet has no class 3 and calls purple leaves class 1), and 148 rosetteSet photos are also in
    senescentSet. Each photo is used once, with the most detailed labels it has: anthoSet (classes 1, 2, 3), else
    senescentSet (1, 2: senescent separated), else rosetteSet (class 1 only: every leaf part is plant). One duplicate
    photo inside anthoSet and one inside senescentSet are dropped, and rosetteSet 301 has no mask.
    Used for D1u only in D1 (not pre-trained on).
  ALED, labelled subset (CC BY 4.0): any non-black pixel of the per-leaf colour mask -> 1, else 0; not every plant
    of a tray is labelled (916 plants in 56 trays of 20 pots), so green pieces outside the mask -> 255 (greenness >
    ALED_GREEN_EXG after a 7 x 7 median, pieces of at least ALED_GREEN_MIN_PX px: the compost is speckled green).
  Potato Leaf, Zenodo 7938231 (CC BY): labelme leaf polygons filled -> 1. The polygons are coarse and stems are
    not drawn, so (a) a band of POLY_BAND_PX native pixels on each side of every polygon edge -> 255, and (b) green
    pixels outside the polygons (greenness > GREEN_OUT_EXG and G > R, grown by GREEN_OUT_GROW px) -> 255.
  Potato Canopy, Mendeley wg3rv2rddd (CC BY 4.0): JPEG mask thresholded at 128 -> 1. It labels weeds as
    background, but weeds are plants for us, so green pixels outside the canopy mask (same rule as (b) above) -> 255,
    and a band of CANOPY_BAND_PX native pixels around the mask edge (JPEG ringing) -> 255.
  WE3DS (CC BY 4.0): class 0 void -> 255, 1 soil -> 0, 2 to 18 (crops and weeds) -> 1.
  Sugar Beets 2016 crop/weed (CC BY-SA 4.0): iMapCleaned 0 soil -> 0, 10000 sugar beet and 2xxxx weeds -> 1,
    1 (not checked) and any other value -> 255.

Scale. A network trained at half resolution should see public leaves at about the pixel size of ours. Measured,
not guessed: "plant-part width" = 4 x the mean, over plant pixels, of the distance to the nearest not-plant pixel
(for a strip of width W this is W), per image, median over images (`widths`; ours: the 42 training truths at half
resolution). Each set is resized by f = ours / theirs, rounded to a step of 0.05 and clipped to [0.2, 1.0] (reasons at SCALE),
with the physical setup as a sanity check (see results/public_scales.csv and stage-D1.md). The chosen factors are SCALE
below. Images are resized with area averaging (bilinear when enlarged). Labels: plant share and labelled share are
resized the same way; a pixel is ignore where under half of it was labelled, otherwise the plant share of its
labelled part is the soft target (0..200 as in our cache).

Tiles. As our cache (`train_cv.py`, docstring "Tile cache"): the scaled image on a 256 px grid, each square stored
as a 320 px patch (square + 32 px each side; image reflect-padded, label padded with ignore). Per image: every
square with plant up to cap_plant(set size) (4 to 64), drawn at random (seed fixed), plus up to a quarter as many
squares with >= 10% labelled pixels and no plant (at least 1). Images are taken in a seeded random order until the set holds SET_CAP patches (or the
set runs out), so the large sets are subsampled by image.

Balance. In pre-training every sample first draws a set uniformly (each of the sets used with the same probability),
then a patch uniformly within that set, so no set dominates however many patches it has.

D1u. ARADEEPOPSIS photos (each once, see above) are read like a production photo: resized by the
ARADEEPOPSIS scale, tiles of 256 with stride 192, middle kept, logits back to native size (bilinear). Networks:
the mean of the five fold models' probabilities (D1 folds `runs/s2_f<k>_pt6`, current best `runs/s2_f<k>`);
plant where the mean probability > 0.5. Grow from leaf cores: `npec_rig.segmentation.grow_from_cores` on the native
image, the whole image as inside, no tags, default cutoffs. Scored on labelled pixels only (truth 255 left out):
IoU per image (1 if both empty), area ratio predicted / truth px (left out where the truth is empty), pooled IoU,
mean IoU, mean abs(area ratio - 1), per label source and for anthoSet photos with and without much purple (class 3
over ARA_PURPLE_MIN of the authors' plant pixels), against our labels and against the authors' masks with every leaf
class as plant.

D2 on ARADEEPOPSIS (`d2u`, information only). D2 (train_cv.py docstring) was pre-trained on all seven sets, ARADEEPOPSIS
included: every one of its photos gave one tile (the photo at x0.45 is smaller than one 256 px square), so every photo
was seen in training. D2's five fold models are read exactly as in D1u and tabled beside D1u's rows, labelled "seen in
training"; the purple-rich anthoSet photos are the group of interest.
"""
import argparse
import csv
import glob
import json
import math
import os
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import train_cv as T  # noqa: E402

PUB = f'{T.NN}/data/public'
PCACHE = f'{T.TRAIN}/cache/public'
SCR = T.SCR
IGN, SOFT, TILE, PAD = 255, 200, 256, 32
PATCH = TILE + 2 * PAD

SETS = ['vegann', 'aradeepopsis', 'aled', 'potato_leaf', 'potato_canopy', 'we3ds', 'sugarbeets']
PRETRAIN_D1 = ['vegann', 'aled', 'potato_leaf', 'potato_canopy', 'we3ds', 'sugarbeets']   # ARADEEPOPSIS left out
NAMES = {'vegann': 'VegAnn', 'aradeepopsis': 'ARADEEPOPSIS', 'aled': 'ALED', 'potato_leaf': 'Potato Leaf',
         'potato_canopy': 'Potato Canopy', 'we3ds': 'WE3DS', 'sugarbeets': 'Sugar Beets 2016'}
ARA_SUBSETS = ['ara_rosetteSet', 'ara_senescentSet', 'ara_anthoSet']

MIN_LAB = 0.10
SET_CAP = 12000
# Per image: up to cap_plant(n) squares with plant and a quarter as many without, where n is the set's image count,
# so a set of few large images (ALED, the potato sets) gives many squares per image and a set of many images (Sugar
# Beets, WE3DS) few per image, from more images.


def cap_plant(n_images):
    return int(min(64, max(4, math.ceil(SET_CAP / n_images))))
GREEN_OUT_EXG, GREEN_OUT_GROW = 0.10, 3       # green outside the label -> ignore (Potato Leaf, Potato Canopy)
POLY_BAND_PX, CANOPY_BAND_PX = 6, 3           # native px each side of a label edge -> ignore
ALED_GREEN_EXG, ALED_GREEN_MIN_PX = 0.15, 300  # ALED: unlabelled plants -> ignore (see load_item)

# Scale factor per set (native px -> our half-resolution px), from `widths` (results/public_scales.csv); see docstring.
# Measured factor (ours / theirs, results/public_widths.csv, 2026-11-20): VegAnn 0.379, ARADEEPOPSIS 0.440, ALED 0.460,
# Potato Leaf 0.064, Potato Canopy 0.391, WE3DS 0.540, Sugar Beets 1.371. Rounded to 0.05 and clipped to [0.2, 1.0]:
# never enlarged (an enlarged photo is blurrier than ours; Sugar Beets plants then stay a little smaller than ours,
# like our seedlings), and Potato Leaf not below 0.2: its leaf polygons merge into whole-plant blobs that the width
# measure reads as one wide part; at 0.2 its 9-10 cm pots (about 1180 px native, 11.8 px/mm) come to about 2.4 px/mm,
# our half-resolution scale (2.5 px/mm), so its potato leaves are the pixel size of ours.
SCALE = {'vegann': 0.40, 'aradeepopsis': 0.45, 'aled': 0.45, 'potato_leaf': 0.20, 'potato_canopy': 0.40,
         'we3ds': 0.55, 'sugarbeets': 1.00}

# ARADEEPOPSIS: authors' class -> our label (see docstring; Aaron, 2026-11-21). Any other value -> ignore.
ARA_CLASS_TO_OURS = {0: 0, 1: 1, 2: 0, 3: 1}
ARA_PRIORITY = ['ara_anthoSet', 'ara_senescentSet', 'ara_rosetteSet']   # label source when a photo is in several
ARA_PURPLE_MIN = 0.25    # D1u: "purple-rich" photo = class 3 is more than this share of the authors' plant (1-3) px


def log(msg):
    T.log(msg)


# ---------------------------------------------------------------- readers: (key, rgb uint8, label 0/1/255) native

def green_outside(rgb, lab, exg_min=GREEN_OUT_EXG, blur=0, min_px=0):
    """Green pixels (greenness (2G-R-B)/(R+G+B) > exg_min and G > R) outside the label, grown by GREEN_OUT_GROW px.
    blur: median filter size first (0 none); min_px: only green pieces of at least this many pixels."""
    src = cv2.medianBlur(rgb, blur) if blur else rgb
    r, g, b = [src[..., i].astype(np.float32) for i in range(3)]
    exg = (2 * g - r - b) / (r + g + b + 1e-6)
    gr = ((exg > exg_min) & (g > r)).astype(np.uint8)
    if min_px:
        n, labels, stats, _ = cv2.connectedComponentsWithStats(gr, connectivity=8)
        keep = np.zeros(n, np.uint8)
        keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_px
        gr = keep[labels]
    gr = cv2.dilate(gr, np.ones((2 * GREEN_OUT_GROW + 1,) * 2, np.uint8)) > 0
    return gr & (lab == 0)


def edge_band(mask, px):
    k = np.ones((2 * px + 1,) * 2, np.uint8)
    m = mask.astype(np.uint8)
    return (cv2.dilate(m, k) > 0) & ~(cv2.erode(m, k) > 0)


def list_items(name):
    """Every item of a set: a list of dicts with at least 'key'."""
    if name == 'vegann':
        V = f'{PUB}/vegann/extracted/VegAnn_dataset/VegAnn_dataset'
        rows = list(csv.DictReader(open(f'{V}/VegAnn_dataset.csv'), delimiter=';'))
        return [dict(key='vegann_' + r['Name'][:-4], img=f'{V}/images/{r["Name"]}', lab=f'{V}/annotations/{r["Name"]}',
                     species=r['Species'], system=r['System']) for r in rows if r['Orientation'] == 'Nadir']
    if name == 'aradeepopsis':
        return ara_items()
    if name == 'aled':
        out = []
        for g in sorted(glob.glob(f'{PUB}/aled/extracted/images_and_annotations/PSI_Tray*/tv/gt/*gt.png')):
            img = g.replace('/gt/', '/').replace('_gt.png', '.png').replace('-gt.png', '.png')   # one is named '-gt'
            out.append(dict(key='aled_' + os.path.basename(img)[:-4], img=img, lab=g))
        return out
    if name == 'potato_leaf':
        d = f'{PUB}/potato-leaf-zenodo/files'
        out = []
        for j in sorted(glob.glob(f'{d}/*.json')):
            try:
                json.load(open(j))
            except ValueError:
                continue        # IMG_8186.json is broken as published (md5 matches Zenodo): left out
            out.append(dict(key='potleaf_' + os.path.basename(j)[:-5], img=j[:-5] + '.JPG', lab=j))
        return out
    if name == 'potato_canopy':
        d = f'{PUB}/potato-canopy-mendeley'
        return [dict(key='potcan_' + os.path.basename(f)[:-4], img=f, lab=f'{d}/masks/{os.path.basename(f)}')
                for f in sorted(glob.glob(f'{d}/images/*.jpg'))]
    if name == 'we3ds':
        W = f'{PUB}/we3ds/extracted/WE3DS'
        return [dict(key='we3ds_' + os.path.basename(f)[:-4], img=f, lab=f'{W}/annotations/segmentation/SegmentationLabel/{os.path.basename(f)}')
                for f in sorted(glob.glob(f'{W}/images/*.png'))]
    if name == 'sugarbeets':
        out = []
        for f in sorted(glob.glob(f'{PUB}/sugarbeets2016/extracted/ijrr_sugarbeets_2016_annotations/CKA_*/annotations/dlp/iMapCleaned/*.png')):
            day = f.split('/')[-5]
            img = f.replace('annotations/dlp/iMapCleaned', 'images/rgb')
            if os.path.exists(img):
                out.append(dict(key=f'sb_{day}_{os.path.basename(f)[:-4]}', img=img, lab=f, day=day))
        return out
    raise ValueError(name)


def _ara_hash(f):
    import hashlib
    im = cv2.imread(f)
    return f, (hashlib.md5(im.tobytes()).hexdigest() if im is not None else '')


def ara_items():
    """ARADEEPOPSIS photos, each once, with its label source (ARA_PRIORITY); the photo table (decoded-pixel md5 of
    every file) is made once, results/public_ara_photos.csv."""
    tab = f'{T.RESULTS}/public_ara_photos.csv'
    if not os.path.exists(tab):
        from multiprocessing import Pool
        files = []
        for s in ARA_PRIORITY:
            d = f'{PUB}/aradeepopsis/extracted/{s}/rosettes'
            files += [(s, f) for f in sorted(glob.glob(f'{d}/PNGImages/*.png'), key=lambda f: int(os.path.basename(f)[:-4]))]
        with Pool(12) as pool:
            hs = dict(pool.map(_ara_hash, [f for _, f in files], chunksize=32))
        seen, rows = {}, []
        for s, f in files:          # priority order: the first source of a photo is used
            n = os.path.basename(f)[:-4]
            lab = f.replace('/PNGImages/', '/SegmentationClassRaw/')
            h = hs[f]
            if not os.path.exists(lab) or not h:
                use, why = False, 'no mask'
            elif h in seen:
                use, why = False, f'same photo as {seen[h]}'
            else:
                use, why = True, ''
                seen[h] = f'{s}_{n}'
            rows.append(dict(key=f'{s}_{n}', subset=s, img=f, lab=lab, md5_pixels=h, used=int(use), why_not=why))
        T.write_csv(tab, rows)
    return [dict(key=r['key'], subset=r['subset'], img=r['img'], lab=r['lab'])
            for r in T.read_csv(tab) if r['used'] == '1']


def relabel_ara(rgb, orig):
    """orig: ARADEEPOPSIS class map. Our label (0/1/255) from the authors' classes (ARA_CLASS_TO_OURS); rgb unused
    (kept for the callers)."""
    lut = np.full(256, IGN, np.uint8)
    for c, v in ARA_CLASS_TO_OURS.items():
        lut[c] = v
    return lut[orig]


def ara_original(orig):
    """The authors' masks with every leaf class (1 to 3) as plant, other non-0 values ignore."""
    lut = np.full(256, IGN, np.uint8)
    lut[0] = 0
    lut[1:4] = 1
    return lut[orig]


def load_item(name, it, ara='relabelled'):
    """(rgb, label) at native size. ara: 'relabelled' or 'original' for ARADEEPOPSIS."""
    # EXIF orientation applied (OpenCV default): the labelme polygons of the portrait Potato Leaf photos are drawn on
    # the turned image (their imageHeight / imageWidth match it; checked by the assert below)
    rgb = cv2.cvtColor(cv2.imread(it['img'], cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    if name == 'vegann':
        a = cv2.imread(it['lab'], 0)
        lab = (a > 127).astype(np.uint8)
    elif name == 'aradeepopsis':
        o = cv2.imread(it['lab'], 0)
        if ara == 'original':
            lab = ara_original(o)
        else:
            lab = relabel_ara(rgb, o)
    elif name == 'aled':
        a = cv2.imread(it['lab'], cv2.IMREAD_UNCHANGED)
        lab = (a[..., :3].max(axis=2) > 0).astype(np.uint8)
        # not every plant in a tray is labelled (916 of 56 x 20 pots); the compost is speckled with greenish pixels
        # (99th percentile greenness 0.14 to 0.29, plants' median 0.24 to 0.32), so: 7 x 7 median first, stricter
        # cutoff, pieces of at least ALED_GREEN_MIN_PX native pixels
        lab[green_outside(rgb, lab, ALED_GREEN_EXG, 7, ALED_GREEN_MIN_PX)] = IGN
    elif name == 'potato_leaf':
        j = json.load(open(it['lab']))
        assert (j['imageHeight'], j['imageWidth']) == rgb.shape[:2], (it['key'], rgb.shape)
        m = np.zeros(rgb.shape[:2], np.uint8)
        for sh in j['shapes']:
            if sh['shape_type'] == 'polygon':
                cv2.fillPoly(m, [np.round(np.array(sh['points'])).astype(np.int32).reshape(-1, 1, 2)], 1)
        lab = m.copy()
        band = np.zeros_like(m)
        for sh in j['shapes']:
            if sh['shape_type'] == 'polygon':
                cv2.polylines(band, [np.round(np.array(sh['points'])).astype(np.int32).reshape(-1, 1, 2)], True, 1,
                              thickness=2 * POLY_BAND_PX + 1)
        go = green_outside(rgb, m)
        lab[band > 0] = IGN
        lab[go] = IGN
    elif name == 'potato_canopy':
        a = cv2.imread(it['lab'], 0)
        if a.shape != rgb.shape[:2] and a.shape == rgb.shape[1::-1]:
            a = np.ascontiguousarray(a.T)       # not expected; checked in `widths`
        assert a.shape == rgb.shape[:2], (it['key'], a.shape, rgb.shape)
        m = (a >= 128).astype(np.uint8)
        lab = m.copy()
        lab[green_outside(rgb, m)] = IGN
        lab[edge_band(m, CANOPY_BAND_PX)] = IGN
    elif name == 'we3ds':
        a = cv2.imread(it['lab'], 0)
        lab = np.where(a >= 2, 1, 0).astype(np.uint8)
        lab[a == 0] = IGN
    elif name == 'sugarbeets':
        a = cv2.imread(it['lab'], cv2.IMREAD_UNCHANGED)
        lab = np.full(a.shape, IGN, np.uint8)
        lab[a == 0] = 0
        lab[a >= 10000] = 1
    assert lab.shape == rgb.shape[:2], (it['key'], lab.shape, rgb.shape)
    return rgb, lab


# ---------------------------------------------------------------- widths (to set the scale)

def part_width(plant):
    """4 x mean distance to the nearest not-plant pixel over plant pixels (W for a strip of width W). The image
    border counts as not plant (padded), so full-cover images are bounded by their size."""
    if plant.sum() < 20:
        return None
    m = cv2.copyMakeBorder(plant.astype(np.uint8), 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    d = cv2.distanceTransform(m, cv2.DIST_L2, 5)[1:-1, 1:-1]
    return 4 * float(d[plant].mean())


def _width_one(args):
    name, it = args
    try:
        rgb, lab = load_item(name, it, ara='original')
    except AssertionError as e:
        return it['key'], None, None, str(e)
    plant = lab == 1
    if name == 'aradeepopsis':
        plant = lab != 0       # the authors' ignore ring lies between leaves: count it with the plant here
    return it['key'], part_width(plant), float(plant.mean()), f'{rgb.shape[1]}x{rgb.shape[0]}'


def cmd_widths(a):
    from multiprocessing import Pool
    rows = []
    # ours: training truths at half resolution (soft truth > 0.5)
    ours = []
    for r in T.cells():
        _, truth = T.load_crop(r['name'])
        t = T.scale_truth(truth, 2) > SOFT // 2
        w = part_width(t)
        if w:
            ours.append(w)
    rows.append(dict(set='ours (42 training truths, half resolution)', images=len(ours), median_width_px=round(float(np.median(ours)), 1),
                     p25=round(float(np.percentile(ours, 25)), 1), p75=round(float(np.percentile(ours, 75)), 1),
                     median_cover='', sizes=''))
    target = float(np.median(ours))
    for name in SETS:
        items = list_items(name)
        rng = random.Random('widths-' + name)
        smp = rng.sample(items, min(200, len(items)))
        with Pool(12) as pool:
            res = pool.map(_width_one, [(name, it) for it in smp])
        bad = [r for r in res if r[1] is None and r[3] and not r[3][0].isdigit()]
        ws = [r[1] for r in res if r[1]]
        cov = [r[2] for r in res if r[2] is not None]
        sizes = sorted({r[3] for r in res if r[3] and r[3][0].isdigit()})
        f = target / float(np.median(ws))
        rows.append(dict(set=name, images=len(ws), median_width_px=round(float(np.median(ws)), 1),
                         p25=round(float(np.percentile(ws, 25)), 1), p75=round(float(np.percentile(ws, 75)), 1),
                         median_cover=round(float(np.median(cov)), 3),
                         sizes=' '.join(sizes[:4]) + (' ...' if len(sizes) > 4 else ''),
                         factor_measured=round(f, 3), items_total=len(items), load_errors=len(bad)))
        if bad:
            print(name, 'load errors', bad[:3])
    T.write_csv(f'{T.RESULTS}/public_widths.csv', [dict({k: '' for k in rows[-1]}, **r) for r in rows])
    for r in rows:
        print(r)


# ---------------------------------------------------------------- scaling and tiles

def scale_pair(rgb, lab, f):
    if abs(f - 1) < 1e-6:
        tgt = np.where(lab == 1, SOFT, 0).astype(np.uint8)
        tgt[lab == IGN] = IGN
        return rgb, tgt
    h, w = lab.shape
    size = (max(1, round(w * f)), max(1, round(h * f)))
    interp = cv2.INTER_AREA if f < 1 else cv2.INTER_LINEAR
    img = cv2.resize(rgb, size, interpolation=interp)
    valid = cv2.resize((lab != IGN).astype(np.float32), size, interpolation=interp)
    plant = cv2.resize((lab == 1).astype(np.float32), size, interpolation=interp)
    tgt = np.round(np.clip(plant / np.maximum(valid, 1e-6), 0, 1) * SOFT).astype(np.uint8)
    tgt[valid < 0.5] = IGN
    return img, tgt


def _cache_one(args):
    name, it, f, cap = args
    out = f'{PCACHE}/{name}/{it["key"]}'
    if os.path.exists(out + '_tgt.npy'):
        return it['key'], np.load(out + '_tgt.npy', mmap_mode='r').shape[0], 'exists'
    if os.path.exists(out + '_empty'):
        return it['key'], 0, 'exists'
    rgb, lab = load_item(name, it)
    img, tgt = scale_pair(rgb, lab, f)
    del rgb, lab
    H, W = tgt.shape
    gh, gw = math.ceil(H / TILE), math.ceil(W / TILE)
    ph_, pw_ = gh * TILE + 2 * PAD, gw * TILE + 2 * PAD
    imgp = cv2.copyMakeBorder(img, PAD, ph_ - H - PAD, PAD, pw_ - W - PAD, cv2.BORDER_REFLECT_101)
    tgtp = cv2.copyMakeBorder(tgt, PAD, ph_ - H - PAD, PAD, pw_ - W - PAD, cv2.BORDER_CONSTANT, value=IGN)
    plant, neg = [], []
    for gy in range(gh):
        for gx in range(gw):
            core = tgtp[PAD + gy * TILE:PAD + (gy + 1) * TILE, PAD + gx * TILE:PAD + (gx + 1) * TILE]
            labd = core != IGN
            if ((core > 0) & labd).any():
                plant.append((gy, gx))
            elif labd.mean() >= MIN_LAB:
                neg.append((gy, gx))
    rng = random.Random(f'{it["key"]}-public')
    rng.shuffle(plant)
    rng.shuffle(neg)
    keep = plant[:cap] + neg[:max(1, cap // 4)]
    if not keep:
        open(out + '_empty', 'w').close()
        return it['key'], 0, 'empty'
    ims = np.stack([imgp[gy * TILE:gy * TILE + PATCH, gx * TILE:gx * TILE + PATCH] for gy, gx in keep])
    tgs = np.stack([tgtp[gy * TILE:gy * TILE + PATCH, gx * TILE:gx * TILE + PATCH] for gy, gx in keep])
    np.save(out + '_img.tmp.npy', ims)
    np.save(out + '_tgt.tmp.npy', tgs)
    os.replace(out + '_img.tmp.npy', out + '_img.npy')
    os.replace(out + '_tgt.tmp.npy', out + '_tgt.npy')
    return it['key'], len(keep), 'new'


def cmd_cache(a):
    from multiprocessing import Pool
    name = a.set
    done_f = f'{PCACHE}/{name}/index.csv'
    if os.path.exists(done_f) and not a.force:
        log(f'D0 tiles {NAMES[name]}: skipped, already done ({done_f})')
        return
    free = __import__('shutil').disk_usage(T.TRAIN).free
    if free - 6 * 2 ** 30 < 100 * 2 ** 30:
        log(f'D0 tiles {NAMES[name]}: STOPPED, only {free / 2 ** 30:.0f} GiB free, would leave under 100 GiB')
        sys.exit(1)
    os.makedirs(f'{PCACHE}/{name}', exist_ok=True)
    items = list_items(name)
    order = items[:]
    random.Random('order-' + name).shuffle(order)
    f = SCALE[name]
    cap = cap_plant(len(items))
    log(f'D0 tiles {NAMES[name]}: {len(items)} images, scale x{f}, up to {cap} plant squares per image, up to {SET_CAP} patches')
    total, used, rows = 0, 0, []
    with Pool(a.workers) as pool:
        for key, n, msg in pool.imap(_cache_one, [(name, it, f, cap) for it in order], chunksize=4):
            used += 1
            total += n
            if n:
                rows.append(dict(key=key, patches=n))
            if total >= SET_CAP:
                pool.terminate()
                break
            if used % 500 == 0:
                log(f'D0 tiles {NAMES[name]}: {used} images, {total} patches so far')
    T.write_csv(done_f + '.tmp', rows)
    os.replace(done_f + '.tmp', done_f)
    log(f'D0 tiles {NAMES[name]} done: {total} patches from {used} images (of {len(items)}), scale x{f}')


def set_index(name):
    return T.read_csv(f'{PCACHE}/{name}/index.csv')


# ---------------------------------------------------------------- pictures

def overlay(rgb, lab_or_soft, soft=False):
    """plant solid magenta on a grey copy; ignore cyan."""
    g = cv2.cvtColor(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), cv2.COLOR_GRAY2RGB)
    if soft:
        g[(lab_or_soft != IGN) & (lab_or_soft > SOFT // 2)] = (255, 0, 255)
    else:
        g[lab_or_soft == 1] = (255, 0, 255)
    g[lab_or_soft == IGN] = (0, 200, 255)
    return g


def head(txt, w, h=None):
    h = h or 18 * len(txt) + 6
    b = np.full((h, w, 3), 255, np.uint8)
    for i, t in enumerate(txt):
        cv2.putText(b, t, (4, 15 + 18 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 1, cv2.LINE_AA)
    return b


def ara_stats(it):
    rgb = cv2.cvtColor(cv2.imread(it['img']), cv2.COLOR_BGR2RGB)
    o = cv2.imread(it['lab'], 0)
    lab = relabel_ara(rgb, o)
    plant = (o >= 1) & (o <= 3)
    n = int(plant.sum())
    r = dict(key=it['key'], subset=it['subset'], orig_plant_px=n,
             to_not_plant=int((plant & (lab == 0)).sum()), to_ignore=int((plant & (lab == IGN)).sum()),
             kept=int((lab == 1).sum()))
    for c in (1, 2, 3):
        m = o == c
        r[f'class{c}_px'] = int(m.sum())
        r[f'class{c}_to_not_plant'] = int((m & (lab == 0)).sum())
        r[f'class{c}_to_ignore'] = int((m & (lab == IGN)).sum())
    return r


def cmd_relabel_sheet(a):
    from multiprocessing import Pool
    items = list_items('aradeepopsis')
    f = f'{T.RESULTS}/public_ara_relabel.csv'
    if not os.path.exists(f) or a.force:
        with Pool(12) as pool:
            rows = pool.map(ara_stats, items, chunksize=16)
        T.write_csv(f, rows)
    rows = T.read_csv(f)
    for r in rows:
        for k in r:
            if k not in ('key', 'subset'):
                r[k] = int(r[k])
        r['share'] = r['to_not_plant'] / r['orig_plant_px'] if r['orig_plant_px'] else 0.0
    by = {it['key']: it for it in items}
    # pick 8 by a fixed rule: per subset, the image at the given quantile of the share moved to not plant
    rule = [('ara_rosetteSet', 0.5), ('ara_rosetteSet', 1.0), ('ara_senescentSet', 0.5), ('ara_senescentSet', 0.9),
            ('ara_senescentSet', 1.0), ('ara_anthoSet', 0.5), ('ara_anthoSet', 0.9), ('ara_anthoSet', 1.0)]
    S = 300
    out = []
    for sub, q in rule:
        rr = sorted([r for r in rows if r['subset'] == sub and r['orig_plant_px'] > 0], key=lambda r: (r['share'], r['key']))
        r = rr[min(len(rr) - 1, int(round(q * (len(rr) - 1))))]
        it = by[r['key']]
        rgb = cv2.cvtColor(cv2.imread(it['img']), cv2.COLOR_BGR2RGB)
        o = cv2.imread(it['lab'], 0)
        orig = ara_original(o)
        lab = relabel_ara(rgb, o)
        pans = [(rgb, [f'{r["key"]}', f'{sub[4:]} labels, quantile {q:.1f} of share moved']),
                (overlay(rgb, orig), ["authors' classes 1-3 all plant", f'{r["orig_plant_px"]} plant px']),
                (overlay(rgb, lab), [f'our label: {100 * r["share"]:.1f}% of plant px -> not plant',
                                     f'(class 2 senescent); purple class 3 {100 * r["class3_px"] / max(1, r["orig_plant_px"]):.0f}% kept'])]
        line = []
        for im, txt in pans:
            im = cv2.resize(im, (S, S), interpolation=cv2.INTER_NEAREST)
            line += [np.vstack([head(txt, S, 42), im]), np.full((S + 42, 6, 3), 255, np.uint8)]
        out += [np.hstack(line), np.full((10, (S + 6) * 3, 3), 255, np.uint8)]
    W = out[0].shape[1]
    ht = ['ARADEEPOPSIS labels (#406 D0, rule decided by Aaron 2026-11-21). Columns: photo | authors\' classes 1-3 all plant | our label.',
          'Our label from the authors\' classes: 1 healthy and 3 anthocyanin-rich (purple, living) = plant; 2 senescent = not plant;',
          '255 and stray 248-254 = ignore. Plant solid magenta on a grey copy; ignore (the authors\' edge ring) cyan.',
          'Each photo once (the subsets overlap), labelled by anthoSet, else senescentSet, else rosetteSet (rosetteSet: class 1 only).',
          'Images picked by a fixed rule: per label source, the image at a quantile of the share moved to not plant.']
    cv2.imwrite(f'{SCR}/d0-aradeepopsis-relabel.png', cv2.cvtColor(np.vstack([head(ht, W)] + out), cv2.COLOR_RGB2BGR))
    # table per subset and class
    summ = []
    for sub in ARA_SUBSETS:
        rr = [r for r in rows if r['subset'] == sub]
        d = dict(subset=sub, images=len(rr), plant_px=sum(r['orig_plant_px'] for r in rr),
                 to_not_plant=sum(r['to_not_plant'] for r in rr), to_ignore=sum(r['to_ignore'] for r in rr))
        for c in (1, 2, 3):
            n = sum(r[f'class{c}_px'] for r in rr)
            d[f'class{c}_px'] = n
            d[f'class{c}_share_to_not_plant'] = round(sum(r[f'class{c}_to_not_plant'] for r in rr) / n, 4) if n else ''
            d[f'class{c}_share_to_ignore'] = round(sum(r[f'class{c}_to_ignore'] for r in rr) / n, 4) if n else ''
        d['share_to_not_plant'] = round(d['to_not_plant'] / d['plant_px'], 4)
        d['share_to_ignore'] = round(d['to_ignore'] / d['plant_px'], 4)
        d['median_image_share_to_not_plant'] = round(float(np.median([r['share'] for r in rr])), 4)
        summ.append(d)
    T.write_csv(f'{T.RESULTS}/public_ara_relabel_summary.csv', summ)
    for d in summ:
        print(d)
    log('D0 ARADEEPOPSIS relabel check written: d0-aradeepopsis-relabel.png, results/public_ara_relabel_summary.csv')


def cmd_samples(a):
    S = 150
    lines = []
    for name in SETS:
        idx = set_index(name)
        rng = random.Random('samples-' + name)
        pick = rng.sample(idx, min(6, len(idx)))
        row = []
        for r in pick:
            ims = np.load(f'{PCACHE}/{name}/{r["key"]}_img.npy', mmap_mode='r')
            tgs = np.load(f'{PCACHE}/{name}/{r["key"]}_tgt.npy', mmap_mode='r')
            j = rng.randrange(ims.shape[0])
            im, tg = np.array(ims[j][PAD:-PAD, PAD:-PAD]), np.array(tgs[j][PAD:-PAD, PAD:-PAD])
            row += [cv2.resize(im, (S, S), interpolation=cv2.INTER_AREA),
                    cv2.resize(overlay(im, tg, soft=True), (S, S), interpolation=cv2.INTER_NEAREST),
                    np.full((S, 8, 3), 255, np.uint8)]
        row = np.hstack(row)
        n = sum(int(r['patches']) for r in idx)
        lines += [head([f'{NAMES[name]}: scale x{SCALE[name]}, {n} patches from {len(idx)} images'
                        + ('  (not in D1 pre-training; D1u test only)' if name == 'aradeepopsis' else '')], row.shape[1], 22),
                  row, np.full((8, row.shape[1], 3), 255, np.uint8)]
    W = max(l.shape[1] for l in lines)
    lines = [np.pad(l, ((0, 0), (0, W - l.shape[1]), (0, 0)), constant_values=255) for l in lines]
    ht = ['Public sets cut to tiles (#406 D0): each pair is a 256 px tile at our half-resolution pixel size and its label.',
          'Plant (soft target > 0.5) solid magenta on a grey copy; ignore cyan. 6 tiles per set drawn at random (seed fixed).']
    cv2.imwrite(f'{SCR}/d0-public-samples.png', cv2.cvtColor(np.vstack([head(ht, W)] + lines), cv2.COLOR_RGB2BGR))
    log('D0 sample sheet written: d0-public-samples.png')


def cmd_summary(a):
    rows = []
    for name in SETS:
        idx = set_index(name)
        n = sum(int(r['patches']) for r in idx)
        rows.append(dict(set=name, name=NAMES[name], scale=SCALE[name], images_total=len(list_items(name)),
                         images_with_patches=len(idx), patches=n, in_d1_pretraining=name in PRETRAIN_D1,
                         sample_probability_d1=round(1 / len(PRETRAIN_D1), 4) if name in PRETRAIN_D1 else 0))
    T.write_csv(f'{T.RESULTS}/public_tiles.csv', rows)
    for r in rows:
        print(r)


# ---------------------------------------------------------------- D1u

def _grow_one(it):
    sys.path.insert(0, '/home/txoof/temp.nobackup/wt/npec-406-label-sources/src')
    from npec_rig.segmentation import grow_from_cores
    rgb = cv2.cvtColor(cv2.imread(it['img']), cv2.COLOR_BGR2RGB)
    m = grow_from_cores(rgb, np.ones(rgb.shape[:2], bool)).mask
    return it['key'], m


def score_mask(m, lab):
    v = lab != IGN
    t = (lab == 1) & v
    p = m & v
    return dict(inter=int((p & t).sum()), union=int((p | t).sum()), method_px=int(p.sum()), truth_px=int(t.sum()))


def cmd_d1u(a):
    import torch
    from multiprocessing import Pool
    items = list_items('aradeepopsis')
    out_csv = f'{T.RESULTS}/d1u_per_image.csv'
    pdir = f'{T.TRAIN}/pred/d1u'
    os.makedirs(pdir, exist_ok=True)
    f = SCALE['aradeepopsis']
    if not os.path.exists(out_csv) or a.force:
        log(f'D1u: scoring {len(items)} ARADEEPOPSIS images (grow from leaf cores, current best, D1)')
        grow = {}
        with Pool(12) as pool:
            for k, m in pool.imap_unordered(_grow_one, items, chunksize=16):
                grow[k] = m
        models = {'best': [T.load_model(2, k) for k in range(T.NFOLD)],
                  'd1': [T.load_model(2, k, '_pt6') for k in range(T.NFOLD)]}
        rows = []
        for i, it in enumerate(items):
            rgb = cv2.cvtColor(cv2.imread(it['img']), cv2.COLOR_BGR2RGB)
            o = cv2.imread(it['lab'], 0)
            labs = {'relabelled': relabel_ara(rgb, o)}
            labs['original'] = ara_original(o)
            img = rgb if abs(f - 1) < 1e-6 else cv2.resize(rgb, (round(rgb.shape[1] * f), round(rgb.shape[0] * f)),
                                                           interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_LINEAR)
            masks = {'grow': grow[it['key']]}
            for mk, ms in models.items():
                pr = np.zeros(img.shape[:2], np.float32)
                for mdl in ms:
                    lg, _ = T.infer(mdl, img)
                    pr += 1 / (1 + np.exp(-lg))
                pr /= len(ms)
                if img.shape[:2] != rgb.shape[:2]:
                    pr = cv2.resize(pr, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_LINEAR)
                masks[mk] = pr > 0.5
            for mk, m in masks.items():
                cv2.imwrite(f'{pdir}/{it["key"]}_{mk}.png', m.astype(np.uint8) * 255)
                for lk, lab in labs.items():
                    rows.append(dict(key=it['key'], subset=it['subset'], method=mk, truth=lk, **score_mask(m, lab)))
            if (i + 1) % 500 == 0:
                log(f'D1u: {i + 1} of {len(items)} images scored')
        T.write_csv(out_csv + '.tmp', rows)
        os.replace(out_csv + '.tmp', out_csv)
    rows = T.read_csv(out_csv)
    for r in rows:
        for c in ('inter', 'union', 'method_px', 'truth_px'):
            r[c] = int(r[c])
    d1u_report(rows, items)


MNAME = {'grow': 'grow from leaf cores', 'best': 'current best (no public data)', 'd1': 'D1 (6 public sets, then ours)'}


def d1u_report(rows, items):
    L = ['# Stage D1u: unseen species check on ARADEEPOPSIS', '',
         f'Written by `public_prep.py d1u` ({datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")} UTC). Development '
         'check, information only (not a decision). Neither network saw ARADEEPOPSIS: D1 was pre-trained on the other six '
         'public sets, then trained on our training cells; the current best was trained on our training cells only.', '',
         f'Networks: the mean of the five fold models\' probabilities, plant where > 0.5 (D1: `runs/s2_f<k>_pt6`; current '
         f'best: `runs/s2_f<k>`). Each image resized by x{SCALE["aradeepopsis"]} (the D0 ARADEEPOPSIS scale, so plants are '
         'about our half-resolution pixel size), tiles 256 stride 192 middle kept, probabilities back to native size. Grow from '
         'leaf cores: `grow_from_cores` on the native image, whole image as inside, no tags. Scored on labelled pixels only '
         '(truth 255 left out). Area ratio left out where the truth is empty.', '']
    rel = {r['key']: r for r in T.read_csv(f'{T.RESULTS}/public_ara_relabel.csv')}
    purple = lambda k: int(rel[k]['class3_px']) / max(1, int(rel[k]['orig_plant_px']))
    groups = [('labels of rosetteSet (class 1 only)', lambda r: r['subset'] == 'ara_rosetteSet'),
              ('labels of senescentSet (classes 1, 2)', lambda r: r['subset'] == 'ara_senescentSet'),
              ('labels of anthoSet (classes 1, 2, 3)', lambda r: r['subset'] == 'ara_anthoSet'),
              (f'anthoSet, purple-rich (class 3 > {ARA_PURPLE_MIN:.0%} of plant)',
               lambda r: r['subset'] == 'ara_anthoSet' and purple(r['key']) > ARA_PURPLE_MIN),
              (f'anthoSet, not purple-rich (class 3 <= {ARA_PURPLE_MIN:.0%})',
               lambda r: r['subset'] == 'ara_anthoSet' and purple(r['key']) <= ARA_PURPLE_MIN),
              ('all photos (each once)', lambda r: True)]
    L += [f'Photos: {len(items)}, each photo once (the three subsets overlap; see D0 and `results/public_ara_photos.csv`), '
          'grouped by which subset\'s labels it carries. Purple-rich: the authors\' class 3 (anthocyanin-rich, purple) is more '
          f'than {ARA_PURPLE_MIN:.0%} of their plant pixels; only anthoSet labels separate purple, so rosetteSet and '
          'senescentSet photos are not split this way. Neither grow from leaf cores nor our network has seen purple leaves.', '']
    for truth in ('relabelled', 'original'):
        L += [f'## Against {"our labels" if truth == "relabelled" else "the authors\' masks, every leaf class as plant"}', '',
              ('Our labels (Aaron, 2026-11-21): authors\' class 1 healthy and 3 anthocyanin-rich = plant, 2 senescent = '
               'not plant, edge ring = ignore.' if truth == 'relabelled' else
               'Original: classes 1 to 3 (green, senescent, anthocyanin) all plant.'), '',
              '| Photos (n) | Method | Pooled IoU | Mean IoU | Mean abs(area ratio - 1) | Pooled area ratio | Photos with empty truth |',
              '|---|---|---|---|---|---|---|']
        for gname, sel in groups:
            for mk in ('grow', 'best', 'd1'):
                rr = [r for r in rows if r['method'] == mk and r['truth'] == truth and sel(r)]
                if not rr:
                    continue
                st = T.stats(rr)
                L.append(f"| {gname} ({st['n']}) | {MNAME[mk]} | {st['pooled_iou']:.3f} | {st['mean_iou']:.3f} | "
                         f"{st['mean_abs_ratio_err']:.3f} | {st['pooled_ratio']:.3f} | {st['empty_truth_cells']} |")
        L.append('')
    # picture
    by = defaultdict(dict)
    for r in rows:
        if r['truth'] == 'relabelled':
            by[r['key']][r['method']] = r
    iou = lambda r: r['inter'] / r['union'] if r['union'] else 1.0
    picks = []

    def add(why, key):
        if key and key not in [p[1] for p in picks]:
            picks.append((why, key))
    sh = lambda k: (int(rel[k]['to_not_plant']) / max(1, int(rel[k]['orig_plant_px'])), k)
    cand = lambda sub: [k for k in by if k.startswith(sub + '_') and by[k]['d1']['truth_px'] > 0]
    cs = sorted(cand('ara_rosetteSet'), key=lambda k: (by[k]['d1']['truth_px'], k))
    add('rosetteSet labels: median truth size', cs[(len(cs) - 1) // 2])
    add('rosetteSet labels: smallest non-empty truth (seedling)', cs[0])
    cs = sorted(cand('ara_senescentSet'), key=sh)
    add('senescentSet labels: median share moved to not plant', cs[(len(cs) - 1) // 2])
    cs = sorted(cand('ara_anthoSet'), key=sh)
    add('anthoSet labels: median share moved to not plant', cs[(len(cs) - 1) // 2])
    add('anthoSet labels: largest share moved to not plant (truth not empty)', cs[-1])
    cs = sorted([k for k in cand('ara_anthoSet') if purple(k) > ARA_PURPLE_MIN], key=lambda k: (purple(k), k))
    add('purple-rich: median purple share', cs[(len(cs) - 1) // 2])
    rest = [k for k in by if k not in [p[1] for p in picks]]
    add('D1 worst IoU of all images', min(rest, key=lambda k: (iou(by[k]['d1']), k)))
    rest = [k for k in rest if k != picks[-1][1]]
    add('largest IoU gap between D1 and the current best', max(rest, key=lambda k: (abs(iou(by[k]['d1']) - iou(by[k]['best'])), k)))
    itm = {it['key']: it for it in items}
    S = 260
    out = []
    for why, key in picks:
        it = itm[key]
        rgb = cv2.cvtColor(cv2.imread(it['img']), cv2.COLOR_BGR2RGB)
        lab = relabel_ara(rgb, cv2.imread(it['lab'], 0))
        pans = [(rgb, [key, f"{it['subset'][4:]} labels; purple {100 * purple(key):.0f}%"]),
                (overlay(rgb, lab), ['our label (truth)', f'{int((lab == 1).sum())} plant px'])]
        for mk in ('grow', 'best', 'd1'):
            m = cv2.imread(f'{T.TRAIN}/pred/d1u/{key}_{mk}.png', 0) > 0
            r = by[key][mk]
            rat = f"{r['method_px'] / r['truth_px']:.2f}" if r['truth_px'] else 'n/a'
            pans.append((overlay(rgb, m.astype(np.uint8)), [MNAME[mk][:34], f'IoU {iou(r):.2f}  area x{rat}']))
        line = []
        for im, txt in pans:
            im = cv2.resize(im, (S, S), interpolation=cv2.INTER_NEAREST)
            line += [np.vstack([head(txt, S, 42), im]), np.full((S + 42, 6, 3), 255, np.uint8)]
        line = np.hstack(line)
        bar = np.full((22, line.shape[1], 3), 235, np.uint8)
        cv2.putText(bar, 'picked as: ' + why, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
        out += [bar, line, np.full((10, line.shape[1], 3), 255, np.uint8)]
    W = out[1].shape[1]
    ht = ['Stage D1u: unseen species (ARADEEPOPSIS Arabidopsis rosettes, blue mesh and soil). Neither network saw this set.',
          'Columns: photo | our label (classes 1 healthy + 3 purple = plant, 2 senescent = not) | grow from leaf cores | current best | D1.',
          'Plant solid magenta on a grey copy; ignore cyan. Networks: mean of the 5 fold models. Captions: IoU and area ratio',
          'against our label, labelled pixels only. Images picked by fixed rules (line above each row).']
    cv2.imwrite(f'{SCR}/stage-D1u.png', cv2.cvtColor(np.vstack([head(ht, W)] + out), cv2.COLOR_RGB2BGR))
    L += ['## Picture', '', '`stage-D1u.png`: photo | our label | grow from leaf cores | current best | D1. Picked by these rules:', '']
    L += [f'- {k}: {why}' for why, k in picks]
    L += ['', 'Files: `experiments/round4-segmentation-nn/code/public_prep.py` (method in its docstring); per-image scores '
          '`results/d1u_per_image.csv`; masks `~/temp.nobackup/npec-406-nn/analysis/train/pred/d1u/`.', '']
    open(f'{SCR}/stage-D1u.md', 'w').write('\n'.join(L))
    print('\n'.join(L))
    log('stage D1u written: stage-D1u.md, stage-D1u.png')


def cmd_d2u(a):
    """Stage D2, information only: D2's networks (mean of the 5 fold models `runs/s2_f<k>_pt7`) scored on the
    ARADEEPOPSIS photos exactly as D1u (same read, scale, threshold, labelled pixels only), beside D1u's rows for grow
    from leaf cores, the current best and D1. D2 was pre-trained on ARADEEPOPSIS (every photo gave one tile, nearly the
    whole photo at x0.45), so its rows are "seen in training", not an unseen-species check. Writes
    results/d2u_per_image.csv and results/d2u_table.md (included in stage-D2.md)."""
    items = list_items('aradeepopsis')
    out_csv = f'{T.RESULTS}/d2u_per_image.csv'
    pdir = f'{T.TRAIN}/pred/d2u'
    os.makedirs(pdir, exist_ok=True)
    f = SCALE['aradeepopsis']
    if not os.path.exists(out_csv) or a.force:
        log(f'D2 on ARADEEPOPSIS (seen in training, information only): scoring {len(items)} images')
        ms = [T.load_model(2, k, '_pt7') for k in range(T.NFOLD)]
        rows = []
        for i, it in enumerate(items):
            rgb = cv2.cvtColor(cv2.imread(it['img']), cv2.COLOR_BGR2RGB)
            o = cv2.imread(it['lab'], 0)
            labs = {'relabelled': relabel_ara(rgb, o), 'original': ara_original(o)}
            img = rgb if abs(f - 1) < 1e-6 else cv2.resize(rgb, (round(rgb.shape[1] * f), round(rgb.shape[0] * f)),
                                                           interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_LINEAR)
            pr = np.zeros(img.shape[:2], np.float32)
            for mdl in ms:
                lg, _ = T.infer(mdl, img)
                pr += 1 / (1 + np.exp(-lg))
            pr /= len(ms)
            if img.shape[:2] != rgb.shape[:2]:
                pr = cv2.resize(pr, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_LINEAR)
            m = pr > 0.5
            cv2.imwrite(f'{pdir}/{it["key"]}_d2.png', m.astype(np.uint8) * 255)
            for lk, lab in labs.items():
                rows.append(dict(key=it['key'], subset=it['subset'], method='d2', truth=lk, **score_mask(m, lab)))
            if (i + 1) % 500 == 0:
                log(f'D2 on ARADEEPOPSIS: {i + 1} of {len(items)} images scored')
        T.write_csv(out_csv + '.tmp', rows)
        os.replace(out_csv + '.tmp', out_csv)
    rows = T.read_csv(f'{T.RESULTS}/d1u_per_image.csv') + T.read_csv(out_csv)
    for r in rows:
        for c in ('inter', 'union', 'method_px', 'truth_px'):
            r[c] = int(r[c])
    rel = {r['key']: r for r in T.read_csv(f'{T.RESULTS}/public_ara_relabel.csv')}
    purple = lambda k: int(rel[k]['class3_px']) / max(1, int(rel[k]['orig_plant_px']))
    groups = [(f'anthoSet, purple-rich (class 3 > {ARA_PURPLE_MIN:.0%} of plant)',
               lambda r: r['subset'] == 'ara_anthoSet' and purple(r['key']) > ARA_PURPLE_MIN),
              (f'anthoSet, not purple-rich (class 3 <= {ARA_PURPLE_MIN:.0%})',
               lambda r: r['subset'] == 'ara_anthoSet' and purple(r['key']) <= ARA_PURPLE_MIN),
              ('all photos (each once)', lambda r: True)]
    names = dict(MNAME, d2='D2 (all 7 public sets, then ours): SEEN IN TRAINING')
    L = ['## D2 on ARADEEPOPSIS photos (seen in training, information only)', '',
         'D2 was pre-trained on ARADEEPOPSIS: every one of its 1899 photos gave one tile (nearly the whole photo at x0.45) '
         'to the pre-training, so D2\'s rows are **seen in training** and say only how well the network learned purple '
         'rosettes it was shown, not how it does on unseen plants. The other rows are D1u\'s (none of those networks saw '
         'ARADEEPOPSIS). Same reading as D1u: mean of the 5 fold models, x0.45, tiles 256 stride 192 middle kept, '
         'threshold 0.5, labelled pixels only; our labels (healthy and purple = plant, senescent = not plant).', '',
         '| Photos (n) | Method | Pooled IoU | Mean IoU | Mean abs(area ratio - 1) | Pooled area ratio |', '|---|---|---|---|---|---|']
    for gname, sel in groups:
        for mk in ('grow', 'best', 'd1', 'd2'):
            rr = [r for r in rows if r['method'] == mk and r['truth'] == 'relabelled' and sel(r)]
            st = T.stats(rr)
            L.append(f"| {gname} ({st['n']}) | {names[mk]} | {st['pooled_iou']:.3f} | {st['mean_iou']:.3f} | "
                     f"{st['mean_abs_ratio_err']:.3f} | {st['pooled_ratio']:.3f} |")
    L += ['', 'Per-image scores `results/d2u_per_image.csv`; masks `analysis/train/pred/d2u/`.', '']
    open(f'{T.RESULTS}/d2u_table.md', 'w').write('\n'.join(L))
    print('\n'.join(L))
    log('D2 on ARADEEPOPSIS written: results/d2u_table.md (seen in training, information only)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['widths', 'cache', 'relabel_sheet', 'samples', 'summary', 'd1u', 'd2u'])
    ap.add_argument('--set', choices=SETS)
    ap.add_argument('--workers', type=int, default=10)
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    globals()['cmd_' + a.cmd](a)


if __name__ == '__main__':
    main()
