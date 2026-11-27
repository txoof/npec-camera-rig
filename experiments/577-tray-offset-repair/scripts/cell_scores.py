"""Ring-loop coverage of each lattice cell (Method B output) on the old test sets and on photo 319."""
import os, sys
os.environ["TRAY328_DATA"] = "/home/pi/.claude/jobs/44c5d2e5/tmp"
os.environ["TRAY328_VIEW"] = "/home/pi/scratch/tray-boundaries/view"
sys.path.insert(0, "/home/pi/npec_camera_rig/experiments/round3-tray-outlines"); sys.path.insert(0, os.path.dirname(__file__))
import cv2, numpy as np, harness, methods_blue, methods_ring as mr

def cell_scores(still, found):
    rim = mr._evidence(still); H, W = rim.shape; F = 4
    ppm = still.px_per_mm(W * F / 2, H * F / 2) / F
    band = max(3, int(round(mr.BAND_MM * ppm)))
    tw, th = int(round(305 * ppm)), int(round(366 * ppm))
    pad = max(tw, th)
    padded = cv2.copyMakeBorder(rim, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    ring = np.ones((th, tw), np.float32); ring[band:-band, band:-band] = 0
    sc = cv2.matchTemplate(padded, ring, cv2.TM_CCORR) / ring.sum()
    out = []
    for f in found:
        o = np.asarray(f["outline"]) / F
        x0, y0 = int(round(o[:, 0].min())) , int(round(o[:, 1].min()))
        # tolerate a few px of position error
        win = sc[y0 + pad - 6: y0 + pad + 7, x0 + pad - 6: x0 + pad + 7]
        out.append(float(win.max()) if win.size else 0.0)
    return out

rows = []
for rig in harness.RIGS:
    for s in harness.stills(rig):
        found = methods_blue.find_photo_only(s)
        sc = harness.score(s, found)
        cs = cell_scores(s, found)
        # which found outline matched a reference tray? approximate: extra outlines = those not near any reference
        refs = harness.reference(s)
        for f, c in zip(found, cs):
            fc = harness._centre(f["outline"])
            ppm = s.px_per_mm(*fc)
            d = min([np.hypot(fc[0] - harness._centre(r["outline"])[0], fc[1] - harness._centre(r["outline"])[1]) / ppm for r in refs] or [999])
            rows.append((rig, d <= 30, c))
import collections
for rig in harness.RIGS:
    good = [c for r, ok, c in rows if r == rig and ok]; bad = [c for r, ok, c in rows if r == rig and not ok]
    print(rig, "cells near a reference tray:", len(good), "min %.2f p5 %.2f median %.2f" % (min(good), np.percentile(good, 5), np.median(good)),
          "| cells matching no tray:", len(bad), ("max %.2f" % max(bad)) if bad else "")
