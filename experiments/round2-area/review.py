"""Plant area per tray on the potato run, the review of metrology log 17.2, from a COPY of rig.db.
Nothing is written into rig.db, the experiment folder or the masks folder.

    python review.py COPY_OF_RIG_DB --experiment 18 --out OUT_DIR

Writes OUT_DIR/review.html (tables and charts) and one CSV per table, and prints the tables.
Undisturbed pairs, lit and dark, and movement windows as metrology log 16.3, with the run's own
code (`experiments/round2-run/analysis.py`).
"""

import argparse
import csv
import json
import math
import sqlite3
import statistics
import sys
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "round2-run"))
import analysis  # noqa: E402

BENCHMARK_FROM = datetime(2026, 10, 22, 9, 34, 53, tzinfo=timezone.utc)  # 16.5
# The benchmark was put on between these photos (16.5): pairs across them are disturbed.
BENCHMARK_BREAK = (datetime(2026, 10, 22, 9, 33, 0, tzinfo=timezone.utc), datetime(2026, 10, 22, 9, 34, 0, tzinfo=timezone.utc))
BENCHMARK_TRAY = 8
EMPTY_TRAYS = (9, 10, 11, 12)  # black pots only (16.1)
PLANT_TRAYS = (1, 2, 3, 4, 5, 6, 7)
# Categorical order of the dataviz reference palette, one colour per plant tray, in tray order.
COLOURS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6"]


def utc(text):
    return datetime.fromisoformat(text)


def load(db, experiment_id):
    """(photos, readings by capture id, camera event times) from the copy. `app_up_s` from each
    photo's sidecar file, read only."""
    from npec_rig.captures import experiments_root

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    photos = []
    for row in conn.execute(
        "SELECT c.*, r.status FROM capture c LEFT JOIN tray_read r ON r.capture_id = c.id"
        " WHERE c.experiment_id = ? AND c.purpose = 'capture' ORDER BY c.taken_at",
        (experiment_id,),
    ):
        sidecar = experiments_root() / (row["path"].removeprefix("experiments/") + ".json")
        app_up_s = json.loads(sidecar.read_text()).get("uptime", {}).get("app_up_s") if sidecar.exists() else None
        photos.append({
            "capture_id": row["id"], "path": row["path"], "taken_at": utc(row["taken_at"]),
            "status": row["status"] or "not read", "calibration": row["calibration"],
            "lens_position": row["lens_position"], "flags": json.loads(row["flags"] or "[]"), "app_up_s": app_up_s,
        })
    readings = {}
    for row in conn.execute(
        "SELECT t.* FROM tray_reading t JOIN capture c ON c.id = t.capture_id WHERE c.experiment_id = ?",
        (experiment_id,),
    ):
        readings.setdefault(row["capture_id"], {})[row["tray_id"]] = dict(row)
    camera_events = [utc(r[0]) for r in conn.execute(
        "SELECT time_utc FROM camera_events WHERE COALESCE(detail, '') NOT LIKE '%synthetic camera%'")]
    conn.close()
    return photos, readings, camera_events


def lit(photo):
    return photo["status"] == "read"


def day(photo):
    return analysis.window(photo["taken_at"])[0]


def pct(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))]


# --- Questions ------------------------------------------------------------------------------------


def failures(photos, readings):
    """Question 1: photos per chamber day by status, and lit photos with a tray placed but no area."""
    rows = {}
    no_area = []
    for p in photos:
        r = rows.setdefault(day(p), {"day": day(p), "photos": 0, "lit (read)": 0, "dark (no tags found)": 0,
                                    "read failed": 0, "other status": 0, "trays placed": 0, "trays with no area": 0})
        r["photos"] += 1
        key = {"read": "lit (read)", "no tags found": "dark (no tags found)", "read failed": "read failed"}.get(p["status"], "other status")
        r[key] += 1
        for tray in readings.get(p["capture_id"], {}).values():
            r["trays placed"] += 1
            if tray["area_mm2"] is None:
                r["trays with no area"] += 1
                no_area.append({"taken_at": p["taken_at"].isoformat(), "tray": tray["tray_id"]})
    others = sorted({p["status"] for p in photos} - {"read", "no tags found", "read failed"})
    return list(rows.values()), no_area, others


def benchmark(photos, readings, camera_events, breaks):
    """Question 2: tray 8 from BENCHMARK_FROM. (pair changes, rows per lit period and slot)."""
    after = [p for p in photos if p["taken_at"] >= BENCHMARK_FROM]
    pairs = analysis.pairs(after, [BENCHMARK_BREAK, *breaks], camera_events)
    by_id = {p["capture_id"]: p for p in after}
    area_changes, px_changes, reasons = [], [], {}
    for pair in pairs:
        if pair["reason"]:
            reasons[pair["reason"]] = reasons.get(pair["reason"], 0) + 1
            continue
        a = readings.get(pair["before"], {}).get(BENCHMARK_TRAY)
        b = readings.get(pair["after"], {}).get(BENCHMARK_TRAY)
        if not a or not b or not a["area_mm2"] or b["area_mm2"] is None:
            reasons["tray 8 not found or no area"] = reasons.get("tray 8 not found or no area", 0) + 1
            continue
        area_changes.append(100 * (b["area_mm2"] - a["area_mm2"]) / a["area_mm2"])
        px_changes.append(100 * (b["plant_px"] - a["plant_px"]) / a["plant_px"])
    rms = lambda xs: math.sqrt(sum(x * x for x in xs) / len(xs)) if xs else float("nan")  # noqa: E731
    pair_row = {
        "undisturbed pairs used": len(area_changes),
        "area change RMS %": round(rms(area_changes), 3),
        "area change largest %": round(max(map(abs, area_changes), default=float("nan")), 3),
        # Added after the first run (2026-10-23): the RMS is set by a few pairs at lights on and off.
        "area change median of size %": round(statistics.median(map(abs, area_changes)), 3) if area_changes else None,
        "area change 95th pct of size %": round(pct([abs(x) for x in area_changes], 0.95), 3) if area_changes else None,
        "pixel change RMS %": round(rms(px_changes), 3),
        "pixel change largest %": round(max(map(abs, px_changes), default=float("nan")), 3),
    }
    periods = {}
    for p in after:
        t = readings.get(p["capture_id"], {}).get(BENCHMARK_TRAY)
        if lit(p) and t and t["area_mm2"] is not None and not any(s <= p["taken_at"] <= e for s, e in breaks):
            periods.setdefault((day(p), t["slot"]), []).append((t["area_mm2"], t["plant_px"]))
    period_rows = []
    for (d, slot), values in periods.items():
        areas = [v[0] for v in values]
        pxs = [v[1] for v in values]
        period_rows.append({
            "day (lit photos)": d, "slot": slot, "photos": len(values),
            "area mean mm2": round(statistics.fmean(areas), 1),
            "area SD mm2": round(statistics.pstdev(areas), 1),
            "area SD %": round(100 * statistics.pstdev(areas) / statistics.fmean(areas), 2),
            "area min": round(min(areas), 1), "area max": round(max(areas), 1),
            "pixels SD %": round(100 * statistics.pstdev(pxs) / statistics.fmean(pxs), 2),
        })
    return pair_row, reasons, period_rows


def empty_trays(photos, readings):
    """Question 3: trays 9 to 12 in lit photos, per tray and day."""
    values = {}
    for p in photos:
        if not lit(p):
            continue
        for tray_id in EMPTY_TRAYS:
            t = readings.get(p["capture_id"], {}).get(tray_id)
            if t and t["area_mm2"] is not None:
                values.setdefault((tray_id, day(p)), []).append(t["area_mm2"])
    rows = []
    for (tray_id, d), areas in sorted(values.items()):
        rows.append({
            "tray": tray_id, "day": d, "photos": len(areas),
            "median mm2": round(statistics.median(areas), 1), "95th percentile mm2": round(pct(areas, 0.95), 1),
            "largest mm2": round(max(areas), 1), "share above 0 %": round(100 * sum(a > 0 for a in areas) / len(areas), 1),
        })
    every = [a for areas in values.values() for a in areas]
    return rows, (pct(every, 0.95) if every else None), (max(every) if every else None)


def series(photos, readings, trays, since=None):
    """{tray: [(time, area)]} over lit photos."""
    out = {t: [] for t in trays}
    for p in photos:
        if not lit(p) or (since and p["taken_at"] < since):
            continue
        for tray_id in trays:
            t = readings.get(p["capture_id"], {}).get(tray_id)
            if t and t["area_mm2"] is not None:
                out[tray_id].append((p["taken_at"], t["area_mm2"]))
    return out


def first_above(plant, largest_empty):
    """Question 4: per plant tray, the first lit period (chamber day) in which every area is above
    the empty trays' largest."""
    rows = []
    for tray_id, points in plant.items():
        by_day = {}
        for t, a in points:
            by_day.setdefault(analysis.window(t)[0], []).append(a)
        first = next((d for d, areas in sorted(by_day.items()) if min(areas) > largest_empty), None)
        rows.append({"tray": tray_id, "first lit day wholly above the empty trays' largest": first or "not yet",
                     "latest area mm2": round(points[-1][1], 1) if points else None})
    return rows


# --- Output ---------------------------------------------------------------------------------------


def write_csv(path, rows):
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def html_table(title, rows):
    if not rows:
        return f"<h3>{escape(title)}</h3><p>None.</p>"
    head = "".join(f"<th>{escape(str(k))}</th>" for k in rows[0])
    body = "".join("<tr>" + "".join(f"<td>{escape(str(v))}</td>" for v in r.values()) + "</tr>" for r in rows)
    return f"<h3>{escape(title)}</h3><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def svg_chart(title, lines, *, x_of, x_label, y_label, ref=None, width=960, height=360):
    """A line or dot chart: `lines` is [(name, colour, [(x, y)], dots)]; `ref` an optional
    (value, label) horizontal line. x values are numbers (`x_of` turns them into axis text)."""
    pad_l, pad_r, pad_t, pad_b = 70, 150, 30, 50
    xs = [x for _, _, pts, _ in lines for x, _ in pts]
    ys = [y for _, _, pts, _ in lines for _, y in pts] + ([ref[0]] if ref else []) + [0]
    if not xs:
        return f"<h3>{escape(title)}</h3><p>No data.</p>"
    x0, x1 = min(xs), max(xs) or 1
    y1 = max(ys) * 1.05 or 1
    sx = lambda x: pad_l + (x - x0) / ((x1 - x0) or 1) * (width - pad_l - pad_r)  # noqa: E731
    sy = lambda y: height - pad_b - y / y1 * (height - pad_t - pad_b)  # noqa: E731
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">']
    for i in range(6):  # grid and y ticks
        y = y1 * i / 5
        parts.append(f'<line x1="{pad_l}" x2="{width - pad_r}" y1="{sy(y):.1f}" y2="{sy(y):.1f}" class="grid"/>')
        parts.append(f'<text x="{pad_l - 6}" y="{sy(y) + 4:.1f}" text-anchor="end" class="tick">{y:,.0f}</text>')
    for i in range(6):  # x ticks
        x = x0 + (x1 - x0) * i / 5
        parts.append(f'<text x="{sx(x):.1f}" y="{height - pad_b + 18}" text-anchor="middle" class="tick">{escape(x_of(x))}</text>')
    parts.append(f'<text x="{(pad_l + width - pad_r) / 2}" y="{height - 8}" text-anchor="middle" class="axis">{escape(x_label)}</text>')
    parts.append(f'<text x="14" y="{pad_t - 10}" class="axis">{escape(y_label)}</text>')
    if ref:
        parts.append(f'<line x1="{pad_l}" x2="{width - pad_r}" y1="{sy(ref[0]):.1f}" y2="{sy(ref[0]):.1f}" class="ref"/>')
        parts.append(f'<text x="{width - pad_r + 6}" y="{sy(ref[0]) + 4:.1f}" class="tick">{escape(ref[1])}</text>')
    for n, (name, colour, pts, dots) in enumerate(lines):
        if dots:
            parts += [f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="1.5" fill="{colour}"><title>{escape(name)}: {y:,.0f}</title></circle>' for x, y in pts]
        else:
            path = " ".join(f"{'M' if i == 0 else 'L'}{sx(x):.1f},{sy(y):.1f}" for i, (x, y) in enumerate(pts))
            parts.append(f'<path d="{path}" fill="none" stroke="{colour}" stroke-width="2"/>')
        parts.append(f'<rect x="{width - pad_r + 6}" y="{pad_t + 18 * n}" width="10" height="10" fill="{colour}"/>'
                     f'<text x="{width - pad_r + 22}" y="{pad_t + 18 * n + 9}" class="tick">{escape(name)}</text>')
    parts.append("</svg>")
    return f"<h3>{escape(title)}</h3>" + "".join(parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("db", type=Path)
    ap.add_argument("--experiment", type=int, default=18)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--break", dest="breaks", nargs=2, action="append", default=[], metavar=("START", "END"),
                    help="UTC times of a shuffle or event: pairs across it are disturbed, photos in it left out of question 2")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    photos, readings, camera_events = load(a.db, a.experiment)
    q1, no_area, others = failures(photos, readings)
    breaks = [(utc(s), utc(e)) for s, e in a.breaks]
    pair_row, reasons, q2 = benchmark(photos, readings, camera_events, breaks)
    q3, p95_empty, largest_empty = empty_trays(photos, readings)
    plant = series(photos, readings, PLANT_TRAYS)
    q4 = first_above(plant, largest_empty) if largest_empty is not None else []
    tables = {
        "q1-failures": q1, "q1-no-area": no_area, "q2-benchmark-pairs": [pair_row],
        "q2-benchmark-pairs-left-out": [{"reason": k, "pairs": v} for k, v in sorted(reasons.items())],
        "q2-benchmark-per-day": q2, "q3-empty-trays": q3, "q4-plant-trays": q4,
    }
    for name, rows in tables.items():
        write_csv(a.out / f"{name}.csv", rows)
        print(f"\n{name}")
        for r in rows[:40]:
            print("  ", r)
    print("\nother statuses:", others, "| empty trays 95th percentile:", p95_empty, "largest:", largest_empty)

    start = min(p["taken_at"] for p in photos)
    hours = lambda t: (t - start).total_seconds() / 3600  # noqa: E731
    at = lambda h: (start + timedelta(hours=h)).astimezone(analysis.CHAMBER).strftime("%d %b %H:%M")  # noqa: E731
    bench = series(photos, readings, [BENCHMARK_TRAY], since=BENCHMARK_FROM)[BENCHMARK_TRAY]
    empty = series(photos, readings, EMPTY_TRAYS)
    tod = lambda t: (lambda l: l.hour + l.minute / 60)(t.astimezone(analysis.CHAMBER))  # noqa: E731
    charts = [
        svg_chart("Question 2. Benchmark (tray 8), lit photos", [("tray 8", "#2a78d6", [(hours(t), y) for t, y in bench], True)],
                  x_of=at, x_label="chamber time", y_label="plant area, mm²"),
        svg_chart("Question 3. Empty trays (black pots), lit photos",
                  [(f"tray {k}", COLOURS[i], [(hours(t), y) for t, y in v], True) for i, (k, v) in enumerate(empty.items())],
                  x_of=at, x_label="chamber time", y_label="plant area, mm²"),
        svg_chart("Question 4. Plant trays, lit photos",
                  [(f"tray {k}", COLOURS[i], [(hours(t), y) for t, y in v], True) for i, (k, v) in enumerate(plant.items())],
                  x_of=at, x_label="chamber time", y_label="plant area, mm²",
                  ref=(p95_empty, "empty trays, 95th pct") if p95_empty is not None else None),
        svg_chart("Question 5. Trays 8 to 12 by time of day, lit photos",
                  [(f"tray {k}", COLOURS[i], [(tod(t), y) for t, y in v], True)
                   for i, (k, v) in enumerate({BENCHMARK_TRAY: bench, **empty}.items())],
                  x_of=lambda h: f"{int(h):02d}:{int(h % 1 * 60):02d}", x_label="chamber time of day", y_label="plant area, mm²"),
    ]
    html = ["<!doctype html><meta charset='utf-8'><title>Potato area review</title><style>",
            "body{font-family:system-ui,sans-serif;margin:16px;max-width:1000px;color:#1a1a19;background:#fff}",
            "table{border-collapse:collapse;margin:8px 0 24px;font-size:13px}td,th{border-bottom:1px solid #ddd;padding:3px 8px;text-align:right}",
            "th:first-child,td:first-child{text-align:left}svg{width:100%;height:auto}.grid{stroke:#e6e5e0}.ref{stroke:#e34948;stroke-dasharray:4 3}",
            ".tick{font-size:11px;fill:#55554f}.axis{font-size:12px;fill:#1a1a19}</style>",
            f"<h1>Plant area per tray, potato run (metrology log 17.2)</h1><p>{len(photos)} photos, "
            f"{start.isoformat()} to {max(p['taken_at'] for p in photos).isoformat()} UTC. Development check.</p>"]
    html += [html_table(name, rows) for name, rows in tables.items()]
    html += charts
    (a.out / "review.html").write_text("".join(html))
    print("\nwrote", a.out / "review.html")


if __name__ == "__main__":
    main()
