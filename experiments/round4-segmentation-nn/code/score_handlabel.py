"""#406, log 44: score grow from leaf cores and the stage E network against Aaron's 8 hand-drawn cells.

  score_handlabel.py OUTCSV OUTPNG

Answer key: `analysis/labels/handlabel/returned/unzipped/labelled/<file>_hand_mask.png` (255 = plant), drawn by
Aaron from an empty picture on 2026-11-21, no machine draft shown. Every leaf in the crop counts, also leaves of
neighbouring plants (handlabel README), so every method is scored over the whole crop.

Methods, each on the crop box of `analysis/labels/handlabel/manifest.csv` (native pixels):
- grow from leaf cores: the training label of the photo (`analysis/labels-grow/masks/<rig>/<capture>.png`,
  1 = plant; 0 and 255 = not plant).
- network: the stage E fold model that held out the cell's day (manifest column fold_run), read as in the
  stage scores: production on the whole photo, development on the crop alone; half resolution, stride 192,
  middle kept. Photos decoded with `npec_rig.images.decode_full`.
Scores: IoU = |method & hand| / |method | hand|; area ratio = method px / hand px.
"""
import csv
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import train_cv as T  # noqa: E402

HL = f'{T.NN}/analysis/labels/handlabel'
HAND = f'{HL}/returned/unzipped/labelled'


def main(out_csv, out_png):
    from npec_rig.images import decode_full
    import torch
    man = list(csv.DictReader(open(f'{HL}/manifest.csv')))
    models = {}
    rows, panels = [], []
    for r in man:
        x, y, w, h = (int(r[k]) for k in ('crop_x0', 'crop_y0', 'crop_w', 'crop_h'))
        hand = cv2.imread(f'{HAND}/{r["file"]}_hand_mask.png', 0) > 0
        assert hand.shape == (h, w), (r['id'], hand.shape, (h, w))
        rgb_full = decode_full(f'{T.DATA}/{r["photo_file"]}')
        crop = rgb_full[y:y + h, x:x + w].copy()
        lab = cv2.imread(f'{T.LABELS}/masks/{r["rig"]}/{r["photo_capture_id"]}.png', 0)
        assert lab.shape == rgb_full.shape[:2]
        grow = lab[y:y + h, x:x + w] == 1
        run = r['fold_run']                       # s2_f{k}_e40
        k = int(run.split('_f')[1].split('_')[0])
        if k not in models:
            models[k] = T.load_model(2, k, '_e40')
        with torch.no_grad():
            if r['rig'] == 'production':
                m, _ = T.predict_crop_from_photo(models[k], rgb_full, [(x, y, w, h, 'c')], 2)
                net = m['c']
            else:
                net = T.predict_crop_alone(models[k], crop, 2)
        del rgb_full
        res = dict(id=r['id'], rig=r['rig'], day=r['day'], tray=r['tray'], cell=r['cell'], group=r['group'],
                   fold_run=run, hand_px=int(hand.sum()))
        for name, m in (('grow', grow), ('net', net)):
            inter, union = int((m & hand).sum()), int((m | hand).sum())
            res[f'{name}_px'] = int(m.sum())
            res[f'{name}_iou'] = round(inter / union, 4) if union else 1.0
            res[f'{name}_ratio'] = round(m.sum() / hand.sum(), 4) if hand.sum() else ''
        rows.append(res)
        panels.append((r, crop, hand, grow, net, res))
        print(res, flush=True)
    with open(out_csv, 'w', newline='') as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    sheet(panels, out_png)


def sheet(panels, out_png):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    n = len(panels)
    fig, ax = plt.subplots(n, 4, figsize=(13, 3.5 * n + 1.2))
    fig.suptitle('Hand-drawn answer key (Aaron, 2026-11-21) against grow from leaf cores and the network\n'
                 'Solid magenta = plant. Grey with no fill = not plant (a grey copy of the colour crop). '
                 'Network = stage E fold model that never saw this day.', fontsize=10, y=0.999)
    for i, (r, crop, hand, grow, net, s) in enumerate(panels):
        cols = [(crop, f'{r["id"]}, {r["rig"]}, {r["day"]}, tray {r["tray"]} {r["cell"]}\ncolour crop'),
                (T.magenta(crop, hand), f'your hand outline\n{s["hand_px"]} plant px'),
                (T.magenta(crop, grow), f'grow from leaf cores\nIoU {s["grow_iou"]:.3f}, area ratio {s["grow_ratio"]:.3f}'),
                (T.magenta(crop, net), f'network (stage E, {r["fold_run"]})\nIoU {s["net_iou"]:.3f}, area ratio {s["net_ratio"]:.3f}')]
        for j, (im, t) in enumerate(cols):
            ax[i, j].imshow(im)
            ax[i, j].set_title(t, fontsize=8, loc='left')
            ax[i, j].axis('off')
    fig.tight_layout(rect=(0, 0, 1, 0.985))
    fig.savefig(out_png, dpi=110)


if __name__ == '__main__':
    main(*sys.argv[1:3])
