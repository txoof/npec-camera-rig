"""#352: is a plant lost by rule F lost in every still, or only in some? Tray 3, 31 stills one a
minute, 2026-11-02 10:43:53 to 11:13:53 UTC, tray outline of the 10:58 still (capture 17940)."""
import json, glob, os, csv
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi
Image.MAX_IMAGE_PIXELS = None
T = '/home/pi/scratch/thr-352/'; S = T + 'seq-1102/'; V = '/home/pi/scratch/sam297/352-sequence/'; os.makedirs(V, exist_ok=True)
EIGHT = np.ones((3, 3), bool); TRAY = int(os.environ.get('TRAY', 3))
rd = {r['tray_id']: r for r in json.load(open(T + 'prod/db_readings.json'))['17940']['readings'] if r['outline']}[TRAY]
mm2 = rd['area_mm2'] / rd['plant_px']
o = np.array(json.loads(rd['outline']))
x0, y0 = np.floor(o.min(0)).astype(int); x1, y1 = np.ceil(o.max(0)).astype(int) + 1
pim = Image.new('L', (x1 - x0, y1 - y0), 0); ImageDraw.Draw(pim).polygon([(float(a - x0), float(c - y0)) for a, c in o], fill=1)
ins = np.asarray(pim).astype(bool)


def masks(sub):
    r, g, b = (sub[..., i].astype(np.float32) for i in range(3))
    exg = (2 * g - r - b) / (r + g + b + 1e-6); nb = ~((b > r) & (b > g))
    tag = ndi.maximum_filter(np.minimum(np.minimum(r, g), b) > 140, size=61)
    A = (exg > 0.1) & (g > r) & ~tag & ins; C = (exg > 0) & nb & ~tag & ins; E = (exg > -0.045) & nb & ~tag & ins
    lab, n = ndi.label(E, structure=EIGHT); keep = np.zeros(n + 1, bool); keep[np.unique(lab[A])] = True; keep[0] = False
    return dict(A=A, C=C, E=E, F=keep[lab]), exg


def load(j):
    return np.asarray(Image.open(j).convert('RGB'))[y0:y1, x0:x1]


jpgs = sorted(glob.glob(S + '*.jpg'))
ref = [j for j in jpgs if '105853' in j][0]
m0, _ = masks(load(ref))
# Plants on the reference still: rule C pieces of 150 px or more, joined within 15 px.
big = m0['C'] & (lambda l: np.bincount(l[0].ravel())[l[0]] >= 150)(ndi.label(m0['C'], structure=EIGHT))
reg, nreg = ndi.label(ndi.binary_dilation(big, iterations=15), structure=EIGHT)
cent = ndi.center_of_mass(np.ones_like(reg), reg, range(1, nreg + 1))
order = sorted(range(1, nreg + 1), key=lambda k: (round(cent[k - 1][0] / 400), cent[k - 1][1]))  # rows of cells, then left to right
print('plants found on the 10:58 still:', nreg)
rows = []
for j in jpgs:
    meta = json.load(open(j[:-4] + '.json')); sm = meta['sensor_metadata']
    m, exg = masks(load(j))
    for i, k in enumerate(order, 1):
        R = reg == k
        rows.append(dict(still=os.path.basename(j)[:13], plant=i, exposure_us=sm['ExposureTime'], gain=round(sm['AnalogueGain'], 3),
                         core_px=int((m['A'] & R).sum()), F_mm2=round((m['F'] & R).sum() * mm2, 2), C_mm2=round((m['C'] & R).sum() * mm2, 2),
                         E_mm2=round((m['E'] & R).sum() * mm2, 2), max_exg=round(float(exg[R & m['C']].max()) if (R & m['C']).any() else float('nan'), 4)))
with open(T + f'seq-1102_tray{TRAY}.csv', 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(f'{"plant":>5} {"stills with core":>16} {"core px min-max":>16} {"F mm2 min-mean-max":>22} {"C mm2 mean (sd)":>16} {"E mm2 mean":>10} {"max greenness":>14}')
for i in range(1, nreg + 1):
    rr = [r for r in rows if r['plant'] == i]
    cores = np.array([r['core_px'] for r in rr]); F = np.array([r['F_mm2'] for r in rr]); C = np.array([r['C_mm2'] for r in rr])
    E = np.array([r['E_mm2'] for r in rr]); mx = np.array([r['max_exg'] for r in rr])
    print(f'{i:5d} {int((cores > 0).sum()):>10d} of {len(rr)} {cores.min():>7d}-{cores.max():<7d} {F.min():7.1f}-{F.mean():6.1f}-{F.max():6.1f} {C.mean():9.1f} ({C.std(ddof=1):4.1f}) {E.mean():9.1f} {mx.min():6.3f}-{mx.max():.3f}')
ex = sorted({(r['still'], r['exposure_us'], r['gain']) for r in rows})
print('exposure us', min(e[1] for e in ex), 'to', max(e[1] for e in ex), 'gain', sorted({e[2] for e in ex}))
# Picture: the reference still, plants numbered.
im = Image.fromarray(load(ref)).reduce(2); d = ImageDraw.Draw(im); f = ImageFont.load_default(size=30)
for i, k in enumerate(order, 1):
    cy, cx = cent[k - 1]; d.text((cx / 2 + 30, cy / 2 - 40), str(i), fill='yellow', font=f, stroke_width=3, stroke_fill='black')
im.save(V + f'tray{TRAY}_plants_numbered.png')
