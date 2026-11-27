"""#406, log 44 step 1: score the three label sources on the staged TRAINING cells, as logs 33 and 34.
  score_sources.py LABELS OUTDIR
Scores with group() and stats() of ../../round3-grow-tuning/code/score363.py (imported). Per cell, over
the whole crop: intersection, union, source px, truth px; IoU = inter / union (1 if both empty); area ratio
= source / truth (left out where the truth is empty). Writes to OUTDIR: per_cell.csv, summary.csv,
groups.csv, times.csv, disagree.csv, sheet_disagree.png (8 cells where the best settings of the three
sources disagree most: lowest mean IoU between each pair of source masks, cells with plant only) and
sheet_mats_yellow.png (A30, A25 on blue mats, B21, B24 with yellow leaves). Sheets: translucent fills,
green in both, magenta source only, yellow truth only; zoomed inset where the truth is under 2% of the crop.

Yellow, a rough rule for pointing at cells: pixels a source marks and the truth does not, whose HSV hue
is 16 to 38 degrees (OpenCV 8 to 19) with saturation at least 120 and value at least 60 of 255. Set after
a first rule (24 to 60 degrees) took in most of the truth's green: on the training truths the hue's 5th
percentile is OpenCV 19 and its median 39; the yellow leaves SAM 3 adds on B21 and B24 have median 16 to 18."""
import csv
import itertools
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'round3-grow-tuning', 'code'))
from score363 import group, stats  # noqa: E402

TUNE = os.path.join(HERE, '..', '..', 'round3-grow-tuning', 'data')
PROMPTS = ['plant', 'leaf', 'potato_plant']
THRS = [0.3, 0.4, 0.5]
SAM2V = ['p1m', 'p1s', 'p5s']


def settings():
    s = [('grow', 'grow core 0.07')]
    s += [('sam3', f'sam3 {p} {t}') for p in PROMPTS for t in THRS]
    s += [('sam2', f'sam2 {v}') for v in SAM2V]
    return s


def masks_for(labels, name, hw):
    out = {'grow core 0.07': cv2.imread(f'{labels}/grow/{name}_grow.png', 0) > 0}
    z = np.load(f'{labels}/sam3/{name}.npz')
    for p in PROMPTS:
        sc = z[p + '_scores']
        m = np.unpackbits(z[p + '_masks'], axis=-1, count=hw[1]).astype(bool) if len(sc) else np.zeros((0, *hw), bool)
        for t in THRS:
            k = sc > t
            out[f'sam3 {p} {t}'] = m[k].any(axis=0) if k.any() else np.zeros(hw, bool)
    for v in SAM2V:
        out[f'sam2 {v}'] = cv2.imread(f'{labels}/sam2/{name}_{v}.png', 0) > 0
    return out


def yellow_of(rgb):
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    return (h >= 8) & (h <= 19) & (s >= 120) & (v >= 60)


def write(path, rows):
    with open(path, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


BOTH, EXTRA, MISSED, TRUTH = (0, 200, 0), (255, 0, 255), (255, 230, 0), (0, 220, 255)
ALPHA = 0.55
PH = 340          # panel image height, px
HEAD = 40         # two header lines


def fill(rgb, layers):
    out = rgb.astype(np.float32)
    for mask, col in layers:
        out[mask] = (1 - ALPHA) * out[mask] + ALPHA * np.array(col, np.float32)
    return out.clip(0, 255).astype(np.uint8)


def panel(rgb, truth, m, line1, line2):
    """Translucent fills, no outlines. m None: the truth alone (cyan). Otherwise green = in both, magenta =
    source only (extra), yellow = truth only (missed). When the truth covers under 2% of the crop, a
    zoomed inset of the area around the truth sits in the lower right corner."""
    if m is None:
        ov = fill(rgb, [(truth, TRUTH)])
    else:
        ov = fill(rgb, [(m & truth, BOTH), (m & ~truth, EXTRA), (truth & ~m, MISSED)])
    H, W = truth.shape
    sc = PH / H
    img = cv2.resize(ov, (round(W * sc), PH), interpolation=cv2.INTER_AREA)
    if truth.any() and truth.mean() < 0.02:
        ys, xs = np.nonzero(truth)
        cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
        half = max(xs.max() - xs.min(), ys.max() - ys.min()) * 0.75 + 10
        x0, x1 = int(max(cx - half, 0)), int(min(cx + half, W))
        y0, y1 = int(max(cy - half, 0)), int(min(cy + half, H))
        side = int(img.shape[1] * 0.45)
        zoom = side / max(x1 - x0, y1 - y0)
        ins = cv2.resize(ov[y0:y1, x0:x1], (round((x1 - x0) * zoom), round((y1 - y0) * zoom)),
                         interpolation=cv2.INTER_NEAREST)
        cv2.rectangle(img, (round(x0 * sc), round(y0 * sc)), (round(x1 * sc), round(y1 * sc)), (255, 255, 255), 1)
        ih, iw = ins.shape[:2]
        Y, X = img.shape[0] - ih - 4, img.shape[1] - iw - 4
        cv2.rectangle(img, (X - 2, Y - 2), (X + iw + 1, Y + ih + 1), (255, 255, 255), 2)
        img[Y:Y + ih, X:X + iw] = ins
        cv2.putText(img, f'{zoom / sc:.1f}x', (X + 3, Y + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1,
                    cv2.LINE_AA)
    head = np.zeros((HEAD, img.shape[1], 3), np.uint8)
    for i, t in enumerate((line1, line2)):
        cv2.putText(head, t, (4, 15 + 19 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.43, (255, 255, 255), 1, cv2.LINE_AA)
    return np.vstack([head, img])


def words(m, truth):
    t = int(truth.sum())
    if not m.any():
        return 'IoU 0.00 | found nothing' if t else 'IoU 1.00 | nothing, as truth'
    iou = (m & truth).sum() / (m | truth).sum()
    if not t:
        return f'IoU 0.00 | marked {int(m.sum())} px, truth empty'
    ex, mi = (m & ~truth).sum() / t, (truth & ~m).sum() / t
    return f'IoU {iou:.2f} | extra {100 * ex:.0f}% of truth | missed {100 * mi:.0f}%'


def legend(w):
    out = np.zeros((34, w, 3), np.uint8)
    x = 6
    for col, txt in ((TRUTH, 'truth (column 1)'), (BOTH, 'both'), (EXTRA, 'extra (not plant)'),
                     (MISSED, 'missed (plant)')):
        cv2.rectangle(out, (x, 8), (x + 22, 26), col, -1)
        cv2.putText(out, txt, (x + 30, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        x += 40 + cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0] + 20
    return out


def write_sheet(path, ids, keys, cache):
    rows = []
    for cid in ids:
        name, rgb, truth, ms = cache[cid]
        row = [panel(rgb, truth, None, f'{cid} {name}', f'truth {int(truth.sum())} px')]
        row += [panel(rgb, truth, ms[k], k, words(ms[k], truth)) for k in keys]
        rows.append(np.hstack([np.pad(p, ((0, 0), (0, 4), (0, 0))) for p in row]))
    w = max(x.shape[1] for x in rows)
    sheet = np.vstack([legend(w)] + [np.pad(x, ((0, 4), (0, w - x.shape[1]), (0, 0))) for x in rows])
    cv2.imwrite(path, cv2.cvtColor(sheet, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_PNG_COMPRESSION, 9])


def main(labels, outdir):
    os.makedirs(outdir, exist_ok=True)
    ref = f'{labels}/ref'
    rows = list(csv.DictReader(open(f'{ref}/manifest_train.csv')))
    assert all(r['split'] == 'train' for r in rows)
    src = {r['id']: r['truth_source'] for r in csv.DictReader(open(f'{ref}/truth_index_train.csv'))}
    stored = {r['id']: r for r in csv.DictReader(open(f'{TUNE}/oat_scores.csv')) if r['setting'] == '2'}
    S = settings()
    per, cache = [], {}
    for r in rows:
        name = r['file'][:-4]
        rgb = cv2.cvtColor(cv2.imread(f'{ref}/crops/{name}.png'), cv2.COLOR_BGR2RGB)
        truth = cv2.imread(f'{ref}/truth/{name}_truth.png', 0) > 0
        ms = masks_for(labels, name, truth.shape)
        yel = yellow_of(rgb)
        cache[r['id']] = (name, rgb, truth, ms)
        for source, key in S:
            m = ms[key]
            row = dict(setting=key, source=source, id=r['id'], rig=r['rig'], group=group(r['stratum']),
                       src='corrected' if src[r['id']].startswith('corrected') else 'accepted',
                       inter=int((m & truth).sum()), union=int((m | truth).sum()), method_px=int(m.sum()),
                       truth_px=int(truth.sum()), yellow_extra_px=int((m & ~truth & yel).sum()),
                       truth_yellow_px=int((truth & yel).sum()))
            if source == 'grow':   # the reused counts of log 34.1, setting 2
                assert all(row[k] == int(stored[r['id']][k]) for k in ('inter', 'union', 'method_px', 'truth_px'))
            per.append(row)
    write(f'{outdir}/per_cell.csv', per)

    summ, groups = [], []
    for source, key in S:
        rs = [x for x in per if x['setting'] == key]
        row = dict(setting=key)
        for nm, sub in (('all', rs), ('corr', [x for x in rs if x['src'] == 'corrected']),
                        ('acc', [x for x in rs if x['src'] == 'accepted']),
                        ('prod_corr', [x for x in rs if x['rig'] == 'prod' and x['src'] == 'corrected']),
                        ('dev_corr', [x for x in rs if x['rig'] == 'dev' and x['src'] == 'corrected']),
                        ('prod', [x for x in rs if x['rig'] == 'prod']), ('dev', [x for x in rs if x['rig'] == 'dev'])):
            st = stats(sub)
            ious = [x['inter'] / x['union'] if x['union'] else 1.0 for x in sub]
            row.update({f'{nm}_n': st['n'], f'{nm}_iou': st.get('mean_iou'), f'{nm}_iou_min': round(min(ious), 3),
                        f'{nm}_pooled': st.get('pooled_ratio'), f'{nm}_median': st.get('median_ratio')})
        row['yellow_extra_px'] = sum(x['yellow_extra_px'] for x in rs)
        summ.append(row)
        for rig in ('prod', 'dev', 'both'):
            for g in sorted({x['group'] for x in rs}):
                for sn in ('all', 'corrected', 'accepted'):
                    sub = [x for x in rs if (rig == 'both' or x['rig'] == rig) and x['group'] == g
                           and (sn == 'all' or x['src'] == sn)]
                    if sub:
                        groups.append(dict(setting=key, rig=rig, group=g, truth=sn, **stats(sub)))
    write(f'{outdir}/summary.csv', summ)
    write(f'{outdir}/groups.csv', groups)

    # times per crop
    t = []
    for f, cols in ((f'{labels}/sam3/times.csv', ['encoder_s', 'plant_s', 'leaf_s', 'potato_plant_s']),
                    (f'{labels}/sam2/times.csv', ['encoder_s', 'p1m_s', 'p1s_s', 'p5s_s'])):
        rr = list(csv.DictReader(open(f)))
        for c in cols:
            v = np.array([float(x[c]) for x in rr])
            t.append(dict(file=os.path.basename(os.path.dirname(f)), step=c, median_s=round(float(np.median(v)), 4),
                          min_s=round(float(v.min()), 4), max_s=round(float(v.max()), 4), n=len(v)))
    gc = list(csv.DictReader(open(f'{labels}/grow/check.csv')))
    v = np.array([float(x['crop_s']) for x in gc])
    t.append(dict(file='grow (crop rebuild, CPU, not the method)', step='crop_s', median_s=round(float(np.median(v)), 4),
                  min_s=round(float(v.min()), 4), max_s=round(float(v.max()), 4), n=len(v)))
    write(f'{outdir}/times.csv', t)

    # best setting per source on corrected cells, then disagreement
    best = {}
    for source, key in S:
        r = next(x for x in summ if x['setting'] == key)
        if source not in best or r['corr_iou'] > best[source][1]:
            best[source] = (key, r['corr_iou'])
    keys = [best[s][0] for s in ('grow', 'sam3', 'sam2')]
    dis = []
    for cid, (name, rgb, truth, ms) in cache.items():
        if not truth.any():
            continue
        pair = []
        for a, b in itertools.combinations(keys, 2):
            u = (ms[a] | ms[b]).sum()
            pair.append((ms[a] & ms[b]).sum() / u if u else 1.0)
        iou_t = {k: ((ms[k] & truth).sum() / (ms[k] | truth).sum()) for k in keys}
        dis.append(dict(id=cid, name=name, mean_pair_iou=round(float(np.mean(pair)), 3),
                        **{k + ' iou': round(float(v), 3) for k, v in iou_t.items()}))
    dis.sort(key=lambda d: d['mean_pair_iou'])
    write(f'{outdir}/disagree.csv', dis)
    write_sheet(f'{outdir}/sheet_disagree.png', [d['id'] for d in dis[:8]], keys, cache)
    # blue mats and yellow leaves, picked by eye from the first sheets
    write_sheet(f'{outdir}/sheet_mats_yellow.png', ['A30', 'A25', 'B21', 'B24'], keys, cache)
    print('best per source on corrected cells:', best)


if __name__ == '__main__':
    main(*sys.argv[1:3])
