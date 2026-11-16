"""Score light-ramp rules for #382 on both rigs. Read-only inputs; prints tables, writes scored CSVs."""
import bisect, csv, collections, datetime as dt, json, statistics as st, sys
sys.path.insert(0, '/home/pi/npec_camera_rig/src')
from npec_rig.exclusions import light_exclusions  # pure function, no database access

S = '/home/pi/scratch/382-light-norm'
T = '/home/pi/.claude/jobs/e705fff3/tmp'
DARK = 200_000
P = dt.datetime.fromisoformat


def load(rig, tagfile):
    caps = list(csv.DictReader(open(f'{S}/abc_{rig}_captures.csv')))
    for x in caps:
        x['E'] = float(x['exposure_us']) * float(x['analogue_gain']); x['t'] = P(x['taken_at'])
    tags = collections.defaultdict(list)
    for r in csv.DictReader(open(tagfile)):
        tags[r['id']].append(r)
    return caps, tags


def truth(caps, tags, half=dt.timedelta(hours=6)):
    lit = [x for x in caps if x['E'] < DARK and x['id'] in tags]
    for x in lit:
        x['F'] = float(tags[x['id']][0]['frame_G_lin']) / x['E']
    ts = [x['t'] for x in lit]
    for i, x in enumerate(lit):
        a, b = bisect.bisect_left(ts, x['t'] - half), bisect.bisect_right(ts, x['t'] + half)
        x['L'] = x['F'] / st.median(y['F'] for y in lit[a:b])


def rule_current(caps):
    names = light_exclusions([{'taken_at': x['taken_at'], 'exposure_us': float(x['exposure_us']),
                               'analogue_gain': float(x['analogue_gain'])} for x in caps])['exclusions']
    for x, n in zip(caps, names):
        x['cur_name'] = n
        x['cur'] = n is not None and n != 'lights off'


def rule_A(caps, tags, frac=0.85):
    t0 = caps[0]['t']; dark = [x['t'] for x in caps if x['E'] >= DARK]
    def near(t):
        i = bisect.bisect_left(dark, t)
        return any(abs(dark[j] - t) <= dt.timedelta(minutes=60) for j in (i - 1, i) if 0 <= j < len(dark))
    ref = collections.defaultdict(list)
    for x in caps:
        if x['E'] < DARK and x['id'] in tags and x['t'] < t0 + dt.timedelta(hours=24) and not near(x['t']):
            for r in tags[x['id']]:
                if r['tag'] != '-1': ref[r['tag']].append(float(r['white_in_G_lin']) / x['E'])
    ref = {k: st.median(v) for k, v in ref.items()}
    for x in caps:
        if x['E'] >= DARK or x['id'] not in tags: x['Aidx'] = None; continue
        v = [float(r['white_in_G_lin']) / x['E'] / ref[r['tag']] for r in tags[x['id']] if r['tag'] in ref]
        x['Aidx'] = st.median(v) if v else None
        x['A'] = x['Aidx'] is None or x['Aidx'] < frac
    return ref


def rule_B(caps, k):
    lit = [x for x in caps if x['E'] < DARK]
    d = [0]
    for p, q in zip(lit, lit[1:]):
        gap = (q['t'] - p['t']).total_seconds()
        d.append(0 if gap > 150 or q['E'] == p['E'] else (1 if q['E'] > p['E'] else -1))
    flag = [False] * len(lit); i = 0
    while i < len(lit):
        j = i
        if d[i] != 0:
            while j + 1 < len(lit) and d[j + 1] == d[i]: j += 1
            if j - i + 1 >= k:
                for m in range(i - 1 if i else 0, j + 1): flag[m] = True
        i = j + 1
    for x, f in zip(lit, flag): x[f'B{k}'] = f


def rule_C(caps, n):
    dark = [x['t'] for x in caps if x['E'] >= DARK]
    for x in caps:
        if x['E'] >= DARK: continue
        i = bisect.bisect_left(dark, x['t'])
        x[f'C{n}'] = any(abs(dark[j] - x['t']) <= dt.timedelta(minutes=n) for j in (i - 1, i) if 0 <= j < len(dark))


def score(caps, key, thr=0.10):
    ev = [x for x in caps if x['E'] < DARK and 'L' in x]
    ramp = [x for x in ev if abs(x['L'] - 1) > thr]
    steady = [x for x in ev if abs(x['L'] - 1) <= thr]
    miss = [x for x in ramp if not x.get(key)]
    false = [x for x in steady if x.get(key)]
    worst = min((x['L'] for x in miss), default=None)
    lit = [x for x in caps if x['E'] < DARK]
    return dict(rule=key, scored=len(ev), ramp=len(ramp), missed=len(miss),
                worst_missed=None if worst is None else round(worst, 2),
                false=len(false), steady=len(steady), flagged_all=sum(bool(x.get(key)) for x in lit), lit_all=len(lit),
                miss_list=miss, false_list=false)


if __name__ == '__main__':
    out = {}
    import os
    for rig, tagfile in [(r, f'{T}/abc/{r}_tags.csv') for r in sys.argv[1:] or ('prod', 'dev')]:
        caps, tags = load(rig, tagfile)
        truth(caps, tags); rule_current(caps); ref = rule_A(caps, tags)
        for k in (3, 4, 5, 6, 8): rule_B(caps, k)
        for n in (20, 30, 35, 45, 60, 90): rule_C(caps, n)
        keys = ['cur', 'A', 'B3', 'B4', 'B5', 'B6', 'B8', 'C20', 'C30', 'C35', 'C45', 'C60', 'C90']
        print(f'\n{rig.upper()}  ramp truth: lit photo whose frame/E is >10% off its 12-hour median; A reference tags {ref}')
        print(f"{'rule':5} {'scored':>6} {'ramp':>5} {'missed':>6} {'worstL':>6} {'false':>5} {'of steady':>9} {'flagged/all lit':>16}")
        res = {}
        for k in keys:
            s = score(caps, k); res[k] = s
            print(f"{k:5} {s['scored']:6} {s['ramp']:5} {s['missed']:6} {str(s['worst_missed']):>6} {s['false']:5} {s['steady']:9} {s['flagged_all']:7}/{s['lit_all']}")
        out[rig] = (caps, res)
        with open(f'{S}/abc_{rig}_scored.csv', 'w') as f:
            cols = ['id', 'taken_at', 'E', 'L', 'Aidx', 'cur_name'] + keys
            w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore'); w.writeheader()
            for x in caps: w.writerow({c: x.get(c) for c in cols})
    json.dump({rig: {k: dict(miss=[(x['taken_at'][:16], round(x['L'], 3), x['E']) for x in s['miss_list']][:400],
                                false=[(x['taken_at'][:16], round(x['L'], 3), x['E']) for x in s['false_list']][:400])
                     for k, s in res.items()} for rig, (caps, res) in out.items()},
              open(f'{T}/abc/misses.json', 'w'), indent=0)
