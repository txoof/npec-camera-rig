"""#406 stages F and G: tables and pictures for Aaron (scratch/406-train/stage-F.md/png, stage-G.md/png).

    final_fg.py stage_f     # truth-edit re-score, final network training, sanity check on seen cells, whole photo
    final_fg.py stage_g     # compile results per chip, 8-bit loss on the truth cells by cross-validation

Stage F (method in train_cv.py's docstring). Re-score after the purple-check truth edit: stage A (half resolution),
stage E (40 epochs) and grow from leaf cores, before against after, all from saved predictions or masks (no network
run); "before" = the score files kept as scores_before_purple_check.csv, and for grow from leaf cores its masks
scored against the original truths kept in analysis/labels/truth_edits/. The final network is scored on the 42
training cells as a sanity check only: every cell was seen in training. Whole photo: production_28022, read at half
resolution (stride 192, middle kept) by the stage E fold model that held out its day and by the final network.

Stage G (method in hailo_final.py's docstring). Each training cell scored by its held-out stage E fold model, float32
(the stage E scores, re-scored on the current truths) and quantised in Hailo's emulator for each chip (the same
reading: whole photo for production, crop for development). Per rig: pooled IoU, mean IoU, mean area error
(mean |area ratio - 1|, in %); the quantised-minus-float difference per fold and its standard deviation over the 5
folds; seedlings on their own.

Pictures: plant is solid magenta (255, 0, 255) on a grey copy of the crop; not plant is grey with no fill. The same 8
cells as stage A (the cells stage-A.md lists, fixed here so later truth edits cannot move the picks).
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, '/home/txoof/temp.nobackup/wt/npec-406-label-sources/src')
import train_cv as T  # noqa: E402

NN = Path(T.NN)
TRAIN = Path(T.TRAIN)
SCR = Path(T.SCR)
HROOT = NN / 'hailo'
EDITS = NN / 'analysis' / 'labels' / 'truth_edits'
TAG = 'before_purple_check'
PHOTO = 'production_28022'
# stage A's 8 cells and why they were picked (stage-A.md), kept fixed
PICKS = [('A02', 'seedling: production "empty" cell with the smallest truth'),
         ('A27', 'blue mat: median truth size of the blue-mat cells'),
         ('A12', 'green soil, production: median truth size'),
         ('B03', 'green soil / moss, development: median truth size'),
         ('B24', '"empty" development cell (dead or tiny plant): median truth size'),
         ('B23', 'largest plants (size 5 of 5): median truth size, both rigs'),
         ('B19', 'network best in stage A: highest half-resolution IoU of the cells not picked above'),
         ('A01', 'network worst in stage A: lowest half-resolution IoU of the cells not picked above')]
RIGNAME = {'prod': 'production', 'dev': 'development'}
HEAD_IOU = 'Mean IoU (0 to 1, higher is better)'
HEAD_ERR = 'Mean area error (%, lower is better)'
HEAD_POOL = 'Pooled IoU (0 to 1, higher is better)'


def now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')


def rows_for(suffix, tag='', s=2):
    return T.variant_rows(32, 'mid192', T.cells(), suffix, tag, s=s)


def st(rows):
    x = T.stats(rows)
    x['err_pct'] = 100 * x['mean_abs_ratio_err']
    return x


def iou_of(r):
    return r['inter'] / r['union'] if r['union'] else 1.0


def ratio_of(r):
    return r['method_px'] / r['truth_px'] if r['truth_px'] else float('nan')


def grow_before():
    """Grow from leaf cores against the truths as they were before the purple check (originals in truth_edits/)."""
    out = {}
    for r in T.cells():
        orig = EDITS / f'{r["name"]}_truth_{TAG}.png'
        truth = cv2.imread(str(orig if orig.exists() else f'{T.REF}/truth/{r["name"]}_truth.png'), 0) > 0
        m = cv2.imread(f'{T.NN}/analysis/labels/grow/{r["name"]}_grow.png', 0) > 0
        out[r['id']] = dict(inter=int((m & truth).sum()), union=int((m | truth).sum()), method_px=int(m.sum()),
                            truth_px=int(truth.sum()))
    return out


def fold_sd(man, fold, a, b):
    """Per-fold differences b - a in mean IoU and in mean area error (percentage points), and their SD over folds."""
    di, de = [], []
    for k in range(T.NFOLD):
        ids = [r['id'] for r in man if fold[r['day']] == k]
        if ids:
            sa, sb = st([a[i] for i in ids]), st([b[i] for i in ids])
            di.append(sb['mean_iou'] - sa['mean_iou'])
            de.append(sb['err_pct'] - sa['err_pct'])
    return di, de


# ---------------------------------------------------------------- pictures

def font(px):
    from PIL import ImageFont
    import matplotlib.font_manager as fm
    return ImageFont.truetype(fm.findfont('DejaVu Sans'), px)


def wrap(draw, text, f, width):
    words, lines, cur = text.split(), [], ''
    for w in words:
        t = (cur + ' ' + w).strip()
        if draw.textlength(t, font=f) <= width - 8:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def text_block(texts, width, px=15, bg=255, bold_first=False):
    """White block with each text wrapped to width; returns an RGB array."""
    from PIL import Image, ImageDraw
    f, fb = font(px), font(px)
    probe = ImageDraw.Draw(Image.new('RGB', (10, 10)))
    lines = []
    for i, t in enumerate(texts):
        lines += [(ln, fb if (bold_first and i == 0) else f) for ln in wrap(probe, t, f, width)]
    lh = int(px * 1.3)
    img = Image.new('RGB', (width, lh * len(lines) + 8), (bg, bg, bg))
    d = ImageDraw.Draw(img)
    for i, (ln, ff) in enumerate(lines):
        d.text((4, 4 + i * lh), ln, fill=(0, 0, 0), font=ff)
    return np.asarray(img)


def pad_h(a, h, val=255):
    return np.vstack([a, np.full((h - a.shape[0], a.shape[1], 3), val, np.uint8)]) if a.shape[0] < h else a


def grid_row(panels, S):
    """panels: [(rgb image, [caption lines])] -> one row, captions above, all headers the same height."""
    heads = [text_block(c, S) for _, c in panels]
    hh = max(h.shape[0] for h in heads)
    cols = []
    for (im, _), h in zip(panels, heads):
        im = cv2.resize(im, (S, S), interpolation=cv2.INTER_AREA if im.shape[0] > S else cv2.INTER_NEAREST)
        cols += [np.vstack([pad_h(h, hh), im]), np.full((hh + S, 6, 3), 255, np.uint8)]
    return np.hstack(cols)


def legend(width, title, extra):
    sw = np.full((26, width, 3), 255, np.uint8)
    sw[4:22, 6:30] = (255, 0, 255)
    sw[4:22, 250:274] = (128, 128, 128)
    from PIL import Image, ImageDraw
    im = Image.fromarray(sw)
    d = ImageDraw.Draw(im)
    f = font(15)
    d.text((36, 4), 'solid magenta = plant', fill=(0, 0, 0), font=f)
    d.text((280, 4), 'grey, no fill = not plant (a grey copy of the crop)', fill=(0, 0, 0), font=f)
    top = text_block([title], width, px=18)
    return np.vstack([top, text_block(['COLOURS: solid magenta (255, 0, 255) means plant. Grey with no fill means not '
                                       'plant; the grey is a grey copy of the colour crop. The first column is the '
                                       'crop in colour.'], width), np.asarray(im), text_block(extra, width)])


def cell_picture(path, title, extra, columns, S=320):
    """columns: function(cell row, rgb, truth) -> list of (image, caption lines) per panel."""
    man = {r['id']: r for r in T.cells()}
    fold = T.folds()
    rows = []
    for cid, why in PICKS:
        r = man[cid]
        rgb, truth = T.load_crop(r['name'])
        pan = [(rgb, [f'{cid}, {RIGNAME[r["rig"]]}, {r["day"]}', f'colour crop; {r["stratum"]}; day held out in '
                      f'fold {fold[r["day"]] + 1}']),
               (T.magenta(rgb, truth), ['truth (Aaron)', f'{int(truth.sum())} plant px'])]
        pan += columns(r, rgb, truth)
        line = grid_row(pan, S)
        bar = text_block([f'{cid}, picked as: {why}'], line.shape[1], bg=235)
        rows += [bar, line, np.full((12, line.shape[1], 3), 255, np.uint8)]
    W = max(x.shape[1] for x in rows)
    head = legend(W, title, extra)
    return head, rows, W


def cap(r):
    return f'IoU {iou_of(r):.3f}, area ratio {ratio_of(r):.3f}'


def save(path, parts):
    W = max(p.shape[1] for p in parts)
    parts = [np.hstack([p, np.full((p.shape[0], W - p.shape[1], 3), 255, np.uint8)]) if p.shape[1] < W else p
             for p in parts]
    cv2.imwrite(str(path), cv2.cvtColor(np.vstack(parts), cv2.COLOR_RGB2BGR))


# ---------------------------------------------------------------- stage F

def whole_photo():
    """production_28022 at half resolution: E fold model (held out) and final network; quarter-size pictures."""
    from npec_rig.images import decode_full
    fold = T.folds()
    p = {x['key']: x for x in T.photos()}[PHOTO]
    k = fold[p['day_utc']]
    rgb = decode_full(f'{T.DATA}/{p["jpg"]}')
    img = T.scale_img(rgb, 2)
    out = {}
    for nm, kk in (('fold', k), ('final', None)):
        model = T.load_model(2, kk, '_e40')
        lg, _ = T.infer(model, img)
        out[nm] = lg > 0
        del model
    q = cv2.resize(rgb, (rgb.shape[1] // 4, rgb.shape[0] // 4), interpolation=cv2.INTER_AREA)
    del rgb
    a, b = out['fold'], out['final']
    info = dict(photo=PHOTO, day=p['day_utc'], fold=k + 1, px=int(a.size), fold_plant=int(a.sum()),
                final_plant=int(b.sum()), agree_iou=float((a & b).sum() / max(1, (a | b).sum())))
    pics = {}
    for nm, m in out.items():
        mq = cv2.resize(m.astype(np.float32), (q.shape[1], q.shape[0]), interpolation=cv2.INTER_AREA) > 0.05
        pics[nm] = T.magenta(q, mq)
    return q, pics, info


def stage_f():
    man, fold = T.cells(), T.folds()
    src = {r['id']: r['truth_source'] for r in T.read_csv(f'{T.REF}/truth_index_train.csv')}
    A_b, A_a = rows_for('', TAG), rows_for('')
    E_b, E_a = rows_for('_e40', TAG), rows_for('_e40')
    G_b, G_a = grow_before(), T.grow_rows()
    sets = [('grow from leaf cores', G_b, G_a), ('stage A (15 epochs), half resolution', A_b, A_a),
            ('stage E (40 epochs), the final settings', E_b, E_a)]
    rb = json.load(open(TRAIN / f'rescore_{TAG}.json'))
    tc = json.load(open(TRAIN / 'cache' / 's2' / f'truth_cells_rebuild_{TAG}.json'))
    L = ['# Stage F: the final network, trained on every training day', '',
         f'Written by `final_fg.py stage_f` ({now()} UTC). Development check. Training cells only (42: production 17, '
         'development 25); no test cell was opened. Half resolution, threshold probability 0.5, float32.', '',
         '## 1. The purple-check truth edit', '',
         'Aaron decided that purple stalk tissue is plant. After stage E was trained, three more development truths were '
         'edited (B12, B13, B19; B21 was edited earlier and was already in E\'s training). Record: '
         '`analysis/labels/truth_edits/`.', '',
         f'- Half-resolution truth cells (`cache/s2/truth_cells.npz`) rebuilt from the truth files; the old file is kept as '
         f'`truth_cells_{TAG}.npz`. Cells that changed: {"; ".join(tc["changed"])}. The other '
         f'{tc["cells"] - len(tc["changed"])} cells are identical.',
         f'- Every earlier run re-scored from its saved predictions, with no network run and no retraining '
         f'({len(T.RESCORE_RUNS)} score files; the old ones kept as `scores*_{TAG}.csv`). Cells whose scores changed: '
         f'{", ".join(rb["changed_cells"])}. Grow from leaf cores was scored from its masks.',
         '- Stage E\'s fold models were trained with the old B12, B13 and B19 labels. The final network uses the new ones.', '',
         'Development cells, before and after the edit (production cells did not change):', '',
         f'| Method | {HEAD_IOU}, before | {HEAD_IOU}, after | {HEAD_ERR}, before | {HEAD_ERR}, after | '
         f'{HEAD_POOL}, before | {HEAD_POOL}, after |', '|---|---|---|---|---|---|---|']
    dev = [r['id'] for r in man if r['rig'] == 'dev']
    for nm, b, a in sets:
        sb, sa = st([b[i] for i in dev]), st([a[i] for i in dev])
        L.append(f"| {nm} | {sb['mean_iou']:.4f} | {sa['mean_iou']:.4f} | {sb['err_pct']:.2f} | {sa['err_pct']:.2f} | "
                 f"{sb['pooled_iou']:.4f} | {sa['pooled_iou']:.4f} |")
    L += ['', 'The three edited cells:', '',
          '| Cell | Truth px, before | Truth px, after | Method | IoU, before | IoU, after | Area ratio, before | Area ratio, after |',
          '|---|---|---|---|---|---|---|---|']
    for cid in ('B12', 'B13', 'B19'):
        for nm, b, a in sets:
            L.append(f"| {cid} | {b[cid]['truth_px']} | {a[cid]['truth_px']} | {nm} | {iou_of(b[cid]):.3f} | "
                     f"{iou_of(a[cid]):.3f} | {ratio_of(b[cid]):.3f} | {ratio_of(a[cid]):.3f} |")
    # E against A after the edit
    rows_dec, kept = T.decide(A_a, E_a, man, fold)
    L += ['', 'Stage E against stage A by the agreed rule, on the new truths (information only; Aaron chose E on '
          '2026-11-21):', '',
          '| Rig | Mean IoU, E minus A | SD over folds | Mean area error, A minus E (percentage points) | SD over folds (percentage points) | E better by more than the spread? |',
          '|---|---|---|---|---|---|']
    for d in rows_dec:
        L.append(f"| {RIGNAME[d['rig']]} | {d['d_iou']:+.4f} | {d['sd_iou']:.4f} | {100 * d['d_err']:+.2f} | "
                 f"{100 * d['sd_err']:.2f} | {'yes' if d['ok'] else 'no'} |")
    # ---- training
    run = TRAIN / 'runs' / 's2_final_e40'
    meta = json.load(open(run / 'meta.json'))
    lf = T.epoch_losses(meta)
    le = np.mean([T.epoch_losses(json.load(open(TRAIN / 'runs' / f's2_f{k}_e40' / 'meta.json'))) for k in range(T.NFOLD)],
                 axis=0)
    last = meta['history'][-1]
    L += ['', '## 2. Training the final network', '',
          f'Stage E\'s settings: U-Net with a MobileNetV2 encoder from ImageNet weights, half resolution, 256 px tiles, '
          f'crop shifts up to 32 px, no public data, AdamW lr 5e-4, 150 warm-up steps then cosine to zero over '
          f'{meta["epochs"]} epochs of {T.STEPS_PER_EPOCH} steps ({meta["steps"]} steps), batch {meta["batch"]}, '
          f'BCE + dice, truth-cell share {meta["p_truth"]}, the same augmentation. Trained on every training day: '
          f'{meta["photos"]} photos ({meta["patches"]} patches; the flagged steadiness photos left out) and all '
          f'{len(meta["cells"])} training truth cells with the current truths. Seed 199 (the fold formula with no fold). '
          f'A checkpoint every epoch; the last weights kept, no early stopping.', '',
          f'- Model: `analysis/train/runs/s2_final_e40/model.pt`.',
          f'- Training time {meta["train_seconds"] / 60:.1f} min on the RTX 2060 SUPER, peak GPU memory {meta["peak_mem_mib"]} MiB.',
          f'- Final training loss (mean of the last epoch, BCE + dice with augmentation): **{lf[-1]:.4f}** '
          f'(last logged stretch: loss {last["loss"]:.4f}, BCE {last["bce"]:.4f}, dice {last["dice"]:.4f}). '
          f'The 5 stage E fold models ended at {le[-1]:.4f} on average.', '',
          '| Epoch | Final network, training loss | Stage E fold models, mean training loss |', '|---|---|---|']
    for e in list(range(0, len(lf), 5)) + ([len(lf) - 1] if (len(lf) - 1) % 5 else []):
        L.append(f'| {e + 1} | {lf[e]:.4f} | {le[e]:.4f} |')
    nan_free = all(np.isfinite(h['loss']) for h in meta['history'])
    L += ['', f'No NaN or infinite loss in the log: {"yes" if nan_free else "NO"}.']
    # ---- sanity check
    F = {}
    for r in T.read_csv(str(run / 'scores.csv')):
        if (r['rig'] == 'prod' and r['mode'] == 'photo') or (r['rig'] == 'dev' and r['mode'] == 'crop'):
            for c in ('inter', 'union', 'method_px', 'truth_px'):
                r[c] = int(r[c])
            F[r['id']] = r
    assert set(F) == {r['id'] for r in man}
    L += ['', '## 3. Sanity check on the 42 training cells: seen in training, not a score', '',
          'The final network has no held-out score: every training cell was seen in training. These numbers only show '
          'that it learned what it was given. The cross-validated figure for the final settings is the stage E fold '
          'model row (each cell scored by the model that never saw its day). Production cells: network on the whole '
          'photo; development cells: on the crop alone.', '',
          f'| Rig | Method | {HEAD_IOU} | {HEAD_ERR} | {HEAD_POOL} | Lowest IoU |', '|---|---|---|---|---|---|']
    for rig in ('prod', 'dev'):
        ids = [r['id'] for r in man if r['rig'] == rig]
        for nm, rr in (('grow from leaf cores', G_a), ('stage E fold model, not trained on the cell\'s day (held out)', E_a),
                       ('final network, trained on these cells (seen in training)', F)):
            s_ = st([rr[i] for i in ids])
            L.append(f"| {RIGNAME[rig]} ({len(ids)}) | {nm} | {s_['mean_iou']:.3f} | {s_['err_pct']:.1f} | "
                     f"{s_['pooled_iou']:.3f} | {s_['min_iou']:.3f} |")
    seeds = [r for r in man if r['stratum'] == 'empty' and r['rig'] == 'prod'] + \
            [r for r in man if r['stratum'].endswith('size 1 of 5')]
    L += ['', 'Seedlings (production "empty" cells and every "size 1 of 5" cell), seen in training for the final network:', '',
          '| Cell | Rig | Truth px | IoU, stage E fold model (held out) | IoU, final network (seen) | Area ratio, stage E fold model (held out) | Area ratio, final network (seen) |',
          '|---|---|---|---|---|---|---|']
    for r in seeds:
        i = r['id']
        L.append(f"| {i} | {RIGNAME[r['rig']]} | {F[i]['truth_px']} | {iou_of(E_a[i]):.3f} | {iou_of(F[i]):.3f} | "
                 f"{ratio_of(E_a[i]):.3f} | {ratio_of(F[i]):.3f} |")
    # ---- whole photo and picture
    q, pics, info = whole_photo()
    L += ['', f'## 4. One whole production photo ({PHOTO}, {info["day"]}), seen in training', '',
          f'Read at half resolution (stride 192, middle kept) by the stage E fold model that held out its day (fold '
          f'{info["fold"]}) and by the final network (this photo was one of its training photos). Plant pixels at half '
          f'resolution: fold model {info["fold_plant"]:,} ({100 * info["fold_plant"] / info["px"]:.2f}% of the photo), '
          f'final network {info["final_plant"]:,} ({100 * info["final_plant"] / info["px"]:.2f}%). Agreement between '
          f'the two masks: IoU {info["agree_iou"]:.3f}.', '']

    def cols(r, rgb, truth):
        mode = 'photo' if r['rig'] == 'prod' else 'crop'
        gm = cv2.imread(f'{T.NN}/analysis/labels/grow/{r["name"]}_grow.png', 0) > 0
        me = cv2.imread(str(TRAIN / 'pred' / 's2_e40' / f'{r["id"]}_{mode}.png'), 0) > 0
        mf = cv2.imread(str(TRAIN / 'pred' / 's2_final_e40' / f'{r["id"]}_{mode}.png'), 0) > 0
        return [(T.magenta(rgb, gm), ['grow from leaf cores', cap(G_a[r['id']])]),
                (T.magenta(rgb, me), ['stage E fold model, not trained on this cell\'s day', cap(E_a[r['id']])]),
                (T.magenta(rgb, mf), ['final network, trained on this cell (seen in training)', cap(F[r['id']])])]
    head, rows, W = cell_picture(SCR / 'stage-F.png', 'Stage F: the final network, trained on every training day',
                                 ['Columns: colour crop | truth (Aaron) | grow from leaf cores | stage E fold model, not '
                                  'trained on this cell\'s day (the cross-validated figure) | final network, trained on '
                                  'this cell (seen in training: a sanity check, not a score).',
                                  'Production cells: network run on the whole photo; development cells: on the crop alone. '
                                  'Captions: IoU with the truth, and area ratio = marked px / truth px. Truths as edited '
                                  'after the purple check. The same 8 cells as stage A.'], cols)
    half = (W - 6) // 2
    def ph(img, txt):
        h = int(img.shape[0] * half / img.shape[1])
        return np.vstack([text_block(txt, half), cv2.resize(img, (half, h), interpolation=cv2.INTER_AREA)])
    p1 = ph(q, [f'Whole photo {PHOTO} ({info["day"]}), colour, quarter size'])
    p2 = ph(pics['final'], ['final network, trained on this photo (seen in training)',
                            f'{100 * info["final_plant"] / info["px"]:.2f}% of the photo plant'])
    p3 = ph(pics['fold'], [f'stage E fold model, not trained on this photo\'s day (fold {info["fold"]})',
                           f'{100 * info["fold_plant"] / info["px"]:.2f}% of the photo plant'])
    p4 = text_block([f'Agreement between the two masks over the whole photo: IoU {info["agree_iou"]:.3f}.',
                     'Plant marks are drawn 1 px wider at this size so thin marks stay visible.'], half)
    hh = max(p1.shape[0], p2.shape[0])
    sp = np.full((hh, 6, 3), 255, np.uint8)
    r1 = np.hstack([pad_h(p1, hh), sp, pad_h(p2, hh)])
    hh2 = max(p3.shape[0], p4.shape[0])
    r2 = np.hstack([pad_h(p3, hh2), np.full((hh2, 6, 3), 255, np.uint8), pad_h(p4, hh2)])
    save(SCR / 'stage-F.png', [head] + rows + [text_block(['Whole photo, read at half resolution, stride 192, middle kept'],
                                                           W, px=17, bg=235), r1, np.full((6, r1.shape[1], 3), 255, np.uint8), r2])
    L += ['## Picture', '', '`stage-F.png`: colour crop | truth | grow from leaf cores | stage E fold model, not trained on '
          'this cell\'s day | final network, trained on this cell (seen in training); then the whole photo. The same 8 '
          'cells as stage A:', '']
    L += [f'- {c}: {w}' for c, w in PICKS]
    L += ['', 'Files: `experiments/round4-segmentation-nn/code/train_cv.py` (method in its docstring) and `final_fg.py`; '
          'driver `~/temp.nobackup/npec-406-nn/analysis/train/run_fg.sh`; final network `runs/s2_final_e40/` (model.pt, '
          'meta.json, scores.csv), its masks `pred/s2_final_e40/`, under `~/temp.nobackup/npec-406-nn/analysis/train/`.', '']
    open(SCR / 'stage-F.md', 'w').write('\n'.join(L))
    T.log('stage F summary written: stage-F.md, stage-F.png')
    print('\n'.join(L))


# ---------------------------------------------------------------- stage G

def q_rows(arch):
    out = {}
    for k in range(T.NFOLD):
        for r in T.read_csv(str(HROOT / 'stage-G' / f'f{k}' / f'{arch}_L1' / 'cell_scores.csv')):
            if (r['rig'] == 'prod' and r['mode'] == 'photo') or (r['rig'] == 'dev' and r['mode'] == 'crop'):
                for c in ('inter', 'union', 'method_px', 'truth_px'):
                    r[c] = int(r[c])
                out[r['id']] = r
    assert set(out) == {r['id'] for r in T.cells()}, f'{arch}: missing cells'
    return out


def steps(d):
    f = d / 'steps.jsonl'
    out = {}
    if f.exists():
        for ln in f.read_text().splitlines():
            r = json.loads(ln)
            out[r['step']] = r
    return out


def snr(d):
    f = d / 'optimize.log'
    m = re.findall(r'SNR:\s*([0-9.]+) dB', f.read_text()) if f.exists() else []
    return float(m[-1]) if m else None


def mask_agree(arch, man):
    """Pooled IoU of the quantised masks against the float masks, per rig (how far quantisation moves the masks)."""
    out = {}
    for rig in ('prod', 'dev'):
        I = U = 0
        for r in man:
            if r['rig'] != rig:
                continue
            mode = 'photo' if rig == 'prod' else 'crop'
            a = cv2.imread(str(TRAIN / 'pred' / 's2_e40' / f'{r["id"]}_{mode}.png'), 0) > 0
            b = cv2.imread(str(TRAIN / 'pred' / f's2_e40_q_{arch}' / f'{r["id"]}_{mode}.png'), 0) > 0
            I += int((a & b).sum())
            U += int((a | b).sum())
        out[rig] = I / U if U else 1.0
    return out


def stage_g():
    man, fold = T.cells(), T.folds()
    Fl = rows_for('_e40')
    Q = {a: q_rows(a) for a in ('hailo8', 'hailo10h')}
    chip = {'hailo8': 'Hailo-8', 'hailo10h': 'Hailo-10H'}
    dfc = {'hailo8': 'DFC 3.33.1', 'hailo10h': 'DFC 5.1.0'}
    cal = json.load(open(HROOT / 'final' / 'calib.json'))
    ncal = cal['calib_tiles']
    L = ['# Stage G: the final network compiled for both Hailo chips, and the 8-bit loss on the truth cells', '',
         f'Written by `final_fg.py stage_g` ({now()} UTC). Development check, Hailo\'s emulator only: no HEF has run on a '
         'chip and no rig was touched. Training cells only (42: production 17, development 25); no test cell was opened.', '',
         '## 1. Method', '',
         f'- Compiled at optimisation level 1 on the CPU, compression level 0, the trial A way (`hailo_final.py`, '
         f'`notes/hailo.md` section 13): ONNX opset 13, ImageNet normalisation in the model script, so the HEF takes '
         f'uint8 RGB 256 x 256 tiles. Hailo-8 with DFC 3.33.1, Hailo-10H with DFC 5.1.0.',
         f'- Calibration: **{ncal} tiles** per model (the DFC\'s suggested 1024' + ('' if ncal == 1024 else
                                                                                 '; reduced, see below') +
         '), from the training photo patches only (`cache/s2/mm`, centre 256 px), half with plant and half without, '
         'shared equally over the UTC dates. Each stage E fold model was calibrated only on tiles of its own training '
         'dates, never its held-out dates; the final network on tiles of every training date.',
         '- Models: the final network (compiled to HEFs, the network that ships) and the 5 stage E fold models '
         '(quantised and emulated only, not compiled to HEFs: they exist to measure the 8-bit loss by cross-validation).',
         '- Scoring: each training cell scored by the stage E fold model that never saw its day, exactly as the float '
         'scores are made: production cells from the **whole photo** at half resolution, development cells from the crop; '
         '256 px tiles at stride 192, logits blended keeping each tile\'s middle, bilinear resize back to full size, '
         'threshold at logit 0 (probability 0.5). The quantised logits come from the emulator (SDK_QUANTIZED) on the same '
         'tiles, stitched by the same code. Before any quantised run, the float logits of the same tiles were stitched '
         'with this code and compared with stage E\'s saved masks: ' +
         f"{sum(json.load(open(HROOT / 'stage-G' / f'f{k}' / 'cell_tiles.json'))['total_px_differing'] for k in range(5))}"
         ' pixels differ over all 42 cells, so the only change between float and quantised is the network.',
         '- Float = the stage E fold models in float32 (torch), scored on the current truths (after the purple check).', '']
    # ---- compile table
    L += ['## 2. Compile results (final network)', '',
          '| | ' + ' | '.join(f'{chip[a]} ({dfc[a]})' for a in Q) + ' |', '|---|---|---|']
    info = {}
    for a in Q:
        d = HROOT / 'final' / f'{a}_L1'
        s_ = steps(d)
        hef = d / f'plantseg_s2_final_e40_{a}.hef'
        est = {}
        for f in (d / 'estimation.csv', d / 'plantseg_s2_final_e40_profile.csv'):
            if f.exists() and not est:
                rr = list(csv.DictReader(open(f)))
                if rr and 'number_of_contexts' in rr[0]:
                    est = rr[0]
        plog = (d / 'profile.log').read_text() if (d / 'profile.log').exists() else ''
        fps = re.search(r'Throughput\s+([0-9.]+ FPS|N/A)', plog)
        lat = re.search(r'Latency\s+([0-9.]+ ms|N/A)', plog)
        ctx = est.get('number_of_contexts')
        if not ctx:
            cl = (d / 'compile.log').read_text() if (d / 'compile.log').exists() else ''
            m = re.findall(r'Context:(\d+)/(\d+)', cl)
            ctx = str(int(m[-1][1]) + 1) if m else '?'
        chk = json.load(open(d / 'check_metrics.json')) if (d / 'check_metrics.json').exists() else {}
        info[a] = dict(ok=hef.exists(), parse=s_.get('parse', {}).get('seconds'), opt=s_.get('optimize', {}).get('seconds'),
                       opt_mem=(s_.get('optimize', {}).get('peak_rss_mib_self', 0) + s_.get('optimize', {}).get('peak_rss_mib_children', 0)),
                       comp=s_.get('compile', {}).get('seconds'), hef=hef, size=hef.stat().st_size if hef.exists() else None,
                       sha=hashlib.sha256(hef.read_bytes()).hexdigest() if hef.exists() else '', ctx=ctx,
                       fps=fps.group(1) if fps else 'not reported', lat=lat.group(1) if lat else 'not reported',
                       snr=snr(d), chk=chk)
    def rowc(nm, f):
        L.append(f'| {nm} | ' + ' | '.join(f(info[a]) for a in Q) + ' |')
    rowc('compile result', lambda i: 'HEF written, no errors' if i['ok'] else 'FAILED')
    rowc('optimise time (level 1, CPU)', lambda i: f"{i['opt'] / 60:.1f} min" if i['opt'] else '?')
    rowc('optimise peak memory (process + largest child)', lambda i: f"{i['opt_mem'] / 1024:.1f} GiB")
    rowc('output signal-to-noise ratio after quantisation', lambda i: f"{i['snr']:.2f} dB" if i['snr'] else '?')
    rowc('compile time', lambda i: f"{i['comp'] / 60:.1f} min" if i['comp'] else '?')
    rowc('contexts', lambda i: str(i['ctx']))
    rowc('compiler speed estimate (profiler)', lambda i: f"{i['fps']}, latency {i['lat']}")
    rowc('HEF', lambda i: f"`{i['hef'].relative_to(NN)}`")
    rowc('HEF size', lambda i: f"{i['size']:,} bytes" if i['size'] else '?')
    rowc('HEF sha256', lambda i: f"`{i['sha']}`")
    rowc('quantised against float, 200 check tiles: mean abs logit difference',
         lambda i: f"{i['chk'].get('mean_abs_logit', float('nan')):.3f}")
    rowc('quantised against float, 200 check tiles: mask IoU at 0.5',
         lambda i: f"{i['chk'].get('iou', float('nan')):.4f}")
    L += ['', f'Copies of both HEFs sit directly in `hailo/final/`. The 200 check tiles are training patches not used for '
          f'calibration (seen in training; {cal.get("check_plant", "?")} with plant), compared with the float network, '
          'as in trial A (level 1 there: mean abs logit difference 0.342, mask IoU 0.985).', '']
    fps8 = re.match(r'([0-9.]+)', str(info['hailo8']['fps']))
    if fps8:
        L += [f'Arithmetic, not measured: one half-resolution photo read as in stage A (432 tiles) is 432 / '
              f'{float(fps8.group(1)):.0f} = {432 / float(fps8.group(1)):.1f} s of Hailo-8 time at the compiler\'s estimate.', '']
    # fold models' quantisation
    L += ['Stage E fold models (quantised for the cross-validation, not compiled):', '',
          '| Fold | Held-out dates | Calibration tiles | Calibration dates | Optimise min, Hailo-8 | Optimise min, Hailo-10H | SNR dB, Hailo-8 | SNR dB, Hailo-10H | Cell tiles emulated | Emulator s per tile, Hailo-8 | Emulator s per tile, Hailo-10H |',
          '|---|---|---|---|---|---|---|---|---|---|---|']
    for k in range(5):
        d = HROOT / 'stage-G' / f'f{k}'
        c = json.load(open(d / 'calib.json'))
        ct = json.load(open(d / 'cell_tiles.json'))
        s8, s10 = steps(d / 'hailo8_L1'), steps(d / 'hailo10h_L1')
        L.append(f"| {k + 1} | {', '.join(x[5:] for x in c['held_out_dates'])} | {c['calib_tiles']} | {c['calib_dates']} | "
                 f"{s8['optimize']['seconds'] / 60:.1f} | {s10['optimize']['seconds'] / 60:.1f} | {snr(d / 'hailo8_L1')} | "
                 f"{snr(d / 'hailo10h_L1')} | {ct['tiles']} | {s8['emulate']['seconds_per_tile']} | {s10['emulate']['seconds_per_tile']} |")
    # ---- results
    L += ['', '## 3. 8-bit loss on the truth cells, cross-validated', '',
          'Each cell scored by the stage E fold model that never saw its day. Whole photos for production cells.', '',
          f'| Rig | Network | {HEAD_IOU} | {HEAD_ERR} | {HEAD_POOL} | Lowest IoU | Pooled area ratio |',
          '|---|---|---|---|---|---|---|']
    meths = [('float32 (torch)', Fl)] + [(f'{chip[a]}, quantised (emulator)', Q[a]) for a in Q]
    for rig in ('prod', 'dev'):
        ids = [r['id'] for r in man if r['rig'] == rig]
        for nm, rr in meths:
            s_ = st([rr[i] for i in ids])
            L.append(f"| {RIGNAME[rig]} ({len(ids)}) | {nm} | {s_['mean_iou']:.4f} | {s_['err_pct']:.2f} | "
                     f"{s_['pooled_iou']:.4f} | {s_['min_iou']:.3f} | {s_['pooled_ratio']:.4f} |")
    L += ['', 'The difference, quantised minus float (negative IoU and positive area error mean the 8-bit network is '
          'worse), with the spread over the 5 folds (standard deviation of the per-fold differences, same cells under '
          'both):', '',
          '| Rig | Chip | Mean IoU difference | SD over folds (IoU) | Mean area error difference (percentage points) | SD over folds (percentage points) | Pooled IoU difference |',
          '|---|---|---|---|---|---|---|']
    perfold = []
    for rig in ('prod', 'dev'):
        rm = [r for r in man if r['rig'] == rig]
        ids = [r['id'] for r in rm]
        for a in Q:
            sf, sq = st([Fl[i] for i in ids]), st([Q[a][i] for i in ids])
            di, de = fold_sd(rm, fold, Fl, Q[a])
            perfold.append((rig, a, di, de))
            L.append(f"| {RIGNAME[rig]} | {chip[a]} | {sq['mean_iou'] - sf['mean_iou']:+.4f} | {np.std(di, ddof=1):.4f} | "
                     f"{sq['err_pct'] - sf['err_pct']:+.2f} | {np.std(de, ddof=1):.2f} | {sq['pooled_iou'] - sf['pooled_iou']:+.4f} |")
    L += ['', 'Per fold, quantised minus float:', '',
          '| Rig | Chip | Measure | fold 1 | fold 2 | fold 3 | fold 4 | fold 5 |', '|---|---|---|---|---|---|---|---|']
    for rig, a, di, de in perfold:
        L.append(f"| {RIGNAME[rig]} | {chip[a]} | mean IoU | " + ' | '.join(f'{x:+.4f}' for x in di) + ' |')
        L.append(f"| {RIGNAME[rig]} | {chip[a]} | mean area error (percentage points) | " + ' | '.join(f'{x:+.2f}' for x in de) + ' |')
    L += ['', 'How far quantisation moves the masks themselves (pooled IoU of the quantised mask against the float mask, '
          'over the cells of the rig; 1 = identical):', '',
          '| Rig | Hailo-8 | Hailo-10H |', '|---|---|---|']
    ag = {a: mask_agree(a, man) for a in Q}
    for rig in ('prod', 'dev'):
        L.append(f"| {RIGNAME[rig]} | {ag['hailo8'][rig]:.4f} | {ag['hailo10h'][rig]:.4f} |")
    # seedlings
    seeds = [r for r in man if r['stratum'] == 'empty' and r['rig'] == 'prod'] + \
            [r for r in man if r['stratum'].endswith('size 1 of 5')]
    L += ['', '## 4. Seedlings on their own', '',
          'Production "empty" cells (seedlings, A01, A02, A17) and every "size 1 of 5" cell, each scored by its held-out '
          'stage E fold model.', '',
          '| Cell | Rig | Truth px | IoU, float | IoU, Hailo-8 | IoU, Hailo-10H | Area ratio, float | Area ratio, Hailo-8 | Area ratio, Hailo-10H |',
          '|---|---|---|---|---|---|---|---|---|']
    for r in seeds:
        i = r['id']
        L.append(f"| {i} | {RIGNAME[r['rig']]} | {Fl[i]['truth_px']} | {iou_of(Fl[i]):.3f} | {iou_of(Q['hailo8'][i]):.3f} | "
                 f"{iou_of(Q['hailo10h'][i]):.3f} | {ratio_of(Fl[i]):.3f} | {ratio_of(Q['hailo8'][i]):.3f} | "
                 f"{ratio_of(Q['hailo10h'][i]):.3f} |")
    sd = [r['id'] for r in seeds]
    L += ['', f'| All {len(sd)} seedling cells | {HEAD_IOU} | {HEAD_ERR} |', '|---|---|---|']
    for nm, rr in meths:
        s_ = st([rr[i] for i in sd])
        L.append(f"| {nm} | {s_['mean_iou']:.4f} | {s_['err_pct']:.2f} |")
    # ---- picture
    def cols(r, rgb, truth):
        mode = 'photo' if r['rig'] == 'prod' else 'crop'
        out = []
        for nm, pdir, rr in (('float: stage E fold model, not trained on this cell\'s day', 's2_e40', Fl),
                             ('Hailo-8 quantised (emulator), same fold model', 's2_e40_q_hailo8', Q['hailo8']),
                             ('Hailo-10H quantised (emulator), same fold model', 's2_e40_q_hailo10h', Q['hailo10h'])):
            m = cv2.imread(str(TRAIN / 'pred' / pdir / f'{r["id"]}_{mode}.png'), 0) > 0
            out.append((T.magenta(rgb, m), [nm, cap(rr[r['id']])]))
        return out
    head, rows, W = cell_picture(SCR / 'stage-G.png', 'Stage G: 8-bit loss in Hailo\'s emulator, cross-validated on '
                                 'the training cells',
                                 ['Columns: colour crop | truth (Aaron) | float32 network | Hailo-8 quantised | Hailo-10H '
                                  'quantised. Every network panel is the stage E fold model that was not trained on this '
                                  'cell\'s day; the quantised panels are that model after 8-bit quantisation, run in '
                                  'Hailo\'s emulator.',
                                  'Production cells: network run on the whole photo; development cells: on the crop alone. '
                                  'Captions: IoU with the truth, and area ratio = marked px / truth px. The same 8 cells '
                                  'as stage A.'], cols)
    save(SCR / 'stage-G.png', [head] + rows)
    L += ['', '## Picture', '', '`stage-G.png`: colour crop | truth | float | Hailo-8 quantised | Hailo-10H quantised, the '
          'same 8 cells as stage A:', '']
    L += [f'- {c}: {w}' for c, w in PICKS]
    L += ['', 'Files: `experiments/round4-segmentation-nn/code/hailo_final.py` (method in its docstring) and '
          '`final_fg.py`; driver `~/temp.nobackup/npec-406-nn/analysis/train/run_fg.sh`; final network HEFs, HARs and '
          'logs in `~/temp.nobackup/npec-406-nn/hailo/final/`; fold models in `hailo/stage-G/f<k>/` (k = fold - 1); '
          'quantised masks in `analysis/train/pred/s2_e40_q_<chip>/`.', '']
    open(SCR / 'stage-G.md', 'w').write('\n'.join(L))
    T.log('stage G summary written: stage-G.md, stage-G.png')
    print('\n'.join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['stage_f', 'stage_g'])
    a = ap.parse_args()
    {'stage_f': stage_f, 'stage_g': stage_g}[a.cmd]()


if __name__ == '__main__':
    main()
