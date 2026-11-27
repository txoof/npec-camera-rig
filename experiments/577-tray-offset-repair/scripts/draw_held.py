import os, sys
os.environ["TRAY328_DATA"] = "/home/pi/.claude/jobs/44c5d2e5/tmp"
sys.path.insert(0, "/home/pi/npec_camera_rig/experiments/round3-tray-outlines"); sys.path.insert(0, os.path.dirname(__file__))
import cv2, numpy as np, harness, methods_hybrid, methods_blue
from PIL import Image
s = harness.Still("held", "dev_907f12cd_20261023_133141_374223")
def draw(found, title):
    im = s.quarter.copy()
    for f in found:
        c = (np.asarray(f["outline"]) / 4).astype(np.int32)
        col = (255, 0, 255) if f["how"].startswith("lattice") or f["how"] == "blue mask" else (0, 0, 255)
        cv2.polylines(im, [c], True, col, 6)
        if not f["how"].startswith("lattice") and f["how"] != "blue mask":
            cv2.putText(im, f["how"], (c[0][0] + 20, c[0][1] + 60), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 0), 5)
    return Image.fromarray(cv2.cvtColor(im, cv2.COLOR_BGR2RGB))
a = draw(methods_blue.find_photo_only(s), ""); b = draw(methods_hybrid.find(s), "")
w, h = a.size; k = 0.5
a = a.resize((int(w * k), int(h * k))); b = b.resize((int(w * k), int(h * k)))
im = Image.new("RGB", (a.width * 2 + 20, a.height), (255, 255, 255)); im.paste(a, (0, 0)); im.paste(b, (a.width + 20, 0)); im.save("held_dev_907f12cd_compare.png"); print(im.size)
