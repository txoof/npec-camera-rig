"""Rule sweep on full photos (metrology log 46). For each photo: noise from the image, then every
tray the app found run through grow_from_cores with the rule at thr = N levels (method c) and
thr = k x sigma_b (method b), N and k = 0..12. One CSV row per photo, tray, method, level.
usage: run_photos.py LABEL OUT.csv photo.jpg:api.json [...]   (with --no-trays: whole-photo noise only)"""
import csv, json, sys, time
import os
import cv2
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import rule
from npec_rig import images, segmentation as sg

LEVELS = list(range(13))
FORM = os.environ.get("FORM", "A")
TAG_SHRINK = 40 / 59  # cell A1 corners, shrunk to the 40 mm tray tag (cell about 59 mm)


def trays_of(api):
    out = []
    for t in api["trays"]:
        if not t.get("outline_px") or t.get("found") is None:
            continue
        tag = next((c["corners_px"] for c in t["cells"] if c["holds"] == "tag"), None)
        mm2 = None
        for a, p in (("grown_area_mm2", "grown_plant_px"), ("area_mm2", "plant_px")):
            if t.get(p, 0) and t.get(p) > 200 and t.get(a):
                mm2 = t[a] / t[p]; break
        out.append((t["tray_id"], t["outline_px"], tag, mm2, t))
    return out


def main():
    label, out_csv, *specs = sys.argv[1:]
    rows = []
    for spec in specs:
        jpg, apij = spec.split(":")
        api = json.load(open(apij))
        rgb = images.decode_full(jpg)
        trays = trays_of(api)
        boxes = []
        res_all, s_all = [], []
        for tid, outline, tag, mm2, t in trays:
            box = sg._box(np.zeros(rgb.shape[:2], bool), outline)
            if box is None:
                continue
            x0, y0, x1, y1 = box
            inside = sg._inside(box, outline)
            tagc = []
            if tag:
                c = np.asarray(tag, float) - [x0, y0]
                ctr = c.mean(axis=0)
                tagc = [ctr + TAG_SHRINK * (c - ctr)]
            res, s = rule.noise_arrays(rgb[y0:y1, x0:x1], inside, form=FORM)
            res_all.append(res); s_all.append(s)
            boxes.append((tid, box, inside, tagc, mm2, t))
        res = np.concatenate(res_all); s = np.concatenate(s_all)
        sig, sig_all, n_dark = rule.sigma_from(res, s)
        mm2s = [b[4] for b in boxes if b[4]]
        mm2_photo = float(np.median(mm2s)) if mm2s else float("nan")
        print(jpg.split("/")[-1], "sigma_b %.3f (all pixels %.3f, %d dark px)" % (sig, sig_all, n_dark), flush=True)
        for tid, box, inside, tagc, mm2, t in boxes:
            x0, y0, x1, y1 = box
            sweeps = [("app", "-", None)] + [("c", n, float(n)) for n in LEVELS] + [("b", k, k * sig) for k in LEVELS]
            thrs = [x[2] for x in sweeps]
            t0 = time.time()
            for (method, lev, thr), (_t, mask, soil, lc) in zip(sweeps, rule.grow_sweep(rgb[y0:y1, x0:x1], inside, thrs, tagc, form=FORM)):
                px = int(mask.sum()); main_px = rest_px = ""
                if mask.any():
                    n, lab, st, _ = cv2.connectedComponentsWithStats(mask.view(np.uint8), connectivity=8)
                    big = int(st[1:, cv2.CC_STAT_AREA].max()); main_px, rest_px = big, px - big
                else:
                    main_px, rest_px = 0, 0
                rows.append(dict(form=FORM, set=label, photo=jpg.split("/")[-1][:-4], day=jpg.split("/")[-2] if "e18" in jpg else "2026-11-24", tray=tid, method=method, level=lev, thr=thr if thr is not None else "",
                                 sigma_b=round(sig, 3), sigma_all=round(sig_all, 3), px=px, main_px=main_px, rest_px=rest_px,
                                 mm2_per_px=mm2 if mm2 else mm2_photo, soil=soil, lower_cutoff=lc,
                                 stored_grown_px=t.get("grown_plant_px")))
            print("  tray", tid, "%.0fs" % (time.time() - t0), flush=True)
        del rgb
        images.release_freed_memory() if hasattr(images, "release_freed_memory") else None
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


if __name__ == "__main__":
    main()
