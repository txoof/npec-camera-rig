"""#363, metrology log 34, phase 1: tune grow from leaf cores on the TRAINING cells of the reference
set of log 33 (experiments/round3-classifier/data/). Run on the development rig.

  cache RUN RIG CID      the photo decoded once; every tray box that overlaps a training crop is cut
                         as drafts402.measure cuts it (same outline, same own-tag handling) and saved
                         with its outline and tag masks to RUN/cache/; the harness check is done here:
                         ruleg402.rules (the code the drafts were made with) composed over the full
                         photo must equal each training draft PNG, and this file's grow_p at the
                         present settings must equal ruleg402 on every cached tray
  sweep RUN GRID [N]     every setting of RUN/GRID (json list of settings) on every cached tray,
                         scored per training cell against its truth; N worker processes (at most 3)
  timeit RUN RIG CID S   seconds for one full photo, all trays, with setting S (json) and the present one

RUN/ref holds only the training rows of the manifest and their truth and draft PNGs: test cells
cannot be scored by this script. Scores are over the whole crop (cell plus 40 px), as the truth
covers it ("every leaf in a crop counts")."""
import csv
import glob
import json
import os
import sys
import time
from multiprocessing import Pool

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ruleg402 import rules, soil_peak, tag_mask  # noqa: E402
from npec_rig.tags import TagDetection  # noqa: E402

PRESENT = dict(core=0.1, gr=True, gap=0.07, floor=-0.045, blue=0, edge=0, fill=False, sigma=0.0)
ALLOWED = 3


def read_rgb(path):
    bgr = cv2.imread(path)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    del bgr
    return rgb


def tray_box(img, outline):
    """As drafts402.tray_box."""
    H, W = img.shape[:2]
    o = np.asarray(outline, float)
    x0, y0 = np.maximum(np.floor(o.min(0)).astype(int), 0)
    x1, y1 = np.minimum(np.ceil(o.max(0)).astype(int) + 1, [W, H])
    ins = np.zeros((y1 - y0, x1 - x0), np.uint8)
    cv2.fillPoly(ins, [np.round(o - [x0, y0]).astype(np.int32).reshape(-1, 1, 2)], 1)
    return np.ascontiguousarray(img[y0:y1, x0:x1]), ins > 0, (int(x0), int(y0))


def grow_p(rgb, ins, tag, s):
    """Grow from leaf cores with settings s on one tray box. tag: the tag mask of ruleg402.tag_mask
    (from the raw colour). Present settings reproduce ruleg402.rules(...)['H']."""
    if s['sigma'] > 0:
        f = cv2.GaussianBlur(rgb.astype(np.float32), (0, 0), s['sigma'])
        r, g, b = f[..., 0], f[..., 1], f[..., 2]
    else:
        r, g, b = (rgb[..., i].astype(np.float32) for i in range(3))
    exg = (2 * g - r - b) / (r + g + b + 1e-6)
    m = s['blue']
    notblue = ~((b > r + m) & (b > g + m))
    sel = ins & ~tag
    peak = soil_peak(exg, sel & notblue)
    low_cut = max(s['floor'], peak + s['gap'])
    core = (exg > s['core']) & sel
    if s['gr']:
        core &= g > r
    above = (exg > low_cut) & sel
    low = (above & notblue).astype(np.uint8)
    n, lab = cv2.connectedComponents(low, connectivity=8, ltype=cv2.CV_32S)
    keep = np.zeros(n, bool)
    keep[np.unique(lab[core])] = True
    keep[0] = False
    mask = keep[lab]
    if s['edge']:
        mask |= (cv2.dilate(mask.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=s['edge']) > 0) & above
    if s['fill']:
        # a 1 px gap (narrower than 2 px) between plant pixels on opposite sides is plant
        p = np.pad(mask, 1)
        c = p[1:-1, 1:-1]
        gap = ((p[1:-1, :-2] & p[1:-1, 2:]) | (p[:-2, 1:-1] & p[2:, 1:-1]) |
               (p[:-2, :-2] & p[2:, 2:]) | (p[:-2, 2:] & p[2:, :-2]))
        mask = c | (gap & sel)
    return mask, peak, low_cut


def train_rows(run):
    return [r for r in csv.DictReader(open(f'{run}/ref/manifest_train.csv')) if r['split'] == 'train']


def overlaps(box, crop):
    (x0, y0, w, h), (cx, cy, cw, ch) = box, crop
    return x0 < cx + cw and cx < x0 + w and y0 < cy + ch and cy < y0 + h


def cache(run, rig, cid):
    t0 = time.time()
    caps = json.load(open(f'{run}/data/{rig}/readings.json'))['captures']
    v = caps[cid]
    cells = [r for r in train_rows(run) if r['rig'] == rig and r['capture_id'] == cid]
    if not cells:
        return
    img = read_rgb(f"{run}/data/{rig}/{v['file']}")
    H, W = img.shape[:2]
    tags = {}
    for t in v['tags']:
        tags.setdefault(t['tag_id'], []).append(t)
    Hm = np.zeros((H, W), bool)
    os.makedirs(f'{run}/cache', exist_ok=True)
    kept, same_p = [], []
    for r in v['readings']:
        if r['tray_id'] is None or r['placement'] != 'placed' or r['outline'] is None:
            continue
        tid = r['tray_id']
        sub, ins, (x0, y0) = tray_box(img, r['outline'])
        own = [TagDetection(tid, tuple((c[0] - x0, c[1] - y0) for c in t['corners']),
                            (t['centre'][0] - x0, t['centre'][1] - y0)) for t in tags.get(tid, [])]
        m = rules(sub, ins, tid, tags=own)
        h, w = ins.shape
        Hm[y0:y0 + h, x0:x0 + w] |= m['H']
        box = (x0, y0, w, h)
        if any(overlaps(box, tuple(int(c[k]) for k in ('crop_x0', 'crop_y0', 'crop_w', 'crop_h'))) for c in cells):
            tag, _ = tag_mask(sub, tid, own)
            mp, _, _ = grow_p(sub, ins, tag, PRESENT)
            same_p.append(dict(tray=tid, same=bool(np.array_equal(mp, m['H']))))
            np.savez(f'{run}/cache/{rig}_{cid}_t{tid}.npz', rgb=sub, ins=ins, tag=tag, origin=np.array([x0, y0]))
            kept.append(dict(tray=tid, box=box))
        del sub, ins, m
    checks = []
    for c in cells:
        x0, y0, w, h = (int(c[k]) for k in ('crop_x0', 'crop_y0', 'crop_w', 'crop_h'))
        mine = Hm[y0:y0 + h, x0:x0 + w]
        name = c['file'][:-4]
        draft = cv2.imread(f'{run}/ref/drafts/{name}_draft.png', cv2.IMREAD_GRAYSCALE) > 0
        diff = int((mine != draft).sum()) if mine.shape == draft.shape else -1
        checks.append(dict(id=c['id'], name=name, same=diff == 0, diff_px=diff, draft_px=int(draft.sum()),
                           trays=[k['tray'] for k in kept if overlaps(k['box'], (x0, y0, w, h))]))
    info = dict(rig=rig, capture_id=cid, seconds=round(time.time() - t0, 1), trays_cached=[k['tray'] for k in kept],
                grow_p_equals_ruleg402=same_p, cells=checks)
    json.dump(info, open(f'{run}/cache/{rig}_{cid}_check.json', 'w'), indent=1)
    print(json.dumps(dict(rig=rig, cid=cid, s=info['seconds'], all_same=all(k['same'] for k in checks),
                          grow_p_same=all(k['same'] for k in same_p))))


def _score_photo(args):
    run, rig, cid, grid = args
    cells = [r for r in train_rows(run) if r['rig'] == rig and r['capture_id'] == cid]
    trays = []
    for f in sorted(glob.glob(f'{run}/cache/{rig}_{cid}_t*.npz')):
        z = np.load(f)
        trays.append((z['rgb'], z['ins'], z['tag'], tuple(z['origin'])))
    truths = []
    for c in cells:
        x0, y0, w, h = (int(c[k]) for k in ('crop_x0', 'crop_y0', 'crop_w', 'crop_h'))
        t = cv2.imread(f"{run}/ref/truth/{c['file'][:-4]}_truth.png", cv2.IMREAD_GRAYSCALE) > 0
        truths.append((c['id'], (x0, y0, w, h), t))
    out = []
    for si, s in enumerate(grid):
        crops = {cid_: np.zeros(t.shape, bool) for cid_, _, t in truths}
        for rgb, ins, tag, (tx, ty) in trays:
            m, peak, cut = grow_p(rgb, ins, tag, s)
            th, tw = m.shape
            for cid_, (x0, y0, w, h), _ in truths:
                ax0, ay0, ax1, ay1 = max(x0, tx), max(y0, ty), min(x0 + w, tx + tw), min(y0 + h, ty + th)
                if ax0 < ax1 and ay0 < ay1:
                    crops[cid_][ay0 - y0:ay1 - y0, ax0 - x0:ax1 - x0] |= m[ay0 - ty:ay1 - ty, ax0 - tx:ax1 - tx]
        for cid_, _, t in truths:
            m = crops[cid_]
            out.append(dict(setting=si, id=cid_, inter=int((m & t).sum()), union=int((m | t).sum()),
                            method_px=int(m.sum()), truth_px=int(t.sum())))
    return out


def sweep(run, grid_file, n=3):
    n = min(int(n), ALLOWED)
    grid = json.load(open(grid_file))
    rows = train_rows(run)
    photos = sorted({(r['rig'], r['capture_id']) for r in rows})
    t0 = time.time()
    with Pool(n) as p:
        res = p.map(_score_photo, [(run, rig, cid, grid) for rig, cid in photos], chunksize=1)
    out = [x for r in res for x in r]
    stem = os.path.splitext(grid_file)[0]
    with open(stem + '_scores.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(json.dumps(dict(settings=len(grid), rows=len(out), seconds=round(time.time() - t0, 1))))


def timeit(run, rig, cid, s_json):
    caps = json.load(open(f'{run}/data/{rig}/readings.json'))['captures']
    v = caps[cid]
    res = {}
    for label, s in (('present', PRESENT), ('chosen', dict(PRESENT, **json.loads(s_json)))):
        for rep in range(3):
            t0 = time.time()
            img = read_rgb(f"{run}/data/{rig}/{v['file']}")
            t1 = time.time()
            tags = {}
            for t in v['tags']:
                tags.setdefault(t['tag_id'], []).append(t)
            n = 0
            for r in v['readings']:
                if r['tray_id'] is None or r['placement'] != 'placed' or r['outline'] is None:
                    continue
                tid = r['tray_id']
                sub, ins, (x0, y0) = tray_box(img, r['outline'])
                own = [TagDetection(tid, tuple((c[0] - x0, c[1] - y0) for c in t['corners']),
                                    (t['centre'][0] - x0, t['centre'][1] - y0)) for t in tags.get(tid, [])]
                tag, _ = tag_mask(sub, tid, own)
                grow_p(sub, ins, tag, s)
                n += 1
            t2 = time.time()
            del img
            res.setdefault(label, []).append(dict(decode_s=round(t1 - t0, 2), trays_s=round(t2 - t1, 2), trays=n))
    print(json.dumps(res))


if __name__ == '__main__':
    cmd, *a = sys.argv[1:]
    dict(cache=cache, sweep=sweep, timeit=timeit)[cmd](*a)
