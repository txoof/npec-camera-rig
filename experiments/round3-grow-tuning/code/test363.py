"""#363, metrology log 34, phase 2 ("Test, once"): the present and the chosen setting of grow from
leaf cores (34.1: core 0.07 alone), and the fixed green cutoff for comparison, on
  cells RUN       the 19 test cells of the reference set (RUN/ref-test: test rows, truth, drafts)
  outlines RUN    the 15 outlines of log 24 (RUN/p2-outlines: still 19380, its readings from
                  production rig.db read only, the crops, manifest and pass 1 / pass 2 ROI zips)
Per photo: each tray box cut as drafts402.measure does, the method run per tray on the full photo,
the masks composed over the photo and cut to each crop. The fixed green cutoff is greenness above 0.1
and G > R inside the tray outline (ruleg402 'current', as composed for the drafts), no tag or blue
handling. Scores are over the whole crop. No setting is chosen or changed here."""
import csv
import glob
import json
import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grow363 import PRESENT, grow_p, overlaps, read_rgb, tray_box  # noqa: E402
from mask_rois import fill, read_roi_zip  # noqa: E402
from ruleg402 import tag_mask  # noqa: E402
from npec_rig.tags import TagDetection  # noqa: E402

CHOSEN = dict(PRESENT, core=0.07)
METHODS = ('present', 'chosen', 'fixed')


def fixed_cut(rgb, ins):
    r, g, b = (rgb[..., i].astype(np.float32) for i in range(3))
    exg = (2 * g - r - b) / (r + g + b + 1e-6)
    return (exg > 0.1) & (g > r) & ins


def compose(img, v, crops):
    """Masks of the three methods for each crop {key: (x0, y0, w, h)}, from every placed tray whose
    box overlaps a crop. Also the trays used per crop."""
    tags = {}
    for t in v['tags']:
        tags.setdefault(t['tag_id'], []).append(t)
    out = {k: {m: np.zeros((c[3], c[2]), bool) for m in METHODS} for k, c in crops.items()}
    used = {k: [] for k in crops}
    for r in v['readings']:
        if r['tray_id'] is None or r['placement'] != 'placed' or r['outline'] is None:
            continue
        tid = r['tray_id']
        sub, ins, (tx, ty) = tray_box(img, r['outline'])
        th, tw = ins.shape
        hit = [k for k, c in crops.items() if overlaps((tx, ty, tw, th), c)]
        if not hit:
            continue
        own = [TagDetection(tid, tuple((c[0] - tx, c[1] - ty) for c in t['corners']),
                            (t['centre'][0] - tx, t['centre'][1] - ty)) for t in tags.get(tid, [])]
        tag, _ = tag_mask(sub, tid, own)
        ms = dict(present=grow_p(sub, ins, tag, PRESENT)[0], chosen=grow_p(sub, ins, tag, CHOSEN)[0],
                  fixed=fixed_cut(sub, ins))
        for k in hit:
            x0, y0, w, h = crops[k]
            ax0, ay0, ax1, ay1 = max(x0, tx), max(y0, ty), min(x0 + w, tx + tw), min(y0 + h, ty + th)
            used[k].append(tid)
            for m in METHODS:
                out[k][m][ay0 - y0:ay1 - y0, ax0 - x0:ax1 - x0] |= ms[m][ay0 - ty:ay1 - ty, ax0 - tx:ax1 - tx]
    return out, used


def sc(m, t):
    i, u = int((m & t).sum()), int((m | t).sum())
    return dict(inter=i, union=u, method_px=int(m.sum()), truth_px=int(t.sum()), crop_px=int(t.size),
                iou=round(i / u, 4) if u else 1.0, ratio=round(m.sum() / t.sum(), 4) if t.sum() else None)


def cells(run):
    ref = f'{run}/ref-test'
    rows = [r for r in csv.DictReader(open(f'{ref}/manifest_test.csv'))]
    assert all(r['split'] == 'test' for r in rows) and len(rows) == 18  # manifest: 13 prod + 5 dev (log 33 text says 6 dev)
    src = {r['id']: r['truth_source'] for r in csv.DictReader(open(f'{ref}/truth_index_test.csv'))}
    out = []
    for rig, cid in sorted({(r['rig'], r['capture_id']) for r in rows}):
        t0 = time.time()
        v = json.load(open(f'{run}/data/{rig}/readings.json'))['captures'][cid]
        img = read_rgb(f"{run}/data/{rig}/{v['file']}")
        mine = [r for r in rows if r['rig'] == rig and r['capture_id'] == cid]
        crops = {r['id']: tuple(int(r[k]) for k in ('crop_x0', 'crop_y0', 'crop_w', 'crop_h')) for r in mine}
        masks, used = compose(img, v, crops)
        del img
        for r in mine:
            name = r['file'][:-4]
            truth = cv2.imread(f'{ref}/truth/{name}_truth.png', cv2.IMREAD_GRAYSCALE) > 0
            draft = cv2.imread(f'{ref}/drafts/{name}_draft.png', cv2.IMREAD_GRAYSCALE) > 0
            base = dict(id=r['id'], rig=rig, day=r['day'], tray=r['tray'], cell=r['cell'], stratum=r['stratum'],
                        truth_source=src[r['id']], trays_used=' '.join(map(str, used[r['id']])),
                        present_equals_draft=bool(np.array_equal(masks[r['id']]['present'], draft)))
            for m in METHODS:
                out.append(dict(base, method=m, **sc(masks[r['id']][m], truth)))
        print(json.dumps(dict(rig=rig, cid=cid, cells=len(mine), s=round(time.time() - t0, 1))), flush=True)
    os.makedirs(f'{run}/out-test', exist_ok=True)
    with open(f'{run}/out-test/test_cells.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)


def load_pass(zf, resf, drop_row=None):
    """ROIs in zip order matched to the Results rows in order (as log 24's check_prod_crops_h:
    pass 1 has 17 rows and 16 ROIs, row 16 dropped)."""
    rois = read_roi_zip(zf)
    res = list(csv.DictReader(open(resf)))
    if drop_row is not None:
        res = res[:drop_row] + res[drop_row + 1:]
    assert len(res) == len(rois), (len(res), len(rois))
    return [(r['Label'].split(':')[0], int(r['Area']), kind, outlines) for r, (_, kind, _, outlines) in zip(res, rois)]


def outlines(run):
    d = f'{run}/p2-outlines'
    cap = json.load(open(f'{d}/db19380.json'))
    v = dict(tags=cap['tags'], readings=cap['readings'])
    man = {r['file']: r for r in csv.DictReader(open(f'{d}/imagej/manifest.csv'))}
    stem = '2026-11-03_105853_597207'
    files = [f'{stem}_t{t}_p{p}.tif'.replace('_t6_p1.tif', '_t6_p1b.tif') for t in (1, 3, 6) for p in range(1, 6)]
    img = read_rgb(f'{d}/{stem}.jpg')
    align = {}
    for f in files:
        x0, y0, w, h = (int(man[f][k]) for k in ('x0', 'y0', 'width', 'height'))
        crop = cv2.cvtColor(cv2.imread(f'{d}/imagej/{f}', cv2.IMREAD_UNCHANGED), cv2.COLOR_BGR2RGB)
        align[f] = bool(crop.shape[:2] == (h, w) and np.array_equal(crop, img[y0:y0 + h, x0:x0 + w]))
    crops = {f: tuple(int(man[f][k]) for k in ('x0', 'y0', 'width', 'height')) for f in files}
    masks, used = compose(img, v, crops)
    del img
    P = {1: load_pass(glob.glob(f'{d}/imagej/pass_1_*Results.roi.zip')[0], glob.glob(f'{d}/imagej/pass_1_*Results.csv')[0], 15),
         2: load_pass(glob.glob(f'{d}/imagej/pass_2_*Results.roi.zip')[0], glob.glob(f'{d}/imagej/pass_2_*Results.csv')[0])}
    out = []
    for f in files:
        x0, y0, w, h = crops[f]
        pm = {}
        for p in (1, 2):
            hits = [x for x in P[p] if x[0] == f]
            assert len(hits) == 1, (p, f, len(hits))
            lab, area, kind, ol = hits[0]
            pm[p] = (fill(ol, w, h), area, kind)
        rep = sc(pm[2][0], pm[1][0])
        for m in METHODS:
            for p in (1, 2):
                out.append(dict(file=f, tray=man[f]['tray'], plant=man[f]['plant'], aligned=align[f],
                                trays_used=' '.join(map(str, used[f])), method=m, vs_pass=p, roi_kind=pm[p][2],
                                imagej_area=pm[p][1], **sc(masks[f][m], pm[p][0]),
                                person_repeat_iou=rep['iou'], pass2_over_pass1=rep['ratio']))
    os.makedirs(f'{run}/out-test', exist_ok=True)
    with open(f'{run}/out-test/outlines.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(json.dumps(dict(crops=len(files), all_aligned=all(align.values()))))


if __name__ == '__main__':
    cmd, *a = sys.argv[1:]
    dict(cells=cells, outlines=outlines)[cmd](*a)
