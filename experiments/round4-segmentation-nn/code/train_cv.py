"""#406, log 44 stage 2: first plant / not-plant network, scored by cross-validation grouped by UTC day
on the TRAINING reference cells only, at two input scales (full and half resolution).

    train_cv.py folds                       # print the fold of every UTC day, write folds.csv
    train_cv.py cache  --scale S            # build the tile cache for scale S (1 full, 2 half)
    train_cv.py train  --scale S --fold K   # train one fold
    train_cv.py score  --scale S --fold K   # score the held-out truth cells of fold K
    train_cv.py report                      # tables over all folds and both scales, grow from leaf cores
    train_cv.py sheet                       # picture sheets
    train_cv.py timing --scale S            # time one full photo, float32, after a warm-up
    train_cv.py photo [--photo KEY]         # one whole photo predicted at both scales, pictures
    train_cv.py stage                       # stage-A.png and stage-A.md in the scratch folder, for Aaron
    train_cv.py score --scale 2 --fold K --read avg128          # stage B: A's models read with 50% overlap
    train_cv.py timing --scale 2 --read R --reads-table         # stage B: time per photo for each read
    train_cv.py compare --stage B           # stage-B.md/png; writes the winning read to runs/../stage_B_read.txt
    train_cv.py cache --scale 2 --jitter 128                    # stage C: 512 px patches around the same squares
    train_cv.py train --scale 2 --jitter 128 --fold K           # stage C: retrain with crop jitter +-128
    train_cv.py score --scale 2 --jitter 128 --fold K --read R  # stage C, read the way that won stage B
    train_cv.py compare --stage C           # stage-C.md/png
  (driver for stages B and C: analysis/train/run_bc.sh, resumable)
    train_cv.py train --scale 2 --pretrain pt6                  # stage D1: pre-train on 6 public sets (runs/pt6)
    train_cv.py train --scale 2 --fold K --init pt6 --suffix _pt6   # stage D1: then ours, as stage A
    train_cv.py score --scale 2 --fold K --suffix _pt6
    train_cv.py compare --stage D1          # stage-D1.md/png
  (driver for stages D0, D1, D1u: analysis/train/run_d.sh, resumable; public tiles and D1u: public_prep.py)
    train_cv.py truth_cells --scale 2       # after a truth edit: rebuild cache/s2/truth_cells.npz, old kept once
    train_cv.py rescore                     # after a truth edit: re-score saved predictions of earlier runs
    train_cv.py train --scale 2 --pretrain pt7                  # stage D2: pre-train on all 7 public sets (runs/pt7)
    train_cv.py train --scale 2 --fold K --init pt7 --suffix _pt7   # stage D2: then ours, as stage A
    train_cv.py score --scale 2 --fold K --suffix _pt7
    train_cv.py compare --stage D2          # stage-D2.md/png; writes the decision to analysis/train/stage_D2_decision.txt
    train_cv.py e_init                      # prints the stage E start ('pt7' if D2 passed, else nothing)
    train_cv.py train --scale 2 --fold K --epochs 40 [--init pt7] --suffix [_pt7]_e40   # stage E
    train_cv.py score --scale 2 --fold K --suffix [_pt7]_e40
    train_cv.py compare --stage E           # stage-E.md/png, stage-E-loss.png
  (driver for the truth edit, D2 and E: analysis/train/run_de.sh, resumable; D2 on ARADEEPOPSIS: public_prep.py d2u)
    train_cv.py truth_cells --scale 2 --edit-tag before_purple_check   # the purple-check truth edit (B12, B13, B19)
    train_cv.py rescore --edit-tag before_purple_check
    train_cv.py train --scale 2 --final --epochs 40 --suffix _e40      # stage F: one network on every training day
    train_cv.py score --scale 2 --final --suffix _e40                  # stage F: sanity check on the 42 (seen) cells
  (driver for F and G: analysis/train/run_fg.sh, resumable; stage F/G tables and pictures: final_fg.py;
   Hailo compile and emulator scoring: hailo_final.py)

Method (written before the first training run, 2026-11-20).

Data. Training reference cells only (`analysis/labels/ref/manifest_train.csv`, its crops and truths: 42 cells,
production 17, development 25). The test manifest and test truths are never opened. Machine labels: the
grow-from-leaf-cores PNGs of step 2 (`analysis/labels-grow/masks/<rig>/<capture_id>.png`; 0 not plant,
1 plant, 255 ignore), the photos in `results/labels_done.csv`, minus every photo with `steadiness_flag` set
(the 61 development photos of 19 November, kept for the steadiness measure): 232 photos, production 184,
development 48. Photos are decoded with `npec_rig.images.decode_full`.

Folds. Every UTC date that holds a training photo or a training truth cell is one group (both rigs
together: a date is held out on both rigs at once). The 13 dates with truth cells are dealt to 5 folds first,
largest first (development cells, then production cells) to the fold with the fewest cells of that rig; each
fold gets one of the five development cell dates. The other dates go to the folds in date order, round robin.
For fold k, the network is trained on every photo and every truth cell whose date is not in fold k, and the
truth cells of fold k are scored. Every truth cell is scored once, by a model that never saw its date.

Scale. S = 1: the photo as decoded. S = 2: downscaled by 2 with area averaging (4576 x 3472). Labels at S = 2:
per 2x2 block, ignore if fewer than 2 of its 4 pixels are labelled, otherwise the plant share of its labelled
pixels as a soft target. Truth crops at S = 2: area-averaged truth as a soft target.

Tile cache (per scale). The scaled photo is cut on a 256 px grid; each grid square is stored as a 320 x 320
patch (the square plus 32 px each side; image reflect-padded, label padded with ignore at the photo edge), so
training can take a random 256 crop (shift up to +-32 px). Kept: every patch with plant in its 256 square
(at most 150 per photo, drawn at random, seed fixed), and up to 60 patches with at least 10% labelled
pixels and no plant (drawn at random). In production reference photos, the machine label inside each
training truth cell's crop rectangle is replaced by Aaron's truth (the cell's date equals the photo's date,
so this never leaks across folds). Truth cells are also kept whole as separate samples.

Weight of Aaron's cells. Each training sample is a truth cell (random 256 crop of the scaled crop; padded
with ignore where the crop is smaller) with probability 0.125, otherwise a cached photo patch. With 34
training cells against about 30,000 to 40,000 patches this samples each truth cell several hundred times more
often than a machine patch.

Network. segmentation_models_pytorch 0.6.0 Unet, encoder mobilenet_v2 from ImageNet weights, default decoder,
1 output logit (plant), input 256 x 256, the architecture of the Hailo smoke compile with one output channel
instead of two. ImageNet normalisation inside the forward pass (on the chip it is the model script's
normalization layer).

Training. AdamW, lr 5e-4, weight decay 1e-4, 150 warm-up steps then cosine to zero, batch 24, fp16 autocast
with GradScaler. Loss: binary cross-entropy (soft targets) plus soft Dice over the batch, both over labelled
pixels only (255 ignored). One "epoch" is 400 steps (9,600 samples); 15 epochs per fold (6,000 steps; set after a 1-epoch speed trial, about 9 steps a second), fixed in
advance, no early stopping, the last weights are scored. Augmentation on every sample: random 90 degree
rotation and flips; colour and brightness on purpose (log 44, "Why"), each applied with probability 0.8:
brightness x U(0.7, 1.3), contrast x U(0.75, 1.25), saturation x U(0.7, 1.3), hue rotation U(-12, 12)
degrees (kept small: yellow is not plant and lies about 40 degrees from leaf green), per-channel gain
U(0.9, 1.1) (white balance), gamma U(0.8, 1.25).

Scoring. Network in float32, threshold probability 0.5. Production cells: the whole photo at the scale, cut
into 256 tiles with stride 192 (64 px overlap), logits blended with a weight that falls off over the 32 px
next to each tile edge; at S = 2 the logit map is resized back to full size (bilinear); the cell's crop
rectangle is cut out. Development cells (no full photo; experiment 3 photos purged): the network runs on the
crop itself at the scale, reflect-padded to at least 256 px; production cells are also scored this way, as a
side figure showing what the lack of context costs. Per cell, over the whole crop: IoU (1 if both empty),
area ratio predicted px / truth px (left out where the truth is empty; no training truth is empty). Per rig:
pooled IoU (sum of intersections / sum of unions), mean IoU, mean |area ratio - 1|. Grow from leaf cores on
the same cells: its step 1 masks (`analysis/labels/grow/`) scored against the current truth files over the whole
crop; until the B21 edit these were exactly the per-cell counts of step 1 (`results/per_cell.csv`, setting
`grow core 0.07`, the numbers of score_sources.py), and `rescore` checks that only edited cells differ.

Stages B and C (method written before they were run, 2026-11-20). Half resolution only (decided in stage A).
One rule for both: the new setting is kept only if it beats the current best, for both rigs, in mean IoU and in
mean |area ratio - 1|, each by more than the standard deviation over the 5 folds of the paired per-fold
difference; otherwise the simpler setting stays. Seedlings and the corrected-cells-only subset reported too.

Stage B, reading. Stage A's five half-resolution fold models, no retraining. Old ('mid192', stage A's way, the
scores of stage A): stride 192, logits blended with the 32 px edge ramp above. New ('avg128'): stride 128 (50%
overlap), the sigmoid probability of each tile averaged under a 2D Hann weight w(i) = sin^2(pi (i + 0.5) / 256)
per axis (never exactly 0, so photo-edge pixels seen by one tile still get a value); plant where the averaged
probability > 0.5. The map is returned as the logit of the averaged probability, so the bilinear resize back to
full size at S = 2 is the same step as in A. Same cells, same models, threshold 0.5. Time per full photo
measured both ways as in A (`results/train_cv_timing_reads.csv`).

Stage C, crop jitter. The 5 half-resolution folds retrained with crop jitter +-128 px instead of +-32: a second
tile cache (`cache/s2_j128`) with 512 px patches (the 256 square plus 128 px each side; same padding rules)
around exactly the same kept grid squares (the square selection uses the same seeded draw), so only the window
shift changes. Training recipe, seeds and truth-cell sampling as above; truth cells were already cropped at
random over the whole crop and are unchanged. Run folders `runs/s2_j128_f<k>`. Read the way that won stage B.
Compared with the best of A and B by the rule.

Stage D1, public pre-training (method written before it was run, 2026-11-20). Public tiles from public_prep.py (D0:
binary labels in our convention, rescaled so plant parts are about our half-resolution pixel size, 320 px patches as
our cache). Pre-training: the same network from ImageNet weights, trained on six public sets (VegAnn, ALED, Potato
Leaf, Potato Canopy, WE3DS, Sugar Beets 2016; ARADEEPOPSIS left out for the D1u unseen-species check), each sample
drawing a set with equal probability and then a patch within it (PublicSamples), no truth cells, PRETRAIN_EPOCHS = 30
epochs of 400 steps (12,000 steps, twice stage A: the public pool, about 27,000 patches, is larger than ours, about 19,600 per fold,
and far more varied),
the stage A optimiser, warm-up, cosine schedule, loss and augmentation; fixed in advance, last weights kept
(runs/pt6). Then each fold trained on ours exactly as stage A (same data, seeds, length and learning rate), starting
from runs/pt6 instead of ImageNet (runs/s2_f<k>_pt6), read stride 192 middle kept, jitter 32. Compared with stage A's
half-resolution folds by the rule.

Truth edit B21 (2026-11-21, after D1, before D2; Aaron: purple, anthocyanin, tissue is plant). One training truth
changed (B21: 896 px of purple leaf stalk filled as plant; log in analysis/labels/truth_edits/). `truth_cells` rebuilds
the half-resolution truth cells used in training from the truth files (photo tiles untouched: B21 is a development
cell, which has no photo; the old npz is kept as truth_cells_before_B21.npz) and checks that only B21's target changed.
`rescore` re-scores every earlier run (RESCORE_RUNS: A at both scales, B, C, D1) from its saved prediction PNGs
against the new truth, with no network run and no retraining (old score files kept as scores*_before_B21.csv), and
checks that only B21's rows change. Earlier models keep the old B21 label in their training; every comparison from D2
on is scored against the new truth.

Stage D2 (method written before it was run, 2026-11-21). As D1 with all seven public sets (PRETRAIN['pt7']: D1's six
plus ARADEEPOPSIS with Aaron's labels of 2026-11-21, healthy and anthocyanin-rich = plant, senescent = not plant; see
public_prep.py), each set drawn with probability 1/7 per sample, 30 epochs of 400 steps from ImageNet (runs/pt7), then
each fold exactly as stage A starting from runs/pt7 (runs/s2_f<k>_pt7), with the edited B21 truth. Compared with the
current best (stage A, half resolution) by the rule; with D1 by the same rule as information only. Decision written to
analysis/train/stage_D2_decision.txt ('pt7' or 'none'). D2 is also scored on ARADEEPOPSIS (public_prep.py d2u) as
information only, labelled "seen in training".

Stage E (method written before it was run, 2026-11-21). Training length: the setting that stands after D2 (stage A's
recipe, or D2's start if D2 passed the rule), each fold trained for 40 epochs of 400 steps (16,000 steps) instead of 15,
the same 150-step warm-up and cosine schedule stretched over the whole run (lr reaches zero at the last step), last
weights kept, no early stopping, the same seeds and data (run folders runs/s2_f<k>_e40, or _pt7_e40). Compared with the
15-epoch folds of the same setting by the rule; 40 epochs is the less simple setting, kept only if it passes. The 15-epoch
stage A folds were trained before the B21 edit (old label in one of 34 training cells), the 40-epoch folds after it.
Training loss per epoch (step-weighted mean of the logged history) shown for both lengths (stage-E-loss.png).

Truth edit from the purple check (2026-11-21, after E was trained). Three more development truths changed (B12, B13,
B19: purple leaf tissue filled as plant; log in analysis/labels/truth_edits/). The same two commands as for B21, with
`--edit-tag before_purple_check`: `truth_cells` keeps the old npz as truth_cells_before_purple_check.npz and checks that
only those three targets changed; `rescore` keeps the old score files as scores*_before_purple_check.csv and re-scores
every run in RESCORE_RUNS (now including D2 and E) from its saved predictions. E's fold models keep the old labels of
B12, B13 and B19 in their training; the final network is trained on the new ones.

Stage F, final network (Aaron, 2026-11-21: the final settings are stage E's). One network trained on every training
day together (`--final`): stage A's recipe for 40 epochs of 400 steps, the 232 photos (steadiness photos left out),
all 42 training truth cells with the current truths, seed 100 * S - 1 (the fold formula with k = -1), a checkpoint
every epoch, run folder runs/s2_final_e40. It has no held-out score: every training cell was seen. `score --final`
runs it on the 42 cells (production on the whole photo, development on the crop) as a sanity check only, labelled
"seen in training" (pred/s2_final_e40, runs/s2_final_e40/scores.csv).
"""
import argparse
import csv
import json
import math
import os
import random
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(HERE)
RESULTS = os.path.join(EXP, 'results')
NN = '/home/txoof/temp.nobackup/npec-406-nn'
REF = f'{NN}/analysis/labels/ref'
LABELS = f'{NN}/analysis/labels-grow'
DATA = f'{NN}/data/rigs'
TRAIN = f'{NN}/analysis/train'
PROGRESS = '/home/txoof/temp.nobackup/scratch/406-train/progress.txt'

TILE, PATCH, PAD = 256, 320, 32
MAX_PLANT, MAX_NEG, MIN_LAB = 150, 60, 0.10
P_TRUTH = 0.125
BATCH, STEPS_PER_EPOCH, EPOCHS, LR, WARMUP = 24, 400, 15, 5e-4, 150
STRIDE, EDGE = 192, 32
# Ways of reading a photo (stage B): 'mid192' is stage A's (stride 192, logits blended with a linear ramp over the
# 32 px next to each tile edge, so the middle of each tile is kept); 'avg128' is 50% overlap with the tile
# probabilities averaged under a 2D Hann weight.
READS = {'mid192': dict(stride=192, blend='ramp'), 'avg128': dict(stride=128, blend='hann')}
JITTERS = (32, 128)   # crop jitter of training patches (stage C): patch = 256 + 2 * jitter
NFOLD = 5
IGN = 255
SOFT = 200          # stored target: 0..200 = plant share 0..1, 255 = ignore


def log(msg):
    line = f'{datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")} UTC  {msg}'
    print(line, flush=True)
    with open(PROGRESS, 'a') as fh:
        fh.write(line + '\n')


def read_csv(p):
    with open(p, newline='') as fh:
        return list(csv.DictReader(fh))


def write_csv(p, rows):
    with open(p, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def cells():
    man = read_csv(f'{REF}/manifest_train.csv')
    assert len(man) == 42 and all(r['split'] == 'train' for r in man)
    for r in man:
        r['name'] = r['file'].rsplit('.', 1)[0]
    return man


def photos():
    rows = [r for r in read_csv(f'{RESULTS}/labels_done.csv') if not r['steadiness_flag']]
    jpg = {(r['rig'], r['capture_id']): r['jpg'] for r in read_csv(f'{RESULTS}/labels_photos.csv')}
    for r in rows:
        r['jpg'] = jpg[(r['rig'], r['capture_id'])]
        r['key'] = f"{r['rig']}_{r['capture_id']}"
    return rows


def folds():
    """date -> fold, deterministic (see docstring)."""
    man, ph = cells(), photos()
    per = defaultdict(lambda: [0, 0])          # date -> [dev cells, prod cells]
    for r in man:
        per[r['day']][0 if r['rig'] == 'dev' else 1] += 1
    load = [[0, 0] for _ in range(NFOLD)]
    fold = {}
    for d in sorted(per, key=lambda d: (-per[d][0], -per[d][1], d)):
        if per[d][0]:
            k = min(range(NFOLD), key=lambda k: (load[k][0] > 0, load[k][1], k))
        else:
            k = min(range(NFOLD), key=lambda k: (load[k][1], load[k][0], k))
        fold[d] = k
        load[k][0] += per[d][0]
        load[k][1] += per[d][1]
    rest = sorted({r['day_utc'] for r in ph} - set(fold))
    for i, d in enumerate(rest):
        fold[d] = i % NFOLD
    return fold


# ---------------------------------------------------------------- scaling

def scale_img(rgb, s):
    if s == 1:
        return rgb
    h, w = rgb.shape[:2]
    return cv2.resize(rgb, (round(w / s), round(h / s)), interpolation=cv2.INTER_AREA)


def scale_label(lab, s):
    """0/1/255 full-size label -> 0..200 soft target / 255 at scale s."""
    if s == 1:
        out = np.where(lab == 1, SOFT, 0).astype(np.uint8)
        out[lab == IGN] = IGN
        return out
    h, w = lab.shape
    h2, w2 = h // s * s, w // s * s
    l = lab[:h2, :w2].reshape(h2 // s, s, w2 // s, s)
    lab_n = (l != IGN).sum(axis=(1, 3))
    pl_n = (l == 1).sum(axis=(1, 3))
    frac = np.divide(pl_n, np.maximum(lab_n, 1))
    out = np.round(frac * SOFT).astype(np.uint8)
    out[lab_n < 2] = IGN
    return out


def scale_truth(truth, s):
    t = truth.astype(np.float32)
    if s != 1:
        h, w = t.shape
        t = cv2.resize(t, (round(w / s), round(h / s)), interpolation=cv2.INTER_AREA)
    return np.round(t * SOFT).astype(np.uint8)


def load_crop(name):
    rgb = cv2.cvtColor(cv2.imread(f'{REF}/crops/{name}.png'), cv2.COLOR_BGR2RGB)
    truth = cv2.imread(f'{REF}/truth/{name}_truth.png', 0) > 0
    return rgb, truth


# ---------------------------------------------------------------- cache

def cache_dir(s, jitter=PAD):
    return f'{TRAIN}/cache/s{s}' if jitter == PAD else f'{TRAIN}/cache/s{s}_j{jitter}'


def cache_one(args):
    p, s, overrides, pad = args
    patch = TILE + 2 * pad
    sys.path.insert(0, '/home/txoof/temp.nobackup/wt/npec-406-label-sources/src')
    from npec_rig.images import decode_full
    out = f'{cache_dir(s, pad)}/mm/{p["key"]}'
    if os.path.exists(out + '_tgt.npy') or os.path.exists(out + '_empty'):
        return p['key'], 'exists'
    rgb = decode_full(f'{DATA}/{p["jpg"]}')
    lab = cv2.imread(f'{LABELS}/{p["mask"]}', cv2.IMREAD_UNCHANGED)
    assert lab.shape == rgb.shape[:2] and lab.dtype == np.uint8
    for (x, y, w, h, name) in overrides:
        _, truth = load_crop(name)
        lab[y:y + h, x:x + w] = truth.astype(np.uint8)
    img = scale_img(rgb, s)
    tgt = scale_label(lab, s)
    del rgb, lab
    H, W = tgt.shape
    gh, gw = math.ceil(H / TILE), math.ceil(W / TILE)
    ph_, pw_ = gh * TILE + 2 * pad, gw * TILE + 2 * pad
    imgp = cv2.copyMakeBorder(img, pad, ph_ - H - pad, pad, pw_ - W - pad, cv2.BORDER_REFLECT_101)
    tgtp = cv2.copyMakeBorder(tgt, pad, ph_ - H - pad, pad, pw_ - W - pad, cv2.BORDER_CONSTANT, value=IGN)
    plant, neg = [], []
    for gy in range(gh):
        for gx in range(gw):
            core = tgt[gy * TILE:(gy + 1) * TILE, gx * TILE:(gx + 1) * TILE]
            labd = core != IGN
            if ((core > 0) & labd).any():
                plant.append((gy, gx))
            elif labd.mean() >= MIN_LAB:
                neg.append((gy, gx))
    rng = random.Random(f'{p["key"]}-{s}')
    rng.shuffle(plant)
    rng.shuffle(neg)
    keep = plant[:MAX_PLANT] + neg[:MAX_NEG]
    if not keep:
        open(out + '_empty', 'w').close()
        return p['key'], 'empty'
    ims = np.stack([imgp[gy * TILE:gy * TILE + patch, gx * TILE:gx * TILE + patch] for gy, gx in keep])
    tgs = np.stack([tgtp[gy * TILE:gy * TILE + patch, gx * TILE:gx * TILE + patch] for gy, gx in keep])
    np.save(out + '_img.tmp.npy', ims)
    np.save(out + '_tgt.tmp.npy', tgs)
    os.replace(out + '_img.tmp.npy', out + '_img.npy')
    os.replace(out + '_tgt.tmp.npy', out + '_tgt.npy')
    return p['key'], f'{len(keep)} patches ({min(len(plant), MAX_PLANT)} with plant of {len(plant)})'


def cmd_cache(a):
    from multiprocessing import Pool
    s, J = a.scale, a.jitter
    C = cache_dir(s, J)
    os.makedirs(f'{C}/mm', exist_ok=True)
    if J != PAD:
        need = 30 * 2 ** 30
        free = __import__('shutil').disk_usage(TRAIN).free
        if free - need < 100 * 2 ** 30 and not os.path.exists(f'{C}/truth_cells.npz'):
            log(f'tile cache scale {s} jitter {J}: STOPPED, only {free / 2 ** 30:.0f} GiB free, would leave under 100 GiB')
            sys.exit(1)
    man, ph = cells(), photos()
    ov = defaultdict(list)
    for r in man:
        if r['rig'] == 'prod':
            ov[f"production_{r['capture_id']}"].append(
                (int(r['crop_x0']), int(r['crop_y0']), int(r['crop_w']), int(r['crop_h']), r['name']))
    assert sum(len(v) for v in ov.values()) == 17 and all(k in {p['key'] for p in ph} for k in ov)
    jobs = [(p, s, ov.get(p['key'], []), J) for p in ph]
    tag = f'scale {s}' + ('' if J == PAD else f' jitter {J}')
    t0 = time.time()
    skipped = 0
    with Pool(a.workers) as pool:
        for i, (k, msg) in enumerate(pool.imap_unordered(cache_one, jobs), 1):
            skipped += msg == 'exists'
            if (i % 10 == 0 or i == len(jobs)) and skipped < i:
                el = time.time() - t0
                log(f'building tile cache, {tag}: {i} of {len(jobs)} photos, {el / 60:.1f} min so far, '
                    f'about {el / i * (len(jobs) - i) / 60:.1f} min left')
    if skipped:
        log(f'tile cache {tag}: {skipped} of {len(jobs)} photos skipped, already cached')
    # truth cells at this scale
    tc = {}
    for r in man:
        rgb, truth = load_crop(r['name'])
        tc[r['id'] + '_img'] = scale_img(rgb, s)
        tc[r['id'] + '_tgt'] = scale_truth(truth, s)
    np.savez(f'{C}/truth_cells.npz', **tc)
    n = sum(np.load(f'{C}/mm/{p["key"]}_tgt.npy', mmap_mode='r').shape[0]
            for p in ph if os.path.exists(f'{C}/mm/{p["key"]}_tgt.npy'))
    log(f'tile cache {tag} done: {n} patches from {len(ph)} photos, {(time.time() - t0) / 60:.1f} min')


# ---------------------------------------------------------------- model, augmentation

MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


def make_model(pretrained=True):
    import segmentation_models_pytorch as smp
    return smp.Unet('mobilenet_v2', encoder_weights='imagenet' if pretrained else None, in_channels=3, classes=1)


def normalise(x):
    """x float 0..1, NCHW."""
    import torch
    m = torch.tensor(MEAN, device=x.device).view(1, 3, 1, 1)
    sd = torch.tensor(STD, device=x.device).view(1, 3, 1, 1)
    return (x - m) / sd


def colour_aug(x):
    """x float 0..1 NCHW on the GPU; per-sample random brightness, contrast, saturation, hue, gain, gamma."""
    import torch
    n = x.shape[0]
    dev = x.device

    def u(lo, hi):
        v = torch.empty(n, 1, 1, 1, device=dev).uniform_(lo, hi)
        on = (torch.rand(n, 1, 1, 1, device=dev) < 0.8).float()
        return on * v + (1 - on) * (1.0 if lo < 1 < hi else 0.0)

    gray_w = torch.tensor([0.299, 0.587, 0.114], device=dev).view(1, 3, 1, 1)
    x = x * u(0.7, 1.3)                                                     # brightness
    mean = (x * gray_w).sum(1, keepdim=True).mean((2, 3), keepdim=True)
    x = (x - mean) * u(0.75, 1.25) + mean                                   # contrast
    g = (x * gray_w).sum(1, keepdim=True)
    x = (x - g) * u(0.7, 1.3) + g                                           # saturation
    th = u(-12.0, 12.0).view(n) * math.pi / 180                            # hue, YIQ rotation
    T = torch.tensor([[0.299, 0.587, 0.114], [0.596, -0.274, -0.322], [0.211, -0.523, 0.312]], device=dev)
    Ti = torch.linalg.inv(T)
    c, s_ = torch.cos(th), torch.sin(th)
    R = torch.zeros(n, 3, 3, device=dev)
    R[:, 0, 0] = 1
    R[:, 1, 1], R[:, 1, 2], R[:, 2, 1], R[:, 2, 2] = c, -s_, s_, c
    M = Ti @ R @ T
    x = torch.einsum('nij,njhw->nihw', M, x)
    gain = torch.empty(n, 3, 1, 1, device=dev).uniform_(0.9, 1.1)
    on = (torch.rand(n, 1, 1, 1, device=dev) < 0.8).float()
    x = x * (on * gain + (1 - on))                                          # white balance
    x = x.clamp(0, 1)
    x = x ** u(0.8, 1.25)                                                   # gamma
    return x.clamp(0, 1)


# ---------------------------------------------------------------- training

class Samples:
    """Infinite random samples: photo patches of the training dates and truth cells of the training dates."""

    def __init__(self, s, keys, cell_ids, seed, jitter=PAD):
        self.s, self.keys, self.cell_ids, self.seed = s, keys, cell_ids, seed
        self.dir, self.patch = cache_dir(s, jitter), TILE + 2 * jitter

    def setup(self, wid):
        self.rng = np.random.default_rng(self.seed * 1000 + wid)
        self.patches = []          # (file index, patch index)
        self.files = []
        for i, k in enumerate(self.keys):
            img = np.load(f'{self.dir}/mm/{k}_img.npy', mmap_mode='r')
            tgt = np.load(f'{self.dir}/mm/{k}_tgt.npy', mmap_mode='r')
            assert img.shape[1] == self.patch
            self.files.append((img, tgt))
            self.patches += [(i, j) for j in range(img.shape[0])]
        z = np.load(f'{self.dir}/truth_cells.npz')
        self.cells = [(z[c + '_img'], z[c + '_tgt']) for c in self.cell_ids]

    def sample(self):
        rng = self.rng
        if self.cells and rng.random() < P_TRUTH:
            img, tgt = self.cells[rng.integers(len(self.cells))]
            h, w = tgt.shape
            if h < TILE or w < TILE:
                ph, pw = max(0, TILE - h), max(0, TILE - w)
                t0, l0 = rng.integers(ph + 1), rng.integers(pw + 1)
                img = cv2.copyMakeBorder(img, t0, ph - t0, l0, pw - l0, cv2.BORDER_REFLECT_101)
                tgt = cv2.copyMakeBorder(tgt, t0, ph - t0, l0, pw - l0, cv2.BORDER_CONSTANT, value=IGN)
                h, w = tgt.shape
            y, x = rng.integers(h - TILE + 1), rng.integers(w - TILE + 1)
        else:
            i, j = self.patches[rng.integers(len(self.patches))]
            img, tgt = self.files[i][0][j], self.files[i][1][j]
            y, x = rng.integers(self.patch - TILE + 1), rng.integers(self.patch - TILE + 1)
        img = np.ascontiguousarray(img[y:y + TILE, x:x + TILE])
        tgt = np.ascontiguousarray(tgt[y:y + TILE, x:x + TILE])
        k = rng.integers(4)
        img, tgt = np.rot90(img, k), np.rot90(tgt, k)
        if rng.random() < 0.5:
            img, tgt = img[:, ::-1], tgt[:, ::-1]
        return np.ascontiguousarray(img.transpose(2, 0, 1)), np.ascontiguousarray(tgt)


class PublicSamples:
    """Stage D pre-training: infinite random samples from the public tile caches (public_prep.py). Each sample first
    draws a set uniformly, then a patch uniformly within it, so no set dominates however many patches it holds."""

    def __init__(self, sets, seed):
        self.sets, self.seed = sets, seed

    def setup(self, wid):
        self.rng = np.random.default_rng(self.seed * 1000 + wid)
        self.files = []
        for name in self.sets:
            d = f'{TRAIN}/cache/public/{name}'
            fl = []
            for r in read_csv(f'{d}/index.csv'):
                img = np.load(f'{d}/{r["key"]}_img.npy', mmap_mode='r')
                tgt = np.load(f'{d}/{r["key"]}_tgt.npy', mmap_mode='r')
                assert img.shape[1] == PATCH
                fl += [(img, tgt, j) for j in range(img.shape[0])]
            self.files.append(fl)

    def sample(self):
        rng = self.rng
        fl = self.files[rng.integers(len(self.files))]
        img, tgt, j = fl[rng.integers(len(fl))]
        y, x = rng.integers(PATCH - TILE + 1), rng.integers(PATCH - TILE + 1)
        img = np.ascontiguousarray(img[j, y:y + TILE, x:x + TILE])
        tgt = np.ascontiguousarray(tgt[j, y:y + TILE, x:x + TILE])
        k = rng.integers(4)
        img, tgt = np.rot90(img, k), np.rot90(tgt, k)
        if rng.random() < 0.5:
            img, tgt = img[:, ::-1], tgt[:, ::-1]
        return np.ascontiguousarray(img.transpose(2, 0, 1)), np.ascontiguousarray(tgt)


PRETRAIN = {'pt6': ['vegann', 'aled', 'potato_leaf', 'potato_canopy', 'we3ds', 'sugarbeets'],   # D1: ARADEEPOPSIS out
            'pt7': ['vegann', 'aradeepopsis', 'aled', 'potato_leaf', 'potato_canopy', 'we3ds', 'sugarbeets']}   # D2: all 7
PRETRAIN_EPOCHS = 30


def cmd_train(a):
    import torch
    from torch.utils.data import DataLoader, IterableDataset, get_worker_info

    s, k, J = a.scale, a.fold, a.jitter
    C = cache_dir(s, J)
    fold = folds()
    man, ph = cells(), photos()
    pre = a.pretrain
    if a.final:
        # stage F: one network on every training day (no fold held out), all 42 truth cells
        k = -1
        keys = [p['key'] for p in ph if os.path.exists(f'{C}/mm/{p["key"]}_tgt.npy')]
        cell_ids = [r['id'] for r in man]
        run = f'{TRAIN}/runs/{final_name(s, J)}{a.suffix}'
        jt = ('' if J == PAD else f' jitter {J}') + ' final network (every training day)'
    elif pre:
        # stage D pre-training on public tiles only: one run, no fold, no truth cells
        k, keys, cell_ids = -1, [], []
        run = f'{TRAIN}/runs/{pre}'
        jt = f' public pre-training {pre} ({len(PRETRAIN[pre])} sets)'
    else:
        keys = [p['key'] for p in ph if fold[p['day_utc']] != k and os.path.exists(f'{C}/mm/{p["key"]}_tgt.npy')]
        cell_ids = [r['id'] for r in man if fold[r['day']] != k]
        run = f'{TRAIN}/runs/{run_name(s, k, J)}{a.suffix}'
        jt = ('' if J == PAD else f' jitter {J}') + (f' from {a.init}' if a.init else '')
    os.makedirs(run, exist_ok=True)
    nofold = pre or a.final
    if os.path.exists(f'{run}/model.pt') and not a.force:
        log(f'training scale {s}{jt} fold {k + 1}: skipped, already done ({run}/model.pt exists)' if not nofold else
            f'training{jt}: skipped, already done ({run}/model.pt exists)')
        return
    epochs = a.epochs or (PRETRAIN_EPOCHS if pre else EPOCHS)
    total = epochs * STEPS_PER_EPOCH

    src = PublicSamples(PRETRAIN[pre], seed=900 + s) if pre else Samples(s, keys, cell_ids, seed=100 * s + k, jitter=J)

    class DS(IterableDataset):
        def __iter__(self):
            wi = get_worker_info()
            src.setup(wi.id if wi else 0)
            while True:
                yield src.sample()

    dl = DataLoader(DS(), batch_size=BATCH, num_workers=6, pin_memory=True, persistent_workers=True,
                    prefetch_factor=4)
    torch.manual_seed(100 * s + k)
    torch.backends.cudnn.benchmark = True
    dev = 'cuda'
    model = make_model()
    if a.init:
        # stage D: start from the public pre-training (runs/<init>/model.pt) instead of ImageNet alone
        model.load_state_dict(torch.load(f'{TRAIN}/runs/{a.init}/model.pt', map_location='cpu'))
    model = model.to(dev).to(memory_format=torch.channels_last)
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda i: (i + 1) / WARMUP if i < WARMUP else 0.5 * (1 + math.cos(math.pi * (i - WARMUP) / (total - WARMUP))))
    scaler = torch.amp.GradScaler()
    if pre:
        n_patches = sum(sum(int(r['patches']) for r in read_csv(f'{TRAIN}/cache/public/{n}/index.csv')) for n in PRETRAIN[pre])
        log(f'training{jt}: {n_patches} public patches, each set drawn with probability 1/{len(PRETRAIN[pre])}, '
            f'{epochs} epochs of {STEPS_PER_EPOCH} steps, batch {BATCH}')
    else:
        n_patches = sum(np.load(f'{C}/mm/{kk}_tgt.npy', mmap_mode='r').shape[0] for kk in keys)
        log(f'training scale {s}{jt}' + ('' if a.final else f' fold {k + 1} of {NFOLD}') +
            f': {len(keys)} photos ({n_patches} patches), {len(cell_ids)} '
            f'truth cells, {epochs} epochs of {STEPS_PER_EPOCH} steps, batch {BATCH}')
    meta = dict(scale=s, fold=k, jitter=J, photos=len(keys), patches=n_patches, cells=cell_ids, epochs=epochs,
                steps=total, batch=BATCH, lr=LR, p_truth=P_TRUTH, init=a.init, pretrain=pre,
                pretrain_sets=PRETRAIN.get(pre), final=bool(a.final),
                held_out_dates=sorted(d for d, f in fold.items() if f == k))
    hist = []
    start = 0
    t_prev = 0.0
    ck = f'{run}/ckpt.pt'
    if os.path.exists(ck) and not a.force:
        c = torch.load(ck, map_location=dev, weights_only=False)
        if c['total'] == total:
            model.load_state_dict(c['model'])
            opt.load_state_dict(c['opt'])
            sched.load_state_dict(c['sched'])
            scaler.load_state_dict(c['scaler'])
            start, hist, t_prev = c['step'], c['hist'], c['seconds']
            log(f'training scale {s}{jt}' + ('' if nofold else f' fold {k + 1}') + f': resumed from the checkpoint at step {start} of {total} '
                f'(epochs before it are already done)')
    t0 = time.time() - t_prev
    tlast = time.time()
    it = iter(dl)
    run_loss = run_bce = run_dice = 0.0
    nrun = 0
    model.train()
    tlast_start = time.time()
    for step in range(start, total):
        img, tgt = next(it)
        x = img.to(dev, non_blocking=True).float().div_(255).contiguous(memory_format=torch.channels_last)
        t = tgt.to(dev, non_blocking=True)
        with torch.no_grad():
            x = normalise(colour_aug(x)).contiguous(memory_format=torch.channels_last)
        valid = (t != IGN).float().unsqueeze(1)
        y = (t.float() / SOFT).clamp(0, 1).unsqueeze(1) * valid
        with torch.autocast('cuda', dtype=torch.float16):
            logit = model(x)
        logit = logit.float()
        bce = (torch.nn.functional.binary_cross_entropy_with_logits(logit, y, reduction='none') * valid).sum() \
            / valid.sum().clamp(min=1)
        p = torch.sigmoid(logit) * valid
        dice = 1 - (2 * (p * y).sum() + 1) / (p.sum() + y.sum() + 1)
        loss = bce + dice
        opt.zero_grad(set_to_none=True)
        scaler.scale(loss).backward()
        scaler.step(opt)
        scaler.update()
        sched.step()
        run_loss += loss.item()
        run_bce += bce.item()
        run_dice += dice.item()
        nrun += 1
        now = time.time()
        if now - tlast > 50 or step + 1 == total or (step + 1) % STEPS_PER_EPOCH == 0:
            e = step // STEPS_PER_EPOCH + 1
            el = now - t0
            per_step = (time.time() - tlast_start) / (step + 1 - start)
            left = per_step * (total - step - 1)
            others = 0 if nofold else sum(1 for K in range(NFOLD) if K != k
                                       and not os.path.exists(f'{TRAIN}/runs/{run_name(s, K, J)}{a.suffix}/model.pt'))
            whole = left + others * (per_step * total + 90)
            hist.append(dict(step=step + 1, loss=run_loss / nrun, bce=run_bce / nrun, dice=run_dice / nrun,
                             seconds=round(el, 1)))
            log(f'training scale {s}{jt}' + ('' if nofold else f' fold {k + 1} of {NFOLD}') + f', epoch {e} of {epochs}, step {step + 1} of {total}, '
                f'loss {run_loss / nrun:.4f} (bce {run_bce / nrun:.4f}, dice {run_dice / nrun:.4f}), ' +
                (f'about {left / 60:.1f} min left in this fold, about {whole / 60:.0f} min until all '
                 f'training is done ({others} more folds to train after this one)' if step + 1 - start >= 50 else 'starting'))
            run_loss = run_bce = run_dice = 0.0
            nrun = 0
            tlast = now
            if (step + 1) % STEPS_PER_EPOCH == 0 and step + 1 < total:
                torch.save(dict(model=model.state_dict(), opt=opt.state_dict(), sched=sched.state_dict(),
                                scaler=scaler.state_dict(), step=step + 1, total=total, hist=hist,
                                seconds=time.time() - t0), ck + '.tmp')
                os.replace(ck + '.tmp', ck)
    torch.save(model.state_dict(), f'{run}/model.pt.tmp')
    os.replace(f'{run}/model.pt.tmp', f'{run}/model.pt')
    if os.path.exists(ck):
        os.remove(ck)
    meta.update(train_seconds=round(time.time() - t0, 1), history=hist,
                peak_mem_mib=round(torch.cuda.max_memory_allocated() / 2 ** 20))
    json.dump(meta, open(f'{run}/meta.json', 'w'), indent=1)
    log(f'training scale {s}{jt}' + ('' if nofold else f' fold {k + 1}') + f' done in {(time.time() - t0) / 60:.1f} min')


# ---------------------------------------------------------------- inference

def run_name(s, k, jitter=PAD):
    return f's{s}_f{k}' if jitter == PAD else f's{s}_j{jitter}_f{k}'


def final_name(s, jitter=PAD):
    """Run folder (without suffix) of the stage F network trained on every training day."""
    return f's{s}_final' if jitter == PAD else f's{s}_j{jitter}_final'


def weight_map(blend='ramp'):
    if blend == 'hann':
        # sin^2 over the tile, sampled at pixel centres: never exactly 0, so photo-edge pixels covered by one
        # tile only still get a value
        r = np.sin(np.pi * (np.arange(TILE, dtype=np.float64) + 0.5) / TILE) ** 2
        return np.outer(r, r).astype(np.float32)
    r = np.ones(TILE, np.float32)
    ramp = (np.arange(EDGE, dtype=np.float32) + 1) / (EDGE + 1)
    r[:EDGE], r[-EDGE:] = ramp, ramp[::-1]
    return np.outer(r, r)


def positions(n, stride=STRIDE):
    if n <= TILE:
        return [0]
    p = list(range(0, n - TILE, stride))
    return p + [n - TILE]


def infer(model, img, batch=32, half=False, read='mid192'):
    """img uint8 HxWx3 at the network's scale -> logit map HxW float32. read 'mid192': tiles 256, stride 192,
    logits blended (ramp). read 'avg128': stride 128, probabilities averaged under a Hann weight, returned as
    the logit of the averaged probability (so logit > 0 is probability > 0.5)."""
    rd = READS[read]
    import torch
    H, W = img.shape[:2]
    ph, pw = max(0, TILE - H), max(0, TILE - W)
    if ph or pw:
        img = cv2.copyMakeBorder(img, 0, ph, 0, pw, cv2.BORDER_REFLECT_101)
    Hp, Wp = img.shape[:2]
    acc = np.zeros((Hp, Wp), np.float32)
    wsum = np.zeros((Hp, Wp), np.float32)
    wm = weight_map(rd['blend'])
    prob = rd['blend'] == 'hann'
    pos = [(y, x) for y in positions(Hp, rd['stride']) for x in positions(Wp, rd['stride'])]
    gpu = torch.from_numpy(img).cuda()
    with torch.no_grad():
        for i in range(0, len(pos), batch):
            pb = pos[i:i + batch]
            x = torch.stack([gpu[y:y + TILE, x:x + TILE] for y, x in pb]).permute(0, 3, 1, 2).float().div_(255)
            x = normalise(x).contiguous(memory_format=torch.channels_last)
            if half:
                with torch.autocast('cuda', dtype=torch.float16):
                    out = model(x).float()
            else:
                out = model(x)
            out = out[:, 0]
            if prob:
                out = torch.sigmoid(out.float())
            out = out.cpu().numpy()
            for (y, x_), o in zip(pb, out):
                acc[y:y + TILE, x_:x_ + TILE] += o * wm
                wsum[y:y + TILE, x_:x_ + TILE] += wm
    res = (acc / wsum)[:H, :W]
    if prob:
        p = np.clip(res, 1e-6, 1 - 1e-6)
        res = np.log(p / (1 - p)).astype(np.float32)
    return res, len(pos)


def load_model(s, k, suffix='', jitter=PAD):
    """k = None loads the stage F network (runs/s<S>_final<suffix>)."""
    import torch
    m = make_model(pretrained=False)
    rn = final_name(s, jitter) if k is None else run_name(s, k, jitter)
    m.load_state_dict(torch.load(f'{TRAIN}/runs/{rn}{suffix}/model.pt', map_location='cuda'))
    return m.cuda().eval().to(memory_format=torch.channels_last)


def predict_crop_from_photo(model, rgb_full, rects, s, read='mid192'):
    """Whole photo at scale s; returns {name: bool mask at full res for each rect}."""
    img = scale_img(rgb_full, s)
    lg, ntiles = infer(model, img, read=read)
    if s != 1:
        lg = cv2.resize(lg, (rgb_full.shape[1], rgb_full.shape[0]), interpolation=cv2.INTER_LINEAR)
    return {n: lg[y:y + h, x:x + w] > 0 for (x, y, w, h, n) in rects}, ntiles


def predict_crop_alone(model, rgb, s, read='mid192'):
    h, w = rgb.shape[:2]
    img = scale_img(rgb, s)
    lg, _ = infer(model, img, read=read)
    if s != 1:
        lg = cv2.resize(lg, (w, h), interpolation=cv2.INTER_LINEAR)
    return lg > 0


def cmd_score(a):
    sys.path.insert(0, '/home/txoof/temp.nobackup/wt/npec-406-label-sources/src')
    from npec_rig.images import decode_full
    s, k, J, read = a.scale, a.fold, a.jitter, a.read
    fold = folds()
    man, ph = cells(), photos()
    jpg = {p['key']: p['jpg'] for p in ph}
    if a.final:
        k = None          # stage F: every training cell, seen in training (a sanity check, not a score)
    run = f'{TRAIN}/runs/{final_name(s, J) if a.final else run_name(s, k, J)}{a.suffix}'
    sc = scores_file(read)
    tag = f'scale {s}' + ('' if J == PAD else f' jitter {J}') + ('' if read == 'mid192' else f' read {read}')
    which = 'final network' if a.final else f'fold {k + 1}'
    if os.path.exists(f'{run}/{sc}') and not a.force:
        log(f'scoring {tag} {which}: skipped, already done ({sc} exists)')
        return
    held = list(man) if a.final else [r for r in man if fold[r['day']] == k]
    model = load_model(s, k, a.suffix, J)
    out = f'{TRAIN}/pred/{pred_name(s, J, read)}' + (f'_final{a.suffix}' if a.final else a.suffix)
    os.makedirs(out, exist_ok=True)
    log(f'scoring {tag} {which}: {len(held)} ' + ('truth cells, all seen in training' if a.final else 'held-out truth cells'))
    rows = []
    by_photo = defaultdict(list)
    for r in held:
        if r['rig'] == 'prod':
            by_photo[f"production_{r['capture_id']}"].append(r)
    full = {}
    for key, rs in by_photo.items():
        rgb = decode_full(f'{DATA}/{jpg[key]}')
        rects = [(int(r['crop_x0']), int(r['crop_y0']), int(r['crop_w']), int(r['crop_h']), r['name']) for r in rs]
        m, _ = predict_crop_from_photo(model, rgb, rects, s, read)
        full.update(m)
        del rgb
    for r in held:
        rgb, truth = load_crop(r['name'])
        alone = predict_crop_alone(model, rgb, s, read)
        for mode, m in (('photo', full.get(r['name'])), ('crop', alone)):
            if m is None:
                continue
            assert m.shape == truth.shape
            cv2.imwrite(f'{out}/{r["id"]}_{mode}.png', m.astype(np.uint8) * 255)
            rows.append(dict(scale=s, jitter=J, read=read, fold='final' if a.final else k, mode=mode, id=r['id'], rig=r['rig'], day=r['day'],
                             inter=int((m & truth).sum()), union=int((m | truth).sum()),
                             method_px=int(m.sum()), truth_px=int(truth.sum())))
    write_csv(f'{run}/{sc}.tmp', rows)
    os.replace(f'{run}/{sc}.tmp', f'{run}/{sc}')
    log(f'scoring {tag} {which} done')


def scores_file(read):
    return 'scores.csv' if read == 'mid192' else f'scores_{read}.csv'


def pred_name(s, jitter, read):
    return f's{s}' + ('' if jitter == PAD else f'_j{jitter}') + ('' if read == 'mid192' else f'_{read}')


# ---------------------------------------------------------------- report

def stats(rows):
    iou = [r['inter'] / r['union'] if r['union'] else 1.0 for r in rows]
    rat = [r['method_px'] / r['truth_px'] for r in rows if r['truth_px'] > 0]
    U = sum(r['union'] for r in rows)
    return dict(n=len(rows), pooled_iou=round(sum(r['inter'] for r in rows) / U, 4) if U else None,
                mean_iou=round(float(np.mean(iou)), 4), min_iou=round(float(np.min(iou)), 4),
                mean_abs_ratio_err=round(float(np.mean([abs(x - 1) for x in rat])), 4),
                pooled_ratio=round(sum(r['method_px'] for r in rows) / sum(r['truth_px'] for r in rows), 4),
                empty_truth_cells=sum(1 for r in rows if r['truth_px'] == 0))


def cmd_report(a):
    man = {r['id']: r for r in cells()}
    src = {r['id']: r['truth_source'] for r in read_csv(f'{REF}/truth_index_train.csv')}
    allrows = []
    for i, g in grow_rows().items():
        allrows.append(dict(method='grow core 0.07', scale='', fold='', mode='', id=i, rig=man[i]['rig'],
                            day=man[i]['day'], **g))
    for s in (1, 2):
        for k in range(NFOLD):
            f = f'{TRAIN}/runs/s{s}_f{k}/scores.csv'
            if not os.path.exists(f):
                continue
            for r in read_csv(f):
                for c in ('inter', 'union', 'method_px', 'truth_px'):
                    r[c] = int(r[c])
                allrows.append(dict(method=f'net s{s}', **r))
    for r in allrows:
        r['truth_source'] = src[r['id']]
        r['iou'] = round(r['inter'] / r['union'], 4) if r['union'] else 1.0
        r['area_ratio'] = round(r['method_px'] / r['truth_px'], 4) if r['truth_px'] else ''
    write_csv(f'{RESULTS}/train_cv_per_cell.csv', allrows)
    summ = []
    variants = [('grow core 0.07', '', 'grow from leaf cores (step 1 counts)')]
    for s in (1, 2):
        variants += [(f'net s{s}', 'photo', f'network, scale {s}, prod cells from the whole photo, dev from crop'),
                     (f'net s{s}', 'crop', f'network, scale {s}, every cell from its crop alone')]
    for meth, mode, desc in variants:
        for rig in ('prod', 'dev', 'both'):
            for subset in ('all', 'corrected'):
                rows = [r for r in allrows if r['method'] == meth and (r['mode'] == mode or meth.startswith('grow'))
                        and (rig == 'both' or r['rig'] == rig)
                        and (subset == 'all' or r['truth_source'].startswith('corrected'))]
                if meth.startswith('net') and mode == 'photo':
                    # dev cells have no photo: their crop score stands in
                    rows = [r for r in allrows if r['method'] == meth and (rig == 'both' or r['rig'] == rig)
                            and (subset == 'all' or r['truth_source'].startswith('corrected'))
                            and ((r['rig'] == 'prod' and r['mode'] == 'photo') or (r['rig'] == 'dev' and r['mode'] == 'crop'))]
                if rows:
                    summ.append(dict(method=desc, rig=rig, cells=subset, **stats(rows)))
    write_csv(f'{RESULTS}/train_cv_summary.csv', summ)
    for r in summ:
        if r['cells'] == 'all':
            print(f"{r['method'][:70]:70s} {r['rig']:5s} n={r['n']:2d} pooled {r['pooled_iou']} mean {r['mean_iou']} "
                  f"min {r['min_iou']} |ratio-1| {r['mean_abs_ratio_err']} pooled ratio {r['pooled_ratio']}")


# ---------------------------------------------------------------- pictures, timing

def magenta(rgb, m):
    g = cv2.cvtColor(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), cv2.COLOR_GRAY2RGB)
    g[m] = (255, 0, 255)
    return g


def cmd_sheet(a):
    man = cells()
    rows_by = defaultdict(dict)
    for r in read_csv(f'{RESULTS}/train_cv_per_cell.csv'):
        rows_by[r['id']][(r['method'], r['mode'])] = r
    os.makedirs('/home/txoof/temp.nobackup/scratch/406-train', exist_ok=True)
    S = 220
    for rig in ('prod', 'dev'):
        lines = []
        for r in [x for x in man if x['rig'] == rig]:
            rgb, truth = load_crop(r['name'])
            grow = cv2.imread(f'{NN}/analysis/labels/grow/{r["name"]}_grow.png', 0) > 0
            mode = 'photo' if rig == 'prod' else 'crop'
            panels = [(rgb, f'{r["id"]} {r["stratum"]}'), (magenta(rgb, truth), 'truth (Aaron)')]
            for s in (1, 2):
                f = f'{TRAIN}/pred/s{s}/{r["id"]}_{mode}.png'
                if os.path.exists(f):
                    m = cv2.imread(f, 0) > 0
                    sc = rows_by[r['id']].get((f'net s{s}', mode))
                    panels.append((magenta(rgb, m), f'net {"full" if s == 1 else "half"} IoU {float(sc["iou"]):.2f}'))
            sc = rows_by[r['id']].get(('grow core 0.07', ''))
            panels.append((magenta(rgb, grow), f'grow IoU {float(sc["iou"]):.2f}'))
            row = []
            for im, txt in panels:
                im = cv2.resize(im, (S, S), interpolation=cv2.INTER_AREA)
                head = np.full((22, S, 3), 255, np.uint8)
                cv2.putText(head, txt, (3, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
                row.append(np.vstack([head, im]))
                row.append(np.full((S + 22, 4, 3), 255, np.uint8))
            lines.append(np.hstack(row))
            lines.append(np.full((4, lines[-1].shape[1], 3), 255, np.uint8))
        w = max(l.shape[1] for l in lines)
        lines = [np.pad(l, ((0, 0), (0, w - l.shape[1]), (0, 0)), constant_values=255) for l in lines]
        out = f'/home/txoof/temp.nobackup/scratch/406-train/cells_{rig}.png'
        cv2.imwrite(out, cv2.cvtColor(np.vstack(lines), cv2.COLOR_RGB2BGR))
        print(out)


def cmd_timing(a):
    import torch
    sys.path.insert(0, '/home/txoof/temp.nobackup/wt/npec-406-label-sources/src')
    from npec_rig.images import decode_full
    s, read = a.scale, a.read
    if a.reads_table:
        f = f'{RESULTS}/train_cv_timing_reads.csv'
        if os.path.exists(f) and any(int(r['scale']) == s and r['read'] == read for r in read_csv(f)) and not a.force:
            log(f'timing scale {s} read {read}: skipped, already done')
            return
    ph = photos()
    p = [x for x in ph if x['rig'] == 'production'][0]
    model = load_model(s, 0)
    t0 = time.time()
    rgb = decode_full(f'{DATA}/{p["jpg"]}')
    t_dec = time.time() - t0
    img = scale_img(rgb, s)
    infer(model, img, read=read)          # warm-up
    torch.cuda.synchronize()
    res = []
    for _ in range(3):
        t0 = time.time()
        img = scale_img(rgb, s)
        lg, n = infer(model, img, read=read)
        if s != 1:
            lg = cv2.resize(lg, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_LINEAR)
        torch.cuda.synchronize()
        res.append(time.time() - t0)
    row = dict(scale=s, read=read, tiles=n, tile=TILE, stride=READS[read]['stride'], seconds_median=round(float(np.median(res)), 2),
               seconds_all=' '.join(f'{x:.2f}' for x in res), decode_s=round(t_dec, 2), precision='float32',
               gpu=torch.cuda.get_device_name(0), photo=p['key'])
    print(row)
    if a.reads_table:
        f = f'{RESULTS}/train_cv_timing_reads.csv'
        old = read_csv(f) if os.path.exists(f) else []
        old = [r for r in old if not (int(r['scale']) == s and r['read'] == read)]
        log(f'timing scale {s} read {read}: {row["seconds_median"]} s per photo ({n} tiles), median of 3')
    else:
        f = f'{RESULTS}/train_cv_timing.csv'
        row.pop('read')
        old = read_csv(f) if os.path.exists(f) else []
        old = [r for r in old if int(r['scale']) != s]
    write_csv(f, old + [row])


def cmd_photo(a):
    """One whole production photo, predicted by the fold model that never saw its date, at both scales:
    photo and prediction side by side at 1/4 size, plant solid magenta on grey (dilated 1 px at 1/4 so thin
    marks stay visible)."""
    sys.path.insert(0, '/home/txoof/temp.nobackup/wt/npec-406-label-sources/src')
    from npec_rig.images import decode_full
    fold = folds()
    ph = {p['key']: p for p in photos()}
    key = a.photo or 'production_28022'
    p = ph[key]
    k = fold[p['day_utc']]
    rgb = decode_full(f'{DATA}/{p["jpg"]}')
    q = cv2.resize(rgb, (rgb.shape[1] // 4, rgb.shape[0] // 4), interpolation=cv2.INTER_AREA)
    out = [q]
    for s in (1, 2):
        model = load_model(s, k)
        lg, _ = infer(model, scale_img(rgb, s))
        m = cv2.resize((lg > 0).astype(np.float32), (q.shape[1], q.shape[0]), interpolation=cv2.INTER_AREA) > 0.05
        out.append(magenta(q, m))
    for i, s in enumerate(('photo', 'network full resolution', 'network half resolution')):
        img = cv2.cvtColor(out[i], cv2.COLOR_RGB2BGR)
        cv2.putText(img, f'{key} {p["day_utc"]} fold {k + 1} model: {s}', (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.6,
                    (255, 255, 255), 3, cv2.LINE_AA)
        f = f'/home/txoof/temp.nobackup/scratch/406-train/photo_{key}_{i}.png'
        cv2.imwrite(f, img)
        print(f)


# ---------------------------------------------------------------- stage summary for Aaron

SCR = '/home/txoof/temp.nobackup/scratch/406-train'


def _cellrows():
    """{(method, id): row} with net rows taken as prod from the whole photo, dev from the crop."""
    out = {}
    for r in read_csv(f'{RESULTS}/train_cv_per_cell.csv'):
        for c in ('inter', 'union', 'method_px', 'truth_px'):
            r[c] = int(r[c])
        if r['method'].startswith('grow'):
            out[('grow', r['id'])] = r
        elif (r['rig'] == 'prod' and r['mode'] == 'photo') or (r['rig'] == 'dev' and r['mode'] == 'crop'):
            out[(r['method'], r['id'])] = r
    return out


def _pick_cells(man, cr):
    """8 cells by rule (see stage-A.md), not by look."""
    def med(rows):
        rows = sorted(rows, key=lambda r: (int(cr[('grow', r['id'])]['truth_px']), r['id']))
        return rows[(len(rows) - 1) // 2] if rows else None
    picks = []
    def add(why, r):
        if r is not None and r['id'] not in [p[1]['id'] for p in picks]:
            picks.append((why, r))
    seed = [r for r in man if r['rig'] == 'prod' and r['stratum'] == 'empty']
    add('seedling: production "empty" cell with the smallest truth',
        min(seed, key=lambda r: cr[('grow', r['id'])]['truth_px']))
    add('blue mat: median truth size of the blue-mat cells', med([r for r in man if r['stratum'].startswith('blue mat')]))
    add('green soil, production: median truth size', med([r for r in man if r['rig'] == 'prod' and r['stratum'] == 'green soil']))
    add('green soil / moss, development: median truth size', med([r for r in man if r['rig'] == 'dev' and r['stratum'] == 'green soil']))
    add('"empty" development cell (dead or tiny plant): median truth size', med([r for r in man if r['rig'] == 'dev' and r['stratum'] == 'empty']))
    add('largest plants (size 5 of 5): median truth size, both rigs', med([r for r in man if r['stratum'] == 'size 5 of 5']))
    rest = [r for r in man if r['id'] not in [p[1]['id'] for p in picks]]
    iou = lambda r: cr[('net s2', r['id'])]['inter'] / cr[('net s2', r['id'])]['union']
    add('network best: highest half-resolution IoU of the cells not picked above', max(rest, key=iou))
    rest = [r for r in rest if r['id'] != picks[-1][1]['id']]
    add('network worst: lowest half-resolution IoU of the cells not picked above', min(rest, key=iou))
    return picks


def _cap(r):
    iou = r['inter'] / r['union'] if r['union'] else 1.0
    rat = f"{r['method_px'] / r['truth_px']:.2f}" if r['truth_px'] else 'n/a'
    return f'IoU {iou:.2f}  area x{rat}'


def _fold_table(cr, man, fold):
    rows = []
    for meth in ('grow', 'net s2', 'net s1'):
        for rig in ('prod', 'dev'):
            for k in range(NFOLD):
                rr = [cr[(meth, r['id'])] for r in man if r['rig'] == rig and fold[r['day']] == k]
                if rr:
                    st = stats(rr)
                    rows.append(dict(method=meth, rig=rig, fold=k + 1, n=st['n'], mean_iou=st['mean_iou'],
                                     pooled_iou=st['pooled_iou'], mean_abs_ratio_err=st['mean_abs_ratio_err']))
    return rows


def cmd_stage(a):
    man = cells()
    fold = folds()
    cr = _cellrows()
    name = {'grow': 'grow from leaf cores', 'net s2': 'network, half resolution', 'net s1': 'network, full resolution'}
    # ---- picture
    picks = _pick_cells(man, cr)
    S, HEADH = 290, 40
    rows = []
    for why, r in picks:
        rgb, truth = load_crop(r['name'])
        mode = 'photo' if r['rig'] == 'prod' else 'crop'
        grow = cv2.imread(f'{NN}/analysis/labels/grow/{r["name"]}_grow.png', 0) > 0
        pan = [(rgb, [f'{r["id"]} {"production" if r["rig"] == "prod" else "development"} {r["day"]}',
                      f'held out in fold {fold[r["day"]] + 1}; {r["stratum"]}']),
               (magenta(rgb, truth), ['truth (Aaron)', f'{int(truth.sum())} plant px'])]
        for meth, f in (('grow', None), ('net s2', f'{TRAIN}/pred/s2/{r["id"]}_{mode}.png'),
                        ('net s1', f'{TRAIN}/pred/s1/{r["id"]}_{mode}.png')):
            m = grow if f is None else cv2.imread(f, 0) > 0
            pan.append((magenta(rgb, m), [name[meth], _cap(cr[(meth, r['id'])])]))
        line = []
        for im, txt in pan:
            im = cv2.resize(im, (S, S), interpolation=cv2.INTER_AREA if im.shape[0] > S else cv2.INTER_NEAREST)
            head = np.full((HEADH, S, 3), 255, np.uint8)
            for i, t in enumerate(txt):
                cv2.putText(head, t, (4, 16 + 18 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 1, cv2.LINE_AA)
            line += [np.vstack([head, im]), np.full((S + HEADH, 6, 3), 255, np.uint8)]
        line = np.hstack(line)
        why_bar = np.full((22, line.shape[1], 3), 235, np.uint8)
        cv2.putText(why_bar, 'picked as: ' + why, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
        rows += [why_bar, line, np.full((10, line.shape[1], 3), 255, np.uint8)]
    W = rows[1].shape[1]
    head_txt = ['Stage A: first plant network (U-Net, MobileNetV2), cross-validation by day on the 42 TRAINING cells only.',
                'Each row is one cell, scored by the fold model that never saw that day. Plant is solid magenta on a grey copy of the crop.',
                'Columns: crop in colour | Aaron\'s truth | grow from leaf cores | network half resolution | network full resolution.',
                'Production cells: network run on the whole photo; development cells: on the crop alone (photos purged).',
                'Captions: IoU with the truth, area = marked px / truth px. Cells picked by fixed rules (line above each row), not by look.']
    head = np.full((20 * len(head_txt) + 12, W, 3), 255, np.uint8)
    for i, t in enumerate(head_txt):
        cv2.putText(head, t, (6, 20 + 20 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.imwrite(f'{SCR}/stage-A.png', cv2.cvtColor(np.vstack([head] + rows), cv2.COLOR_RGB2BGR))
    # ---- numbers
    L = ['# Stage A: first plant network, cross-validation on the training cells', '',
         f'Written by `train_cv.py stage` ({datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")} UTC). '
         'Development check. Training cells only (42: production 17, development 25); no test cell was opened.',
         'Every cell is scored once, by the model of the fold that held out its UTC day (5 folds, `results/train_cv_folds.csv`).',
         'Production cells: network on the whole photo; development cells: network on the crop alone (their photos were purged).',
         'Grow from leaf cores: the step 1 counts of the same cells (`results/per_cell.csv`). Threshold probability 0.5, float32.', '',
         '## Results per rig', '',
         '| Rig | Method | Pooled IoU | Mean IoU | Lowest IoU | Mean abs(area ratio - 1) | Pooled area ratio |',
         '|---|---|---|---|---|---|---|']
    for rig in ('prod', 'dev'):
        for meth in ('grow', 'net s2', 'net s1'):
            st = stats([cr[(meth, r['id'])] for r in man if r['rig'] == rig])
            L.append(f"| {'production' if rig == 'prod' else 'development'} ({st['n']}) | {name[meth]} | {st['pooled_iou']:.3f} | "
                     f"{st['mean_iou']:.3f} | {st['min_iou']:.3f} | {st['mean_abs_ratio_err']:.3f} | {st['pooled_ratio']:.3f} |")
    src = {r['id']: r['truth_source'] for r in read_csv(f'{REF}/truth_index_train.csv')}
    L += ['', 'No training truth is empty, so every cell has an area ratio.', '',
          '**Corrected cells only.** 12 of the 42 truths are accepted drafts of grow from leaf cores, where it scores '
          '1.000 by construction (step 1). The fairer comparison is on the 30 truths Aaron corrected:', '',
          '| Rig | Method | Pooled IoU | Mean IoU | Lowest IoU | Mean abs(area ratio - 1) | Pooled area ratio |',
          '|---|---|---|---|---|---|---|']
    for rig in ('prod', 'dev'):
        for meth in ('grow', 'net s2', 'net s1'):
            st = stats([cr[(meth, r['id'])] for r in man if r['rig'] == rig and src[r['id']].startswith('corrected')])
            L.append(f"| {'production' if rig == 'prod' else 'development'} ({st['n']}) | {name[meth]} | {st['pooled_iou']:.3f} | "
                     f"{st['mean_iou']:.3f} | {st['min_iou']:.3f} | {st['mean_abs_ratio_err']:.3f} | {st['pooled_ratio']:.3f} |")
    L += ['',
          '## Fold to fold', '',
          'Mean IoU / mean abs(area ratio - 1) of each fold\'s held-out cells (cells per fold in brackets).', '',
          '| Rig | Method | ' + ' | '.join(f'fold {k + 1}' for k in range(NFOLD)) + ' | SD of folds |', '|---|---|' + '---|' * (NFOLD + 1)]
    ft = _fold_table(cr, man, fold)
    for rig in ('prod', 'dev'):
        for meth in ('grow', 'net s2', 'net s1'):
            rr = {x['fold']: x for x in ft if x['method'] == meth and x['rig'] == rig}
            cellsx = [f"{rr[k]['mean_iou']:.3f} / {rr[k]['mean_abs_ratio_err']:.3f} ({rr[k]['n']})" if k in rr else '-'
                      for k in range(1, NFOLD + 1)]
            sd_i = np.std([x['mean_iou'] for x in rr.values()], ddof=1)
            sd_r = np.std([x['mean_abs_ratio_err'] for x in rr.values()], ddof=1)
            L.append(f"| {rig} | {name[meth]} | " + ' | '.join(cellsx) + f' | {sd_i:.3f} / {sd_r:.3f} |')
    # ---- decision
    L += ['', '## Scale, by the agreed rule', '',
          'Rule: half resolution, unless full resolution beats half for both rigs, in mean IoU and in mean abs(area '
          'ratio - 1), each by more than the fold-to-fold variation. Fold-to-fold variation, as computed here: the '
          'standard deviation over folds of the per-fold difference full minus half (the same cells under both, so the '
          'paired difference is the fair spread).', '',
          '| Rig | Mean IoU full - half | SD over folds | Mean abs(ratio-1) half - full | SD over folds | Full better by more than the spread? |',
          '|---|---|---|---|---|---|']
    beats = []
    for rig in ('prod', 'dev'):
        d_iou, d_err = [], []
        for k in range(1, NFOLD + 1):
            f1 = [x for x in ft if x['method'] == 'net s1' and x['rig'] == rig and x['fold'] == k]
            f2 = [x for x in ft if x['method'] == 'net s2' and x['rig'] == rig and x['fold'] == k]
            if f1 and f2:
                d_iou.append(f1[0]['mean_iou'] - f2[0]['mean_iou'])
                d_err.append(f2[0]['mean_abs_ratio_err'] - f1[0]['mean_abs_ratio_err'])
        s1 = stats([cr[('net s1', r['id'])] for r in man if r['rig'] == rig])
        s2 = stats([cr[('net s2', r['id'])] for r in man if r['rig'] == rig])
        di, de = s1['mean_iou'] - s2['mean_iou'], s2['mean_abs_ratio_err'] - s1['mean_abs_ratio_err']
        sdi, sde = float(np.std(d_iou, ddof=1)), float(np.std(d_err, ddof=1))
        ok = di > sdi and de > sde
        beats.append(ok)
        L.append(f"| {rig} | {di:+.4f} | {sdi:.4f} | {de:+.4f} | {sde:.4f} | {'yes' if ok else 'no'} |")
    choice = 'full resolution' if all(beats) else 'half resolution'
    L += ['', f'**Decision by the rule: {choice}.**', '']
    # ---- seedlings
    seeds = [r for r in man if r['stratum'] == 'empty' and r['rig'] == 'prod'] + \
            [r for r in man if r['stratum'].endswith('size 1 of 5')]
    L += ['## Seedlings on their own', '',
          'Production "empty" cells (seedlings, A01, A02, A17) and every "size 1 of 5" cell. IoU / area ratio.', '',
          '| Cell | Rig | Stratum | Truth px | Grow from leaf cores | Network half | Network full |', '|---|---|---|---|---|---|---|']
    for r in seeds:
        c = [cr[(m, r['id'])] for m in ('grow', 'net s2', 'net s1')]
        L.append(f"| {r['id']} | {r['rig']} | {r['stratum']} | {c[0]['truth_px']} | " +
                 ' | '.join(_cap(x).replace('  area x', ' / ').replace('IoU ', '') for x in c) + ' |')
    # ---- timing
    if os.path.exists(f'{RESULTS}/train_cv_timing.csv'):
        L += ['', '## Time per full photo, float32 network on the RTX 2060 SUPER', '',
              '| Scale | Tiles (256, stride 192) | Seconds (median of 3, after warm-up; excludes JPEG decode) | JPEG decode s |',
              '|---|---|---|---|']
        for t in sorted(read_csv(f'{RESULTS}/train_cv_timing.csv'), key=lambda t: t['scale']):
            L.append(f"| {'full' if t['scale'] == '1' else 'half'} | {t['tiles']} | {t['seconds_median']} | {t['decode_s']} |")
    L += ['', '## Picture', '', '`stage-A.png`: 8 cells picked by these rules, not by look:', '']
    L += [f'- {r["id"]}: {why}' for why, r in picks]
    L += ['', 'Files: `experiments/round4-segmentation-nn/code/train_cv.py` (method in its docstring), tables '
          '`results/train_cv_summary.csv`, `train_cv_per_cell.csv`, `train_cv_folds.csv`, `train_cv_timing.csv`; models, '
          'predictions and logs under `~/temp.nobackup/npec-406-nn/analysis/train/`.', '']
    open(f'{SCR}/stage-A.md', 'w').write('\n'.join(L))
    print('\n'.join(L))


# ---------------------------------------------------------------- stages B and C (same rule as stage A)

B_DECISION = f'{TRAIN}/stage_B_read.txt'


def variant_rows(J, read, man, suffix='', tag='', s=2):
    """{id: score row} for models of scale s (default half resolution), jitter J (run folder suffix, e.g. '_pt6')
    read the given way: prod from the photo, dev from the crop. Every training cell must be present. tag: read the
    score files kept before a truth edit (e.g. TRUTH_EDIT_TAG) instead of the current ones."""
    out = {}
    for k in range(NFOLD):
        f = f'{TRAIN}/runs/{run_name(s, k, J)}{suffix}/{scores_file(read)}'
        if tag:
            f = f.replace('.csv', f'_{tag}.csv')
        for r in read_csv(f):
            if (r['rig'] == 'prod' and r['mode'] == 'photo') or (r['rig'] == 'dev' and r['mode'] == 'crop'):
                for c in ('inter', 'union', 'method_px', 'truth_px'):
                    r[c] = int(r[c])
                out[r['id']] = r
    assert set(out) == {r['id'] for r in man}, 'missing cells'
    return out


def grow_rows():
    """Grow from leaf cores on every training cell, scored against the CURRENT truth files: its step 1 masks
    (`analysis/labels/grow/<name>_grow.png`, the masks behind results/per_cell.csv) over the whole crop. Equal to the
    step 1 counts wherever the truth has not been edited since (checked by `rescore`)."""
    out = {}
    for r in cells():
        _, truth = load_crop(r['name'])
        m = cv2.imread(f'{NN}/analysis/labels/grow/{r["name"]}_grow.png', 0) > 0
        assert m.shape == truth.shape
        out[r['id']] = dict(inter=int((m & truth).sum()), union=int((m | truth).sum()), method_px=int(m.sum()),
                            truth_px=int(truth.sum()))
    return out


# ---------------------------------------------------------------- truth edits (B21, 2026-11-21)

TRUTH_EDIT_TAG = 'before_B21'     # backups of every table / cache made before the B21 truth edit carry this tag
# later edits pass their own tag (--edit-tag), e.g. 'before_purple_check' for B12, B13 and B19
# Every run whose saved predictions are re-scored against the current truth: (run folder, read, pred folder)
RESCORE_RUNS = ([(f's1_f{k}', 'mid192', 's1') for k in range(NFOLD)] +
                [(f's2_f{k}', 'mid192', 's2') for k in range(NFOLD)] +
                [(f's2_f{k}', 'avg128', 's2_avg128') for k in range(NFOLD)] +
                [(f's2_j128_f{k}', 'mid192', 's2_j128') for k in range(NFOLD)] +
                [(f's2_f{k}_pt6', 'mid192', 's2_pt6') for k in range(NFOLD)] +
                [(f's2_f{k}_pt7', 'mid192', 's2_pt7') for k in range(NFOLD)] +     # D2 and E: re-scored from the
                [(f's2_f{k}_e40', 'mid192', 's2_e40') for k in range(NFOLD)])      # purple-check edit on


def cmd_truth_cells(a):
    """Rebuild cache/s<S>/truth_cells.npz (the truth cells at the scale, as `cache` writes them) from the current
    truth files, without touching the photo tiles; the old file is kept once as truth_cells_<TRUTH_EDIT_TAG>.npz.
    Logs which cells' targets changed."""
    s, tag = a.scale, a.edit_tag
    C = cache_dir(s, a.jitter)
    f = f'{C}/truth_cells.npz'
    bak = f'{C}/truth_cells_{tag}.npz'
    if not os.path.exists(bak):
        os.replace(f, bak)
    old = np.load(bak)
    tc = {}
    for r in cells():
        rgb, truth = load_crop(r['name'])
        tc[r['id'] + '_img'] = scale_img(rgb, s)
        tc[r['id'] + '_tgt'] = scale_truth(truth, s)
    np.savez(f + '.tmp.npz', **tc)
    os.replace(f + '.tmp.npz', f)
    changed = []
    for r in cells():
        i = r['id']
        assert np.array_equal(old[i + '_img'], tc[i + '_img']), f'{i} crop changed'
        d = old[i + '_tgt'].astype(int) != tc[i + '_tgt'].astype(int)
        if d.any():
            changed.append(f"{i} ({int(d.sum())} target px changed, plant share "
                           f"{old[i + '_tgt'].sum() / SOFT:.0f} -> {tc[i + '_tgt'].sum() / SOFT:.0f} px)")
    log(f'truth cells scale {s} rebuilt from the current truth files: {len(changed)} of {len(tc) // 2} cells '
        f'changed: {"; ".join(changed) if changed else "none"}')
    json.dump(dict(scale=s, changed=changed, cells=len(tc) // 2, tag=tag),
              open(f'{C}/truth_cells_rebuild.json' if tag == TRUTH_EDIT_TAG else f'{C}/truth_cells_rebuild_{tag}.json', 'w'),
              indent=1)


def rescore_rows(rows, pdir):
    """Score rows recomputed from the saved prediction PNGs against the current truth files."""
    names = {c['id']: c['name'] for c in cells()}
    out = []
    for r in rows:
        _, truth = load_crop(names[r['id']])
        m = cv2.imread(f'{TRAIN}/pred/{pdir}/{r["id"]}_{r["mode"]}.png', 0) > 0
        assert m.shape == truth.shape
        n = dict(r)
        n.update(inter=int((m & truth).sum()), union=int((m | truth).sum()), method_px=int(m.sum()),
                 truth_px=int(truth.sum()))
        out.append(n)
    return out


def cmd_rescore(a):
    """After a truth edit: every run in RESCORE_RUNS re-scored from its saved predictions (no network run, no
    retraining) against the current truth files. The old score file is kept once as scores*_<TRUTH_EDIT_TAG>.csv.
    Also checks grow from leaf cores, scored from its masks against the current truth, against the step 1 counts
    (results/per_cell.csv). Logs every cell whose score changed (only edited cells should)."""
    changed = set()
    tag = a.edit_tag
    for run, read, pdir in RESCORE_RUNS:
        f = f'{TRAIN}/runs/{run}/{scores_file(read)}'
        if not os.path.exists(f):
            continue          # a run made after this edit's list was written (e.g. D2/E for the B21 edit)
        bak = f.replace('.csv', f'_{tag}.csv')
        if not os.path.exists(bak):
            __import__('shutil').copy2(f, bak)
        old = read_csv(bak)
        new = rescore_rows(old, pdir)
        for o, n in zip(old, new):
            if any(int(o[c]) != n[c] for c in ('inter', 'union', 'method_px', 'truth_px')):
                changed.add((run, read, n['id'], n['mode']))
        write_csv(f + '.tmp', new)
        os.replace(f + '.tmp', f)
    ids = sorted({c[2] for c in changed})
    g_new = grow_rows()
    g_old = {r['id']: r for r in read_csv(f'{RESULTS}/per_cell.csv') if r['setting'] == 'grow core 0.07'}
    g_changed = sorted(i for i in g_new if any(int(g_old[i][c]) != g_new[i][c] for c in g_new[i]))
    log(f'rescore against the current truth files: {len(RESCORE_RUNS)} score files from saved predictions; '
        f'cells whose scores changed: {", ".join(ids) or "none"} ({len(changed)} rows); grow from leaf cores '
        f'differs from the step 1 counts on: {", ".join(g_changed) or "none"}')
    json.dump(dict(changed_rows=sorted(changed), changed_cells=ids, grow_changed=g_changed),
              open(f'{TRAIN}/rescore_{tag}.json', 'w'), indent=1)


def decide(old, new, man, fold):
    """The agreed rule: new kept only if, for both rigs, mean IoU new - old and mean abs(ratio-1) old - new each
    exceed the SD over folds of the paired per-fold difference. Returns (table rows, kept)."""
    rows, beats = [], []
    for rig in ('prod', 'dev'):
        d_iou, d_err = [], []
        for k in range(NFOLD):
            ids = [r['id'] for r in man if r['rig'] == rig and fold[r['day']] == k]
            if ids:
                so, sn = stats([old[i] for i in ids]), stats([new[i] for i in ids])
                d_iou.append(sn['mean_iou'] - so['mean_iou'])
                d_err.append(so['mean_abs_ratio_err'] - sn['mean_abs_ratio_err'])
        ids = [r['id'] for r in man if r['rig'] == rig]
        so, sn = stats([old[i] for i in ids]), stats([new[i] for i in ids])
        di, de = sn['mean_iou'] - so['mean_iou'], so['mean_abs_ratio_err'] - sn['mean_abs_ratio_err']
        sdi, sde = float(np.std(d_iou, ddof=1)), float(np.std(d_err, ddof=1))
        ok = di > sdi and de > sde
        beats.append(ok)
        rows.append(dict(rig=rig, d_iou=di, sd_iou=sdi, d_err=de, sd_err=sde, ok=ok,
                         fold_d_iou=d_iou, fold_d_err=d_err))
    return rows, all(beats)


def stage_B_read():
    if not os.path.exists(B_DECISION):
        sys.exit('stage B decision missing: run "train_cv.py compare --stage B" first')
    return open(B_DECISION).read().strip()


def cmd_best_read(a):
    print(stage_B_read())


D2_DECISION = f'{TRAIN}/stage_D2_decision.txt'     # 'pt7' if D2 passed the rule, else 'none'


def stage_D2_init():
    """'pt7' if stage D2 passed the rule (stage E then starts every fold from runs/pt7), else '' (stage A's start)."""
    if not os.path.exists(D2_DECISION):
        sys.exit('stage D2 decision missing: run "train_cv.py compare --stage D2" first')
    v = open(D2_DECISION).read().strip()
    return '' if v == 'none' else v


def cmd_e_init(a):
    """Print the stage E start for the driver: 'pt7' or nothing."""
    print(stage_D2_init())


def truth_edit_section(man, src, fold):
    """stage-D2.md: how far the B21 truth edit moved stage A's and D1's tables (scores before the edit are the kept
    *_before_B21 score files and the step 1 grow counts; after: re-scored from the same saved predictions)."""
    grow_old = {r['id']: {c: int(r[c]) for c in ('inter', 'union', 'method_px', 'truth_px')}
                for r in read_csv(f'{RESULTS}/per_cell.csv') if r['setting'] == 'grow core 0.07'}
    T_ = TRUTH_EDIT_TAG
    sets = [('grow from leaf cores', grow_old, grow_rows()),
            ('stage A, half resolution (current best)', variant_rows(32, 'mid192', man, tag=T_), variant_rows(32, 'mid192', man)),
            ('stage A, full resolution', variant_rows(32, 'mid192', man, tag=T_, s=1), variant_rows(32, 'mid192', man, s=1)),
            ('D1: 6 public sets first, then ours', variant_rows(32, 'mid192', man, '_pt6', T_), variant_rows(32, 'mid192', man, '_pt6'))]
    info = json.load(open(f'{TRAIN}/rescore_{T_}.json'))
    L = ['## The B21 truth edit, and how far it moved stage A and D1', '',
         'Before this stage, one training truth was changed (Aaron, 2026-11-21: purple, anthocyanin, tissue is plant): '
         'B21, 896 px of reddish-purple leaf stalk filled as plant (129,099 -> 129,995 truth px; log in '
         '`analysis/labels/truth_edits/`). The half-resolution truth cells used in training were rebuilt from the truth '
         'files: only B21\'s target changed (41 cells identical). Stage A, D1 (and B, C) were **not retrained**: their saved '
         'predictions were re-scored against the new truth; only B21\'s rows changed '
         f'(cells changed: {", ".join(info["changed_cells"])}; grow from leaf cores: {", ".join(info["grow_changed"])}). '
         'Every score in this file uses the new truth. Stage A and D1 models were trained with the old B21 label, D2 with '
         'the new one.', '',
         '| Rig | Method | Pooled IoU before -> after | Mean IoU before -> after | Mean abs(area ratio - 1) before -> after | B21 IoU / area ratio before -> after |',
         '|---|---|---|---|---|---|']
    for rig in ('prod', 'dev'):
        ids = [r['id'] for r in man if r['rig'] == rig]
        for nm, o, n in sets:
            so, sn = stats([o[i] for i in ids]), stats([n[i] for i in ids])
            b21 = ''
            if rig == 'dev':
                b21 = (f"{_cap(o['B21']).replace('  area x', ' / ').replace('IoU ', '')} -> "
                       f"{_cap(n['B21']).replace('  area x', ' / ').replace('IoU ', '')}")
            L.append(f"| {rig} | {nm} | {so['pooled_iou']:.4f} -> {sn['pooled_iou']:.4f} | {so['mean_iou']:.4f} -> "
                     f"{sn['mean_iou']:.4f} | {so['mean_abs_ratio_err']:.4f} -> {sn['mean_abs_ratio_err']:.4f} | {b21} |")
    L += ['', 'The rule\'s numbers, before -> after (difference / SD over folds):', '',
          '| Comparison | Rig | Mean IoU difference | SD | Mean abs(ratio-1) difference | SD | Passes? |', '|---|---|---|---|---|---|---|']
    for nm, (oo, on_), (no, nn_) in (('stage A: full against half resolution', (sets[1][1], sets[2][1]), (sets[1][2], sets[2][2])),
                                     ('D1 against stage A', (sets[1][1], sets[3][1]), (sets[1][2], sets[3][2]))):
        before, _ = decide(oo, on_, man, fold)
        after, _ = decide(no, nn_, man, fold)
        for b, a_ in zip(before, after):
            L.append(f"| {nm} | {b['rig']} | {b['d_iou']:+.4f} -> {a_['d_iou']:+.4f} | {b['sd_iou']:.4f} -> {a_['sd_iou']:.4f} | "
                     f"{b['d_err']:+.4f} -> {a_['d_err']:+.4f} | {b['sd_err']:.4f} -> {a_['sd_err']:.4f} | "
                     f"{'yes' if b['ok'] else 'no'} -> {'yes' if a_['ok'] else 'no'} |")
    L.append('')
    return L


def epoch_losses(meta):
    """Mean training loss per epoch (BCE + dice, as optimised), from the history logged in meta.json: each history
    entry is the mean over the steps since the entry before, so the epoch mean is their step-weighted mean."""
    out, prev = defaultdict(lambda: [0.0, 0]), 0
    for h in meta['history']:
        n = h['step'] - prev
        e = (h['step'] - 1) // STEPS_PER_EPOCH + 1
        out[e][0] += h['loss'] * n
        out[e][1] += n
        prev = h['step']
    return [out[e][0] / out[e][1] for e in sorted(out)]


def loss_section(bs):
    """stage-E.md loss table and stage-E-loss.png: training loss per epoch, 15 against 40 epochs, every fold."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    l15 = [epoch_losses(json.load(open(f'{TRAIN}/runs/{run_name(2, k)}{bs}/meta.json'))) for k in range(NFOLD)]
    l40 = [epoch_losses(json.load(open(f'{TRAIN}/runs/{run_name(2, k)}{bs}_e40/meta.json'))) for k in range(NFOLD)]
    m15, m40 = np.mean(l15, axis=0), np.mean(l40, axis=0)
    C15, C40, INK, MUTED, GRID = '#2a78d6', '#eb6834', '#1f1f1e', '#5f5e5a', '#e4e3df'
    fig, ax = plt.subplots(figsize=(9, 4.8), dpi=130)
    for k in range(NFOLD):
        ax.plot(range(1, len(l15[k]) + 1), l15[k], color=C15, lw=0.8, alpha=0.35)
        ax.plot(range(1, len(l40[k]) + 1), l40[k], color=C40, lw=0.8, alpha=0.35)
    ax.plot(range(1, len(m15) + 1), m15, color=C15, lw=2, marker='o', ms=4, label='15 epochs (mean of 5 folds)')
    ax.plot(range(1, len(m40) + 1), m40, color=C40, lw=2, marker='o', ms=4, label='40 epochs (mean of 5 folds)')
    ax.text(len(m15) + 0.4, m15[-1], f'15 ep: {m15[-1]:.4f}', color=INK, va='center', fontsize=9)
    ax.text(len(m40) + 0.4, m40[-1], f'40 ep: {m40[-1]:.4f}', color=INK, va='center', fontsize=9)
    ax.set_yscale('log')
    ax.set_xlabel('epoch (400 steps of 24 tiles)', color=MUTED)
    ax.set_ylabel('training loss, BCE + dice (log scale)', color=MUTED)
    ax.set_title('Stage E: training loss per epoch (thin lines: single folds). Learning rate falls to zero at the last '
                 'epoch of each run.', fontsize=9.5, color=INK, loc='left')
    ax.grid(True, which='both', color=GRID, lw=0.6)
    for sp in ('top', 'right'):
        ax.spines[sp].set_visible(False)
    ax.set_xlim(0.5, len(m40) + 4)
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(f'{SCR}/stage-E-loss.png', facecolor='white')
    plt.close(fig)
    L = ['## Training loss per epoch', '',
         '`stage-E-loss.png`. Mean over the 5 folds of the training loss (BCE + dice on the training samples, with '
         'augmentation; not a held-out score). Both runs end with the learning rate at zero, so the last epochs flatten '
         'by construction; what matters is the level reached and whether the held-out scores above follow it.', '',
         '| Epoch | 15 epochs | 40 epochs |', '|---|---|---|']
    for e in range(len(m40)):
        L.append(f'| {e + 1} | {m15[e]:.4f} | {m40[e]:.4f} |' if e < len(m15) else f'| {e + 1} | | {m40[e]:.4f} |')
    q = len(m40) // 4
    L += ['', '40 epochs, change of the mean loss over each quarter of the run: ' +
          ', '.join(f'epochs {i * q + 1}-{(i + 1) * q}: {m40[(i + 1) * q - 1] - (m40[i * q - 1] if i else m40[0]):+.4f}'
                    for i in range(4)) +
          f'. Last 5 epochs: {m40[-1] - m40[-6]:+.4f}. 15 epochs ended at {m15[-1]:.4f}; 40 epochs passed that level at '
          f'epoch {next((e + 1 for e, v in enumerate(m40) if v <= m15[-1]), "never")}.', '']
    return L


def cmd_compare(a):
    """stage-B.md/png or stage-C.md/png for Aaron: the same tables, fold spread, rule, seedlings and 8-cell
    picture as stage A, old setting against new."""
    st_ = a.stage
    man, fold = cells(), folds()
    src = {r['id']: r['truth_source'] for r in read_csv(f'{REF}/truth_index_train.csv')}
    grow = grow_rows()
    A = variant_rows(32, 'mid192', man)
    B = variant_rows(32, 'avg128', man)
    rowsAB, keepB = decide(A, B, man, fold)
    bread = 'avg128' if keepB else 'mid192'
    if st_ == 'B':
        open(B_DECISION, 'w').write(bread + '\n')
        meths = [('grow', grow, 'grow from leaf cores', None),
                 ('A', A, 'A: stride 192, middle kept', ('32', 'mid192', '')),
                 ('B', B, 'B: stride 128, averaged (Hann)', ('32', 'avg128', ''))]
        old_k, new_k, rows_dec, kept = 'A', 'B', rowsAB, keepB
    elif st_ == 'D1':
        assert not keepB and stage_B_read() == 'mid192'
        D1 = variant_rows(32, 'mid192', man, '_pt6')
        meths = [('grow', grow, 'grow from leaf cores', None),
                 ('A', A, 'current best: ImageNet start, ours only', ('32', 'mid192', '')),
                 ('D1', D1, 'D1: 6 public sets first, then ours', ('32', 'mid192', '_pt6'))]
        old_k, new_k = 'A', 'D1'
        rows_dec, kept = decide(A, D1, man, fold)
    elif st_ == 'D2':
        assert not keepB and stage_B_read() == 'mid192'
        D1 = variant_rows(32, 'mid192', man, '_pt6')
        D2 = variant_rows(32, 'mid192', man, '_pt7')
        meths = [('grow', grow, 'grow from leaf cores', None),
                 ('A', A, 'current best: ImageNet start, ours only', ('32', 'mid192', '')),
                 ('D1', D1, 'D1: 6 public sets first, then ours', ('32', 'mid192', '_pt6')),
                 ('D2', D2, 'D2: all 7 public sets first, then ours', ('32', 'mid192', '_pt7'))]
        old_k, new_k = 'A', 'D2'
        rows_dec, kept = decide(A, D2, man, fold)
        rows_info, kept_info = decide(D1, D2, man, fold)      # D2 against D1: information only
        open(D2_DECISION, 'w').write(('pt7' if kept else 'none') + '\n')
    elif st_ == 'E':
        init = stage_D2_init()
        bs = '_pt7' if init else ''
        E15 = variant_rows(32, 'mid192', man, bs)
        E40 = variant_rows(32, 'mid192', man, bs + '_e40')
        bdesc = 'D2: all 7 public sets first' if init else 'current best: ImageNet start'
        meths = [('grow', grow, 'grow from leaf cores', None),
                 ('15 ep', E15, f'15 epochs ({bdesc})', ('32', 'mid192', bs)),
                 ('40 ep', E40, f'40 epochs (otherwise the same)', ('32', 'mid192', bs + '_e40'))]
        old_k, new_k = '15 ep', '40 ep'
        rows_dec, kept = decide(E15, E40, man, fold)
    else:
        assert stage_B_read() == bread
        C = variant_rows(128, bread, man)
        best = B if keepB else A
        bname = 'B: stride 128, averaged (Hann)' if keepB else 'A: stride 192, middle kept'
        meths = [('grow', grow, 'grow from leaf cores', None),
                 ('A', A, 'A: jitter 32, stride 192 middle kept', ('32', 'mid192', '')),
                 ('B', B, 'B: jitter 32, stride 128 averaged', ('32', 'avg128', '')),
                 ('C', C, f'C: jitter 128, read {"stride 128 averaged" if bread == "avg128" else "stride 192 middle kept"}',
                  ('128', bread, ''))]
        old_k, new_k = ('B' if keepB else 'A'), 'C'
        rows_dec, kept = decide(best, C, man, fold)
    M = {m[0]: m for m in meths}
    title = {'B': 'Stage B: reading a photo with 50% tile overlap, averaged',
             'C': 'Stage C: training windows shifted up to 128 px',
             'D1': 'Stage D1: pre-trained on 6 public sets, then trained on ours',
             'D2': 'Stage D2: pre-trained on all 7 public sets, then trained on ours',
             'E': 'Stage E: training length, 15 against 40 epochs'}[st_]
    L = [f'# {title}', '',
         f'Written by `train_cv.py compare --stage {st_}` ({datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")} UTC). '
         'Development check. Training cells only (42: production 17, development 25); no test cell was opened.',
         'Half resolution (S = 2), the stage A recipe otherwise. Every cell is scored once, by the fold model that '
         'never saw its UTC day. Production cells: network on the whole photo; development cells: on the crop alone. '
         'Threshold probability 0.5, float32.', '']
    if st_ == 'B':
        L += ['What changed: only the reading. Stage A\'s five half-resolution fold models, no retraining.', '',
              '- **A** (stage A\'s way): 256 tiles at stride 192 (64 px overlap); logits blended with a weight that '
              'rises linearly over the 32 px next to each tile edge, so the middle of each tile is what counts. '
              'Scores are stage A\'s own `scores.csv`.',
              '- **B** (new): 256 tiles at stride 128 (50% overlap, every pixel inside the photo seen by about 4 '
              'tiles); each tile\'s probabilities (sigmoid of the logit) are averaged under a 2D Hann weight '
              '(sin^2 across the tile, sampled at pixel centres, so it is never exactly 0 at the photo edge); plant where '
              'the averaged probability > 0.5. At half resolution the map is taken back to full size as the logit of '
              'the averaged probability, bilinear, as in A.', '']
    elif st_ == 'D1':
        pm = json.load(open(f'{TRAIN}/runs/pt6/meta.json'))
        L += ['What changed: only the starting weights. The same network (U-Net, MobileNetV2 encoder from ImageNet) was '
              f'first trained on public tiles of six sets ({", ".join(pm["pretrain_sets"])}; ARADEEPOPSIS left out for '
              f'D1u), {pm["patches"]} patches, each set drawn with equal probability per sample, {pm["epochs"]} epochs of '
              f'{STEPS_PER_EPOCH} steps ({pm["steps"]} steps, batch {BATCH}), the stage A optimiser, schedule, loss and '
              'augmentation, no truth cells, no early stopping (length fixed in advance). Then, for each of the 5 folds, '
              'trained on ours exactly as stage A (same photos, cells, seeds, 15 epochs, lr 5e-4 with warm-up and cosine), '
              'starting from those weights. Read as stage A (stride 192, middle kept, the stage B winner; jitter 32, '
              'stage C kept it). Public sets, scales and tile counts: D0, `public_prep.py` and `results/public_tiles.csv`.', '']
    elif st_ == 'D2':
        pm = json.load(open(f'{TRAIN}/runs/pt7/meta.json'))
        L += ['What changed: only the starting weights, as in D1 but with all seven public sets. The same network '
              f'(U-Net, MobileNetV2 encoder from ImageNet) was first trained on public tiles of {", ".join(pm["pretrain_sets"])} '
              f'(ARADEEPOPSIS with Aaron\'s labels of 2026-11-21: healthy and purple = plant, senescent = not plant), '
              f'{pm["patches"]} patches, each set drawn with probability 1/{len(pm["pretrain_sets"])} per sample, '
              f'{pm["epochs"]} epochs of {STEPS_PER_EPOCH} steps ({pm["steps"]} steps, batch {BATCH}), the stage A optimiser, '
              'schedule, loss and augmentation, no truth cells, no early stopping (length fixed in advance; the D1 recipe). '
              'Then, for each of the 5 folds, trained on ours exactly as stage A (same photos, cells, seeds, 15 epochs, '
              'lr 5e-4 with warm-up and cosine), starting from those weights, with the B21 truth as edited on 2026-11-21. '
              'Read as stage A (stride 192, middle kept). Compared with the current best (stage A) by the rule, and with '
              'D1 as information.', '']
        L += truth_edit_section(man, src, fold)
    elif st_ == 'E':
        m40 = json.load(open(f'{TRAIN}/runs/{run_name(2, 0)}{bs}_e40/meta.json'))
        L += [f'What changed: only the training length. The 5 half-resolution folds trained for {m40["epochs"]} epochs of '
              f'{STEPS_PER_EPOCH} steps ({m40["steps"]} steps) instead of 15 ({15 * STEPS_PER_EPOCH} steps), the same '
              'warm-up and cosine schedule stretched over the longer run (lr 5e-4 falling to zero at the last step), last '
              'weights kept, no early stopping. Everything else is the setting that stood after D2: '
              f'**{"D2 (all 7 public sets first, then ours)" if init else "stage A (ImageNet start, ours only)"}**. '
              'The 40-epoch models were trained with the B21 truth as edited on 2026-11-21; the 15-epoch models '
              + ('(D2) too.' if init else '(stage A) were trained before the edit, with the old B21 truth (896 px of one of '
                 '34 training cells per fold); every score here is against the new truth.') +
              ' Longer training is the less simple setting, so it is kept only if it beats 15 epochs by the rule.', '']
    else:
        L += [f'What changed: only the training crop jitter. The 5 half-resolution folds retrained with patches of '
              f'512 px (256 + 2 x 128) around the same grid squares as stage A (same photos, same squares kept, same '
              f'seed for the square selection), so a training window can be shifted up to 128 px from its square '
              f'instead of 32. Everything else as stage A. Read the way that won stage B: '
              f'**{"stride 128, averaged" if bread == "avg128" else "stride 192, middle kept"}**. Compared with the best '
              f'of A and B by the rule ({old_k}).', '']
    def table(subset):
        out = ['| Rig | Method | Pooled IoU | Mean IoU | Lowest IoU | Mean abs(area ratio - 1) | Pooled area ratio |',
               '|---|---|---|---|---|---|---|']
        for rig in ('prod', 'dev'):
            for key, rr, nm, _ in meths:
                ids = [r['id'] for r in man if r['rig'] == rig and (subset == 'all' or src[r['id']].startswith('corrected'))]
                st = stats([rr[i] for i in ids])
                out.append(f"| {'production' if rig == 'prod' else 'development'} ({st['n']}) | {nm} | {st['pooled_iou']:.3f} | "
                           f"{st['mean_iou']:.3f} | {st['min_iou']:.3f} | {st['mean_abs_ratio_err']:.3f} | {st['pooled_ratio']:.3f} |")
        return out
    L += ['## Results per rig', ''] + table('all')
    L += ['', '**Corrected cells only** (the 30 truths Aaron corrected; on the other 12, grow from leaf cores scores 1.000 by '
          'construction):', ''] + table('corrected')
    L += ['', '## Fold to fold', '', 'Mean IoU / mean abs(area ratio - 1) of each fold\'s held-out cells (cells per fold in brackets).', '',
          '| Rig | Method | ' + ' | '.join(f'fold {k + 1}' for k in range(NFOLD)) + ' | SD of folds |', '|---|---|' + '---|' * (NFOLD + 1)]
    for rig in ('prod', 'dev'):
        for key, rr, nm, _ in meths:
            vals = []
            cl = []
            for k in range(NFOLD):
                ids = [r['id'] for r in man if r['rig'] == rig and fold[r['day']] == k]
                st = stats([rr[i] for i in ids])
                vals.append((st['mean_iou'], st['mean_abs_ratio_err']))
                cl.append(f"{st['mean_iou']:.3f} / {st['mean_abs_ratio_err']:.3f} ({st['n']})")
            L.append(f'| {rig} | {nm} | ' + ' | '.join(cl) +
                     f" | {np.std([v[0] for v in vals], ddof=1):.3f} / {np.std([v[1] for v in vals], ddof=1):.3f} |")
    on, nn_ = M[old_k][2], M[new_k][2]
    L += ['', '## Decision by the agreed rule', '',
          f'Rule: keep {new_k} only if it beats {old_k} for both rigs, in mean IoU and in mean abs(area ratio - 1), each by '
          'more than the fold-to-fold variation: the standard deviation over the 5 folds of the per-fold difference '
          f'(the same cells under both, so the paired difference is the fair spread). Otherwise {old_k} stays.', '',
          f'| Rig | Mean IoU {new_k} - {old_k} | SD over folds | Mean abs(ratio-1) {old_k} - {new_k} | SD over folds | '
          f'Per-fold IoU differences | Per-fold abs(ratio-1) differences | {new_k} better by more than the spread? |',
          '|---|---|---|---|---|---|---|---|']
    for d in rows_dec:
        L.append(f"| {d['rig']} | {d['d_iou']:+.4f} | {d['sd_iou']:.4f} | {d['d_err']:+.4f} | {d['sd_err']:.4f} | "
                 + ' '.join(f'{x:+.3f}' for x in d['fold_d_iou']) + ' | ' + ' '.join(f'{x:+.3f}' for x in d['fold_d_err'])
                 + f" | {'yes' if d['ok'] else 'no'} |")
    if st_ == 'B':
        verdict = ('B, stride 128 averaged' if kept else 'A, stride 192 middle kept (the simpler setting)')
    elif st_ == 'D1':
        verdict = ('D1, public pre-training kept' if kept else 'no public pre-training (the simpler setting)')
    elif st_ == 'D2':
        verdict = ('D2, pre-training on all 7 public sets kept' if kept else 'no public pre-training (the simpler setting)')
    elif st_ == 'E':
        verdict = ('40 epochs' if kept else '15 epochs (the simpler setting)')
    else:
        verdict = ('C, jitter 128' if kept else 'jitter 32 (the simpler setting)')
    L += ['', f'**Decision by the rule: {verdict}.**', '']
    if st_ == 'D2':
        L += ['**D2 against D1, information only** (not a decision: D1 did not pass the rule, so it is not the current '
              'best). Same rule and spread; positive means D2 better.', '',
              '| Rig | Mean IoU D2 - D1 | SD over folds | Mean abs(ratio-1) D1 - D2 | SD over folds | Per-fold IoU differences '
              '| Per-fold abs(ratio-1) differences | D2 better than D1 by more than the spread? |',
              '|---|---|---|---|---|---|---|---|']
        for d in rows_info:
            L.append(f"| {d['rig']} | {d['d_iou']:+.4f} | {d['sd_iou']:.4f} | {d['d_err']:+.4f} | {d['sd_err']:.4f} | "
                     + ' '.join(f'{x:+.3f}' for x in d['fold_d_iou']) + ' | ' + ' '.join(f'{x:+.3f}' for x in d['fold_d_err'])
                     + f" | {'yes' if d['ok'] else 'no'} |")
        L.append('')
    if st_ == 'E':
        L += [f'(Stage D2 decision, read from `{D2_DECISION.rsplit("/", 1)[1]}`: '
              f'{"D2 kept" if init else "no public pre-training"}.)', '']
    if st_ == 'C' and keepB is not None:
        L += [f'(Stage B decision, recomputed here from the same scores: {"B kept" if keepB else "A kept"}.)', '']
    # seedlings
    seeds = [r for r in man if r['stratum'] == 'empty' and r['rig'] == 'prod'] + \
            [r for r in man if r['stratum'].endswith('size 1 of 5')]
    L += ['## Seedlings on their own', '',
          'Production "empty" cells (seedlings, A01, A02, A17) and every "size 1 of 5" cell. IoU / area ratio.', '',
          '| Cell | Rig | Stratum | Truth px | ' + ' | '.join(m[2] for m in meths) + ' |',
          '|---|---|---|---|' + '---|' * len(meths)]
    for r in seeds:
        c = [m[1][r['id']] for m in meths]
        L.append(f"| {r['id']} | {r['rig']} | {r['stratum']} | {c[0]['truth_px']} | " +
                 ' | '.join(_cap(x).replace('  area x', ' / ').replace('IoU ', '') for x in c) + ' |')
    sd = [r['id'] for r in seeds]
    for key in (old_k, new_k):
        st = stats([M[key][1][i] for i in sd])
        L.append(f'| all {len(sd)} | | mean | | ' + ' | '.join(
            (f"{st['mean_iou']:.2f} / {st['mean_abs_ratio_err']:.3f} (mean abs(ratio-1))" if m[0] == key else '')
            for m in meths) + ' |')
    # timing
    f = f'{RESULTS}/train_cv_timing_reads.csv'
    if os.path.exists(f) and st_ in ('B', 'C'):
        L += ['', '## Time per full photo, float32 network on the RTX 2060 SUPER, half resolution', '',
              '| Read | Tiles (256) | Stride | Seconds (median of 3, after warm-up; excludes JPEG decode) | JPEG decode s |',
              '|---|---|---|---|---|']
        for t in read_csv(f):
            if t['scale'] == '2':
                L.append(f"| {'A, middle kept' if t['read'] == 'mid192' else 'B, averaged'} | {t['tiles']} | {t['stride']} | "
                         f"{t['seconds_median']} ({t['seconds_all']}) | {t['decode_s']} |")
        L += ['', 'Measured the same way as stage A (one production photo, scale, tiles, blend and resize back to full size '
              'included), both in this session. Stage A measured the middle-kept read at 1.71 s per photo in its own '
              'session; the same code here took about 1.2 s, so compare B with A only within this table. ' + ('Stage C changes only training, so its reading time is that of the read it uses.'
                                               if st_ == 'C' else '')]
    if st_ == 'D1':
        pm = json.load(open(f'{TRAIN}/runs/pt6/meta.json'))
        L += ['', '## Training time', '', f'Public pre-training (once): {pm["train_seconds"] / 60:.1f} min, peak GPU '
              f'{pm["peak_mem_mib"]} MiB. Reading time is unchanged (same network, same read).', '',
              '| Fold | A (ImageNet start) min | D1 (from pre-training) min |', '|---|---|---|']
        for k in range(NFOLD):
            ma = json.load(open(f'{TRAIN}/runs/{run_name(2, k)}/meta.json'))
            md = json.load(open(f'{TRAIN}/runs/{run_name(2, k)}_pt6/meta.json'))
            L.append(f"| {k + 1} | {ma['train_seconds'] / 60:.1f} | {md['train_seconds'] / 60:.1f} |")
    if st_ == 'D2':
        pm = json.load(open(f'{TRAIN}/runs/pt7/meta.json'))
        p6 = json.load(open(f'{TRAIN}/runs/pt6/meta.json'))
        L += ['', '## Training time', '', f'Public pre-training on 7 sets (once): {pm["train_seconds"] / 60:.1f} min, peak GPU '
              f'{pm["peak_mem_mib"]} MiB (D1, 6 sets: {p6["train_seconds"] / 60:.1f} min). Reading time is unchanged (same '
              'network, same read).', '',
              '| Fold | A (ImageNet start) min | D1 min | D2 min |', '|---|---|---|---|']
        for k in range(NFOLD):
            mm = [json.load(open(f'{TRAIN}/runs/{run_name(2, k)}{x}/meta.json')) for x in ('', '_pt6', '_pt7')]
            L.append(f'| {k + 1} | ' + ' | '.join(f"{m['train_seconds'] / 60:.1f}" for m in mm) + ' |')
        dt = f'{RESULTS}/d2u_table.md'
        if os.path.exists(dt):
            L += ['', open(dt).read().rstrip(), '']
    if st_ == 'E':
        L += ['', '## Training time per fold', '', '| Fold | 15 epochs min | 40 epochs min | 40 epochs peak GPU MiB |',
              '|---|---|---|---|']
        for k in range(NFOLD):
            m15 = json.load(open(f'{TRAIN}/runs/{run_name(2, k)}{bs}/meta.json'))
            m40 = json.load(open(f'{TRAIN}/runs/{run_name(2, k)}{bs}_e40/meta.json'))
            L.append(f"| {k + 1} | {m15['train_seconds'] / 60:.1f} | {m40['train_seconds'] / 60:.1f} | {m40['peak_mem_mib']} |")
        L += [''] + loss_section(bs)
    if st_ == 'C':
        L += ['', '## Training time per fold', '', '| Fold | A (jitter 32) min | C (jitter 128) min | C peak GPU MiB |', '|---|---|---|---|']
        for k in range(NFOLD):
            ma = json.load(open(f'{TRAIN}/runs/{run_name(2, k)}/meta.json'))
            mc = json.load(open(f'{TRAIN}/runs/{run_name(2, k, 128)}/meta.json'))
            L.append(f"| {k + 1} | {ma['train_seconds'] / 60:.1f} | {mc['train_seconds'] / 60:.1f} | {mc['peak_mem_mib']} |")
    # picture: same cells as stage A (the rules use stage A's half-resolution IoU)
    cr = _cellrows()
    picks = _pick_cells(man, cr)
    S, HEADH = 290, 40
    prow = []
    for why, r in picks:
        rgb, truth = load_crop(r['name'])
        mode = 'photo' if r['rig'] == 'prod' else 'crop'
        gm = cv2.imread(f'{NN}/analysis/labels/grow/{r["name"]}_grow.png', 0) > 0
        pan = [(rgb, [f'{r["id"]} {"production" if r["rig"] == "prod" else "development"} {r["day"]}',
                      f'held out in fold {fold[r["day"]] + 1}; {r["stratum"]}']),
               (magenta(rgb, truth), ['truth (Aaron)', f'{int(truth.sum())} plant px']),
               (magenta(rgb, gm), ['grow from leaf cores', _cap(grow[r['id']])])]
        for key in (old_k, new_k):
            J, rd, sfx = M[key][3]
            m = cv2.imread(f'{TRAIN}/pred/{pred_name(2, int(J), rd)}{sfx}/{r["id"]}_{mode}.png', 0) > 0
            pan.append((magenta(rgb, m), [('old ' if key == old_k else 'new ') + M[key][2][:44], _cap(M[key][1][r['id']])]))
        line = []
        for im, txt in pan:
            im = cv2.resize(im, (S, S), interpolation=cv2.INTER_AREA if im.shape[0] > S else cv2.INTER_NEAREST)
            head = np.full((HEADH, S, 3), 255, np.uint8)
            for i, t in enumerate(txt):
                cv2.putText(head, t, (4, 16 + 18 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 1, cv2.LINE_AA)
            line += [np.vstack([head, im]), np.full((S + HEADH, 6, 3), 255, np.uint8)]
        line = np.hstack(line)
        bar = np.full((22, line.shape[1], 3), 235, np.uint8)
        cv2.putText(bar, 'picked as: ' + why, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
        prow += [bar, line, np.full((10, line.shape[1], 3), 255, np.uint8)]
    W = prow[1].shape[1]
    ht = [f'{title}. Half-resolution U-Net (MobileNetV2), cross-validation by day on the 42 TRAINING cells only.',
          'COLOURS: solid magenta = plant. Grey with no fill (a grey copy of the crop) = not plant. First column: the crop in colour.',
          'Each row is one cell, scored by the fold model that never saw that day.',
          f'Columns: crop in colour | Aaron\'s truth | grow from leaf cores | old: {on} | new: {nn_}.',
          'Production cells: network run on the whole photo; development cells: on the crop alone (photos purged).',
          'Captions: IoU with the truth, area = marked px / truth px. Same 8 cells as stage A, picked by the same fixed rules.']
    head = np.full((20 * len(ht) + 12, W, 3), 255, np.uint8)
    for i, t in enumerate(ht):
        cv2.putText(head, t, (6, 20 + 20 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.imwrite(f'{SCR}/stage-{st_}.png', cv2.cvtColor(np.vstack([head] + prow), cv2.COLOR_RGB2BGR))
    L += ['', '## Picture', '', f'`stage-{st_}.png`: columns crop | truth | grow from leaf cores | old ({on}) | new ({nn_}). '
          'The same 8 cells as stage A, by the same rules (the best/worst rules use stage A\'s half-resolution IoU, so they '
          'pick the same cells):', '']
    L += [f'- {r["id"]}: {why}' for why, r in picks]
    L += ['', 'Files: `experiments/round4-segmentation-nn/code/train_cv.py` (method in its docstring), driver '
          f'`~/temp.nobackup/npec-406-nn/analysis/train/{ {"D1": "run_d.sh", "D2": "run_de.sh", "E": "run_de.sh"}.get(st_, "run_bc.sh")}`; per-fold scores `runs/<run>/scores*.csv`, predictions '
          '`pred/<run>/`, under `~/temp.nobackup/npec-406-nn/analysis/train/`.', '']
    open(f'{SCR}/stage-{st_}.md', 'w').write('\n'.join(L))
    print('\n'.join(L))
    log(f'stage {st_} summary written: stage-{st_}.md, stage-{st_}.png; decision: {verdict}')


def cmd_folds(a):
    fold = folds()
    man, ph = cells(), photos()
    rows = []
    for d in sorted(fold):
        rows.append(dict(day=d, fold=fold[d] + 1,
                         prod_cells=sum(1 for r in man if r['day'] == d and r['rig'] == 'prod'),
                         dev_cells=sum(1 for r in man if r['day'] == d and r['rig'] == 'dev'),
                         prod_photos=sum(1 for p in ph if p['day_utc'] == d and p['rig'] == 'production'),
                         dev_photos=sum(1 for p in ph if p['day_utc'] == d and p['rig'] == 'development')))
    write_csv(f'{RESULTS}/train_cv_folds.csv', rows)
    for k in range(NFOLD):
        rr = [r for r in rows if r['fold'] == k + 1]
        print(k + 1, [r['day'][5:] for r in rr], 'cells prod', sum(r['prod_cells'] for r in rr), 'dev',
              sum(r['dev_cells'] for r in rr), 'photos', sum(r['prod_photos'] + r['dev_photos'] for r in rr))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['folds', 'cache', 'train', 'score', 'report', 'sheet', 'timing', 'photo', 'stage',
                                    'compare', 'best_read', 'truth_cells', 'rescore', 'e_init'])
    ap.add_argument('--scale', type=int, choices=[1, 2])
    ap.add_argument('--fold', type=int)
    ap.add_argument('--epochs', type=int)
    ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--photo', help='photo key for the photo command, e.g. production_28022')
    ap.add_argument('--suffix', default='', help='run folder suffix: trial runs, and stage D1 fold runs (_pt6)')
    ap.add_argument('--pretrain', choices=list(PRETRAIN),
                    help='stage D: pre-train on public tiles (pt6: the 6 sets of D1; pt7: all 7 sets, D2)')
    ap.add_argument('--init', help='stage D: start training from runs/<init>/model.pt (e.g. pt6)')
    ap.add_argument('--final', action='store_true', help='stage F: train / score the network of every training day')
    ap.add_argument('--edit-tag', default=TRUTH_EDIT_TAG,
                    help='truth_cells / rescore: tag of the backups made before this truth edit (before_purple_check)')
    ap.add_argument('--force', action='store_true', help='redo a train or score step that is already done')
    ap.add_argument('--jitter', type=int, default=PAD, choices=JITTERS, help='training crop jitter (stage C: 128)')
    ap.add_argument('--read', default='mid192', choices=list(READS), help='how a photo is read (stage B: avg128)')
    ap.add_argument('--reads-table', action='store_true', help='timing: write train_cv_timing_reads.csv (stage B)')
    ap.add_argument('--stage', choices=['B', 'C', 'D1', 'D2', 'E'], help='compare: which stage summary to write')
    a = ap.parse_args()
    globals()['cmd_' + a.cmd](a)


if __name__ == '__main__':
    main()
