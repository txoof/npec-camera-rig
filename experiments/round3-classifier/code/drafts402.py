"""#402, metrology log 33: draft plant masks by rule H (24.8) for about 30 cells per rig, for Aaron to
check and correct. Run on the development rig, one photo per process, one tray at a time.

  measure DATA OUT RIG CAPTURE   rule H and current rule per tray, composed into a full-photo
                                 draft (OUT/work/<rig>_<day>_H.png), per-cell values to
                                 OUT/work/<rig>_<day>_cells.json
  select OUT                     seeded pick of cells (seed 402), OUT/work/picks.json
  crops DATA OUT RIG CAPTURE     crops, draft ROI zips (round trip checked), draft PNGs, previews,
                                 and the photo's overview, for the picks on that photo
  sheets OUT                     picture sheets, manifest.csv
Calibration: each capture's tray readings name the calibration they were read with; it is looked
up in DATA/calibration and in ./calibration-extra (the production twin calibration of 26 Oct,
copied read-only from ac-testing, since the staged one is the 22 Oct original)."""
import glob
import json
import math
import os
import resource
import sys
import time

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mask_rois import mask_to_roi_zip, roi_zip_to_mask  # noqa: E402
from ruleg402 import rules  # noqa: E402
from npec_rig.calibration import scale_field_from_dict  # noqa: E402
from npec_rig.segmentation import measure_cells  # noqa: E402
from npec_rig.tags import TagDetection  # noqa: E402
from npec_rig.tray_placement import Cell, TrayPlacement, place_cells  # noqa: E402

SEED = 402
N_PER_RIG = 30
MARGIN = 40
BLUE_MARGIN = 20  # strongly blue: b > r + 20 and b > g + 20 (0 to 255 values)
N_EMPTY, N_MAT, N_GREEN, N_SIZE_BINS = 3, 4, 4, 5
REMOVED = {'prod': ((9, 11, 12), '2026-11-06')}  # trays read near 0 plant from that day on
LETTER = {'prod': 'A', 'dev': 'B'}
MAGENTA, RED = (255, 0, 255), (0, 0, 255)  # BGR


def load(data, rig):
    return json.load(open(f'{data}/{rig}/readings.json'))['captures']


def scale_field(data, name):
    here = os.path.dirname(os.path.abspath(__file__))
    files = glob.glob(f'{data}/calibration/*{name}.json') + glob.glob(f'{here}/calibration-extra/*{name}.json')
    return scale_field_from_dict(json.load(open(files[0]))['scale_field'])


def tray_box(img, outline):
    """As check_prod_crops_h.tray_box (pad 0), also returning the box's origin."""
    H, W = img.shape[:2]
    o = np.asarray(outline, float)
    x0, y0 = np.maximum(np.floor(o.min(0)).astype(int), 0)
    x1, y1 = np.minimum(np.ceil(o.max(0)).astype(int) + 1, [W, H])
    ins = np.zeros((y1 - y0, x1 - x0), np.uint8)
    cv2.fillPoly(ins, [np.round(o - [x0, y0]).astype(np.int32).reshape(-1, 1, 2)], 1)
    return np.ascontiguousarray(img[y0:y1, x0:x1]), ins > 0, (int(x0), int(y0))


def read_rgb(path):
    bgr = cv2.imread(path)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    del bgr
    return rgb


def bearings_1106(caps):
    """Each 2 x 2 tray's A1 bearing from its first stored-cell row (11-06 on development)."""
    out = {}
    for v in sorted(caps.values(), key=lambda v: v['taken_at']):
        if not v['cells_stored']:
            continue
        for r in v['readings']:
            if r['tray_id'] is not None and r.get('a1_bearing_deg') is not None:
                out.setdefault(r['tray_id'], (v['day'], r['a1_bearing_deg']))
    return out


def measure(data, out, rig, cid):
    t0 = time.time()
    caps = load(data, rig)
    v = caps[cid]
    day = v['day']
    sf = scale_field(data, v['readings'][0]['calibration'])
    img = read_rgb(f"{data}/{rig}/{v['file']}")
    H, W = img.shape[:2]
    tags = {}
    for t in v['tags']:
        tags.setdefault(t['tag_id'], []).append(t)
    Hm = np.zeros((H, W), bool)
    cur = np.zeros((H, W), bool)
    trays, skipped = [], []
    for r in v['readings']:
        if r['tray_id'] is None:
            skipped.append(dict(tray=None, why='no tray id'))
            continue
        if r['placement'] != 'placed' or r['outline'] is None:
            skipped.append(dict(tray=r['tray_id'], why=f"placement {r['placement']}"))
            continue
        tid = r['tray_id']
        sub, ins, (x0, y0) = tray_box(img, r['outline'])
        own = [TagDetection(tid, tuple((c[0] - x0, c[1] - y0) for c in t['corners']),
                            (t['centre'][0] - x0, t['centre'][1] - y0)) for t in tags.get(tid, [])]
        m = rules(sub, ins, tid, tags=own)
        h, w = ins.shape
        Hm[y0:y0 + h, x0:x0 + w] |= m['H']
        cur[y0:y0 + h, x0:x0 + w] |= m['current']
        trays.append(dict(r=r, soil_peak=m['soil_peak'], cut_h=m['cut_h'], warn_h=bool(m['warn_h']),
                          n_own_tags=len(own)))
        del sub, ins, m
    bear = bearings_1106(caps)
    stored = {}
    for c in v['cells']:
        stored.setdefault(c['tray_id'], []).append(c)
    rows = []
    for t in trays:
        r = t['r']
        tid = r['tray_id']
        why = None
        if 'partly outside the photo' in r['warnings']:
            why = 'partly outside the photo'
        elif t['n_own_tags'] != 1:
            why = f"{t['n_own_tags']} tags with its id"
        if why:
            skipped.append(dict(tray=tid, why=why))
            continue
        if v['cells_stored']:
            cells = [Cell(c['cell'], (c['centre_x_px'], c['centre_y_px']), tuple(map(tuple, c['corners'])), c['holds'])
                     for c in sorted(stored[tid], key=lambda c: c['cell'])]
            how = 'stored'
        else:
            p = TrayPlacement(tid, (r['centre_x_px'], r['centre_y_px']), r['slot'], r['a1_corner'], r['tilt_deg'],
                              tuple(map(tuple, r['outline'])), r['margin_mm'], 'placed')
            tg = tags[tid][0]
            tag = TagDetection(tid, tuple(map(tuple, tg['corners'])), tuple(tg['centre']))
            b = bear[tid][1] if r['tray_type'] == '2x2' else None
            if r['tray_type'] == '2x2' and tid not in bear:
                skipped.append(dict(tray=tid, why='2x2 with no stored bearing'))
                continue
            cells = sorted(place_cells(p, tag, sf, a1_bearing_deg=b), key=lambda c: c.name)
            how = 'placed again' + (f' (bearing of {bear[tid][0]})' if b is not None else '')
        mh = measure_cells(Hm, cells, sf, outline_px=r['outline'])
        mc = measure_cells(cur, cells, sf, outline_px=r['outline'])
        st = {c['cell']: c for c in stored.get(tid, [])}
        for c, a, b2 in zip(cells, mh, mc):
            if c.holds != 'plant':
                continue
            sub, ins, (x0, y0) = tray_box(img, c.corners)
            px = sub[ins].astype(np.int16)
            rr, gg, bb = px[:, 0], px[:, 1], px[:, 2]
            blue = float(((bb > rr + BLUE_MARGIN) & (bb > gg + BLUE_MARGIN)).mean())
            ppm = sf.px_per_mm(*c.centre)
            rows.append(dict(rig=rig, day=day, capture_id=int(cid), taken_at=v['taken_at'], jpeg_quality=v['jpeg_quality'],
                             jpeg_note=v['jpeg_note'], tray=tid, tray_type=r['tray_type'], cell=c.name, cells_from=how,
                             corners=[list(map(float, q)) for q in c.corners], centre=list(map(float, c.centre)),
                             mm2_per_px=1 / ppm ** 2, ruleH_px=a.plant_px, current_px=b2.plant_px,
                             stored_current_px=st[c.name]['plant_px'] if c.name in st else None,
                             soil_peak=t['soil_peak'], cut_h=t['cut_h'], warn_h=t['warn_h'], blue_share=blue,
                             opening_px=int(ins.sum())))
    os.makedirs(f'{out}/work', exist_ok=True)
    cv2.imwrite(f'{out}/work/{rig}_{day}_H.png', Hm.astype(np.uint8) * 255, [cv2.IMWRITE_PNG_COMPRESSION, 1])
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    info = dict(rig=rig, day=day, capture_id=int(cid), seconds=round(time.time() - t0, 1), peak_mb=round(peak),
                n_trays_drafted=len(trays), skipped=skipped,
                trays=[dict(tray=t['r']['tray_id'], soil_peak=t['soil_peak'], cut_h=t['cut_h'], warn_h=t['warn_h'])
                       for t in trays])
    json.dump(dict(info=info, cells=rows), open(f'{out}/work/{rig}_{day}_cells.json', 'w'))
    print(json.dumps(info))


def split_of(rig, day, days):
    i = days.index(day) + 1
    return 'test' if i % 3 == 0 or (rig == 'prod' and day == '2026-11-03') else 'train'


def select(out):
    rng = np.random.default_rng(SEED)
    picks = []
    for rig in ('prod', 'dev'):
        rows = []
        for f in sorted(glob.glob(f'{out}/work/{rig}_*_cells.json')):
            rows += json.load(open(f))['cells']
        days = sorted({r['day'] for r in rows})
        removed_trays, since = REMOVED.get(rig, ((), '9999'))
        for r in rows:
            r['removed'] = r['tray'] in removed_trays and r['day'] >= since
        chosen = []
        key = lambda r: (r['day'], r['tray'], r['cell'])  # noqa: E731
        taken = set()

        def take(r, stratum):
            r = dict(r, stratum=stratum)
            chosen.append(r)
            taken.add(key(r))

        def prefer(cands):
            """Uncovered days first, then a tray cell not yet picked; random within the best group."""
            have_days = {c['day'] for c in chosen}
            have_tc = {(c['tray'], c['cell']) for c in chosen}
            best = min((r['day'] in have_days, (r['tray'], r['cell']) in have_tc) for r in cands)
            group = [r for r in cands if (r['day'] in have_days, (r['tray'], r['cell']) in have_tc) == best]
            return group[rng.integers(len(group))]

        free = lambda: [r for r in rows if key(r) not in taken]  # noqa: E731
        # Empty: the cells with no rule H pixel, any tray (removed trays included).
        for _ in range(N_EMPTY):
            c = [r for r in free() if r['ruleH_px'] == 0]
            if c:
                take(prefer(c), 'empty')
        live = lambda: [r for r in free() if not r['removed']]  # noqa: E731
        # Blue mats: the highest blue shares (ties in random order), each from another tray and,
        # where there are enough, another day.
        order = list(live())
        tie = rng.permutation(len(order))
        order = [order[i] for i in sorted(range(len(order)), key=lambda i: (-round(order[i]['blue_share'], 3), tie[i]))]
        for need_new_day in (True, False):
            for r in order:
                mats = [c for c in chosen if c['stratum'] == 'blue mat']
                if len(mats) >= N_MAT:
                    break
                if key(r) in taken or r['blue_share'] <= 0 or r['tray'] in {c['tray'] for c in mats}:
                    continue
                if need_new_day and r['day'] in {c['day'] for c in mats}:
                    continue
                take(r, 'blue mat')
        # Greenest soils: the trays with the highest soil peak (one photo each), a cell with plant.
        seen = set()
        for r in sorted(live(), key=lambda r: -r['soil_peak']):
            if len(seen) >= N_GREEN:
                break
            if r['tray'] in seen:
                continue
            c = [q for q in live() if q['day'] == r['day'] and q['tray'] == r['tray'] and q['ruleH_px'] > 0]
            if c:
                seen.add(r['tray'])
                take(prefer(c), 'green soil')
        # Plant size: bins of equal count on rule H px over the cells with plant.
        sized = sorted([r for r in rows if r['ruleH_px'] > 0 and not r['removed']], key=lambda r: r['ruleH_px'])
        edges = [sized[int(len(sized) * k / N_SIZE_BINS)]['ruleH_px'] for k in range(N_SIZE_BINS)] + [math.inf]
        bin_of = lambda r: next(k for k in range(N_SIZE_BINS) if edges[k] <= r['ruleH_px'] < edges[k + 1])  # noqa: E731
        k = 0
        while len(chosen) < N_PER_RIG and k < 1000:
            missing = set(days) - {c['day'] for c in chosen}
            c = [r for r in live() if r['ruleH_px'] > 0 and bin_of(r) == k % N_SIZE_BINS]
            if missing and len(chosen) >= N_PER_RIG - len(missing):
                c = [r for r in c if r['day'] in missing] or [r for r in live() if r['day'] in missing and r['ruleH_px'] > 0]
            if c:
                r = prefer(c)
                take(r, f'size {bin_of(r) + 1} of {N_SIZE_BINS}')
            k += 1
        chosen.sort(key=key)
        for i, r in enumerate(chosen):
            r['id'] = f'{LETTER[rig]}{i + 1:02d}'
            r['split'] = split_of(rig, r['day'], days)
            r['name'] = f"{rig}_{r['day']}_{r['tray']}_{r['cell']}"
        picks += chosen
        print(rig, len(rows), 'candidate cells;', len(chosen), 'picked; size bin edges (rule H px)', edges[:-1])
    json.dump(dict(seed=SEED, blue_margin=BLUE_MARGIN, picks=picks), open(f'{out}/work/picks.json', 'w'), indent=1)

# Amended selection (metrology log 33, amendment of 2026-11-09).
PLANT_TRAYS = {'prod': set(range(1, 7))}  # production plant trays; development: every tray with pots
MISSING_POT_BLUE = 0.3  # development: a cell whose opening is over 30% strongly blue has no pot
# (pots read 0.02 to 0.094, missing pots 0.47 to 0.87, 2026-11-03 to 11-09: a clear gap)
MAT_SINCE = '2026-11-06'  # production plant cells lie on blue mats from this day
N_MAT2 = 5
EMPTY_CURRENT_MAX = 50  # an empty pot: no rule H pixel and fewer than 50 current-rule pixels


def select2(out):
    rng = np.random.default_rng(SEED)
    picks = []
    for rig in ('prod', 'dev'):
        rows = []
        for f in sorted(glob.glob(f'{out}/work/{rig}_*_cells.json')):
            rows += json.load(open(f))['cells']
        days = sorted({r['day'] for r in rows})
        if rig == 'prod':
            plant = [r for r in rows if r['tray'] in PLANT_TRAYS['prod']]
        else:
            plant = [r for r in rows if r['blue_share'] <= MISSING_POT_BLUE]
        key = lambda r: (r['day'], r['tray'], r['cell'])  # noqa: E731
        chosen, taken = [], set()

        def take(r, stratum):
            chosen.append(dict(r, stratum=stratum))
            taken.add(key(r))

        def prefer(cands):
            have_days = {c['day'] for c in chosen}
            have_tc = {(c['tray'], c['cell']) for c in chosen}
            score = lambda r: (r['day'] in have_days, (r['tray'], r['cell']) in have_tc)  # noqa: E731
            best = min(score(r) for r in cands)
            group = [r for r in cands if score(r) == best]
            return group[rng.integers(len(group))]

        free = lambda pool: [r for r in pool if key(r) not in taken]  # noqa: E731
        mat_days = rig == 'prod'
        before = [r for r in plant if not (mat_days and r['day'] >= MAT_SINCE)]
        on_mat = [r for r in plant if mat_days and r['day'] >= MAT_SINCE]

        def bins(pool):
            sized = sorted([r for r in pool if r['ruleH_px'] > 0], key=lambda r: r['ruleH_px'])
            edges = [sized[int(len(sized) * k / N_SIZE_BINS)]['ruleH_px'] for k in range(N_SIZE_BINS)] + [math.inf]
            return edges, lambda r: next(k for k in range(N_SIZE_BINS) if edges[k] <= r['ruleH_px'] < edges[k + 1])

        # Not plant: one green paper square on a production tray 7 or 10, from MAT_SINCE on.
        if rig == 'prod':
            c = [r for r in rows if r['tray'] in (7, 10) and r['day'] >= MAT_SINCE and r['current_px'] > 1000]
            take(prefer(c), 'not plant: green paper')
        # Empty pots in plant trays.
        for _ in range(N_EMPTY):
            c = [r for r in free(plant) if r['ruleH_px'] == 0 and r['current_px'] < EMPTY_CURRENT_MAX]
            if c:
                take(prefer(c), 'empty')
        # Mats (production only): N_MAT2 cells from MAT_SINCE on, across sizes, every mat day once first.
        if on_mat:
            edges_m, bin_m = bins(on_mat)
            mat_days_left = sorted({r['day'] for r in on_mat})
            k = 0
            while sum(c['stratum'].startswith('blue mat') for c in chosen) < N_MAT2 and k < 100:
                c = [r for r in free(on_mat) if r['ruleH_px'] > 0 and bin_m(r) == k % N_SIZE_BINS]
                if c:
                    r = prefer(c)
                    take(r, f'blue mat, size {bin_m(r) + 1} of {N_SIZE_BINS}')
                k += 1
            print(rig, 'mat size bin edges', edges_m[:-1], 'mat days', mat_days_left)
        # Greenest soils: the plant trays with the highest soil peak, one photo each, a cell with plant.
        seen = set()
        for r in sorted(free(before), key=lambda r: -r['soil_peak']):
            if len(seen) >= N_GREEN:
                break
            if r['tray'] in seen:
                continue
            c = [q for q in free(before) if q['day'] == r['day'] and q['tray'] == r['tray'] and q['ruleH_px'] > 0]
            if c:
                seen.add(r['tray'])
                take(prefer(c), 'green soil')
        # Plant size over the rest.
        edges, bin_of = bins(before)
        k = 0
        while len(chosen) < N_PER_RIG and k < 1000:
            missing = set(days) - {c['day'] for c in chosen}
            c = [r for r in free(before) if r['ruleH_px'] > 0 and bin_of(r) == k % N_SIZE_BINS]
            if missing and len(chosen) >= N_PER_RIG - len(missing):
                c = [r for r in c if r['day'] in missing] or [r for r in free(plant) if r['day'] in missing and r['ruleH_px'] > 0]
            if c:
                r = prefer(c)
                take(r, f'size {bin_of(r) + 1} of {N_SIZE_BINS}')
            k += 1
        missing = set(days) - {c['day'] for c in chosen}
        chosen.sort(key=key)
        for i, r in enumerate(chosen):
            r['id'] = f'{LETTER[rig]}{i + 1:02d}'
            r['split'] = split_of(rig, r['day'], days)
            r['name'] = f"{rig}_{r['day']}_{r['tray']}_{r['cell']}"
        picks += chosen
        print(rig, len(plant), 'plant-tray cells;', len(chosen), 'picked; size bin edges', edges[:-1], 'days missing', sorted(missing))
    json.dump(dict(seed=SEED, blue_margin=BLUE_MARGIN, missing_pot_blue=MISSING_POT_BLUE, mat_since=MAT_SINCE,
                   method='metrology log 33 with its amendment of 2026-11-09', picks=picks),
              open(f'{out}/work/picks.json', 'w'), indent=1)


def boundary(mask, thick):
    m = mask.astype(np.uint8)
    return (m > 0) & (cv2.erode(m, np.ones((3, 3), np.uint8), iterations=thick, borderType=cv2.BORDER_CONSTANT, borderValue=0) == 0)


def crops(data, out, rig, cid):
    t0 = time.time()
    caps = load(data, rig)
    v = caps[cid]
    picks = [p for p in json.load(open(f'{out}/work/picks.json'))['picks'] if p['rig'] == rig and str(p['capture_id']) == cid]
    if not picks:
        return
    bgr = cv2.imread(f"{data}/{rig}/{v['file']}")
    Hm = cv2.imread(f"{out}/work/{rig}_{v['day']}_H.png", cv2.IMREAD_GRAYSCALE) > 0
    Hh, Ww = Hm.shape
    os.makedirs(f'{out}/cells', exist_ok=True)
    done = []
    for p in picks:
        c = np.asarray(p['corners'])
        x0, y0 = np.maximum(np.floor(c.min(0)).astype(int) - MARGIN, 0)
        x1, y1 = np.minimum(np.ceil(c.max(0)).astype(int) + 1 + MARGIN, [Ww, Hh])
        crop = np.ascontiguousarray(bgr[y0:y1, x0:x1])
        mask = np.ascontiguousarray(Hm[y0:y1, x0:x1])
        h, w = mask.shape
        stem = f"{out}/cells/{p['name']}"
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        Image.fromarray(rgb).save(stem + '.tif')  # uncompressed RGB TIFF
        assert np.array_equal(np.asarray(Image.open(stem + '.tif').convert('RGB')), rgb)
        mask_to_roi_zip(mask, stem + '_draft.roi.zip', p['name'])
        back = roi_zip_to_mask(stem + '_draft.roi.zip', w, h)
        ok = bool(np.array_equal(back, mask))
        cv2.imwrite(stem + '_draft.png', mask.astype(np.uint8) * 255)
        big = cv2.resize(crop, (2 * w, 2 * h), interpolation=cv2.INTER_NEAREST)
        m2 = cv2.resize(mask.astype(np.uint8), (2 * w, 2 * h), interpolation=cv2.INTER_NEAREST) > 0
        big[boundary(m2, 2)] = MAGENTA
        cv2.polylines(big, [np.round((c - [x0, y0]) * 2).astype(np.int32).reshape(-1, 1, 2)], True, RED, 3)
        cv2.imwrite(stem + '_preview.png', big)
        done.append(dict(name=p['name'], crop=[int(x0), int(y0), int(w), int(h)], roi_round_trip=ok,
                         draft_px=int(mask.sum())))
    # Overview: the photo at about 2000 px wide, every measured cell of the photo thin magenta,
    # the picks thick red with their id.
    s = 2000 / bgr.shape[1]
    ov = cv2.resize(bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    del bgr
    allc = json.load(open(f"{out}/work/{rig}_{v['day']}_cells.json"))['cells']
    for q in allc:
        cv2.polylines(ov, [np.round(np.asarray(q['corners']) * s).astype(np.int32).reshape(-1, 1, 2)], True, MAGENTA, 1)
    for p in picks:
        pts = np.round(np.asarray(p['corners']) * s).astype(np.int32)
        cv2.polylines(ov, [pts.reshape(-1, 1, 2)], True, RED, 3)
        x, y = pts[:, 0].min(), pts[:, 1].min() - 6
        cv2.putText(ov, p['id'], (int(x), int(max(y, 20))), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 5)
        cv2.putText(ov, p['id'], (int(x), int(max(y, 20))), cv2.FONT_HERSHEY_SIMPLEX, 0.9, RED, 2)
    cv2.putText(ov, f"{rig} {v['day']} capture {cid}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 6)
    cv2.putText(ov, f"{rig} {v['day']} capture {cid}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 2)
    os.makedirs(f'{out}/sheets', exist_ok=True)
    cv2.imwrite(f"{out}/sheets/overview_{rig}_{v['day']}.png", ov)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    json.dump(done, open(f"{out}/work/{rig}_{v['day']}_crops.json", 'w'))
    print(json.dumps(dict(rig=rig, day=v['day'], n=len(done), seconds=round(time.time() - t0, 1), peak_mb=round(peak),
                          round_trip_all=all(d['roi_round_trip'] for d in done))))


def sheets(out):
    import csv
    picks = json.load(open(f'{out}/work/picks.json'))['picks']
    crops_ = {}
    for f in glob.glob(f'{out}/work/*_crops.json'):
        for d in json.load(open(f)):
            crops_[d['name']] = d
    cols, tile, gap, lab = 4, 470, 24, 90
    for rig in ('prod', 'dev'):
        ps = [p for p in picks if p['rig'] == rig]
        for page in range(math.ceil(len(ps) / 12)):
            part = ps[page * 12:(page + 1) * 12]
            rows_n = math.ceil(len(part) / cols)
            W = cols * tile + (cols + 1) * gap
            sheet = np.full((rows_n * (tile + lab + gap) + gap, W, 3), 255, np.uint8)
            for i, p in enumerate(part):
                im = cv2.imread(f"{out}/cells/{p['name']}_preview.png")
                f = tile / max(im.shape[:2])
                im = cv2.resize(im, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
                x = gap + (i % cols) * (tile + gap)
                y = gap + (i // cols) * (tile + lab + gap)
                cv2.putText(sheet, p['id'], (x, y + 52), cv2.FONT_HERSHEY_SIMPLEX, 1.9, (0, 0, 0), 4)
                cv2.putText(sheet, f"{p['day'][5:]} tray {p['tray']} {p['cell']}", (x + 150, y + 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (60, 60, 60), 2)
                cv2.putText(sheet, p['stratum'], (x + 150, y + 62), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (60, 60, 60), 2)
                sheet[y + lab:y + lab + im.shape[0], x:x + im.shape[1]] = im
            cv2.imwrite(f'{out}/sheets/sheet_{LETTER[rig]}{page + 1}_{rig}.png', sheet)
    fields = ['id', 'file', 'rig', 'day', 'split', 'capture_id', 'taken_at', 'jpeg_quality', 'tray', 'cell',
              'crop_x0', 'crop_y0', 'crop_w', 'crop_h', 'mm2_per_px', 'ruleH_px', 'current_px', 'soil_peak',
              'blue_share', 'stratum', 'cells_from', 'cut_h', 'draft_px_in_crop', 'roi_round_trip']
    with open(f'{out}/manifest.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for p in picks:
            d = crops_[p['name']]
            q = p['jpeg_quality'] if p['jpeg_quality'] is not None else '75 (NULL in rig.db, before schema 20)'
            w.writerow(dict(id=p['id'], file=p['name'] + '.tif', rig=p['rig'], day=p['day'], split=p['split'],
                            capture_id=p['capture_id'], taken_at=p['taken_at'], jpeg_quality=q, tray=p['tray'],
                            cell=p['cell'], crop_x0=d['crop'][0], crop_y0=d['crop'][1], crop_w=d['crop'][2],
                            crop_h=d['crop'][3], mm2_per_px=f"{p['mm2_per_px']:.6f}", ruleH_px=p['ruleH_px'],
                            current_px=p['current_px'], soil_peak=f"{p['soil_peak']:+.3f}",
                            blue_share=f"{p['blue_share']:.4f}", stratum=p['stratum'], cells_from=p['cells_from'],
                            cut_h=p['cut_h'], draft_px_in_crop=d['draft_px'], roi_round_trip=d['roi_round_trip']))
    print('manifest', len(picks), 'rows; all round trips exact:', all(c['roi_round_trip'] for c in crops_.values()))


if __name__ == '__main__':
    cmd, *a = sys.argv[1:]
    dict(measure=measure, select=select, select2=select2, crops=crops, sheets=sheets)[cmd](*a)
