"""Round 1 (issue #164): FastSAM on the Hailo-8, on tray crops placed from the tray tags.

fast_sam_s.hef (Hailo Model Zoo v2.17.0, Hailo-8) is a YOLOv8 instance segmentation network with
one class, "object". Its outputs are decoded here: per grid cell a box (4 x 16 distance bins),
a score and 32 mask coefficients, on 80, 40 and 20 cell grids; 32 base masks of 160 x 160.

    PYTHONPATH=src python3 experiments/round1-trays/fastsam.py STILL [STILL ...]

Crops: each row of trays (North, South, from the A1 tags) is cut into tiles of 2 neighbouring
trays, padded to a square and resized to 640 x 640. Stills are read only; overlays and the HEF are
in ~/scratch/round1-trays/.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np

import trays

HEF_PATH = trays.SCRATCH / "hailo" / "fast_sam_s.hef"
OUT = trays.SCRATCH / "fastsam"
SIZE = 640
STRIDES = (8, 16, 32)
SCORE_MIN = 0.25  # decision: FastSAM's usual default confidence
IOU_MAX = 0.7  # decision: FastSAM's usual default for removing duplicates
TRAY_W_PX = 1480  # tray east-west at full resolution (305 mm at about 4.86 px/mm)
TRAY_H_PX = 1780  # north-south (366 mm)
TRAYS_PER_TILE = 2
TILE_MARGIN = 0.75  # trays past the outer tags; overridden by --margin
TILES = "tags"  # 'tags': 2-tray tiles from the A1 tags; 'grid': overlapping grid (--tiles)
# Which masks are trays (decisions, not measurements).
TRAY_AREA = (0.8, 1.2)  # mask area in trays
TRAY_FILL_MIN = 0.85  # mask area over its rotated rectangle's area
TRAY_ASPECT = (366 / 305 / 1.15, 366 / 305 * 1.15)  # north-south over east-west
GRID_TILE_PX = 3000  # overlapping grid: tile side at full resolution (about 1 px per mm at 640)
GRID_STEP_PX = 1000  # step between tiles; tile minus step (2000 px) exceeds a tray (1780 px) plus lip
BOX_EW_MM = (230.0, 400.0)  # candidate boxes of about one tray; masks are built only for these
BOX_NS_MM = (280.0, 460.0)  # (decisions, wide of the TRAY_* tests below so they decide)
SAME_TRAY_MM = 100.0  # masks from overlapping tiles with centres closer than this are one tray
LINK_MAX_MM = 60.0  # a tag links to the nearest tray mask within this distance
LINK_MARGIN_MM = 20.0  # ...only if the second-nearest mask is at least this much further
# Fallback around a tag whose tray was not found (decisions).
FALLBACK = True  # --no-fallback turns it off
FALLBACK_REACH = 1.15  # trays from the tag in every direction: where its tray must lie
FALLBACK_TILE_PX = 2600  # window side at full resolution (about 1.2 px per mm at 640)
TRAY_BOX_PX = (1650, 1950)  # a tray with its lip and a little turn, east-west and north-south
FALLBACK_SCORE_MIN = 0.05  # lower than SCORE_MIN: the window is already where the tray must be
HIDE_GREY = 114  # trays already found are painted this grey before the fallback


# ---------------------------------------------------------------- pure functions (unit tested)


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def dfl_distances(bins: np.ndarray) -> np.ndarray:
    """(N, 64) box bins to (N, 4) distances left, top, right, bottom in grid cells."""
    b = bins.reshape(-1, 4, 16)
    b = np.exp(b - b.max(axis=2, keepdims=True))
    b /= b.sum(axis=2, keepdims=True)
    return (b * np.arange(16)).sum(axis=2)


def decode(outputs: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Boxes (x0, y0, x1, y1 in input px), scores, coefficients, base masks from raw outputs.

    Outputs are told apart by shape: channels 64 (box), 1 (score), 32 (coefficients), and the
    160 x 160 base masks."""
    by_grid: dict[int, dict[int, np.ndarray]] = {}
    protos = None
    for a in outputs.values():
        a = a.reshape(a.shape[-3:])
        h, _, c = a.shape
        if h == SIZE // 4 and c == 32:
            protos = a
        else:
            by_grid.setdefault(h, {})[c] = a
    boxes, scores, coefs = [], [], []
    for stride in STRIDES:
        g = by_grid[SIZE // stride]
        n = SIZE // stride
        ys, xs = np.mgrid[0:n, 0:n]
        cx, cy = (xs.ravel() + 0.5), (ys.ravel() + 0.5)
        d = dfl_distances(g[64].reshape(-1, 64))
        boxes.append(np.stack([cx - d[:, 0], cy - d[:, 1], cx + d[:, 2], cy + d[:, 3]], 1) * stride)
        s = g[1].reshape(-1)
        scores.append(s if (s.min() >= 0 and s.max() <= 1) else sigmoid(s))
        coefs.append(g[32].reshape(-1, 32))
    return np.concatenate(boxes), np.concatenate(scores), np.concatenate(coefs), protos


def nms(boxes: np.ndarray, scores: np.ndarray, iou_max: float) -> list[int]:
    keep = cv2.dnn.NMSBoxes(
        [[float(x0), float(y0), float(x1 - x0), float(y1 - y0)] for x0, y0, x1, y1 in boxes],
        scores.astype(float).tolist(), 0.0, iou_max)
    return [int(i) for i in np.array(keep).ravel()]


def is_tray_mask(area_trays: float, fill: float, ew_mm: float, ns_mm: float) -> bool:
    aspect = ns_mm / ew_mm if ew_mm else 0
    return (TRAY_AREA[0] <= area_trays <= TRAY_AREA[1] and fill >= TRAY_FILL_MIN
            and TRAY_ASPECT[0] <= aspect <= TRAY_ASPECT[1])


def dedupe(cands: list[dict], same_px: float) -> list[dict]:
    """One mask per tray: of masks whose centres lie closer than same_px, the best filled stays."""
    kept: list[dict] = []
    for c in sorted(cands, key=lambda c: -c["fill"]):
        if all(np.hypot(c["cx"] - k["cx"], c["cy"] - k["cy"]) >= same_px for k in kept):
            kept.append(c)
    return kept


def link_tags(masks: list[dict], tags: list[dict], ppm: float) -> tuple[dict[int, int], list[int]]:
    """Each tray tag to the index of the nearest mask (outline distance, 0 inside), within
    LINK_MAX_MM and LINK_MARGIN_MM clear of the second-nearest; and the tags left ambiguous."""
    links, ambiguous = {}, []
    for t in tags:
        if trays.tray_of(t["id"]) is None or not masks:
            continue
        d = sorted((max(0.0, -cv2.pointPolygonTest(m["contour"], (t["cx"], t["cy"]), True)) / ppm, k)
                   for k, m in enumerate(masks))
        if d[0][0] > LINK_MAX_MM:
            continue
        if len(d) > 1 and d[1][0] - d[0][0] < LINK_MARGIN_MM:
            ambiguous.append(t["id"])
            continue
        links[t["id"]] = d[0][1]
    return links, ambiguous


def masks_for(boxes, coefs, protos) -> np.ndarray:
    """Masks at input size (K, 640, 640), each cut to its box."""
    m = sigmoid(np.einsum("kc,hwc->khw", coefs, protos))
    out = np.zeros((len(boxes), SIZE, SIZE), bool)
    for k, (x0, y0, x1, y1) in enumerate(boxes):
        up = cv2.resize(m[k], (SIZE, SIZE), interpolation=cv2.INTER_LINEAR) > 0.5
        bx0, by0 = max(0, int(x0)), max(0, int(y0))
        bx1, by1 = min(SIZE, int(np.ceil(x1))), min(SIZE, int(np.ceil(y1)))
        out[k, by0:by1, bx0:bx1] = up[by0:by1, bx0:bx1]
    return out


def tiles_from_tags(tags: list[dict], per_tile: int = TRAYS_PER_TILE) -> list[dict]:
    """Full-resolution crop boxes, one per run of `per_tile` neighbouring trays in a row.

    Row and order from the A1 tags (North is the 6 with the smallest y). A tag sits at the south-
    west or north-east corner of its tray, so the tray reaches a whole tray past its tag. The crop
    reaches TILE_MARGIN trays past the outer tags on every side; below 1 it cuts trays (#164
    diagnosis: 27 of 54 missing trays at 0.75)."""
    a1 = sorted((t for t in tags if t["id"] in trays.A1_TAGS), key=lambda t: t["cy"])
    if len(a1) != 12:
        return []
    out = []
    for row, sel in (("North", a1[:6]), ("South", a1[6:])):
        sel = sorted(sel, key=lambda t: t["cx"])
        for k in range(0, 6, per_tile):
            grp = sel[k : k + per_tile]
            xs, ys = [t["cx"] for t in grp], [t["cy"] for t in grp]
            out.append({
                "name": f"{row} {k + 1}-{k + len(grp)}", "trays": [t["id"] for t in grp],
                "x0": int(min(xs) - TILE_MARGIN * TRAY_W_PX), "x1": int(max(xs) + TILE_MARGIN * TRAY_W_PX),
                "y0": int(min(ys) - TILE_MARGIN * TRAY_H_PX), "y1": int(max(ys) + TILE_MARGIN * TRAY_H_PX),
            })
    return out


def grid_tiles(w: int, h: int, y0: int, y1: int, size: int = GRID_TILE_PX, step: int = GRID_STEP_PX) -> list[dict]:
    """Overlapping square tiles over the full width and rows y0..y1, the last tile in each
    direction flush with the end, so any tray smaller than size - step lies wholly in one tile."""
    def starts(lo, hi):
        if hi - lo <= size:
            return [max(0, (lo + hi - size) // 2)]
        out = list(range(lo, hi - size, step))
        return out + [hi - size]
    y0, y1 = max(0, y0), min(h, y1)
    return [{"name": f"grid {i},{j}", "trays": [], "x0": x, "x1": x + size, "y0": y, "y1": y + size}
            for j, y in enumerate(starts(y0, y1)) for i, x in enumerate(starts(0, w))]


def window_starts(lo: int, hi: int, size: int, item: int) -> list[int]:
    """Starts of windows of `size` over lo..hi, spaced so any item of `item` px inside lo..hi lies
    wholly in one window: neighbours no further apart than size - item."""
    if hi - lo <= size:
        return [(lo + hi - size) // 2]
    n = int(np.ceil((hi - lo - size) / (size - item))) + 1
    return [int(round(v)) for v in np.linspace(lo, hi - size, n)]


def fallback_windows(cx: float, cy: float, w: int, h: int) -> list[dict]:
    """Windows around a tag at (cx, cy) that between them hold its whole tray in some window."""
    rx, ry = FALLBACK_REACH * TRAY_W_PX, FALLBACK_REACH * TRAY_H_PX
    x0, x1 = int(max(0, cx - rx)), int(min(w, cx + rx))
    y0, y1 = int(max(0, cy - ry)), int(min(h, cy + ry))
    size = FALLBACK_TILE_PX
    return [{"name": f"fallback {i},{j}", "trays": [], "x0": x, "x1": x + size, "y0": y, "y1": y + size}
            for j, y in enumerate(window_starts(y0, y1, size, TRAY_BOX_PX[1]))
            for i, x in enumerate(window_starts(x0, x1, size, TRAY_BOX_PX[0]))]


def square_tile(img: np.ndarray, t: dict) -> tuple[np.ndarray, float, int, int]:
    """The crop padded to a square with grey and resized to 640; (tile, scale, x origin, y origin)."""
    h, w = img.shape[:2]
    x0, y0 = max(0, t["x0"]), max(0, t["y0"])
    crop = img[y0 : min(h, t["y1"]), x0 : min(w, t["x1"])]
    side = max(crop.shape[:2])
    sq = np.full((side, side, 3), 114, np.uint8)
    sq[: crop.shape[0], : crop.shape[1]] = crop
    scale = SIZE / side
    return cv2.resize(sq, (SIZE, SIZE), interpolation=cv2.INTER_AREA), scale, x0, y0


# ---------------------------------------------------------------- Hailo


class FastSam:
    def __init__(self, hef_path: Path):
        from hailo_platform import (HEF, ConfigureParams, FormatType, HailoStreamInterface,
                                    InferVStreams, InputVStreamParams, OutputVStreamParams, VDevice)

        self.hef = HEF(str(hef_path))
        self.device = VDevice()
        cp = ConfigureParams.create_from_hef(self.hef, interface=HailoStreamInterface.PCIe)
        self.group = self.device.configure(self.hef, cp)[0]
        self.ivp = InputVStreamParams.make(self.group, format_type=FormatType.UINT8)
        self.ovp = OutputVStreamParams.make(self.group, format_type=FormatType.FLOAT32)
        self.input_name = self.hef.get_input_vstream_infos()[0].name
        self._infer = InferVStreams(self.group, self.ivp, self.ovp)
        self._pipe = self._infer.__enter__()
        self._active = self.group.activate(self.group.create_params())
        self._active.__enter__()

    def __call__(self, rgb640: np.ndarray) -> dict[str, np.ndarray]:
        return self._pipe.infer({self.input_name: rgb640[None].astype(np.uint8)})

    def close(self):
        self._active.__exit__(None, None, None)
        self._infer.__exit__(None, None, None)
        self.device.release()


# ---------------------------------------------------------------- run


def tray_masks(img, tiles, model, scale_field, score_min: float, source: str) -> tuple[list[dict], float]:
    """Tray-shaped FastSAM masks from the given tiles, as full-resolution contours; Hailo time."""
    import time

    cands, t_infer = [], 0.0
    for t in tiles:
        tile, s, ox, oy = square_tile(img, t)
        ti = time.perf_counter()
        raw = model(cv2.cvtColor(tile, cv2.COLOR_BGR2RGB))
        t_infer += time.perf_counter() - ti
        boxes, scores, coefs, protos = decode(raw)
        sel = np.nonzero(scores >= score_min)[0]
        keep = sel[nms(boxes[sel], scores[sel], IOU_MAX)] if len(sel) else sel
        tile_ppm = scale_field.px_per_mm(ox + SIZE / 2 / s, oy + SIZE / 2 / s) * s
        bew = (boxes[keep, 2] - boxes[keep, 0]) / tile_ppm
        bns = (boxes[keep, 3] - boxes[keep, 1]) / tile_ppm
        keep = keep[(bew >= BOX_EW_MM[0]) & (bew <= BOX_EW_MM[1]) & (bns >= BOX_NS_MM[0]) & (bns <= BOX_NS_MM[1])]
        if not len(keep):
            continue
        tray_px = trays.TRAY_EW_MM * trays.TRAY_NS_MM * tile_ppm**2
        for k, m in enumerate(masks_for(boxes[keep], coefs[keep], protos)):
            ys, xs = np.nonzero(m)
            if len(xs) == 0:
                continue
            (rx, ry), (rw, rh), _ = cv2.minAreaRect(np.column_stack([xs, ys]).astype(np.float32))
            area, fill = m.sum() / tray_px, m.sum() / max(rw * rh, 1)
            ew, ns = (xs.max() - xs.min() + 1) / tile_ppm, (ys.max() - ys.min() + 1) / tile_ppm
            if not is_tray_mask(area, fill, ew, ns):
                continue
            cnts, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            c = max(cnts, key=cv2.contourArea).astype(np.float32) / s + np.float32([ox, oy])
            cands.append({"tile": t["name"], "source": source, "score": float(scores[keep][k]),
                          "area_trays": float(area), "fill": float(fill), "ew_mm": float(ew),
                          "ns_mm": float(ns), "cx": ox + rx / s, "cy": oy + ry / s,
                          "contour": c.astype(np.int32)})
    return cands, t_infer


def judge_masks(masks: list[dict], links: dict[int, int], a1: list[int]) -> list[int]:
    """Sets each mask's verdict and trays from its linked tags; the A1 trays found right."""
    found: dict[int, list[int]] = {}
    for k, m in enumerate(masks):
        ids = sorted(i for i, j in links.items() if j == k)
        m["verdict"], m["trays"] = trays.judge_shape(ids, 1.0)
        m["tag_ids"] = ids
        for tr in m["trays"]:
            found.setdefault(tr, []).append(k)
    return [tr for tr in a1 if len(found.get(tr, [])) == 1 and masks[found[tr][0]]["verdict"] == "one tray"]


def run_still(still: str, model: FastSam, scale_field, det, rows: list[dict], table_rows=(0, 0)) -> dict:
    """Tray masks of one still: first pass, then the fallback around tags whose tray was not
    found; tags linked, one overlay. Returns timings and counts."""
    import time

    t0 = time.perf_counter()
    img = cv2.imread(str(trays.EXPERIMENT / f"{still}.jpg"))
    t1 = time.perf_counter()
    cached = (trays.SCRATCH / "tags" / f"{still}.json").exists()
    tags = trays.detect(still, det)  # cached in scratch after the first time
    t2 = time.perf_counter()
    h, w = img.shape[:2]
    ppm = scale_field.px_per_mm(w / 2, h / 2)  # full-res px per mm, for distances
    a1 = sorted(g["id"] for g in tags if g["id"] in trays.A1_TAGS)

    tiles = tiles_from_tags(tags) if TILES == "tags" else grid_tiles(w, h, *table_rows)
    cands, t_infer = tray_masks(img, tiles, model, scale_field, SCORE_MIN, "first")
    masks = dedupe(cands, SAME_TRAY_MM * ppm)
    links, ambiguous = link_tags(masks, tags, ppm)
    ok_first = judge_masks(masks, links, a1)
    t3 = time.perf_counter()

    # Fallback: trays found right stay; masks holding several trays are dropped; for every A1 tag
    # whose tray is not right, its surroundings are searched with the found trays painted grey.
    failed = [tr for tr in a1 if tr not in ok_first]
    n_fb_tiles, t_fb_infer, fb_found = 0, 0.0, []
    if FALLBACK and failed:
        good = [m for m in masks if m["verdict"] == "one tray" and m["trays"][0] in ok_first]
        loose = [m for m in masks if m["verdict"] == "no tray"]
        hidden = img.copy()
        for m in good:
            cv2.drawContours(hidden, [m["contour"]], -1, (HIDE_GREY,) * 3, thickness=-1)
            cv2.drawContours(hidden, [m["contour"]], -1, (HIDE_GREY,) * 3, thickness=int(5 * ppm))
        by_id = {g["id"]: g for g in tags}
        new = []
        for tr in failed:
            g = by_id[tr]
            win = fallback_windows(g["cx"], g["cy"], w, h)
            n_fb_tiles += len(win)
            fc, ti = tray_masks(hidden, win, model, scale_field, FALLBACK_SCORE_MIN, "fallback")
            t_fb_infer += ti
            fc = [c for c in dedupe(fc, SAME_TRAY_MM * ppm)
                  if all(np.hypot(c["cx"] - m["cx"], c["cy"] - m["cy"]) >= SAME_TRAY_MM * ppm for m in good + new)]
            d = [(max(0.0, -cv2.pointPolygonTest(c["contour"], (g["cx"], g["cy"]), True)) / ppm, -c["fill"], k)
                 for k, c in enumerate(fc)]
            d = [x for x in d if x[0] <= LINK_MAX_MM]
            if d:
                pick = fc[min(d)[2]]
                new.append(pick)
                fb_found.append(tr)
                cv2.drawContours(hidden, [pick["contour"]], -1, (HIDE_GREY,) * 3, thickness=-1)
        # Final set: right first-pass trays, fallback trays, and first-pass masks with no tag that
        # are not the same tray as one of those.
        kept = good + new
        kept += [m for m in loose if all(np.hypot(m["cx"] - k["cx"], m["cy"] - k["cy"]) >= SAME_TRAY_MM * ppm for k in kept)]
        masks = kept
        links, ambiguous = link_tags(masks, tags, ppm)
    ok = judge_masks(masks, links, a1)
    t4 = time.perf_counter()

    found = {tr for m in masks for tr in m["trays"]}
    for k, m in enumerate(masks):
        rows.append({"still": still, "mask": k, "tile": m["tile"], "source": m["source"], "verdict": m["verdict"],
                     "trays": " ".join(map(str, m["trays"])), "tag_ids": " ".join(map(str, m["tag_ids"])),
                     "score": round(m["score"], 3), "area_trays": round(m["area_trays"], 2), "fill": round(m["fill"], 2),
                     "ew_mm": round(m["ew_mm"], 1), "ns_mm": round(m["ns_mm"], 1),
                     "cx_full": round(m["cx"]), "cy_full": round(m["cy"])})
    res = {"still": still, "a1_tags": len(a1), "first_pass_ok": len(ok_first), "fallback_tags": len(failed) if FALLBACK else 0,
           "fallback_found": len(fb_found), "tray_masks": len(masks), "trays_ok": len(ok),
           "no_tag_masks": sum(m["verdict"] == "no tray" for m in masks),
           "several_masks": sum(m["verdict"] == "several trays" for m in masks),
           "trays_without_mask": sum(tr not in found for tr in a1),
           "ambiguous_tags": " ".join(map(str, ambiguous)),
           "t_decode_s": round(t1 - t0, 2), "t_tags_s": round(t2 - t1, 2), "tags_cached": cached,
           "t_hailo_s": round(t_infer, 2), "t_masks_s": round(t3 - t2 - t_infer, 2),
           "t_fallback_s": round(t4 - t3, 2), "t_fallback_hailo_s": round(t_fb_infer, 2),
           "t_total_s": round(t4 - t0, 2), "tiles": TILES, "n_tiles": len(tiles), "n_fallback_tiles": n_fb_tiles}
    folder = (f"fastsam-stills-m{TILE_MARGIN:g}" if TILES == "tags" else "fastsam-stills-grid") + ("-fb" if FALLBACK else "")
    overlay_still(img, masks, tags, links, res, trays.SCRATCH / folder / f"{still}.jpg")
    return res


def overlay_still(img, masks, tags, links, res, out: Path) -> None:
    """Tray masks and tag links on a 1/8 copy of the still. The still is never altered."""
    r = trays.REDUCE
    im = cv2.resize(img, (img.shape[1] // r, img.shape[0] // r), interpolation=cv2.INTER_AREA)
    cols = {"one tray": (0, 200, 0), "several trays": (0, 0, 255), "no tray": (0, 165, 255)}
    for k, m in enumerate(masks):
        c = (m["contour"] / r).astype(np.int32)
        cv2.drawContours(im, [c], -1, cols[m["verdict"]], 2 if m.get("source") != "fallback" else 4)
        label = {"one tray": "OK", "several trays": "MERGED", "no tray": "NO TAG"}[m["verdict"]]
        if m.get("source") == "fallback":
            label += " (fallback)"
        text = [f"{label} tray {','.join(map(str, m['trays']))}" if m["trays"] else label,
                f"{m['ew_mm']:.0f} x {m['ns_mm']:.0f} mm"]
        for j, line in enumerate(text):
            org = (int(m["cx"] / r) - 60, int(m["cy"] / r) + 22 * j)
            cv2.putText(im, line, org, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 4)
            cv2.putText(im, line, org, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    for g in tags:
        p = (int(g["cx"] / r), int(g["cy"] / r))
        if g["id"] in links:
            m = masks[links[g["id"]]]
            cv2.line(im, p, (int(m["cx"] / r), int(m["cy"] / r)), (255, 0, 255), 1)
        cv2.circle(im, p, 5, (255, 0, 255), -1)
        cv2.putText(im, str(g["id"]), (p[0] + 6, p[1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 2)
    cv2.rectangle(im, (0, 0), (im.shape[1], 28), (0, 0, 0), -1)
    cv2.putText(im, f"{res['still']} FastSAM: {res['trays_ok']}/{res['a1_tags']} trays OK "
                f"(first pass {res.get('first_pass_ok', res['trays_ok'])}), "
                f"{res['no_tag_masks']} no tag, {res['several_masks']} merged, "
                f"{res['trays_without_mask']} without mask", (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (255, 255, 255), 1)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), im, [cv2.IMWRITE_JPEG_QUALITY, 85])


def main(argv: list[str] | None = None) -> None:
    global TILE_MARGIN, TILES, FALLBACK
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("stills", nargs="+")
    ap.add_argument("--name", default="run", help="results file suffix")
    ap.add_argument("--margin", type=float, default=TILE_MARGIN, help="tile margin in trays")
    ap.add_argument("--tiles", choices=["tags", "grid"], default=TILES)
    ap.add_argument("--no-fallback", action="store_true", help="first pass only")
    args = ap.parse_args(argv)
    TILE_MARGIN, TILES, FALLBACK = args.margin, args.tiles, not args.no_fallback
    from npec_rig.calibration_store import load_calibration

    det = trays.detector()
    model = FastSam(HEF_PATH)
    rows: list[dict] = []
    results: list[dict] = []
    calibs: dict = {}
    try:
        for still in args.stills:
            info = trays.capture_info(still)
            stem = info["calibration"]
            if stem not in calibs:
                art = load_calibration(trays.RIG / "calibration" / f"{stem}.json")
                ys = [y for c in art.corner_baseline.corners_by_id.values() for _, y in c]
                calibs[stem] = (art.scale_field, (int(min(ys)), int(max(ys))))
            sf, table_rows = calibs[stem]
            res = run_still(still, model, sf, det, rows, table_rows)
            res = {"step": "", **res, "calibration": stem, "validation": info["validation"], "lens": info["lens"]}
            results.append(res)
            print(f"{still}: {res['trays_ok']}/{res['a1_tags']} OK (first {res['first_pass_ok']}, "
                  f"fallback {res['fallback_found']}/{res['fallback_tags']}), {res['tray_masks']} masks, "
                  f"no tag {res['no_tag_masks']}, merged {res['several_masks']}, "
                  f"no mask {res['trays_without_mask']}, ambiguous [{res['ambiguous_tags']}], "
                  f"{res['t_total_s']} s (tags {res['t_tags_s']}, hailo {res['t_hailo_s']})", flush=True)
    finally:
        model.close()
    steps = {r["still"]: r["step"] for r in trays.session_rows(sum(trays.SETS.values(), []))}
    for r in results:
        r["step"] = steps.get(r["still"], "")
    trays.write_csv(trays.HERE / f"fastsam-{args.name}.csv", results)
    trays.write_csv(trays.HERE / f"fastsam-{args.name}-masks.csv", rows)


if __name__ == "__main__":
    sys.exit(main())
