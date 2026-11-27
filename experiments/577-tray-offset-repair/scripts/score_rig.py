import os, sys, time
os.environ["TRAY328_DATA"] = "/home/pi/.claude/jobs/44c5d2e5/tmp"
sys.path.insert(0, "/home/pi/npec_camera_rig/experiments/round3-tray-outlines"); sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, harness, methods_hybrid
rig = sys.argv[1]; tot = []; changed = 0
for s in harness.stills(rig):
    f = methods_hybrid.find(s); sc = harness.score(s, f)
    rep = [h["how"] for h in f if not h["how"].startswith("lattice")]
    changed += bool(rep)
    tot.append((sc["found"], sc["of"], sc["extra"]))
    print(rig, s.stem, sc["found"], "/", sc["of"], "extra", sc["extra"], rep, flush=True)
print("SUMMARY", rig, "stills", len(tot), "worst", min(t[0] for t in tot), "of", tot[0][1], "mean", round(np.mean([t[0] for t in tot]), 2),
      "extra/still", round(np.mean([t[2] for t in tot]), 2), "stills where hybrid changed something:", changed, flush=True)
