"""Script B: metrology log 16.9 Question 1 (trays only), written from the method text alone.

Reads a read-only copy of rig.db with SQL. Writes CSVs beside this file.
"""
import csv
import json
import math
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

AMS = ZoneInfo("Europe/Amsterdam")
MAX_GAP_S = 150.0
WIDEN = timedelta(minutes=15)
NO_START = timedelta(minutes=60)
BAD_WARNINGS = {"no tag", "tag seen, tray not found in the photo", "two tags in one tray outline"}
OUTSIDE = "partly outside the photo"
LEFT_OUT = (datetime(2026, 10, 28, 8, 47, 53, tzinfo=timezone.utc),
            datetime(2026, 10, 28, 8, 50, 2, tzinfo=timezone.utc))  # 08:47:53 to 08:50:01 inclusive
END = datetime(2026, 11, 9, 10, 40, 0, tzinfo=timezone.utc)
EXCLUSIONS = {"light changing", "lights off", "visit"}


def ts(s):
    return datetime.fromisoformat(s).astimezone(timezone.utc)


def chamber_day(t):
    return t.astimezone(AMS).date().isoformat()


def shuffle_windows(rows, shuffle0=False):
    """rows: dicts shuffle,date,start,finish in chamber time. Shuffle 0 has no window unless
    `shuffle0` (then like shuffle 1: 60 minutes before its finish)."""
    out = []
    for r in rows:
        if int(r["shuffle"]) == 0 and not shuffle0:
            continue
        fin = datetime.fromisoformat(f"{r['date']}T{r['finish']}").replace(tzinfo=AMS)
        if r["start"]:
            st = datetime.fromisoformat(f"{r['date']}T{r['start']}").replace(tzinfo=AMS)
        else:
            st = fin - NO_START
        out.append(((st - WIDEN).astimezone(timezone.utc), (fin + WIDEN).astimezone(timezone.utc)))
    return out


def photo_reasons(p1, p2, windows, events, app_starts, cam_events):
    """Photo-level reasons a pair is disturbed, in the order of the rules. [] when none.

    p: dict t (datetime), calibration, lens, flags (list), status, exclusion (str or None).
    """
    t1, t2 = p1["t"], p2["t"]
    r = []
    if any(a <= t2 and b >= t1 for a, b in windows):
        r.append("shuffle")
    if any(t1 <= e <= t2 for e in events):
        r.append("events log")
    if p1["calibration"] != p2["calibration"] or p1["lens"] != p2["lens"]:
        r.append("calibration or lens differs")
    if p1["flags"] or p2["flags"]:
        r.append("flag")
    if p1["status"] != "read" or p2["status"] != "read":
        r.append("not read")
    if (t2 - t1).total_seconds() > MAX_GAP_S:
        r.append("more than 150 s apart")
    if any(t1 < a <= t2 for a in app_starts):
        r.append("app start")
    if any(t1 <= e <= t2 for e in cam_events):
        r.append("camera event")
    if p1["exclusion"] in EXCLUSIONS or p2["exclusion"] in EXCLUSIONS:
        r.append("exclusion")
    if any(LEFT_OUT[0] <= p["t"] < LEFT_OUT[1] for p in (p1, p2)):
        r.append("left out (17.12)")
    return r


def tray_reasons(r1, r2):
    """Rule 8 for one tray. r: list of reading dicts for the tray in that photo (placement, slot,
    warnings list, area). Returns (reasons, partly_outside)."""
    if len(r1) == 0 or len(r2) == 0:
        return ["tray not read"], False
    if len(r1) > 1 or len(r2) > 1:
        return ["tray read twice in a photo"], False
    a, b = r1[0], r2[0]
    out = []
    if a["placement"] != "placed" or b["placement"] != "placed":
        out.append("placement not placed")
    if a["slot"] != b["slot"]:
        out.append("slot differs")
    if (set(a["warnings"]) | set(b["warnings"])) & BAD_WARNINGS:
        out.append("warning")
    if a["area"] is None or b["area"] is None:
        out.append("no area")
    return out, OUTSIDE in a["warnings"] or OUTSIDE in b["warnings"]


def pct_change(a1, a2):
    m = (a1 + a2) / 2
    return None if m == 0 else (a2 - a1) / m * 100


def stats(values):
    """median (signed), median of size, p95 of size (linear), RMS, largest by size (signed)."""
    v = np.asarray(values, dtype=float)
    if v.size == 0:
        return dict(n=0, median=None, median_abs=None, p95_abs=None, rms=None, largest=None)
    a = np.abs(v)
    return dict(n=int(v.size), median=float(np.median(v)), median_abs=float(np.median(a)),
                p95_abs=float(np.percentile(a, 95)), rms=float(math.sqrt(np.mean(v * v))),
                largest=float(v[int(np.argmax(a))]))


def growth_per_minute(day_points):
    """day_points: {day: [(t, area)]}. For each day with a following calendar day: change of the
    median areas over the minutes between the median times. Returns {day: (mm2/min, %/min)}."""
    out = {}
    days = sorted(day_points)
    for d in days:
        nxt = (datetime.fromisoformat(d) + timedelta(days=1)).date().isoformat()
        if nxt not in day_points:
            continue
        def med(pts):
            ts_ = sorted(p[0].timestamp() for p in pts)
            return float(np.median([p[1] for p in pts])), float(np.median(ts_))
        a1, t1 = med(day_points[d])
        a2, t2 = med(day_points[nxt])
        g = (a2 - a1) / ((t2 - t1) / 60)
        out[d] = (g, None if a1 == 0 else g / a1 * 100)
    return out


V2 = True  # coordinator's second run: shuffle 0 window, tray 8 from 09:34:53 UTC
TRAY8_FROM = datetime(2026, 10, 22, 9, 34, 53, tzinfo=timezone.utc)
LAYOUT = "/home/pi/scratch/331/cal/prod/validations/slot-layouts/20261022T072523939958.json"
SLOT_DISAGREE = []


def nearest_slot(x, y, slots):
    """Name of the slot whose centre is nearest (x, y), in photo pixels. The column `slot` is NULL
    in nearly every reading since #331, so the slot is taken from the calibration's slot layout."""
    return min(slots, key=lambda s: math.hypot(s["centre"][0] - x, s["centre"][1] - y))["name"]


def load(db):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    photos = []
    for cid, t, cal, lens, flags, status, excl in c.execute(
            "SELECT c.id, c.taken_at, c.calibration, c.lens_position, c.flags, tr.status, e.name "
            "FROM capture c LEFT JOIN tray_read tr ON tr.capture_id = c.id "
            "LEFT JOIN exclusion e ON e.capture_id = c.id "
            "WHERE c.experiment_id = 18 AND c.purpose = 'capture' ORDER BY c.taken_at"):
        t = ts(t)
        if t >= END:
            continue
        photos.append(dict(id=cid, t=t, calibration=cal, lens=lens, flags=json.loads(flags),
                           status=status, exclusion=excl))
    reads = defaultdict(lambda: defaultdict(list))
    slots = json.loads(Path(LAYOUT).read_text())["slots"]
    for cid, tray, stored, x, y, pl, warn, area in c.execute(
            "SELECT r.capture_id, r.tray_id, r.slot, r.centre_x_px, r.centre_y_px, r.placement, "
            "r.warnings, r.area_mm2 "
            "FROM tray_reading r JOIN capture c ON c.id = r.capture_id "
            "WHERE c.experiment_id = 18 AND r.tray_id IS NOT NULL"):
        slot = nearest_slot(x, y, slots)
        if stored is not None and stored != slot:
            SLOT_DISAGREE.append((cid, tray, stored, slot))
        reads[cid][tray].append(dict(slot=slot, placement=pl,
                                     warnings=json.loads(warn) if warn else [], area=area))
    app_starts = [ts(s) for (s,) in c.execute("SELECT started_at FROM app_start")]
    cam = [ts(s) for (s,) in c.execute("SELECT time_utc FROM camera_events")]
    return photos, reads, app_starts, cam


def main(db, shuffle_csv, events_csv, out):
    out = Path(out)
    photos, reads, app_starts, cam = load(db)
    with open(shuffle_csv) as f:
        windows = shuffle_windows(list(csv.DictReader(f)), shuffle0=V2)
    with open(events_csv) as f:
        events = [ts(r["time_utc"]) for r in csv.DictReader(f)]
    print("stored slot differs from nearest:", len(SLOT_DISAGREE), SLOT_DISAGREE[:5])
    trays = range(1, 13)
    counts = {k: defaultdict(int) for k in trays}
    pairs = []  # (tray, day, slot, t1, t2, a1, a2, outside)
    for p1, p2 in zip(photos, photos[1:]):
        pr = photo_reasons(p1, p2, windows, events, app_starts, cam)
        for k in trays:
            c = counts[k]
            c["pairs"] += 1
            tr, outside = tray_reasons(reads[p1["id"]][k], reads[p2["id"]][k])
            if V2 and k == 8 and p1["t"] < TRAY8_FROM:
                tr = tr + ["tray 8 before 09:34:53"]
            allr = pr + tr
            if allr:
                c["first: " + allr[0]] += 1
                for x in allr:
                    c["any: " + x] += 1
                continue
            c["undisturbed"] += 1
            if outside:
                c["undisturbed, partly outside"] += 1
            a = reads[p1["id"]][k][0]
            b = reads[p2["id"]][k][0]
            pairs.append((k, chamber_day(p1["t"]), a["slot"], p1, p2, a["area"], b["area"], outside))

    with open(out / "pairs_all.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tray", "before_id", "after_id", "before_mm2", "after_mm2", "change_pct",
                    "partly_outside"])
        for k, d, s_, p1, p2, a1, a2, o in pairs:
            pc = pct_change(a1, a2)
            w.writerow([k, p1["id"], p2["id"], a1, a2, "" if pc is None else pc, int(o)])
    keys = sorted({x for c in counts.values() for x in c} - {"pairs", "undisturbed"})
    with open(out / "q1_pair_counts.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tray", "pairs", "undisturbed"] + keys)
        for k in trays:
            w.writerow([k, counts[k]["pairs"], counts[k]["undisturbed"]] + [counts[k][x] for x in keys])

    def fmt(x, nd=4):
        return "" if x is None else round(x, nd)

    statcols = ["n", "median", "median_abs", "p95_abs", "rms", "largest"]
    # Tray 8: per day and slot.
    g = defaultdict(list)
    photos_g = defaultdict(dict)
    for k, d, s, p1, p2, a1, a2, o in pairs:
        if k != 8:
            continue
        g[(d, s)].append(pct_change(a1, a2))
        photos_g[(d, s)][p1["id"]] = a1
        photos_g[(d, s)][p2["id"]] = a2
    with open(out / "q1_tray8_day_slot.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["chamber_day", "slot"] + ["pct_" + c for c in statcols]
                   + ["n_photos", "mean_area_mm2", "sd_area_mm2"])
        for key in sorted(g):
            st = stats([v for v in g[key] if v is not None])
            ar = np.array(list(photos_g[key].values()))
            w.writerow(list(key) + [fmt(st[c]) for c in statcols]
                       + [ar.size, round(float(ar.mean()), 2),
                          round(float(ar.std(ddof=1)), 2) if ar.size > 1 else ""])
    # Trays 1 to 7: per tray and day.
    g = defaultdict(list)
    zero = defaultdict(int)
    pts = defaultdict(lambda: defaultdict(dict))
    for k, d, s, p1, p2, a1, a2, o in pairs:
        if not 1 <= k <= 7:
            continue
        v = pct_change(a1, a2)
        if v is None:
            zero[(k, d)] += 1
        else:
            g[(k, d)].append(v)
        pts[k][chamber_day(p1["t"])][p1["id"]] = (p1["t"], a1)
        pts[k][chamber_day(p2["t"])][p2["id"]] = (p2["t"], a2)
    with open(out / "q1_trays1to7_day.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tray", "chamber_day"] + ["pct_" + c for c in statcols]
                   + ["pairs_zero_mean", "median_area_mm2", "growth_mm2_per_min",
                      "growth_pct_per_min"])
        for k in range(1, 8):
            gr = growth_per_minute({d: list(v.values()) for d, v in pts[k].items()})
            for d in sorted({dd for (kk, dd) in list(g) + list(zero) if kk == k}):
                st = stats(g[(k, d)])
                med = float(np.median([a for _, a in pts[k][d].values()]))
                gm, gp = gr.get(d, (None, None))
                w.writerow([k, d] + [fmt(st[c]) for c in statcols]
                           + [zero[(k, d)], round(med, 2), fmt(gm, 6), fmt(gp, 6)])
    # Trays 9 to 12: mm2, per tray (whole run) and per tray and day.
    g = defaultdict(list)
    for k, d, s, p1, p2, a1, a2, o in pairs:
        if k >= 9:
            g[(k, "all")].append(a2 - a1)
            g[(k, d)].append(a2 - a1)
    with open(out / "q1_trays9to12_mm2.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tray", "chamber_day"] + ["mm2_" + c for c in statcols])
        for key in sorted(g, key=lambda x: (x[0], x[1] != "all", x[1])):
            st = stats(g[key])
            w.writerow(list(key) + [fmt(st[c]) for c in statcols])
    # Whole-run summary per tray, percent (1 to 8) and mm2 (all).
    g = defaultdict(list)
    for k, d, s, p1, p2, a1, a2, o in pairs:
        g[k].append((pct_change(a1, a2), a2 - a1))
    with open(out / "q1_summary_per_tray.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tray"] + ["pct_" + c for c in statcols] + ["mm2_" + c for c in statcols])
        for k in trays:
            sp = stats([p for p, _ in g[k] if p is not None])
            sm = stats([m for _, m in g[k]])
            w.writerow([k] + [fmt(sp[c]) for c in statcols] + [fmt(sm[c]) for c in statcols])


if __name__ == "__main__":
    main(*sys.argv[1:5])
