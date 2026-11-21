"""#406 step 2: list every copied full-size photo with its day, set, lit state, and whether it is
labelled for training and why not (README, step 2).
  select_photos.py DATA OUT.csv    (DATA = npec-406-nn/data/rigs)"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, '..', '..', 'round3-classifier', 'data', 'manifest.csv')
RIG_SHORT = {'production': 'prod', 'development': 'dev'}
SETS = {'production': ('reference', 'steadiness', 'spread', 'spread_extra', 'variety'),
        'development': ('spread', 'steadiness')}
DARK_BY_NOTES = {('production', '1620')}  # copy notes: experiment 16, 2026-10-21 01:53 UTC, dark


def test_days():
    days = {}
    for r in csv.DictReader(open(REF)):
        days.setdefault(r['rig'], {}).setdefault(r['day'], set()).add(r['split'])
    out = {}
    for rig, d in days.items():
        assert all(len(s) == 1 for s in d.values()), 'a day both train and test'
        out[rig] = sorted(k for k, s in d.items() if s == {'test'})
    return out


def main(data, out):
    tdays = test_days()
    print('test days', tdays)
    photos = {}
    for rig, sets in SETS.items():
        for s in sets:
            for r in csv.DictReader(open(f'{data}/{rig}/lists/{s}.tsv'), delimiter='\t'):
                key = (rig, r['capture_id'])
                p = photos.setdefault(key, dict(rig=rig, capture_id=r['capture_id'], utc_time=r['utc_time'],
                                                day_utc=r['utc_time'][:10], experiment_id=r['experiment_id'],
                                                path=r['path'], exclusion=r['exclusion'], sets=[]))
                assert p['exclusion'] == r['exclusion'] and p['utc_time'] == r['utc_time']
                p['sets'].append(s)
    rows = []
    for (rig, cid), p in sorted(photos.items(), key=lambda kv: (kv[0][0], kv[1]['utc_time'])):
        jpg = f"{data}/{rig}/{p['path']}.jpg"
        assert os.path.isfile(jpg), jpg
        why = []
        if p['day_utc'] in tdays.get(RIG_SHORT[rig], []):
            why.append('test day')
        if p['exclusion'] in ('lights off', 'light changing'):
            why.append(p['exclusion'])
        elif p['exclusion']:
            raise SystemExit(f'unknown exclusion {p["exclusion"]}')
        if (rig, cid) in DARK_BY_NOTES:
            why.append('dark (copy notes)')
        kind = 'negative' if rig == 'production' and int(p['experiment_id']) in range(9, 17) else 'grow'
        rows.append(dict(rig=rig, capture_id=cid, utc_time=p['utc_time'], day_utc=p['day_utc'],
                         experiment_id=p['experiment_id'], sets='+'.join(p['sets']), exclusion=p['exclusion'],
                         label_kind=kind, labelled='no' if why else 'yes', why_not='; '.join(why),
                         steadiness_flag='yes' if 'steadiness' in p['sets'] else '',
                         jpg=os.path.relpath(jpg, data)))
    with open(out, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    print(Counter((r['rig'], r['sets'], r['labelled'], r['why_not']) for r in rows))


if __name__ == '__main__':
    main(*sys.argv[1:3])
