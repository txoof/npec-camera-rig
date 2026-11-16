import csv, statistics as st, collections, json
T='/home/pi/.claude/jobs/e705fff3/tmp'; S='/home/pi/scratch/382-light-norm'
def load(f):
    r=[x for x in csv.DictReader(open(f)) if x['tag']!='-1']
    for x in r:
        for k in list(x):
            if k not in('taken_at','set','id','tag'):
                x[k]=float(x[k]) if x[k] else None
    return r
def per_photo(rows, refday_fn):
    byp=collections.defaultdict(list)
    for x in rows: byp[x['id']].append(x)
    # per-tag reference: median of black/E and white/E over reference photos
    ref=collections.defaultdict(lambda: collections.defaultdict(list))
    for x in rows:
        if refday_fn(x):
            for m in ('black','white_in','outer'): ref[x['tag']][m].append(x[f'{m}_G_lin']/x['E'])
    refm={t:{m:st.median(v) for m,v in d.items()} for t,d in ref.items()}
    out=[]
    for pid,xs in byp.items():
        x0=xs[0]; rec=dict(id=pid,taken_at=x0['taken_at'],set=x0['set'],E=x0['E'],frame=x0['frame_G_lin']/x0['E'],ntags=len(xs))
        for m in ('black','white_in','outer'):
            v=[x[f'{m}_G_lin']/x['E']/refm[x['tag']][m] for x in xs if x['tag'] in refm]
            rec[m]=st.median(v) if v else None
            rec[m+'_spread']=(max(v)-min(v)) if len(v)>1 else None
        rec['white_Gclip']=st.median([x['white_in_Gclip'] for x in xs])
        rec['black_G']=st.median([x['black_G'] for x in xs])
        rec['tags']={x['tag']:round(x['black_G_lin']/x['E']/refm[x['tag']]['black'],3) for x in xs if x['tag'] in refm}
        out.append(rec)
    out.sort(key=lambda r:r['taken_at'])
    return out, refm
# production
prod,refp=per_photo(load(f'{T}/prod_tags.csv'), lambda x: x['taken_at']<'2026-10-23' and x['E']<6000 and x['set']=='sample')
earlier={x['id']:x for x in csv.DictReader(open(f'{S}/samples_raw.csv'))}
ln={x['taken_at'][:19]:x for x in csv.DictReader(open(f'{S}/light_norm_samples.csv'))}
for r in prod:
    e=ln.get(r['taken_at'][:19].replace('T',' '))
    r['strip']=float(e['light_strip']) if e else None; r['wall']=float(e['light_wall']) if e else None
fr=[r['frame'] for r in prod if r['taken_at']<'2026-10-23' and r['E']<6000]; f0=st.median(fr)
for r in prod: r['frame']/=f0
dev,refd=per_photo(load(f'{T}/dev_tags.csv'), lambda x: x['taken_at']<'2026-11-05' and x['E']<4000 and x['set']=='sample')
fr=[r['frame'] for r in dev if r['taken_at']<'2026-11-05' and r['E']<4000]; f0=st.median(fr)
for r in dev: r['frame']/=f0
json.dump({'prod':prod,'dev':dev},open(f'{T}/perphoto.json','w'),default=str)
def day_table(rows,daylit):
    d=collections.defaultdict(list)
    for r in rows:
        if r['set']=='sample' and daylit(r): d[r['taken_at'][:10]].append(r)
    print('day        n  E     black  white  outer  strip  wall   blackspread clipG')
    for k,v in sorted(d.items()):
        m=lambda key: st.median([x[key] for x in v if x.get(key) is not None]) if any(x.get(key) is not None for x in v) else float('nan')
        print(f"{k} {len(v):2d} {m('E'):5.0f} {m('black'):.3f}  {m('white_in'):.3f}  {m('outer'):.3f}  {m('strip'):.3f}  {m('wall'):.3f}  {m('black_spread'):.3f}       {m('white_Gclip'):.2f}")
print('PRODUCTION (daytime samples, E<6000)'); day_table(prod, lambda r:r['E']<6000)
print('reference tags', {t:round(v['black']*1e5,2) for t,v in refp.items()})
print('\nDEVELOPMENT (daytime samples, E<4000)'); day_table(dev, lambda r:r['E']<4000)
print('reference tags', {t:round(v['black']*1e5,2) for t,v in refd.items()})
for name,rows in (('PROD ramp 5 Nov',[r for r in prod if r['taken_at'].startswith('2026-11-05T00')]),('DEV ramp 5 Nov',[r for r in dev if r['taken_at'].startswith('2026-11-05T00')])):
    print('\n'+name); print('time   E       frame  black  white  ntags')
    for r in rows: print(r['taken_at'][11:16], f"{r['E']:7.0f}", f"{r['frame']:.3f}", f"{r['black']:.3f}" if r['black'] else '  -  ', f"{r['white_in']:.3f}" if r['white_in'] else '  -  ', r['ntags'])
