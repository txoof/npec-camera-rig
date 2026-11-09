"""Corner-tag light index for #382. Reads copied photos only; writes CSV to argv[3]."""
import cv2, csv, sys, numpy as np
from multiprocessing import Pool
ROOT, LIST, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
CORNER = {450, 451, 452, 455, 456}
D = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
C = 16  # canonical px per cell
LUT = np.array([((v/255)/12.92 if v/255 <= 0.04045 else ((v/255+0.055)/1.055)**2.4) for v in range(256)], np.float32)

def masks(tid):
    m = cv2.aruco.generateImageMarker(D, int(tid), 8, borderBits=1)  # 8x8 cells, 0 black 255 white
    W = 10*C
    white_in = np.zeros((W, W), bool); black = np.zeros((W, W), bool); outer = np.zeros((W, W), bool)
    q = C//4
    for r in range(8):
        for c in range(8):
            y, x = (r+1)*C, (c+1)*C
            (white_in if m[r, c] else black)[y+q:y+C-q, x+q:x+C-q] = True
    outer[q:W-q, q:W-q] = True; outer[C-q:W-C+q, C-q:W-C+q] = False
    return white_in, black, outer

def one(row):
    p = f"{ROOT}/{row['path']}.jpg"
    im = cv2.imread(p, cv2.IMREAD_REDUCED_COLOR_2)
    E = float(row['exposure_us'])*float(row['analogue_gain'])
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    det = cv2.aruco.ArucoDetector(D, cv2.aruco.DetectorParameters())
    cs, ids, _ = det.detectMarkers(g)
    frame_lin = float(LUT[im[::8, ::8, 1]].mean())
    out = []
    found = {} if ids is None else {int(i): c[0] for c, i in zip(cs, ids.ravel()) if int(i) in CORNER}
    for tid, q in found.items():
        dst = np.float32([[C, C], [9*C, C], [9*C, 9*C], [C, 9*C]])
        H = cv2.getPerspectiveTransform(q.astype(np.float32), dst)
        w = cv2.warpPerspective(im, H, (10*C, 10*C), flags=cv2.INTER_LINEAR)
        wi, bl, ou = masks(tid)
        rec = dict(id=row['id'], taken_at=row['taken_at'], set=row['set'], E=E, tag=tid,
                   cx=round(float(q[:, 0].mean()), 1), cy=round(float(q[:, 1].mean()), 1), frame_G_lin=frame_lin)
        for name, mk in (('white_in', wi), ('outer', ou), ('black', bl)):
            px = w[mk]
            rec[f'{name}_G'] = float(px[:, 1].mean())
            rec[f'{name}_G_lin'] = float(LUT[px[:, 1]].mean())
            rec[f'{name}_clip'] = float((px.max(1) >= 250).mean())
            rec[f'{name}_Gclip'] = float((px[:, 1] >= 250).mean())
        out.append(rec)
    if not out:
        out.append(dict(id=row['id'], taken_at=row['taken_at'], set=row['set'], E=E, tag=-1, frame_G_lin=frame_lin))
    return out

if __name__ == '__main__':
    rows = list(csv.DictReader(open(LIST)))
    res = []
    with Pool(3) as pool:
        for i, r in enumerate(pool.imap(one, rows, chunksize=4)):
            res.extend(r)
            if i % 50 == 0: print(i, flush=True)
    keys = list(dict.fromkeys(k for r in res for k in r))
    with open(OUT, 'w') as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(res)
    print('rows', len(res))
