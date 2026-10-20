"""Round 2 (issue #236): trays placed from 40 mm cell tags through a day of shuffles (15.5l).

Method: docs/metrology-log.md section 15.5l, written before the photos, with the decisions of 20
October. Every still of the experiment is read in time order. Layouts are found from the stills:
a run of stills that are not settled is a move, matched to Aaron's nearest leave time
(shuffle-times-2026-10-20.csv). A still is settled when every tag found in it and in the next
still lies within 5 mm of its position there (tags missing from either are not compared). In
every settled still each tray is placed by the 15.5j rule with the 40 mm offset, not refitted, and
compared with the shuffle map. Layout 1 is the learning layout and is left out of the counts.

    cd experiments/round1-trays
    PYTHONPATH=<worktree>/src <venv python> shuffle_day.py --experiment "tray tracking 26.10.20" --until 2026-10-20T11:01

Stills and rig.db are read only. Writes shuffle-day-<folder>.csv here; pictures of the first
settled still of each layout and crops of every missing tag to ~/scratch/round2-shuffles/.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

import cv2
import numpy as np

import trays
from shuffle import TRAY_TAGS, TRAY_TYPES, detect, experiment_folder, place_any_rotation, stills_of, tilt

MAPS = trays.SESSIONS / "shuffle-maps-2026-10-20.json"
TIMES = trays.HERE / "shuffle-times-2026-10-20.csv"
TRAY_TYPE = "4x5 40 mm tag in A1"
SETTLED_MM = 5.0  # 15.5l rule 2, a decision
MATCH_S = 180  # a move ends within this of a leave time (a decision, 20 October)
OUT = trays.SCRATCH.parent / "round2-shuffles"


def leave_times(path, day: str) -> list[dict]:
    with open(path) as f:
        rows = list(csv.DictReader(line for line in f if not line.startswith("#")))
    return [{"shuffle": r["shuffle"], "round": int(re.match(r"\d+", r["shuffle"]).group()), "gaps": r["gaps"],
             "status": r["status"],
             "t": datetime.fromisoformat(f"{day}T{r['left_chamber_utc']}:00+00:00").timestamp()} for r in rows]


def assign_layouts(stills: list[dict], shuffles: list[dict]) -> None:
    """Layouts from the stills: each run of stills that are not settled is a move, matched to the
    leave time nearest its end (within MATCH_S); the stills after it, to the next matched move,
    belong to that shuffle's layout. A run with no leave time near it (a person in the chamber,
    nothing moved) starts no layout. Prints each move against Aaron's leave time."""
    runs, cur = [], []
    for i, s in enumerate(stills):
        if not s["settled"]:
            cur.append(i)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    starts = {0: shuffles[0]["shuffle"]} if stills else {}
    print("moves found in the stills, against Aaron's leave times:")
    for run in runs:
        first_after = run[-1] + 1
        if first_after >= len(stills):
            continue
        t_end = stills[first_after]["t"]
        sh = min(shuffles, key=lambda sh: abs(sh["t"] - t_end))
        dt = t_end - sh["t"]
        ok = abs(dt) <= MATCH_S
        print(f"  {stills[run[0]]['still']} to {stills[run[-1]]['still']} ({len(run)} not settled): "
              + (f"shuffle {sh['shuffle']}, first settled still {dt:+.0f} s from his leave time" if ok
                 else f"no leave time within {MATCH_S} s (nearest shuffle {sh['shuffle']}, {dt:+.0f} s): no new layout"))
        if ok:
            starts[first_after] = sh["shuffle"]
    lay = ""
    for i, s in enumerate(stills):
        lay = starts.get(i, lay)
        s["layout"] = lay


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--experiment", required=True)
    ap.add_argument("--until", default="", help="only stills before this UTC time (ISO); default all")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    args = ap.parse_args(argv)
    from npec_rig.calibration_store import load_calibration
    from npec_rig.validation_store import load_slot_layout

    maps = json.loads(MAPS.read_text())
    plan = {r["round"]: {v["tray"]: (slot, v["a1"]) for slot, v in r["slots"].items()} for r in maps["rounds"]}
    shuffles = leave_times(TIMES, maps["date"])
    tt = TRAY_TYPES[TRAY_TYPE]
    folder = experiment_folder(args.experiment, args.url)
    stills = stills_of(folder)
    for s in [s for s in stills if not s["path"].exists()]:
        print(f"  {s['still']}: capture record with no image file, left out")
    stills = [s for s in stills if s["path"].exists()]
    if args.until:
        end = datetime.fromisoformat(args.until).replace(tzinfo=timezone.utc).timestamp()
        stills = [s for s in stills if s["t"] < end]
    cal = {}
    for i, s in enumerate(stills):
        if s["calibration"] is None:  # a still outside the schedule may carry none: the one before it
            s["calibration"] = stills[i - 1]["calibration"]
            print(f"  {s['still']}: no calibration recorded, {s['calibration']} used")
        if s["calibration"] not in cal:
            cal[s["calibration"]] = (load_calibration(trays.RIG / "calibration" / f"{s['calibration']}.json").scale_field,
                                     load_slot_layout(s["calibration"])["slots"])
        s["tags"] = {t["id"]: t for t in detect(s) if t["id"] in TRAY_TAGS}
        s["copies"] = Counter(t["id"] for t in detect(s))
    for s, nxt in zip(stills, stills[1:] + [None]):
        sf = cal[s["calibration"]][0]
        common = set(s["tags"]) & set(nxt["tags"]) if nxt else set()
        moved = [np.hypot(s["tags"][i]["cx"] - nxt["tags"][i]["cx"], s["tags"][i]["cy"] - nxt["tags"][i]["cy"])
                 / sf.px_per_mm(s["tags"][i]["cx"], s["tags"][i]["cy"]) for i in common]
        s["max_move_mm"] = max(moved) if moved else None
        s["settled"] = bool(moved) and max(moved) <= SETTLED_MM
    assign_layouts(stills, shuffles)
    rnd = {sh["shuffle"]: sh["round"] for sh in shuffles}
    status = {sh["shuffle"]: sh["status"] for sh in shuffles}  # "learning" and "not as planned" are counted apart
    order = [sh["shuffle"] for sh in shuffles]

    rows, centres = [], defaultdict(list)
    OUT.mkdir(parents=True, exist_ok=True)
    pictured = set()
    for k, s in enumerate(stills):
        sf, slots = cal[s["calibration"]]
        want = plan.get(rnd[s["layout"]], {})
        img = None
        if s["settled"] and s["layout"] not in pictured:
            img = cv2.imread(str(s["path"]))
            pictured.add(s["layout"])
        for n in TRAY_TAGS:
            t = s["tags"].get(n)
            row = {"still": s["still"], "taken_at_utc": s["taken_at"], "layout": s["layout"],
                   "settled": s["settled"], "max_move_mm": None if s["max_move_mm"] is None else round(s["max_move_mm"], 1),
                   "tray": n, "found": t is not None, "copies": s["copies"][n],
                   "planned_slot": want.get(n, ("", ""))[0], "planned_a1": want.get(n, ("", ""))[1]}
            if t is not None:
                ppm = sf.px_per_mm(t["cx"], t["cy"])
                p = place_any_rotation(t["cx"], t["cy"], t["heading_deg"], ppm, slots, tt)
                d_near, d_far = sorted((p["d_sw_mm"], p["d_ne_mm"]))
                row.update({"x_px": round(p["centre"][0]), "y_px": round(p["centre"][1]), "slot": p["slot"],
                            "a1": p["a1"], "d_slot_mm": round(d_near, 1), "margin_mm": round(d_far - d_near, 1),
                            "right": (p["slot"], p["a1"]) == want.get(n)})
                if s["settled"]:
                    centres[(s["layout"], n)].append(p["centre"] / ppm)
                if img is not None:
                    box = cv2.boxPoints(((p["centre"][0], p["centre"][1]),
                                         (tt["size_mm"][0] * ppm, tt["size_mm"][1] * ppm), tilt(t["heading_deg"])))
                    colour = (0, 200, 0) if row["right"] else (0, 0, 255)
                    cv2.polylines(img, [box.astype(np.int32)], True, colour, 14)
                    text = f"tray {n} {p['slot']} {p['a1']}" + ("" if row["right"] else f" PLAN {' '.join(want.get(n, ('?', '?')))}")
                    cv2.putText(img, text, (int(p["centre"][0]) - 650, int(p["centre"][1])), cv2.FONT_HERSHEY_SIMPLEX, 3.5, colour, 10)
            elif s["settled"]:
                # where the tag should be: the nearest still in time that found it
                near = min((o for o in stills if n in o["tags"] and o["layout"] == s["layout"]),
                           key=lambda o: abs(o["t"] - s["t"]), default=None)
                if near is not None:
                    cx, cy = int(near["tags"][n]["cx"]), int(near["tags"][n]["cy"])
                    full = cv2.imread(str(s["path"]))
                    crop = full[max(cy - 600, 0):cy + 600, max(cx - 600, 0):cx + 600]
                    cv2.imwrite(str(OUT / f"missing-{s['still']}-tag{n}.jpg"), cv2.resize(crop, None, fx=0.5, fy=0.5))
            rows.append(row)
        if img is not None:
            cv2.imwrite(str(OUT / f"layout{s['layout']:0>3}-{s['still']}.jpg"), cv2.resize(img, None, fx=0.25, fy=0.25))
    trays.write_csv(trays.HERE / f"shuffle-day-{folder}.csv", rows)

    gaps = {sh["shuffle"]: sh["gaps"] for sh in shuffles}
    print(f"{args.experiment} ({folder}): {len(stills)} stills, {stills[0]['still']} to {stills[-1]['still']}")
    print("\nlayout  gaps      stills  settled  right  wrong  not found  min margin mm  max d_slot mm")
    total = defaultdict(Counter)
    for lay in [x for x in order if any(s["layout"] == x for s in stills)]:
        rs = [r for r in rows if r["layout"] == lay and r["settled"]]
        c = Counter("right" if r.get("right") else "not found" if not r["found"] else "wrong" for r in rs)
        found = [r for r in rs if r["found"]]
        n_st = len({r["still"] for r in rows if r["layout"] == lay})
        n_set = len({r["still"] for r in rs})
        mm = min((r["margin_mm"] for r in found), default=float("nan"))
        md = max((r["d_slot_mm"] for r in found), default=float("nan"))
        tag = f" ({status[lay]})" if status[lay] else ""
        print(f"  {lay:>3}    {gaps.get(lay, ''):9s} {n_st:4d}   {n_set:4d}    {c['right']:4d}  {c['wrong']:4d}  {c['not found']:6d}"
              f"      {mm:7.1f}       {md:7.1f}{tag}")
        if not status[lay]:
            total[gaps.get(lay, "")].update(c)
            total["all"].update(c)
    for g, c in total.items():
        n = sum(c.values())
        print(f"  total {g:9s}: right {c['right']} of {n} ({100 * c['right'] / n:.1f}%), wrong {c['wrong']}, not found {c['not found']}")
    for r in rows:
        if r["settled"] and r["found"] and not r["right"] and not status[r["layout"]]:
            print(f"  wrong: layout {r['layout']} {r['still']} tray {r['tray']}: {r['slot']} {r['a1']}, "
                  f"planned {r['planned_slot']} {r['planned_a1']}")
    twice = sorted({(r["still"], r["tray"]) for r in rows if r["copies"] > 1})
    if twice:
        print(f"  found more than once: {twice}")

    print("\nsteadiness of each placed centre over settled stills, mm (layouts after the learning one)")
    spread = []
    for (lay, n), cs in sorted(centres.items()):
        if status[lay] or len(cs) < 2:
            continue
        d = np.linalg.norm(np.array(cs) - np.mean(cs, axis=0), axis=1)
        spread.append((lay, n, float(np.sqrt(np.mean(d ** 2))), float(d.max()), len(cs)))
    if spread:
        rms = np.array([s[2] for s in spread])
        mx = max(spread, key=lambda s: s[3])
        print(f"  {len(spread)} tray-layouts: rms median {np.median(rms):.2f}, max {rms.max():.2f}; "
              f"largest single {mx[3]:.2f} (layout {mx[0]} tray {mx[1]}, {mx[4]} stills)")
    print(f"\nmoving stills (not settled), by layout:")
    for lay in [x for x in order if any(s["layout"] == x for s in stills)]:
        mv = [s["still"] for s in stills if s["layout"] == lay and not s["settled"]]
        print(f"  {lay:>3}: {len(mv)} {' '.join(mv)}")
    print(f"\npictures and missing-tag crops in {OUT}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
