import json, urllib.request
H='http://10.248.49.137:8000'
def get(u): return json.load(urllib.request.urlopen(H+u, timeout=120))
caps=[p for p in get('/api/captures?experiment_id=1&limit=200') if p['record']['experiment_id']==1]
caps.sort(key=lambda p:p['timestamp'])
def run(ts):
    t=ts[11:19]
    if '12:38:08'<=t<='12:44:08': return 1
    if '12:47:08'<=t<='12:59:08': return 2
    if '13:02:08'<=t<='13:59:59': return 3
rows=[]
for p in caps:
    r=run(p['timestamp'])
    if not r: continue
    d=get('/api/captures/trays/'+p['path'])
    for t in d['trays']:
        if t['found']=='tag only' or 'cells' not in t: continue
        u=t['uncertainty']; c3=[c for c in t['cells'] if c['cell']=='C3'][0]
        rows.append(dict(run=r,time=p['timestamp'][11:19],tray=t['tray_id'],slot=u['slot'],band=u['band_pct'],reason=u['reason'],
            c3=c3['area_mm2'],g3=c3['grown_area_mm2'],g3_status=c3['grown_status'],g3_over=c3['grown_over_other_cells'],tray_grown=t.get('grown_area_mm2'),grown_method=t.get('grown_method'),c3_status=c3['status'],tray_area=t['area_mm2'],warnings=t.get('warnings'),outside=t.get('outside_mm'),flag=c3['flagged'],other=[(c['cell'],c['area_mm2']) for c in t['cells'] if c['area_mm2'] and c['cell']!='C3']))
json.dump(rows,open('rows78g.json','w'))
print(len(caps),'stills in experiment;',len(rows),'tray readings')
