import os, sys
os.environ["TRAY328_DATA"] = "/home/pi/.claude/jobs/44c5d2e5/tmp"
os.environ["TRAY328_VIEW"] = "/home/pi/scratch/tray-boundaries/view"
sys.path.insert(0, "/home/pi/npec_camera_rig/experiments/round3-tray-outlines")
sys.path.insert(0, os.path.dirname(__file__))
import harness, methods_blue, methods_ring
which = sys.argv[1]
import methods_hybrid
fn = {"blue": methods_blue.find_photo_only, "ring": methods_ring.find, "hybrid": methods_hybrid.find}[which]
harness.run(which, fn, sys.argv[2], "", rigs=harness.RIGS, pictures="none")
