"""#402, metrology log 33, phase 1: settings by leave-one-day-out CV on TRAINING days only, then the
final models. No test cell (split = test) is read for features, prediction or any metric here.

  python clf402_train.py prep  RUN      sample training pixels from every training cell
  python clf402_train.py bench RUN      time one fit (largest settings) to size the grid
  python clf402_train.py cv    RUN [rig:day,...]  leave-one-day-out CV over the grid, plus rule H and
                                        the current rule on the same held-out cells; resumable
  python clf402_train.py merge RUN      cv_folds/*.csv into cv_cells.csv
  python clf402_train.py pick  RUN      choose the settings from the CV results (written to RUN)
  python clf402_train.py final RUN      train all-train, prod-train, dev-train models, save joblib + JSON
  python clf402_train.py time  RUN NAME time and peak memory of one prediction on crop NAME

RUN holds inputs/ (drafts/cells, check csv) and labels-out/ (from clf402_labels.py).
A fold is one (rig, day) of the training days. Seeds 402 throughout. Decision: forest probability
> 0.5 (sklearn's predict on two classes: a tie goes to not plant). No post-processing.
"""
import csv
import itertools
import json
import os
import platform
import resource
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clf402_features as F  # noqa: E402

SEED = 402
CAP = 1000          # pixels per class per training cell (all of a class when it has fewer); 2000
                    # was tried first and made the CV grid about 10 h on this Pi (bench.log)
N_JOBS = int(os.environ.get('CLF402_JOBS', 3))  # 3 on the Pi (one core for the live app), 6 on the Mac
TREES = (50, 100, 200)
DEPTHS = (12, 20, None)
LEAVES = (1, 5)
SCALESETS = {'with_s8': F.SIGMAS_ALL, 'no_s8': F.SIGMAS_NO8}
# Class balance (Aaron, 2026-11-10): 'even' = the samples as drawn, no weights (about 50/50 plant);
# 'true share' = the same samples with sample_weight so that, within each training cell, plant and
# not-plant carry that cell's true pixel shares, while each cell keeps the same total weight as it
# has samples (so big crops still do not dominate). Decision stays at probability 0.5 in both.
BALANCES = ('even', 'true share')
NEAR = 0.005


def cells(run, split='train'):
    rows = list(csv.DictReader(open(f'{run}/inputs/check_2026-11-10_aaron.csv')))
    out = []
    for r in rows:
        if r['split'] != split:
            continue
        rig, day = r['file'].split('_')[:2]
        out.append(dict(id=r['id'], name=r['file'], rig=rig, day=day, stratum=r['stratum']))
    return out


def load_cell(run, c):
    assert c['id'] in TRAIN_IDS, 'test cell must not be read in phase 1'
    rgb = np.asarray(Image.open(f'{run}/inputs/drafts/cells/{c["name"]}.tif').convert('RGB'))
    lab = np.load(f'{run}/labels-out/labels/{c["name"]}.npz')
    return rgb, lab['truth'], lab['draft']


def current_rule(rgb):
    f = rgb.astype(np.float32)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    exg = (2 * g - r - b) / (r + g + b + 1e-6)
    return (exg > 0.1) & (g > r)


def score(pred, truth):
    nt, npred = int(truth.sum()), int(pred.sum())
    inter, union = int((pred & truth).sum()), int((pred | truth).sum())
    return dict(truth_px=nt, pred_px=npred,
                iou=inter / union if nt else None,
                area_ratio=npred / nt if nt else None,
                false_plant_share=npred / truth.size if nt == 0 else None,
                fp_px=int((pred & ~truth).sum()), fn_px=int((~pred & truth).sum()))


def sample(truth, rng):
    idx = []
    for cls in (True, False):
        p = np.flatnonzero(truth.ravel() == cls)
        idx.append(p if len(p) <= CAP else rng.choice(p, CAP, replace=False))
    return np.concatenate(idx)


def prep(run):
    X, y, cid, sizes = [], [], [], {}
    for k, c in enumerate(cells(run)):
        rgb, truth, _ = load_cell(run, c)
        feat, names = F.features(rgb, F.SIGMAS_ALL)
        idx = sample(truth, np.random.default_rng([SEED, k]))
        X.append(feat.reshape(-1, feat.shape[-1])[idx]); y.append(truth.ravel()[idx])
        cid += [c['id']] * len(idx)
        sizes[c['id']] = dict(plant=int(y[-1].sum()), not_plant=int((~y[-1]).sum()))
        print(c['id'], sizes[c['id']], flush=True)
    np.savez(f'{run}/samples_cap{CAP}.npz', X=np.concatenate(X), y=np.concatenate(y), cid=np.array(cid),
             names=np.array(names))
    json.dump(sizes, open(f'{run}/samples_cap{CAP}_per_cell.json', 'w'), indent=1)


def load_samples(run):
    s = np.load(f'{run}/samples_cap{CAP}.npz')
    return s['X'], s['y'], s['cid'], list(s['names'])


def true_share_weights(run, y, cid):
    """sample_weight for 'true share': in cell c, class k gets n_c * (N_kc / N_c) / n_kc per sampled
    pixel (n = sampled, N = pixels in the crop's truth mask)."""
    w = np.zeros(len(y), np.float64)
    for c in cells(run):
        sel = cid == c['id']
        if not sel.any():
            continue
        truth = np.load(f'{run}/labels-out/labels/{c["name"]}.npz')['truth']
        n_c = sel.sum()
        for k in (True, False):
            sk = sel & (y == k)
            if sk.any():
                w[sk] = n_c * (np.count_nonzero(truth == k) / truth.size) / sk.sum()
    return w


def forest(n_trees, depth, leaf):
    from sklearn.ensemble import RandomForestClassifier
    return RandomForestClassifier(n_estimators=n_trees, max_depth=depth, min_samples_leaf=leaf,
                                  random_state=SEED, n_jobs=N_JOBS)


def tree_proba_cumulative(model, X, stops):
    """Mean plant probability over the first k trees, for each k in stops (exactly what a forest
    of k trees with the same seed gives: sklearn draws the trees' seeds in sequence)."""
    est = model.estimators_
    plant_col = list(model.classes_).index(True)
    acc = np.zeros(len(X), np.float64)
    out = {}
    with ThreadPoolExecutor(N_JOBS) as ex:
        for i, p in enumerate(ex.map(lambda t: t.predict_proba(X)[:, plant_col], est)):
            acc += p
            if i + 1 in stops:
                out[i + 1] = acc / (i + 1)
    return out


def bench(run):
    X, y, cid, names = load_samples(run)
    print('samples', X.shape, 'plant', int(y.sum()), flush=True)
    for depth, leaf in ((None, 1), (12, 5)):
        t = time.time(); m = forest(50, depth, leaf).fit(X, y)
        print(f'fit 50 trees depth {depth} leaf {leaf}: {time.time() - t:.1f} s, '
              f'nodes/tree {np.mean([e.tree_.node_count for e in m.estimators_]):.0f}', flush=True)


_G = {}


def _init(X, y, w, cols):
    _G.update(X=X, y=y, w=w, cols=cols)


def _fit_task(args):
    sk, depth, leaf, bal = args
    from sklearn.ensemble import RandomForestClassifier
    m = RandomForestClassifier(n_estimators=max(TREES), max_depth=depth, min_samples_leaf=leaf,
                               random_state=SEED, n_jobs=1)
    m.fit(_G['X'][:, _G['cols'][sk]], _G['y'],
          sample_weight=_G['w'] if bal == 'true share' else None)
    return args, m


CV_FIELDS = ['rig', 'day', 'id', 'stratum', 'method', 'trees', 'depth', 'leaf', 'scales', 'balance',
             'truth_px', 'pred_px', 'iou', 'area_ratio', 'false_plant_share', 'fp_px', 'fn_px']


def _maxrss_mb(who):
    r = resource.getrusage(who).ru_maxrss
    return r / 2**20 if sys.platform == 'darwin' else r / 1024  # bytes on macOS, kB on Linux


def cv(run, only=None):
    """Resumable: each fold is written to RUN/cv_folds/<rig>_<day>.csv when it is finished
    (written to a .part file, then renamed), and folds with a file are skipped. `only`: list of
    'rig:day' to run just those folds. Per fold the 12 forests are fitted in N_JOBS worker
    processes (one core each), then each held-out cell's features are computed once and
    predicted by all 12 (trees in N_JOBS threads). cv_cells.csv is the union, made by `merge`."""
    import multiprocessing as mp
    X, y, cid, names = load_samples(run)
    tr = cells(run)
    folds = sorted({(c['rig'], c['day']) for c in tr})
    if only:
        want = [tuple(o.split(':')) for o in only]
        folds = [f for f in want if f in folds]
    os.makedirs(f'{run}/cv_folds', exist_ok=True)
    cols = {k: F.column_index(names, s)[0] for k, s in SCALESETS.items()}
    grid = list(itertools.product(SCALESETS, DEPTHS, LEAVES, BALANCES))
    for rig, day in folds:
        out = f'{run}/cv_folds/{rig}_{day}.csv'
        if os.path.exists(out):
            print(f'fold {rig} {day}: done before, skipped', flush=True)
            continue
        t0 = time.time()
        held = [c for c in tr if (c['rig'], c['day']) == (rig, day)]
        keep = ~np.isin(cid, [c['id'] for c in held])
        w = true_share_weights(run, np.where(keep, y, False), np.where(keep, cid, ''))
        with mp.get_context('spawn').Pool(N_JOBS, initializer=_init,
                                          initargs=(X[keep], y[keep], w[keep], cols)) as pool:
            models = dict(pool.map(_fit_task, grid))
        t1 = time.time()
        rows = []
        for c in held:
            rgb, truth, draft = load_cell(run, c)
            base = dict(rig=rig, day=day, id=c['id'], stratum=c['stratum'], trees='', depth='',
                        leaf='', scales='', balance='')
            rows.append({**base, 'method': 'rule H draft', **score(draft, truth)})
            rows.append({**base, 'method': 'current rule', **score(current_rule(rgb), truth)})
            feat, _ = F.features(rgb, F.SIGMAS_ALL)
            feat = feat.reshape(-1, feat.shape[-1])
            for (sk, depth, leaf, bal) in grid:
                fx = np.ascontiguousarray(feat[:, cols[sk]])
                probs = tree_proba_cumulative(models[(sk, depth, leaf, bal)], fx, set(TREES))
                for nt in TREES:
                    pred = (probs[nt] > 0.5).reshape(truth.shape)
                    rows.append(dict(base, method='forest', trees=nt, depth=depth, leaf=leaf,
                                     scales=sk, balance=bal, **score(pred, truth)))
                del fx
            del feat
        with open(out + '.part', 'w', newline='') as f:
            wr = csv.DictWriter(f, fieldnames=CV_FIELDS)
            wr.writeheader(); wr.writerows(rows)
        os.replace(out + '.part', out)
        t2 = time.time()
        info = dict(rig=rig, day=day, n_cells=len(held), n_train_px=int(keep.sum()), n_jobs=N_JOBS,
                    fit_s=round(t1 - t0, 1), predict_s=round(t2 - t1, 1), host=platform.node(),
                    maxrss_parent_mb=round(_maxrss_mb(resource.RUSAGE_SELF)),
                    maxrss_largest_child_mb=round(_maxrss_mb(resource.RUSAGE_CHILDREN)))
        with open(f'{run}/cv_folds/timing.jsonl', 'a') as f:
            f.write(json.dumps(info) + '\n')
        print(f'fold {rig} {day}: {len(held)} cells, fit {t1 - t0:.0f} s, predict {t2 - t1:.0f} s, '
              f'peak MB parent {info["maxrss_parent_mb"]} child {info["maxrss_largest_child_mb"]}',
              flush=True)


def merge(run):
    """Union of RUN/cv_folds/*.csv into RUN/cv_cells.csv (what pick reads)."""
    import glob
    files = sorted(glob.glob(f'{run}/cv_folds/*.csv'))
    with open(f'{run}/cv_cells.csv', 'w', newline='') as f:
        wr = csv.DictWriter(f, fieldnames=CV_FIELDS)
        wr.writeheader()
        for p in files:
            wr.writerows(csv.DictReader(open(p)))
    print(len(files), 'folds merged')


def _num(v):
    return None if v in ('', 'None') else float(v)


def pick(run):
    rows = list(csv.DictReader(open(f'{run}/cv_cells.csv')))
    by = {}
    for r in rows:
        key = (r['method'], r['trees'], r['depth'], r['leaf'], r['scales'], r.get('balance', ''))
        by.setdefault(key, []).append(r)
    summ = []
    for key, rs in by.items():
        ious = [_num(r['iou']) for r in rs if _num(r['iou']) is not None]
        ar = [_num(r['area_ratio']) for r in rs if _num(r['area_ratio']) is not None]
        fps = [_num(r['false_plant_share']) for r in rs if _num(r['false_plant_share']) is not None]
        summ.append(dict(method=key[0], trees=key[1], depth=key[2], leaf=key[3], scales=key[4], balance=key[5],
                         n_cells=len(rs), n_iou=len(ious), mean_iou=float(np.mean(ious)),
                         min_iou=float(np.min(ious)), mean_area_ratio=float(np.mean(ar)),
                         min_area_ratio=float(np.min(ar)), max_area_ratio=float(np.max(ar)),
                         n_empty=len(fps), mean_false_plant_share=float(np.mean(fps)) if fps else None))
    forests = [s for s in summ if s['method'] == 'forest']
    best = max(s['mean_iou'] for s in forests)

    def size(s):  # smaller model first: fewer trees, shallower, bigger leaves, fewer features
        d = 1e9 if s['depth'] == 'None' else float(s['depth'])
        return (int(s['trees']), d, -int(s['leaf']), 0 if s['scales'] == 'no_s8' else 1,
                0 if s['balance'] == 'even' else 1)

    near = sorted([s for s in forests if s['mean_iou'] >= best - NEAR], key=size)
    chosen = near[0]
    json.dump(dict(rule=f'smallest forest with CV mean IoU within {NEAR} of the best',
                   best_mean_iou=best, chosen=chosen, within=near,
                   summary=sorted(summ, key=lambda s: -s['mean_iou'])),
              open(f'{run}/cv_pick.json', 'w'), indent=1)
    print('best', best); print('chosen', chosen)


def final(run):
    from sklearn.ensemble import RandomForestClassifier  # noqa: F401
    import joblib, sklearn, skimage, scipy, PIL
    X, y, cid, names = load_samples(run)
    ch = json.load(open(f'{run}/cv_pick.json'))['chosen']
    depth = None if ch['depth'] == 'None' else int(ch['depth'])
    sig = SCALESETS[ch['scales']]
    col, fnames = F.column_index(names, sig)
    tr = cells(run)
    rig_of = {c['id']: c['rig'] for c in tr}
    rigs = np.array([rig_of[i] for i in cid])
    os.makedirs(f'{run}/models', exist_ok=False)
    info = {}
    for tag, sel in (('all_train', np.ones(len(y), bool)), ('prod_train', rigs == 'prod'),
                     ('dev_train', rigs == 'dev')):
        t = time.time()
        wt = None
        if ch['balance'] == 'true share':
            wt = true_share_weights(run, np.where(sel, y, False), np.where(sel, cid, ''))[sel]
        m = forest(int(ch['trees']), depth, int(ch['leaf'])).fit(X[sel][:, col], y[sel],
                                                                 sample_weight=wt)
        fit_s = time.time() - t
        path = f'{run}/models/rf402_{tag}.joblib'
        joblib.dump(m, path, compress=3)
        info[tag] = dict(file=os.path.basename(path), cells=sorted(set(cid[sel])),
                         n_cells=len(set(cid[sel])), n_pixels=int(sel.sum()),
                         n_plant=int(y[sel].sum()), fit_seconds=round(fit_s, 1),
                         file_bytes=os.path.getsize(path),
                         importances=dict(sorted(zip(fnames, map(float, m.feature_importances_)),
                                                 key=lambda kv: -kv[1])))
        print(tag, info[tag]['n_cells'], info[tag]['n_pixels'], f'{fit_s:.0f} s', flush=True)
    meta = dict(issue=402, log_section=33, phase=1,
                settings=dict(n_estimators=int(ch['trees']), max_depth=depth,
                              min_samples_leaf=int(ch['leaf']), balance=ch['balance'], max_features='sqrt (sklearn default)',
                              criterion='gini', bootstrap=True, random_state=SEED,
                              decision='plant if mean tree probability > 0.5 (sklearn predict)',
                              post_processing='none'),
                features=dict(sigmas=list(sig), colour_channels=F.COLOUR, edge_channels=F.EDGE_CHANNELS,
                              edge_features=F.EDGE, border_mode=F.MODE, n_features=len(fnames),
                              names=fnames, module='clf402_features.py',
                              structure_tensor='gradient of Gaussian at sigma, products smoothed at sigma/2'),
                sampling=dict(cap_per_class_per_cell=CAP, rule='per training cell, up to CAP plant '
                              'and up to CAP not-plant pixels drawn without replacement (all when fewer)',
                              rng='numpy default_rng([402, cell index in check csv training order])'),
                labels='truth: corrected outlines (39), accepted drafts (20), A28 none; Aaron 2026-11-10',
                cv=json.load(open(f'{run}/cv_pick.json'))['rule'],
                seeds=SEED, versions=dict(python=platform.python_version(), sklearn=sklearn.__version__,
                                          skimage=skimage.__version__, scipy=scipy.__version__,
                                          numpy=np.__version__, pillow=PIL.__version__,
                                          joblib=joblib.__version__),
                models=info)
    json.dump(meta, open(f'{run}/models/rf402_settings.json', 'w'), indent=1)


def time_one(run, name):
    import joblib
    meta = json.load(open(f'{run}/models/rf402_settings.json'))
    sig = tuple(meta['features']['sigmas'])
    tr = {c['name']: c for c in cells(run)}
    c = tr[name]  # a training cell: only time and memory are measured, no metric
    rgb, _, _ = load_cell(run, c)
    r0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    m = joblib.load(f'{run}/models/rf402_all_train.joblib')
    r1 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    t = time.time(); feat, _ = F.features(rgb, sig); tf = time.time() - t
    t = time.time(); p = m.predict(feat.reshape(-1, feat.shape[-1])); tp = time.time() - t
    r2 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    npx = rgb.shape[0] * rgb.shape[1]
    out = dict(cell=name, px=npx, feature_s=round(tf, 2), predict_s=round(tp, 2), n_jobs=N_JOBS,
               us_per_px=round(1e6 * (tf + tp) / npx, 2),
               maxrss_mb_before_model=round(r0 / 1024), maxrss_mb_after_model=round(r1 / 1024),
               maxrss_mb_peak=round(r2 / 1024), feature_array_mb=round(feat.nbytes / 2**20))
    print(json.dumps(out))
    with open(f'{run}/timing.jsonl', 'a') as f:
        f.write(json.dumps(out) + '\n')


TRAIN_IDS = set()

if __name__ == '__main__':
    mode, run = sys.argv[1], sys.argv[2]
    TRAIN_IDS.update(c['id'] for c in cells(run))
    if mode == 'time':
        time_one(run, sys.argv[3])
    elif mode == 'cv':
        cv(run, sys.argv[3].split(',') if len(sys.argv) > 3 else None)
    else:
        dict(prep=prep, bench=bench, merge=merge, pick=pick, final=final)[mode](run)
