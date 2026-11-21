"""#406, log 44: 8 cells for Aaron to label from nothing (no draft), for scoring only, never training: a fair
comparison of grow from leaf cores and the network, since every existing truth began as a grow draft.

  handlabel_select.py stats DATA DBDIR GROWMASKS RESULTS HIDDEN [N]
  handlabel_select.py pick  HIDDEN
  handlabel_select.py make  DATA HIDDEN OUT SCRATCH

DATA = npec-406-nn/data/rigs, DBDIR = analysis/labels-grow/db (prod.db, dev.db), GROWMASKS =
analysis/labels-grow/masks, RESULTS = this experiment's results/ (labels_photos.csv), HIDDEN =
analysis/labels/handlabel_selection (per-cell statistics and picks: they hold grow numbers, so Aaron does
not open this folder before he has labelled), OUT = analysis/labels/handlabel (what Aaron opens), SCRATCH =
scratch/406-train. N worker processes for `stats` (default 3; each holds one full photo, about 1.5 GB).

Which photos (fixed before any cell was looked at):
- Production: the lit spread photos of experiment 18 taken on a production TEST day (24, 27 and 30 October,
  2, 3, 5 and 8 November; README step 2), 49 photos. No network trains on a test day in any stage, so the
  network has never seen grow labels of these pixels, and its score on them is fair for every stage,
  the final network included. The reference photos (which hold the test cells) and the steadiness photos
  of 3 November are left out.
- Development: the lit spread photos of experiment 4 (13 to 20 November), labelled for training, not
  flagged steadiness, 48 photos. Development has no test day and experiment 3 (the reference photos) was
  purged, so these are the only development photos still available. A development cell is a training
  photo: the fair network score there is the cross-validation fold that held out its day. Before 16
  November the development trays carried no tray tags, so the rig stored no cells for those photos; the
  development cells come from 16 to 20 November only.
- Not flagged for steadiness, lit (no `lights off` or `light changing` exclusion), file on disk.

Which cells: the cells the rig stored for the photo (`cell_reading`, holds = plant): production trays 1
to 6 (the plant trays; trays 7 to 12 hold paper, targets, empty pots or the synthetic plant), development
trays 8, 9, 11 and 12 (every development tray with pots). Left out: any cell with the same rig, UTC day,
tray and cell as a reference cell of `../../round3-classifier/data/manifest.csv`, training or test (only
the id columns of that manifest are read; no test crop or truth is opened).

Crop: as `../../round3-classifier/code/drafts402.py`: the stored cell corners' bounding box plus 40 px on
every side (floor of the minimum - 40, ceiling of the maximum + 1 + 40, clipped to the photo), native
pixels from cv2.imread, lossless.

Per-cell statistics (stats), from the machine label and the photo, never from a network:
- Machine label: grow from leaf cores as the training labels (README step 2). Development: the existing
  label PNG (`GROWMASKS/development/<capture>.png`, 1 = plant). Production test days have no label PNG
  (they were never labelled), so it is made with the same code, `make_labels.grow_photo`, kept in memory
  only. The same function, run on one development photo, is checked to give its label PNG exactly.
- plant_open: machine plant pixels inside the cell opening (the stored corners' polygon); plant_crop:
  in the whole crop.
- blue_share: share of opening pixels with B > R + 20 and B > G + 20 (drafts402.BLUE_MARGIN).
- soil_level: the tray's soil level as the rig stored it (`tray_reading.grown_soil_level`).
- yellow_excess: yellow pixels (HSV hue 32 to 55 degrees, saturation >= 140, value >= 100) that the
  machine label marks not plant and that lie within 10 px of a machine plant pixel, minus what the cell's
  own soil gives: (yellow share of the not-plant pixels more than 30 px from plant) x (number of not-plant
  pixels within 10 px of plant). Yellow leaves next to green tissue score high; soil does not.
- purple_px: the largest spot of `purple_check.find` (the Task 1 rule, docstring of purple_check.py) on
  the crop with the machine label as the plant mask, counting only spots whose median hue lies at least
  12 degrees below the cell's soil reference (B21's decided stalk: 14.6 degrees below).

Groups and pick (pick), in this order; each pool is sorted by (capture id, tray, cell) and one cell is drawn
with random.Random('406-handlabel-<group>'). A drawn cell's (rig, tray, cell) is removed from the later
pools, so the 8 cells are 8 different pots.
1. production seedling: photo of 24 October (the first test day), plant_open 1 to 1500 px.
2. production blue mat: blue_share >= 0.30 and plant_open >= 1.
3. production green soil: photo before 6 November (no mats), plant_open >= 1, soil_level in the top 10% of
   those cells (the greenest soil).
4. production yellowing leaves: yellow_excess in the top 5% of production cells with plant_open >= 1, and
   at least 100 px.
5. development small plant: plant_open from 1 px to the 25th percentile of development cells with plant.
6. development large plant: plant_open in the top 10% of development cells with plant.
7. development yellowing leaves: as 4, on development cells.
8. reddish-purple stalk: purple_px >= 100, either rig; if no cell reaches 100, the group is left empty.

Second version (2026-11-21), the only change after a first pick: the first yellow rule (hue 16 to 38,
saturation >= 120, value >= 60, README step 1's rough rule) and the first purple count (any spot of the
Task 1 rule, 5 degrees below the soil) picked production cells whose crops show no yellow leaf and no
purple stalk: production's red-brown soil itself passes both. The yellow band was moved, on the 42
TRAINING crops only, to the band where production soil gives 0 not-plant pixels (hue 32 to 55, saturation
>= 140, value >= 100: production 0 px over 17 crops, against 2,206 with the first rule) and B21 and B24,
the training cells with yellow leaves, rank first and second on development. The purple count was given
the 12 degree contrast above. The first picks are kept in HIDDEN/picks_v1.json.

Third version (2026-11-21): the second yellow rule finds no cell at all, on the 97 photos above nor on the
154 production training-day photos (`stats_train`, HIDDEN/cell_stats_train.csv: largest yellow_excess
3 px): the rig's photos of experiments 18 and 4 never reach saturation 140 with value 100 in that band. A
yellowing group whose pool is empty therefore falls back to the first-version pool (HIDDEN/
cell_stats_v1.csv), with the same seed; the pick is marked doubtful in the manifest's note column. No
rule was changed again after this.

Fourth version (2026-11-21, Aaron): the reserved production test days are not to be touched, so the five
production cells of the third version (H01 to H04 and H08, all from test days) are replaced. The third
version's picks are kept in HIDDEN/picks_v3_testday.json and its production files in
analysis/labels/handlabel_old_testday/. The development cells H05 to H07 are kept as they were; H07's
group is renamed "development pale seedling" (Aaron: production has no yellow leaves and the development
"yellowing" cell is a pale seedling, so no yellow group remains).

  handlabel_select.py pick_train HIDDEN FOLDS
  handlabel_select.py make_v4    DATA HIDDEN OUT OLD PACKAGE SCRATCH

FOLDS = results/train_cv_folds.csv, OLD = analysis/labels/handlabel_old_testday, PACKAGE = the folder that
becomes handlabel_406/ in the download zip (SCRATCH/handlabel_package.zip). Templates of the package text
files (README, AGENT, check script) are in code/handlabel_package/. No Fiji macro is shipped (Aaron,
2026-11-21): the AI agent on Aaron's computer writes and tests it there, from the specification in AGENT.md.

New production pool: HIDDEN/cell_stats_train.csv, made by `stats_train` before this version, unchanged:
production experiment 18 spread photos labelled for training (a production TRAINING day; lit, i.e. no
`lights off` or `light changing` exclusion; not steadiness-flagged; file on disk in DATA), 154 photos,
15,804 stored plant-tray cells, the 42 training reference cells (and the test reference cells) already
left out by rig, UTC day, tray and cell. Every UTC day must be in FOLDS (asserted), so every cell has a
stage E cross-validation fold model that did not train on its day (fold k of FOLDS = run folder
runs/s2_f{k-1}_e40), and none may be a test day (asserted against the list of README step 2). No test
photo, test cell or test truth is opened. The statistics are those of `cell_stats` (machine label and
photo only, never a network).

Groups, drawn in this order, each pool sorted by (capture id, tray, cell), one cell drawn with
random.Random('406-handlabel-<group>'), a drawn (rig, tray, cell) removed from the later pools (and the
kept development cells' pots too, which can not clash: other rig):
1. H01 production tiny seedling: photo of 22 October (the first production training day of experiment
   18), plant_open 1 to 1500 px.
2. H02 production blue mat: blue_share >= 0.30 and plant_open >= 1 (as before).
3. H03 production normal small plant: photo before 6 November (bare soil, no mat), plant_open from the
   25th to the 75th percentile of those cells with plant_open >= 1.
4. H04 production larger plant: plant_open in the top 10% of all pool cells with plant_open >= 1.
5. H08 production reddish-purple stalk: purple_px >= 100 (second-version purple count). Whether the
   drawn crop really shows a reddish-purple stalk is judged from the colour crop and written in the
   manifest note; the cell is not redrawn.
"""
import csv
import json
import os
import random
import sqlite3
import sys
import multiprocessing as mp

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
EXP = os.path.normpath(os.path.join(HERE, '..', '..'))
REF_MANIFEST = os.path.join(EXP, 'round3-classifier', 'data', 'manifest.csv')

MARGIN = 40
BLUE_MARGIN = 20
DB = {'production': 'prod.db', 'development': 'dev.db'}
SHORT = {'production': 'prod', 'development': 'dev'}
PLANT_TRAYS = {'production': {1, 2, 3, 4, 5, 6}, 'development': {8, 9, 11, 12}}
NEAR_YELLOW, FAR_YELLOW = 10, 30
PURPLE_CONTRAST = 12.0
GROUPS = ['production seedling', 'production blue mat', 'production green soil', 'production yellowing leaves',
          'development small plant', 'development large plant', 'development yellowing leaves',
          'reddish-purple stalk']
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONTB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'


def photos(results, data, train=False):
    """train=False: the photos above. train=True: the fallback pool, production spread photos of experiment
    18 labelled for training (lit, not steadiness)."""
    out = []
    for p in csv.DictReader(open(os.path.join(results, 'labels_photos.csv'))):
        if p['steadiness_flag'] or p['exclusion'] or p['sets'] != 'spread':
            continue
        if train:
            if p['rig'] == 'production' and p['labelled'] == 'yes' and p['experiment_id'] == '18' and \
                    os.path.exists(os.path.join(data, p['jpg'])):
                out.append(p)
            continue
        if p['rig'] == 'production' and p['why_not'] == 'test day':
            pass
        elif p['rig'] == 'development' and p['labelled'] == 'yes':
            pass
        else:
            continue
        if os.path.exists(os.path.join(data, p['jpg'])):
            out.append(p)
    return out


def ref_cells():
    """(rig, day, tray, cell) of every reference cell, training and test. Only the id columns are read."""
    keep = set()
    for r in csv.DictReader(open(REF_MANIFEST)):
        keep.add(({'prod': 'production', 'dev': 'development'}[r['rig']], r['day'], int(r['tray']), r['cell']))
    return keep


def crop_box(corners, w, h):
    c = np.asarray(corners, np.float64)
    x0, y0 = np.maximum(np.floor(c.min(0)).astype(int) - MARGIN, 0)
    x1, y1 = np.minimum(np.ceil(c.max(0)).astype(int) + 1 + MARGIN, [w, h])
    return int(x0), int(y0), int(x1 - x0), int(y1 - y0)


def yellow(rgb):
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    hdeg = hsv[..., 0].astype(int) * 2
    return (hdeg >= 32) & (hdeg <= 55) & (hsv[..., 1] >= 140) & (hsv[..., 2] >= 100)


def cell_stats(rgb, plant, opening):
    from purple_check import find
    notp = ~plant
    blue = (rgb[..., 2].astype(int) > rgb[..., 0].astype(int) + BLUE_MARGIN) & \
           (rgb[..., 2].astype(int) > rgb[..., 1].astype(int) + BLUE_MARGIN)
    out = dict(plant_open=int((plant & opening).sum()), plant_crop=int(plant.sum()),
               blue_share=round(float(blue[opening].mean()), 4))
    if plant.any():
        d = ndi.distance_transform_edt(notp)
        y = yellow(rgb)
        near = notp & (d <= NEAR_YELLOW)
        far = notp & (d > FAR_YELLOW)
        base = float(y[far].mean()) if far.sum() >= 500 else float(y[notp].mean())
        out['yellow_excess'] = round(float((y & near).sum() - base * near.sum()), 1)
        soil, spots = find(rgb, plant, -5.0)
        out['purple_px'] = max([s['px'] for s in spots if soil - s['s'] >= PURPLE_CONTRAST], default=0)
    else:
        out['yellow_excess'] = 0.0
        out['purple_px'] = 0
    return out


def machine_label(p, data, dbdir, growmasks):
    f = os.path.join(growmasks, p['rig'], p['capture_id'] + '.png')
    if p['labelled'] == 'yes' and os.path.exists(f):
        return cv2.imread(f, cv2.IMREAD_GRAYSCALE)
    import make_labels
    lab, *_ = make_labels.grow_photo(p, data, dbdir)
    return lab


def one(args):
    p, data, dbdir, growmasks, refs = args
    cv2.setNumThreads(1)
    con = sqlite3.connect(f"file:{dbdir}/{DB[p['rig']]}?mode=ro", uri=True)
    cells = con.execute("select tray_id, cell, corners from cell_reading where capture_id=? and holds='plant'",
                        (int(p['capture_id']),)).fetchall()
    soil = dict(con.execute('select tray_id, grown_soil_level from tray_reading where capture_id=?',
                            (int(p['capture_id']),)).fetchall())
    con.close()
    lab = machine_label(p, data, dbdir, growmasks)
    bgr = cv2.imread(os.path.join(data, p['jpg']))
    H, W = bgr.shape[:2]
    assert lab.shape == (H, W)
    rows = []
    for tid, cell, corners in cells:
        if tid not in PLANT_TRAYS[p['rig']] or (p['rig'], p['day_utc'], tid, cell) in refs:
            continue
        corners = json.loads(corners)
        x0, y0, w, h = crop_box(corners, W, H)
        rgb = cv2.cvtColor(bgr[y0:y0 + h, x0:x0 + w], cv2.COLOR_BGR2RGB)
        plant = lab[y0:y0 + h, x0:x0 + w] == 1
        opening = np.zeros((h, w), np.uint8)
        cv2.fillPoly(opening, [np.round(np.asarray(corners) - [x0, y0]).astype(np.int32).reshape(-1, 1, 2)], 1)
        st = cell_stats(rgb, plant, opening > 0)
        rows.append(dict(rig=p['rig'], capture_id=p['capture_id'], taken_at=p['utc_time'], day=p['day_utc'],
                         experiment=p['experiment_id'], jpg=p['jpg'], tray=tid, cell=cell, crop_x0=x0, crop_y0=y0,
                         crop_w=w, crop_h=h, soil_level=soil.get(tid), **st))
    print(p['rig'], p['capture_id'], len(rows), flush=True)
    return rows


def check_label_code(data, dbdir, growmasks, p):
    """make_labels.grow_photo on one development photo must give its stored label PNG exactly."""
    import make_labels
    lab, *_ = make_labels.grow_photo(p, data, dbdir)
    stored = cv2.imread(os.path.join(growmasks, 'development', p['capture_id'] + '.png'), cv2.IMREAD_GRAYSCALE)
    return bool(np.array_equal(lab, stored))


def stats_train(data, dbdir, growmasks, results, hidden, n=3):
    """Per-cell statistics of the fallback pool (production training-day photos), cell_stats_train.csv."""
    ps = photos(results, data, train=True)
    refs = ref_cells()
    with mp.get_context('spawn').Pool(int(n)) as pool:
        res = pool.map(one, [(p, data, dbdir, growmasks, refs) for p in ps], chunksize=1)
    rows = [r for rr in res for r in rr]
    with open(os.path.join(hidden, 'cell_stats_train.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(len(ps), 'photos', len(rows), 'cells (fallback pool)')


def stats(data, dbdir, growmasks, results, hidden, n=3):
    os.makedirs(hidden, exist_ok=True)
    ps = photos(results, data)
    refs = ref_cells()
    dev = [p for p in ps if p['rig'] == 'development']
    same = check_label_code(data, dbdir, growmasks, dev[len(dev) // 2])
    print('grow_photo equals the stored development label:', same, flush=True)
    assert same
    # spawn, not fork: the parent has run OpenCV (the label check), and forked workers then hang
    with mp.get_context('spawn').Pool(int(n)) as pool:
        res = pool.map(one, [(p, data, dbdir, growmasks, refs) for p in ps], chunksize=1)
    rows = [r for rr in res for r in rr]
    with open(os.path.join(hidden, 'cell_stats.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    json.dump(dict(photos=len(ps), production=sum(p['rig'] == 'production' for p in ps), development=len(dev),
                   cells=len(rows), label_code_check=dict(capture=dev[len(dev) // 2]['capture_id'], equal=same)),
              open(os.path.join(hidden, 'stats_run.json'), 'w'), indent=1)
    print(len(ps), 'photos', len(rows), 'cells')


def pools(rows):
    num = lambda r, k: float(r[k]) if r[k] not in ('', 'None') else None  # noqa: E731
    prod = [r for r in rows if r['rig'] == 'production']
    dev = [r for r in rows if r['rig'] == 'development']
    P = {}
    P['production seedling'] = [r for r in prod if r['day'] == '2026-10-24' and 1 <= num(r, 'plant_open') <= 1500]
    P['production blue mat'] = [r for r in prod if num(r, 'blue_share') >= 0.30 and num(r, 'plant_open') >= 1]
    pre = [r for r in prod if r['day'] < '2026-11-06' and num(r, 'plant_open') >= 1 and num(r, 'soil_level') is not None]
    cut = np.percentile([num(r, 'soil_level') for r in pre], 90)
    P['production green soil'] = [r for r in pre if num(r, 'soil_level') >= cut]
    lim = {}
    for rig, rr in (('production', prod), ('development', dev)):
        wp = [r for r in rr if num(r, 'plant_open') >= 1]
        c = max(100.0, float(np.percentile([num(r, 'yellow_excess') for r in wp], 95)))
        lim[rig] = c
        P[f'{rig} yellowing leaves'] = [r for r in wp if num(r, 'yellow_excess') >= c]
    dp = [num(r, 'plant_open') for r in dev if num(r, 'plant_open') >= 1]
    q25, q90 = np.percentile(dp, 25), np.percentile(dp, 90)
    P['development small plant'] = [r for r in dev if 1 <= num(r, 'plant_open') <= q25]
    P['development large plant'] = [r for r in dev if num(r, 'plant_open') >= q90]
    P['reddish-purple stalk'] = [r for r in rows if num(r, 'purple_px') >= 100]
    cuts = dict(green_soil_p90=float(cut), yellow_min=lim, dev_plant_p25=float(q25), dev_plant_p90=float(q90))
    return P, cuts


def pick(hidden):
    rows = list(csv.DictReader(open(os.path.join(hidden, 'cell_stats.csv'))))
    P, cuts = pools(rows)
    # Fallback for a yellowing group whose pool is empty under the second-version yellow rule: the pool of
    # the first-version rule (cell_stats_v1.csv), and the pick is marked doubtful (docstring, third version).
    v1 = os.path.join(hidden, 'cell_stats_v1.csv')
    P1 = pools(list(csv.DictReader(open(v1))))[0] if os.path.exists(v1) else {}
    used, picks = set(), []
    for g in GROUPS:
        note = ''
        src = P[g]
        if not src and g.endswith('yellowing leaves') and P1.get(g):
            src = P1[g]
            note = ('no cell passes the second yellow rule; drawn from the first-version yellow pool, '
                    'whose production picks showed no yellow leaf: doubtful')
        pool = sorted((r for r in src if (r['rig'], r['tray'], r['cell']) not in used),
                      key=lambda r: (int(r['capture_id']), int(r['tray']), r['cell']))
        if not pool:
            picks.append(dict(group=g, pool=0, row=None, note='no cell in the pool'))
            continue
        r = random.Random(f'406-handlabel-{g}').choice(pool)
        used.add((r['rig'], r['tray'], r['cell']))
        picks.append(dict(group=g, pool=len(pool), row=r, note=note))
    json.dump(dict(cuts=cuts, picks=picks), open(os.path.join(hidden, 'picks.json'), 'w'), indent=1)
    for p in picks:
        r = p['row']
        print(p['group'], p['pool'], r and (r['rig'], r['capture_id'], r['day'], r['tray'], r['cell']))
    print(cuts)


def make_files(data, hidden, out, scratch):
    picks = [p for p in json.load(open(os.path.join(hidden, 'picks.json')))['picks'] if p['row']]
    for d in ('crops', 'cells', 'empty', 'labelled'):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    man, tiles = [], []
    for i, p in enumerate(picks, start=1):
        r = p['row']
        hid = f'H{i:02d}'
        name = f"{SHORT[r['rig']]}_{r['day']}_{r['tray']}_{r['cell']}"
        x0, y0, w, h = (int(r[k]) for k in ('crop_x0', 'crop_y0', 'crop_w', 'crop_h'))
        bgr = cv2.imread(os.path.join(data, r['jpg']))
        rgb = np.ascontiguousarray(cv2.cvtColor(bgr[y0:y0 + h, x0:x0 + w], cv2.COLOR_BGR2RGB))
        del bgr
        Image.fromarray(rgb).save(os.path.join(out, 'crops', name + '.png'))
        Image.fromarray(rgb).save(os.path.join(out, 'cells', name + '.tif'))  # uncompressed RGB TIFF, as drafts402
        assert np.array_equal(np.asarray(Image.open(os.path.join(out, 'cells', name + '.tif')).convert('RGB')), rgb)
        assert np.array_equal(np.asarray(Image.open(os.path.join(out, 'crops', name + '.png')).convert('RGB')), rgb)
        cv2.imwrite(os.path.join(out, 'empty', name + '_mask.png'), np.zeros((h, w), np.uint8))
        man.append(dict(id=hid, name=name, rig=r['rig'], photo_capture_id=r['capture_id'], photo_taken_utc=r['taken_at'],
                        photo_file=r['jpg'], experiment=r['experiment'], tray=r['tray'], cell=r['cell'],
                        group=p['group'], crop_x0=x0, crop_y0=y0, crop_w=w, crop_h=h, note=p.get('note', '')))
        tiles.append((hid, r, p['group'] + (' (doubtful: no yellow leaf seen)' if p.get('note') else ''), rgb))
    with open(os.path.join(out, 'manifest.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(man[0]))
        w.writeheader()
        w.writerows(man)
    macro(man, os.path.join(out, 'handlabel.ijm'))
    overview(tiles, os.path.join(scratch, 'handlabel_cells.png'))


def macro(man, path):
    ids = ','.join(f'"{m["id"]}"' for m in man)
    names = ','.join(f'"{m["name"]}"' for m in man)
    src = f'''// Issue 406: label 8 cells from nothing, one after another (handlabel_instructions.md).
// Plugins > Macros > Run..., choose this file, then choose the handlabel folder (the one that holds cells/).
// Each cell opens zoomed, with no outline. Outline every piece of plant, click OK: it saves and opens the next.
// Cells already saved are skipped, so you can stop (Cancel) and run it again later to carry on.
ids = newArray({ids});
names = newArray({names});
dir = getArgument();
if (dir == "") dir = getDirectory("Choose the handlabel folder (the one that holds cells)");
if (!endsWith(dir, File.separator)) dir = dir + File.separator;
cells = dir + "cells" + File.separator;
out = dir + "labelled" + File.separator;
File.makeDirectory(out);
run("Wand Tool...", "tolerance=20 mode=8-connected");
n = names.length;
for (i = 0; i < n; i++) {{
  done = out + names[i] + "_hand.roi.zip";
  none = out + names[i] + "_none.txt";
  if (File.exists(done) || File.exists(none)) continue;
  open(cells + names[i] + ".tif");
  img = getImageID();
  roiManager("reset");
  roiManager("Show All without labels");
  z = floor(100 * minOf((screenWidth - 450) / getWidth(), (screenHeight - 150) / getHeight()));
  if (z > 800) z = 800;
  run("Set... ", "zoom=" + z + " x=" + floor(getWidth() / 2) + " y=" + floor(getHeight() / 2));
  setTool("wand");
  msg = "No draft: outline every piece of plant in the whole crop.\\n";
  msg = msg + "New piece: Wand or polygon (or selection brush), then Add in the ROI Manager.\\n";
  msg = msg + "Changed piece: select it, edit, then Update. Wrong piece: select it, Delete.\\n";
  msg = msg + "Plant: green and purple living tissue. Not plant: yellow, brown or dead leaf, soil, tray.\\n";
  msg = msg + "Every leaf in the crop counts, also neighbours' leaves.\\n \\n";
  msg = msg + "OK saves and opens the next (no piece added = saved as no plant). Cancel stops; run again later.";
  waitForUser(ids[i] + "   (" + (i + 1) + " of " + n + ")   " + names[i], msg);
  selectImage(img);
  run("Select None");
  roiManager("Deselect");
  if (roiManager("count") > 0) roiManager("Save", done);
  else File.saveString("none\\n", none);
  roiManager("reset");
  close();
}}
showMessage("All done", "Your outlines are in " + out);
'''
    open(path, 'w').write(src)


def overview(tiles, path):
    TH, pad, cap = 420, 20, 68
    ims = []
    for hid, r, g, rgb in tiles:
        s = TH / rgb.shape[0]
        ims.append(Image.fromarray(rgb).resize((round(rgb.shape[1] * s), TH), Image.LANCZOS))
    cols = 4
    cw = max(i.width for i in ims)
    rows_n = (len(ims) + cols - 1) // cols
    head = 70
    W = cols * cw + (cols + 1) * pad
    img = Image.new('RGB', (W, head + rows_n * (TH + cap + pad)), 'white')
    dr = ImageDraw.Draw(img)
    dr.text((pad, 12), 'The 8 cells for you to label from nothing (#406). Colour photo crops only: no label, no draft, '
            'no machine output.', fill='black', font=ImageFont.truetype(FONTB, 20))
    dr.text((pad, 40), 'Each crop is the cell opening plus 40 px on every side, shown at the same height '
            f'({TH} px); production crops are enlarged more than development ones.', fill='black',
            font=ImageFont.truetype(FONT, 16))
    for k, ((hid, r, g, rgb), im) in enumerate(zip(tiles, ims)):
        x = pad + (k % cols) * (cw + pad)
        y = head + (k // cols) * (TH + cap + pad)
        dr.text((x, y), f"{hid}: {r['rig']} rig, photo of {r['day']}", fill='black',
                font=ImageFont.truetype(FONTB, 16))
        dr.text((x, y + 22), f"Tray {r['tray']}, cell {r['cell']}.  Crop {rgb.shape[1]} x {rgb.shape[0]} px.",
                fill='black', font=ImageFont.truetype(FONT, 15))
        dr.text((x, y + 42), f"Group: {g}", fill='black', font=ImageFont.truetype(FONT, 15))
        img.paste(im, (x, y + cap))
    img.save(path)


# ---------------------------------------------------------------- fourth version (training days only)

# README step 2: production test days (development's, 5 and 8 November, are among them)
TEST_DAYS = {'2026-10-24', '2026-10-27', '2026-10-30', '2026-11-02', '2026-11-03', '2026-11-05', '2026-11-08'}
KEEP_DEV = {'development small plant': ('H05', 'development small plant'),
            'development large plant': ('H06', 'development large plant'),
            'development yellowing leaves': ('H07', 'development pale seedling')}
V4_GROUPS = [('H01', 'production tiny seedling'), ('H02', 'production blue mat'),
             ('H03', 'production normal small plant'), ('H04', 'production larger plant'),
             ('H08', 'production reddish-purple stalk')]
ORDER = ['H01', 'H02', 'H03', 'H04', 'H05', 'H06', 'H07', 'H08']
# Judged from the colour crops after the draw (2026-11-21), not used to redraw: H08's crop shows two green
# cotyledons with an olive-brown centre, no reddish-purple tissue; the 8 pool cells (different pots) with the
# largest purple_px show none either: the rule catches the reddish soil next to seedlings.
V4_NOTES = {'H08': 'doubtful: no convincing reddish-purple stalk seen in the colour crop, nor in the 8 pool cells '
                   'with the largest purple_px (other pots); the purple rule seems to catch reddish soil next to '
                   'the seedling. Label it as seen.'}
PKG_SRC = os.path.join(HERE, 'handlabel_package')


def read_folds(path):
    return {r['day']: int(r['fold']) for r in csv.DictReader(open(path))}


def pools_v4(rows):
    num = lambda r, k: float(r[k]) if r[k] not in ('', 'None') else None  # noqa: E731
    wp = [r for r in rows if r['rig'] == 'production' and num(r, 'plant_open') >= 1]
    P = {}
    P['production tiny seedling'] = [r for r in wp if r['day'] == '2026-10-22' and num(r, 'plant_open') <= 1500]
    P['production blue mat'] = [r for r in wp if num(r, 'blue_share') >= 0.30]
    pre = [r for r in wp if r['day'] < '2026-11-06']
    q25, q75 = np.percentile([num(r, 'plant_open') for r in pre], [25, 75])
    P['production normal small plant'] = [r for r in pre if q25 <= num(r, 'plant_open') <= q75]
    q90 = np.percentile([num(r, 'plant_open') for r in wp], 90)
    P['production larger plant'] = [r for r in wp if num(r, 'plant_open') >= q90]
    P['production reddish-purple stalk'] = [r for r in wp if num(r, 'purple_px') >= 100]
    cuts = dict(small_p25=float(q25), small_p75=float(q75), larger_p90=float(q90))
    return P, cuts


def pick_train(hidden, folds_csv):
    """Fourth version: new production picks from training days; development picks of the third version kept."""
    folds = read_folds(folds_csv)
    v3 = os.path.join(hidden, 'picks_v3_testday.json')
    if not os.path.exists(v3):
        os.rename(os.path.join(hidden, 'picks.json'), v3)
    old = json.load(open(v3))['picks']
    rows = list(csv.DictReader(open(os.path.join(hidden, 'cell_stats_train.csv'))))
    assert all(r['day'] in folds and r['day'] not in TEST_DAYS for r in rows)
    P, cuts = pools_v4(rows)
    picks = {}
    used = set()
    for p in old:
        if p['group'] in KEEP_DEV:
            hid, g = KEEP_DEV[p['group']]
            r = p['row']
            note = ''
            if hid == 'H07':
                note = ('kept from the third version; Aaron 2026-11-21: no yellow leaves, labelled as a pale '
                        'development seedling (drawn from the first-version yellow pool)')
            picks[hid] = dict(id=hid, group=g, pool=p['pool'], row=r, note=note, version=3)
            used.add((r['rig'], r['tray'], r['cell']))
    for hid, g in V4_GROUPS:
        pool = sorted((r for r in P[g] if (r['rig'], r['tray'], r['cell']) not in used),
                      key=lambda r: (int(r['capture_id']), int(r['tray']), r['cell']))
        if not pool:
            picks[hid] = dict(id=hid, group=g, pool=0, row=None, note='no cell in the pool', version=4)
            continue
        r = random.Random(f'406-handlabel-{g}').choice(pool)
        used.add((r['rig'], r['tray'], r['cell']))
        picks[hid] = dict(id=hid, group=g, pool=len(pool), row=r, note=V4_NOTES.get(hid, ''), version=4)
    for hid in ORDER:
        r = picks[hid]['row']
        if r:
            assert r['day'] in folds and r['day'] not in TEST_DAYS, (hid, r['day'])
            picks[hid]['fold'] = folds[r['day']]
            picks[hid]['fold_run'] = f"s2_f{folds[r['day']] - 1}_e40"
    out = dict(version=4, cuts=cuts, picks=[picks[h] for h in ORDER])
    json.dump(out, open(os.path.join(hidden, 'picks.json'), 'w'), indent=1)
    for hid in ORDER:
        p = picks[hid]
        r = p['row']
        print(hid, p['group'], p['pool'], r and (r['rig'], r['capture_id'], r['day'], r['tray'], r['cell'],
                                                 r['plant_open'], r['purple_px']), 'fold', p.get('fold'))
    print(cuts)


def _crop(data, r):
    x0, y0, w, h = (int(r[k]) for k in ('crop_x0', 'crop_y0', 'crop_w', 'crop_h'))
    bgr = cv2.imread(os.path.join(data, r['jpg']))
    rgb = np.ascontiguousarray(cv2.cvtColor(bgr[y0:y0 + h, x0:x0 + w], cv2.COLOR_BGR2RGB))
    del bgr
    return rgb, (x0, y0, w, h)


def _move_old(out, old):
    """Third-version production cells (test days) and the old texts out of the package folder, once."""
    if os.path.exists(old):
        return
    rows = list(csv.DictReader(open(os.path.join(out, 'manifest.csv'))))
    assert 'fold' not in rows[0], 'manifest is not the third version'
    for d in ('cells', 'crops', 'empty'):
        os.makedirs(os.path.join(old, d))
    prod = [r for r in rows if r['rig'] == 'production']
    for r in prod:
        n = r['name']
        for d, suf in (('cells', '.tif'), ('crops', '.png'), ('empty', '_mask.png')):
            os.rename(os.path.join(out, d, n + suf), os.path.join(old, d, n + suf))
    for f in ('handlabel.ijm', 'handlabel_instructions.md'):
        os.rename(os.path.join(out, f), os.path.join(old, f))
    with open(os.path.join(old, 'manifest.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(prod)
    with open(os.path.join(old, 'NOTE.md'), 'w') as fh:
        fh.write(
            '# Old hand-labelling picks from production test days (#406, not used)\n\n'
            'The third version of `handlabel_select.py` drew H01, H02, H03, H04 and H08 from production TEST days\n'
            '(24 and 30 October, 3 and 8 November). Aaron does not want the reserved test days touched (2026-11-21),\n'
            'so these five cells were replaced by cells from production training days (fourth version, docstring of\n'
            '`experiments/round4-segmentation-nn/code/handlabel_select.py`). They are kept here only as a record:\n'
            'do not label them and do not score on them. `manifest.csv` is their third-version manifest rows;\n'
            '`handlabel.ijm` and `handlabel_instructions.md` are the third-version macro and instructions. The\n'
            'development cells H05 to H07 of the third version were kept and are in `../handlabel/`.\n'
            'The third version\'s picks (with their statistics) are in `../handlabel_selection/picks_v3_testday.json`.\n')
    print('moved', len(prod), 'old production cells to', old)


def _fill(template, **kw):
    s = open(os.path.join(PKG_SRC, template)).read()
    for k, v in kw.items():
        assert k in s, (template, k)
        s = s.replace(k, v)
    return s


def make_v4(data, hidden, out, old, package, scratch):
    """Fourth version: handlabel folder, old picks moved out, overview, download package and zip."""
    import shutil
    import zipfile
    picks = json.load(open(os.path.join(hidden, 'picks.json')))
    assert picks.get('version') == 4
    picks = picks['picks']
    assert [p['id'] for p in picks] == ORDER and all(p['row'] for p in picks)
    _move_old(out, old)
    for d in ('crops', 'cells', 'empty', 'labelled', 'returned'):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    if os.path.exists(package):
        shutil.rmtree(package)
    os.makedirs(os.path.join(package, 'cells'))
    os.makedirs(os.path.join(package, 'labelled'))
    man, pman, tiles = [], [], []
    for p in picks:
        r = p['row']
        hid = p['id']
        name = f"{SHORT[r['rig']]}_{r['day']}_{r['tray']}_{r['cell']}"
        file = f'{hid}_{name}'
        rgb, (x0, y0, w, h) = _crop(data, r)
        # a kept development cell: the third-version crop must be the same pixels; then its unprefixed files go
        for d, suf in (('crops', '.png'), ('cells', '.tif'), ('empty', '_mask.png')):
            f = os.path.join(out, d, name + suf)
            if os.path.exists(f):
                if d != 'empty':
                    assert np.array_equal(np.asarray(Image.open(f).convert('RGB')), rgb), f
                os.remove(f)
        Image.fromarray(rgb).save(os.path.join(out, 'crops', file + '.png'))
        Image.fromarray(rgb).save(os.path.join(out, 'cells', file + '.tif'))  # uncompressed RGB TIFF
        Image.fromarray(rgb).save(os.path.join(package, 'cells', file + '.tif'))
        for f in (os.path.join(out, 'cells', file + '.tif'), os.path.join(out, 'crops', file + '.png'),
                  os.path.join(package, 'cells', file + '.tif')):
            im = Image.open(f)
            assert im.mode == 'RGB' and np.array_equal(np.asarray(im), rgb), f
        cv2.imwrite(os.path.join(out, 'empty', file + '_mask.png'), np.zeros((h, w), np.uint8))
        man.append(dict(id=hid, name=name, file=file, rig=r['rig'], photo_capture_id=r['capture_id'],
                        photo_taken_utc=r['taken_at'], photo_file=r['jpg'], experiment=r['experiment'], day=r['day'],
                        fold=p['fold'], fold_run=p['fold_run'], tray=r['tray'], cell=r['cell'], group=p['group'],
                        crop_x0=x0, crop_y0=y0, crop_w=w, crop_h=h, selection_version=p['version'], note=p['note']))
        pman.append(dict(id=hid, file=file + '.tif', rig=r['rig'], date=r['day'], tray=r['tray'], cell=r['cell'],
                         group=p['group'], crop_size=f'{w} x {h}'))
        tiles.append((hid, r, p['group'], rgb))
    for path, rows in ((os.path.join(out, 'manifest.csv'), man), (os.path.join(package, 'manifest.csv'), pman)):
        with open(path, 'w', newline='') as fh:
            wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
            wr.writeheader()
            wr.writerows(rows)
    table = '| Id | Rig | Photo date (UTC) | Tray, cell | Group |\n|---|---|---|---|---|\n' + '\n'.join(
        f"| {m['id']} | {m['rig']} | {m['day']} | {m['tray']}, {m['cell']} | {m['group']} |" for m in man)
    readme = _fill('README.md', **{'@CELL_TABLE@': table})
    # No macro is shipped (Aaron, 2026-11-21): the agent on his computer writes and tests it there, from
    # the specification in AGENT.md.
    for d in (out, package):
        open(os.path.join(d, 'README.md'), 'w').write(readme)
    for f in ('AGENT.md', 'check_results.py'):
        shutil.copy(os.path.join(PKG_SRC, f), os.path.join(package, f))
    allowed = {'cells', 'labelled', 'README.md', 'AGENT.md', 'check_results.py', 'manifest.csv'}
    assert set(os.listdir(package)) == allowed, os.listdir(package)
    assert sorted(os.listdir(os.path.join(package, 'cells'))) == sorted(m['file'] + '.tif' for m in man)
    zpath = os.path.join(scratch, 'handlabel_package.zip')
    with zipfile.ZipFile(zpath + '.tmp', 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('handlabel_406/', '')
        z.writestr('handlabel_406/labelled/', '')
        for f in ('README.md', 'AGENT.md', 'manifest.csv', 'check_results.py'):
            z.write(os.path.join(package, f), 'handlabel_406/' + f)
        z.writestr('handlabel_406/cells/', '')
        for m in man:
            z.write(os.path.join(package, 'cells', m['file'] + '.tif'), f"handlabel_406/cells/{m['file']}.tif")
    os.replace(zpath + '.tmp', zpath)
    overview_v4(tiles, os.path.join(scratch, 'handlabel_cells.png'))
    print('package', zpath, os.path.getsize(zpath), 'bytes')


def overview_v4(tiles, path):
    """Colour crops only, plain captions: id, rig, date, tray and cell, group."""
    TH, pad, cap = 420, 20, 70
    ims = [Image.fromarray(rgb).resize((round(rgb.shape[1] * TH / rgb.shape[0]), TH), Image.LANCZOS)
           for _, _, _, rgb in tiles]
    cols = 4
    cw = max(max(i.width for i in ims), 430)
    rows_n = (len(ims) + cols - 1) // cols
    head = 50
    img = Image.new('RGB', (cols * cw + (cols + 1) * pad, head + rows_n * (TH + cap + pad)), 'white')
    dr = ImageDraw.Draw(img)
    dr.text((pad, 12), 'The 8 cells to label from nothing (#406). Colour photo crops only.', fill='black',
            font=ImageFont.truetype(FONTB, 20))
    fb, fr = ImageFont.truetype(FONTB, 17), ImageFont.truetype(FONT, 16)
    for k, ((hid, r, g, rgb), im) in enumerate(zip(tiles, ims)):
        x = pad + (k % cols) * (cw + pad)
        y = head + (k // cols) * (TH + cap + pad)
        dr.text((x, y), f"{hid}   {r['rig']}   {r['day']}", fill='black', font=fb)
        dr.text((x, y + 24), f"tray {r['tray']}, cell {r['cell']}", fill='black', font=fr)
        dr.text((x, y + 46), g, fill='black', font=fr)
        img.paste(im, (x, y + cap))
    img.save(path)


if __name__ == '__main__':
    cmd, *a = sys.argv[1:]
    dict(stats=stats, stats_train=stats_train, pick=pick, make=make_files, pick_train=pick_train,
         make_v4=lambda *x: make_v4(*x))[cmd](*a)
