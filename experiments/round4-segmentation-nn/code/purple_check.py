"""#406, log 44 step 3: find other training truth cells where reddish or purple tissue touching a leaf is
marked NOT plant, as the stalk of B21 was (Aaron, 2026-11-21: purple anthocyanin tissue is plant).

  purple_check.py REF OUT_DIR [--explore]

REF is analysis/labels/ref on the work machine (the 42 staged TRAINING cells: crops/<name>.png and
truth/<name>_truth.png, >0 = plant). Nothing in REF is written; the script checks the SHA256 of every truth
before and after. OUT_DIR gets purple_check.png, purple_check.md and purple_check.csv.

The rule, per training cell (thresholds fixed before looking at the result list, set from B21 only):

1. Colour per pixel. The crop is median-filtered 5 x 5 (to calm JPEG noise), converted to CIE L*a*b*
   (OpenCV 8-bit), and each pixel gets its hue angle h = atan2(b*, a*) in degrees and its chroma
   C = sqrt(a*^2 + b*^2). The angle is written signed, s = ((h + 30) mod 360) - 30, so purple to magenta
   is about -30 to 0, red about 0 to 40, orange-brown soil 25 to 80, the blue mats about -55.
2. Soil reference of the cell. The median s of the not-plant pixels more than 15 px from any plant
   pixel, not strongly blue (B > R + 20 and B > G + 20, as drafts402.BLUE_MARGIN) and with s from -35
   to 120 (so a blue mat that is not strongly blue is left out too). If fewer than 500 such pixels
   exist (cells covered by a blue mat), the reference is 30 degrees: the production brown soil, whose
   reference lies at 24 to 40 degrees in the 12 production cells without a mat.
3. A pixel is "reddish or purple, not soil-coloured" when all of:
   - it is NOT plant in the truth;
   - it is not strongly blue (rule of 2);
   - C >= 5 (a colour, not grey or black);
   - s from -35 to 40 (purple, magenta or red; excludes the blue mats at about -55 and the orange to
     yellow-brown of the pale development soil, 50 to 80);
   - s <= soil reference - 5 degrees (redder or more purple than this cell's own soil). B21: stalk 35
     degrees, its soil 41, the soil seen in its other holes 45 to 56;
   - it lies in a hole of the truth (a not-plant region, 4 neighbours, that does not reach the crop edge,
     so it is closed by plant on every side) or within 8 px of a plant pixel.
4. Spots. Connected pieces (8 neighbours) of the pixels of 3. A spot is kept when it touches plant (one
   of its pixels is at most 2 px from a plant pixel) and holds at least 30 px.
5. Near misses, shown only if no spot is found: the same pieces with the -5 degree margin of 3 relaxed to
   +5 degrees, at least 30 px, ranked by how far their median s lies above (soil reference - 5).

What it does not do: it does not decide that a spot is plant; Aaron decides from the picture. It finds
only reddish or purple tissue next to a leaf; purple tissue far from any leaf, or purple tissue the
truth already marks plant, is not looked for. The 5 degree margin is set from one cell (B21).
"""
import csv
import hashlib
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

BLUR = 5
FAR_PX = 15
MIN_SOIL_PX = 500
BLUE_MARGIN = 20
MIN_CHROMA = 5.0
MIN_S = -35.0
MAX_S = 40.0
SOIL_BAND = (-35.0, 120.0)
SOIL_DEFAULT = 30.0
SOIL_MARGIN = 5.0
NEAR_PX = 8
TOUCH_PX = 2
MIN_SPOT = 30
NEAR_MISS_MARGIN = 5.0  # step 5: margin relaxed from -5 to +5
MAX_ROWS = 15
DECIDED_CELL = 'B21'      # the stalk decided on 2026-11-21: the hole of 896 px at x 33 to 59, y 162 to 215
DECIDED_PIXEL = (45, 190)  # (x, y) inside that hole
DECIDED_HOLE_PX = 896

MAGENTA = (255, 0, 255)
YELLOW = (255, 220, 0)
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONTB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def colour(rgb):
    lab = cv2.cvtColor(cv2.medianBlur(rgb, BLUR), cv2.COLOR_RGB2LAB).astype(np.float64)
    a, b = lab[..., 1] - 128, lab[..., 2] - 128
    h = np.degrees(np.arctan2(b, a)) % 360
    s = ((h + 30) % 360) - 30
    return s, np.hypot(a, b)


def find(rgb, truth, margin):
    """Spots of one cell. Returns (soil reference, list of dicts)."""
    plant = truth
    notp = ~plant
    s, C = colour(rgb)
    r, g, b = (rgb[..., k].astype(int) for k in range(3))
    blue = (b > r + BLUE_MARGIN) & (b > g + BLUE_MARGIN)
    d = ndi.distance_transform_edt(notp)
    far = notp & (d > FAR_PX) & ~blue & (s >= SOIL_BAND[0]) & (s <= SOIL_BAND[1])
    soil = float(np.median(s[far])) if far.sum() >= MIN_SOIL_PX else SOIL_DEFAULT
    lab4, _ = ndi.label(notp)
    edge = np.unique(np.r_[lab4[0], lab4[-1], lab4[:, 0], lab4[:, -1]])
    hole = notp & ~np.isin(lab4, edge)
    ok = notp & ~blue & (C >= MIN_CHROMA) & (s >= MIN_S) & (s <= MAX_S) & (s <= soil + margin) & (hole | (d <= NEAR_PX))
    pieces, n = ndi.label(ok, structure=np.ones((3, 3)))
    out = []
    for i, sl in enumerate(ndi.find_objects(pieces), start=1):
        m = pieces[sl] == i
        px = int(m.sum())
        if px < MIN_SPOT or d[sl][m].min() > TOUCH_PX:
            continue
        full = np.zeros_like(ok)
        full[sl] = m
        holes_hit = np.unique(lab4[full & hole])
        hole_px = int(np.isin(lab4, holes_hit[holes_hit > 0]).sum()) if holes_hit.size else 0
        rr, gg, bb = (int(np.median(rgb[..., k][full])) for k in range(3))
        out.append(dict(px=px, x0=sl[1].start, y0=sl[0].start, x1=sl[1].stop - 1, y1=sl[0].stop - 1,
                        mask=full, s=float(np.median(s[full])), in_hole=int((full & hole).sum()),
                        hole_px=hole_px, rgb=(rr, gg, bb)))
    return soil, out


def font(size, bold=False):
    return ImageFont.truetype(FONTB if bold else FONT, size)


def grey_label(rgb, truth):
    """The label as Aaron saw it: a grey copy of the photo, magenta (255,0,255) where the truth is plant."""
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    out = np.dstack([g, g, g])
    out[truth] = MAGENTA
    return out


def outline(mask):
    return mask & ~ndi.binary_erosion(mask, structure=np.ones((3, 3)), border_value=0)


def panel(img, box, ctx, scale, draw_box=True):
    """Crop the context window ctx=(x0,y0,x1,y1) of img, enlarge by scale (nearest), draw the yellow box."""
    x0, y0, x1, y1 = ctx
    p = Image.fromarray(np.ascontiguousarray(img[y0:y1, x0:x1])).resize(
        ((x1 - x0) * scale, (y1 - y0) * scale), Image.NEAREST)
    if draw_box:
        bx0, by0, bx1, by1 = box
        ImageDraw.Draw(p).rectangle([(bx0 - x0) * scale - 2, (by0 - y0) * scale - 2,
                                     (bx1 - x0 + 1) * scale + 1, (by1 - y0 + 1) * scale + 1],
                                    outline=YELLOW, width=4)
    return p


def closeup(rgb, spot, size):
    """The spot's box plus 6 px, enlarged to about size px; left plain, right with the spot outlined in yellow."""
    H, W = spot['mask'].shape
    x0, y0 = max(spot['x0'] - 6, 0), max(spot['y0'] - 6, 0)
    x1, y1 = min(spot['x1'] + 7, W), min(spot['y1'] + 7, H)
    k = max(2, min(12, size // max(x1 - x0, y1 - y0)))
    big = cv2.resize(rgb[y0:y1, x0:x1], ((x1 - x0) * k, (y1 - y0) * k), interpolation=cv2.INTER_NEAREST)
    m = cv2.resize(spot['mask'][y0:y1, x0:x1].astype(np.uint8), ((x1 - x0) * k, (y1 - y0) * k),
                   interpolation=cv2.INTER_NEAREST) > 0
    o = outline(m)
    o = ndi.binary_dilation(o, iterations=1)
    lined = big.copy()
    lined[o] = YELLOW
    return Image.fromarray(big), Image.fromarray(lined), k


def meta(name):
    rig, day, tray, cell = name.split('_')
    return ('production' if rig == 'prod' else 'development'), day, tray, cell


def sheet(rows, path, title_lines):
    PW = 384  # panel width
    pad, head = 16, 118
    blocks = []
    for r in rows:
        rgb, truth, sp = r['rgb_img'], r['truth_img'], r['spot']
        H, W = truth.shape
        cx, cy = (sp['x0'] + sp['x1']) // 2, (sp['y0'] + sp['y1']) // 2
        half = max(80, (max(sp['x1'] - sp['x0'], sp['y1'] - sp['y0']) + 1) // 2 + 30)
        x0, y0 = max(0, cx - half), max(0, cy - half)
        x1, y1 = min(W, x0 + 2 * half), min(H, y0 + 2 * half)
        x0, y0 = max(0, x1 - 2 * half), max(0, y1 - 2 * half)
        scale = max(1, PW // max(x1 - x0, y1 - y0))
        box = (sp['x0'], sp['y0'], sp['x1'], sp['y1'])
        p1 = panel(rgb, box, (x0, y0, x1, y1), scale)
        p2 = panel(grey_label(rgb, truth), box, (x0, y0, x1, y1), scale)
        c1, c2, k = closeup(rgb, sp, PW)
        rig, day, tray, cell = meta(r['name'])
        where = (f"It lies in a hole of {sp['hole_px']} px in your label, closed by plant on every side."
                 if sp['in_hole'] else "It lies at the edge of a leaf (touches plant, not closed in).")
        lines = [(f"{r['no']}.  Cell {r['id']} ({r['name']}): {rig} rig, photo of {day}, tray {tray}, cell {cell}.",
                  font(19, True)),
                 (f"Spot: {sp['px']} px marked NOT plant in your label.  {where}", font(17, True)),
                 (f"Spot box in the crop: x {sp['x0']} to {sp['x1']}, y {sp['y0']} to {sp['y1']}.  Median colour of "
                  f"the spot in the colour photo: RGB {sp['rgb']}.", font(16))]
        caps = [f"Colour photo, {scale}x, yellow box = spot",
                f"Your label, {scale}x: magenta = plant, grey = not plant",
                f"Colour photo inside the box, {k}x",
                f"Same, {k}x: yellow line = spot (NOT plant now)"]
        ph = max(p1.height, c1.height)
        blk = Image.new('RGB', (4 * PW + 5 * pad, head + ph + pad), 'white')
        dr = ImageDraw.Draw(blk)
        for i, (t, f) in enumerate(lines):
            dr.text((pad, 8 + 26 * i), t, fill='black', font=f)
        for j, p in enumerate((p1, p2, c1, c2)):
            dr.text((pad + j * (PW + pad), head - 24), caps[j], fill='black', font=font(14))
            blk.paste(p, (pad + j * (PW + pad), head))
        blocks.append(blk)
    W = 4 * PW + 5 * pad
    legend = Image.new('RGB', (W, 30 * len(title_lines) + 20), 'white')
    dr = ImageDraw.Draw(legend)
    for i, (t, bold) in enumerate(title_lines):
        dr.text((pad, 10 + 30 * i), t, fill='black', font=font(18 if bold else 17, bold))
    H = legend.height + sum(b.height for b in blocks)
    img = Image.new('RGB', (W, H), 'white')
    img.paste(legend, (0, 0))
    y = legend.height
    for b in blocks:
        img.paste(b, (0, y))
        ImageDraw.Draw(img).line([(0, y), (W, y)], fill=(160, 160, 160), width=2)
        y += b.height
    img.save(path)


LEGEND = [
    ("Training cells other than B21: spots marked NOT plant in your label that touch a leaf",
     True),
    ("and are reddish or purple in the colour photo, as the B21 stalk was.  Largest 15 shown.", True),
    ("Each row: panel 1 = the colour photo.  Panel 2 = your label: magenta (255,0,255) fill = plant;",
     False),
    ("grey copy of the photo with no fill = not plant.  B21 is left out (its stalk was decided on 2026-11-21).",
     False),
    ("Yellow box in panels 1 and 2 = the exact spot.  Panel 3 = the colour photo inside the yellow box,",
     False),
    ("enlarged.  Panel 4 = the same, with the spot outlined in yellow: inside the line = NOT plant in your label.",
     False),
    ("Question per spot: should it be plant?  Answer by the row number (all spots, with box coordinates:"
     " purple_check.md).", False),
]


def write_md(spots, b21, path):
    def row(x):
        sp = x['spot']
        rig, day, tray, cell = meta(x['name'])
        where = f"hole of {sp['hole_px']} px closed by plant" if sp['in_hole'] else 'edge of a leaf'
        return (f"| {x['no']} | {x['id']} | {x['name']} | {rig} | {day} | {tray} {cell} | {sp['px']} | "
                f"x {sp['x0']} to {sp['x1']}, y {sp['y0']} to {sp['y1']} | {where} | {sp['rgb']} | "
                f"{sp['s']:.0f} / {x['soil']:.0f} |")
    head = ("| No. | Cell | Crop file | Rig | Photo date | Tray, cell | Spot px | Spot box in the crop (px) | "
            "Where | Median colour in the colour photo, RGB | Spot hue / soil hue (degrees) |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|")
    cells = sorted({x['id'] for x in spots})
    L = ["# Purple or reddish spots marked NOT plant in the training truths (#406, log 44 step 3)", "",
         "Made by `experiments/round4-segmentation-nn/code/purple_check.py` (its docstring has the rule). No truth "
         "file was changed. Picture: `purple_check.png` (rows 1 to "
         f"{min(MAX_ROWS, len(spots))}, the largest spots).", "",
         "A spot is a piece of at least 30 px that your label marks NOT plant, that touches plant (or lies in a "
         "hole closed by plant), and whose colour in the colour photo is purple, magenta or red AND at least 5 "
         "degrees of hue redder or more purple than the soil of the same cell. Box coordinates are in pixels of "
         "the crop `analysis/labels/ref/crops/<crop file>.png`, x from the left, y from the top, both ends "
         "included.", "",
         f"**{len(spots)} spots in {len(cells)} cells** (not counting B21): {', '.join(cells)}. "
         f"Rows 1 to {min(MAX_ROWS, len(spots))} are in the picture; the rest are listed only.", "",
         "Question per spot: should it be plant? Answer by number.", "", head]
    L += [row(x) for x in spots]
    L += ["", "## B21, for completeness", "",
          "B21's stalk (the hole of 896 px) was decided on 2026-11-21. The rule finds it (rows marked *decided*: "
          "the rule takes only the pixels of the hole that pass the colour test, so their px is less than 896). "
          "B21's other spots are listed here, not in the picture.", "", head]
    L += [row(x).replace(f"| {x['no']} |", f"| {x['no']}{' (decided)' if x['decided'] else ''} |", 1) for x in b21]
    open(path, 'w').write('\n'.join(L) + '\n')


def main(ref, out, explore=False):
    rows = list(csv.DictReader(open(os.path.join(ref, 'manifest_train.csv'))))
    assert len(rows) == 42 and all(r['split'] == 'train' for r in rows)
    os.makedirs(out, exist_ok=True)
    truths = {r['id']: os.path.join(ref, 'truth', r['file'][:-4] + '_truth.png') for r in rows}
    before = {k: sha(v) for k, v in truths.items()}
    spots, misses, soils = [], [], {}
    for r in rows:
        name = r['file'][:-4]
        rgb = cv2.cvtColor(cv2.imread(os.path.join(ref, 'crops', name + '.png')), cv2.COLOR_BGR2RGB)
        truth = cv2.imread(truths[r['id']], cv2.IMREAD_GRAYSCALE) > 0
        if not truth.any():
            continue
        soil, found = find(rgb, truth, -SOIL_MARGIN)
        soils[r['id']] = soil
        for sp in found:
            spots.append(dict(id=r['id'], name=name, spot=sp, rgb_img=rgb, truth_img=truth, soil=soil))
        _, loose = find(rgb, truth, NEAR_MISS_MARGIN)
        for sp in loose:
            if sp['s'] > soil - SOIL_MARGIN:
                misses.append(dict(id=r['id'], name=name, spot=sp, rgb_img=rgb, truth_img=truth, soil=soil,
                                   above=sp['s'] - (soil - SOIL_MARGIN)))
        if explore:
            print(r['id'], name, f'soil {soil:.1f}', [(x['px'], round(x['s'], 1)) for x in found])
    b21 = sorted([x for x in spots if x['id'] == DECIDED_CELL], key=lambda x: -x['spot']['px'])
    spots = sorted([x for x in spots if x['id'] != DECIDED_CELL], key=lambda x: -x['spot']['px'])
    misses = [x for x in misses if x['id'] != DECIDED_CELL]
    for i, x in enumerate(spots, start=1):
        x['no'] = i
    for i, x in enumerate(b21, start=1):
        x['no'] = f'B21-{i}'
        x['decided'] = bool(x['spot']['mask'][DECIDED_PIXEL[1], DECIDED_PIXEL[0]] or
                            x['spot']['hole_px'] == DECIDED_HOLE_PX)
    with open(os.path.join(out, 'purple_check.csv'), 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['no', 'id', 'name', 'rig', 'day', 'tray', 'cell', 'px', 'x0', 'y0', 'x1', 'y1', 'in_hole_px',
                    'hole_px', 'median_rgb', 'spot_hue_deg', 'soil_hue_deg', 'shown'])
        for x in spots + b21:
            sp = x['spot']
            w.writerow([x['no'], x['id'], x['name'], *meta(x['name']), sp['px'], sp['x0'], sp['y0'], sp['x1'],
                        sp['y1'], sp['in_hole'], sp['hole_px'], ' '.join(map(str, sp['rgb'])), f"{sp['s']:.1f}",
                        f"{x['soil']:.1f}",
                        'yes' if isinstance(x['no'], int) and x['no'] <= MAX_ROWS else 'no'])
    write_md(spots, b21, os.path.join(out, 'purple_check.md'))
    if spots:
        sheet(spots[:MAX_ROWS], os.path.join(out, 'purple_check.png'), LEGEND)
    else:
        misses.sort(key=lambda x: x['above'])
        for i, x in enumerate(misses[:4], start=1):
            x['no'] = i
        sheet(misses[:4], os.path.join(out, 'purple_check.png'),
              [("NO spot passed the rule. These are the 4 nearest misses, to show what the rule looks at.", True)]
              + LEGEND[1:3])
    after = {k: sha(v) for k, v in truths.items()}
    assert after == before, 'a truth file changed'
    print('spots', len(spots), 'cells', sorted({x['id'] for x in spots}), 'near misses', len(misses))
    for x in spots:
        sp = x['spot']
        print(x['no'], x['id'], x['name'], sp['px'], (sp['x0'], sp['y0'], sp['x1'], sp['y1']), 'hole', sp['in_hole'],
              sp['hole_px'], 'rgb', sp['rgb'], f"s {sp['s']:.1f} soil {x['soil']:.1f}")
    return spots, misses


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], '--explore' in sys.argv)
