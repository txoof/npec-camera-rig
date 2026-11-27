"""Place the 4x5 cell grid on a Helios tray photo from its AprilTag, and draw it."""
import sys, json, cv2, numpy as np

TAG_MM = 39.95          # callipers, Aaron 2026-10-20 (metrology log 35.x)
PITCH_SIDES = 1.742     # cell centre spacing in tag sides, measured from rig photo 32300
ROWS = '12345'          # 5 along the tray's long axis
COLS = 'ABCD'           # 4 across

def params():
    p = cv2.aruco.DetectorParameters()
    p.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    p.minMarkerPerimeterRate = 0.005
    p.adaptiveThreshWinSizeMin = 11
    p.adaptiveThreshWinSizeMax = 91
    p.adaptiveThreshWinSizeStep = 10
    return p

def grid(path):
    img = cv2.imread(path)
    h, w = img.shape[:2]
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    det = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11), params())
    corners, ids, _ = det.detectMarkers(g)
    if ids is None or len(ids) != 1:
        raise SystemExit(f'{path}: expected one tag, got {ids}')
    tag = int(ids.flatten()[0])
    tc = corners[0].reshape(4, 2)
    o = tc.mean(axis=0)
    ex = (tc[1] - tc[0] + tc[2] - tc[3]) / 2.0
    ey = (tc[3] - tc[0] + tc[2] - tc[1]) / 2.0
    side = (np.linalg.norm(ex) + np.linalg.norm(ey)) / 2.0
    ex, ey = ex / np.linalg.norm(ex), ey / np.linalg.norm(ey)
    best = None
    for k in range(4):                       # 4 rotations of the tag in its cell
        a = [ex, ey, -ex, -ey][k]            # direction of increasing row (1->5)
        b = [ey, -ex, -ey, ex][k]            # direction of increasing column (A->D)
        cells = {}
        for ci, col in enumerate(COLS):
            for ri, row in enumerate(ROWS):
                p = o + a * (ri * PITCH_SIDES * side) + b * (ci * PITCH_SIDES * side)
                cells[col + row] = p
        m = PITCH_SIDES * side * 0.5
        inside = sum(m <= p[0] <= w - m and m <= p[1] <= h - m for p in cells.values())
        if best is None or inside > best[0]:
            best = (inside, cells, side, a, b)
    inside, cells, side, a, b = best
    if inside != 20:
        raise SystemExit(f'{path}: only {inside}/20 cells inside the frame')
    return img, tag, cells, side, a, b

if __name__ == '__main__':
    src, out_json, out_png = sys.argv[1], sys.argv[2], sys.argv[3]
    img, tag, cells, side, a, b = grid(src)
    px_per_mm = side / TAG_MM
    half = int(PITCH_SIDES * side * 0.5)
    vis = img.copy()
    for name, p in cells.items():
        p = tuple(int(v) for v in p)
        cv2.rectangle(vis, (p[0]-half, p[1]-half), (p[0]+half, p[1]+half), (0, 0, 255), 4)
        cv2.putText(vis, name, (p[0]-half+12, p[1]-half+70), cv2.FONT_HERSHEY_SIMPLEX, 2.2, (0, 0, 255), 5)
    sc = 1400 / vis.shape[1]
    cv2.imwrite(out_png, cv2.resize(vis, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA))
    json.dump({'tag': tag, 'tag_side_px': round(float(side), 3), 'px_per_mm': round(float(px_per_mm), 4),
               'cells': {k: [round(float(v[0]), 1), round(float(v[1]), 1)] for k, v in cells.items()}},
              open(out_json, 'w'), indent=1)
    print(src.split('/')[-1], 'tag', tag, 'side_px', round(float(side), 2), 'px/mm', round(float(px_per_mm), 3))
