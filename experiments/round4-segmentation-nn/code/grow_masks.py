"""#406, log 44 step 1: grow from leaf cores at the setting of log 34.1 (core 0.07), rebuilt per
TRAINING crop, checked against the per-cell counts stored by log 34.1, plus its cores and the SAM 2.1
point prompts.
  grow_masks.py LABELS        (LABELS = analysis/labels; reads LABELS/ref/, writes LABELS/grow/)

The tray cache of log 34 is gone, so the mask is rebuilt in the crop: the stored draft (core 0.1,
the method pixel for pixel, log 34.1 harness) joined with every 8-connected region of the crop that is
above the cell's lower cutoff (manifest cut_h) and not blue (as grow363.grow_p, blue margin 0) and
holds a core pixel at 0.07 (greenness above 0.07 and G > R) and does not touch the draft. A region
that touches the draft was already grown at core 0.1; in the crop it can be larger than on the tray,
because the crop knows neither the tray outline nor the tray tag, so it is not added. Accepted only when intersection, union and
pixel count with the truth equal setting 2 of ../../round3-grow-tuning/data/oat_scores.csv.

Cores: mask pixels with greenness above 0.07 and G > R. Points per 8-connected core: the most interior
pixel (largest distance to the core edge), and for p5 up to 4 more core pixels at random (seed 0)."""
import csv
import json
import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TUNE = os.path.join(HERE, '..', '..', 'round3-grow-tuning', 'data')
CORE = 0.07


def exg_of(rgb):
    r, g, b = (rgb[..., i].astype(np.float32) for i in range(3))
    return (2 * g - r - b) / (r + g + b + 1e-6), r, g, b


def rebuild(rgb, draft, cut):
    exg, r, g, b = exg_of(rgb)
    notblue = ~((b > r) & (b > g))
    low = ((exg > cut) & notblue).astype(np.uint8)
    core = (exg > CORE) & (g > r)
    n, lab = cv2.connectedComponents(low, connectivity=8, ltype=cv2.CV_32S)
    keep = np.zeros(n, bool)
    keep[np.unique(lab[core])] = True
    keep[np.unique(lab[draft])] = False   # regions touching the draft: already in it (see docstring)
    keep[0] = False
    return draft | keep[lab], exg, g > r


def points(cores, rng):
    n, lab = cv2.connectedComponents(cores.astype(np.uint8), connectivity=8, ltype=cv2.CV_32S)
    dist = cv2.distanceTransform(np.pad(cores, 1).astype(np.uint8), cv2.DIST_L2, 3)[1:-1, 1:-1]
    out = []
    for k in range(1, n):
        ys, xs = np.nonzero(lab == k)
        i = int(np.argmax(dist[ys, xs]))
        p1 = [[int(xs[i]), int(ys[i])]]
        rest = [j for j in range(len(xs)) if j != i]
        extra = rng.choice(rest, size=min(4, len(rest)), replace=False) if rest else []
        out.append(dict(px=int(len(xs)), p1=p1, p5=p1 + [[int(xs[j]), int(ys[j])] for j in extra]))
    return out


def main(labels):
    ref = os.path.join(labels, 'ref')
    out = os.path.join(labels, 'grow')
    os.makedirs(out, exist_ok=True)
    rows = list(csv.DictReader(open(os.path.join(ref, 'manifest_train.csv'))))
    assert all(r['split'] == 'train' for r in rows)
    stored = {r['id']: r for r in csv.DictReader(open(os.path.join(TUNE, 'oat_scores.csv'))) if r['setting'] == '2'}
    grid = json.load(open(os.path.join(TUNE, 'oat.json')))
    assert grid[2]['core'] == CORE and grid[2]['varied'] == 'core'
    rng = np.random.default_rng(0)
    checks, prompts = [], {}
    for r in rows:
        name = r['file'][:-4]
        rgb = cv2.cvtColor(cv2.imread(os.path.join(ref, 'crops', name + '.png')), cv2.COLOR_BGR2RGB)
        draft = cv2.imread(os.path.join(ref, 'drafts', name + '_draft.png'), cv2.IMREAD_GRAYSCALE) > 0
        truth = cv2.imread(os.path.join(ref, 'truth', name + '_truth.png'), cv2.IMREAD_GRAYSCALE) > 0
        t0 = time.perf_counter()
        m, exg, gr = rebuild(rgb, draft, float(r['cut_h']))
        dt = time.perf_counter() - t0
        got = dict(inter=int((m & truth).sum()), union=int((m | truth).sum()), method_px=int(m.sum()),
                   truth_px=int(truth.sum()))
        s = stored[r['id']]
        same = all(got[k] == int(s[k]) for k in got)
        checks.append(dict(id=r['id'], name=name, same=same, draft_px=int(draft.sum()),
                           added_px=int((m & ~draft).sum()), crop_s=round(dt, 4),
                           **got, **{'stored_' + k: int(s[k]) for k in got}))
        cv2.imwrite(os.path.join(out, name + '_grow.png'), m.astype(np.uint8) * 255)
        cores = m & (exg > CORE) & gr
        cv2.imwrite(os.path.join(out, name + '_cores.png'), cores.astype(np.uint8) * 255)
        prompts[r['id']] = dict(name=name, cores=points(cores, rng))
    with open(os.path.join(out, 'check.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(checks[0]))
        w.writeheader()
        w.writerows(checks)
    json.dump(prompts, open(os.path.join(out, 'prompts.json'), 'w'))
    bad = [c['id'] for c in checks if not c['same']]
    nc = [len(p['cores']) for p in prompts.values()]
    print(json.dumps(dict(cells=len(checks), same=len(checks) - len(bad), differ=bad,
                          added=[(c['id'], c['added_px']) for c in checks if c['added_px']],
                          cores_min=min(nc), cores_max=max(nc), cores_total=sum(nc))))


if __name__ == '__main__':
    main(sys.argv[1])
