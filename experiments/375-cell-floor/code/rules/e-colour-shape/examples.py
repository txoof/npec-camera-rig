"""Draw one example: RGB | mask (magenta) + opening (red), with rule A's verdict.
Usage: examples.py NAME rig exp tray cell taken_at_prefix"""
import csv, json, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
K=['rig','experiment_id','tray_id','cell','taken_at_utc']
name,rig,exp,tray,cell,t=sys.argv[1:7]
idx=[r for r in csv.DictReader(open('../../data/index.csv')) if (r['rig'],r['experiment_id'],r['tray_id'],r['cell'])==(rig,exp,tray,cell) and r['taken_at_utc'].startswith(t)]
r=idx[0]; k=tuple(r[c] for c in K)
A={tuple(x[c] for c in K):x['verdict'] for x in csv.DictReader(open('results_A.csv'))}[k]
a=np.array(Image.open('../../data/'+r['rgb_png']).convert('RGB')); m=np.array(Image.open('../../data/'+r['mask_png']))>0
poly=np.array(json.loads(r['opening_polygon_crop_px'])); pad=int(0.12*(poly.max(0)-poly.min(0)).max())
x0,y0=np.maximum(poly.min(0).astype(int)-pad,0); x1,y1=poly.max(0).astype(int)+pad
a=a[y0:y1,x0:x1]; m=m[y0:y1,x0:x1]; poly=poly-[x0,y0]
o=a.copy(); o[m]=[255,0,255]
t1=Image.fromarray(a); t2=Image.fromarray(o); ImageDraw.Draw(t2).polygon([tuple(p) for p in poly],outline=(255,0,0),width=2)
W,H=t1.size; out=Image.new('RGB',(2*W+10,H+60),(255,255,255)); out.paste(t1,(0,60)); out.paste(t2,(W+10,60))
d=ImageDraw.Draw(out); font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',16)
d.text((6,4),f"{rig} exp{exp} tray {tray} {cell} day {r['day_since_grow_start']} {r['taken_at_utc'][:16]}Z  label: {r['label_contents']}, {r['label_outcome']}",fill=(0,0,0),font=font)
d.text((6,30),f"rule A verdict: {A.upper()}   mask px in opening {r['mask_px_in_opening']}",fill=(200,0,0),font=font)
out.save(f'examples/{name}.png'); print(name,out.size)
