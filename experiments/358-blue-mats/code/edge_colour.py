"""#358, metrology log 36: why grow from leaf cores loses the leaf edge on a blue mat. For chosen
cells, the pixels in a band just outside the app's grow from leaf cores mask, by distance from it
(1 to 6 px), sorted by the condition of `segmentation.grow_from_cores` that leaves them out: blue
(blue above red and green), or greenness (2G - R - B) / (R + G + B) at or below the tray's lower
cutoff. Writes a close-up with the band marked: red = left out as blue, white = left out as not
green enough. Usage: edge_colour.py STILLS TRAYS OUT_JPG TRAY CELL[,CELL] TIME[,TIME]"""
import glob, json, os, sys
import cv2, numpy as np
from npec_rig.segmentation import grow_trays
from npec_rig.tags import detect_tags

stills, trays_dir, out, tray, cells, times = sys.argv[1:7]
tray = int(tray); cells = cells.split(','); rows = []
for t in times.split(','):
    path = glob.glob(os.path.join(stills, f'*T{t}*.jpg'))[0]
    rgb = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2RGB)
    tr = [x for x in json.load(open(os.path.join(trays_dir, os.path.basename(path)[:-4] + '.json')))['trays'] if x['tray_id'] == tray][0]
    tag = [d for d in detect_tags(rgb) if d.tag_id == tray][0]
    grown, levels = grow_trays(rgb, [(np.array(tr['outline_px'], float), [tag.corners])])
    cutoff = levels[0][1]
    row = []
    for c in [c for c in tr['cells'] if c['cell'] in cells]:
        cx, cy = np.array(c['corners_px']).mean(0).astype(int); h = 110
        sub = rgb[cy - h:cy + h, cx - h:cx + h].astype(np.int32); m = grown[cy - h:cy + h, cx - h:cx + h]
        r, g, b = sub[..., 0], sub[..., 1], sub[..., 2]
        blue = (b - np.maximum(r, g)) > 0
        green = (2 * g - r - b) / np.maximum(r + g + b, 1)
        dull = ~blue & (green <= cutoff)
        dist = cv2.distanceTransform((~m).astype(np.uint8), cv2.DIST_L2, 3)
        print(f'tray {tray} {c["cell"]} {t} UTC, lower cutoff {cutoff:+.3f}, plant px {int(m.sum())}')
        for d in range(1, 7):
            ring = (dist > d - 1) & (dist <= d) & ~m
            n = int(ring.sum())
            print(f'  {d} px out: n {n:4d}, blue {blue[ring].mean() * 100:5.1f}%, not green enough {dull[ring].mean() * 100:5.1f}%, '
                  f'kept-colour but unjoined {((~blue & ~dull)[ring]).mean() * 100:5.1f}%; median R G B '
                  f'{int(np.median(r[ring]))} {int(np.median(g[ring]))} {int(np.median(b[ring]))}, greenness median {np.median(green[ring]):+.3f}')
        band = (dist > 0) & (dist <= 6) & ~m
        big = cv2.resize(cv2.cvtColor(sub.astype(np.uint8), cv2.COLOR_RGB2BGR), None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST)
        for sel, colr in ((band & blue, (0, 0, 255)), (band & dull, (255, 255, 255))):
            big[cv2.resize(sel.astype(np.uint8), None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST) > 0] = colr
        cs, _ = cv2.findContours(cv2.resize(m.astype(np.uint8), None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(big, cs, -1, (255, 0, 255), 2)
        for col, th in (((255, 255, 255), 4), ((255, 0, 255), 2)):
            cv2.putText(big, f"tray {tray} {c['cell']} {t[:2]}:{t[2:]} UTC", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, col, th)
        row.append(big)
    rows.append(np.hstack(row)); del rgb, grown
cv2.imwrite(out, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 90])
