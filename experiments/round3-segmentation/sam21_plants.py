"""Issue #297: the supervisor's method, SAM 2.1 small through ONNX Runtime on the CPU, with prompts
from colour: each green blob of the green threshold in use gives a box and a point; one image
embedding per tile is cached and used for every prompt in it; overlapping masks are merged into
one plant; plants are counted per tray and measured in mm2.

    PYTHONPATH=~/npec_camera_rig/src:DIR venv/bin/python DIR/sam21_plants.py --sam MODELS \
        --calibration C --slots S --out NEW_FOLDER still.jpg [...]

MODELS: onnx-community/sam2.1-hiera-small-ONNX, onnx/vision_encoder.onnx and
prompt_encoder_mask_decoder.onnx (with their .onnx_data). Preprocessing as the transformers
Sam2Processor: RGB resized to 1024 x 1024, scaled to 0..1, ImageNet mean and standard deviation.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

import fastsam_plants as fp
from npec_rig.calibration_store import load_calibration
from npec_rig.tags import detect_tags

SAM_PX = 1024
LOW_PX = 256  # the decoder's mask size
MEAN = np.float32([0.485, 0.456, 0.406])
STD = np.float32([0.229, 0.224, 0.225])
# Decisions for a first run, not measured optima.
GRID = (3, 2)  # tiles across the tray rows: about two trays per tile, about 3x reduced
OVERLAP_PX = 300  # tiles overlap by this much at full size, so a plant near an edge lies whole in one
BOX_PAD = 0.25  # each blob's box widened by this fraction per side for the box prompt
BOX_PAD_MIN_PX = 12
MERGE_OVERLAP = 0.3  # two masks are one plant when they share this fraction of the smaller one
# Known contents on 2026-10-29 (Aaron): trays 1 to 6, 19 plants; tray 7 (North 5) 6 plants and a
# green benchmark; tray 8, the Benchy: 4 plastic rosettes and a green benchmark.
TRUTH = {1: 19, 2: 19, 3: 19, 4: 19, 5: 19, 6: 19, 7: 7, 8: 5}
IPHONE_MM2 = {"NE": 1692.05, "SE": 1064.17, "NW": 611.92, "SW": 325.37}  # metrology log 17.14


def tiles(w, h):
    """GRID tiles over w x h with OVERLAP_PX overlap: (x0, y0, x1, y1)."""
    nx, ny = GRID
    tw, th = (w + (nx - 1) * OVERLAP_PX) / nx, (h + (ny - 1) * OVERLAP_PX) / ny
    return [(int(i * (tw - OVERLAP_PX)), int(j * (th - OVERLAP_PX)),
             int(min(w, i * (tw - OVERLAP_PX) + tw)), int(min(h, j * (th - OVERLAP_PX) + th)))
            for j in range(ny) for i in range(nx)]


def home_tile(box, ts):
    """The tile holding the box whole with its centre furthest from the tile's edges."""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    best = None
    for k, (x0, y0, x1, y1) in enumerate(ts):
        whole = box[0] >= x0 and box[1] >= y0 and box[2] <= x1 and box[3] <= y1
        room = min(cx - x0, x1 - cx, cy - y0, y1 - cy)
        key = (whole, room)
        if best is None or key > best[0]:
            best = (key, k)
    return best[1]


class Sam21:
    def __init__(self, models: Path, threads=4):
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        p = ["CPUExecutionProvider"]
        self.enc = ort.InferenceSession(str(models / "vision_encoder.onnx"), so, providers=p)
        self.dec = ort.InferenceSession(str(models / "prompt_encoder_mask_decoder.onnx"), so, providers=p)

    def embed(self, rgb):
        x = cv2.resize(rgb, (SAM_PX, SAM_PX), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
        x = ((x - MEAN) / STD).transpose(2, 0, 1)[None]
        out = self.enc.run(None, {"pixel_values": np.ascontiguousarray(x)})
        return {f"image_embeddings.{i}": a for i, a in enumerate(out)}

    def mask(self, emb, box, point):
        """Best of the decoder's three masks for one box and point (1024 coordinates): its low-res
        logits (256 x 256), predicted IoU and object score."""
        iou, masks, obj = self.dec.run(None, dict(
            emb, input_boxes=np.float32([[box]]), input_points=np.float32([[[point]]]),
            input_labels=np.ones((1, 1, 1), np.int64)))
        k = int(iou[0, 0].argmax())
        return masks[0, 0, k], float(iou[0, 0, k]), float(obj[0, 0, 0])


def full_mask(logits, tile, box):
    """The mask inside `box` (full-size px, a little widened), at full size: (x0, y0, bool array).
    Logits cover the whole tile at 256 x 256; only the box's part is enlarged."""
    tx0, ty0, tx1, ty1 = tile
    sx, sy = LOW_PX / (tx1 - tx0), LOW_PX / (ty1 - ty0)
    x0, y0, x1, y1 = (int(max(tx0, box[0])), int(max(ty0, box[1])), int(min(tx1, box[2])), int(min(ty1, box[3])))
    # low-res window with a cell of margin, enlarged to the full-size window
    lx0, ly0 = max(0, int((x0 - tx0) * sx) - 1), max(0, int((y0 - ty0) * sy) - 1)
    lx1, ly1 = min(LOW_PX, int(np.ceil((x1 - tx0) * sx)) + 1), min(LOW_PX, int(np.ceil((y1 - ty0) * sy)) + 1)
    win = logits[ly0:ly1, lx0:lx1]
    fx0, fy0 = tx0 + lx0 / sx, ty0 + ly0 / sy
    fw, fh = int(round((lx1 - lx0) / sx)), int(round((ly1 - ly0) / sy))
    big = cv2.resize(win, (fw, fh), interpolation=cv2.INTER_LINEAR) > 0
    return int(fx0), int(fy0), big


def overlap(a, b):
    """Shared pixels of two masks over the smaller mask's pixels."""
    ax, ay, am = a
    bx, by, bm = b
    x0, y0 = max(ax, bx), max(ay, by)
    x1, y1 = min(ax + am.shape[1], bx + bm.shape[1]), min(ay + am.shape[0], by + bm.shape[0])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    s = (am[y0 - ay : y1 - ay, x0 - ax : x1 - ax] & bm[y0 - by : y1 - by, x0 - bx : x1 - bx]).sum()
    return s / max(1, min(am.sum(), bm.sum()))


def merge(masks):
    """Groups of mask indices: masks sharing MERGE_OVERLAP of the smaller one, chained."""
    parent = list(range(len(masks)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(masks)):
        for j in range(i + 1, len(masks)):
            if overlap(masks[i], masks[j]) >= MERGE_OVERLAP:
                parent[find(i)] = find(j)
    groups = {}
    for i in range(len(masks)):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def union(masks, idx):
    x0 = min(masks[i][0] for i in idx)
    y0 = min(masks[i][1] for i in idx)
    x1 = max(masks[i][0] + masks[i][2].shape[1] for i in idx)
    y1 = max(masks[i][1] + masks[i][2].shape[0] for i in idx)
    m = np.zeros((y1 - y0, x1 - x0), bool)
    for i in idx:
        x, y, a = masks[i]
        m[y - y0 : y - y0 + a.shape[0], x - x0 : x - x0 + a.shape[1]] |= a
    return x0, y0, m


def run(still, sam, placing, out: Path):
    out.mkdir(parents=True, exist_ok=False)
    t = {}
    t0 = time.perf_counter()
    full = cv2.imread(str(still))
    t["read"] = time.perf_counter() - t0
    t1 = time.perf_counter()
    tags = detect_tags(cv2.cvtColor(full, cv2.COLOR_BGR2RGB))
    trays = fp.trays_of(tags, placing)
    bgr, crop, n = fp.crop_to_corner_tags(full, tags)
    t["tags_and_trays"] = time.perf_counter() - t1
    if bgr is None:
        print(f"{still.name}: {n} corner tags, skipped", flush=True)
        return
    oy = crop[1]
    t2 = time.perf_counter()
    _, blobs = fp.exg_blobs(bgr)
    t["green_blobs"] = time.perf_counter() - t2

    plants, masks, prompts, n_enc, tt = sam_plants(bgr, blobs, sam, placing[0], oy)
    t.update(tt)
    t["total"] = time.perf_counter() - t0
    h, w = bgr.shape[:2]

    per_tray = []
    for tp, tag in trays:
        inside = [pl for pl in plants if cv2.pointPolygonTest(np.float32(tp.outline), (pl["cx"], pl["cy"]), False) >= 0]
        per_tray.append((tp, tag, inside))
    run_pictures(still, bgr, oy, plants, masks, blobs, per_tray, t, prompts, n_enc, out)


def sam_plants(bgr, blobs, sam, scale_field, oy):
    """Plants from SAM 2.1 with a box and point prompt per green blob, one embedding per tile,
    overlapping masks merged. Each plant: its mask (x, y, bool array, cropped still), centre in the
    uncropped still, area in px and mm2. Also the masks, prompts, tiles encoded and timings."""
    t = {}
    h, w = bgr.shape[:2]
    ts = tiles(w, h)
    prompts = []
    for b in blobs:
        bw, bh = b["x1"] - b["x0"], b["y1"] - b["y0"]
        px, py = max(BOX_PAD_MIN_PX, BOX_PAD * bw), max(BOX_PAD_MIN_PX, BOX_PAD * bh)
        box = (max(0, b["x0"] - px), max(0, b["y0"] - py), min(w, b["x1"] + px), min(h, b["y1"] + py))
        prompts.append({"blob": b, "box": box, "tile": home_tile(box, ts)})
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    masks, info, t_enc, t_dec, n_enc = [], [], 0.0, 0.0, 0
    for k, tile in enumerate(ts):
        mine = [p for p in prompts if p["tile"] == k]
        if not mine:
            continue
        x0, y0, x1, y1 = tile
        te = time.perf_counter()
        emb = sam.embed(rgb[y0:y1, x0:x1])
        t_enc += time.perf_counter() - te
        n_enc += 1
        sx, sy = SAM_PX / (x1 - x0), SAM_PX / (y1 - y0)
        for p in mine:
            bx = p["box"]
            td = time.perf_counter()
            logits, iou, obj = sam.mask(emb, [(bx[0] - x0) * sx, (bx[1] - y0) * sy, (bx[2] - x0) * sx, (bx[3] - y0) * sy],
                                        [(p["blob"]["cx"] - x0) * sx, (p["blob"]["cy"] - y0) * sy])
            t_dec += time.perf_counter() - td
            m = full_mask(logits, tile, bx)
            if m[2].any():
                masks.append(m)
                info.append({"iou": iou, "object_score": obj, "blob_area_px": p["blob"]["area_px"]})
    t["sam_encode"], t["sam_decode"] = t_enc, t_dec
    t3 = time.perf_counter()
    groups = merge(masks)
    plants = []
    for g in groups:
        ux, uy, um = union(masks, g)
        ys, xs = np.nonzero(um)
        cx, cy = ux + xs.mean(), uy + ys.mean() + oy  # uncropped still
        ppm = scale_field.px_per_mm(cx, cy)
        plants.append({"x": ux, "y": uy, "mask": um, "cx": cx, "cy": cy, "masks": len(g),
                       "area_px": int(um.sum()), "area_mm2": float(um.sum()) / ppm**2,
                       "green_px": sum(info[i]["blob_area_px"] for i in g), "ppm": ppm})
    t["merge_and_measure"] = time.perf_counter() - t3
    return plants, masks, prompts, n_enc, t


def run_pictures(still, bgr, oy, plants, masks, blobs, per_tray, t, prompts, n_enc, out):
    h, w = bgr.shape[:2]

    # pictures: whole rows at 1/4, and the Benchy's tray at full size
    f = 1 / fp.VIEW_REDUCE
    im = cv2.resize(bgr, (w // fp.VIEW_REDUCE, h // fp.VIEW_REDUCE), interpolation=cv2.INTER_AREA)

    def outline(img, pl, scale, ox, oyy, col, lw):
        cnts, _ = cv2.findContours(pl["mask"].astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            cv2.drawContours(img, [((c + np.int32([pl["x"] - ox, pl["y"] - oyy])) * scale).astype(np.int32)], -1, col, lw)

    for pl in plants:
        outline(im, pl, f, 0, 0, (0, 255, 0), 2)
    for tp, tag, inside in per_tray:
        o = (np.float32(tp.outline) - np.float32([0, oy])) * f
        cv2.polylines(im, [o.astype(np.int32)], True, (255, 255, 0), 3)
        truth = TRUTH.get(tp.tray_id)
        lab = f"tray {tp.tray_id}: {len(inside)}" + (f" (true {truth})" if truth is not None else "")
        org = (int(tp.centre[0] * f) - 90, int((tp.centre[1] - oy) * f))
        cv2.putText(im, lab, org, cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 6)
        cv2.putText(im, lab, org, cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.rectangle(im, (0, 0), (im.shape[1], 30), (0, 0, 0), -1)
    cv2.putText(im, f"{still.stem}  SAM 2.1 small, prompts from green blobs: {len(plants)} plants from {len(masks)} masks "
                f"({len(blobs)} blobs), {t['total']:.0f} s", (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    cv2.imwrite(str(out / "1_sam21_plants.jpg"), im, [cv2.IMWRITE_JPEG_QUALITY, 85])
    benchy = next(((tp, inside) for tp, _, inside in per_tray if tp.tray_id == 8), None)
    if benchy:
        tp, inside = benchy
        xs, ys = [x for x, _ in tp.outline], [y - oy for _, y in tp.outline]
        bx0, by0, bx1, by1 = int(max(0, min(xs))), int(max(0, min(ys))), int(min(w, max(xs))), int(min(h, max(ys)))
        cut = bgr[by0:by1, bx0:bx1].copy()
        for pl in inside:
            outline(cut, pl, 1.0, bx0, by0, (0, 255, 0), 3)
            org = (int(pl["cx"] - bx0) - 60, int(pl["cy"] - oy - by0))
            cv2.putText(cut, f"{pl['area_mm2']:.0f} mm2", org, cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 8)
            cv2.putText(cut, f"{pl['area_mm2']:.0f} mm2", org, cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3)
        cv2.imwrite(str(out / "2_tray8_benchy_closeup.jpg"), cut, [cv2.IMWRITE_JPEG_QUALITY, 85])

    with open(out / "plants.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["tray", "slot", "cx_px", "cy_px", "masks_merged", "area_px", "area_mm2", "green_px", "px_per_mm"])
        for tp, _, inside in per_tray:
            for pl in inside:
                wr.writerow([tp.tray_id, tp.slot, round(pl["cx"]), round(pl["cy"]), pl["masks"], pl["area_px"],
                             round(pl["area_mm2"], 1), round(pl["green_px"]), round(pl["ppm"], 3)])
    notes = {
        "still": str(still), "model": "sam2.1-hiera-small ONNX (onnx-community), full precision, CPU 4 threads",
        "grid": GRID, "overlap_px": OVERLAP_PX, "tiles_encoded": n_enc, "prompts": len(prompts),
        "box_pad": BOX_PAD, "merge_overlap": MERGE_OVERLAP, "blob_min_mm2": fp.BLOB_MIN_MM2, "join_mm": fp.JOIN_MM,
        "masks": len(masks), "plants": len(plants),
        "trays": {f"{tp.tray_id} {tp.slot}": {"plants": len(inside), "true": TRUTH.get(tp.tray_id)} for tp, _, inside in per_tray},
        "benchy_tray8_mm2": sorted((round(pl["area_mm2"], 1) for pl in (benchy[1] if benchy else [])), reverse=True),
        "iphone_mm2": IPHONE_MM2,
        "seconds": {k: round(v, 1) for k, v in t.items()},
    }
    (out / "notes.json").write_text(json.dumps(notes, indent=1))
    print(json.dumps({k: notes[k] for k in ("plants", "masks", "prompts", "tiles_encoded", "trays", "benchy_tray8_mm2", "seconds")}), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("stills", nargs="+", type=Path)
    ap.add_argument("--sam", type=Path, required=True)
    ap.add_argument("--calibration", type=Path, required=True)
    ap.add_argument("--slots", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--blob-min", type=float, default=0.5)
    ap.add_argument("--join-mm", type=float, default=3.0)
    a = ap.parse_args()
    fp.BLOB_MIN_MM2, fp.JOIN_MM = a.blob_min, a.join_mm
    a.out.mkdir(parents=True, exist_ok=False)
    placing = (load_calibration(a.calibration).scale_field, json.loads(a.slots.read_text())["slots"])
    sam = Sam21(a.sam)
    for s in a.stills:
        run(s, sam, placing, a.out / s.stem)


if __name__ == "__main__":
    main()
