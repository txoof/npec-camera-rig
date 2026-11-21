"""#406 step 2: training labels for the copied full photos by grow from leaf cores (README, step 2).
  make_labels.py DATA DBDIR OUT RESULTS [N] [--only RIG:CID,...]
DATA = npec-406-nn/data/rigs, DBDIR holds prod.db and dev.db (code/load_dump.py), OUT the label root
(masks/<rig>/<capture_id>.png), RESULTS the folder with labels_photos.csv (code/select_photos.py),
where labels_done.csv and labels_trays.csv are written. N worker processes (default 6).

Label PNG, single channel, full size: 0 not plant (inside a tray), 1 plant, 255 ignore (outside every
tray). Trays and tags are the rig's own stored ones; grow from leaf cores is the app's
segmentation.grow_trays; experiments 9 to 16 are negatives inside trays found by the app's
tray_placement.find_outlines."""
import csv
import json
import os
import sqlite3
import sys
import time
from multiprocessing import Pool

import cv2
import numpy as np
from PIL import Image

from npec_rig import images, segmentation
from npec_rig.calibration import scale_field_from_dict
from npec_rig.tray_placement import find_outlines
from npec_rig.tray_readings import FINDER_FACTOR

import grow_loose

DB = {'production': 'prod.db', 'development': 'dev.db'}
NEG_CAL = ('/home/txoof/temp.nobackup/npec-406-nn/data/kept-from-testpi02/kept-from-dev/'
           'steady-20261110T115150Z/calibration/prod_20261022T072523939958.json')
PLANT, NOT, IGNORE = 1, 0, 255
_SF = None
# Aaron, 2026-11-20 (README, step 2, decision): production experiment 18, every labelled photo.
# Trays 9, 10, 11, 12 hold no plants (paper squares, labels, empty pots, tag sheets): all 0. Tray 7: CELLS_KEPT.
# Tray 8 holds a synthetic Arabidopsis-like plant (and the yellow target): all 255, so the network
# learns nothing from it either way. Tray numbers are the tray tag ids, as the app stores them.
OVERRIDE = {('production', '18'): {9: NOT, 10: NOT, 11: NOT, 12: NOT, 8: IGNORE}}
# Tray 7 (Aaron, 2026-11-20, from tray7_exp18.png): cells B1, C1, D1, A2, B2, C2 hold real plants in
# pots; every other cell (A1 the tag cell included) holds an empty slot, an empty pot or green
# calibration samples. Grow from leaf cores over the whole tray, then 0 inside every other cell's
# opening, as the app placed and stored the cells (cell_reading). Between cells only marks whose
# connected piece reaches into one of the six cells stay (leaves overhanging from the plant cells);
# other pieces (paper edges past the openings) become 0.
CELLS_KEPT = {('production', '18', 7): {'B1', 'C1', 'D1', 'A2', 'B2', 'C2'}}
RULE_WORDS = {NOT: 'not plant (Aaron 2026-11-20)', IGNORE: 'ignore (Aaron 2026-11-20)'}
# Untagged trays of experiment 18 that the rig's own readings do not name (no tagged tray stored
# within NAME_DIST_PX in the photos nearby), labelled by eye on 2026-11-20 (README, step 2):
BY_EYE = {('production', 23643): IGNORE,   # the yellow target with the synthetic plant (tray 8), tag outside the photo
          ('production', 20821): NOT,      # a tray of tag sheets being carried in by hand, no plant
          ('production', 38164): NOT,      # empty black pots and mat scraps at the photo edge, no plant
          ('production', 38284): NOT,      # the same tray, 2 hours later
          ('production', 39483): None}     # a plant tray (tray 6's place, 192 px) with a camera held over it: grown
# Glare (Aaron, 2026-11-20, check sheet 09, 10, 12): light reflected by the clear domes and by water
# pooled in empty slots on development was marked plant. A plant piece (8-connected) whose mean
# brightest channel is GLARE_V or more becomes 0. Over all 24,620 pieces of the 293 labels, plants
# lie below 160 (the brightest, 150 to 159, are 50 production pieces) and no piece lies from 160 to
# 169; the 51 pieces from 170 up hold 12,401 pixels, 12,169 of them on development.
GLARE_V = 160
NAME_WINDOW = 30   # captures (one a minute on production) either side searched to name an untagged tray
NAME_DIST_PX = 150  # a tagged tray whose stored centre lies this close names it


def name_untagged(con, cid, cx, cy):
    """The tag id of the tray stored nearest (cx, cy) in the rig's own readings of the photos within
    NAME_WINDOW captures, by majority; None when none lies within NAME_DIST_PX."""
    rows = con.execute(
        "select tray_id from tray_reading where capture_id between ? and ? and tray_id is not null "
        "and outline is not null and (centre_x_px-?)*(centre_x_px-?)+(centre_y_px-?)*(centre_y_px-?) < ?",
        (cid - NAME_WINDOW, cid + NAME_WINDOW, cx, cx, cy, cy, NAME_DIST_PX ** 2)).fetchall()
    if not rows:
        return None, 0
    ids = [r[0] for r in rows]
    best = max(set(ids), key=ids.count)
    return best, ids.count(best) / len(ids)


def keep_marks_touching(lab, outline, keep_cells, centre=None, others=()):
    """Inside the tray `outline`, keep plant marks (8-connected pieces) only when the piece reaches
    into one of `keep_cells` (cell opening corners); every other piece becomes 0 (Aaron, 2026-11-20:
    paper edges sticking out past cell openings are not plant). Pixels where the outline overlaps
    another tray's (`others`: (outline, centre)) and that tray's centre is nearer are that tray's
    (segmentation.measure_trays) and are left alone."""
    H, W = lab.shape
    c = np.asarray(outline, np.float64)
    x0, y0 = np.clip(np.floor(c.min(0)).astype(int), 0, [W, H])
    x1, y1 = np.clip(np.ceil(c.max(0)).astype(int) + 1, 0, [W, H])
    box = lab[y0:y1, x0:x1]
    ins = np.zeros(box.shape, np.uint8)
    cv2.fillPoly(ins, [np.round(c - [x0, y0]).astype(np.int32).reshape(-1, 1, 2)], 1)
    kc = np.zeros(box.shape, np.uint8)
    for k in keep_cells:
        cv2.fillPoly(kc, [np.round(np.asarray(k, np.float64) - [x0, y0]).astype(np.int32).reshape(-1, 1, 2)], 1)
    plant = ((box == PLANT) & (ins > 0)).astype(np.uint8)
    n, lbl = cv2.connectedComponents(plant, connectivity=8, ltype=cv2.CV_32S)
    ok = np.zeros(n, bool)
    ok[np.unique(lbl[(kc > 0) & (plant > 0)])] = True
    ok[0] = True
    drop = ~ok[lbl]
    if centre is not None:
        xs = np.arange(x0, x1) + 0.5
        ys = (np.arange(y0, y1) + 0.5)[:, None]
        own = (xs - centre[0]) ** 2 + (ys - centre[1]) ** 2
        for o2, c2 in others:
            m2 = np.zeros(box.shape, np.uint8)
            cv2.fillPoly(m2, [np.round(np.asarray(o2, np.float64) - [x0, y0]).astype(np.int32).reshape(-1, 1, 2)], 1)
            drop &= ~((m2 > 0) & (((xs - c2[0]) ** 2 + (ys - c2[1]) ** 2) < own))
    box[drop] = NOT


def apply_override(lab, trays_px, values):
    """Set every pixel inside each overridden tray outline to its value. Where its outline overlaps
    another tray with a different rule, a pixel goes to the tray whose centre is nearer (the app's
    rule for touching trays, segmentation.measure_trays). trays_px: (outline, centre) per tray;
    values: per tray None (keep grow from leaf cores) or the label value."""
    H, W = lab.shape
    boxes = []
    for o, _ in trays_px:
        c = np.asarray(o, np.float64)
        x0, y0 = np.clip(np.floor(c.min(0)).astype(int), 0, [W, H])
        x1, y1 = np.clip(np.ceil(c.max(0)).astype(int) + 1, 0, [W, H])
        boxes.append((x0, y0, x1, y1))

    def inside(box, o):
        x0, y0, x1, y1 = box
        m = np.zeros((y1 - y0, x1 - x0), np.uint8)
        cv2.fillPoly(m, [np.round(np.asarray(o, np.float64) - [x0, y0]).astype(np.int32).reshape(-1, 1, 2)], 1)
        return m.astype(bool)
    for i, ((o, cen), v) in enumerate(zip(trays_px, values)):
        if v is None:
            continue
        b = boxes[i]
        if b[2] <= b[0] or b[3] <= b[1]:
            continue
        ins = inside(b, o)
        for j, ((o2, cen2), v2) in enumerate(zip(trays_px, values)):
            if j == i or v2 == v:
                continue
            x0, y0 = max(b[0], boxes[j][0]), max(b[1], boxes[j][1])
            x1, y1 = min(b[2], boxes[j][2]), min(b[3], boxes[j][3])
            if x0 >= x1 or y0 >= y1:
                continue
            xs = np.arange(x0, x1) + 0.5
            ys = (np.arange(y0, y1) + 0.5)[:, None]
            lose = ((xs - cen2[0]) ** 2 + (ys - cen2[1]) ** 2) < ((xs - cen[0]) ** 2 + (ys - cen[1]) ** 2)
            part = ins[y0 - b[1]:y1 - b[1], x0 - b[0]:x1 - b[0]]
            part &= ~(inside((x0, y0, x1, y1), o2) & lose)
        lab[b[1]:b[3], b[0]:b[2]][ins] = v


def sf():
    global _SF
    if _SF is None:
        _SF = scale_field_from_dict(json.load(open(NEG_CAL))['scale_field'])
    return _SF


def fill(lab, corners):
    cv2.fillPoly(lab, [np.round(np.asarray(corners, np.float64)).astype(np.int32).reshape(-1, 1, 2)], NOT)


def grow_photo(p, data, dbdir):
    con = sqlite3.connect(f"file:{dbdir}/{DB[p['rig']]}?mode=ro", uri=True)
    path = p['jpg'].split('/', 1)[1][:-4]  # experiments/<folder>/stills/<day>/<name>
    cal = con.execute('select calibration from capture where id=?', (int(p['capture_id']),)).fetchone()[0]
    tray_rows = con.execute(
        "select tray_id, found, outline, centre_x_px, centre_y_px, grown_plant_px, grown_soil_level, grown_lower_cutoff "
        "from tray_reading where capture_id=? and placement='placed' and outline is not null order by id",
        (int(p['capture_id']),)).fetchall()
    tags = json.loads(con.execute("select value from capture_analysis where kind='tags' and source=?", (path,)).fetchone()[0])
    override = OVERRIDE.get((p['rig'], p['experiment_id']), {})
    cells_zero = {}
    for (rig, exp, tid), kept in CELLS_KEPT.items():
        if (rig, exp) == (p['rig'], p['experiment_id']):
            got = con.execute('select cell, corners from cell_reading where capture_id=? and tray_id=?',
                              (int(p['capture_id']), tid)).fetchall()
            cells_zero[tid] = ([json.loads(c) for name, c in got if name not in kept],
                               [json.loads(c) for name, c in got if name in kept])
    named = [(r[0], 1.0) if r[0] is not None or not override else name_untagged(con, int(p['capture_id']), r[3], r[4])
             for r in tray_rows]
    con.close()
    t0 = time.perf_counter()
    rgb = images.decode_full(f"{data}/{p['jpg']}")
    t1 = time.perf_counter()
    trays = []
    for tid, found, outline, cx, cy, *_ in tray_rows:
        corners = [t['corners'] for t in tags if tid is not None and t['tag_id'] == tid]
        trays.append((json.loads(outline), corners))
    # The smallest seedlings kept (grow_loose.py, Aaron 2026-11-20); `app` is the app's own mask.
    grown, levels, app = grow_loose.grow_trays(rgb, trays)
    t2 = time.perf_counter()
    h, w = rgb.shape[:2]
    n_cc, cc = cv2.connectedComponents(grown.astype(np.uint8), connectivity=8, ltype=cv2.CV_32S)
    idx = cc[grown]
    bright = np.bincount(idx, rgb[grown].max(1).astype(np.float64), n_cc) / np.maximum(np.bincount(idx, minlength=n_cc), 1)
    glare = (bright >= GLARE_V)[cc] & grown
    del rgb, cc, idx
    lab = np.full((h, w), IGNORE, np.uint8)
    for outline, _ in trays:
        fill(lab, outline)
    lab[grown & ~glare] = PLANT
    for tid, (cells, keep_cells) in cells_zero.items():
        for i, ((n, _), (o, _c)) in enumerate(zip(named, trays)):
            if n != tid:
                continue
            assert len(cells) == 14 and len(keep_cells) == 6, (p['capture_id'], tid, len(cells))
            for c in cells:
                fill(lab, c)
            keep_marks_touching(lab, o, keep_cells, (tray_rows[i][3], tray_rows[i][4]),
                                [(trays[j][0], (tray_rows[j][3], tray_rows[j][4])) for j in range(len(trays)) if j != i])
    values = [override.get(n) if n is not None else BY_EYE.get((p['rig'], int(p['capture_id']))) if override else None
              for n, _ in named]
    apply_override(lab, [(o, (r[3], r[4])) for (o, _), r in zip(trays, tray_rows)], values)
    meas = segmentation.measure_trays(app, [(o, (r[3], r[4])) for (o, _), r in zip(trays, tray_rows)], sf())
    per_tray = []
    final = segmentation.measure_trays(lab == PLANT, [(o, (r[3], r[4])) for (o, _), r in zip(trays, tray_rows)], sf())
    for (tid, found, _o, _cx, _cy, s_px, s_soil, s_cut), (soil, cut), m, (_, corners), (nm, share), v, f in zip(
            tray_rows, levels, meas, trays, named, values, final):
        per_tray.append(dict(rig=p['rig'], capture_id=p['capture_id'], day_utc=p['day_utc'], tray_id=tid,
                             named_as=('' if nm is None else nm) if tid is None and override else '',
                             named_share=(round(share, 3) if nm is not None else 'by eye') if tid is None and override else '',
                             label_rule=RULE_WORDS.get(v, 'grow from leaf cores' + (
                                 ', 0 outside cells ' + ' '.join(sorted(CELLS_KEPT[(p['rig'], p['experiment_id'], nm)]))
                                 + ' (Aaron 2026-11-20)' if (p['rig'], p['experiment_id'], nm) in CELLS_KEPT else '')), final_plant_px=f.plant_px, found=found,
                             own_tags=len(corners), soil_level=soil, lower_cutoff=cut,
                             soil_hidden=segmentation.soil_hidden(soil), plant_px=m.plant_px,
                             stored_grown_px=s_px, stored_soil_level=s_soil, stored_lower_cutoff=s_cut,
                             same_as_rig=(s_px == m.plant_px), outline=_o))
    for t in per_tray:
        t['glare_px_whole_photo'] = int(glare.sum())
    return lab, cal, len(trays), per_tray, (t1 - t0, t2 - t1)


def negative_photo(p, data):
    t0 = time.perf_counter()
    with Image.open(f"{data}/{p['jpg']}") as im:
        w, h = im.size
        im.draft('RGB', (w // FINDER_FACTOR, h // FINDER_FACTOR))
        small = np.asarray(im.convert('RGB'))
    t1 = time.perf_counter()
    outlines = find_outlines(small, sf(), w / small.shape[1])
    lab = np.full((h, w), IGNORE, np.uint8)
    for o in outlines:
        fill(lab, o.corners)
    t2 = time.perf_counter()
    return lab, os.path.basename(NEG_CAL)[5:-5] + ' (scale only)', len(outlines), [], (t1 - t0, t2 - t1)


def one(args):
    p, data, dbdir, out = args
    cv2.setNumThreads(2)
    t0 = time.perf_counter()
    if p['label_kind'] == 'negative':
        lab, cal, n, per_tray, (td, tg) = negative_photo(p, data)
    else:
        lab, cal, n, per_tray, (td, tg) = grow_photo(p, data, dbdir)
    t1 = time.perf_counter()
    os.makedirs(f"{out}/masks/{p['rig']}", exist_ok=True)
    f = f"{out}/masks/{p['rig']}/{p['capture_id']}.png"
    cv2.imwrite(f, lab, [cv2.IMWRITE_PNG_COMPRESSION, 3])
    t2 = time.perf_counter()
    cnt = np.bincount(lab.ravel(), minlength=256)
    n0, n1, n255 = int(cnt[NOT]), int(cnt[PLANT]), int(cnt[IGNORE])
    assert n0 + n1 + n255 == lab.size
    row = dict(rig=p['rig'], capture_id=p['capture_id'], utc_time=p['utc_time'], day_utc=p['day_utc'],
               experiment_id=p['experiment_id'], sets=p['sets'], label_kind=p['label_kind'],
               steadiness_flag=p['steadiness_flag'], calibration=cal, trays=n, px_not_plant=n0, px_plant=n1,
               px_ignore=n255, plant_share_in_trays=round(n1 / (n0 + n1), 6) if n0 + n1 else '',
               trays_same_as_rig=sum(t['same_as_rig'] for t in per_tray) if per_tray else '',
               decode_s=round(td, 2), label_s=round(tg, 2), write_s=round(t2 - t1, 2), total_s=round(t2 - t0, 2),
               mask=os.path.relpath(f, out))
    print(json.dumps({k: row[k] for k in ('rig', 'capture_id', 'trays', 'px_plant', 'trays_same_as_rig', 'total_s')}), flush=True)
    return row, per_tray


def main(data, dbdir, out, results, n=6, *rest):
    photos = [r for r in csv.DictReader(open(f'{results}/labels_photos.csv')) if r['labelled'] == 'yes']
    if rest and rest[0] == '--only':
        want = set(rest[1].split(','))
        photos = [p for p in photos if f"{p['rig']}:{p['capture_id']}" in want]
    t0 = time.time()
    with Pool(int(n)) as pool:
        res = pool.map(one, [(p, data, dbdir, out) for p in photos], chunksize=1)
    rows = [r for r, _ in res]
    trays = [t for _, ts in res for t in ts]
    tag = '' if not rest else '_partial'
    for name, rr in ((f'labels_done{tag}.csv', rows), (f'labels_trays{tag}.csv', trays)):
        if rr:
            with open(f'{results}/{name}', 'w', newline='') as fh:
                w = csv.DictWriter(fh, fieldnames=list(rr[0]))
                w.writeheader()
                w.writerows(rr)
    print(json.dumps(dict(photos=len(rows), workers=int(n), wall_s=round(time.time() - t0, 1))))


if __name__ == '__main__':
    main(*sys.argv[1:])
