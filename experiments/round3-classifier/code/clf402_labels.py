"""#402, metrology log 33: truth masks for the 60 cells and the correction record.

  python clf402_labels.py CELLS CORRECTED CHECK OUT

CELLS      folder with <name>.tif and <name>_draft.roi.zip (from drafts-2026-11-09.zip)
CORRECTED  data/corrected-20261110T1109Z (only <name>_corrected.roi.zip is read; *_MISTAKE* never)
CHECK      data/check_2026-11-10_aaron.csv (id, file, split, stratum)
OUT        new folder: labels/<name>.npz (truth, draft as bool), correction_record.csv,
           correction_summary.json

Truth (Aaron, 2026-11-10): the corrected outlines for the 39 corrected cells; the draft for the
20 accepted as drafted; A28 (green paper) no plant at all. Everything outside the outlines is
not plant. Outlines read with mask_rois.roi_zip_to_mask (ImageJ fill).

The correction record is about the labels, not about any model: it may use every cell.
"""
import csv
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mask_rois import roi_zip_to_mask  # noqa: E402

ACCEPTED = {'A03', 'A04', 'A05', 'A06', 'A07', 'A08', 'A09', 'A10', 'A11', 'A13', 'A15', 'A16',
            'A20', 'A22', 'A23', 'B02', 'B17', 'B25', 'B29', 'B30'}
NO_PLANT = {'A28'}


def iou(a, b):
    u = np.count_nonzero(a | b)
    return np.count_nonzero(a & b) / u if u else float('nan')


def main(cells, corrected, check, out):
    os.makedirs(f'{out}/labels', exist_ok=False)
    rows = list(csv.DictReader(open(check)))
    assert len(rows) == 60
    rec = []
    for r in rows:
        name = r['file']
        img = Image.open(f'{cells}/{name}.tif')
        w, h = img.size
        draft = roi_zip_to_mask(f'{cells}/{name}_draft.roi.zip', w, h)
        cfile = f'{corrected}/{name}_corrected.roi.zip'
        if r['id'] in NO_PLANT:
            truth, source = np.zeros((h, w), bool), 'no plant (none.txt)'
        elif r['id'] in ACCEPTED:
            assert not os.path.exists(cfile), name
            truth, source = draft.copy(), 'draft accepted'
        else:
            truth, source = roi_zip_to_mask(cfile, w, h), 'corrected'
            if r['id'] == 'B13':
                source = 'corrected (equal to draft)' if np.array_equal(truth, draft) else 'corrected (DIFFERS from draft)'
        np.savez_compressed(f'{out}/labels/{name}.npz', truth=truth, draft=draft)
        nd, nt = int(draft.sum()), int(truth.sum())
        rec.append(dict(id=r['id'], file=name, rig=name.split('_')[0], split=r['split'],
                        stratum=r['stratum'], source=source, w=w, h=h, draft_px=nd, truth_px=nt,
                        added_px=int((truth & ~draft).sum()), removed_px=int((draft & ~truth).sum()),
                        iou_draft_truth=round(iou(draft, truth), 4),
                        area_ratio_truth_over_draft=round(nt / nd, 4) if nd else None))
    with open(f'{out}/correction_record.csv', 'w', newline='') as f:
        wr = csv.DictWriter(f, fieldnames=list(rec[0]))
        wr.writeheader(); wr.writerows(rec)

    def group(sel):
        g = [x for x in rec if sel(x)]
        ious = [x['iou_draft_truth'] for x in g if not np.isnan(x['iou_draft_truth'])]
        d, t = sum(x['draft_px'] for x in g), sum(x['truth_px'] for x in g)
        return dict(n=len(g), n_changed=sum(1 for x in g if x['added_px'] or x['removed_px']),
                    mean_iou=round(float(np.mean(ious)), 4) if ious else None,
                    min_iou=round(float(np.min(ious)), 4) if ious else None,
                    pooled_truth_over_draft=round(t / d, 4) if d else None,
                    added_px=sum(x['added_px'] for x in g), removed_px=sum(x['removed_px'] for x in g),
                    draft_px=d, truth_px=t)

    summ = {'all': group(lambda x: True)}
    for rig in ('prod', 'dev'):
        summ[rig] = group(lambda x, rig=rig: x['rig'] == rig)
    for s in sorted({x['stratum'] for x in rec}):
        for rig in ('prod', 'dev'):
            g = group(lambda x, s=s, rig=rig: x['stratum'] == s and x['rig'] == rig)
            if g['n']:
                summ[f'{rig} | {s}'] = g
    json.dump(summ, open(f'{out}/correction_summary.json', 'w'), indent=1)
    for k, v in summ.items():
        print(k, v)


if __name__ == '__main__':
    main(*sys.argv[1:5])
