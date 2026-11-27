"""Make the ImageJ crop pairs: one rig crop and one Helios crop per chosen plant.

No mask, area or ratio is written or drawn. Each crop gets a sidecar with its scale.
"""
import sqlite3, sys, json, os, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helios_grid import grid, TAG_MM, PITCH_SIDES

CELL_PITCH_MM = 69.7    # cell centre spacing (reference/trays.md)
CELL_OPENING_MM = 59.5  # cell opening, callipers (reference/trays.md)

DB = sys.argv[1]; HEL = sys.argv[2]; RIG = sys.argv[3]; OUT = sys.argv[4]
os.makedirs(OUT, exist_ok=True)

# tag -> (helios file, rig jpg, rig capture id), 12 November scan
PAIRS = {
 1: ('138_2_2026-11-12_11-34-14_PS_Tray_2688', '2026-11-12_101653_622476', 32300, 2688),
 2: ('138_2_2026-11-12_11-31-38_PS_Tray_2689', '2026-11-12_100153_637089', 32285, 2689),
 3: ('138_2_2026-11-12_11-36-34_PS_Tray_2690', '2026-11-12_101653_622476', 32300, 2690),
 4: ('138_2_2026-11-12_11-35-26_PS_Tray_2691', '2026-11-12_101653_622476', 32300, 2691),
 5: ('138_2_2026-11-12_11-29-50_PS_Tray_2692', '2026-11-12_100153_637089', 32285, 2692),
 6: ('138_2_2026-11-12_11-29-11_PS_Tray_2693', '2026-11-12_100153_637089', 32285, 2693),
 7: ('138_2_2026-11-12_11-40-10_PS_Tray_2694', '2026-11-12_101653_622476', 32300, 2694),
}
CHOSEN = [(t, 'C3') for t in range(1, 8)] + [(t, 'B2') for t in (1, 2, 3)]

c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
man = []
rig_cache = {}
for tag, cell in CHOSEN:
    hstem, rstem, cid, helios_tray = PAIRS[tag]
    # ---- Helios crop, from the tag's frame
    img, htag, cells, side, a, b = grid(f'{HEL}/{hstem}_RGB2_FishEyeCorrected.png')
    assert htag == tag, (htag, tag)
    cx, cy = cells[cell]
    half = 0.70 * PITCH_SIDES * side
    hx0, hy0 = int(cx - half), int(cy - half)
    hx1, hy1 = int(cx + half), int(cy + half)
    hc = img[max(0, hy0):hy1, max(0, hx0):hx1]
    hname = f'tag{tag}_{cell}_helios.png'
    cv2.imwrite(f'{OUT}/{hname}', hc)
    # ---- rig crop, from the app's own cell corners
    if rstem not in rig_cache:
        rig_cache[rstem] = cv2.imread(f'{RIG}/{rstem}.jpg')
    rimg = rig_cache[rstem]
    row = c.execute('select corners, area_mm2, plant_px, over_other_cells from cell_reading '
                    'where capture_id=? and tray_id=? and cell=?', (cid, tag, cell)).fetchone()
    poly = np.array(json.loads(row[0]), dtype=float)
    ctr = poly.mean(axis=0)
    # Same field of view as the Helios crop: 0.70 of the 69.7 mm cell pitch either side of centre,
    # measured here from this cell's own 59.5 mm opening.
    cell_side_px = float(np.mean([np.linalg.norm(poly[i] - poly[(i + 1) % 4]) for i in range(4)]))
    rad = 0.70 * (CELL_PITCH_MM / CELL_OPENING_MM) * cell_side_px
    rx0, ry0 = int(ctr[0] - rad), int(ctr[1] - rad)
    rc = rimg[max(0, ry0):int(ctr[1] + rad), max(0, rx0):int(ctr[0] + rad)]
    rname = f'tag{tag}_{cell}_rig.png'
    cv2.imwrite(f'{OUT}/{rname}', rc)
    man.append({
        'tray_tag': tag, 'cell': cell, 'helios_tray': helios_tray,
        'helios_file': hname, 'helios_source': f'{hstem}_RGB2_FishEyeCorrected.png',
        'helios_px_per_mm': round(float(side / TAG_MM), 4),
        'helios_scale_from': f'tray tag {tag}, {TAG_MM} mm across the black square, {round(float(side),2)} px',
        'rig_file': rname, 'rig_source': f'{rstem}.jpg', 'rig_capture_id': cid,
        'rig_mm2_per_px': round(row[1] / row[2], 6) if row[1] and row[2] else None,
        'rig_over_other_cells': row[3],
        'helios_crop_px': list(hc.shape[:2]), 'rig_crop_px': list(rc.shape[:2]),
    })
json.dump(man, open(f'{OUT}/manifest.json', 'w'), indent=1)
for m in man:
    print(m['tray_tag'], m['cell'], 'helios', m['helios_crop_px'], f"{m['helios_px_per_mm']} px/mm",
          '| rig', m['rig_crop_px'], 'over_other_cells', m['rig_over_other_cells'])
