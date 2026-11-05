"""#352, 24.7 check 2: rules F and G on the #355 frames, each JPEG setting against the uncompressed frame."""
import json, csv, sys, os
import numpy as np, cv2
from PIL import Image
sys.path.insert(0, os.path.dirname(__file__))
from ruleg import rules
Image.MAX_IMAGE_PIXELS = None
J = '/home/pi/scratch/thr-352/jpegq/'
SET = ['B', 'C', 'D', 'F', 'G', 'H', 'E']
trays = json.load(open(J + 'trays.json'))['trays']


def per_tray(rgb):
    H, W = rgb.shape[:2]; out = {}
    for t in trays:
        o = np.array(t['outline'])
        x0, y0 = np.maximum(np.floor(o.min(0)).astype(int), 0); x1, y1 = np.minimum(np.ceil(o.max(0)).astype(int) + 1, [W, H])
        ins = np.zeros((y1 - y0, x1 - x0), np.uint8); cv2.fillPoly(ins, [np.round(o - [x0, y0]).astype(np.int32).reshape(-1, 1, 2)], 1)
        out[t['tray_id']] = rules(np.ascontiguousarray(rgb[y0:y1, x0:x1]), ins > 0, t['tray_id'])
    return out


rows = []
for i in range(3):
    ref = per_tray(np.load(J + f'frame{i}.npy', mmap_mode='r'))
    for tid, m in ref.items():
        rows.append(dict(frame=i, setting='raw', tray=tid, soil_peak=m['soil_peak'], cut=m['cut'], warn=m['warn'], tag_found=any(d.tag_id == tid for d in m['dets']),
                         F_ratio=1.0, G_ratio=1.0, F_iou=1.0, G_iou=1.0, F_px=int(m['F'].sum()), G_px=int(m['G'].sum()), cur_px=int(m['current'].sum())))
    for s in SET:
        mm = per_tray(np.asarray(Image.open(J + f'frame{i}_{s}.jpg').convert('RGB')))
        for tid, m in mm.items():
            a = ref[tid]
            row = dict(frame=i, setting=s, tray=tid, soil_peak=m['soil_peak'], cut=m['cut'], warn=m['warn'], tag_found=any(d.tag_id == tid for d in m['dets']))
            for k in 'FG':
                row[f'{k}_ratio'] = round(m[k].sum() / max(a[k].sum(), 1), 4); row[f'{k}_iou'] = round((m[k] & a[k]).sum() / max((m[k] | a[k]).sum(), 1), 4)
                row[f'{k}_px'] = int(m[k].sum())
            row['cur_px'] = int(m['current'].sum())
            rows.append(row)
    print('frame', i, 'done', flush=True)
with open(J + 'ruleg_dev.csv', 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print('\nper tray, uncompressed frames: soil peak, cutoff, warning, tag found, G area / F area')
for t in trays:
    rr = [r for r in rows if r['tray'] == t['tray_id'] and r['setting'] == 'raw']
    print(f"  tray {t['tray_id']}: soil peak {', '.join(f'{r['soil_peak']:+.3f}' for r in rr)}; cutoff {', '.join(f'{r['cut']:+.3f}' for r in rr)}; "
          f"warn {sum(r['warn'] for r in rr)}/3; tag {sum(r['tag_found'] for r in rr)}/3; G/F {', '.join(f'{r['G_px'] / max(r['F_px'], 1):.3f}' for r in rr)}")
print('\nsetting: area / uncompressed, mean (range) over 27, and IoU')
for s in SET:
    rr = [r for r in rows if r['setting'] == s]
    for k in 'FG':
        v = np.array([r[f'{k}_ratio'] for r in rr]); u = np.array([r[f'{k}_iou'] for r in rr])
        print(f'  {s} rule {k}: {v.mean():.4f} ({v.min():.3f} to {v.max():.3f})  IoU {u.mean():.3f} (min {u.min():.3f})')
