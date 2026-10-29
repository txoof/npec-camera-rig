"""Issue #297: every method tried so far, on one still, in one run, with the same crop, the same
tray placement and the same truth: plants per tray, plant area per tray, the Benchy rosettes, and
the time each method takes. Metrology log 19.

    PYTHONPATH=~/npec_camera_rig/src:DIR venv/bin/python DIR/compare.py --fastsam-hef H --clip CDIR \
        --sam SDIR --calibration C --slots S --rig-reading R.json --out NEW_FOLDER still.jpg

Methods (all from the green threshold in use, EXG_MIN, pieces of at least 0.5 mm2):
    exg_join3, exg_join5, exg_join10   green pieces closer than 3, 5, 10 mm are one plant
    fastsam_point                      the smallest FastSAM mask at each 3 mm blob's centre; blobs
                                       landing in the same mask are one plant
    clip_foliage, clip_leaves, clip_plants
                                       FastSAM objects that CLIP scores higher for the word than
                                       for any background word (clip_prompts.py)
    sam21                              SAM 2.1 small, box and point from each 3 mm blob, overlapping
                                       masks merged; area = the mask (sam21_plants.py)
    sam21_green                        the same plants; area = green pixels inside the mask
A plant belongs to the tray its centre lies in. R.json is the rig's own stored reading of the
still (GET /api/captures/trays/...), shown beside the methods.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import cv2
import numpy as np

import clip_prompts as cp
import fastsam_plants as fp
import sam21_plants as sp
from npec_rig.calibration_store import load_calibration
from npec_rig.segmentation import ExGSegmenter
from npec_rig.tags import detect_tags

TRUTH = sp.TRUTH  # Aaron, 2026-10-29
METHODS = ("exg_join3", "exg_join5", "exg_join10", "fastsam_point", "clip_foliage", "clip_leaves",
           "clip_plants", "sam21", "sam21_green")


def obj(cx, cy, area_px, contour=None, box=None):
    """One plant found by a method; centre in the cropped still."""
    return {"cx": float(cx), "cy": float(cy), "area_px": float(area_px), "contour": contour, "box": box}


def contour_centre(c):
    m = cv2.moments(c)
    return (m["m10"] / m["m00"], m["m01"] / m["m00"]) if m["m00"] else tuple(c.reshape(-1, 2).mean(0))


def by_tray(objs, trays, oy, sf):
    """tray id -> (count, area mm2, [areas mm2]) of the objects whose centre lies in the tray."""
    out = {}
    for tp, _ in trays:
        o = np.float32(tp.outline)
        areas = []
        for ob in objs:
            x, y = ob["cx"], ob["cy"] + oy
            if cv2.pointPolygonTest(o, (x, y), False) >= 0:
                areas.append(ob["area_px"] / sf.px_per_mm(x, y) ** 2)
        out[tp.tray_id] = (len(areas), sum(areas), sorted(areas, reverse=True))
    return out


def picture(bgr, objs, trays, counts, oy, title, path):
    f = 1 / fp.VIEW_REDUCE
    im = cv2.resize(bgr, (bgr.shape[1] // fp.VIEW_REDUCE, bgr.shape[0] // fp.VIEW_REDUCE), interpolation=cv2.INTER_AREA)
    for ob in objs:
        if ob["contour"] is not None:
            cv2.drawContours(im, [(ob["contour"] * f).astype(np.int32)], -1, (0, 255, 0), 2)
        else:
            x0, y0, x1, y1 = ob["box"]
            cv2.rectangle(im, (int(x0 * f), int(y0 * f)), (int(x1 * f), int(y1 * f)), (255, 0, 255), 2)
    for tp, _ in trays:
        cv2.polylines(im, [((np.float32(tp.outline) - np.float32([0, oy])) * f).astype(np.int32)], True, (255, 255, 0), 3)
        n = counts[tp.tray_id][0]
        lab = f"tray {tp.tray_id}: {n}" + (f" (true {TRUTH[tp.tray_id]})" if tp.tray_id in TRUTH else "")
        org = (int(tp.centre[0] * f) - 90, int((tp.centre[1] - oy) * f))
        cv2.putText(im, lab, org, cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 6)
        cv2.putText(im, lab, org, cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.rectangle(im, (0, 0), (im.shape[1], 30), (0, 0, 0), -1)
    cv2.putText(im, title, (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    cv2.imwrite(str(path), im, [cv2.IMWRITE_JPEG_QUALITY, 85])


def run(still, nets, placing, rig_reading, out: Path):
    fastsam, image_net, texts, sam = nets
    sf = placing[0]
    out.mkdir(parents=True, exist_ok=False)
    secs = {}
    t0 = time.perf_counter()
    full = cv2.imread(str(still))
    tags = detect_tags(cv2.cvtColor(full, cv2.COLOR_BGR2RGB))
    trays = fp.trays_of(tags, placing)
    bgr, crop, _ = fp.crop_to_corner_tags(full, tags)
    oy = crop[1]
    secs["shared: read, tags, trays, crop"] = time.perf_counter() - t0
    found = {}

    blobs3 = None
    for j in (3, 5, 10):
        fp.JOIN_MM = j
        t = time.perf_counter()
        _, blobs = fp.exg_blobs(bgr)
        secs[f"exg_join{j}"] = time.perf_counter() - t
        found[f"exg_join{j}"] = [obj(b["cx"], b["cy"], b["area_px"], box=(b["x0"], b["y0"], b["x1"], b["y1"])) for b in blobs]
        if j == 3:
            blobs3 = blobs
    fp.JOIN_MM = 3

    t = time.perf_counter()
    dets, _ = fp.fastsam_all(bgr, fastsam)
    t_fastsam = time.perf_counter() - t
    t = time.perf_counter()
    picks = fp.prompted(dets, blobs3)
    uniq = {id(d): d for d in picks if d is not None}.values()
    found["fastsam_point"] = [obj(*contour_centre(d["contour"]), d["area_px"], contour=d["contour"]) for d in uniq]
    secs["fastsam_point"] = t_fastsam + time.perf_counter() - t

    t = time.perf_counter()
    img = np.stack([cp.unit(image_net(cp.object_crop(bgr, d))) for d in dets])
    bg = np.stack([texts[w] for w in cp.BACKGROUND])
    t_clip = time.perf_counter() - t
    for p in cp.PROMPTS:
        kept = (img @ np.vstack([texts[p][None], bg]).T).argmax(1) == 0
        found[f"clip_{p}"] = [obj(*contour_centre(d["contour"]), d["area_px"], contour=d["contour"])
                              for d, k in zip(dets, kept) if k]
        secs[f"clip_{p}"] = t_fastsam + t_clip  # FastSAM and CLIP once, all three words from it

    t = time.perf_counter()
    plants, _, _, _, _ = sp.sam_plants(bgr, blobs3, sam, sf, oy)
    secs["sam21"] = time.perf_counter() - t

    def contours(pl):
        cnts, _ = cv2.findContours(pl["mask"].astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return max(cnts, key=cv2.contourArea) + np.int32([pl["x"], pl["y"]])

    found["sam21"] = [obj(pl["cx"], pl["cy"] - oy, pl["area_px"], contour=contours(pl)) for pl in plants]
    t = time.perf_counter()
    seg = ExGSegmenter()
    green = []
    for pl in plants:
        x, y, m = pl["x"], pl["y"], pl["mask"]
        g = seg.segment(cv2.cvtColor(bgr[y : y + m.shape[0], x : x + m.shape[1]], cv2.COLOR_BGR2RGB))
        green.append(obj(pl["cx"], pl["cy"] - oy, (g & m).sum(), contour=contours(pl)))
    found["sam21_green"] = green
    secs["sam21_green"] = secs["sam21"] + time.perf_counter() - t

    counts = {m: by_tray(found[m], trays, oy, sf) for m in METHODS}
    for i, m in enumerate(METHODS, 1):
        c = counts[m]
        tot = sum(c[k][0] for k in range(1, 7) if k in c)
        picture(bgr, found[m], trays, c, oy, f"{still.stem}  {m}: trays 1-6 {tot} plants (true 114), "
                f"{secs[m]:.0f} s", out / f"{i:02d}_{m}.jpg")

    rig = {t["tray_id"]: t.get("area_mm2") for t in rig_reading["trays"]} if rig_reading else {}
    tray_ids = sorted(counts[METHODS[0]])
    with open(out / "per_tray.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["tray", "slot", "true_plants", *[f"{m}_plants" for m in METHODS], *[f"{m}_mm2" for m in METHODS], "rig_reading_mm2"])
        slots = {tp.tray_id: tp.slot for tp, _ in trays}
        for k in tray_ids:
            wr.writerow([k, slots[k], TRUTH.get(k, ""), *[counts[m][k][0] for m in METHODS],
                         *[round(counts[m][k][1], 1) for m in METHODS], round(rig[k], 1) if rig.get(k) is not None else ""])
    summary = {}
    for m in METHODS:
        c = counts[m]
        err = [c[k][0] - TRUTH[k] for k in TRUTH if k in c]
        summary[m] = {"trays_1_6_plants": sum(c[k][0] for k in range(1, 7)), "tray_7": c[7][0], "tray_8": c[8][0],
                      "mean_abs_error_trays_1_8": round(float(np.mean(np.abs(err))), 2),
                      "worst_tray_error": int(max(err, key=abs)), "seconds": round(secs[m], 1),
                      "benchy_4_largest_mm2": [round(a) for a in c[8][2][:4]]}
    notes = {"still": str(still), "truth": TRUTH, "iphone_benchy_mm2": sp.IPHONE_MM2,
             "scan_benchy_mm2": {"NE": 2009.9, "SE": 1343.7, "NW": 753.4, "SW": 413.7},
             "shared_seconds": round(secs["shared: read, tags, trays, crop"], 1), "methods": summary}
    (out / "summary.json").write_text(json.dumps(notes, indent=1))
    for m, s in summary.items():
        print(f"{m:14s} trays1-6 {s['trays_1_6_plants']:3d}/114  t7 {s['tray_7']:2d}/7  t8 {s['tray_8']:2d}/5  "
              f"MAE {s['mean_abs_error_trays_1_8']:5.2f}  worst {s['worst_tray_error']:+d}  {s['seconds']:6.1f} s  "
              f"benchy {s['benchy_4_largest_mm2']}", flush=True)
    print("shared", notes["shared_seconds"], "s", flush=True)


def main():
    from hailo_platform import VDevice

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("still", type=Path)
    for a_ in ("--fastsam-hef", "--clip", "--sam", "--calibration", "--slots", "--out"):
        ap.add_argument(a_, type=Path, required=True)
    ap.add_argument("--rig-reading", type=Path)
    a = ap.parse_args()
    fp.BLOB_MIN_MM2 = 0.5
    a.out.mkdir(parents=True, exist_ok=False)
    placing = (load_calibration(a.calibration).scale_field, json.loads(a.slots.read_text())["slots"])
    rig = json.loads(a.rig_reading.read_text()) if a.rig_reading else None
    vocab = json.loads((a.clip / "clip_tokenizer.json").read_text())["model"]["vocab"]
    lut = np.load(a.clip / "token_embedding_lut.npy", allow_pickle=False)
    proj = np.load(a.clip / "text_projection.npy", allow_pickle=False)
    device = VDevice()
    fastsam = fp.FastSam(a.fastsam_hef, device)
    image_net = cp.HailoNet(device, a.clip / "clip_vit_b_32_image_encoder.hef", input_float=False)
    text_net = cp.HailoNet(device, a.clip / "clip_vit_b_32_text_encoder.hef", input_float=True)
    try:
        texts = {w: cp.text_embedding(w, text_net, vocab, lut, proj) for w in cp.PROMPTS + cp.BACKGROUND}
        sam = sp.Sam21(a.sam)
        run(a.still, (fastsam, image_net, texts, sam), placing, rig, a.out / a.still.stem)
    finally:
        text_net.close()
        image_net.close()
        fastsam.close()
        device.release()


if __name__ == "__main__":
    main()
