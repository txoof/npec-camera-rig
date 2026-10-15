"""Round 1 (issue #162): real leaves of known area on the trays, rig area against scan area.

The round 1 green test unchanged (`experiments/round1-benchy/benchy.py`: excess green above 0.1,
green above red), tags masked, area through the calibration scale field at each leaf's centre,
no height correction. The leaves' known areas come from `scan_area.py`; for each still the known
area is read off the straight line between the scan before and the scan after the photos.

    PYTHONPATH=src python3 experiments/round1-leaves/leaves.py

Stills are read only. Overlays (not committed) and results.csv are written next to this file.
"""

from __future__ import annotations

import csv
import itertools
import json
import math
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "round1-benchy"))
import benchy  # noqa: E402  (round 1 colour tests, unchanged)

RIG = Path("/var/lib/npec-rig")
SCANS = HERE / "scans"  # also /var/lib/npec-rig/scans/2026-10-15_leaves/, read only
LEAVES = ("L001", "L002", "L003")
MIN_PIECE_RED = 40  # 1/8 decode pixels, about 2500 full-res px, about 100 mm²; smaller is noise
MARGIN = 120  # full-res px around a leaf's box
NEAR_SMALL = 40  # 1/8 decode px, about 65 mm: farthest a piece of a leaf may lie from its largest piece

# Stills 1 to 32 from 11:54 UTC, Aaron 2026-10-15. Blue: the 3 leaves in a line, moving one slot
# per still along PATH; black: all 3 on a black sheet on one slot, 003 NW, 001 NE, 002 S.
PATH = ["South 1", "South 2", "South 3", "South 4", "South 5", "South 6",
        "North 6", "North 5", "North 4", "North 3", "North 2", "North 1"]


def session() -> list[dict]:
    db = sqlite3.connect(f"file:{RIG / 'rig.db'}?mode=ro", uri=True)
    rows = db.execute(
        "select taken_at, path, calibration from capture where taken_at >= '2026-10-15T11:50' "
        "and taken_at < '2026-10-15T12:05' order by taken_at"
    ).fetchall()
    out = []
    for i, (t, p, cal) in enumerate(rows, start=1):
        if i <= 10:
            setup, side = "blue", "top"
        elif i <= 21:
            setup, side = "black", "top"
        else:
            setup, side = "black", "under"
        out.append({"n": i, "taken_at_utc": t, "path": p, "calibration": cal, "setup": setup, "side": side})
    return out


def scan_areas() -> dict[str, dict]:
    rows = {r["scan"]: r for r in csv.DictReader((HERE / "scan_areas.csv").open())}
    times = {r["scan"]: datetime.fromisoformat(r["scanned_at_utc"])
             for r in csv.DictReader((SCANS / "scan_times.csv").open())}
    out = {}
    for leaf in LEAVES:
        t0, t1 = times[leaf], times[f"{leaf}_after"]
        out[leaf] = {"t0": t0, "a0": float(rows[leaf]["leaf_mm2"]),
                     "t1": t1, "a1": float(rows[f"{leaf}_after"]["leaf_mm2"])}
    return out


def known_at(scan: dict, t: datetime) -> float:
    f = (t - scan["t0"]) / (scan["t1"] - scan["t0"])
    return scan["a0"] + f * (scan["a1"] - scan["a0"])


def scan_contour(leaf: str) -> np.ndarray:
    im = cv2.imread(str(SCANS / f"{leaf}.jpg"))
    m = benchy.excess_green_mask(im)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8))
    big = 1 + int(np.argmax(st[1:, 4]))
    cs, _ = cv2.findContours((lab == big).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    return max(cs, key=cv2.contourArea)


def benchmark_exclusion(small: np.ndarray) -> np.ndarray:
    """1/8 decode mask of the benchmark's base, grown, so its rosettes are never a leaf."""
    y = benchy.yellow_mask(small).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(y)
    out = np.zeros(small.shape[:2], np.uint8)
    for i in range(1, n):
        if 6000 < st[i, 4] < 20000:
            cs, _ = cv2.findContours((lab == i).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.fillPoly(out, [cv2.convexHull(cs[0])], 1)
    return cv2.dilate(out, np.ones((9, 9), np.uint8)) > 0


def table_mask(shape, slots: list[dict]) -> np.ndarray:
    """1/8 decode mask of the two rows: the rows of the slot boxes, across the full image width,
    so the aisle (moss pots) and the floor are left out but a sheet that runs past the end slots
    is not cut off (the first run cut the leaves at South 1 and South 6)."""
    m = np.zeros(shape, bool)
    for row in ("North", "South"):
        boxes = np.array([s["box"] for s in slots if s["name"].startswith(row)]) / 8
        x0, y0 = boxes[:, :2].min(0).astype(int)
        x1, y1 = boxes[:, 2:].max(0).astype(int)
        m[max(0, y0):y1, :] = True
    return m


def nearest_slot(x, y, slots):
    return min(slots, key=lambda s: math.hypot(s["centre"][0] - x, s["centre"][1] - y))["name"]


def find_leaves(small, slots, n_leaves=3):
    """Leaf pieces on the 1/8 decode: green, on the table, not the benchmark. Pieces are grouped
    into `n_leaves` leaves around the largest pieces."""
    green = benchy.excess_green_mask(small) & table_mask(small.shape[:2], slots)
    bench = benchmark_exclusion(small)
    leaf = (green & ~bench).astype(np.uint8)
    # Group on a copy with gaps up to 4 px closed (pale midribs split a leaf); measure unclosed.
    n, lab, st, cen = cv2.connectedComponentsWithStats(cv2.dilate(leaf, np.ones((5, 5), np.uint8)))
    lab = lab * leaf
    pieces = [i for i in range(1, n) if st[i, 4] >= MIN_PIECE_RED]
    seeds = sorted(pieces, key=lambda i: -st[i, 4])[:n_leaves]
    groups = {s: [s] for s in seeds}
    for i in pieces:
        if i in groups:
            continue
        # A piece joins the nearest leaf only when it lies within NEAR_SMALL px of that leaf's box;
        # farther green (tray tags, stray bits) is left out.
        def gap(k):
            x, y, w, h = st[k, :4]
            return math.hypot(max(x - cen[i][0], 0, cen[i][0] - x - w), max(y - cen[i][1], 0, cen[i][1] - y - h))
        s = min(seeds, key=gap)
        if gap(s) <= NEAR_SMALL:
            groups[s].append(i)
    return lab, groups, bench


def analyse(still: dict, field, slots, contours, scans) -> list[dict]:
    from npec_rig.tags import detect_tags

    jpg = RIG / f"{still['path']}.jpg"
    small = cv2.imread(str(jpg), cv2.IMREAD_REDUCED_COLOR_8)
    # On the black sheet the 3 leaves lie almost touching and cannot be split by colour alone:
    # one group, measured together against the sum of their known areas.
    lab, groups, bench = find_leaves(small, slots, n_leaves=1 if still["setup"] == "black" else 3)
    if len(groups) < 3:
        print(f"still {still['n']}: {len(groups)} leaves found", file=sys.stderr)
    full = cv2.imread(str(jpg))
    t = datetime.fromisoformat(still["taken_at_utc"])
    found = []
    for seed, ids in groups.items():
        piece = np.isin(lab, ids).astype(np.uint8)
        touches = bool((cv2.dilate(piece, np.ones((5, 5), np.uint8)) > 0)[bench].any())
        ys, xs = np.nonzero(piece)
        x0, y0 = max(0, xs.min() * 8 - MARGIN), max(0, ys.min() * 8 - MARGIN)
        x1, y1 = min(full.shape[1], (xs.max() + 1) * 8 + MARGIN), min(full.shape[0], (ys.max() + 1) * 8 + MARGIN)
        crop = full[y0:y1, x0:x1]
        # Only full-res green near this leaf's 1/8 pieces counts (grown by 2 small px = 16 px).
        near = cv2.dilate(piece, np.ones((5, 5), np.uint8))
        sy, sx = y0 // 8, x0 // 8
        near = np.kron(near[sy : (y1 + 7) // 8, sx : (x1 + 7) // 8], np.ones((8, 8), np.uint8))
        near = near[y0 - sy * 8 : y1 - sy * 8, x0 - sx * 8 : x1 - sx * 8] > 0
        tag_mask = np.zeros(crop.shape[:2], np.uint8)
        tags = detect_tags(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY))
        for tg in tags:
            cv2.fillPoly(tag_mask, [np.round(np.array(tg.corners)).astype(np.int32)], 1)
        m = benchy.excess_green_mask(crop) & near & (tag_mask == 0)
        my, mx = np.nonzero(m)
        cx, cy = x0 + mx.mean(), y0 + my.mean()
        ppm = field.px_per_mm(cx, cy)
        cs, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        found.append({"x": cx, "y": cy, "area": benchy.area_mm2(m, ppm), "mask": m, "box": (x0, y0, x1, y1),
                      "contour": max(cs, key=cv2.contourArea), "tags": [tg.tag_id for tg in tags],
                      "slot": nearest_slot(cx, cy, slots), "touches": touches})
    del full

    # Identity from Aaron's record, and a shape match against the scans as a cross-check.
    if still["setup"] == "black":
        by_record, best = {id(found[0]): "all 3"}, ["all 3"]
    else:
        by_record = record_identity(still, found)
        best = min(itertools.permutations(LEAVES),
                   key=lambda perm: sum(cv2.matchShapes(f["contour"], contours[l], cv2.CONTOURS_MATCH_I1, 0)
                                        for f, l in zip(found, perm)))
    rows = []
    for f, shape_id in zip(found, best):
        leaf = by_record.get(id(f), "")
        names = LEAVES if leaf == "all 3" else (leaf,) if leaf else ()
        known = sum(known_at(scans[l], t) for l in names) if names else None
        a0 = sum(scans[l]["a0"] for l in names) if names else None
        a1 = sum(scans[l]["a1"] for l in names) if names else None
        rows.append({
            "still_n": still["n"], "still": Path(still["path"]).name, "taken_at_utc": still["taken_at_utc"],
            "calibration": still["calibration"], "setup": still["setup"], "side": still["side"],
            "leaf": leaf, "leaf_by_shape": shape_id, "slot": f["slot"],
            "x_px": round(f["x"]), "y_px": round(f["y"]),
            "rig_mm2": round(f["area"], 1),
            "scan_before_mm2": a0 or "", "scan_after_mm2": a1 or "",
            "known_at_photo_mm2": round(known, 1) if known else "",
            "err_pct": round(100 * (f["area"] - known) / known, 2) if known else "",
            "err_pct_vs_before": round(100 * (f["area"] - a0) / a0, 2) if a0 else "",
            "err_pct_vs_after": round(100 * (f["area"] - a1) / a1, 2) if a1 else "",
            "tags_in_crop": " ".join(map(str, f["tags"])), "touches_benchmark": f["touches"],
        })
    write_overlay(still, found, rows)
    return rows


def record_identity(still: dict, found: list[dict]) -> dict[int, str]:
    """Leaf names from Aaron's record of the session."""
    if still["setup"] == "blue":
        # Still k (1..10): L001 on PATH[k-1], L002 on PATH[k], L003 on PATH[k+1].
        k = still["n"]
        want = {PATH[k - 1]: "L001", PATH[k]: "L002", PATH[k + 1]: "L003"}
        return {id(f): want.get(f["slot"], "") for f in found}
    # Black sheet: the most southern is L002; of the other two, the western is L003.
    south = max(found, key=lambda f: f["y"])
    rest = sorted((f for f in found if f is not south), key=lambda f: f["x"])
    return {id(south): "L002", id(rest[0]): "L003", id(rest[1]): "L001"}


def write_overlay(still, found, rows) -> None:
    xs0 = min(f["box"][0] for f in found); ys0 = min(f["box"][1] for f in found)
    xs1 = max(f["box"][2] for f in found); ys1 = max(f["box"][3] for f in found)
    full = cv2.imread(str(RIG / f"{still['path']}.jpg"))
    im = full[ys0:ys1, xs0:xs1].copy()
    del full
    font = cv2.FONT_HERSHEY_SIMPLEX
    for f, r in zip(found, rows):
        x0, y0, x1, y1 = f["box"]
        sub = im[y0 - ys0 : y1 - ys0, x0 - xs0 : x1 - xs0]
        sub[f["mask"]] = (sub[f["mask"]] * 0.45 + np.array([255, 0, 255]) * 0.55).astype(np.uint8)
        cv2.drawContours(sub, [f["contour"]], -1, (255, 255, 0), 3)
        txt = f"{r['leaf']} ({r['leaf_by_shape']}) {r['rig_mm2']:.0f} {r['err_pct']:+.1f}%" if r["leaf"] else "?"
        p = (int(f["x"] - xs0 - 250), int(y0 - ys0 + 60))
        cv2.putText(im, txt, p, font, 1.8, (0, 0, 0), 10)
        cv2.putText(im, txt, p, font, 1.8, (255, 255, 255), 4)
    s = min(1.0, 1600 / max(im.shape[:2]))
    im = cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(HERE / "overlays" / f"{still['n']:02d}_{Path(still['path']).name}.jpg"), im,
                [cv2.IMWRITE_JPEG_QUALITY, 85])


def add_bands(rows: list[dict]) -> None:
    """Each reading next to its slot's validation band (the session in force for the still).

    The band (p95 of |tag area error| in the slot) covers flat objects at tray-top height. A
    reading is `within_band` when |error| is at most the band; because the known area is itself
    uncertain (the leaves shrank between scans), `band_overlaps_scans` also says whether the band
    overlaps the range from "against the before scan" to "against the after scan". Nothing is
    corrected."""
    db = sqlite3.connect(f"file:{RIG / 'rig.db'}?mode=ro", uri=True)
    sessions: dict[str, dict] = {}
    for r in rows:
        still = db.execute("select validation from capture where path like ?", (f"%{r['still']}",)).fetchone()[0]
        if still not in sessions:
            v = json.loads((RIG / "calibration" / "validations" / f"{still}.json").read_text())
            sessions[still] = {x["name"]: x for x in v["results"]}
        band = sessions[still].get(r["slot"])
        r["validation"] = still
        if not band or band["p95_abs_pct"] is None or r["err_pct"] == "":
            r.update(band_p95_pct="", band_median_pct="", within_band="", band_overlaps_scans="")
            continue
        p95 = band["p95_abs_pct"]
        lo, hi = sorted((float(r["err_pct_vs_before"]), float(r["err_pct_vs_after"])))
        r.update(band_p95_pct=round(p95, 2), band_median_pct=round(band["median_pct"], 2),
                 within_band=abs(float(r["err_pct"])) <= p95, band_overlaps_scans=lo <= p95 and hi >= -p95)


def main() -> None:
    if "--bands-only" in sys.argv:  # add the band columns to an existing results.csv
        rows = list(csv.DictReader((HERE / "results.csv").open()))
        add_bands(rows)
        write_results(rows)
        return

    from npec_rig.calibration_store import load_calibration

    stills = session()
    scans = scan_areas()
    contours = {l: scan_contour(l) for l in LEAVES}
    stems = {s["calibration"] for s in stills}
    fields, layouts = {}, {}
    for stem in stems:
        fields[stem] = load_calibration(RIG / "calibration" / f"{stem}.json").scale_field
        layouts[stem] = json.loads((RIG / "calibration" / "validations" / "slot-layouts" / f"{stem}.json").read_text())["slots"]
    (HERE / "overlays").mkdir(exist_ok=True)
    rows = []
    for s in stills:
        print(s["n"], s["path"], file=sys.stderr, flush=True)
        rows += analyse(s, fields[s["calibration"]], layouts[s["calibration"]], contours, scans)
    add_bands(rows)
    write_results(rows)


def write_results(rows: list[dict]) -> None:
    with (HERE / "results.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
