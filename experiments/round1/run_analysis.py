import sys, csv, json, time, cv2
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))
from npec_rig import tags
from npec_rig.camera import to_grayscale
D = "/var/lib/npec-rig/experiments/2026-10-15_44a9e96e/stills/2026-10-15"
rows = [r[4] for r in csv.reader(open(HERE / "session-2026-10-15.csv")) if r[0] == "R3"]
dic = cv2.aruco.getPredefinedDictionary(tags.TAG_DICTIONARY)
pA = tags._detector_parameters(); pC = tags._detector_parameters(); pC.perspectiveRemovePixelPerCell = 8; pC.perspectiveRemoveIgnoredMarginPerCell = 0.2
out = csv.writer(open("hourrun_tags.csv", "w")); out.writerow(["still", "exposure_us", "gain", "red_gain", "blue_gain", "lens", "found_A", "found_C", "secs_A", "secs_C"])
for s in rows:
    m = json.load(open(f"{D}/{s}.json")); sm = m["sensor_metadata"]
    img = cv2.cvtColor(cv2.imread(f"{D}/{s}.jpg"), cv2.COLOR_BGR2RGB); g = to_grayscale(img).astype("uint8"); del img
    res = []
    for p in (pA, pC):
        t = time.perf_counter(); _, ids, _ = cv2.aruco.ArucoDetector(dic, p).detectMarkers(g); dt = time.perf_counter() - t
        f = sorted(int(i) for i in ids.flatten()) if ids is not None else []
        res += [" ".join(map(str, f)), round(dt, 2)]
    out.writerow([s, sm["ExposureTime"], sm["AnalogueGain"], round(sm["ColourGains"][0], 4), round(sm["ColourGains"][1], 4), round(sm["LensPosition"], 4), res[0], res[2], res[1], res[3]])
    print(s, flush=True)
print("DONE", flush=True)
