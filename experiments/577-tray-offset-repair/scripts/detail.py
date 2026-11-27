import os, sys
os.environ["TRAY328_DATA"] = "/home/pi/.claude/jobs/44c5d2e5/tmp"
os.environ["TRAY328_VIEW"] = "/home/pi/scratch/tray-boundaries/view"
sys.path.insert(0, "/home/pi/npec_camera_rig/experiments/round3-tray-outlines"); sys.path.insert(0, os.path.dirname(__file__))
import harness, methods_ring
for rig in ("prod", "dev"):
    for s in harness.stills(rig)[:13:6]:
        sc = harness.score(s, methods_ring.find(s))
        print(rig, s.stem, sc["found"], "/", sc["of"], "extra", sc["extra"])
        for r in sc["rows"]:
            if not r["found"] and not r["partial"]: print("   MISS", r["tray"], r["centre_mm"], r["iou"], r["how"])
