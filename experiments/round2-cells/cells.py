"""Plant area per cell over the Round 2 run, against the photo-to-photo change (#394, metrology log 38).

    python cells.py SLIM_DB RESTART_PAIRS_JSON OUT_DIR

SLIM_DB: the copy made by extract.py. RESTART_PAIRS_JSON: 16.9's list of photo pairs across an app
restart before 2 Nov 16:19 UTC, from the photos' sidecars (`../round2-run/steadiness/restarts.py`).
Writes CSV tables and the per-tray charts into OUT_DIR. Reads only; writes only OUT_DIR.

Steps are numbered as in the method (log 38, "What is worked out").
"""
import collections
import csv
import json
import math
import sqlite3
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "round2-run"))
import analysis  # noqa: E402  (the 16.3 pair rules)



def nearest_slot(x, y, slots):
    """As `npec_rig.tray_placement.nearest_slot` (the same rule, written here so the script runs
    without OpenCV): the slot whose centre is nearest (x, y), and its distance in pixels."""
    return min(((s["name"], math.hypot(s["centre"][0] - x, s["centre"][1] - y)) for s in slots),
               key=lambda s: s[1])


RECORD = HERE.parent / "round2-run" / "sessions" / "shuffle-record-2026-10-22.csv"
UTC = timezone.utc
CHAMBER = analysis.CHAMBER
APP_START_FROM = datetime(2026, 11, 2, 16, 19, 0, tzinfo=UTC)
SKIP = (datetime(2026, 10, 28, 8, 47, 53, tzinfo=UTC), datetime(2026, 10, 28, 8, 50, 2, tzinfo=UTC))
TRAY7_UNTIL = datetime(2026, 11, 5, 11, 0, 0, tzinfo=UTC)
MATS = (datetime(2026, 11, 6, 8, 10, tzinfo=UTC), datetime(2026, 11, 6, 9, 19, tzinfo=UTC))
BAD_WARN = {"no tag", "tag seen, tray not found in the photo", "two tags in one tray outline"}
BANDS = [(0, 0.001), (0.001, 1), (1, 5), (5, 10), (10, 20), (20, 50), (50, 100), (100, 200),
         (200, 500), (500, 1000), (1000, 5000), (5000, 100000)]
RULES = {"fixed green cutoff": 0, "grow from leaf cores": 1}
TRAYS = range(1, 8)
# The slot layout of experiment 18's one calibration (20261022T072523939958), a copy from production
# (16.9). tray_reading.slot is NULL since the 2 Nov re-read, so the slot is the layout's nearest to
# the stored tray centre, as in 16.9 and 22.1.
SLOT_LAYOUT = Path.home() / "scratch/331/cal/prod/validations/slot-layouts/20261022T072523939958.json"
SLOTS = json.loads(SLOT_LAYOUT.read_text())["slots"]


def utc(text):
    return datetime.fromisoformat(text)


def shuffles():
    """16.9 rule 7: each shuffle from its start (60 min before its finish if not recorded) to its
    finish, widened by 15 minutes each side. Times in the record are chamber time."""
    out = []
    for r in csv.DictReader(open(RECORD)):
        fin = datetime.fromisoformat(f"{r['date']}T{r['finish']}").replace(tzinfo=CHAMBER).astimezone(UTC)
        st = (datetime.fromisoformat(f"{r['date']}T{r['start']}").replace(tzinfo=CHAMBER).astimezone(UTC)
              if r["start"] else fin - timedelta(minutes=60))
        out.append((st - timedelta(minutes=15), fin + timedelta(minutes=15)))
    return out


def band_of(m):
    for lo, hi in BANDS:
        if lo <= m < hi:
            return (lo, hi)
    return BANDS[-1]


def load(db_path, restart_pairs):
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    starts = [utc(r[0]) for r in db.execute("select started_at from app_start")]
    cam = [utc(r[0]) for r in db.execute(
        "select time_utc from camera_events where coalesce(detail,'') not like '%synthetic camera%'")]
    photos = []
    for r in db.execute("""select c.*, t.status, e.name excl from capture c
                           left join tray_read t on t.capture_id = c.id
                           left join exclusion e on e.capture_id = c.id order by c.taken_at"""):
        photos.append(dict(capture_id=r["id"], taken_at=utc(r["taken_at"]), status=r["status"] or "not read",
                           calibration=r["calibration"], lens_position=r["lens_position"],
                           flags=json.loads(r["flags"] or "[]"), excl=r["excl"]))
    trays = {}
    for r in db.execute("select * from tray_reading"):
        trays.setdefault((r["capture_id"], r["tray_id"]), []).append(dict(r))
    cells = collections.defaultdict(dict)
    for r in db.execute("""select capture_id, tray_id, cell, area_mm2, grown_area_mm2, over_other_cells,
                                  grown_over_other_cells from cell_reading where holds = 'plant'"""):
        cells[r[0]][(r[1], r[2])] = ((r[3], r[5]), (r[4], r[6]))
    restarted = {(int(a), int(b)) for a, b in restart_pairs}
    return photos, starts, cam, trays, cells, restarted


def photo_ok(p, breaks):
    """A single photo passes the 16.9 photo rules."""
    t = p["taken_at"]
    if p["status"] != "read" or p["excl"] or p["flags"]:
        return False
    if any(s <= t <= e for s, e in breaks) or SKIP[0] <= t <= SKIP[1]:
        return False
    return True


def tray_ok(rows):
    """One reading, placed, none of the bad warnings. Returns the slot or None."""
    if not rows or len(rows) != 1:
        return None
    r = rows[0]
    if r["placement"] != "placed" or set(json.loads(r["warnings"] or "[]")) & BAD_WARN:
        return None
    return nearest_slot(r["centre_x_px"], r["centre_y_px"], SLOTS)[0]


def tray_in_study(tray, t):
    return tray != 7 or t < TRAY7_UNTIL


def undisturbed_pairs(photos, starts, cam, restarted, breaks):
    """16.9 rules 1 to 9 for consecutive photos."""
    out = []
    for a, b in zip(photos, photos[1:]):
        gap = (b["taken_at"] - a["taken_at"]).total_seconds()
        if b["taken_at"] >= APP_START_FROM:
            up = 0 if any(a["taken_at"] < s <= b["taken_at"] for s in starts) else gap + 1
        else:
            up = 0 if (a["capture_id"], b["capture_id"]) in restarted else gap + 1
        reason = analysis._reason(a, dict(b, app_up_s=up), breaks, cam)
        if reason is None and (a["excl"] or b["excl"]):
            reason = "exclusion"
        if reason is None and any(SKIP[0] <= p["taken_at"] <= SKIP[1] for p in (a, b)):
            reason = "17.12 left out"
        if reason is None:
            out.append((a, b))
    return out


def summarise(changes):
    """changes: list of (mean, diff). By band: count, median |d|, 95th pct |d|, rms d."""
    by = collections.defaultdict(list)
    for m, d in changes:
        by[band_of(m)].append(d)
    rows = []
    for lo, hi in BANDS:
        ds = by.get((lo, hi))
        if not ds:
            continue
        ab = sorted(abs(d) for d in ds)
        rows.append(dict(band_lo=lo, band_hi=hi, n=len(ds), median_abs=statistics.median(ab),
                         p95_abs=ab[min(len(ab) - 1, int(0.95 * len(ab)))],
                         rms=(sum(d * d for d in ds) / len(ds)) ** 0.5))
    return rows


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main(db_path, restart_json, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    breaks = shuffles()
    photos, starts, cam, trays, cells, restarted = load(db_path, json.load(open(restart_json)))

    # 1. photo-to-photo change, undisturbed cell pairs
    pairs = undisturbed_pairs(photos, starts, cam, restarted, breaks)
    pair_changes = {rule: [] for rule in RULES}
    check_169 = []  # the 16.9 window, fixed green cutoff, to compare with 16.9's counts
    for a, b in pairs:
        ca, cb = cells.get(a["capture_id"], {}), cells.get(b["capture_id"], {})
        for tray in TRAYS:
            if not tray_in_study(tray, b["taken_at"]):
                continue
            sa, sb = tray_ok(trays.get((a["capture_id"], tray))), tray_ok(trays.get((b["capture_id"], tray)))
            if sa is None or sa != sb:
                continue
            for key in ca.keys() & cb.keys():
                if key[0] != tray:
                    continue
                for rule, i in RULES.items():
                    (va, oa), (vb, ob) = ca[key][i], cb[key][i]
                    if va is None or vb is None:
                        continue
                    pair_changes[rule].append(((va + vb) / 2, vb - va, bool(oa or ob)))
            if (datetime(2026, 11, 6, 12, 28, tzinfo=UTC) <= a["taken_at"]
                    and b["taken_at"] <= datetime(2026, 11, 9, 10, 40, 59, tzinfo=UTC)):
                for key in ca.keys() & cb.keys():
                    if key[0] == tray and ca[key][0][0] is not None and cb[key][0][0] is not None:
                        check_169.append(abs(cb[key][0][0] - ca[key][0][0]))
    noise = []
    for rule, ch in pair_changes.items():
        for row in summarise([(m, d) for m, d, over in ch if not over]):
            noise.append(dict(rule=rule, **row))
    write_csv(out / "photo_to_photo.csv", noise)
    print("undisturbed photo pairs", len(pairs))
    print("16.9 window check: cell pairs", len(check_169), "median |d|",
          round(statistics.median(check_169), 2) if check_169 else None)

    # 2. hourly median per cell and rule, from usable photos
    series = collections.defaultdict(list)  # (tray, cell) -> [(t, slot, (a, over), (g, over))]
    for p in photos:
        if not photo_ok(p, breaks):
            continue
        cs = cells.get(p["capture_id"], {})
        for tray in TRAYS:
            if not tray_in_study(tray, p["taken_at"]):
                continue
            slot = tray_ok(trays.get((p["capture_id"], tray)))
            if slot is None:
                continue
            for key, v in cs.items():
                if key[0] == tray:
                    series[key].append((p["taken_at"], slot) + v)
    hourly = []
    hour_of = {}
    for key, pts in sorted(series.items()):
        by_hour = collections.defaultdict(list)
        for t, slot, *vals in pts:
            by_hour[(t.replace(minute=0, second=0, microsecond=0), slot)].append(vals)
        for (h, slot), vs in sorted(by_hour.items()):
            row = dict(tray=key[0], cell=key[1], hour_utc=h.isoformat(), slot=slot, photos=len(vs))
            for rule, i in RULES.items():
                xs = [v[i][0] for v in vs if v[i][0] is not None]
                med = statistics.median(xs) if xs else None
                row[f"{rule} median"] = med
                row[f"{rule} mad"] = statistics.median(abs(x - med) for x in xs) if xs else None
                row[f"{rule} first"] = xs[0] if xs else None
                row[f"{rule} over other cells"] = sum(bool(v[i][1]) for v in vs)
            hourly.append(row)
            hour_of[(key, h)] = row
    write_csv(out / "hourly.csv", hourly)

    # 3. hour to hour: following hours, same slot, no shuffle between
    h2h = {rule: [] for rule in RULES}
    single = {rule: [] for rule in RULES}
    for (key, h), row in hour_of.items():
        nxt = hour_of.get((key, h + timedelta(hours=1)))
        if not nxt or nxt["slot"] != row["slot"]:
            continue
        if any(s < h + timedelta(hours=2) and e > h for s, e in breaks):
            continue
        for rule in RULES:
            a, b = row[f"{rule} median"], nxt[f"{rule} median"]
            if a is not None and b is not None:
                h2h[rule].append(((a + b) / 2, b - a))
            a, b = row[f"{rule} first"], nxt[f"{rule} first"]
            if a is not None and b is not None:
                single[rule].append(((a + b) / 2, b - a))
    rows = []
    for rule in RULES:
        for kind, src in (("hourly median", h2h), ("one photo per hour", single)):
            for r in summarise(src[rule]):
                rows.append(dict(rule=rule, kind=kind, **r))
    write_csv(out / "hour_to_hour.csv", rows)
    h2h_rms = {(r["rule"], (r["band_lo"], r["band_hi"])): r["rms"] for r in rows if r["kind"] == "hourly median"}

    # 4. day to day growth against the hour-to-hour change at that size
    daily = collections.defaultdict(lambda: collections.defaultdict(list))
    for row in hourly:
        day = datetime.fromisoformat(row["hour_utc"]).astimezone(CHAMBER).date()
        for rule in RULES:
            if row[f"{rule} median"] is not None:
                daily[(row["tray"], row["cell"], rule)][day].append(row[f"{rule} median"])
    growth = []
    for (tray, cell, rule), days in sorted(daily.items()):
        ds = sorted(days)
        for d0, d1 in zip(ds, ds[1:]):
            if (d1 - d0).days != 1:
                continue
            m0, m1 = statistics.median(days[d0]), statistics.median(days[d1])
            rms = h2h_rms.get((rule, band_of((m0 + m1) / 2)))
            growth.append(dict(tray=tray, cell=cell, rule=rule, day=d1.isoformat(), median_before=m0,
                               median_day=m1, hours_day=len(days[d1]), growth=m1 - m0,
                               hour_to_hour_rms=rms, ratio=(m1 - m0) / rms if rms else None))
    write_csv(out / "daily_growth.csv", growth)
    print("cells", len(series), "hourly rows", len(hourly), "daily rows", len(growth))
    json.dump(dict(breaks=[(s.isoformat(), e.isoformat()) for s, e in breaks],
                   mats=[t.isoformat() for t in MATS]), open(out / "events.json", "w"))


if __name__ == "__main__":
    main(*sys.argv[1:4])
