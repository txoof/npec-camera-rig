"""Express each cell centre in the tray tag's own frame, from the rig photo."""
import sqlite3, sys, json, cv2, numpy as np

db, jpg, cid = sys.argv[1], sys.argv[2], int(sys.argv[3])

def params():
    p = cv2.aruco.DetectorParameters()
    p.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    p.minMarkerPerimeterRate = 0.005
    p.adaptiveThreshWinSizeMin = 11
    p.adaptiveThreshWinSizeMax = 91
    p.adaptiveThreshWinSizeStep = 10
    p.markerBorderBits = 1
    p.perspectiveRemovePixelPerCell = 8
    p.relativeCornerRefinmentWinSize = 0.5
    return p

img = cv2.imread(jpg)
print('rig photo', img.shape, file=sys.stderr)
g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
det = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11), params())
corners, ids, _ = det.detectMarkers(g)
tags = {int(i): c.reshape(4, 2) for i, c in zip(ids.flatten(), corners)} if ids is not None else {}
print('tags found', sorted(tags), file=sys.stderr)

c = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
out = {}
for tag in sorted(t for t in tags if t < 300):
    q = c.execute('select cell,centre_x_px,centre_y_px from cell_reading where capture_id=? and tray_id=?', (cid, tag)).fetchall()
    if not q:
        continue
    tc = tags[tag]
    o = tc.mean(axis=0)
    ex = (tc[1] - tc[0] + tc[2] - tc[3]) / 2.0     # tag corner 0->1 direction
    ey = (tc[3] - tc[0] + tc[2] - tc[1]) / 2.0     # tag corner 0->3 direction
    side = (np.linalg.norm(ex) + np.linalg.norm(ey)) / 2.0
    ex, ey = ex / np.linalg.norm(ex), ey / np.linalg.norm(ey)
    M = np.array([ex, ey]).T
    loc = {}
    for cell, x, y in q:
        v = np.linalg.solve(M, np.array([x, y]) - o)
        loc[cell] = [round(float(v[0] / side), 4), round(float(v[1] / side), 4)]
    out[tag] = {'side_px': round(float(side), 2), 'cells': loc}
json.dump(out, open(sys.argv[4], 'w'), indent=1)
for tag in list(out)[:2]:
    print(tag, {k: out[tag]['cells'][k] for k in ('A1','A2','B1','D5')}, file=sys.stderr)
