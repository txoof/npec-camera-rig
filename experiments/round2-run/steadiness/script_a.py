"""Metrology log 16.9, questions 1 (trays only) and 2, script A. Reads a read-only copy of
production rig.db; writes CSVs beside this file. Uses analysis.pairs(), analysis.window() and
analysis.detection() from experiments/round2-run unchanged.

Departures from 16.9 (see the report):
- Rule 5 app uptime: the photos' sidecar files are not on the controller. Uptime is worked out
  from the app_start table (app_up_s = photo time minus the last app start before it).
  app_start rows exist only from 2 Nov 16:19:27 UTC (#344); before that no restart is known and
  the pair is kept (column uptime_known = False). The strict reading ("app uptime unknown")
  is reported as a second set of tables, "strict", from the first app_start row on.
- Rule 8 slot: tray_reading.slot is NULL since the 2 Nov re-read; the slot is the nearest slot
  of the calibration's slot layout to the stored tray centre (tray_placement.nearest_slot), as 22.1.
- Tray 8 pairs whose earlier photo is before 22 Oct 09:34:53 UTC (benchmark put on, 16.5) are left out.
- Shuffle windows: blank start = 60 min before finish for shuffles 0 and 1 (as movements.py).
"""
import csv, json, math, sqlite3, statistics, sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROUND2 = Path(__file__).resolve().parents[1]  # experiments/round2-run
sys.path.insert(0, str(ROUND2))
import analysis  # noqa: E402
from npec_rig.tray_placement import nearest_slot  # noqa: E402

OUT = Path.home() / "scratch/223-area-jumps/a"  # outputs, not kept in the repository
DB = Path.home() / "scratch/223-shuffle-check/prod2/rig.db"
RECORD = ROUND2 / "sessions/shuffle-record-2026-10-22.csv"
SLOTS = json.loads((Path.home() / "scratch/331/cal/prod/validations/slot-layouts/20261022T072523939958.json").read_text())["slots"]
EXP = 18
UTC = timezone.utc
END = datetime(2026, 11, 9, 10, 40, tzinfo=UTC)  # photos after 10:40 UTC not used
DUP = (datetime(2026, 10, 28, 8, 47, 53, tzinfo=UTC), datetime(2026, 10, 28, 8, 50, 2, tzinfo=UTC))  # rule 9
NO_START, PAD = timedelta(minutes=60), timedelta(minutes=15)
BAD_WARN = {"no tag", "tag seen, tray not found in the photo", "two tags in one tray outline"}
BENCH_FROM = datetime(2026, 10, 22, 9, 34, 53, tzinfo=UTC)  # 16.5, 17.2
BENCH, PLANTS, EMPTY = 8, range(1, 8), range(9, 13)
ROUND2_END = "2026-11-05"


def T(s):
    return datetime.fromisoformat(s)


def chamber_utc(date, clock):
    return datetime.fromisoformat(f"{date}T{clock}").replace(tzinfo=analysis.CHAMBER).astimezone(UTC)


def shuffle_windows():
    out = []
    for r in csv.DictReader(RECORD.open()):
        fin = chamber_utc(r["date"], r["finish"])
        st = chamber_utc(r["date"], r["start"]) if r["start"] else fin - NO_START
        out.append((int(r["shuffle"]), st - PAD, fin + PAD))
    return out


def load():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    starts = sorted(T(r[0]) for r in c.execute("SELECT started_at FROM app_start"))
    excl = {r[0]: r[1] for r in c.execute("SELECT capture_id, name FROM exclusion")}
    photos = []
    for r in c.execute("SELECT c.*, r.status FROM capture c LEFT JOIN tray_read r ON r.capture_id=c.id"
                       " WHERE c.experiment_id=? AND c.purpose='capture' ORDER BY c.taken_at", (EXP,)):
        t = T(r["taken_at"])
        if t >= END:
            continue
        before = [s for s in starts if s <= t]
        photos.append({"capture_id": r["id"], "path": r["path"], "taken_at": t, "status": r["status"] or "not read",
                       "calibration": r["calibration"], "lens_position": r["lens_position"],
                       "flags": json.loads(r["flags"] or "[]"),
                       "app_up_s": (t - before[-1]).total_seconds() if before else 10**9,
                       "uptime_known": bool(before), "exclusion": excl.get(r["id"])})
    reads = defaultdict(lambda: defaultdict(list))
    for r in c.execute("SELECT t.capture_id, t.tray_id, t.placement, t.centre_x_px, t.centre_y_px, t.area_mm2,"
                       " t.warnings FROM tray_reading t JOIN capture c ON c.id=t.capture_id"
                       " WHERE c.experiment_id=? AND t.tray_id IS NOT NULL", (EXP,)):
        reads[r[0]][r[1]].append({"placement": r[2], "slot": nearest_slot(r[3], r[4], SLOTS)[0], "area": r[5],
                                  "warnings": set(json.loads(r[6] or "[]"))})
    events = [T(r[0]) for r in c.execute(
        "SELECT time_utc FROM camera_events WHERE COALESCE(detail,'') NOT LIKE '%synthetic camera%'")]
    return photos, reads, events, starts


def tray_ok(rs):
    """Rule 8 for one photo: (reading or None, reason)."""
    if not rs:
        return None, "tray not read"
    if len(rs) > 1:
        return None, "tag on two trays"
    r = rs[0]
    if r["placement"] != "placed":
        return None, "placement not placed"
    bad = r["warnings"] & BAD_WARN
    if bad:
        return None, "warning " + sorted(bad)[0]
    if r["area"] is None:
        return None, "no area"
    return r, None


def pct(xs, q):
    o = sorted(xs)
    return o[min(len(o) - 1, max(0, math.ceil(q * len(o)) - 1))]


def stats(changes):
    a = [abs(x) for x in changes]
    return {"pairs": len(a), "median_abs": round(statistics.median(a), 3), "p95_abs": round(pct(a, 0.95), 3),
            "rms": round(math.sqrt(sum(x * x for x in changes) / len(changes)), 3), "largest_abs": round(max(a), 3)}


def write(name, rows):
    rows = list(rows)
    with (OUT / name).open("w", newline="") as f:
        if not rows:
            return
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    photos, reads, events, starts = load()
    by_id = {p["capture_id"]: p for p in photos}
    shuf = shuffle_windows()
    breaks = [(s, e) for _, s, e in shuf] + [DUP]
    pairs = analysis.pairs(photos, breaks, events)
    # Relabel: which break; then rule 6 (exclusion) and the strict uptime reading.
    counts = Counter()
    good = []
    for pr in pairs:
        a, b = by_id[pr["before"]], by_id[pr["after"]]
        reason = pr["reason"]
        if reason == "shuffle or event":
            hit = [n for n, s, e in shuf if s <= b["taken_at"] and e > a["taken_at"]]
            reason = f"shuffle window (rule 7)" if hit else "28 Oct duplicate-tag photos (rule 9)"
        if reason is None and (a["exclusion"] or b["exclusion"]):
            reason = "exclusion: " + " / ".join(sorted({x for x in (a["exclusion"], b["exclusion"]) if x}))
        counts[reason or "undisturbed"] += 1
        if reason is None:
            good.append((a, b))
    strict_unknown = sum(1 for a, b in good if not b["uptime_known"])
    write("pair_reasons.csv", [{"reason": k, "pairs": v} for k, v in counts.most_common()]
          + [{"reason": "of the undisturbed: later photo before first app_start row (strict rule 5: app uptime unknown)",
              "pairs": strict_unknown}])

    # Per tray changes.
    tray_reason = Counter()
    rows = []  # one per tray per undisturbed pair
    for a, b in good:
        day, win = analysis.window(b["taken_at"])
        for tray in range(1, 13):
            ra, why_a = tray_ok(reads[a["capture_id"]].get(tray))
            rb, why_b = tray_ok(reads[b["capture_id"]].get(tray))
            why = why_a or why_b
            if not why and ra["slot"] != rb["slot"]:
                why = "slot changed"
            if not why and tray == BENCH and a["taken_at"] < BENCH_FROM:
                why = "tray 8 before the benchmark was put on (16.5)"
            if why:
                tray_reason[(tray, why)] += 1
                continue
            outside = "partly outside the photo" in (ra["warnings"] | rb["warnings"])
            tray_reason[(tray, "used, partly outside the photo" if outside else "used")] += 1
            mean = (ra["area"] + rb["area"]) / 2
            rows.append({"tray": tray, "day": day, "window": win, "slot": rb["slot"],
                         "before_id": a["capture_id"], "after_id": b["capture_id"],
                         "before_utc": a["taken_at"].isoformat(), "after_utc": b["taken_at"].isoformat(),
                         "before_path": a["path"], "after_path": b["path"],
                         "before_mm2": round(ra["area"], 2), "after_mm2": round(rb["area"], 2),
                         "change_mm2": round(rb["area"] - ra["area"], 3),
                         "change_pct": round(100 * (rb["area"] - ra["area"]) / mean, 4) if mean > 0 else None,
                         "partly_outside": outside, "uptime_known": b["uptime_known"]})
    write("tray_pair_reasons.csv", [{"tray": t, "reason": r, "pairs": n} for (t, r), n in sorted(tray_reason.items())])
    write("tray_pairs_all.csv", rows)

    def grouped(sel, keyf, field="change_pct"):
        g = defaultdict(list)
        for r in rows:
            if sel(r) and r[field] is not None:
                g[keyf(r)].append(r)
        return g

    def area_sd(rs):
        # Mean and SD over the distinct photos of the group's pairs (each photo's area once).
        seen = {}
        for r in rs:
            seen[r["before_id"]] = r["before_mm2"]
            seen[r["after_id"]] = r["after_mm2"]
        v = list(seen.values())
        return {"photos": len(v), "mean_mm2": round(statistics.fmean(v), 1), "sd_mm2": round(statistics.pstdev(v), 1),
                "sd_pct": round(100 * statistics.pstdev(v) / statistics.fmean(v), 2) if statistics.fmean(v) else None}

    for tag, sel0 in (("", lambda r: True), ("strict_", lambda r: r["uptime_known"])):
        # Tray 8.
        out = []
        for (d, slot), rs in sorted(grouped(lambda r: sel0(r) and r["tray"] == BENCH, lambda r: (r["day"], r["slot"])).items()):
            out.append({"day": d, "slot": slot, **stats([r["change_pct"] for r in rs]), **area_sd(rs)})
        write(f"{tag}tray8_day_slot.csv", out)
        out = []
        for slot, rs in sorted(grouped(lambda r: sel0(r) and r["tray"] == BENCH, lambda r: r["slot"]).items()):
            out.append({"slot": slot, **stats([r["change_pct"] for r in rs]), **area_sd(rs)})
        write(f"{tag}tray8_slot.csv", out)
        out = []
        for w, rs in sorted(grouped(lambda r: sel0(r) and r["tray"] == BENCH, lambda r: r["window"]).items()):
            out.append({"window": w, **stats([r["change_pct"] for r in rs])})
        allb = [r for r in rows if sel0(r) and r["tray"] == BENCH]
        out.append({"window": "all", **stats([r["change_pct"] for r in allb])})
        write(f"{tag}tray8_overall.csv", out)

        # Trays 1 to 7 per tray and day, with growth per minute to the next day.
        out = []
        for tray in PLANTS:
            g = grouped(lambda r: sel0(r) and r["tray"] == tray, lambda r: r["day"])
            days = sorted(g)
            med = {}
            for d in days:
                ph = {}
                for r in g[d]:
                    ph[r["before_id"]] = (T(r["before_utc"]), r["before_mm2"])
                    ph[r["after_id"]] = (T(r["after_utc"]), r["after_mm2"])
                ts = sorted(t for t, _ in ph.values())
                med[d] = (statistics.median(a for _, a in ph.values()), ts[len(ts) // 2])
            for i, d in enumerate(days):
                s = stats([r["change_pct"] for r in g[d]])
                gpm = gpct = None
                if i + 1 < len(days):
                    (a0, t0), (a1, t1) = med[d], med[days[i + 1]]
                    mins = (t1 - t0).total_seconds() / 60
                    gpm = (a1 - a0) / mins
                    gpct = 100 * gpm / a0 if a0 else None
                out.append({"tray": tray, "day": d, **s, "median_area_mm2": round(med[d][0], 1),
                            "next_day": days[i + 1] if i + 1 < len(days) else "",
                            "growth_mm2_per_min": round(gpm, 4) if gpm is not None else None,
                            "growth_pct_per_min": round(gpct, 5) if gpct is not None else None,
                            "rms_over_growth": round(s["rms"] / abs(gpct), 1) if gpct else None})
        write(f"{tag}plants_tray_day.csv", out)
        out = []
        for (tray, w), rs in sorted(grouped(lambda r: sel0(r) and r["tray"] in PLANTS, lambda r: (r["tray"], r["window"])).items()):
            out.append({"tray": tray, "window": w, **stats([r["change_pct"] for r in rs])})
        for tray in PLANTS:
            rs = [r for r in rows if sel0(r) and r["tray"] == tray and r["change_pct"] is not None]
            out.append({"tray": tray, "window": "all", **stats([r["change_pct"] for r in rs])})
        write(f"{tag}plants_tray_window.csv", out)

        # Trays 9 to 12, mm2.
        out = []
        for (tray, d), rs in sorted(grouped(lambda r: sel0(r) and r["tray"] in EMPTY, lambda r: (r["tray"], r["day"]), "change_mm2").items()):
            out.append({"tray": tray, "day": d, **{k.replace("abs", "abs_mm2").replace("rms", "rms_mm2"): v
                        for k, v in stats([r["change_mm2"] for r in rs]).items()},
                        "median_area_mm2": round(statistics.median(r["after_mm2"] for r in rs), 1)})
        for tray in EMPTY:
            rs = [r for r in rows if sel0(r) and r["tray"] == tray]
            out.append({"tray": tray, "day": "all", **{k.replace("abs", "abs_mm2").replace("rms", "rms_mm2"): v
                        for k, v in stats([r["change_mm2"] for r in rs]).items()},
                        "median_area_mm2": round(statistics.median(r["after_mm2"] for r in rs), 1)})
        write(f"{tag}empty_tray_day_mm2.csv", out)

    # 20 largest percent changes.
    cols = ["tray", "day", "window", "slot", "before_id", "after_id", "before_utc", "after_utc", "before_path",
            "after_path", "before_mm2", "after_mm2", "change_mm2", "change_pct", "partly_outside"]
    for name, sel in (("largest20_tray8.csv", lambda r: r["tray"] == BENCH),
                      ("largest20_trays1-7.csv", lambda r: r["tray"] in PLANTS)):
        rs = sorted((r for r in rows if sel(r) and r["change_pct"] is not None), key=lambda r: -abs(r["change_pct"]))[:20]
        write(name, [{k: r[k] for k in cols} for r in rs])

    # Question 2: tags found, lit photos (no 'lights off' exclusion).
    lit = [p for p in photos if p["exclusion"] != "lights off"]
    found = {cid: set(t) for cid, t in reads.items()}
    det = analysis.detection(lit, found, list(range(1, 13)))
    for tag, sel in (("to_5nov", lambda d: d <= ROUND2_END), ("6_to_9nov", lambda d: d > ROUND2_END)):
        write(f"tags_found_{tag}.csv", [r | {"share": round(r["share"], 4)} for r in det["trays"] if sel(r["day"])])
        write(f"tags_not_read_{tag}.csv", [r for r in det["not read"] if sel(r["day"])])
        write(f"tags_misses_{tag}.csv", [{"capture_id": m["capture_id"], "taken_at": m["taken_at"].isoformat(),
                                          "missing": " ".join(map(str, m["missing"]))}
                                         for m in det["misses"] if sel(analysis.window(m["taken_at"])[0])])
        # Summary per tray and window over the period.
        agg = defaultdict(lambda: [0, 0])
        for r in det["trays"]:
            if sel(r["day"]):
                agg[(r["tray"], r["window"])][0] += r["photos"]
                agg[(r["tray"], r["window"])][1] += r["found"]
        write(f"tags_found_summary_{tag}.csv", [{"tray": t, "window": w, "photos": n, "found": f, "share": round(f / n, 4)}
                                                for (t, w), (n, f) in sorted(agg.items())])
    excl_counts = Counter(p["exclusion"] or "none" for p in photos)
    status_lit = Counter(p["status"] for p in lit)
    print("photos", len(photos), "excl", dict(excl_counts), "lit statuses", dict(status_lit))
    print("pairs", len(pairs), dict(counts), "strict unknown", strict_unknown)
    print("shuffle windows", [(n, s.isoformat(), e.isoformat()) for n, s, e in shuf])


if __name__ == "__main__":
    main()
