"""#406, log 44 step 1: SAM 2.1 large, prompted by the cores of grow from leaf cores, on the staged
TRAINING crops.
  . models/smoke/env.sh; env-sam/bin/python -I sam2_run.py LABELS CKPT_DIR SAM2_SRC
fp16 autocast. Each connected core is one prompt (LABELS/grow/prompts.json); the masks of all prompts of a
crop are joined. Variants: p1m one point, 3 masks out, highest predicted IoU kept; p1s one point, one
mask out; p5s up to 5 points, one mask out. Writes LABELS/sam2/<name>_<variant>.png and times.csv. One
warm-up crop is not timed. A crop without cores gets an empty mask."""
import csv
import json
import os
import sys
import time

import cv2
import numpy as np
import torch

from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor

CFG = 'configs/sam2.1/sam2.1_hiera_l.yaml'
CKPT = 'sam2.1_hiera_large.pt'
BATCH = 64


def run_variant(pred, cores, key, multi, hw):
    out = np.zeros(hw, bool)
    if not cores:
        return out
    groups = {}
    for c in cores:   # prompts with the same number of points go in one batch
        groups.setdefault(len(c[key]), []).append(c[key])
    for n, pts in groups.items():
        for i in range(0, len(pts), BATCH):
            p = np.array(pts[i:i + BATCH], np.float32)          # B x n x 2
            m, s, _ = pred.predict(point_coords=p, point_labels=np.ones(p.shape[:2], np.int32),
                                   multimask_output=multi)
            m = m.reshape(len(p), -1, *hw)
            s = s.reshape(len(p), -1)
            best = np.argmax(s, axis=1)
            out |= np.any(m[np.arange(len(p)), best] > 0, axis=0)
    return out


def main(labels, ckpt_dir):
    ref = os.path.join(labels, 'ref')
    out = os.path.join(labels, 'sam2')
    os.makedirs(out, exist_ok=True)
    rows = list(csv.DictReader(open(os.path.join(ref, 'manifest_train.csv'))))
    assert all(r['split'] == 'train' for r in rows)
    prompts = json.load(open(os.path.join(labels, 'grow', 'prompts.json')))
    pred = SAM2ImagePredictor(build_sam2(CFG, os.path.join(ckpt_dir, CKPT), device='cuda'))
    sync = torch.cuda.synchronize
    variants = (('p1m', 'p1', True), ('p1s', 'p1', False), ('p5s', 'p5', False))
    times = []
    with torch.inference_mode(), torch.autocast('cuda', dtype=torch.float16):
        for warm in (True, False):
            for r in (rows[:1] if warm else rows):
                name = r['file'][:-4]
                img = cv2.cvtColor(cv2.imread(os.path.join(ref, 'crops', name + '.png')), cv2.COLOR_BGR2RGB)
                cores = prompts[r['id']]['cores']
                t0 = time.perf_counter()
                pred.set_image(img)
                sync()
                rec = dict(id=r['id'], name=name, cores=len(cores), encoder_s=round(time.perf_counter() - t0, 4))
                for v, key, multi in variants:
                    t0 = time.perf_counter()
                    m = run_variant(pred, cores, key, multi, img.shape[:2])
                    sync()
                    rec[v + '_s'] = round(time.perf_counter() - t0, 4)
                    if not warm:
                        cv2.imwrite(os.path.join(out, f'{name}_{v}.png'), m.astype(np.uint8) * 255)
                if warm:
                    torch.cuda.reset_peak_memory_stats()
                    continue
                times.append(rec)
                print(rec, flush=True)
    with open(os.path.join(out, 'times.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(times[0]))
        w.writeheader()
        w.writerows(times)
    print('peak MiB allocated', round(torch.cuda.max_memory_allocated() / 2**20))


if __name__ == '__main__':
    main(*sys.argv[1:3])
