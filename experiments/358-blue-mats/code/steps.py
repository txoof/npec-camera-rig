"""#358, metrology log 36: each cell's plant area before and after its blue mat, 2026-11-06.

Reads production's own saved readings (read only, GET /api/captures/trays/<path>) after the
Reprocess of experiment 18 (#410), so both methods are the app's: the fixed green cutoff
(`area_mm2`) and grow from leaf cores (`grown_area_mm2`).

Windows (UTC, metrology log 36): before, from 08:30 to the tray's first mat, leaving out photos with
a glove over the tray (timeline.csv) and photos the rig marks "light changing"; after near, 09:14 to
09:27; after later, 10:21 to 10:50.

Drift: the mean per-minute change of a cell where nothing was done to it, from a straight line
through its photos in one window, pooled over cells (bare trays in their before windows; all trays
across the two after windows).

Usage: steps.py CAPS_JSON TIMELINE_CSV CACHE_DIR OUT_DIR"""
import csv, json, os, statistics as st, subprocess, sys
from collections import defaultdict

caps_json, timeline_csv, cache, out = sys.argv[1:5]
os.makedirs(cache, exist_ok=True); os.makedirs(out, exist_ok=True)
FIRST_MAT = {3: '08:34', 6: '08:42', 4: '08:48', 5: '08:59'}  # first touch, timeline.csv / log 36
TRAYS = [3, 6, 4, 5]
NEAR, LATER = ('09:14', '09:27'), ('10:21', '10:50')
METHODS = {'fixed': 'area_mm2', 'grown': 'grown_area_mm2'}

hand = {(r['t'][:5], int(r['tray'])) for r in csv.DictReader(open(timeline_csv))
        if r['tray'] and float(r['glove']) > 0.003}
caps = [c for c in json.load(open(caps_json)) if '08:30' <= c['timestamp'][11:16] <= '10:50']


def reading(c):
    f = os.path.join(cache, c['key'] + '.json')
    if not os.path.exists(f):
        subprocess.run(['curl', '-s', '-m90', '-o', f, 'ac-testing:8000/api/captures/trays/' + c['path']], check=True)
    return json.load(open(f))


def window(t, tray):
    if t < FIRST_MAT[tray]:
        return None if (t, tray) in hand else 'before'
    if NEAR[0] <= t <= NEAR[1]:
        return 'near'
    if LATER[0] <= t <= LATER[1]:
        return 'later'
    return None


rows, soil = [], []
for c in caps:
    t = c['timestamp'][11:16]
    r = reading(c)
    if not r or r.get('exclusion') == 'light changing':
        continue
    for tr in r['trays']:
        tid = tr['tray_id']
        if tid not in FIRST_MAT or not (w := window(t, tid)):
            continue
        soil.append(dict(t=t, tray=tid, window=w, soil=tr['grown_soil_level'], cutoff=tr['grown_lower_cutoff']))
        for cell in tr['cells'] or []:
            if cell['holds'] != 'plant':
                continue
            rows.append(dict(t=t, minute=int(t[:2]) * 60 + int(t[3:]), tray=tid, cell=cell['cell'], window=w,
                             fixed=cell['area_mm2'], grown=cell['grown_area_mm2'], exclusion=r.get('exclusion')))

with open(os.path.join(out, 'per_cell_photo.csv'), 'w', newline='') as fh:
    w = csv.DictWriter(fh, rows[0].keys()); w.writeheader(); w.writerows(rows)
with open(os.path.join(out, 'soil.csv'), 'w', newline='') as fh:
    w = csv.DictWriter(fh, soil[0].keys()); w.writeheader(); w.writerows(soil)

by = defaultdict(list)
for r in rows:
    by[(r['tray'], r['cell'], r['window'])].append(r)


def mean_sd(vals):
    vals = [v for v in vals if v is not None]
    if len(vals) < 2:
        return None, None, len(vals)
    m = st.mean(vals)
    return m, (st.stdev(vals) / m * 100 if m else None), len(vals)


def slope_pct(pts, key):
    """Per-minute change in % of the mean, least squares, or None."""
    pts = [(p['minute'], p[key]) for p in pts if p[key] is not None]
    if len(pts) < 3:
        return None
    mx = st.mean(x for x, _ in pts); my = st.mean(y for _, y in pts)
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    return None if not sxx or not my else sum((x - mx) * (y - my) for x, y in pts) / sxx / my * 100


cells = []
for tray in TRAYS:
    for name in sorted({k[1] for k in by if k[0] == tray}):
        row = dict(tray=tray, cell=name)
        for m, key in METHODS.items():
            b, n = [mean_sd(r[m] for r in by.get((tray, name, w), [])) for w in ('before', 'near', 'later')], None
            for w, (mean, sd, n) in zip(('before', 'near', 'later'), b):
                row[f'{m}_{w}'] = None if mean is None else round(mean, 2)
                row[f'{m}_{w}_sd_pct'] = None if sd is None else round(sd, 2)
                row[f'{m}_{w}_n'] = n
            for w in ('near', 'later'):
                bm, am = row[f'{m}_before'], row[f'{m}_{w}']
                row[f'{m}_change_{w}_pct'] = None if not bm or am is None else round((am / bm - 1) * 100, 2)
            # Mid-time of each window, for the drift times the elapsed minutes.
            for w in ('before', 'near'):
                ms = [r['minute'] for r in by.get((tray, name, w), [])]
                row[f'{w}_mid'] = round(st.mean(ms), 1) if ms else None
        cells.append(row)
with open(os.path.join(out, 'per_cell.csv'), 'w', newline='') as fh:
    w = csv.DictWriter(fh, cells[0].keys()); w.writeheader(); w.writerows(cells)

lines = []
for m, key in METHODS.items():
    bare = [s for k, v in by.items() if k[2] == 'before' and len(v) >= 5 if (s := slope_pct(v, m)) is not None]
    after = []
    for tray in TRAYS:
        for name in {k[1] for k in by if k[0] == tray}:
            s = slope_pct(by.get((tray, name, 'near'), []) + by.get((tray, name, "later"), []), m)
            if s is not None:
                after.append(s)
    lines.append(f'{m}: drift, bare cells in before windows (>= 5 photos): median {st.median(bare):+.3f} %/min, n {len(bare)}'
                 if bare else f'{m}: no bare drift')
    lines.append(f'{m}: drift, matted cells near to later: median {st.median(after):+.3f} %/min, n {len(after)}')
    for tray in TRAYS:
        cs = [c for c in cells if c['tray'] == tray and c[f'{m}_change_near_pct'] is not None]
        if not cs:
            lines.append(f'{m} tray {tray}: no cells'); continue
        ch = [c[f'{m}_change_near_pct'] for c in cs]; chl = [c[f'{m}_change_later_pct'] for c in cs if c[f'{m}_change_later_pct'] is not None]
        sdb = [c[f'{m}_before_sd_pct'] for c in cs if c[f'{m}_before_sd_pct'] is not None]
        sda = [c[f'{m}_near_sd_pct'] for c in cs if c[f'{m}_near_sd_pct'] is not None]
        gap = st.mean(c['near_mid'] - c['before_mid'] for c in cs if c['near_mid'] and c['before_mid'])
        pb = sum(c[f'{m}_before'] for c in cs); pa = sum(c[f'{m}_near'] for c in cs if c[f'{m}_near'] is not None)
        lines.append(f'{m} tray {tray}: cells {len(cs)}, change near median {st.median(ch):+.1f}% '
                     f'(range {min(ch):+.1f} to {max(ch):+.1f}), pooled {(pa / pb - 1) * 100:+.1f}%; later median '
                     f'{st.median(chl) if chl else float("nan"):+.1f}%; photo sd median before {st.median(sdb) if sdb else float("nan"):.2f}% '
                     f'after {st.median(sda) if sda else float("nan"):.2f}%; minutes between windows {gap:.0f}; '
                     f'photos before {cs[0][f"{m}_before_n"]}, near {cs[0][f"{m}_near_n"]}, later {cs[0][f"{m}_later_n"]}')
sl = defaultdict(list)
for s in soil:
    sl[(s['tray'], s['window'])].append(s)
for (tray, w), v in sorted(sl.items()):
    sv = [x['soil'] for x in v if x['soil'] is not None]; cv = [x['cutoff'] for x in v if x['cutoff'] is not None]
    lines.append(f'soil tray {tray} {w}: level median {st.median(sv) if sv else float("nan"):+.3f}, lower cutoff median '
                 f'{st.median(cv) if cv else float("nan"):+.3f}, photos {len(v)}')
open(os.path.join(out, 'summary.txt'), 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
