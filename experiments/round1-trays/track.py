"""Round 1 (issue #171): tray tracking over time on the 15 October stills.

Method and decisions: docs/metrology-log.md section 15.5d and its amendments, written before this
ran. Reads the full FastSAM run (fastsam-full176.csv, -masks.csv), the tag cache in scratch and
rig.db (read only). No Hailo run, no photos read, nothing written to the experiment folder.

    cd experiments/round1-trays
    PYTHONPATH=<worktree>/src <venv python> track.py fastsam-full176.csv

Writes track-<name>.csv (one row per tray per still) and track-<name>-moves.csv (one row per
pair of consecutive stills) next to this file, and the timeline picture and the evidence
pictures (track/evidence-<name>/, drawn on the overlays of --overlays) to ~/scratch/round1-trays/.
"""

from __future__ import annotations

import argparse
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
FILL_MAX_GAP = 3  # patch 3: at most this many consecutive stills filled (decision)
FILL_AGREE_MM = 20.0  # patch 3: the positions before and after the gap agree within this (decision)
OUT = trays.SCRATCH / "track"

# Labels in the record. Only "measured" positions are used for moves and spread.
MEASURED, PATCH2, ELIMINATION, UNRESOLVED, IN_TWO_TRAY_MASK, NO_MASK = (
    "measured", "kept by patch 2", "inferred by elimination", "tag moved to unresolved",
    "in a two-tray mask", "no mask")
FILLED = "filled from neighbours"
RIGHT = {MEASURED, PATCH2, ELIMINATION, FILLED}  # with a position the rig would report


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


def fill_gaps(good: list[bool], need: list[bool], steps: list[str], max_gap: int = FILL_MAX_GAP) -> list[tuple[int, int]]:
    """Patch 3, the rules on order alone: runs [i, j) of stills that need a position, at most
    max_gap long, with a good still just before and just after, all in one step (so never at a
    sequence end and never across a step boundary). The caller checks position and heading."""
    out, n, i = [], len(good), 0
    while i < n:
        if not need[i]:
            i += 1
            continue
        j = i
        while j < n and need[j]:
            j += 1
        if (j - i <= max_gap and i > 0 and j < n and good[i - 1] and good[j]
                and len({steps[k] for k in range(i - 1, j + 1)}) == 1):
            out.append((i, j))
        i = j
    return out


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
    argv = trays.session_argv(argv)
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("results", help="fastsam-NAME.csv")
    ap.add_argument("--overlays", default="fastsam-stills-m1.15-fb",
                    help="folder in scratch holding that run's fastsam.py overlays (-holes for --fill-holes)")
    args = ap.parse_args(argv)
    name = args.results.removeprefix("fastsam-").removesuffix(".csv")
    stills, masks = load(name)
    rows, per_still = [], []
    for k, s in enumerate(stills):
        tags = trays.detect(s["still"], None)
        by_tray = defaultdict(list)
        for g in tags:
            t = trays.tray_of(g["id"])
            if t is not None:
                by_tray[t].append(g)
        a1 = {g["id"]: g for g in tags if g["id"] in trays.SESSION.trays}
        ppm0 = s["scale"].px_per_mm(4576, 3472)  # image centre of a 9152 x 6944 still
        resolved = resolve_still(masks[s["still"]], {t: by_tray[t] for t in a1}, ppm0)
        # Slot check of 15.5c (provisional reference: row and order), on any tray with a mask.
        placed = {t: (float(v["mask"]["cx_full"]), float(v["mask"]["cy_full"])) for t, v in resolved.items() if v["mask"]}
        slot_m = summarise.row_order(placed)
        slot_t = summarise.row_order({t: (g["cx"], g["cy"]) for t, g in a1.items()})
        for t, v in resolved.items():
            g, m = a1[t], v["mask"]
            rows.append({"order": k, "still": s["still"], "taken_at_utc": s["taken_at"], "step": s["step"], "tray": t,
                         "label": v["label"], "label_raw": v.get("was", v["label"]) if v["label"] == ELIMINATION else v["label"],
                         "before_patch_1": v.get("was", ""), "source": m and m["source"],
                         "x_px": m and m["cx_full"], "y_px": m and m["cy_full"],
                         "ew_mm": m and m["ew_mm"], "ns_mm": m and m["ns_mm"],
                         "x_mm": m and round(float(m["cx_full"]) / ppm0), "y_mm": m and round(float(m["cy_full"]) / ppm0),
                         "tag_x_px": round(g["cx"]), "tag_y_px": round(g["cy"]), "heading_deg": g["heading_deg"],
                         "slot_tag": slot_t.get(t, ""), "slot_mask": slot_m.get(t, ""),
                         "slot_agrees": bool(slot_m) and slot_m.get(t) == slot_t.get(t),
                         "off_median_mm": None, "before_patch_3": "", "x_px_before_fill": None, "y_px_before_fill": None, "fill_refused": "", "slot_agrees_final": False})
        per_still.append(s)
    by = defaultdict(dict)
    for r in rows:
        by[r["order"]][r["tray"]] = r
    # Moves and spread from the raw positions (planned measures), before anything is patched.
    moves = moves_between(by, stills, lambda r: r["label"] == MEASURED)
    spread_raw = spread(rows, lambda r: r["label"] == MEASURED)
    for (k, t), d in off_positions(rows, stills).items():
        by[k][t]["off_median_mm"] = round(d, 1)
    patch3(by, stills, masks)
    final_slots(by)
    trays.write_csv(trays.HERE / f"track-{name}.csv", rows)
    trays.write_csv(trays.HERE / f"track-{name}-moves.csv", moves)
    trays.write_csv(trays.HERE / f"track-{name}-stills.csv", per_still_counts(by, stills))
    after = moves_between(by, stills, lambda r: r["label"] in RIGHT and not is_off(r))
    report(rows, moves, stills, spread_raw, after)
    timeline(rows, stills, OUT / f"timeline-{name}.png")
    evidence(rows, stills, trays.SCRATCH / args.overlays, OUT / f"evidence-{name}")


def evidence(rows: list[dict], stills: list[dict], src, out) -> None:
    """Every still with a patched, filled or wrong tray: the 15.5c overlay (read, not altered) with
    the final positions drawn over it as tray-sized boxes, each with its label in words."""
    out.mkdir(parents=True, exist_ok=True)
    marks = {FILLED: ("FILLED", (255, 255, 0)), PATCH2: ("KEPT BY PATCH 2", (0, 255, 255)),
             ELIMINATION: ("BY ELIMINATION", (255, 0, 255))}
    by = defaultdict(list)
    for r in rows:
        if r["label"] != MEASURED or r["off_median_mm"] is not None:
            by[r["order"]].append(r)
    for k, rs in by.items():
        im = cv2.imread(str(src / f"{stills[k]['still']}.jpg"))
        if im is None:
            continue
        f = im.shape[1] / 9152  # overlay size over full resolution
        ppm = stills[k]["scale"].px_per_mm(4576, 3472) * f
        hw, hh = trays.TRAY_EW_MM / 2 * ppm, trays.TRAY_NS_MM / 2 * ppm

        def box(x, y, col, lines, dashed=False):
            x, y = float(x) * f, float(y) * f
            p0, p1 = (int(x - hw), int(y - hh)), (int(x + hw), int(y + hh))
            cv2.rectangle(im, p0, p1, col, 1 if dashed else 3)
            if dashed:
                cv2.line(im, p0, p1, col, 2)
                cv2.line(im, (p0[0], p1[1]), (p1[0], p0[1]), col, 2)
            for i, text in enumerate(lines):
                y0 = p1[1] - 12 - 22 * (len(lines) - 1) if dashed else p0[1] + 22  # wrong: bottom of its box
                org = (p0[0] + 6, y0 + 22 * i)
                cv2.putText(im, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4)
                cv2.putText(im, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)

        notes = []
        for r in rs:
            t = r["tray"]
            if r["off_median_mm"] is not None:
                x, y = (r["x_px_before_fill"], r["y_px_before_fill"]) if r["label"] == FILLED else (r["x_px"], r["y_px"])
                box(x, y, (0, 0, 255), [f"WRONG tray {t}", f"{r['off_median_mm']:.0f} mm off"], dashed=True)
            if r["label"] in marks:
                word, col = marks[r["label"]]
                box(r["x_px"], r["y_px"], col, [f"{word} tray {t}"])
            elif r["label"] != MEASURED:
                why = f", fill refused: {r['fill_refused']}" if r["fill_refused"] else ""
                notes.append(f"tray {t}: {r['label']}, no position{why}")
            elif r["fill_refused"]:
                notes.append(f"tray {t}: still wrong, fill refused: {r['fill_refused']}")
        bar = f"{stills[k]['still']} step {stills[k]['step']} | tracking (#171): " + ("; ".join(notes) or "every tray placed")
        cv2.rectangle(im, (0, im.shape[0] - 30), (im.shape[1], im.shape[0]), (0, 0, 0), -1)
        cv2.putText(im, bar, (8, im.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        cv2.imwrite(str(out / f"{stills[k]['step']}_{stills[k]['still']}.jpg"), im, [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(f"evidence: {len(by)} stills in {out}")


def moves_between(by: dict, stills: list[dict], use) -> list[dict]:
    """Every tray between consecutive stills: tag reference against the mask centre, judged only
    where use(row) holds in both stills."""
    moves = []
    for k in range(1, len(stills)):
        a, b, scale = by[k - 1], by[k], stills[k]["scale"]
        pair = f"{stills[k - 1]['step']} to {stills[k]['step']}" if stills[k - 1]["step"] != stills[k]["step"] \
            else f"within {stills[k]['step']}"
        for t in sorted(b):
            ra, rb = a[t], b[t]
            tag_mm = distance_mm((ra["tag_x_px"], ra["tag_y_px"]), (rb["tag_x_px"], rb["tag_y_px"]), scale.px_per_mm)
            mask_mm = distance_mm((float(ra["x_px"]), float(ra["y_px"])), (float(rb["x_px"]), float(rb["y_px"])),
                                  scale.px_per_mm) if use(ra) and use(rb) else None
            c = classify_moves(mask_mm, tag_mm, heading_change(ra["heading_deg"], rb["heading_deg"]))
            moves.append({"pair": pair, "from": stills[k - 1]["still"], "to": stills[k]["still"], "tray": t,
                          "tag_mm": round(tag_mm, 1), "mask_mm": None if mask_mm is None else round(mask_mm, 1),
                          **c})
    return moves


def spread(rows: list[dict], use, steps: set[str] | None = None) -> dict[str, tuple[int, float, float]]:
    """Per step where nothing moved: positions, rms and max distance from the tray's mean, in mm
    by the scale at the image centre."""
    out = {}
    for step in sorted(steps or trays.SESSION.nothing_moved):
        d = []
        for t in sorted({r["tray"] for r in rows}):
            pts = np.array([(float(r["x_mm"]), float(r["y_mm"])) for r in rows
                            if r["step"] == step and r["tray"] == t and use(r)])
            if len(pts) > 1:
                d += list(np.hypot(*(pts - pts.mean(axis=0)).T))
        if d:
            out[step] = (len(d), float(np.sqrt(np.mean(np.square(d)))), float(max(d)))
    return out


def per_still_counts(by: dict, stills: list[dict]) -> list[dict]:
    """One row per still: how many trays were measured, patched, filled, wrong or without a position."""
    out = []
    for k, s in enumerate(stills):
        rs = list(by[k].values())
        n = lambda f: sum(1 for r in rs if f(r))
        out.append({"order": k, "still": s["still"], "step": s["step"], "taken_at_utc": s["taken_at"],
                    "measured": n(lambda r: r["label"] == MEASURED and not is_off(r)),
                    "kept_by_patch_2": n(lambda r: r["label"] == PATCH2),
                    "inferred_by_elimination": n(lambda r: r["label"] == ELIMINATION),
                    "filled_from_neighbours": n(lambda r: r["label"] == FILLED),
                    "wrong_not_filled": n(is_off),
                    "no_position": n(lambda r: r["x_px"] is None),
                    "passes_raw": all(r["label_raw"] == MEASURED and r["slot_agrees"] for r in rs),
                    "passes_after_patches": all(r["label"] in RIGHT and not is_off(r) and r["slot_agrees_final"] for r in rs)})
    return out


def is_off(r: dict) -> bool:
    """A measured position counted wrong by tracking and not since filled."""
    return r["off_median_mm"] is not None and r["label"] != FILLED


def off_positions(rows: list[dict], stills: list[dict], steps: set[str] | None = None) -> dict[tuple[int, int], float]:
    """Measured positions more than MOVE_MM from the tray's median in a step where nothing moved,
    at the local scale. Counted as wrong (Aaron, 2026-10-16; 15.5d, first slice)."""
    out = {}
    for step in steps or trays.SESSION.nothing_moved:
        for t in sorted({r["tray"] for r in rows}):
            meas = [r for r in rows if r["step"] == step and r["tray"] == t and r["label"] == MEASURED]
            if len(meas) < 2:
                continue
            med = tuple(np.median([(float(r["x_px"]), float(r["y_px"])) for r in meas], axis=0))
            for r in meas:
                d = distance_mm((float(r["x_px"]), float(r["y_px"])), med, stills[r["order"]]["scale"].px_per_mm)
                if d > MOVE_MM:
                    out[(r["order"], t)] = d
    return out


def patch3(by: dict, stills: list[dict], masks: dict) -> None:
    """Patch 3: fill a tray without a right position from the good stills before and after it."""
    steps = [s["step"] for s in stills]
    for t in sorted({t for trs in by.values() for t in trs}):
        seq = [by[k][t] for k in range(len(stills))]
        good = [r["label"] == MEASURED and not is_off(r) for r in seq]
        need = [r["x_px"] is None or is_off(r) for r in seq]
        for i, j in fill_gaps(good, need, steps):
            a, b = seq[i - 1], seq[j]
            pa, pb = (float(a["x_px"]), float(a["y_px"])), (float(b["x_px"]), float(b["y_px"]))
            ppm = stills[i]["scale"].px_per_mm
            why = ""
            if distance_mm(pa, pb, ppm) > FILL_AGREE_MM:
                why = "before and after disagree"
            elif heading_change(a["heading_deg"], b["heading_deg"]) > FLIP_DEG:
                why = "heading changed"
            x, y = (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2
            for k in range(i, j):
                others = [m for m in masks[stills[k]["still"]] if m["trays"] and m["trays"] != str(t)]
                if not why and any(in_box(m, x, y, ppm(x, y), 0.0) for m in others):
                    why = "another mask covers it"
            for k in range(i, j):
                r = seq[k]
                if why:
                    r["fill_refused"] = why
                    continue
                r["before_patch_3"] = "off" if is_off(r) else r["label"]
                r["x_px_before_fill"], r["y_px_before_fill"] = r["x_px"], r["y_px"]
                r["label"], r["source"], r["x_px"], r["y_px"] = FILLED, "", round(x), round(y)
                ppm0 = stills[k]["scale"].px_per_mm(4576, 3472)
                r["x_mm"], r["y_mm"] = round(x / ppm0), round(y / ppm0)


def final_slots(by: dict) -> None:
    """The slot check of 15.5c again, on the positions left after every patch."""
    for k, trs in by.items():
        pos = {t: (float(r["x_px"]), float(r["y_px"])) for t, r in trs.items() if r["label"] in RIGHT and not is_off(r)}
        slot_m = summarise.row_order(pos)
        for t, r in trs.items():
            r["slot_agrees_final"] = bool(slot_m) and slot_m.get(t) == r["slot_tag"]


def report(rows: list[dict], moves: list[dict], stills: list[dict], spread_raw: dict, after: list[dict]) -> None:
    n = len(stills)
    print(f"trays by label, of {len(rows)}:")
    for lab in (MEASURED, PATCH2, ELIMINATION, UNRESOLVED, IN_TWO_TRAY_MASK, NO_MASK):
        print(f"  {lab:26s} {sum(r['label'] == lab for r in rows)}")
    print(f"  {FILLED:26s} {sum(r['label'] == FILLED for r in rows)}"
          f" (of them off before: {sum(r.get('before_patch_3') == 'off' for r in rows)})")
    refused = defaultdict(int)
    for r in rows:
        if r.get("fill_refused"):
            refused[r["fill_refused"]] += 1
    print(f"  patch 3 refused: {dict(refused) or 'none'}")
    print(f"  no right position left: {sum(r['label'] not in RIGHT or is_off(r) for r in rows)}")
    on = lambda r: r["off_median_mm"] is None
    levels = (("raw, 15.5c rule", lambda r: r["label_raw"] == MEASURED, "slot_agrees"),
              ("raw, off positions wrong", lambda r: r["label_raw"] == MEASURED and on(r), "slot_agrees"),
              ("after patches 1 and 2", lambda r: (r["before_patch_3"] or r["label"]) in {MEASURED, PATCH2, ELIMINATION}
               and on(r), "slot_agrees"),
              ("after patch 3", lambda r: r["label"] in RIGHT and not is_off(r), "slot_agrees_final"))
    sets = {st: name for name, sts in trays.SESSION.sets.items() for st in sts}
    print(f"\n  {'':26s} " + " ".join(f"{x:>22s}" for x in ("all", "gaps", "touching")))
    for title, ok, slot in levels:
        cells = []
        for which in (None, "gaps", "touching"):
            ks = [k for k in range(n) if which is None or sets[stills[k]["step"]] == which]
            rs = [r for r in rows if r["order"] in set(ks)]
            right = sum(ok(r) for r in rs)
            passing = sum(all(ok(r) and r[slot] for r in rs if r["order"] == k) for k in ks)
            cells.append(f"{right:4d}/{len(rs):4d} {passing:3d}/{len(ks):3d}")
        print(f"  {title:26s} " + " ".join(f"{c:>22s}" for c in cells))
    print("  (trays right, stills passing)")
    print("\nmoves (tag reference against mask result, trays):")
    pairs = defaultdict(list)
    for m in moves:
        pairs[m["pair"]].append(m)
    keys = ["move found", "move missed", "false move", "still, agreed", "not judged"]
    print(f"  {'pair':26s} {'stills':>6s} {'turned':>6s} " + " ".join(f"{k:>13s}" for k in keys))
    for p, ms in pairs.items():
        print(f"  {p:26s} {len(ms) // 12:6d} {sum(m['turned'] for m in ms):6d} "
              + " ".join(f"{sum(m['verdict'] == k for m in ms):13d}" for k in keys))
    fin = defaultdict(int)
    for m in after:
        if m["pair"] == "within R3":
            fin[m["verdict"]] += 1
    print(f"  within R3 after all patches (patched positions included): {dict(fin)}")
    spread_ok = spread(rows, lambda r: r["label"] == MEASURED and r["off_median_mm"] is None)
    for title, sp in (("raw, all measured", spread_raw), ("measured, not counted wrong", spread_ok)):
        print(f"\nposition spread where nothing moved ({title}; mm from the tray's mean, scale at image centre):")
        for step, (n_, rms, mx) in sp.items():
            print(f"  {step:5s} n {n_:4d}  rms {rms:5.1f}  max {mx:5.1f}")
    # Added after the first run (15.5d, first slice), counted as wrong since.
    print(f"\npositions more than {MOVE_MM:.0f} mm from the tray's median in its step (nothing moved, local scale):")
    for r in rows:
        if r["off_median_mm"] is not None:
            print(f"  {r['step']:5s} {r['still']} tray {r['tray']:2d} {r['off_median_mm']:6.1f} mm -> {r['label']}")
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
    for i, t in enumerate(sorted({r["tray"] for r in rows})):
        y0 = top + i * strip
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
                if is_off(r):
                    cv2.drawMarker(im, p, (0, 0, 200), cv2.MARKER_TRIANGLE_UP, 8, 1)
                elif r["label"] == MEASURED:
                    cv2.circle(im, p, 2, col, -1)
                else:
                    cv2.rectangle(im, (p[0] - 3, p[1] - 3), (p[0] + 3, p[1] + 3), col, 1)
    cv2.putText(im, f"blue east-west, orange north-south, {lo:.0f} to {hi:.0f} mm | dot measured, square patched, "
                "red triangle wrong, red cross no position | x: stills in time order", (left, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), im)
    print(f"\ntimeline: {out}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
