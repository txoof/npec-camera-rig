"""#406, log 44 step 1: SAM 3 with text prompts on the staged TRAINING crops.
  . models/smoke/env.sh; env-sam/bin/python -I sam3_run.py LABELS CHECKPOINT
fp16 autocast (fp32 fails, bf16 runs out of memory on 8 GB: notes/sam.md). Detection threshold 0.3, the
lowest scored; every kept instance mask is saved with its score, so 0.4 and 0.5 are applied afterwards
(the kept set at 0.4 is the subset of 0.3 with score above 0.4). Writes LABELS/sam3/<name>.npz (per
prompt: bool masks N x H x W, scores N) and LABELS/sam3/times.csv. One warm-up crop is not timed."""
import csv
import os
import sys
import time

import numpy as np
import torch
from PIL import Image

from sam3.model.sam3_image_processor import Sam3Processor
from sam3.model_builder import build_sam3_image_model

PROMPTS = ['plant', 'leaf', 'potato plant']
THRESH = 0.3


def main(labels, ckpt):
    ref = os.path.join(labels, 'ref')
    out = os.path.join(labels, 'sam3')
    os.makedirs(out, exist_ok=True)
    rows = list(csv.DictReader(open(os.path.join(ref, 'manifest_train.csv'))))
    assert all(r['split'] == 'train' for r in rows)
    model = build_sam3_image_model(checkpoint_path=ckpt, load_from_HF=False)
    proc = Sam3Processor(model, confidence_threshold=THRESH)
    times = []
    sync = torch.cuda.synchronize
    with torch.inference_mode(), torch.autocast('cuda', dtype=torch.float16):
        img0 = Image.open(os.path.join(ref, 'crops', rows[0]['file'][:-4] + '.png')).convert('RGB')
        st = proc.set_image(img0)
        proc.set_text_prompt(prompt=PROMPTS[0], state=st)
        sync()
        torch.cuda.reset_peak_memory_stats()
        for r in rows:
            name = r['file'][:-4]
            img = Image.open(os.path.join(ref, 'crops', name + '.png')).convert('RGB')
            t0 = time.perf_counter()
            st = proc.set_image(img)
            sync()
            rec = dict(id=r['id'], name=name, w=img.width, h=img.height, encoder_s=round(time.perf_counter() - t0, 4))
            save = {}
            for p in PROMPTS:
                proc.reset_all_prompts(st)
                t0 = time.perf_counter()
                o = proc.set_text_prompt(prompt=p, state=st)
                sync()
                rec[p.replace(' ', '_') + '_s'] = round(time.perf_counter() - t0, 4)
                m = o['masks']
                m = m[:, 0].cpu().numpy().astype(bool) if len(m) else np.zeros((0, img.height, img.width), bool)
                sc = o['scores'].float().cpu().numpy() if len(m) else np.zeros(0, np.float32)
                assert np.all(np.isfinite(sc))
                key = p.replace(' ', '_')
                save[key + '_masks'] = np.packbits(m, axis=-1)
                save[key + '_scores'] = sc
                rec[key + '_n'] = len(sc)
            np.savez_compressed(os.path.join(out, name + '.npz'), shape=np.array([img.height, img.width]), **save)
            times.append(rec)
            print(rec, flush=True)
    peak = round(torch.cuda.max_memory_allocated() / 2**20)
    with open(os.path.join(out, 'times.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(times[0]))
        w.writeheader()
        w.writerows(times)
    print('peak MiB allocated', peak)


if __name__ == '__main__':
    main(*sys.argv[1:3])
