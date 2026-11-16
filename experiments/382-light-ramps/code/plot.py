import json, datetime as dt, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
d=json.load(open('perphoto.json'))
P=lambda s: dt.datetime.fromisoformat(s[:19])
fig,ax=plt.subplots(3,1,figsize=(13,13))
pr=[r for r in d['prod'] if r['set']=='sample' and r['E']<6000]
t=[P(r['taken_at']) for r in pr]
a=ax[0]
a.plot(t,[r['E']/5248 for r in pr],'k-',lw=1,label='Exposure (relative to 22 Oct)')
a.plot(t,[r['strip'] for r in pr],'o',ms=3,color='tab:green',label='White strip / exposure (earlier check)')
a.plot(t,[r['wall'] for r in pr],'s',ms=3,color='tab:olive',label='Back wall / exposure (earlier check)')
a.plot(t,[r['white_in'] for r in pr],'^',ms=4,color='red',label='Corner tags, white cells / exposure')
a.plot(t,[r['black'] for r in pr],'v',ms=4,color='magenta',label='Corner tags, black cells / exposure')
for x,l in (('2026-10-26T04:00','trays moved,\nwhite sheets added'),('2026-11-05T19:29','light warning\nstarts'),('2026-11-06T09:30','blue mats')):
    a.axvline(P(x),color='grey',ls='--'); a.text(P(x),1.17,l,fontsize=8)
a.axhspan(0.98,1.02,color='0.92'); a.set_ylim(0.72,1.22)
a.set_title('Production, experiment 18: light readings in daytime photos (1.00 = 22 Oct). Lamps unchanged.')
a.set_ylabel('relative to 22 Oct'); a.legend(fontsize=8,loc='lower left'); a.grid(alpha=.3)
dv=[r for r in d['dev'] if r['set']=='sample' and r['E']<4000]
t=[P(r['taken_at']) for r in dv]; a=ax[1]
a.plot(t,[r['E']/3741 for r in dv],'k-',lw=1,label='Exposure (relative to 3 Nov)')
a.plot(t,[r['white_in'] for r in dv],'^',ms=4,color='red',label='Corner tags, white cells / exposure')
a.plot(t,[r['black'] for r in dv],'v',ms=4,color='magenta',label='Corner tags, black cells / exposure (too dark to read)')
a.axhspan(0.98,1.02,color='0.92'); a.set_ylim(0.72,1.22)
a.set_title('Development, experiment 3: scene unchanged, exposure steady'); a.legend(fontsize=8,loc='lower left'); a.grid(alpha=.3)
a=ax[2]
for rows,mk,lab in ((d['prod'],'-',"production"),(d['dev'],'--',"development")):
    rr=[r for r in rows if r['taken_at'][:13] in('2026-11-05T00',) and r['E']<200000]
    m=[int(r['taken_at'][14:16]) for r in rr]
    f0=rr[0]['frame']; w0=rr[0]['white_in']
    a.plot(m,[r['frame']/f0 for r in rr],'k'+mk,label=f'{lab}: whole frame / exposure')
    a.plot(m,[r['white_in']/w0 for r in rr],'r'+mk,marker='^',ms=4,label=f'{lab}: corner tag white / exposure')
a.set_title('Lights dimming, 5 Nov 00:00 to 00:28 UTC: the tag reading falls with the real light on both rigs')
a.set_xlabel('minute after 00:00 UTC'); a.set_ylabel('relative to 00:00'); a.legend(fontsize=8); a.grid(alpha=.3)
fig.tight_layout(); fig.savefig('/home/pi/scratch/382-light-norm/corner_tag_check.png',dpi=90)
