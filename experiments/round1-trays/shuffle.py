"""Round 1 (issue #213): trays placed from their cell tag only, checked against shuffle maps (15.5i).

Method: docs/metrology-log.md section 15.5i, written before the photos. Every still of one
experiment is read in time order and split into rounds wherever two stills are more than --gap
seconds apart (round 0 the starting layout, then the rounds of the plan). In each still every
tray is placed from its tag alone: tray centre = tag centre + the tray type's offset, turned by the
tag heading; slot = nearest slot centre of the calibration's slot layout to that centre; A1 corner
from the heading. Each round's trays are compared with the plan. No FastSAM.

    cd experiments/round1-trays
    PYTHONPATH=<worktree>/src <venv python> shuffle.py --experiment "simple segmentation test"

Stills and rig.db are read only. Tag detections are cached in ~/scratch/round1-trays/shuffle/tags/;
writes shuffle-<folder>.csv here and one picture per round to ~/scratch/round1-trays/shuffle/.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

import trays
from footprint import from_tag

PLAN = trays.SESSIONS / "shuffle-2026-10-19.json"
OUT = trays.SCRATCH / "shuffle"

# Where the tag sits on each tray type, so other types can place their tags elsewhere. The offset
# is from the tag centre to the tray centre in the tag's own frame (right, up), mm; sw_heading_deg
# is the tag heading when A1 is at the south-west corner (tray turned 0).
TRAY_TYPES = {
    # 30 mm tag flat in the empty cell A1, the same way round on every tray: the median offset of
    # 12 trays in 15.5h (step 1, 19 October; within 18 mm on every tray), headings about 180 when
    # A1 is SW and about 0 when NE (same stills).
    "4x5 tag in A1": {"offset_mm": (-107.8, -149.1), "sw_heading_deg": 180.0,
                      "size_mm": (trays.TRAY_EW_MM, trays.TRAY_NS_MM)},
    # 40 mm tag lying any way round, roughly centred in cell A1: the median of 12 trays' medians
    # over the 6 layout 1 stills of 20 October (15.5l, learn_offset.py; within 9.6 mm on every tray),
    # in the A1-at-SW frame turned by the tilt only, as place_any_rotation uses it.
    "4x5 40 mm tag in A1": {"offset_mm": (-104.0, -141.6), "sw_heading_deg": 180.0,
                            "size_mm": (trays.TRAY_EW_MM, trays.TRAY_NS_MM)},
}
TRAY_TYPE = "4x5 tag in A1"
TRAY_TAGS = range(1, 13)


def corner(heading_deg: float, sw_heading_deg: float) -> str:
    """SW if the heading is within 90 degrees of the type's SW heading, else NE (turned 180)."""
    d = (heading_deg - sw_heading_deg + 180) % 360 - 180
    return "SW" if abs(d) < 90 else "NE"


def tilt(heading_deg: float) -> float:
    """The tray's turn off the image axes, taking the tag to lie square in its cell."""
    return (heading_deg + 45) % 90 - 45


def place_any_rotation(cx: float, cy: float, heading_deg: float, ppm: float, slots: list[dict],
                       tt: dict) -> dict:
    """Tray centre, slot and A1 corner from the tag centre alone, the tag lying any way round (15.5j).

    Two candidates, A1 at SW and A1 at NE, each turned by the tilt only; the one whose nearest slot
    centre is closer is taken. Distances in mm at the tag's scale."""
    v = from_tag(np.array(tt["offset_mm"]), tt["sw_heading_deg"] + tilt(heading_deg)) * ppm
    out = {}
    for a1, c in (("SW", np.array([cx, cy]) + v), ("NE", np.array([cx, cy]) - v)):
        slot, d, _, _ = trays.nearest_slots(c[0], c[1], slots)
        out[a1] = {"centre": c, "slot": slot, "d_mm": d / ppm}
    a1 = min(out, key=lambda k: out[k]["d_mm"])
    return {"a1": a1, "slot": out[a1]["slot"], "centre": out[a1]["centre"],
            "d_sw_mm": out["SW"]["d_mm"], "d_ne_mm": out["NE"]["d_mm"],
            "turned_deg": round((heading_deg - tt["sw_heading_deg"] - (180 if a1 == "NE" else 0)) / 90) * 90 % 360}


def rounds_by_gap(stills: list[dict], gap_s: float) -> list[list[dict]]:
    """Stills in time order, split wherever two are more than gap_s apart."""
    out: list[list[dict]] = []
    for s in stills:
        if out and s["t"] - out[-1][-1]["t"] <= gap_s:
            out[-1].append(s)
        else:
            out.append([s])
    return out


def experiment_folder(name: str, url: str) -> str:
    with urllib.request.urlopen(f"{url}/api/experiments", timeout=30) as r:
        found = [e for e in json.load(r) if e["name"] == name]
    if len(found) != 1:
        raise SystemExit(f"{len(found)} experiments named {name!r}")
    return found[0]["folder"]


def stills_of(folder: str) -> list[dict]:
    from datetime import datetime

    db = sqlite3.connect(f"file:{trays.RIG / 'rig.db'}?mode=ro", uri=True)
    rows = db.execute("select path, taken_at, calibration, lens_position from capture where path like ? "
                      "order by taken_at", (f"experiments/{folder}/stills/%",)).fetchall()
    db.close()
    return [{"path": trays.RIG / f"{p}.jpg", "still": Path(p).name, "taken_at": t,
             "t": datetime.fromisoformat(t).timestamp(), "calibration": c, "lens": lens}
            for p, t, c, lens in rows]


def detect(s: dict) -> list[dict]:
    from npec_rig.tags import detect_tags

    cache = OUT / "tags" / f"{s['still']}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    img = cv2.imread(str(s["path"]))
    out = []
    for d in detect_tags(img[:, :, ::-1]):
        c = np.asarray(d.corners, dtype=float)
        out.append({"id": int(d.tag_id), "cx": float(c[:, 0].mean()), "cy": float(c[:, 1].mean()),
                    "heading_deg": round(trays.tag_heading_deg(c), 1)})
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out))
    return out


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--experiment", required=True, help="name of the experiment holding the stills")
    ap.add_argument("--gap", type=float, default=60.0, help="seconds between stills that start a new round")
    ap.add_argument("--rounds", type=int, nargs="*",
                    help="plan round of each group of stills in time order (0: no plan); default 0, 1, 2, ...")
    ap.add_argument("--after", default="", help="only stills taken at or after this UTC time (ISO), e.g. 2026-10-19T12:18")
    ap.add_argument("--before", default="", help="only stills taken before this UTC time (ISO)")
    ap.add_argument("--name", default="", help="output name: shuffle-<folder>-<name>.csv (default: -any with --any-rotation)")
    ap.add_argument("--any-rotation", action="store_true",
                    help="15.5j: turn from the slot grid, not the tag heading")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    args = ap.parse_args(argv)
    from npec_rig.calibration_store import load_calibration
    from npec_rig.validation_store import load_slot_layout

    plan = {r["round"]: r for r in json.loads(PLAN.read_text())["rounds"]}
    tt = TRAY_TYPES[TRAY_TYPE]
    folder = experiment_folder(args.experiment, args.url)
    stills = [s for s in stills_of(folder)
              if (not args.after or s["taken_at"] >= args.after) and (not args.before or s["taken_at"] < args.before)]
    suffix = f"-{args.name}" if args.name else ("-any" if args.any_rotation else "")
    groups = rounds_by_gap(stills, args.gap)
    print(f"{args.experiment} ({folder}): {len(stills)} stills in {len(groups)} rounds (gap {args.gap:g} s)")
    names = args.rounds if args.rounds is not None else list(range(len(groups)))
    if len(names) != len(groups):
        raise SystemExit(f"--rounds names {len(names)} groups, the stills make {len(groups)}")
    for n, g in zip(names, groups):
        print(f"  group: round {n}, {len(g)} stills, {g[0]['still']} to {g[-1]['still']}")

    cal = {}
    rows, per_round = [], defaultdict(Counter)
    OUT.mkdir(parents=True, exist_ok=True)
    for gi, (k, g) in enumerate(zip(names, groups)):
        expect = {v["tray"]: (slot, v["a1"]) for slot, v in plan[k]["slots"].items()} if k in plan else {}
        for i, s in enumerate(g):
            stem = s["calibration"]
            if stem not in cal:
                cal[stem] = (load_calibration(trays.RIG / "calibration" / f"{stem}.json").scale_field,
                             load_slot_layout(stem)["slots"])
            sf, slots = cal[stem]
            tags = detect(s)
            ids = Counter(t["id"] for t in tags)
            img = cv2.imread(str(s["path"])) if i == 0 else None
            for t in sorted((t for t in tags if t["id"] in TRAY_TAGS), key=lambda t: t["id"]):
                ppm = sf.px_per_mm(t["cx"], t["cy"])
                extra = {}
                if args.any_rotation:
                    p = place_any_rotation(t["cx"], t["cy"], t["heading_deg"], ppm, slots, tt)
                    c, slot, a1 = p["centre"], p["slot"], p["a1"]
                    extra = {"d_sw_mm": round(p["d_sw_mm"], 1), "d_ne_mm": round(p["d_ne_mm"], 1),
                             "tag_turned_deg": p["turned_deg"]}
                else:
                    c = np.array([t["cx"], t["cy"]]) + from_tag(np.array(tt["offset_mm"]), t["heading_deg"]) * ppm
                    slot = trays.nearest_slots(c[0], c[1], slots)[0]
                    a1 = corner(t["heading_deg"], tt["sw_heading_deg"])
                want = expect.get(t["id"])
                ok = want == (slot, a1) if want else None
                rows.append({"group": gi, "round": k, "still": s["still"], "taken_at_utc": s["taken_at"], "lens": s["lens"],
                             "tray": t["id"], "copies": ids[t["id"]], "x_px": round(c[0]), "y_px": round(c[1]),
                             "heading_deg": t["heading_deg"], "slot": slot, "a1": a1,
                             "planned_slot": want[0] if want else "", "planned_a1": want[1] if want else "",
                             "right": ok, **extra})
                if want:
                    per_round[gi]["right" if ok else "wrong"] += 1
                if img is not None:
                    box = cv2.boxPoints(((c[0], c[1]), (tt["size_mm"][0] * ppm, tt["size_mm"][1] * ppm), tilt(t["heading_deg"])))
                    colour = (0, 200, 0) if ok in (True, None) else (0, 0, 255)
                    cv2.polylines(img, [box.astype(np.int32)], True, colour, 14)
                    text = f"tray {t['id']} {slot} {a1}" + ("" if ok in (True, None) else f" PLAN {want[0]} {want[1]}")
                    cv2.putText(img, text, (int(c[0]) - 650, int(c[1])), cv2.FONT_HERSHEY_SIMPLEX, 3.5, colour, 10)
            found = {t["id"] for t in tags if t["id"] in TRAY_TAGS}
            missing = [n for n in TRAY_TAGS if n not in found]
            twice = sorted(n for n in found if ids[n] > 1)
            per_round[gi]["missing"] += len(missing)
            if missing or twice:
                print(f"  {s['still']}: missing {missing}, found twice {twice}")
            if img is not None:
                cv2.imwrite(str(OUT / f"group{gi}-round{k}-{s['still']}{suffix}.jpg"), cv2.resize(img, None, fx=0.25, fy=0.25))
    trays.write_csv(trays.HERE / f"shuffle-{folder}{suffix}.csv", rows)

    print("\ngroup round  stills  trays in planned slot and corner  wrong  tags missing")
    for gi, (k, g) in enumerate(zip(names, groups)):
        c = per_round[gi]
        if k in plan:
            print(f"  {gi}    {k}     {len(g):3d}     {c['right']:3d} of {12 * len(g):3d}                    {c['wrong']:3d}    {c['missing']:3d}")
        else:
            print(f"  {gi}    {k}     {len(g):3d}     (no plan: starting layout)              {c['missing']:3d}")
    wrong = [r for r in rows if r["right"] is False]
    for r in wrong:
        print(f"  wrong: group {r['group']} round {r['round']} {r['still']} tray {r['tray']}: found {r['slot']} {r['a1']}, "
              f"planned {r['planned_slot']} {r['planned_a1']}")
    print(f"\npictures in {OUT}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
