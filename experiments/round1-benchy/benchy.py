"""Round 1 (issue #154): red and green area on the Benchy Yellow-4 benchmark stills.

Fixed thresholds, nothing trained. Pixel areas become mm² through the rig's calibration scale
field (`ScaleField.px_per_mm`, the local scale at each blob's centre, the same pattern as
`certainty_map.py`). No height correction: the expected effect of height is reported next to
the results instead.

    PYTHONPATH=src python3 experiments/round1-benchy/benchy.py \
        --session-csv session-2026-10-15.csv STILL.jpg [STILL.jpg ...]

Stills are read only. Overlays and results.csv are written next to this file.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
RIG = Path("/var/lib/npec-rig")

# Thresholds. Decisions for round 1, picked on one probe still (065407_243036), not measured.
YELLOW_HSV = ((15, 120, 120), (35, 255, 255))  # OpenCV hue 0..180
RED_HSV = (((0, 120, 80), (8, 255, 255)), ((170, 120, 80), (180, 255, 255)))  # hue wraps at 0
EXG_MIN = 0.1  # normalised excess green 2g - r - b, with g > r so yellow does not pass
MIN_RED_PX = 300  # full-res pixels, about 13 mm²; smaller red pieces are noise
MIN_GREEN_PX = 300
BASE_MARGIN_PX = 250  # crop margin around the base, full-res pixels
REGION_GROW_PX = 41  # the base's hull grown by this kernel, so leaf tips over the edge count

# Static grouping: a still is a repeat of the one before when the benchmark has not moved.
STATIC_SHIFT_PX = 20.0  # about 4 mm at 4.85 px/mm
STATIC_TURN_DEG = 1.0

CORNERS = ("NW", "NE", "SE", "SW")  # clockwise seen from above
SOLIDS = {  # corner: (name, known area mm², height above tray mm), metrology-log 15.1
    "NW": ("prism", 6.34 * 8.14, 15.04),
    "NE": ("circle", math.pi * 5.0**2, 4.27),
    "SE": ("sphere", math.pi * (8.85 / 2) ** 2, 6.6),
    "SW": ("cylinder", math.pi * (8.39 / 2) ** 2, 12.00),
}
# Rosette widest diameters, calliper estimates (Aaron 2026-10-15, SE and SW corrected from 15.1).
ROSETTE_DIAM_MM = {"NW": 50.87, "NE": 67.20, "SE": 59.64, "SW": 38.68}
ROSETTE_TOP_MM = {"NW": 26.15, "NE": 32.27, "SE": 28.48, "SW": 23.62}


# ---------------------------------------------------------------- pure functions (unit tested)


def excess_green_mask(bgr: np.ndarray, exg_min: float = EXG_MIN) -> np.ndarray:
    """True where normalised excess green 2g - r - b exceeds `exg_min` and green beats red."""
    f = bgr.astype(np.float32)
    b, g, r = f[..., 0], f[..., 1], f[..., 2]
    exg = (2 * g - r - b) / (b + g + r + 1e-6)
    return (exg > exg_min) & (g > r)


def red_mask(bgr: np.ndarray) -> np.ndarray:
    """True where the hue is red (both ends of OpenCV's 0..180 hue circle)."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    m = np.zeros(bgr.shape[:2], bool)
    for lo, hi in RED_HSV:
        m |= cv2.inRange(hsv, lo, hi) > 0
    return m


def yellow_mask(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, *YELLOW_HSV) > 0


def area_mm2(mask: np.ndarray, px_per_mm: float) -> float:
    """Pixel count over the squared local scale."""
    return float(np.count_nonzero(mask)) / px_per_mm**2


def circularity(contour: np.ndarray) -> float:
    """4 pi A / P², 1.0 for a circle, about 0.785 for a square."""
    a = cv2.contourArea(contour)
    p = cv2.arcLength(contour, True)
    return 4 * math.pi * a / p**2 if p > 0 else 0.0


def corner_angles(nw_angle: float) -> dict[str, float]:
    """Image angle (atan2, y down) of each corner, given the NW corner's angle.

    Clockwise seen from above is increasing atan2 angle in image coordinates (y points down),
    so NE is a quarter turn after NW, and so on."""
    return {name: nw_angle + i * math.pi / 2 for i, name in enumerate(CORNERS)}


def nearest_corner(angle: float, corners: dict[str, float]) -> str:
    return min(corners, key=lambda k: abs(math.remainder(angle - corners[k], 2 * math.pi)))


def static_groups(poses: list[tuple[str, float, float, float] | None],
                  shift_px: float = STATIC_SHIFT_PX, turn_deg: float = STATIC_TURN_DEG) -> list[int | None]:
    """Group number per still, in order: a still joins the group before it when it is in the
    same experiment, its base centre moved less than `shift_px` and its turn changed less than
    `turn_deg`. `poses` are (experiment, x, y, turn in degrees), or None when no base was found."""
    groups: list[int | None] = []
    current, last = -1, None
    for pose in poses:
        if pose is None:
            groups.append(None)
            continue
        if last is not None and pose[0] == last[0]:
            moved = math.hypot(pose[1] - last[1], pose[2] - last[2])
            turned = abs(math.remainder(pose[3] - last[3], 360.0))
            same = moved < shift_px and turned < turn_deg
        else:
            same = False
        if not same:
            current += 1
        groups.append(current)
        last = pose
    return groups


# ---------------------------------------------------------------- pipeline


@dataclass
class StillResult:
    path: Path
    row: dict = field(default_factory=dict)


def find_base_reduced(path: Path) -> tuple[int, int, int, int] | None:
    """Full-res bounding box of the benchmark's square yellow base, found on a 1/8 decode.

    The largest square yellow blob of plausible size wins; the yellow bin outside the table is
    not square enough."""
    small = cv2.imread(str(path), cv2.IMREAD_REDUCED_COLOR_8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(yellow_mask(small).astype(np.uint8))
    best = None
    for i in range(1, n):
        a = st[i, 4]
        if not 6000 < a < 20000:
            continue
        pts = np.column_stack(np.nonzero(lab == i))[:, ::-1].astype(np.float32)
        (_, _), (rw, rh), _ = cv2.minAreaRect(pts)
        # Square against its own rotated rectangle, so a base turned 45 degrees still passes.
        if 0.75 < rw / rh < 1.33 and a / (rw * rh) > 0.8:
            if best is None or a > st[best, 4]:
                best = i
    if best is None:
        return None
    x, y, w, h = (int(v) * 8 for v in st[best, :4])
    return x, y, w, h


def analyse(path: Path, scale_field, slots: list[dict], overlay_path: Path) -> dict:
    from npec_rig.tags import detect_tags

    row: dict = {}
    box = find_base_reduced(path)
    if box is None:
        row["status"] = "base not found"
        return row
    x, y, w, h = box
    full = cv2.imread(str(path))
    x0, y0 = max(0, x - BASE_MARGIN_PX), max(0, y - BASE_MARGIN_PX)
    crop = full[y0 : y + h + BASE_MARGIN_PX, x0 : x + w + BASE_MARGIN_PX].copy()
    del full

    # Base region: the largest yellow blob's convex hull, grown.
    n, lab, st, _ = cv2.connectedComponentsWithStats(yellow_mask(crop).astype(np.uint8))
    k = 1 + int(np.argmax(st[1:, 4]))
    cnts, _ = cv2.findContours((lab == k).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    hull = cv2.convexHull(max(cnts, key=cv2.contourArea))
    region = np.zeros(crop.shape[:2], np.uint8)
    cv2.fillPoly(region, [hull], 1)
    region = cv2.dilate(region, np.ones((REGION_GROW_PX, REGION_GROW_PX), np.uint8)) > 0
    (bcx, bcy), (bw, bh), _ = cv2.minAreaRect(hull)
    side_px = math.sqrt(bw * bh)

    # Tags in the crop, masked out of both colours.
    tag_mask = np.zeros(crop.shape[:2], np.uint8)
    tags = detect_tags(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY))
    for t in tags:
        cv2.fillPoly(tag_mask, [np.round(np.array(t.corners)).astype(np.int32)], 1)
    tag_mask = tag_mask > 0

    red = red_mask(crop) & region & ~tag_mask
    green = excess_green_mask(crop) & region & ~tag_mask

    # Red pieces, holes (glare) filled, one per solid expected.
    cn, _ = cv2.findContours(red.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    reds = [c for c in cn if cv2.contourArea(c) >= MIN_RED_PX]
    row["red_pieces"] = len(reds)
    if not reds:
        row["status"] = "no red found"
        return row
    # Orientation: the largest green piece is the NE rosette (the largest, and always one piece).
    n, lab, st, cen = cv2.connectedComponentsWithStats(green.astype(np.uint8))
    if n < 2:
        row["status"] = "no green found"
        return row
    big = 1 + int(np.argmax(st[1:, 4]))
    ne_angle = math.atan2(cen[big][1] - bcy, cen[big][0] - bcx)
    corners = corner_angles(ne_angle - math.pi / 2)
    # Cross-check, recorded only: the least round red piece should be the prism, in NW.
    prism = min(reds, key=circularity)
    pc = prism.reshape(-1, 2).mean(0)
    least_round_at = nearest_corner(math.atan2(pc[1] - bcy, pc[0] - bcx), corners)

    cx_full, cy_full = x0 + bcx, y0 + bcy
    row.update(
        status="ok",
        base_x_px=round(cx_full, 1),
        base_y_px=round(cy_full, 1),
        base_side_mm=round(side_px / scale_field.px_per_mm(cx_full, cy_full), 1),
        turn_deg=round(math.degrees(corners["NW"]) % 360, 2),
        slot=nearest_slot(cx_full, cy_full, slots),
        tags_in_crop=" ".join(str(t.tag_id) for t in tags),
        tag_px_masked=int(np.count_nonzero(tag_mask & region)),
        least_round_red_at=least_round_at,
    )

    solid_fill = {}
    for c in reds:
        m = np.zeros(crop.shape[:2], np.uint8)
        cv2.drawContours(m, [c], -1, 1, thickness=cv2.FILLED)
        mx, my = c.reshape(-1, 2).mean(0)
        name = nearest_corner(math.atan2(my - bcy, mx - bcx), corners)
        solid_fill.setdefault(name, []).append((m > 0, c))
    for corner, (sname, known, height) in SOLIDS.items():
        pieces = solid_fill.get(corner, [])
        row[f"{sname}_pieces"] = len(pieces)
        if not pieces:
            continue
        m = np.logical_or.reduce([p[0] for p in pieces])
        ys, xs = np.nonzero(m)
        ppm = scale_field.px_per_mm(x0 + xs.mean(), y0 + ys.mean())
        a = area_mm2(m, ppm)
        row[f"{sname}_mm2"] = round(a, 2)
        row[f"{sname}_err_pct"] = round(100 * (a - known) / known, 1)
        row[f"{sname}_circularity"] = round(circularity(max((p[1] for p in pieces), key=cv2.contourArea)), 3)

    # Green pieces, merged per corner (thin leaves come apart).
    groups: dict[str, list[int]] = {}
    for i in range(1, n):
        if st[i, 4] < MIN_GREEN_PX:
            continue
        name = nearest_corner(math.atan2(cen[i][1] - bcy, cen[i][0] - bcx), corners)
        groups.setdefault(name, []).append(i)
    rosette_masks = {}
    for corner in CORNERS:
        ids = groups.get(corner, [])
        row[f"rosette_{corner}_pieces"] = len(ids)
        if not ids:
            continue
        m = np.isin(lab, ids)
        rosette_masks[corner] = m
        ys, xs = np.nonzero(m)
        ppm = scale_field.px_per_mm(x0 + xs.mean(), y0 + ys.mean())
        (_, _), rad = cv2.minEnclosingCircle(np.column_stack([xs, ys]).astype(np.float32))
        limit = math.pi * (ROSETTE_DIAM_MM[corner] / 2) ** 2
        a = area_mm2(m, ppm)
        row[f"rosette_{corner}_mm2"] = round(a, 1)
        row[f"rosette_{corner}_diam_mm"] = round(2 * rad / ppm, 1)
        row[f"rosette_{corner}_limit_mm2"] = round(limit, 0)
        row[f"rosette_{corner}_below_limit"] = a < limit
    small_green = int(sum(st[i, 4] for i in range(1, n) if st[i, 4] < MIN_GREEN_PX))
    row["green_px_dropped_small"] = small_green

    write_overlay(crop, red, rosette_masks, solid_fill, corners, (bcx, bcy), side_px, tags, row, overlay_path)
    return row


def nearest_slot(x: float, y: float, slots: list[dict]) -> str:
    if not slots:
        return ""
    best = min(slots, key=lambda s: math.hypot(s["centre"][0] - x, s["centre"][1] - y))
    x0, y0, x1, y1 = best["box"]
    return best["name"] if x0 <= x <= x1 and y0 <= y <= y1 else f"{best['name']}?"


def write_overlay(crop, red, rosettes, solid_fill, corners, centre, side_px, tags, row, out: Path) -> None:
    """Masks drawn on a copy of the crop, halved. The original still is never altered."""
    im = crop.copy()
    tint = im.copy()
    for m in rosettes.values():
        tint[m] = (255, 0, 255)
    tint[red] = (255, 255, 0)
    im = cv2.addWeighted(tint, 0.45, im, 0.55, 0)
    font = cv2.FONT_HERSHEY_SIMPLEX

    def label(text, p, scale=1.6):
        p = (int(p[0]), int(p[1]))
        cv2.putText(im, text, p, font, scale, (0, 0, 0), 9)
        cv2.putText(im, text, p, font, scale, (255, 255, 255), 3)

    for corner, m in rosettes.items():
        ys, xs = np.nonzero(m)
        (cx, cy), rad = cv2.minEnclosingCircle(np.column_stack([xs, ys]).astype(np.float32))
        cv2.circle(im, (int(cx), int(cy)), int(rad), (255, 0, 255), 4)
        label(f"{corner} {row.get(f'rosette_{corner}_mm2', '')}", (cx - 140, cy - rad - 15))
    for corner, pieces in solid_fill.items():
        sname = SOLIDS[corner][0]
        for _, c in pieces:
            cv2.drawContours(im, [c], -1, (255, 255, 0), 3)
        mx, my = pieces[0][1].reshape(-1, 2).mean(0)
        ang = corners[corner]
        p = (mx + 70 * math.cos(ang) - 90, my + 70 * math.sin(ang) + 15)
        label(f"{sname} {row.get(f'{sname}_mm2', '')}", p, 1.2)
    for t in tags:
        cv2.polylines(im, [np.round(np.array(t.corners)).astype(np.int32)], True, (0, 165, 255), 4)
    label(f"{row.get('slot', '')}  turn {row.get('turn_deg', '')}", (20, 60))
    im = cv2.resize(im, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(out), im, [cv2.IMWRITE_JPEG_QUALITY, 85])


def capture_rows() -> dict[str, tuple]:
    """rig.db capture rows by still stem path, read only."""
    db = sqlite3.connect(f"file:{RIG / 'rig.db'}?mode=ro", uri=True)
    rows = db.execute(
        "select path, taken_at, calibration, validation, lens_position, focus_locked_at, flags from capture"
    ).fetchall()
    return {r[0]: r[1:] for r in rows}


def main(argv: list[str]) -> None:
    from npec_rig.calibration_store import load_calibration

    ap = argparse.ArgumentParser()
    ap.add_argument("stills", nargs="+", type=Path)
    ap.add_argument("--session-csv", type=Path, help="experiments/round1/session-2026-10-15.csv (#153)")
    ap.add_argument("--out", type=Path, default=HERE)
    args = ap.parse_args(argv)

    steps = {}
    if args.session_csv:
        with args.session_csv.open() as f:
            steps = {(r["experiment_dir"], r["still"]): f"{r['step']} {r['title']}" for r in csv.DictReader(f)}
    captures = capture_rows()
    overlays = args.out / "overlays"
    overlays.mkdir(parents=True, exist_ok=True)
    fields: dict[str, dict] = {}
    rows = []
    for path in sorted(args.stills, key=lambda p: p.stem):
        exp = path.parts[path.parts.index("experiments") + 1]
        rel = str(path.with_suffix("").relative_to(RIG))
        cap = captures.get(rel)
        stem = cap[1] if cap else None
        if stem not in fields:
            cal = json.loads((RIG / "calibration" / f"{stem}.json").read_text())
            lay = RIG / "calibration" / "validations" / "slot-layouts" / f"{stem}.json"
            fields[stem] = {
                "field": load_calibration(RIG / "calibration" / f"{stem}.json").scale_field,
                "lens": cal.get("lens_position"),
                "slots": json.loads(lay.read_text())["slots"] if lay.exists() else [],
            }
        cal = fields[stem]
        row = {
            "still": path.stem,
            "experiment": exp,
            "step": steps.get((exp, path.stem), ""),
            "taken_at_utc": cap[0] if cap else "",
            "calibration": stem,
            "calibration_lens": cal["lens"],
            "validation": cap[2] if cap else "",
            "lens_position": round(cap[3], 3) if cap and cap[3] is not None else "",
            "capture_flags": cap[5] if cap else "",
        }
        print(path.stem, file=sys.stderr, flush=True)
        row.update(analyse(path, cal["field"], cal["slots"], overlays / f"{exp}_{path.stem}.jpg"))
        rows.append(row)

    rows.sort(key=lambda r: r["taken_at_utc"])
    poses = [
        (r["experiment"], r["base_x_px"], r["base_y_px"], r["turn_deg"]) if r.get("status") == "ok" else None
        for r in rows
    ]
    for r, g in zip(rows, static_groups(poses)):
        r["static_group"] = "" if g is None else g

    keys: list[str] = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with (args.out / "results.csv").open("w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=keys)
        wr.writeheader()
        wr.writerows(rows)


if __name__ == "__main__":
    main(sys.argv[1:])
