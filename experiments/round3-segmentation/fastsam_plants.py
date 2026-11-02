"""Issue #297: FastSAM on the Hailo-8 against the green threshold, on whole stills of plants.

FastSAM has no classes: it outlines every "object". Three pictures per still:

    1 all       every FastSAM box
    2 exg       every green blob from the green threshold in use (ExGSegmenter, EXG_MIN)
    3 prompted  for each green blob, the smallest FastSAM mask holding the blob's centre
                (a point prompt, as FastSAM's own point mode)

Runs on a rig with a Hailo-8 (development, npec-rig-01). Stills are read only; everything is
written to a new folder under --out.

    PYTHONPATH=~/npec_camera_rig/src python3 fastsam_plants.py --hef fast_sam_s.hef \
        --out ~/sam297/out/RUN still.jpg [still.jpg ...]

Decoding (decode, nms, masks_for, FastSam) is round 1's (experiments/round1-trays/fastsam.py),
copied so this runs without round 1's session files.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import cv2
import numpy as np

from npec_rig.segmentation import EXG_MIN, ExGSegmenter
from npec_rig.calibration_store import load_calibration
from npec_rig.tags import CORNER_ID_RANGE, TRAY_ID_RANGE, detect_tags, tag_side_px
from npec_rig.tray_placement import place_trays

SIZE = 640
STRIDES = (8, 16, 32)
# Decisions for a first look, not measured optima.
TILE_PX = 1280  # tile side at full resolution: 2 full px per model px
STEP_PX = 960  # tiles overlap by a quarter
SCORE_MIN = 0.25  # FastSAM's usual default confidence
IOU_MAX = 0.7  # FastSAM's usual default for duplicates, within a tile and across tiles
EDGE_PX = 4  # a box this close to an inner tile edge is cut by the tile and dropped
EXG_REDUCE = 2  # green threshold on a half-size copy, for memory
BLOB_MIN_MM2 = 4.0  # green blobs smaller than this are ignored
JOIN_MM = 0.0  # green pieces closer than this are one blob (one plant); 0 joins nothing
PX_PER_MM = 4.86  # about, at tray-top height (round 1); only for the blob size cut
VIEW_REDUCE = 4  # whole-still pictures at quarter size
ZOOM = (0.30, 0.30, 0.70, 0.70)  # close-up: this part of the still, at full size
TAG_PAD = 1.5  # --crop-tags: grey square over each corner tag, this many tag sides from its centre
GREY = 114


# ---------------------------------------------------------------- round 1 decoding


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def dfl_distances(bins: np.ndarray) -> np.ndarray:
    b = bins.reshape(-1, 4, 16)
    b = np.exp(b - b.max(axis=2, keepdims=True))
    b /= b.sum(axis=2, keepdims=True)
    return (b * np.arange(16)).sum(axis=2)


def decode(outputs):
    by_grid, protos = {}, None
    for a in outputs.values():
        a = a.reshape(a.shape[-3:])
        h, _, c = a.shape
        if h == SIZE // 4 and c == 32:
            protos = a
        else:
            by_grid.setdefault(h, {})[c] = a
    boxes, scores, coefs = [], [], []
    for stride in STRIDES:
        g, n = by_grid[SIZE // stride], SIZE // stride
        ys, xs = np.mgrid[0:n, 0:n]
        cx, cy = xs.ravel() + 0.5, ys.ravel() + 0.5
        d = dfl_distances(g[64].reshape(-1, 64))
        boxes.append(np.stack([cx - d[:, 0], cy - d[:, 1], cx + d[:, 2], cy + d[:, 3]], 1) * stride)
        s = g[1].reshape(-1)
        scores.append(s if (s.min() >= 0 and s.max() <= 1) else sigmoid(s))
        coefs.append(g[32].reshape(-1, 32))
    return np.concatenate(boxes), np.concatenate(scores), np.concatenate(coefs), protos


def nms(boxes, scores, iou_max):
    keep = cv2.dnn.NMSBoxes(
        [[float(x0), float(y0), float(x1 - x0), float(y1 - y0)] for x0, y0, x1, y1 in boxes],
        scores.astype(float).tolist(), 0.0, iou_max)
    return [int(i) for i in np.array(keep).ravel()]


def masks_for(boxes, coefs, protos):
    m = sigmoid(np.einsum("kc,hwc->khw", coefs, protos))
    out = np.zeros((len(boxes), SIZE, SIZE), bool)
    for k, (x0, y0, x1, y1) in enumerate(boxes):
        up = cv2.resize(m[k], (SIZE, SIZE), interpolation=cv2.INTER_LINEAR) > 0.5
        bx0, by0 = max(0, int(x0)), max(0, int(y0))
        bx1, by1 = min(SIZE, int(np.ceil(x1))), min(SIZE, int(np.ceil(y1)))
        out[k, by0:by1, bx0:bx1] = up[by0:by1, bx0:bx1]
    return out


class FastSam:
    """FastSAM through HailoRT's InferModel API: the Hailo-10H (HailoRT 5) has no other; the
    Hailo-8 (HailoRT 4.23) has it too. Round 1's InferVStreams fails on the Hailo-10H with
    HAILO_NOT_IMPLEMENTED."""

    def __init__(self, hef_path, device=None):
        from hailo_platform import FormatType, VDevice

        self.own_device = device is None
        self.device = VDevice() if device is None else device
        self.im = self.device.create_infer_model(str(hef_path))
        self.im.input().set_format_type(FormatType.UINT8)
        for n in self.im.output_names:
            self.im.output(n).set_format_type(FormatType.FLOAT32)
        self._ctx = self.im.configure()
        self.cm = self._ctx.__enter__()
        self.outs = {n: np.empty(self.im.output(n).shape, np.float32) for n in self.im.output_names}

    def __call__(self, rgb640):
        b = self.cm.create_bindings(output_buffers=self.outs)
        b.input().set_buffer(np.ascontiguousarray(rgb640, dtype=np.uint8))
        self.cm.run([b], 10000)
        return {n: b.output(n).get_buffer().copy() for n in self.outs}

    def close(self):
        self._ctx.__exit__(None, None, None)
        if self.own_device:
            self.device.release()


# ---------------------------------------------------------------- this experiment


def starts(length, size, step):
    if length <= size:
        return [0]
    out = list(range(0, length - size, step))
    return out + [length - size]


def fastsam_all(bgr, model):
    """Every FastSAM object in the still: box, score, area and outline in full-size px."""
    h, w = bgr.shape[:2]
    dets, t_hailo = [], 0.0
    for y0 in starts(h, TILE_PX, STEP_PX):
        for x0 in starts(w, TILE_PX, STEP_PX):
            crop = bgr[y0 : y0 + TILE_PX, x0 : x0 + TILE_PX]
            s = SIZE / TILE_PX
            tile = cv2.cvtColor(cv2.resize(crop, (SIZE, SIZE), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
            ti = time.perf_counter()
            raw = model(tile)
            t_hailo += time.perf_counter() - ti
            boxes, scores, coefs, protos = decode(raw)
            sel = np.nonzero(scores >= SCORE_MIN)[0]
            if not len(sel):
                continue
            keep = sel[nms(boxes[sel], scores[sel], IOU_MAX)]
            # Drop boxes cut by an inner tile edge; a neighbouring tile holds them whole.
            b = boxes[keep]
            cut = (((b[:, 0] < EDGE_PX) & (x0 > 0)) | ((b[:, 1] < EDGE_PX) & (y0 > 0))
                   | ((b[:, 2] > SIZE - EDGE_PX) & (x0 + TILE_PX < w))
                   | ((b[:, 3] > SIZE - EDGE_PX) & (y0 + TILE_PX < h)))
            keep = keep[~cut]
            for k, m in zip(keep, masks_for(boxes[keep], coefs[keep], protos)):
                cnts, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if not cnts:
                    continue
                c = max(cnts, key=cv2.contourArea)
                x, y, bw, bh = cv2.boundingRect(c)
                dets.append({"score": float(scores[k]), "x0": x0 + x / s, "y0": y0 + y / s,
                             "x1": x0 + (x + bw) / s, "y1": y0 + (y + bh) / s,
                             "area_px": float(m.sum()) / s**2,
                             "contour": (c.astype(np.float32) / s + np.float32([x0, y0])).astype(np.int32)})
    if dets:  # duplicates from overlapping tiles
        b = np.array([[d["x0"], d["y0"], d["x1"], d["y1"]] for d in dets])
        dets = [dets[i] for i in nms(b, np.array([d["score"] for d in dets]), IOU_MAX)]
    return dets, t_hailo


def exg_blobs(bgr, segment=None):
    """Green blobs from the green threshold in use (or `segment`, rgb -> bool), on a half-size
    copy; boxes in full-size px."""
    r = EXG_REDUCE
    small = cv2.resize(bgr, (bgr.shape[1] // r, bgr.shape[0] // r), interpolation=cv2.INTER_AREA)
    mask = (segment or ExGSegmenter().segment)(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
    # Joining: pieces grown by half the join distance touch when closer than it. Areas, boxes and
    # the prompt point come from the green pixels only.
    grown = mask.astype(np.uint8)
    d = int(round(JOIN_MM * PX_PER_MM / r))
    if d > 0:
        grown = cv2.dilate(grown, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (d + 1, d + 1)))
    n, labels = cv2.connectedComponents(grown, connectivity=8)
    ys, xs = np.nonzero(mask)
    lab = labels[ys, xs]
    order = np.argsort(lab, kind="stable")
    ys, xs, lab = ys[order], xs[order], lab[order]
    cuts = np.searchsorted(lab, np.arange(1, n + 1))
    min_px = BLOB_MIN_MM2 * PX_PER_MM**2 / r**2
    blobs = []
    for i in range(1, n):
        by, bx = ys[cuts[i - 1] : cuts[i]], xs[cuts[i - 1] : cuts[i]]
        if len(bx) < min_px:
            continue
        mx, my = bx.mean(), by.mean()
        k = int(np.argmin((bx - mx) ** 2 + (by - my) ** 2))  # green pixel nearest the centre
        blobs.append({"x0": int(bx.min()) * r, "y0": int(by.min()) * r, "x1": (int(bx.max()) + 1) * r,
                      "y1": (int(by.max()) + 1) * r, "area_px": float(len(bx)) * r * r,
                      "cx": (bx[k] + 0.5) * r, "cy": (by[k] + 0.5) * r})
    return mask, blobs


def prompted(dets, blobs):
    """For each blob, the smallest FastSAM mask holding its centre, or None."""
    out = []
    for b in blobs:
        hits = [d for d in dets if d["x0"] <= b["cx"] <= d["x1"] and d["y0"] <= b["cy"] <= d["y1"]
                and cv2.pointPolygonTest(d["contour"], (float(b["cx"]), float(b["cy"])), False) >= 0]
        out.append(min(hits, key=lambda d: d["area_px"]) if hits else None)
    return out


def draw(bgr, kind, dets, mask, blobs, picks, title, out: Path, region=None, trays=(), shift=(0, 0)):
    """One picture: the whole still at 1/VIEW_REDUCE, or `region` (x0, y0, x1, y1) at full size."""
    if region is None:
        f, ox, oy = 1 / VIEW_REDUCE, 0, 0
        im = cv2.resize(bgr, (bgr.shape[1] // VIEW_REDUCE, bgr.shape[0] // VIEW_REDUCE), interpolation=cv2.INTER_AREA)
    else:
        f, (ox, oy, rx, ry) = 1.0, region
        im = bgr[oy:ry, ox:rx].copy()
    lw = 2 if region is None else 3
    P = lambda x, y: (int((x - ox) * f), int((y - oy) * f))
    if kind == "all":
        for d in dets:
            col = (0, 255, 255) if d["score"] >= 0.5 else (0, 165, 255)
            cv2.rectangle(im, P(d["x0"], d["y0"]), P(d["x1"], d["y1"]), col, lw)
    elif kind == "exg":
        m = cv2.resize(mask.astype(np.uint8), (bgr.shape[1], bgr.shape[0]) if region else (im.shape[1], im.shape[0]),
                       interpolation=cv2.INTER_NEAREST)
        if region is not None:
            m = m[oy:ry, ox:rx]
        im[m > 0] = (0.5 * im[m > 0] + (0, 127, 127)).astype(np.uint8)
        for b in blobs:
            cv2.rectangle(im, P(b["x0"], b["y0"]), P(b["x1"], b["y1"]), (255, 0, 255), lw)
    else:
        for b, d in zip(blobs, picks):
            c = P(b["cx"], b["cy"])
            if d is None:
                cv2.drawMarker(im, c, (0, 0, 255), cv2.MARKER_TILTED_CROSS, 18, lw)
                continue
            cnt = ((d["contour"] - np.int32([ox, oy])) * f).astype(np.int32)
            cv2.drawContours(im, [cnt], -1, (0, 255, 0), lw)
            cv2.rectangle(im, P(d["x0"], d["y0"]), P(d["x1"], d["y1"]), (255, 255, 0), 1)
            cv2.circle(im, c, 4, (255, 0, 255), -1)
        sx, sy = shift  # trays are placed in the uncropped still
        for p, tag, n in trays:
            o = np.array([P(x - sx, y - sy) for x, y in p.outline], np.int32)
            cv2.polylines(im, [o], True, (255, 255, 0), lw + 1)
            cv2.polylines(im, [np.array([P(x - sx, y - sy) for x, y in tag.corners], np.int32)], True, (0, 0, 255), lw + 1)
            lab = f"tray {p.tray_id} {p.slot} {p.a1_corner}: {n} blobs" + ("" if p.status == "placed" else f" ({p.status})")
            org = P(p.centre[0] - sx - 140 / f, p.centre[1] - sy)
            for col, th in (((0, 0, 0), 5), ((255, 255, 255), 1 if region is None else 2)):
                cv2.putText(im, lab, org, cv2.FONT_HERSHEY_SIMPLEX, 0.6 if region is None else 1.2, col, th)
    cv2.rectangle(im, (0, 0), (im.shape[1], 30), (0, 0, 0), -1)
    cv2.putText(im, title, (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    cv2.imwrite(str(out), im, [cv2.IMWRITE_JPEG_QUALITY, 85])


def crop_to_corner_tags(bgr, all_tags):
    """The still without the strips above the highest and below the lowest corner tag (full
    width kept, so edge trays stay), each tag (and its green holder) painted grey; and the crop
    box (x0, y0, x1, y1) in full-size px. None if not 4 tags."""
    tags = [t for t in all_tags if t.tag_id in CORNER_ID_RANGE]
    if len(tags) != 4:
        return None, None, len(tags)
    ys = [y for t in tags for _, y in t.corners]
    x0, x1 = 0, bgr.shape[1]
    y0, y1 = int(min(ys)), int(np.ceil(max(ys)))
    out = bgr[y0:y1, x0:x1].copy()
    for t in tags:
        r = TAG_PAD * tag_side_px(t.corners)
        cx, cy = t.centre[0] - x0, t.centre[1] - y0
        cv2.rectangle(out, (int(cx - r), int(cy - r)), (int(cx + r), int(cy + r)), (GREY,) * 3, -1)
    return out, (x0, y0, x1, y1), 4


def trays_of(tags, placing):
    """Each tray placed by the rig's own routine (tray_placement.place_trays) from its A1 tag,
    with the tag: [(TrayPlacement, TagDetection)]. Empty without a calibration and slot layout."""
    if placing is None:
        return []
    scale_field, slots = placing
    by_id = {t.tag_id: t for t in tags if t.tag_id in TRAY_ID_RANGE}
    return [(p, by_id[p.tray_id]) for p in place_trays(list(by_id.values()), scale_field, slots)]


def run(still: Path, model, out: Path, crop_tags: bool = False, placing=None):
    out.mkdir(parents=True, exist_ok=False)
    t0 = time.perf_counter()
    bgr = cv2.imread(str(still))
    crop = None
    tags = detect_tags(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)) if (crop_tags or placing) else []
    trays = trays_of(tags, placing)
    if crop_tags:
        bgr, crop, n = crop_to_corner_tags(bgr, tags)
        if bgr is None:
            print(f"{still.name}: {n} corner tags found, not 4; skipped", flush=True)
            (out / "notes.json").write_text(json.dumps({"still": str(still), "skipped": f"{n} corner tags"}))
            return
    t1 = time.perf_counter()
    dets, t_hailo = fastsam_all(bgr, model)
    t2 = time.perf_counter()
    mask, blobs = exg_blobs(bgr)
    t3 = time.perf_counter()
    picks = prompted(dets, blobs)
    h, w = bgr.shape[:2]
    zoom = (int(ZOOM[0] * w), int(ZOOM[1] * h), int(ZOOM[2] * w), int(ZOOM[3] * h))
    n_hit = sum(p is not None for p in picks)
    oy = crop[1] if crop else 0
    tray_rows = [(p, tag, sum(cv2.pointPolygonTest(np.float32(p.outline), (float(b["cx"]), float(b["cy"] + oy)), False) >= 0
                              for b in blobs)) for p, tag in trays]
    titles = {
        "all": f"{still.stem}  1 FastSAM, every object: {len(dets)} boxes (yellow score >= 0.5, orange below)",
        "exg": f"{still.stem}  2 green threshold {EXG_MIN:g}: {len(blobs)} blobs >= {BLOB_MIN_MM2:g} mm2, joined within {JOIN_MM:g} mm (magenta)",
        "prompted": f"{still.stem}  3 FastSAM mask at each blob centre: {n_hit} of {len(blobs)} (green), red X none",
    }
    for i, kind in enumerate(("all", "exg", "prompted"), 1):
        tr = tray_rows if kind == "prompted" else ()
        draw(bgr, kind, dets, mask, blobs, picks, titles[kind], out / f"{i}_{kind}.jpg", trays=tr, shift=(0, oy))
        draw(bgr, kind, dets, mask, blobs, picks, titles[kind] + "  (close-up, full size)",
             out / f"{i}_{kind}_closeup.jpg", region=zoom, trays=tr, shift=(0, oy))
    with open(out / "detections.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["kind", "i", "score", "x0", "y0", "x1", "y1", "area_px", "blob_area_px", "fastsam_area_px"])
        for i, d in enumerate(dets):
            wr.writerow(["fastsam", i, round(d["score"], 3), *(round(d[k]) for k in ("x0", "y0", "x1", "y1")), round(d["area_px"]), "", ""])
        for i, (b, d) in enumerate(zip(blobs, picks)):
            wr.writerow(["blob", i, "", *(round(b[k]) for k in ("x0", "y0", "x1", "y1")), round(b["area_px"]),
                         round(b["area_px"]), round(d["area_px"]) if d else ""])
    notes = {
        "still": str(still), "size_px": [w, h],
        "crop": None if crop is None else {"box_full_px": crop, "between": "corner tag centres",
                                           "tags_greyed_tag_sides": TAG_PAD},
        "fastsam": {"hef": "fast_sam_s.hef (Hailo Model Zoo v2.17.0)", "tile_px": TILE_PX, "step_px": STEP_PX,
                    "score_min": SCORE_MIN, "iou_max": IOU_MAX, "objects": len(dets)},
        "green_threshold": {"exg_min": EXG_MIN, "on": f"1/{EXG_REDUCE} size copy", "blob_min_mm2": BLOB_MIN_MM2, "join_mm": JOIN_MM,
                            "blobs": len(blobs)},
        "prompt": "point at each blob centre; smallest FastSAM mask holding it",
        "blobs_with_mask": n_hit,
        "trays": [{"tray": p.tray_id, "slot": p.slot, "a1_corner": p.a1_corner, "status": p.status, "blobs_inside": n}
                  for p, _, n in tray_rows],
        "blobs_in_trays": sum(n for _, _, n in tray_rows),
        "close_up": f"x {ZOOM[0]:g}-{ZOOM[2]:g}, y {ZOOM[1]:g}-{ZOOM[3]:g} of the still",
        "seconds": {"read": round(t1 - t0, 1), "fastsam": round(t2 - t1, 1), "hailo": round(t_hailo, 1),
                    "green": round(t3 - t2, 1), "total": round(time.perf_counter() - t0, 1)},
    }
    (out / "notes.json").write_text(json.dumps(notes, indent=1))
    print(f"{still.name}: {len(dets)} objects, {len(blobs)} blobs, {n_hit} with a mask, {notes['seconds']}", flush=True)


def main():
    global BLOB_MIN_MM2, JOIN_MM
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("stills", nargs="+", type=Path)
    ap.add_argument("--hef", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True, help="new folder; one subfolder per still")
    ap.add_argument("--crop-tags", action="store_true", help="only between the corner tags, tags greyed")
    ap.add_argument("--blob-min", type=float, default=BLOB_MIN_MM2, help="smallest green blob, mm2")
    ap.add_argument("--calibration", type=Path, help="calibration JSON (copy), to place trays")
    ap.add_argument("--slots", type=Path, help="its slot layout JSON (copy), to place trays")
    ap.add_argument("--join-mm", type=float, default=JOIN_MM, help="join green pieces closer than this, mm")
    a = ap.parse_args()
    BLOB_MIN_MM2, JOIN_MM = a.blob_min, a.join_mm
    a.out.mkdir(parents=True, exist_ok=False)
    placing = None
    if a.calibration and a.slots:
        placing = (load_calibration(a.calibration).scale_field, json.loads(a.slots.read_text())["slots"])
    model = FastSam(a.hef)
    try:
        for s in a.stills:
            run(s, model, a.out / s.stem, a.crop_tags, placing if s.name.startswith("prod") else None)
    finally:
        model.close()


if __name__ == "__main__":
    main()
