"""Tray 8 (benchmark) area by map, slot and A1 turn; turn checked from the benchmark's offset in the tray."""
import csv, json, sqlite3, statistics as st
from datetime import datetime, timedelta, timezone
from pathlib import Path
H = Path.home(); D = H/'scratch/223-area-jumps'; S = H/'wt/npec-223-area-jumps/experiments/round2-run/sessions'
maps = json.load(open(S/'shuffle-maps-2026-10-22.json'))['maps']
def utc(d, t):
    off = 2 if d < '2026-10-25' else 1
    return datetime.fromisoformat(f'{d}T{t}:00+00:00') - timedelta(hours=off)
rec = {int(r['shuffle']): r for r in csv.DictReader(open(S/'shuffle-record-2026-10-22.csv'))}
fin = {k: utc(r['date'], r['finish']) for k, r in rec.items()}
sta = {k: (utc(r['date'], r['start']) if r['start'] else fin[k] - timedelta(minutes=60)) for k, r in rec.items()}
lo = datetime(2000, 1, 1, tzinfo=timezone.utc); hi = datetime(2100, 1, 1, tzinfo=timezone.utc)
win = {k: ((lo if k == 0 else fin[k]), (sta[k+1] if k+1 in sta else hi)) for k in range(13)}
restart = {tuple(map(int, p)) for p in json.load(open(D/'restart_pairs.json'))}
ph = {}
for r in csv.DictReader(open(D/'a/tray_pairs_all.csv')):
    if r['tray'] != '8' or (int(r['before_id']), int(r['after_id'])) in restart: continue
    for s in ('before', 'after'):
        ph[int(r[s+'_id'])] = (datetime.fromisoformat(r[s+'_utc']), float(r[s+'_mm2']), r['slot'])
db = sqlite3.connect(f'file:{H}/scratch/223-shuffle-check/prod2/rig.db?mode=ro', uri=True)
cen = {c: (px-x, py-y) for c, x, y, px, py in db.execute(
    'select capture_id, centre_x_px, centre_y_px, plant_centre_x_px, plant_centre_y_px from tray_reading '
    'where tray_id=8 and plant_centre_x_px is not null')}
rows, unassigned = [], 0
per = {k: [] for k in range(13)}
for c, (t, a, slot) in ph.items():
    k = [k for k, (s, e) in win.items() if s <= t < e]
    if not k: unassigned += 1; continue
    per[k[0]].append((t, a, slot, cen.get(c)))
# reference direction: SW minus NE offset from maps 11 and 12 (turn confirmed there, metrology log 22.1)
def mo(k):
    o = [x[3] for x in per[k] if x[3]]; return (st.fmean(v[0] for v in o), st.fmean(v[1] for v in o))
plan = {k: next(v['a1'] for v in maps[k]['slots'].values() if v['tray'] == 8) for k in range(13)}
slotplan = {k: next(s for s, v in maps[k]['slots'].items() if v['tray'] == 8) for k in range(13)}
sg = lambda k: 1 if plan[k] == 'SW' else -1
ref = [sum(sg(k)*mo(k)[i] for k in (11, 12)) for i in (0, 1)]
for k in range(13):
    p = per[k]; a = [x[1] for x in p]; ox, oy = mo(k)
    proj = ox*ref[0] + oy*ref[1]
    rows.append({'map': k, 'from_utc': min(x[0] for x in p).strftime('%Y-%m-%d %H:%M'),
                 'to_utc': max(x[0] for x in p).strftime('%Y-%m-%d %H:%M'),
                 'slot': slotplan[k], 'slots_read': '/'.join(sorted({x[2] for x in p})), 'planned_turn': plan[k],
                 'offset_x_px': round(ox), 'offset_y_px': round(oy), 'turn_by_offset': 'SW' if proj > 0 else 'NE',
                 'agreed': 'yes' if (proj > 0) == (plan[k] == 'SW') else 'no',
                 'photos': len(p), 'mean_mm2': round(st.fmean(a), 1), 'sd_pct': round(100*st.pstdev(a)/st.fmean(a), 2)})
g = {}
for k in range(13):
    g.setdefault((slotplan[k], plan[k]), []).append(k)
grp = []
for (s, t), ks in sorted(g.items()):
    a = [x[1] for k in ks for x in per[k]]
    grp.append({'slot': s, 'turn': t, 'maps': ' '.join(map(str, ks)), 'photos': len(a),
                'mean_mm2': round(st.fmean(a), 1), 'sd_pct': round(100*st.pstdev(a)/st.fmean(a), 2)})
with open(D/'y/slot_turn.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, rows[0].keys()); w.writeheader(); w.writerows(rows)
with open(D/'y/slot_turn_grouped.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, grp[0].keys()); w.writeheader(); w.writerows(grp)
def tab(rs): return ('<table><tr>' + ''.join(f'<th>{h}</th>' for h in rs[0]) + '</tr>' +
                     ''.join('<tr>' + ''.join(f'<td>{v}</td>' for v in r.values()) + '</tr>' for r in rs) + '</table>')
html = f"""<!doctype html><meta charset=utf-8><title>Tray 8 slot and turn</title>
<style>body{{font:14px sans-serif;margin:16px;background:#fff;color:#111}}table{{border-collapse:collapse;margin:8px 0 24px}}td,th{{border:1px solid #999;padding:3px 7px;text-align:right}}</style>
<h1>Tray 8 (benchmark): area by map, slot and turn</h1>
<p>Production rig.db copy 2026-11-09 10:41 UTC, experiment 18. Undisturbed tray 8 photos (tray_pairs_all.csv minus restart_pairs.json), each photo once.
Map k from shuffle k finish to shuffle k+1 start. Times in the table: first and last photo used, UTC.
Offset: mean of plant_centre minus tray centre, full-size photo pixels (x right, y down).
Turn by offset: sign of the offset along the SW-minus-NE direction of maps 11 and 12 (turn confirmed there from cell readings, log 22.1); maps 11 and 12 agree by construction.
{unassigned} photos fell in no map window.</p>
<h2>Per map</h2>{tab(rows)}<h2>By slot and turn</h2>{tab(grp)}"""
(D/'y/slot_turn.html').write_text(html)
for r in rows: print(r)
for r in grp: print(r)
print('ref', ref, 'unassigned', unassigned)
