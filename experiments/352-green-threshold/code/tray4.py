"""#352: tray 4 on the 3 Nov still: photo, rule A, rule C; and greenness histograms of trays 4 and 6."""
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
Image.MAX_IMAGE_PIXELS = None
T = '/home/pi/scratch/thr-352/'; STEM = '2026-11-03_105853_597207'; V = '/home/pi/scratch/sam297/352-compare/'
cap = json.load(open(T + 'prod/db_readings.json'))['19380']
reads = {r['tray_id']: r for r in cap['readings'] if r['outline']}
rgb = np.asarray(Image.open(T + f'prod/{STEM}.jpg').convert('RGB'))
font = ImageFont.load_default(size=22)
o = np.array(json.loads(reads[4]['outline']))
x0, y0 = np.floor(o.min(0)).astype(int); x1, y1 = np.ceil(o.max(0)).astype(int)
sub = rgb[y0:y1, x0:x1]; r, g, b = (sub[..., i].astype(np.float32) for i in range(3))
exg = (2 * g - r - b) / (r + g + b + 1e-6)
pan = []
for name, m in (('photo', None), ('rule A, in use (0.1, G>R)', (exg > 0.1) & (g > r)), ('rule C (0, not blue)', (exg > 0) & ~((b > r) & (b > g)))):
    im = sub.copy()
    if m is not None:
        im[m] = (0.3 * im[m] + 0.7 * np.array([255, 0, 255])).astype(np.uint8)
    p = Image.fromarray(im).reduce(3); ImageDraw.Draw(p).text((10, 10), name, fill='white', font=font, stroke_width=3, stroke_fill='black')
    pan.append(p)
W = sum(p.width for p in pan) + 40
out = Image.new('RGB', (W, pan[0].height + 50), 'white'); x = 0
for p in pan:
    out.paste(p, (x, 0)); x += p.width + 20
ImageDraw.Draw(out).text((10, pan[0].height + 12), f'#352 tray 4, still {STEM} UTC, 1/3 size. Magenta: pixels the rule counts as plant.', fill='black', font=font)
out.save(V + 'tray4_rules.png')

# Histograms (from the #352 check: inside the tray outline, not blue, not white), log scale.
h = np.load(T + f'hist/{STEM}.npz'); bins = np.arange(-0.5, 0.5001, 0.01); ctr = (bins[:-1] + bins[1:]) / 2
sel = (ctr > -0.35) & (ctr < 0.25)
Wd, Hd, pad = 900, 300, 60
img = Image.new('RGB', (Wd + 2 * pad, 2 * (Hd + pad) + 70), 'white'); d = ImageDraw.Draw(img)
for i, t in enumerate(('4', '6')):
    v = np.log10(h[t][sel] + 1); c = ctr[sel]; top = pad + i * (Hd + pad)
    bw = Wd / len(v)
    for j, (cv, hv) in enumerate(zip(c, v)):
        hh = hv / v.max() * (Hd - 20)
        d.rectangle([pad + j * bw, top + Hd - hh, pad + (j + 1) * bw - 1, top + Hd], fill=(60, 130, 60) if cv > 0 else (140, 80, 60))
    for xv in (-0.3, -0.2, -0.1, 0, 0.1, 0.2):
        xp = pad + (xv - c[0] + 0.005) / 0.01 * bw
        d.line([xp, top + Hd, xp, top + Hd + 6], fill='black'); d.text((xp - 14, top + Hd + 8), f'{xv:+.1f}', fill='black', font=ImageFont.load_default(size=16))
    d.text((pad, top - 30), f'tray {t}: pixels per greenness step (log scale). Soil peak left; leaf peak right' + (' (the peak finder found none on tray 4)' if t == '4' else ''), fill='black', font=ImageFont.load_default(size=18))
d.text((pad, img.height - 34), 'Bars: brown below 0, green above 0. From the #352 check, 3 Nov 10:58 still; blue and white pixels left out.', fill='black', font=ImageFont.load_default(size=16))
img.save(V + 'tray4_vs_tray6_histogram.png')
print('ok')
