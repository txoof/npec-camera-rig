import os, sys, time
os.environ["TRAY328_DATA"] = "/home/pi/.claude/jobs/44c5d2e5/tmp"
sys.path.insert(0, "/home/pi/npec_camera_rig/experiments/round3-tray-outlines"); sys.path.insert(0, os.path.dirname(__file__))
import harness, methods_hybrid
for rig in ("prod", "dev", "hard"):
    s = harness.stills(rig)[0]; t = time.time()
    f = methods_hybrid.find(s); sc = harness.score(s, f)
    print(rig, s.stem, sc["found"], "/", sc["of"], "extra", sc["extra"], [h["how"] for h in f][:14], round(time.time() - t, 1), "s", flush=True)
