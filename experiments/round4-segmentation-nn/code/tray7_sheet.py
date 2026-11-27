"""#406 step 2: tray 7 of production experiment 18 for Aaron: 4 days and tray 1 for comparison. Per
row the photo, grow from leaf cores before any tray rule (green fill), and the label as saved
(green plant, grey ignore, nothing for not plant).
  tray7_sheet.py DATA DBDIR LABELS RESULTS OUT.png"""
import csv
import json
import sqlite3
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from npec_rig import images, segmentation

FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
MON = 'January February March April May June July August September October November December'.split()


def main(data, dbdir, labels, results, out):
    con = sqlite3.connect(f'file:{dbdir}/prod.db?mode=ro', uri=True)
    done = [r for r in csv.DictReader(open(f'{results}/labels_done.csv')) if r['rig'] == 'production' and r['experiment_id'] == '18']
    jpg = {r['capture_id']: r['jpg'] for r in csv.DictReader(open(f'{results}/labels_photos.csv')) if r['rig'] == 'production'}
    trays = {(r['capture_id'], r['tray_id']): r for r in csv.DictReader(open(f'{results}/labels_trays.csv')) if r['rig'] == 'production'}

    def pick(day, tid):
        c = [r for r in done if r['day_utc'] == day and (r['capture_id'], tid) in trays]
        return min(c, key=lambda r: abs(int(r['utc_time'][11:13]) - 12))
    rows = [(pick(d, '7'), '7') for d in ('2026-10-22', '2026-11-04', '2026-11-12', '2026-11-20')]
    rows.append((pick('2026-11-15', '1'), '1'))  # tray 1's last copied day
    font = ImageFont.truetype(FONT, 19)
    parts, CH = [], 268
    for p, tid in rows:
        t = trays[(p['capture_id'], tid)]
        o = json.loads(t['outline'])
        path = jpg[p['capture_id']].split('/', 1)[1][:-4]
        tags = json.loads(con.execute("select value from capture_analysis where kind='tags' and source=?", (path,)).fetchone()[0])
        rgb = images.decode_full(f"{data}/{jpg[p['capture_id']]}")
        mask, _ = segmentation.grow_trays(rgb, [(o, [g['corners'] for g in tags if g['tag_id'] == int(tid)])])
        lab = cv2.imread(f"{labels}/masks/production/{p['capture_id']}.png", cv2.IMREAD_UNCHANGED)
        a = np.asarray(o)
        H, W = mask.shape
        x0, y0 = np.clip(np.floor(a.min(0)).astype(int), 0, [W, H])
        x1, y1 = np.clip(np.ceil(a.max(0)).astype(int) + 1, 0, [W, H])
        crop = rgb[y0:y1, x0:x1].copy()
        m, lb = mask[y0:y1, x0:x1], lab[y0:y1, x0:x1]
        del rgb, lab
        ov = crop.astype(np.float32)
        ov[m] = 0.45 * ov[m] + 0.55 * np.array([0, 230, 0])
        nl = crop.astype(np.float32)
        nl[lb == 1] = 0.45 * nl[lb == 1] + 0.55 * np.array([0, 230, 0])
        nl[lb == 255] = 0.45 * nl[lb == 255] + 0.55 * np.array([128, 128, 128])
        k = CH / crop.shape[0]
        pa = [cv2.resize(x.astype(np.uint8), None, fx=k, fy=k, interpolation=cv2.INTER_AREA) for x in (crop, ov, nl)]
        gap = np.full((CH, 16, 3), 255, np.uint8)
        body = np.hstack([pa[0], gap, pa[1], gap, pa[2]])
        y, mo, d = p['day_utc'].split('-')
        name = 'tray 7' if tid == '7' else 'tray 1 (real potato plants), for comparison'
        txt = (f"{int(d)} {MON[int(mo) - 1]} {y}, {p['utc_time'][11:16]} UTC, {name}, plant pixels by grow from leaf "
               f"cores: {int(t['plant_px']):,}; in the label: {int(t['final_plant_px']):,}")
        hd = Image.new('RGB', (1450, 32), 'white')
        dr = ImageDraw.Draw(hd)
        dr.text((8, 5), txt, fill='black', font=font)
        assert dr.textlength(txt, font=font) < 1440, txt
        hd = np.asarray(hd)
        w = max(hd.shape[1], body.shape[1])
        pad = lambda x: np.pad(x, ((0, 0), (0, w - x.shape[1]), (0, 0)), constant_values=255)  # noqa: E731
        parts.append(np.vstack([pad(hd), pad(body), np.full((8, w, 3), 255, np.uint8)]))
    w = max(x.shape[1] for x in parts)
    img = np.vstack([np.pad(x, ((0, 0), (0, w - x.shape[1]), (0, 0)), constant_values=255) for x in parts])
    top = Image.new('RGB', (w, 60), 'white')
    ImageDraw.Draw(top).text((8, 5), 'Production, experiment 18. Left: the photo. Middle: grow from leaf cores before any tray rule.\n'
                             'Right: the label as saved (green plant, grey ignore, no fill not plant).', fill='black', font=font)
    Image.fromarray(np.vstack([np.asarray(top), img])).save(out, optimize=True)


if __name__ == '__main__':
    main(*sys.argv[1:6])
