"""Metrology log 41: tray readings before and after the Reprocess, per tray. A reading is
"flagged" when, before, its soil level was in the top bin (>= 0.04) and its cutoff above the floor
(-0.045). A photo holding a flagged reading is grown again whole, so its other readings are
kind "same photo"; the rest are "other". Reports, per tray and kind, how many readings kept their areas within TOL mm2, how many
changed, and the median after/before ratio of the grown area. Only capture ids present before.

    compare.py before_tray.csv.gz after_tray.csv.gz
"""
import csv, gzip, statistics, sys
from collections import defaultdict

TOL = 0.01  # mm2; a decision (metrology log 41), not a measurement


def load(p):
    with gzip.open(p, 'rt') as f:
        return {(r['capture_id'], r['tray_id'], r['centre_x_px'], r['centre_y_px']): r for r in csv.DictReader(f)}


def num(v):
    return None if v in ('', None) else float(v)


def is_flagged(r):
    soil, cut = num(r['grown_soil_level']), num(r['grown_lower_cutoff'])
    return soil is not None and cut is not None and soil >= 0.04 - 1e-9 and cut > -0.045 + 1e-9


before, after = load(sys.argv[1]), load(sys.argv[2])
grown_photos = {k[0] for k, r in before.items() if is_flagged(r)}
out = defaultdict(lambda: {'n': 0, 'same': 0, 'changed': 0, 'missing': 0, 'ratios': [], 'marked': 0})
for key, b in before.items():
    kind = 'flagged' if is_flagged(b) else 'same photo' if key[0] in grown_photos else 'other'
    s = out[(b['tray_id'] or 'no tag', kind)]
    s['n'] += 1
    a = after.get(key)
    if a is None:
        s['missing'] += 1
        continue
    pairs = [(num(b[k]), num(a[k])) for k in ('area_mm2', 'grown_area_mm2')]
    same = all((x is None and y is None) or (x is not None and y is not None and abs(x - y) <= TOL)
               for x, y in pairs)
    s['same' if same else 'changed'] += 1
    gb, ga = pairs[1]
    if gb and ga is not None:
        s['ratios'].append(ga / gb)
    s['marked'] += 'soil hidden' in (a['warnings'] or '')
print('tray\tkind\treadings\tsame\tchanged\tmissing\tmedian_ratio\tmarked_soil_hidden')
for (tray, kind), s in sorted(out.items(), key=lambda kv: (kv[0][0].zfill(3), kv[0][1])):
    med = f"{statistics.median(s['ratios']):.3f}" if s['ratios'] else ''
    print(tray, kind, s['n'], s['same'], s['changed'], s['missing'], med, s['marked'], sep='\t')
