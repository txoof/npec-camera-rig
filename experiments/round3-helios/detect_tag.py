import sys, cv2, numpy as np

def params():
    p = cv2.aruco.DetectorParameters()
    p.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    p.minMarkerPerimeterRate = 0.005
    p.adaptiveThreshWinSizeMin = 11
    p.adaptiveThreshWinSizeMax = 91
    p.adaptiveThreshWinSizeStep = 10
    return p

d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
det = cv2.aruco.ArucoDetector(d, params())
for path in sys.argv[1:]:
    img = cv2.imread(path)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = det.detectMarkers(g)
    out = []
    if ids is not None:
        for i, cset in zip(ids.flatten(), corners):
            c = cset.reshape(4, 2)
            side = float(np.mean([np.linalg.norm(c[j] - c[(j+1) % 4]) for j in range(4)]))
            out.append((int(i), round(side, 2), [round(float(x), 1) for x in c.mean(axis=0)]))
    print(path.split('/')[-1], img.shape, out)
