"""Issue #297: text prompts ("foliage", "leaves", "plants") for FastSAM's objects, with CLIP on the
Hailo-10H, as FastSAM's own text mode does, but keeping every match instead of only the best.

Each FastSAM object is cut out (grey outside its mask), scored by CLIP ViT-B/32 against the prompt
and a few background words, and kept for that prompt when the prompt scores highest. Kept objects
are counted per tray (tray_placement.place_trays, from copies of the rig's calibration and slot
layout).

    PYTHONPATH=~/npec_camera_rig/src:. python3 clip_prompts.py --fastsam-hef H --clip DIR \
        --calibration C --slots S --out NEW_FOLDER still.jpg [...]

CLIP files (Hailo Model Zoo v5.1.0 hailo10h; hailo-apps resources): DIR holds
clip_vit_b_32_image_encoder.hef, clip_vit_b_32_text_encoder.hef, token_embedding_lut.npy,
text_projection.npy, clip_tokenizer.json. The text side follows hailo-apps clip_text_utils.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import cv2
import numpy as np

import fastsam_plants as fp
from npec_rig.calibration_store import load_calibration
from npec_rig.tags import detect_tags

PROMPTS = ("foliage", "leaves", "plants")
# Background words each prompt must beat (decisions, from what is in the photos).
BACKGROUND = ("soil", "blue plastic", "white paper", "black and white pattern", "grey metal")
SOT, EOT, SEQ = 49406, 49407, 77
CLIP_PX = 224
PAD = 0.15  # crop reaches this fraction of the box past each side


class HailoNet:
    """One HEF through HailoRT's InferModel API, float in and out."""

    def __init__(self, device, hef: Path, input_float: bool):
        from hailo_platform import FormatType

        self.im = device.create_infer_model(str(hef))
        self.im.input().set_format_type(FormatType.FLOAT32 if input_float else FormatType.UINT8)
        self.out_name = self.im.output_names[0]
        self.im.output(self.out_name).set_format_type(FormatType.FLOAT32)
        self._ctx = self.im.configure()
        self.cm = self._ctx.__enter__()
        self.dtype = np.float32 if input_float else np.uint8

    def __call__(self, x):
        out = np.empty(self.im.output(self.out_name).shape, np.float32)
        b = self.cm.create_bindings(output_buffers={self.out_name: out})
        b.input().set_buffer(np.ascontiguousarray(x, dtype=self.dtype))
        self.cm.run([b], 10000)
        return b.output(self.out_name).get_buffer().copy()

    def close(self):
        self._ctx.__exit__(None, None, None)


def unit(v):
    v = np.asarray(v, np.float32).ravel()
    return v / (np.linalg.norm(v) + 1e-8)


def text_embedding(words: str, net, vocab, lut, proj):
    """CLIP text embedding of a few plain words, each one vocabulary entry (checked)."""
    ids = [SOT] + [vocab[w + "</w>"] for w in words.lower().split()] + [EOT]
    emb = lut[ids]
    emb = np.concatenate([emb, np.repeat(emb[-1:], SEQ - len(ids), axis=0)])  # pad with EOT, as hailo-apps
    out = net(emb[None]).reshape(SEQ, -1)
    return unit(out[len(ids) - 1] @ proj)


def object_crop(bgr, d):
    """The object's box (plus PAD) with everything outside its mask grey, squared, at 224, RGB."""
    h, w = bgr.shape[:2]
    bw, bh = d["x1"] - d["x0"], d["y1"] - d["y0"]
    x0, y0 = int(max(0, d["x0"] - PAD * bw)), int(max(0, d["y0"] - PAD * bh))
    x1, y1 = int(min(w, d["x1"] + PAD * bw)), int(min(h, d["y1"] + PAD * bh))
    crop = bgr[y0:y1, x0:x1].copy()
    m = np.zeros(crop.shape[:2], np.uint8)
    cv2.drawContours(m, [d["contour"] - np.int32([x0, y0])], -1, 1, -1)
    crop[m == 0] = fp.GREY
    side = max(crop.shape[:2])
    sq = np.full((side, side, 3), fp.GREY, np.uint8)
    sq[: crop.shape[0], : crop.shape[1]] = crop
    return cv2.cvtColor(cv2.resize(sq, (CLIP_PX, CLIP_PX), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)


def run(still, fastsam, image_net, texts, placing, out: Path):
    out.mkdir(parents=True, exist_ok=False)
    t0 = time.perf_counter()
    full = cv2.imread(str(still))
    tags = detect_tags(cv2.cvtColor(full, cv2.COLOR_BGR2RGB))
    trays = fp.trays_of(tags, placing)
    bgr, crop, n = fp.crop_to_corner_tags(full, tags)
    if bgr is None:
        print(f"{still.name}: {n} corner tags, skipped", flush=True)
        return
    oy = crop[1]
    dets, _ = fp.fastsam_all(bgr, fastsam)
    t1 = time.perf_counter()
    img = np.stack([unit(image_net(object_crop(bgr, d))) for d in dets]) if dets else np.zeros((0, 512))
    t2 = time.perf_counter()
    _, blobs = fp.exg_blobs(bgr)  # only for the check below: objects holding green vs not
    has_green = np.array([any(d["x0"] <= b["cx"] <= d["x1"] and d["y0"] <= b["cy"] <= d["y1"] and
                              cv2.pointPolygonTest(d["contour"], (float(b["cx"]), float(b["cy"])), False) >= 0
                              for b in blobs) for d in dets], bool)
    bg = np.stack([texts[w] for w in BACKGROUND])
    notes = {"still": str(still), "objects": len(dets), "background_words": BACKGROUND,
             "seconds": {"fastsam": round(t1 - t0, 1), "clip_images": round(t2 - t1, 1)}, "prompts": {}}
    rows = []
    for p in PROMPTS:
        sims = img @ np.vstack([texts[p][None], bg]).T  # (objects, 1 + background)
        kept = sims.argmax(1) == 0
        margin = sims[:, 0] - sims[:, 1:].max(1)
        per_tray = [(tp, tag, sum(kept[i] and cv2.pointPolygonTest(
            np.float32(tp.outline), ((d["x0"] + d["x1"]) / 2, (d["y0"] + d["y1"]) / 2 + oy), False) >= 0
            for i, d in enumerate(dets))) for tp, tag in trays]
        notes["prompts"][p] = {
            "kept": int(kept.sum()),
            "kept_holding_green": int((kept & has_green).sum()), "kept_without_green": int((kept & ~has_green).sum()),
            "median_margin_holding_green": round(float(np.median(margin[has_green])), 4) if has_green.any() else None,
            "median_margin_without_green": round(float(np.median(margin[~has_green])), 4) if (~has_green).any() else None,
            "trays": {f"{tp.tray_id} {tp.slot}": int(n) for tp, _, n in per_tray}}
        im = cv2.resize(bgr, (bgr.shape[1] // fp.VIEW_REDUCE, bgr.shape[0] // fp.VIEW_REDUCE), interpolation=cv2.INTER_AREA)
        f = 1 / fp.VIEW_REDUCE
        for i, d in enumerate(dets):
            if kept[i]:
                cv2.drawContours(im, [(d["contour"] * f).astype(np.int32)], -1, (0, 255, 0), 2)
        for tp, tag, n in per_tray:
            o = (np.float32(tp.outline) - np.float32([0, oy])) * f
            cv2.polylines(im, [o.astype(np.int32)], True, (255, 255, 0), 3)
            org = (int((tp.centre[0]) * f) - 80, int((tp.centre[1] - oy) * f))
            for col, th in (((0, 0, 0), 5), ((255, 255, 255), 1)):
                cv2.putText(im, f"tray {tp.tray_id}: {n}", org, cv2.FONT_HERSHEY_SIMPLEX, 0.8, col, th if th > 1 else 2)
        cv2.rectangle(im, (0, 0), (im.shape[1], 30), (0, 0, 0), -1)
        cv2.putText(im, f"{still.stem}  prompt \"{p}\": {int(kept.sum())} of {len(dets)} FastSAM objects score "
                    f"higher for \"{p}\" than for any background word (green)", (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        cv2.imwrite(str(out / f"prompt_{p}.jpg"), im, [cv2.IMWRITE_JPEG_QUALITY, 85])
        for i, d in enumerate(dets):
            rows.append([p, i, round(d["x0"]), round(d["y0"] + oy), round(d["x1"]), round(d["y1"] + oy),
                         round(d["area_px"]), int(has_green[i]), *np.round(sims[i], 4), int(kept[i])])
    with open(out / "scores.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["prompt", "object", "x0", "y0", "x1", "y1", "area_px", "holds_green", "sim_prompt",
                     *[f"sim_{w.replace(' ', '_')}" for w in BACKGROUND], "kept"])
        wr.writerows(rows)
    (out / "notes.json").write_text(json.dumps(notes, indent=1))
    print(f"{still.name}: {len(dets)} objects; " + "; ".join(
        f"{p} {v['kept']} kept ({v['kept_holding_green']} with green), margin green {v['median_margin_holding_green']} "
        f"vs none {v['median_margin_without_green']}" for p, v in notes["prompts"].items()), flush=True)


def main():
    from hailo_platform import VDevice

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("stills", nargs="+", type=Path)
    ap.add_argument("--fastsam-hef", type=Path, required=True)
    ap.add_argument("--clip", type=Path, required=True)
    ap.add_argument("--calibration", type=Path, required=True)
    ap.add_argument("--slots", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    placing = (load_calibration(a.calibration).scale_field, json.loads(a.slots.read_text())["slots"])
    vocab = json.loads((a.clip / "clip_tokenizer.json").read_text())["model"]["vocab"]
    lut = np.load(a.clip / "token_embedding_lut.npy", allow_pickle=False)
    proj = np.load(a.clip / "text_projection.npy", allow_pickle=False)

    device = VDevice()  # one device, three networks
    fastsam = fp.FastSam(a.fastsam_hef, device)
    image_net = HailoNet(device, a.clip / "clip_vit_b_32_image_encoder.hef", input_float=False)
    text_net = HailoNet(device, a.clip / "clip_vit_b_32_text_encoder.hef", input_float=True)
    try:
        texts = {w: text_embedding(w, text_net, vocab, lut, proj) for w in PROMPTS + BACKGROUND}
        # Check the text side: related words close, unrelated further (printed, also saved).
        pairs = {f"{x} / {y}": round(float(texts[x] @ texts[y]), 3) for x, y in
                 (("foliage", "leaves"), ("leaves", "plants"), ("plants", "soil"), ("plants", "blue plastic"),
                  ("white paper", "black and white pattern"))}
        print("text similarities:", pairs, flush=True)
        (a.out / "text_similarities.json").write_text(json.dumps(pairs, indent=1))
        for s in a.stills:
            run(s, fastsam, image_net, texts, placing, a.out / s.stem)
    finally:
        text_net.close()
        image_net.close()
        fastsam.close()
        device.release()


if __name__ == "__main__":
    main()
