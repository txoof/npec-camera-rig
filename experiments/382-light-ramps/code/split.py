import csv, bisect, datetime as dt, sys
S='/home/pi/scratch/382-light-norm'; P=dt.datetime.fromisoformat
keys=['cur','A','B3','B5','B8','C30','C35','C45']
for rig in ('prod','dev'):
    r=list(csv.DictReader(open(f'{S}/abc_{rig}_scored.csv')))
    for x in r: x['t']=P(x['taken_at']); x['E']=float(x['E'])
    dark=[x['t'] for x in r if x['E']>=200000]
    def dmin(t):
        i=bisect.bisect_left(dark,t); return min([abs((dark[j]-t).total_seconds())/60 for j in (i-1,i) if 0<=j<len(dark)] or [1e9])
    ev=[x for x in r if x['E']<200000 and x['L'] not in ('',None)]
    for x in ev: x['L']=float(x['L']); x['dm']=dmin(x['t'])
    ramp=[x for x in ev if abs(x['L']-1)>0.10 and x['dm']<=40]
    deep=[x for x in ramp if x['L']<0.7]
    dip=[x for x in ev if abs(x['L']-1)>0.10 and x['dm']>40]
    day=[x for x in ev if x['dm']>40 and abs(x['L']-1)<=0.10]
    edge=[x for x in ev if x['dm']<=40 and abs(x['L']-1)<=0.10]
    lit=[x for x in r if x['E']<200000]
    litday=[x for x in lit if dmin(x['t'])>40]
    print(f"\n{rig.upper()}: ramp photos {len(ramp)} (light below 0.70: {len(deep)}), daytime dips {len(dip)}, steady daytime {len(day)}; all lit photos {len(lit)}, of them daytime {len(litday)}")
    print(f"{'rule':5} {'ramp missed':>11} {'missed <0.70':>12} {'lowest missed':>13} {'dips flagged':>12} {'steady day flagged':>18} {'ALL daytime lit flagged (E only)':>32}")
    on=lambda x,k: x.get(k)=='True'
    for k in keys:
        m=[x for x in ramp if not on(x,k)]
        print(f"{k:5} {len(m):11} {sum(x['L']<0.7 for x in m):12} {min((round(x['L'],2) for x in m),default='-'):>13} {sum(on(x,k) for x in dip):12} {sum(on(x,k) for x in day):18} {sum(on(x,k) for x in litday):32}")
    if rig=='prod':
        for k in ('B5','C30','cur','A'):
            print(k,'ramp misses:',[(x['taken_at'][5:16],round(x['L'],2),int(x['E'])) for x in ramp if not on(x,k)][:14])
