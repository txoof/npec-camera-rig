import os, sys
os.environ["TRAY328_DATA"] = "/home/pi/.claude/jobs/44c5d2e5/tmp"
sys.path.insert(0, "/home/pi/npec_camera_rig/experiments/round3-tray-outlines"); sys.path.insert(0, os.path.dirname(__file__))
from pathlib import Path
import harness, methods_hybrid
n = ch = 0
for p in sorted((harness.DATA / "stills" / "held").glob("*.jpg")):
    s = harness.Still("held", p.stem)
    try:
        f = methods_hybrid.find(s)
    except Exception as e:
        print(p.stem, "ERR", repr(e)[:80], flush=True); continue
    n += 1; rep = [h["how"] for h in f if not h["how"].startswith("lattice")]
    ch += bool(rep); print(p.stem, len(f), "outlines", rep, flush=True)
print("SUMMARY held stills", n, "changed by hybrid", ch)
