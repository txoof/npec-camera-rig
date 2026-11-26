import json, urllib.request, cv2, numpy as np, sys
H='http://10.248.49.137:8000'
get=lambda u: json.load(urllib.request.urlopen(H+u,timeout=120))
caps=[p for p in get('/api/captures?experiment_id=1&limit=200') if p['record']['experiment_id']==1]
pick={'run1':'12:41:08','run3':'13:05:08'}
L={'North 1':'I','North 2':'A','North 3':'E','North 4':'K','North 5':'B','North 6':'F','South 1':'D','South 2':'J','South 3':'H','South 4':'C','South 5':'L','South 6':'G'}
size={'I':55,'A':10,'E':20,'K':40,'B':10,'F':'5?','D':20,'J':55,'H':20,'C':10,'L':40,'G':20}
rows=[]
for run,t in pick.items():
    p=[c for c in caps if c['timestamp'][11:19]==t][0]
    open('s.jpg','wb').write(urllib.request.urlopen(H+p['url'],timeout=180).read())
    im=cv2.imread('s.jpg')[:,:,::-1].astype(np.float32)
    d=get('/api/captures/trays/'+p['path']); slot_of={}
    for tr in d['trays']:
        if tr['found']=='tag only' or 'cells' not in tr: continue
        s=tr['uncertainty']['slot']; c=[c for c in tr['cells'] if c['cell']=='C3'][0]
        xs=[q[0] for q in c['corners_px']]; ys=[q[1] for q in c['corners_px']]
        cx,cy=sum(xs)/4,sum(ys)/4; h=int(max(max(xs)-min(xs),max(ys)-min(ys))*0.8)
        x0,y0=int(cx-h),int(cy-h); cr=im[y0:y0+2*h,x0:x0+2*h]
        r,g,b=cr[...,0],cr[...,1],cr[...,2]; exg=(2*g-r-b)/(r+g+b+1e-6)
        loose=((g>r)&(g>b)&(exg>0.03)).astype(np.uint8)
        n,lab,stt,cen=cv2.connectedComponentsWithStats(loose,8)
        best=max(range(1,n),key=lambda i: stt[i,4]-3*np.hypot(*(cen[i]-[h,h])) if stt[i,4]>100 else -1e9)
        piece=(lab==best).astype(np.uint8)
        core=cv2.erode(piece,np.ones((9,9),np.uint8))
        ring=cv2.dilate(piece,np.ones((61,61),np.uint8))-cv2.dilate(piece,np.ones((41,41),np.uint8))
        kept=int((piece&((exg>0.1)&(g>r))).sum())
        sq=np.median(exg[core>0]); bg=np.median(exg[ring>0]); jump=sq-bg
        rows.append(dict(run=run,slot=s,sq=L[s],mm=size[L[s]],tray=tr['tray_id'],exg_square=sq,exg_bg=bg,jump=jump,cut_pos=(0.1-bg)/(sq-bg),
            rgb_sq=[int(np.median(cr[...,i][core>0])) for i in range(3)],rgb_bg=[int(np.median(cr[...,i][ring>0])) for i in range(3)],square_px=int(piece.sum()),kept_pct=100*kept/int(piece.sum())))
json.dump(rows,open('jump78.json','w'),default=float)
order=[f'{a} {i}' for a in ('North','South') for i in range(1,7)]
print(f"{'slot':8}{'sq':3}{'mm':>3} | {'run':4} {'exg sq':>7} {'exg bg':>7} {'jump':>6} {'cut at':>7} | kept | rgb square | rgb background")
for s in order:
    for x in [r for r in rows if r['slot']==s]:
        print(f"{s:8}{x['sq']:3}{str(x['mm']):>3} | {x['run']:4} {x['exg_square']:7.3f} {x['exg_bg']:7.3f} {x['jump']:6.3f} {x['cut_pos']:7.2f} | {x['kept_pct']:4.0f}% | {x['rgb_sq']} | {x['rgb_bg']}")
