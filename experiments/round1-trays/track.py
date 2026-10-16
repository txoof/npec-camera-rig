"""Round 1 (issue #171): tray tracking over time on the 15 October stills.

Method and decisions: docs/metrology-log.md section 15.5d and its amendments, written before this
ran. Reads the full FastSAM run (fastsam-full176.csv, -masks.csv), the tag cache in scratch and
rig.db (read only). No Hailo run, no photos read, nothing written to the experiment folder.

    cd experiments/round1-trays
    PYTHONPATH=<worktree>/src <venv python> track.py fastsam-full176.csv

Writes track-<name>.csv (one row per tray per still) and track-<name>-moves.csv (one row per
pair of consecutive stills) next to this file, and the timeline picture to
~/scratch/round1-trays/track/. Patch 3 (filled from neighbours) is not in this slice.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict

import cv2
import numpy as np

import summarise
import trays

MOVE_MM = 50.0  # a tray moved if its centre shifts more than this between two stills (decision)
FLIP_DEG = 90.0  # a tray turned if its tag heading changes more than this (decision)
TAG_NEAR_MM = trays.TAG_NEAR_MM  # patch 2: a tag inside a mask's box widened by this much
OUT = trays.SCRATCH / "track"

# Labels in the record. Only "measured" positions are used for moves and spread.
MEASURED, PATCH2, ELIMINATION, UNRESOLVED, IN_TWO_TRAY_MASK, NO_MASK = (
    "measured", "kept by patch 2", "inferred by elimination", "tag moved to unresolved",
    "in a two-tray mask", "no mask")
NOTHING_MOVED = {"1", "R2-1", "R3"}  # steps where nothing moved (15.5d), for the spread


# ---------------------------------------------------------------- pure functions (unit tested)


def heading_change(a: float, b: float) -> float:
    """Smallest angle between two headings, 0 to 180 degrees."""
    d = abs(a - b) % 360
    return min(d, 360 - d)


def distance_mm(p: tuple[float, float], q: tuple[float, float], px_per_mm) -> float:
    """Distance between two image points in mm, at the scale of their midpoint."""
    ppm = px_per_mm((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
    return float(np.hypot(p[0] - q[0], p[1] - q[1])) / ppm


def in_box(mask: dict, x: float, y: float, ppm: float, near_mm: float = TAG_NEAR_MM) -> bool:
    """Whether (x, y) lies inside the mask's axis-aligned box widened by near_mm (amendment)."""
    hw = (float(mask["ew_mm"]) / 2 + near_mm) * ppm
    hh = (float(mask["ns_mm"]) / 2 + near_mm) * ppm
    return abs(x - float(mask["cx_full"])) <= hw and abs(y - float(mask["cy_full"])) <= hh


def patch_two_tray_mask(mask: dict, tags_by_tray: dict[int, list[dict]], ppm: float) -> tuple[int, int] | None:
    """Patch 2: a mask holding the tags of two trays, one tray's tags all inside its box and the
    other's all outside. Returns (tray kept, tray sent to unresolved), or None."""
    held = [int(t) for t in mask["trays"].split()]
    if len(held) != 2:
        return None
    inside = {t: [in_box(mask, g["cx"], g["cy"], ppm) for g in tags_by_tray.get(t, [])] for t in held}
    a, b = held
    if inside[a] and inside[b] and all(inside[a]) and not any(inside[b]):
        return a, b
    if inside[a] and inside[b] and all(inside[b]) and not any(inside[a]):
        return b, a
    return None


def classify_moves(mask_mm: float | None, tag_mm: float, turn_deg: float) -> dict:
    """One tray between two stills: tag reference and mask result (amendment, *Reference per tray*).

    A turn moves the tag across the tray, so where the tag turned there is no position reference
    from the tag and the mask result is reported but not judged."""
    turned = turn_deg > FLIP_DEG
    ref = None if turned else tag_mm > MOVE_MM
    mask = None if mask_mm is None else mask_mm > MOVE_MM
    if ref is None or mask is None:
        verdict = "not judged"
    elif ref and mask:
        verdict = "move found"
    elif ref:
        verdict = "move missed"
    elif mask:
        verdict = "false move"
    else:
        verdict = "still, agreed"
    return {"turned": turned, "tag_moved": ref, "mask_moved": mask, "verdict": verdict}


def resolve_still(masks: list[dict], tags_by_tray: dict[int, list[dict]], ppm: float) -> dict[int, dict]:
    """Every A1 tray of one still: its label and, if it has one, the mask giving its position.

    Raw: a tray in exactly one mask, judged 'one tray', is measured (the 15.5c rule). Then patch 2
    on two-tray masks, then patch 1 (one tray left, one tagless tray-shaped mask)."""
    holding = defaultdict(list)
    for m in masks:
        for t in m["trays"].split():
            holding[int(t)].append(m)
    out = {}
    for t in sorted(tags_by_tray):
        ms = holding[t]
        if len(ms) == 1 and ms[0]["verdict"] == "one tray":
            out[t] = {"label": MEASURED, "mask": ms[0]}
        elif ms and any(m["verdict"] == "several trays" for m in ms):
            out[t] = {"label": IN_TWO_TRAY_MASK, "mask": None}
        else:
            out[t] = {"label": NO_MASK, "mask": None}
    for m in masks:
        if m["verdict"] != "several trays":
            continue
        r = patch_two_tray_mask(m, tags_by_tray, ppm)
        if r and all(len(holding[t]) == 1 for t in r):
            out[r[0]] = {"label": PATCH2, "mask": m}
            out[r[1]] = {"label": UNRESOLVED, "mask": None}
    left = [t for t, v in out.items() if v["mask"] is None]
    tagless = [m for m in masks if m["verdict"] == "no tray"]
    if len(left) == 1 and len(tagless) == 1:
        out[left[0]] = {"label": ELIMINATION, "mask": tagless[0], "was": out[left[0]]["label"]}
    return out


# ---------------------------------------------------------------- run


def load(name: str):
    from npec_rig.calibration_store import load_calibration

    res = list(csv.DictReader(open(trays.HERE / f"fastsam-{name}.csv")))
    masks = defaultdict(list)
    for m in csv.DictReader(open(trays.HERE / f"fastsam-{name}-masks.csv")):
        masks[m["still"]].append(m)
    scales = {}
    stills = []
    for r in res:
        info = trays.capture_info(r["still"])
        if info["calibration"] not in scales:
            art = load_calibration(trays.RIG / "calibration" / f"{info['calibration']}.json")
            scales[info["calibration"]] = art.scale_field
        stills.append({"still": r["still"], "step": r["step"], "taken_at": info["taken_at"],
                       "scale": scales[info["calibration"]]})
    stills.sort(key=lambda s: s["taken_at"])
    return stills, masks


def main(argv: list[str]) -> None:
    name = argv[0].removeprefix("fastsam-").removesuffix(".csv")
    stills, masks = load(name)
    rows, per_still = [], []
    for k, s in enumerate(stills):
        tags = trays.detect(s["still"], None)
        by_tray = defaultdict(list)
        for g in tags:
            t = trays.tray_of(g["id"])
            if t is not None:
                by_tray[t].append(g)
        a1 = {g["id"]: g for g in tags if g["id"] in trays.A1_TAGS}
        ppm0 = s["scale"].px_per_mm(4576, 3472)  # image centre of a 9152 x 6944 still
        resolved = resolve_still(masks[s["still"]], {t: by_tray[t] for t in a1}, ppm0)
        # Slot check of 15.5c (provisional reference: row and order), on any tray with a mask.
        placed = {t: (float(v["mask"]["cx_full"]), float(v["mask"]["cy_full"])) for t, v in resolved.items() if v["mask"]}
        slot_m = summarise.row_order(placed)
        slot_t = summarise.row_order({t: (g["cx"], g["cy"]) for t, g in a1.items()})
        for t, v in resolved.items():
            g, m = a1[t], v["mask"]
            rows.append({"order": k, "still": s["still"], "taken_at_utc": s["taken_at"], "step": s["step"], "tray": t,
                         "label": v["label"], "before_patch_1": v.get("was", ""), "source": m and m["source"],
                         "x_px": m and m["cx_full"], "y_px": m and m["cy_full"],
                         "x_mm": m and round(float(m["cx_full"]) / ppm0), "y_mm": m and round(float(m["cy_full"]) / ppm0),
                         "tag_x_px": round(g["cx"]), "tag_y_px": round(g["cy"]), "heading_deg": g["heading_deg"],
                         "slot_tag": slot_t.get(t, ""), "slot_mask": slot_m.get(t, ""),
                         "slot_agrees": bool(slot_m) and slot_m.get(t) == slot_t.get(t)})
        per_still.append(s)
    trays.write_csv(trays.HERE / f"track-{name}.csv", rows)
    by = defaultdict(dict)
    for r in rows:
        by[r["order"]][r["tray"]] = r

    # Moves between consecutive stills, measured positions only.
    moves = []
    for k in range(1, len(stills)):
        a, b, scale = by[k - 1], by[k], stills[k]["scale"]
        pair = f"{stills[k - 1]['step']} to {stills[k]['step']}" if stills[k - 1]["step"] != stills[k]["step"] \
            else f"within {stills[k]['step']}"
        for t in sorted(b):
            ra, rb = a[t], b[t]
            tag_mm = distance_mm((ra["tag_x_px"], ra["tag_y_px"]), (rb["tag_x_px"], rb["tag_y_px"]), scale.px_per_mm)
            both = ra["label"] == rb["label"] == MEASURED
            mask_mm = distance_mm((float(ra["x_px"]), float(ra["y_px"])), (float(rb["x_px"]), float(rb["y_px"])),
                                  scale.px_per_mm) if both else None
            c = classify_moves(mask_mm, tag_mm, heading_change(ra["heading_deg"], rb["heading_deg"]))
            moves.append({"pair": pair, "from": stills[k - 1]["still"], "to": stills[k]["still"], "tray": t,
                          "tag_mm": round(tag_mm, 1), "mask_mm": None if mask_mm is None else round(mask_mm, 1),
                          **c})
    trays.write_csv(trays.HERE / f"track-{name}-moves.csv", moves)
    report(rows, moves, stills)
    timeline(rows, stills, OUT / f"timeline-{name}.png")


def report(rows: list[dict], moves: list[dict], stills: list[dict]) -> None:
    n = len(stills)
    print(f"trays by label, of {len(rows)}:")
    for lab in (MEASURED, PATCH2, ELIMINATION, UNRESOLVED, IN_TWO_TRAY_MASK, NO_MASK):
        print(f"  {lab:26s} {sum(r['label'] == lab for r in rows)}")
    for title, ok in (("raw", {MEASURED}), ("after patches 1 and 2", {MEASURED, PATCH2, ELIMINATION})):
        right = sum(r["label"] in ok for r in rows)
        passing = sum(all(r["label"] in ok and r["slot_agrees"] for r in rows if r["order"] == k) for k in range(n))
        print(f"{title}: trays right {right}/{len(rows)}, stills passing {passing}/{n}")
    print("\nmoves (tag reference against mask result, trays):")
    pairs = defaultdict(list)
    for m in moves:
        pairs[m["pair"]].append(m)
    keys = ["move found", "move missed", "false move", "still, agreed", "not judged"]
    print(f"  {'pair':26s} {'stills':>6s} {'turned':>6s} " + " ".join(f"{k:>13s}" for k in keys))
    for p, ms in pairs.items():
        print(f"  {p:26s} {len(ms) // 12:6d} {sum(m['turned'] for m in ms):6d} "
              + " ".join(f"{sum(m['verdict'] == k for m in ms):13d}" for k in keys))
    print("\nposition spread where nothing moved (measured only, mm from the tray's mean, by scale at image centre):")
    for step in sorted(NOTHING_MOVED):
        d = []
        for t in range(1, 13):
            pts = np.array([(float(r["x_mm"]), float(r["y_mm"])) for r in rows
                            if r["step"] == step and r["tray"] == t and r["label"] == MEASURED])
            if len(pts) > 1:
                d += list(np.hypot(*(pts - pts.mean(axis=0)).T))
        if d:
            print(f"  {step:5s} n {len(d):4d}  rms {np.sqrt(np.mean(np.square(d))):5.1f}  max {max(d):5.1f}")
    # Added after the first run (15.5d, first slice): distance of each position from its tray's
    # median in a step where nothing moved, at the local scale; patched positions shown, not counted.
    print(f"\npositions more than {MOVE_MM:.0f} mm from the tray's median in its step (nothing moved, local scale):")
    scale = {k: s["scale"] for k, s in enumerate(stills)}
    off = set()
    for step in sorted(NOTHING_MOVED):
        for t in range(1, 13):
            rs = [r for r in rows if r["step"] == step and r["tray"] == t and r["x_px"] is not None]
            meas = [r for r in rs if r["label"] == MEASURED]
            if len(meas) < 2:
                continue
            med = tuple(np.median([(float(r["x_px"]), float(r["y_px"])) for r in meas], axis=0))
            for r in rs:
                d = distance_mm((float(r["x_px"]), float(r["y_px"])), med, scale[r["order"]].px_per_mm)
                if r["label"] != MEASURED:
                    print(f"  {step:5s} {r['still']} tray {t:2d} {r['label']:24s} {d:6.1f} mm (patched, not counted)")
                elif d > MOVE_MM:
                    off.add((r["order"], t))
                    print(f"  {step:5s} {r['still']} tray {t:2d} {r['source']:24s} {d:6.1f} mm")
    right = sum(r["label"] == MEASURED and (r["order"], r["tray"]) not in off for r in rows)
    passing = sum(all(r["label"] == MEASURED and r["slot_agrees"] and (k, r["tray"]) not in off
                      for r in rows if r["order"] == k) for k in range(n))
    print(f"raw, if those {len(off)} count as wrong: trays right {right}/{len(rows)}, stills passing {passing}/{n}")
    turned = [m["mask_mm"] for m in moves if m["turned"] and m["mask_mm"] is not None]
    if turned:
        print(f"mask centre shift where the tag turned: n {len(turned)}, max {max(turned):.1f} mm")


def timeline(rows: list[dict], stills: list[dict], out) -> None:
    """One strip per tray: east-west (blue) and north-south (orange) position against still order.
    Markers: filled circle measured, open square patched, cross none. Steps marked and named."""
    n, left, strip, top = len(stills), 70, 90, 60
    w, h = left + 8 * n + 20, top + 12 * strip + 20
    im = np.full((h, w, 3), 255, np.uint8)
    xs = lambda k: left + 8 * k + 4
    starts = [k for k in range(n) if k == 0 or stills[k]["step"] != stills[k - 1]["step"]]
    for i, k in enumerate(starts):  # labels on two lines, so close steps do not overlap
        cv2.line(im, (xs(k) - 4, top - 10 - 12 * (i % 2)), (xs(k) - 4, h - 10), (160, 160, 160), 1)
        cv2.putText(im, stills[k]["step"], (xs(k) - 2, top - 14 - 12 * (i % 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
    vals = [float(r[a]) for r in rows if r["x_mm"] is not None for a in ("x_mm", "y_mm")]
    lo, hi = min(vals), max(vals)
    for t in range(1, 13):
        y0 = top + (t - 1) * strip
        cv2.rectangle(im, (left, y0 + 4), (w - 20, y0 + strip - 4), (220, 220, 220), 1)
        cv2.putText(im, f"tray {t}", (6, y0 + strip // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
        ys = lambda v: int(y0 + strip - 8 - (v - lo) / (hi - lo) * (strip - 16))
        for r in rows:
            if r["tray"] != t:
                continue
            x = xs(r["order"])
            if r["x_mm"] is None:
                cv2.drawMarker(im, (x, y0 + strip // 2), (0, 0, 200), cv2.MARKER_CROSS, 7, 1)
                continue
            for a, col in (("x_mm", (180, 90, 0)), ("y_mm", (0, 130, 240))):
                p = (x, ys(float(r[a])))
                if r["label"] == MEASURED:
                    cv2.circle(im, p, 2, col, -1)
                else:
                    cv2.rectangle(im, (p[0] - 3, p[1] - 3), (p[0] + 3, p[1] + 3), col, 1)
    cv2.putText(im, f"blue east-west, orange north-south, {lo:.0f} to {hi:.0f} mm | dot measured, square patched, "
                "red cross no position | x: stills in time order", (left, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), im)
    print(f"\ntimeline: {out}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
