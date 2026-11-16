"""#358: picture of when each plant tray got its mats on 2026-11-06 (from timeline.csv), for the
check-in. A tray counts as matted from the first photo with blue share above 0.5 and no glove."""
import csv, collections, sys
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

rows = list(csv.DictReader(open(sys.argv[1])))
mins = lambda t: int(t[:2]) * 60 + int(t[3:5])
PLANT = ['2', '1', '3', '6', '4', '5']
by = collections.defaultdict(list)
for r in rows:
    if r['tray'] in PLANT:
        by[r['tray']].append(r)
fig, ax = plt.subplots(figsize=(12, 4.2), dpi=110)
for band, (a, b, lab) in enumerate([('07:55', '08:02', 'lights off'), ('08:02', '08:30', 'lights coming on'), ('10:16', '10:21', 'trays moved')]):
    ax.axvspan(mins(a), mins(b), color='#d9d9d9', zorder=0)
    ax.text((mins(a) + mins(b)) / 2, len(PLANT) - 0.35, lab, ha='center', va='bottom', fontsize=9, color='#333')
ax.axvspan(mins('08:33'), mins('09:14'), color='#f1ece2', zorder=0)
ax.text((mins('08:33') + mins('09:14')) / 2, len(PLANT) - 0.35, 'person at the table (rig mark)', ha='center', va='bottom', fontsize=9, color='#333')
for i, tray in enumerate(PLANT):
    pts = sorted(by[tray], key=lambda r: r['t'])
    first_mat = next((r['t'] for r in pts if float(r['blue']) > 0.5), None)
    first_touch = next((r['t'] for r in pts if float(r['glove']) > 0.003 or 0.3 <= float(r['blue']) <= 0.5), first_mat)
    done = next((r['t'] for r in pts if r['t'] > first_mat and float(r['blue']) > 0.8 and float(r['glove']) == 0), first_mat)
    y = len(PLANT) - 1 - i
    x0 = mins('08:30')
    if mins(first_touch) > x0:
        ax.barh(y, mins(first_touch) - x0, left=x0, height=0.6, color='#8c6d4f')
        ax.text(x0 + 1, y, 'bare: before', va='center', fontsize=8, color='white')
    ax.barh(y, mins(done) - mins(first_touch) + 1, left=mins(first_touch), height=0.6, color='white', edgecolor='#333', hatch='///')
    ax.barh(y, mins('10:16') - mins('09:14'), left=mins('09:14'), height=0.6, color='#2b5fa8')
    ax.text(mins('09:14') + 1, y, 'matted: after', va='center', fontsize=8, color='white')
    ax.text(mins(done) + 2, y + 0.33, f'mats {first_touch} to {done}', fontsize=7.5, color='#333', va='bottom')
ax.set_yticks(range(len(PLANT)), [f'tray {t}' for t in reversed(PLANT)])
ticks = list(range(mins('08:00'), mins('10:31'), 15))
ax.set_xticks(ticks, [f'{t // 60:02d}:{t % 60:02d}' for t in ticks])
ax.set_xlim(mins('07:55'), mins('10:30')); ax.set_ylim(-0.6, len(PLANT) + 0.2)
ax.set_xlabel('2026-11-06, UTC (local = UTC + 1)')
for s in ('top', 'right'): ax.spines[s].set_visible(False)
ax.set_title('Plant trays of experiment 18: hatched = mats being laid', loc='left', fontsize=11)
fig.tight_layout(); fig.savefig(sys.argv[2])
