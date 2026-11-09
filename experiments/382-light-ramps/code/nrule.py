import csv, bisect, datetime as dt, collections
S='/home/pi/scratch/382-light-norm'; P=dt.datetime.fromisoformat
for rig in ('prod','dev'):
    r=list(csv.DictReader(open(f'{S}/abc_{rig}_scored.csv')))
    for x in r: x['t']=P(x['taken_at']); x['E']=float(x['E']); x['L']=float(x['L']) if x['L'] else None
    E=[x['E'] for x in r]; n=len(r)
    N=[0<i<n-1 and ((E[i-1]<E[i]<E[i+1]) or (E[i-1]>E[i]>E[i+1])) for i in range(n)]
    Npad=[N[i] or (i>0 and N[i-1]) or (i<n-1 and N[i+1]) for i in range(n)]
    Nany=[(i>0 and E[i]!=E[i-1]) or (i<n-1 and E[i]!=E[i+1]) for i in range(n)]
    rules={'C35':[x['C35']=='True' for x in r],'N':N,'N-pad':Npad,'N-any':Nany}
    dark=[x['t'] for x in r if x['E']>=200000]
    def dmin(t):
        i=bisect.bisect_left(dark,t); return min([abs((dark[j]-t).total_seconds())/60 for j in (i-1,i) if 0<=j<len(dark)] or [1e9])
    for x in r: x['dm']=dmin(x['t'])
    lit=[i for i,x in enumerate(r) if x['E']<200000]
    ev=[i for i in lit if r[i]['L'] is not None]
    ramp=[i for i in ev if abs(r[i]['L']-1)>0.10 and r[i]['dm']<=40]
    dip=[i for i in ev if abs(r[i]['L']-1)>0.10 and r[i]['dm']>40]
    litday=[i for i in lit if r[i]['dm']>40]
    days=sorted({r[i]['taken_at'][:10] for i in lit})[1:-1]  # full days only
    print(f"\n{rig.upper()}: ramp photos {len(ramp)}, daytime dips {len(dip)}, daytime lit photos {len(litday)}, full days {len(days)}")
    print(f"{'rule':6} {'ramp missed':>11} {'missed <0.70':>12} {'lowest missed':>13} {'dips flagged':>12} {'daytime discarded':>17} {'discards per full day (median, max)':>36}")
    for k,f in rules.items():
        m=[i for i in ramp if not f[i]]
        per=collections.Counter(r[i]['taken_at'][:10] for i in litday if f[i])
        pd=sorted(per.get(d,0) for d in days)
        print(f"{k:6} {len(m):11} {sum(r[i]['L']<0.7 for i in m):12} {min((round(r[i]['L'],2) for i in m),default='-'):>13} {sum(f[i] for i in dip):12} {sum(f[i] for i in litday):17} {str((pd[len(pd)//2],pd[-1])):>36}")
        if k in('N','N-pad'): print('   missed:',[(r[i]['taken_at'][5:16],round(r[i]['L'],2),int(E[i]),int(E[i-1]),int(E[i+1])) for i in m][:12])
