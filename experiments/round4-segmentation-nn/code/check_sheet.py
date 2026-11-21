"""#406 step 2: check sheet of the training labels for Aaron (README, step 2).
  check_sheet.py DATA LABELS RESULTS OUTDIR
One picture per photo: the whole photo downscaled and 2 trays, plant filled solid magenta, ignore translucent grey
ignore, nothing for not plant. Photos chosen by rule, not by look:
- production experiment 18 (spread and reference): 7 photos at evenly spaced places in time order;
- production experiments 9 to 16: 1, the middle one in time;
- development experiment 4 (spread only, so the 61 steadiness photos of one evening do not crowd
  it): 4 at evenly spaced places;
- the photo with the most plant pixels; the photo with the most plant pixels in production trays
  1 to 6 (the plant trays, log 33), which lies in the blue-mat days (6 to 16 November).
- tray 8 (synthetic plant, labelled ignore, Aaron 2026-11-20): the photo where grow from leaf cores
  found the most on it, shown beside tray 7 (paper squares, labelled not plant).
Trays shown: by the final labels, the tray with the most plant pixels and the next one; on production
experiment 18, the first tray 1 to 6 and the second the next tray 1 to 6."""
import csv
import json
import os
import sys
from collections import defaultdict

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
MAGENTA, GREY = np.array([255, 0, 255], np.float32), np.array([128, 128, 128], np.float32)
MONTHS = 'January February March April May June July August September October November December'.split()


def overlay(rgb, lab):
    out = rgb.astype(np.float32)
    p, i = lab == 1, lab == 255
    out[p] = MAGENTA
    out[i] = 0.45 * out[i] + 0.55 * GREY
    return out.astype(np.uint8)


def words_day(d):
    y, m, dd = d.split('-')
    return f'{int(dd)} {MONTHS[int(m) - 1]} {y}'


def pick(rows, n):
    if not rows:
        return []
    idx = [round(k * (len(rows) - 1) / (n - 1)) for k in range(n)] if n > 1 else [len(rows) // 2]
    return [rows[i] for i in idx]


def text_block(lines, width, size=30):
    font = ImageFont.truetype(FONT, size)
    h = (size + 12) * len(lines) + 12
    im = Image.new('RGB', (width, h), 'white')
    d = ImageDraw.Draw(im)
    for k, s in enumerate(lines):
        d.text((16, 10 + k * (size + 12)), s, fill='black', font=font)
    return np.asarray(im)


def render(p, trays, data, labels, out, title):
    bgr = cv2.imread(f"{data}/{p['jpg']}")
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    del bgr
    lab = cv2.imread(f"{labels}/{p['mask']}", cv2.IMREAD_UNCHANGED)
    H, W = lab.shape
    s = 1400 / W
    small = cv2.resize(overlay(cv2.resize(rgb, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), cv2.resize(lab, None, fx=s, fy=s, interpolation=cv2.INTER_NEAREST)), None, fx=1, fy=1)
    small = np.ascontiguousarray(small)
    crops, caps = [], []
    for t in trays:
        o = np.asarray(json.loads(t['outline']))
        x0, y0 = np.clip(np.floor(o.min(0)).astype(int), 0, [W, H])
        x1, y1 = np.clip(np.ceil(o.max(0)).astype(int) + 1, 0, [W, H])
        cv2.polylines(small, [np.round(o * s).astype(np.int32).reshape(-1, 1, 2)], True, (255, 220, 0), 4)
        cx, cy = (o.mean(0) * s).astype(int)
        name = f"tray {t['tray_id']}" if t['tray_id'] else 'tray, no tag'
        cv2.putText(small, name, (int(cx) - 50, int(cy)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 220, 0), 2)
        c = overlay(rgb[y0:y1, x0:x1], lab[y0:y1, x0:x1])
        k = 690 / c.shape[1]
        crops.append(cv2.resize(c, None, fx=k, fy=k, interpolation=cv2.INTER_AREA))
        rule = t.get('label_rule', '')
        caps.append(f"{name}: {int(t['final_plant_px']):,} plant pixels" if rule.startswith('grow') else f"{name}: {rule.split(' (')[0]}, every pixel")
    del rgb, lab
    col = []
    for c, cap in zip(crops, caps):
        col += [text_block([cap], 700, 24), np.pad(c, ((0, 0), (5, 700 - 5 - c.shape[1]), (0, 0)), constant_values=255)]
    right = np.vstack(col) if col else np.full((10, 700, 3), 255, np.uint8)
    hh = max(small.shape[0], right.shape[0])
    body = np.hstack([np.pad(small, ((0, hh - small.shape[0]), (0, 0), (0, 0)), constant_values=255),
                      np.full((hh, 20, 3), 255, np.uint8),
                      np.pad(right, ((0, hh - right.shape[0]), (0, 0), (0, 0)), constant_values=255)])
    share = float(p['plant_share_in_trays'] or 0)
    head = [title,
            f"{p['rig'].capitalize()} rig, {words_day(p['day_utc'])}, {p['utc_time'][11:16]} UTC, experiment {p['experiment_id']}, photo {p['capture_id']}",
            f"{p['trays']} trays labelled. Plant: {share * 100:.2f}% of the pixels inside trays ({int(p['px_plant']):,} pixels)",
            "Magenta fill: plant.  Grey: ignore (outside every tray, and tray 8).  No fill: not plant.  Yellow outline: the two trays shown on the right."]
    sheet = np.vstack([text_block(head, body.shape[1]), body])
    Image.fromarray(sheet).save(out, optimize=True)


def main(data, labels, results, outdir):
    os.makedirs(outdir, exist_ok=True)
    done = list(csv.DictReader(open(f'{results}/labels_done.csv')))
    meta = {(r['rig'], r['capture_id']): r for r in csv.DictReader(open(f'{results}/labels_photos.csv'))}
    for r in done:
        r['jpg'] = meta[(r['rig'], r['capture_id'])]['jpg']
    trays = defaultdict(list)
    for t in csv.DictReader(open(f'{results}/labels_trays.csv')):
        trays[(t['rig'], t['capture_id'])].append(t)
    done.sort(key=lambda r: (r['rig'], r['utc_time']))
    prod = [r for r in done if r['rig'] == 'production' and r['label_kind'] == 'grow']
    neg = [r for r in done if r['label_kind'] == 'negative']
    dev = [r for r in done if r['rig'] == 'development' and 'spread' in r['sets']]
    chosen = [(r, 'Check') for r in pick(prod, 7) + pick(neg, 1) + pick(dev, 4)]
    most = max(done, key=lambda r: int(r['px_plant']))

    mats = next(r for r in sorted(prod, key=lambda r: -int(r['px_plant'])) if r['day_utc'] >= '2026-11-06' and r['day_utc'] <= '2026-11-16' and r is not most)

    def t8(r):
        return max([int(t['plant_px']) for t in trays[(r['rig'], r['capture_id'])] if t['tray_id'] == '8'] or [0])
    syn = max(prod, key=t8)
    chosen += [(most, 'The photo with the most plant pixels'), (mats, 'Blue mats: the most plant pixels from 6 to 16 November after it'),
               (syn, 'Tray 8, the synthetic plant: labelled ignore (Aaron, 2026-11-20)')]
    index = []
    for k, (r, why) in enumerate(chosen, 1):
        ts = sorted(trays[(r['rig'], r['capture_id'])], key=lambda t: -int(t['final_plant_px']))
        show = ts[:2]
        if r is syn:
            show = [t for t in ts if t['tray_id'] == '8'] + [t for t in ts if t['tray_id'] == '7']
        name = f'labels-{k:02d}.png'
        title = f'{k} of {len(chosen)}. ' + (why if why != 'Check' else 'Labelled photo')
        render(r, show, data, labels, f'{outdir}/{name}', title)
        index.append(dict(n=k, file=name, why=why, rig=r['rig'], capture_id=r['capture_id'], day_utc=r['day_utc'],
                          trays_shown=' '.join(t['tray_id'] or 'none' for t in show)))
        print(name, r['rig'], r['capture_id'], r['day_utc'], why, flush=True)
    with open(f'{results}/check_sheet_index.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(index[0]))
        w.writeheader()
        w.writerows(index)


if __name__ == '__main__':
    main(*sys.argv[1:5])
