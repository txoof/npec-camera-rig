import json, sys
import numpy as np
from npec_rig.tray_placement import place_cells, TrayPlacement
from npec_rig.tags import TagDetection
from npec_rig.calibration import scale_field_from_dict
for rig, f in (('prod',sys.argv[1]+'/prod/readings.json'),('dev',sys.argv[1]+'/dev/readings.json')):
    d=json.load(open(f))['captures']
    for k,v in d.items():
        if not v['cells_stored']: continue
        import glob
        name=v['readings'][0]['calibration']; cal=json.load(open(glob.glob(sys.argv[1]+'/calibration/*'+name+'.json')+glob.glob('calibration-extra/*'+name+'.json')).__getitem__(0)) if False else json.load(open((glob.glob(sys.argv[1]+'/calibration/*'+name+'.json')+glob.glob('calibration-extra/*'+name+'.json'))[0]))
        sf=scale_field_from_dict(cal['scale_field'])
        tags={t['tag_id']:TagDetection(t['tag_id'],tuple(map(tuple,t['corners'])),tuple(t['centre'])) for t in v['tags']}
        errs=[]
        for r in v['readings']:
            if r['tray_id'] is None: continue
            p=TrayPlacement(r['tray_id'],(r['centre_x_px'],r['centre_y_px']),r['slot'],r['a1_corner'],r['tilt_deg'],tuple(map(tuple,r['outline'])),r['margin_mm'],'placed')
            cells=place_cells(p,tags[r['tray_id']],sf,a1_bearing_deg=r['a1_bearing_deg'])
            st={c['cell']:c for c in v['cells'] if c['tray_id']==r['tray_id']}
            for c in cells:
                s=st[c.name]; errs.append(np.abs(np.array(c.corners)-np.array(s['corners'])).max())
        print(rig, v['day'], 'max corner diff px', round(max(errs),2), 'median', round(float(np.median(errs)),2))
        break
