import sys, csv, cv2, collections
sys.path.insert(0, "/home/pi/wt/npec-153-round1-benchmark/src")
from npec_rig import tags
D = "/var/lib/npec-rig/experiments/2026-10-15_44a9e96e/stills/2026-10-15"
rows = [r for r in csv.reader(open("/home/pi/wt/npec-153-round1-benchmark/experiments/round1/session-2026-10-15.csv")) if r[0].startswith("R2-")]
P = {4: 0, 5: 14, 6: 16, 7: 17, 8: 13, 11: 15}
T20 = [0, 1, 2, 3, 13, 14, 15, 16, 17]; T30 = [4, 5, 6, 7, 8, 9, 10, 11, 12]
EXPECTED = set(range(18))
def base():
    return tags._detector_parameters()
def v(**kw):
    def f():
        p = base()
        for k, val in kw.items(): setattr(p, k, val)
        return p
    return f
V = {
 "A baseline (rig)": base,
 "B error correction 1.0": v(errorCorrectionRate=1.0),
 "C bit sampling 8 px/cell": v(perspectiveRemovePixelPerCell=8, perspectiveRemoveIgnoredMarginPerCell=0.2),
 "D threshold windows 3..53, const 5": v(adaptiveThreshWinSizeMin=3, adaptiveThreshWinSizeMax=53, adaptiveThreshWinSizeStep=4, adaptiveThreshConstant=5),
 "E polygon accuracy 0.05": v(polygonalApproxAccuracyRate=0.05),
 "F B+C+D+E": v(errorCorrectionRate=1.0, perspectiveRemovePixelPerCell=8, perspectiveRemoveIgnoredMarginPerCell=0.2,
                adaptiveThreshWinSizeMin=3, adaptiveThreshWinSizeMax=53, adaptiveThreshWinSizeStep=4, adaptiveThreshConstant=5,
                polygonalApproxAccuracyRate=0.05),
}
dic = cv2.aruco.getPredefinedDictionary(tags.TAG_DICTIONARY)
res = collections.defaultdict(dict); extra = collections.defaultdict(set)
for step, title, _, _, s in rows:
    gray = cv2.imread(f"{D}/{s}.jpg", cv2.IMREAD_GRAYSCALE)
    for name, mk in V.items():
        _, ids, _ = cv2.aruco.ArucoDetector(dic, mk()).detectMarkers(gray)
        found = set(int(i) for i in ids.flatten()) if ids is not None else set()
        res[name][(step, s)] = found
        bad = {i for i in found if i not in EXPECTED and not 450 <= i < 500}
        if bad: extra[name] |= bad
    print(step, s, {n[:1]: len(res[n][(step, s)] & EXPECTED) for n in V}, flush=True)
print()
for name in V:
    r = res[name]; m20 = sum(t not in f for f in r.values() for t in T20); m30 = sum(t not in f for f in r.values() for t in T30)
    a = []
    for step in sorted({k[0] for k in r}):
        ss = [k for k in r if k[0] == step]
        for g, t in P.items():
            if all(t not in r[k] for k in ss) and any(g in r[k] for k in ss): a.append(f"{step}:{t}")
    print(f"{name:38s} 20mm missed {m20:3d}/171  30mm missed {m30}/171  persistent {a}  unexpected ids {sorted(extra[name])}")
