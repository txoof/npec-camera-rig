"""Round 1 (issue #164): tray splitting and tray ID on the 15 October stills.

Method and decision rule: docs/metrology-log.md section 15.5c, written before this ran.
Methods here: A (tag only, nearest slot) and B (blue threshold, rotated rectangle per shape).

    PYTHONPATH=src python3 experiments/round1-trays/trays.py --set gaps

Stills and rig.db are read only. Nothing is written into the experiment folder. Tag detections
are cached and overlays written in ~/scratch/round1-trays/; results.csv and shapes.csv are
written next to this file.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
RIG = Path("/var/lib/npec-rig")
EXPERIMENT = RIG / "experiments" / "2026-10-15_44a9e96e" / "stills" / "2026-10-15"
SESSION_CSV = REPO / "experiments" / "round1" / "session-2026-10-15.csv"
SCRATCH = Path.home() / "scratch" / "round1-trays"

# Sets (metrology-log 15.5c; R2-3 confirmed as gaps by Aaron 2026-10-15).
SETS = {
    "gaps": ["1", "2", "3", "R2-1", "R2-2", "R2-3"],
    "touching": ["5", "4", "6", "R2-4", "R3"],
}

# Tray measurements (Aaron 2026-10-15, tape measure), outside size with the lip, portrait.
TRAY_EW_MM = 305.0
TRAY_NS_MM = 366.0

# Tray identity. Session 1 and round 2: IDs 1 to 12 sit in cell A1, one per tray. Round 2 adds
# 20 mm edge tags, each on the same tray as a 30 mm tag (15.3a, green 30 mm : 20 mm paper).
A1_TAGS = set(range(1, 13))
EDGE_PAIRS = {0: 4, 14: 5, 16: 6, 17: 7, 13: 8, 15: 11}  # edge tag -> A1 tag of its tray
TRAY_TAG_MAX_ID = 299

# Blue. Decisions for round 1, picked on one probe still (075756_789328): tray hue 103 to 112
# on OpenCV's 0..180 scale, saturation 170 to 225 at the slot centres; the aisle is S 6.
BLUE_HSV = ((100, 100, 50), (118, 255, 255))
REDUCE = 8  # shapes are found on a 1/8 decode
OPEN_PX = 3  # 1/8 px, opening kernel: removes thin blue specks, kept small so gaps survive
MIN_SHAPE_FRACTION = 0.25  # of one tray's area; smaller blue shapes are not trays
TAG_NEAR_MM = 15.0  # a tag joins a shape if its centre is inside it or this close (paper tags
# extend past the tray corner)


# ---------------------------------------------------------------- pure functions (unit tested)


def tray_of(tag_id: int) -> int | None:
    """The tray a tray tag belongs to, named by its A1 tag ID; None for a non-tray tag."""
    if tag_id in A1_TAGS:
        return tag_id
    return EDGE_PAIRS.get(tag_id)


def tag_heading_deg(corners) -> float:
    """Direction the tag's top edge faces, degrees clockwise from image up (north).

    ArUco corners run top-left, top-right, bottom-right, bottom-left in the tag's own frame, so
    bottom-left to top-left points to the tag's top."""
    c = np.asarray(corners, dtype=float)
    up = (c[0] + c[1]) / 2 - (c[3] + c[2]) / 2
    return math.degrees(math.atan2(up[0], -up[1])) % 360


def nearest_slots(x: float, y: float, slots: list[dict]) -> tuple[str, float, str, float]:
    """Nearest and second-nearest slot names with their centre distances, in pixels."""
    d = sorted((math.hypot(s["centre"][0] - x, s["centre"][1] - y), s["name"]) for s in slots)
    return d[0][1], d[0][0], d[1][1], d[1][0]


def blue_mask(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, np.array(BLUE_HSV[0]), np.array(BLUE_HSV[1])) > 0


def shapes_from_mask(mask: np.ndarray, min_area_px: float) -> list[np.ndarray]:
    """Filled outer contours of the blue regions, holes (cells, tags) filled, small ones dropped.

    Opening is small on purpose: a wider one would close the gap between two trays."""
    m = mask.astype(np.uint8)
    if OPEN_PX > 1:
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((OPEN_PX, OPEN_PX), np.uint8))
    contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [c for c in contours if cv2.contourArea(c) >= min_area_px]


def tags_in_shape(contour: np.ndarray, tags: list[dict], near_px: float) -> list[int]:
    """Tray tag IDs whose centre (in the contour's pixels) is inside it or within near_px."""
    out = []
    for t in tags:
        d = cv2.pointPolygonTest(contour, (float(t["cx"]), float(t["cy"])), True)
        if d >= -near_px:
            out.append(t["id"])
    return out


def judge_shape(tag_ids: list[int]) -> tuple[str, list[int]]:
    """'one tray', 'no tray' or 'several trays', and the trays named by the tags in a shape."""
    trays = sorted({t for t in (tray_of(i) for i in tag_ids) if t is not None})
    if not trays:
        return "no tray", trays
    return ("one tray" if len(trays) == 1 else "several trays"), trays


# ---------------------------------------------------------------- data


def session_rows(steps: list[str]) -> list[dict]:
    with open(SESSION_CSV) as f:
        rows = [r for r in csv.DictReader(f) if r["step"] in steps]
    order = {s: i for i, s in enumerate(steps)}
    return sorted(rows, key=lambda r: (order[r["step"]], r["still"]))


def capture_info(still: str) -> dict:
    """Calibration, validation and lens position of a still, from rig.db (read only)."""
    db = sqlite3.connect(f"file:{RIG / 'rig.db'}?mode=ro", uri=True)
    rel = (EXPERIMENT / still).relative_to(RIG)
    row = db.execute(
        "select taken_at, calibration, validation, lens_position from capture where path = ?",
        (str(rel),),
    ).fetchone()
    db.close()
    if row is None:
        raise SystemExit(f"{still}: not in rig.db")
    return {"taken_at": row[0], "calibration": row[1], "validation": row[2],
            "lens": round(row[3], 3) if row[3] is not None else None}


def detector():
    from npec_rig import tags

    p = tags._detector_parameters()
    # Setting C from #156: finer bit sampling for the 20 mm tags (171 of 171 found).
    p.perspectiveRemovePixelPerCell = 8
    p.perspectiveRemoveIgnoredMarginPerCell = 0.2
    return cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(tags.TAG_DICTIONARY), p)


def detect(still: str, det) -> list[dict]:
    """Tray tags in a still at full resolution, cached in scratch (the still is never altered)."""
    cache = SCRATCH / "tags" / f"{still}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    gray = cv2.imread(str(EXPERIMENT / f"{still}.jpg"), cv2.IMREAD_GRAYSCALE)
    corners, ids, _ = det.detectMarkers(gray)
    out = []
    for c, i in zip(corners, [] if ids is None else ids.ravel()):
        c = c.reshape(4, 2)
        if int(i) <= TRAY_TAG_MAX_ID:
            cx, cy = c.mean(axis=0)
            out.append({"id": int(i), "cx": float(cx), "cy": float(cy), "corners": c.tolist(),
                        "heading_deg": round(tag_heading_deg(c), 1)})
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out))
    return out


# ---------------------------------------------------------------- methods


def method_a(tags: list[dict], slots: list[dict], scale) -> dict[int, dict]:
    """Tray -> slot by the nearest slot centre to its A1 tag (the reference for slots)."""
    out = {}
    for t in tags:
        if t["id"] not in A1_TAGS:
            continue
        name, d1, name2, d2 = nearest_slots(t["cx"], t["cy"], slots)
        ppm = scale.px_per_mm(t["cx"], t["cy"])
        out[t["id"]] = {"slot": name, "dist_mm": d1 / ppm, "second": name2, "second_mm": d2 / ppm,
                        "heading_deg": t["heading_deg"]}
    return out


def method_b(small: np.ndarray, tags: list[dict], scale, slots: list[dict]) -> list[dict]:
    """Blue shapes on the 1/8 decode, each with a rotated rectangle and the trays inside it."""
    h, w = small.shape[:2]
    ppm_mid = scale.px_per_mm(w * REDUCE / 2, h * REDUCE / 2) / REDUCE
    tray_px = TRAY_EW_MM * TRAY_NS_MM * ppm_mid**2
    small_tags = [{"id": t["id"], "cx": t["cx"] / REDUCE, "cy": t["cy"] / REDUCE} for t in tags]
    shapes = []
    for c in shapes_from_mask(blue_mask(small), MIN_SHAPE_FRACTION * tray_px):
        (rx, ry), (rw, rh), ang = cv2.minAreaRect(c)
        ppm = scale.px_per_mm(rx * REDUCE, ry * REDUCE) / REDUCE
        box = cv2.boxPoints(((rx, ry), (rw, rh), ang))
        # Report the rectangle's sides as east-west and north-south by the nearer image axis.
        e = box[1] - box[0]
        side_a = float(np.hypot(*e)) / ppm
        side_b = float(np.hypot(*(box[2] - box[1]))) / ppm
        ew, ns = (side_a, side_b) if abs(e[0]) >= abs(e[1]) else (side_b, side_a)
        ids = tags_in_shape(c, small_tags, TAG_NEAR_MM * ppm)
        verdict, trays = judge_shape(ids)
        slot_b = nearest_slots(rx * REDUCE, ry * REDUCE, slots)[0]
        shapes.append({"contour": c, "box": box, "cx": rx, "cy": ry, "ew_mm": ew, "ns_mm": ns,
                       "area_trays": cv2.contourArea(c) / tray_px, "tag_ids": ids,
                       "verdict": verdict, "trays": trays, "slot_b": slot_b})
    return shapes


def overlay(small: np.ndarray, shapes: list[dict], a: dict[int, dict], tags: list[dict],
            title: str, out: Path) -> None:
    """Shapes and tags drawn on a copy of the 1/8 decode. The still is never altered."""
    im = small.copy()
    colours = {"one tray": (0, 200, 0), "several trays": (0, 0, 255), "no tray": (0, 165, 255)}
    for s in shapes:
        col = colours[s["verdict"]]
        cv2.drawContours(im, [s["contour"]], -1, col, 2)
        cv2.polylines(im, [s["box"].astype(np.int32)], True, (255, 255, 255), 1)
        label = {"one tray": "OK", "several trays": "MERGED", "no tray": "NO TAG"}[s["verdict"]]
        trays = ",".join(str(t) for t in s["trays"])
        slot = s["slot_b"]
        text = [f"{label} tray {trays}" if trays else label, slot,
                f"{s['ew_mm']:.0f} x {s['ns_mm']:.0f} mm"]
        for k, line in enumerate(t for t in text if t):
            org = (int(s["cx"]) - 60, int(s["cy"]) - 10 + 22 * k)
            cv2.putText(im, line, org, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 4)
            cv2.putText(im, line, org, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    for t in tags:
        p = (int(t["cx"] / REDUCE), int(t["cy"] / REDUCE))
        cv2.circle(im, p, 5, (255, 0, 255), -1)
        cv2.putText(im, str(t["id"]), (p[0] + 6, p[1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 2)
    cv2.rectangle(im, (0, 0), (im.shape[1], 28), (0, 0, 0), -1)
    cv2.putText(im, title, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), im, [cv2.IMWRITE_JPEG_QUALITY, 85])


# ---------------------------------------------------------------- run


def run(set_name: str, limit: int | None = None) -> None:
    from npec_rig.calibration_store import load_calibration
    from npec_rig.validation_store import load_slot_layout

    det = detector()
    calibs: dict[str, tuple] = {}
    results, shape_rows = [], []
    for r in session_rows(SETS[set_name])[:limit]:
        still = r["still"]
        info = capture_info(still)
        stem = info["calibration"]
        if stem not in calibs:
            art = load_calibration(RIG / "calibration" / f"{stem}.json")
            calibs[stem] = (art.scale_field, load_slot_layout(stem)["slots"])
        scale, slots = calibs[stem]
        tags = detect(still, det)
        small = cv2.imread(str(EXPERIMENT / f"{still}.jpg"), cv2.IMREAD_REDUCED_COLOR_8)
        a = method_a(tags, slots, scale)
        shapes = method_b(small, tags, scale, slots)

        trays_seen = sorted(a)
        shape_count = {t: sum(t in s["trays"] for s in shapes) for t in trays_seen}
        ok_trays = [t for t in trays_seen if shape_count[t] == 1 and any(
            s["verdict"] == "one tray" and s["trays"] == [t] for s in shapes)]
        slot_agree = [t for t in ok_trays if any(
            s["trays"] == [t] and s["slot_b"] == a[t]["slot"] for s in shapes)]
        slots_a = [a[t]["slot"] for t in trays_seen]
        res = {
            "set": set_name, "step": r["step"], "still": still, "taken_at_utc": info["taken_at"],
            "calibration": stem, "validation": info["validation"], "lens": info["lens"],
            "a1_tags_found": len(trays_seen), "edge_tags_found": sum(t["id"] in EDGE_PAIRS for t in tags),
            "a_slots_unique": len(set(slots_a)) == len(slots_a),
            "a_max_dist_mm": round(max((v["dist_mm"] for v in a.values()), default=0), 1),
            "a_min_margin_mm": round(min((v["second_mm"] - v["dist_mm"] for v in a.values()), default=0), 1),
            "b_shapes": len(shapes),
            "b_one_tray": sum(s["verdict"] == "one tray" for s in shapes),
            "b_several_trays": sum(s["verdict"] == "several trays" for s in shapes),
            "b_no_tray": sum(s["verdict"] == "no tray" for s in shapes),
            "b_trays_ok": len(ok_trays),
            "b_slot_agrees_a": len(slot_agree),
            "b_trays_split": sum(c > 1 for c in shape_count.values()),
            "b_trays_missing": sum(c == 0 for c in shape_count.values()),
        }
        res["b_pass"] = (res["b_trays_ok"] == len(trays_seen) == 12
                         and res["b_slot_agrees_a"] == 12 and res["a_slots_unique"])
        results.append(res)
        for s in shapes:
            shape_rows.append({"still": still, "step": r["step"], "verdict": s["verdict"],
                               "trays": " ".join(map(str, s["trays"])),
                               "tag_ids": " ".join(map(str, s["tag_ids"])),
                               "slot_a": a[s["trays"][0]]["slot"] if len(s["trays"]) == 1 and s["trays"][0] in a else "",
                               "slot_b": s["slot_b"],
                               "ew_mm": round(s["ew_mm"], 1), "ns_mm": round(s["ns_mm"], 1),
                               "area_trays": round(s["area_trays"], 2),
                               "cx_full": round(s["cx"] * REDUCE), "cy_full": round(s["cy"] * REDUCE)})
        title = (f"{still} step {r['step']} | B: {res['b_trays_ok']}/12 trays OK, "
                 f"{res['b_several_trays']} merged, {res['b_no_tray']} no tag")
        overlay(small, shapes, a, tags, title, SCRATCH / set_name / f"{r['step']}_{still}.jpg")
        print(title, flush=True)

    write_csv(HERE / f"results-{set_name}.csv", results)
    write_csv(HERE / f"shapes-{set_name}.csv", shape_rows)


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--set", choices=sorted(SETS), default="gaps")
    ap.add_argument("--limit", type=int, help="first N stills only, for a quick check")
    args = ap.parse_args(argv)
    run(args.set, args.limit)


if __name__ == "__main__":
    sys.exit(main())
