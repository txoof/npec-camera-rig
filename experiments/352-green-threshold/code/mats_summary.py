import csv, numpy as np, collections
rows = list(csv.DictReader(open('/home/pi/scratch/thr-352/mats/per_square_photo.csv')))
for r in rows:
    for k in ('cx', 'cy', 'size', 'calliper', 'current', 'zero_not_blue', 'grow'): r[k] = float(r[k])
def tracks(phase):
    tr = []
    for r in [x for x in rows if x['phase'] == phase]:
        for t in tr:
            if t['size'] == r['size'] and abs(t['cx'] - r['cx']) < 150 and abs(t['cy'] - r['cy']) < 150:
                t['r'].append(r); break
        else:
            tr.append(dict(size=r['size'], cx=r['cx'], cy=r['cy'], r=[r]))
    return [t for t in tr if len(t['r']) >= 10]
B, A = tracks('before'), tracks('after')
HEIGHT = 1 + 0.00145 * 1.5
K = ('current', 'zero_not_blue', 'grow')
print('squares', len(B), len(A))
res = collections.defaultdict(lambda: collections.defaultdict(list))
for t in B:
    a = min([a for a in A if a['size'] == t['size']], key=lambda a: (a['cx'] - t['cx']) ** 2 + (a['cy'] - t['cy']) ** 2)
    for k in K:
        b = np.mean([r[k] for r in t['r']]) / t['r'][0]['calliper']; af = np.mean([r[k] for r in a['r']]) / a['r'][0]['calliper'] / HEIGHT
        res[k][int(t['size'])].append((b, af))
print(f'{"rule":16s} {"size":>4} | {"before / calliper":>22} | {"after / calliper":>22} | change')
for k in K:
    for s in (10, 20, 40, 55):
        v = np.array(res[k][s]); b, af = v[:, 0], v[:, 1]
        print(f'{k:16s} {s:4d} | {b.mean():.3f} ({b.min():.3f} to {b.max():.3f}) | {af.mean():.3f} ({af.min():.3f} to {af.max():.3f}) | {100 * (af.mean() / b.mean() - 1):+5.1f}%')
print('\nphoto-to-photo sd (% of mean), median and max over the 12 squares')
for k in K:
    for ph, T in (('before', B), ('after', A)):
        sds = [100 * np.std([r[k] for r in t['r']], ddof=1) / np.mean([r[k] for r in t['r']]) for t in T]
        print(f'  {k:14s} {ph:6s} {np.median(sds):.2f}% (max {max(sds):.2f}%)')
