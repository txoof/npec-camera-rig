"""Metrology log 29.3: the auto-exposure state against dark, ramp and steady photos.
Reads the development rig's rig.db read-only over ssh; prints a table per group and per hour.
Usage: python3 night.py EXPERIMENT_ID SINCE_UTC [UNTIL_UTC]"""
import collections, csv, io, subprocess, sys

exp, since = sys.argv[1], sys.argv[2]
until = sys.argv[3] if len(sys.argv) > 3 else '9999'
q = ("import sqlite3,csv,sys\n"
     "c=sqlite3.connect('file:/var/lib/npec-rig/rig.db?mode=ro',uri=True)\n"
     f"cur=c.execute(\"select id,taken_at,exposure_us,analogue_gain,ae_state from capture where experiment_id={int(exp)} and purpose='capture' order by taken_at\")\n"
     "w=csv.writer(sys.stdout);w.writerows(cur)\n")
out = subprocess.run(['ssh', 'pi@npec-rig-01', 'python3', '-'], input=q, capture_output=True, text=True, check=True).stdout
rows = [dict(zip(('id', 't', 'exp', 'gain', 'state'), r)) for r in csv.reader(io.StringIO(out))]
for r in rows: r['E'] = float(r['exp']) * float(r['gain'])
E = [r['E'] for r in rows]; n = len(rows)
N = [0 < i < n - 1 and (E[i - 1] < E[i] < E[i + 1] or E[i - 1] > E[i] > E[i + 1]) for i in range(n)]
pad = [N[i] or (i > 0 and N[i - 1]) or (i < n - 1 and N[i + 1]) for i in range(n)]
# dark: E equal to the highest E reached, held by the photo before or after
top = max(E)
dark = [E[i] == top and ((i > 0 and E[i - 1] == top) or (i < n - 1 and E[i + 1] == top)) for i in range(n)]
sel = [i for i, r in enumerate(rows) if since <= r['t'] < until and r['state'] not in ('', None)]
group = {i: 'dark' if dark[i] else 'ramp (N-pad)' if pad[i] else 'steady' for i in sel}
print(f'experiment {exp}, photos with a recorded state from {since} to {until}: {len(sel)}; highest E {top:.0f}')
tab = collections.Counter((group[i], rows[i]['state']) for i in sel)
for g in ('dark', 'ramp (N-pad)', 'steady'):
    tot = sum(v for (gg, _), v in tab.items() if gg == g)
    print(f'  {g:13} {tot:5}  ' + '  '.join(f'{s} {tab[(g, s)]}' for s in ('converged', 'searching', 'idle')))
print('steady photos not converged:', [(rows[i]['t'][5:16], rows[i]['state'], int(E[i])) for i in sel if group[i] == 'steady' and rows[i]['state'] != 'converged'][:40])
print('dark photos not searching:', [(rows[i]['t'][5:16], rows[i]['state'], int(E[i])) for i in sel if group[i] == 'dark' and rows[i]['state'] != 'searching'][:20])
print('per hour (UTC): converged/searching')
h = collections.defaultdict(collections.Counter)
for i in sel: h[rows[i]['t'][:13]][rows[i]['state']] += 1
print(' '.join(f"{k[5:]}:{v['converged']}/{v['searching']}" for k, v in sorted(h.items())))
