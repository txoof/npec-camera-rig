"""Round 2 ground truth for tray movements (#332, part A): where each tray was planned to be, where
the rig read it, and whether the two agree, per shuffle and per tray.

    PYTHONPATH="$(pwd)/src" python experiments/round2-run/movements.py \
        --db ~/scratch/332/prod/rig.db --experiment 18 \
        --calibration ~/scratch/331/cal/prod/20261022T072523939958.json \
        --slots ~/scratch/331/cal/prod/validations/slot-layouts/20261022T072523939958.json \
        --out ~/scratch/332/analysis

Run from the repository root. Needs numpy and matplotlib. The database is opened read-only and
must be a COPY of a rig's rig.db, never the live one.

Inputs:
- `sessions/shuffle-maps-2026-10-22.json`: the planned maps (tray and A1 corner per slot).
- `sessions/shuffle-record-2026-10-22.csv`: the collaborator's shuffle start and finish times,
  chamber time (Europe/Amsterdam). Shuffle k puts map k on the table.
- tray_reading in the database copy: each tray's slot, A1 corner and centre in every photo.
- the calibration the photos used: its four table (corner) tags, and its slot layout.

Areas (Aaron, 2026-10-30): a 3 x 2 grid, NW NM NE over SW SM SE. The grid is laid out in the
calibration's table frame (`calibration.build_table_frame`, a homography from the four table
tags' centres to a unit square, so lines of the grid are straight lines on the table):
- rows: north where v < 0.5, south where v >= 0.5, v = 0 being the northern row of table tags and
  v = 1 the southern row;
- columns: the full photo width, cut in thirds of u, where u runs from the photo's left edge to its
  right edge along the middle line v = 0.5.
A tray's centre decides its area. A planned slot's area is the area of that slot's centre in the
calibration's slot layout.

Rules:
- EXPECTED: map k holds from shuffle k's recorded finish until shuffle k+1's finish (map 0 from
  the experiment's start, since the start layout was already map 0, shuffle-record-README.md).
- MEASURED: per tray, the photos where its tag was read, in time order. A run is a spell of photos
  with one value (an area, or a slot and A1 corner). A run of under 1 hour between two others
  (first to last photo) is ignored, so misses (no photo of the tray) and short stays elsewhere do
  not end a stay. The first and last runs are always kept.
- COMPARISON, per shuffle k and tray: the measured slot stay that overlaps most of the time from
  finish k to the next shuffle's start (or the end of the data), against map k. "Change, min" is
  the stay's first photo minus the recorded finish: negative when the tray was in place before the
  collaborator wrote the finish time.
- OUTSIDE SHUFFLES: every raw run (any length) of a new slot, A1 corner or area that starts
  outside a shuffle window. A shuffle's window is its recorded start (or, with no start written,
  60 minutes before its finish) to its finish, widened by 15 minutes on each side.

All times are UTC inside the script; every output shows Amsterdam time (the clocks went back on
25 October).
"""

import argparse
import csv
import json
import sqlite3
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from npec_rig.calibration import build_table_frame, calibration_artifact_from_dict  # noqa: E402

from analysis import CHAMBER  # noqa: E402

HERE = Path(__file__).parent
MAPS = HERE / "sessions" / "shuffle-maps-2026-10-22.json"
RECORD = HERE / "sessions" / "shuffle-record-2026-10-22.csv"
PHOTO_WIDTH_PX = 9152  # full-size Arducam 64MP still, 9152 x 6944
AREAS = ("NW", "NM", "NE", "SW", "SM", "SE")
MIN_STAY = timedelta(hours=1)  # Aaron, 2026-10-30: counts as moved after 1 hour elsewhere
NO_START = timedelta(minutes=60)  # window before a finish when no start was written (a choice)
WINDOW_PAD = timedelta(minutes=15)  # added to each side of a shuffle window (a choice)
# Categorical slots 1 to 6 of the dataviz reference palette, one per area, always with the name.
AREA_FILL = dict(zip(AREAS, ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300")))
AREA_TEXT = {"NW": "white", "NM": "black", "NE": "black", "SW": "black", "SM": "black", "SE": "white"}


def ams(t):
    return t.astimezone(CHAMBER).strftime("%a %d %b %H:%M") if t else ""


def utc_from_chamber(date, clock):
    local = datetime.fromisoformat(f"{date}T{clock}").replace(tzinfo=CHAMBER)
    if local.utcoffset() != local.replace(fold=1).utcoffset():
        raise ValueError(f"{date} {clock} happened twice (the clocks went back)")
    return local.astimezone(UTC)


def load_shuffles(path):
    rows = list(csv.DictReader(path.open()))
    return [{"shuffle": int(r["shuffle"]),
             "start": utc_from_chamber(r["date"], r["start"]) if r["start"] else None,
             "finish": utc_from_chamber(r["date"], r["finish"])} for r in rows]


def area_finder(calibration_path, width=PHOTO_WIDTH_PX):
    """area(x, y) for photo pixels, from the calibration's table frame (see the docstring)."""
    artifact = calibration_artifact_from_dict(json.loads(Path(calibration_path).read_text()))
    frame = build_table_frame(artifact.corner_baseline)
    y_mid = frame.to_pixel(0.5, 0.5)[1]
    u_left, u_right = frame.to_fraction(0, y_mid)[0], frame.to_fraction(width, y_mid)[0]
    cuts = [u_left + (u_right - u_left) * k / 3 for k in (1, 2)]

    def area(x, y):
        u, v = frame.to_fraction(x, y)
        col = "W" if u < cuts[0] else "M" if u < cuts[1] else "E"
        return ("N" if v < 0.5 else "S") + col

    return area, {"u_cuts": cuts, "u_left": u_left, "u_right": u_right, "corners_px": frame.corners_px,
                  "frame": frame}


def load_readings(db, experiment):
    conn = sqlite3.connect(f"file:{Path(db).expanduser()}?mode=ro", uri=True)
    exp_start = conn.execute("SELECT MIN(taken_at) FROM capture WHERE experiment_id=?", (experiment,)).fetchone()[0]
    end = conn.execute("SELECT MAX(taken_at) FROM capture WHERE experiment_id=?", (experiment,)).fetchone()[0]
    rows = conn.execute(
        """SELECT c.taken_at, r.tray_id, r.slot, r.a1_corner, r.placement, r.centre_x_px, r.centre_y_px
           FROM tray_reading r JOIN capture c ON c.id = r.capture_id
           WHERE c.experiment_id = ? AND r.tray_id IS NOT NULL ORDER BY c.taken_at""", (experiment,)).fetchall()
    started = conn.execute("SELECT * FROM experiment WHERE id=?", (experiment,)).fetchone() \
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='experiment'").fetchone() else None
    conn.close()
    return rows, datetime.fromisoformat(exp_start), datetime.fromisoformat(end), started


def runs(seq):
    """[(t, key, extra)] in time order -> raw runs [{key, first, last, n, extras}]."""
    out = []
    for t, key, extra in seq:
        if out and out[-1]["key"] == key:
            out[-1]["last"] = t
            out[-1]["n"] += 1
            out[-1]["extras"][extra] += 1
        else:
            out.append({"key": key, "first": t, "last": t, "n": 1, "extras": Counter([extra])})
    return out


def stays(raw):
    """Raw runs -> stays: drop interior runs shorter than MIN_STAY (shortest first), merging the
    neighbours they separated when those have the same value."""
    s = [dict(r) for r in raw]
    while True:
        short = [i for i in range(1, len(s) - 1) if s[i]["last"] - s[i]["first"] < MIN_STAY]
        if not short:
            break
        i = min(short, key=lambda j: s[j]["last"] - s[j]["first"])
        del s[i]
        if s[i - 1]["key"] == s[i]["key"]:
            s[i - 1] = s[i - 1] | {"last": s[i]["last"], "n": s[i - 1]["n"] + s[i]["n"]}
            del s[i]
    return s


def expected(maps, shuffles, slot_area, exp_start, end):
    """{tray: [{map, from, to, slot, a1, area}]}"""
    out = {}
    done = [s for s in shuffles if s["shuffle"] < len(maps)]
    for n, sh in enumerate(done):
        frm = exp_start if sh["shuffle"] == 0 else sh["finish"]
        to = done[n + 1]["finish"] if n + 1 < len(done) else end
        for slot, v in maps[sh["shuffle"]]["slots"].items():
            out.setdefault(v["tray"], []).append({"map": sh["shuffle"], "from": frm, "to": to, "slot": slot,
                                                  "a1": v["a1"], "area": slot_area[slot]})
    return out


def windows(shuffles):
    return [((s["start"] or s["finish"] - NO_START) - WINDOW_PAD, s["finish"] + WINDOW_PAD, s["shuffle"])
            for s in shuffles if s["shuffle"] > 0]


def overlap(a0, a1, b0, b1):
    return max(timedelta(0), min(a1, b1) - max(a0, b0))


def compare(maps, shuffles, slot_area, slot_stays, area_stays, by_tray, end):
    rows = []
    for n, sh in enumerate(shuffles):
        p0 = sh["finish"]
        if n + 1 < len(shuffles):
            p1 = shuffles[n + 1]["start"] or shuffles[n + 1]["finish"] - NO_START
        else:
            p1 = end
        for slot, v in sorted(maps[sh["shuffle"]]["slots"].items(), key=lambda kv: kv[1]["tray"]):
            tray = v["tray"]
            best = max(slot_stays[tray], key=lambda s: overlap(s["first"], s["last"], p0, p1))
            a_best = max(area_stays[tray], key=lambda s: overlap(s["first"], s["last"], p0, p1))
            in_period = [r for r in by_tray[tray] if p0 <= r[0] < p1]
            agree = sum(1 for r in in_period if (r[1], r[2]) == (slot, v["a1"]))
            m_slot, m_a1 = best["key"]
            before = None
            if n > 0:
                before = next(slot_area[k] for k, w in maps[shuffles[n - 1]["shuffle"]]["slots"].items()
                              if w["tray"] == tray)
            area_changed = before is not None and before != slot_area[slot]
            rows.append({
                "shuffle": sh["shuffle"], "tray": tray,
                "recorded finish": ams(sh["finish"]),
                "plan slot": slot, "plan A1": v["a1"], "plan area": slot_area[slot],
                "rig slot": m_slot, "rig A1": m_a1, "rig area": a_best["key"],
                "slot ok": m_slot == slot, "A1 ok": m_a1 == v["a1"], "area ok": a_best["key"] == slot_area[slot],
                "rig slot from": ams(best["first"]), "rig slot to": ams(best["last"]),
                "change, min": round((best["first"] - sh["finish"]).total_seconds() / 60, 1)
                if sh["shuffle"] > 0 else "",
                "area change, min": round((a_best["first"] - sh["finish"]).total_seconds() / 60, 1)
                if area_changed else "",
                "plan area before": before or "",
                "photos read in period": len(in_period), "photos agreeing": agree,
            })
    return rows


def outside(raw_by_tray, stays_by_tray, wins, label):
    """Changes read outside shuffle windows, per tray: each stay that starts outside a window (a
    move, under the 1-hour rule), and each excursion: photos that read the tray away from the stay
    it was in, grouped into one event while less than 30 minutes apart."""
    def outside_windows(t):
        return not any(a <= t <= b for a, b, _ in wins)

    out = []
    for tray, rs in sorted(raw_by_tray.items()):
        ss = stays_by_tray[tray]
        for i, st in enumerate(ss[1:], 1):
            if outside_windows(st["first"]):
                out.append({"tray": tray, "what": label, "kind": "move", "from": ams(st["first"]),
                            "to": ams(st["last"]), "minutes": round((st["last"] - st["first"]).total_seconds() / 60),
                            "photos": st["n"], "stay": fmt(ss[i - 1]["key"]), "read as": fmt(st["key"]),
                            "counts as a move": "yes", "_t": st["first"]})
        event = None
        for r in rs:
            home = [st for st in ss if st["first"] <= r["first"]][-1]
            if r["key"] == home["key"] or not outside_windows(r["first"]):
                continue
            if event and r["first"] - event["_last"] < timedelta(minutes=30):
                event["_last"] = r["last"]
                event["photos"] += r["n"]
                event["_keys"][fmt(r["key"])] += r["n"]
                continue
            event = {"tray": tray, "what": label, "kind": "excursion", "_t": r["first"], "_last": r["last"],
                     "photos": r["n"], "stay": fmt(home["key"]), "_keys": Counter({fmt(r["key"]): r["n"]}),
                     "counts as a move": "no"}
            out.append(event)
    for e in out:
        if e["kind"] == "excursion":
            e["from"], e["to"] = ams(e["_t"]), ams(e["_last"])
            e["minutes"] = round((e["_last"] - e["_t"]).total_seconds() / 60)
            e["read as"] = ", ".join(f"{k} ({v} photos)" for k, v in e["_keys"].items())
    cols = ["tray", "what", "kind", "from", "to", "minutes", "photos", "stay", "read as", "counts as a move", "_t"]
    return [{c: e[c] for c in cols} for e in sorted(out, key=lambda e: e["_t"])]


def fmt(key):
    return " ".join(key) if isinstance(key, tuple) else key


def write_csv(path, rows):
    rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["none"])
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------- pictures


def day_axis(ax, t0, t1):
    ax.set_xlim(t0, t1)
    ax.xaxis.set_major_locator(mdates.DayLocator(tz=CHAMBER))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b", tz=CHAMBER))
    ax.xaxis.set_minor_locator(mdates.HourLocator(byhour=[12], tz=CHAMBER))
    ax.grid(axis="x", which="major", color="#d0d0d0", linewidth=0.8)


def strip(ax, y, segments, t0, t1, h=0.8, hatch=None):
    span = (t1 - t0).total_seconds()
    for frm, to, area in segments:
        x0, x1 = mdates.date2num(frm), mdates.date2num(to)
        ax.add_patch(Rectangle((x0, y - h / 2), x1 - x0, h, facecolor=AREA_FILL[area], edgecolor="white",
                               linewidth=1.5, hatch=hatch))
        if (to - frm).total_seconds() / span > 0.02:
            ax.text((x0 + x1) / 2, y, area, ha="center", va="center", fontsize=9, color=AREA_TEXT[area],
                    fontweight="bold")


def timelines(path, trays, exp, meas, diff, t0, t1, shuffles):
    fig, ax = plt.subplots(figsize=(10.24, 0.9 + 0.62 * 3 * len(trays)), dpi=100)
    labels, ticks, y = [], [], 0
    for tray in trays:
        strip(ax, y, [(e["from"], e["to"], e["area"]) for e in exp[tray]], t0, t1)
        strip(ax, y - 1, [(s["first"], s["last"], s["key"]) for s in meas[tray]], t0, t1)
        for a, b in diff.get(tray, []):
            x0, x1 = mdates.date2num(a), mdates.date2num(b)
            ax.add_patch(Rectangle((x0, y - 1.75), max(x1 - x0, 0.02), 0.5, facecolor="black"))
        labels += [f"Tray {tray} plan", f"Tray {tray} rig", "differs"]
        ticks += [y, y - 1, y - 1.5]
        y -= 2.6
    for s in shuffles:
        ax.axvline(mdates.date2num(s["finish"]), color="#555555", linewidth=0.8, linestyle=":")
        ax.text(mdates.date2num(s["finish"]), 0.75, f"S{s['shuffle']}", fontsize=8, ha="center", va="bottom")
    ax.set_yticks(ticks, labels, fontsize=8)
    ax.set_ylim(y + 0.6, 1.3)
    day_axis(ax, t0, t1)
    ax.set_title("Area per tray over time: plan (map in force after each recorded finish, dotted line Sk)\n"
                 "above what the rig read (stays, 1-hour rule). Black bar in 'differs': plan and rig disagree\n"
                 "(only the minutes between a tray's change and the recorded finish).",
                 fontsize=9, loc="left")
    ax.set_xlabel("Amsterdam time, 2026")
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def marey(path, trays, exp, meas, t0, t1, shuffles):
    fig, axes = plt.subplots(3, 2, figsize=(10.24, 10.0), dpi=100, sharex=True)
    ylev = {a: -i for i, a in enumerate(AREAS)}
    for ax, tray in zip(axes.flat, trays):
        xs, ys = [], []
        for e in exp[tray]:
            xs += [e["from"], e["to"]]
            ys += [ylev[e["area"]]] * 2
        ax.plot(xs, ys, color="#9a9a9a", linewidth=5, solid_capstyle="butt", label="plan")
        xs, ys = [], []
        for s in meas[tray]:
            xs += [s["first"], s["last"]]
            ys += [ylev[s["key"]] + 0.0] * 2
        ax.plot(xs, ys, color="black", linewidth=1.5, linestyle="--", label="rig")
        ax.legend(loc="upper right", fontsize=8, ncol=2, framealpha=0.9)
        for s in shuffles:
            ax.axvline(mdates.date2num(s["finish"]), color="#bbbbbb", linewidth=0.6, linestyle=":")
        ax.set_yticks(list(ylev.values()), list(ylev))
        ax.set_ylim(-5.6, 1.5)
        ax.set_title(f"Tray {tray}", fontsize=10, loc="left")
        day_axis(ax, t0, t1)
        ax.tick_params(axis="x", labelsize=8)
    fig.suptitle("Marey chart: area of each tray over time, Amsterdam time. Grey thick line: plan; "
                 "black dashed line: rig.\nDotted vertical lines: recorded shuffle finishes.", fontsize=10, x=0.01,
                 ha="left")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def table_picture(path, comp, shuffles, trays):
    cells, colours = [], []
    for sh in shuffles:
        row, crow = [], []
        for tray in trays:
            r = next((r for r in comp if r["shuffle"] == sh["shuffle"] and r["tray"] == tray), None)
            bad = [k for k in ("slot", "A1", "area") if not r[f"{k} ok"]]
            txt = ("ok" if not bad else "WRONG " + ",".join(bad)) + f"\n{r['plan slot'].replace('orth ', '').replace('outh ', '')} {r['plan A1']}"
            if r["change, min"] != "":
                txt += f"\n{round(r['change, min']) + 0:+d} min"
            row.append(txt)
            crow.append("#ffffff" if not bad else "#f4c7c7")
        cells.append(row)
        colours.append(crow)
    fig, ax = plt.subplots(figsize=(10.24, 1.3 + 0.62 * len(shuffles)), dpi=100)
    ax.axis("off")
    t = ax.table(cellText=cells, cellColours=colours, colLabels=[f"Tray {t}" for t in trays],
                 rowLabels=[f"Shuffle {s['shuffle']}\n{ams(s['finish'])}" for s in shuffles], loc="center",
                 cellLoc="center")
    t.auto_set_font_size(False)
    t.set_fontsize(7.5)
    t.scale(1, 3.1)
    ax.set_title("Plan against rig after each shuffle. Cell: ok, or WRONG and what differs; planned slot "
                 "(N/S 1-6) and A1;\nminutes from the recorded finish to the rig's first photo of the tray in "
                 "its new slot (negative: before the finish was written).", fontsize=9, loc="left")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def outside_picture(path, rows):
    shown = rows[:40]
    fig, ax = plt.subplots(figsize=(10.24, 1.0 + 0.3 * max(len(shown), 1)), dpi=100)
    ax.axis("off")
    cols = ["tray", "what", "kind", "from", "to", "minutes", "photos", "stay", "read as", "counts as a move"]
    if shown:
        t = ax.table(cellText=[[str(r[c]) for c in cols] for r in shown], colLabels=cols, loc="center",
                     cellLoc="center", colWidths=[0.05, 0.07, 0.08, 0.13, 0.13, 0.07, 0.06, 0.1, 0.19, 0.12])
        t.auto_set_font_size(False)
        t.set_fontsize(7.5)
        t.scale(1, 1.3)
    ax.set_title(f"Changes the rig read outside shuffle windows ({len(rows)}"
                 f"{', first 40 shown' if len(rows) > 40 else ''}), Amsterdam time", fontsize=9, loc="left")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def grid_picture(path, info, slot_layout, slot_area, width=PHOTO_WIDTH_PX, height=6944):
    frame = info["frame"]
    fig, ax = plt.subplots(figsize=(10.24, 8.0), dpi=100)
    ax.add_patch(Rectangle((0, 0), width, height, fill=False, edgecolor="black"))
    for u in info["u_cuts"]:
        pts = [frame.to_pixel(u, v) for v in (-0.2, 1.2)]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color="black", linewidth=1.5)
    pts = [frame.to_pixel(u, 0.5) for u in (info["u_left"], info["u_right"])]
    ax.plot([p[0] for p in pts], [p[1] for p in pts], color="black", linewidth=1.5)
    for x, y in info["corners_px"]:
        ax.plot(x, y, marker="s", color="black", markersize=8)
        ax.text(x, y - 120, "table tag", ha="center", fontsize=8)
    for s in slot_layout["slots"]:
        x, y = s["centre"]
        ax.text(x, y, f"{s['name']}\narea {slot_area[s['name']]}", ha="center", va="center", fontsize=8,
                bbox={"facecolor": AREA_FILL[slot_area[s['name']]], "alpha": 0.35, "edgecolor": "none"})
    ax.set_xlim(0, width)
    ax.set_ylim(height, 0)
    ax.set_aspect("equal")
    ax.set_title("The 3 x 2 areas on the photo (pixels). Lines from the calibration's table frame: rows split\n"
                 "halfway between the table-tag rows, columns in thirds of the photo width along the middle line.",
                 fontsize=9, loc="left")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


# ---------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--experiment", type=int, required=True)
    ap.add_argument("--calibration", type=Path, required=True)
    ap.add_argument("--slots", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    out = args.out.expanduser()
    out.mkdir(parents=True, exist_ok=True)

    maps = json.loads(MAPS.read_text())["maps"]
    shuffles = load_shuffles(RECORD)
    area, info = area_finder(args.calibration.expanduser())
    slot_layout = json.loads(args.slots.expanduser().read_text())
    slot_area = {s["name"]: area(*s["centre"]) for s in slot_layout["slots"]}
    rows, exp_start, end, _ = load_readings(args.db, args.experiment)

    by_tray = {}
    for t, tray, slot, a1, placement, x, y in rows:
        by_tray.setdefault(tray, []).append((datetime.fromisoformat(t), slot, a1, placement, area(x, y)))
    trays = sorted(by_tray)
    raw_area = {k: runs([(r[0], r[4], r[3]) for r in v]) for k, v in by_tray.items()}
    raw_slot = {k: runs([(r[0], (r[1], r[2]), r[3]) for r in v]) for k, v in by_tray.items()}
    area_stays = {k: stays(v) for k, v in raw_area.items()}
    slot_stays = {k: stays(v) for k, v in raw_slot.items()}
    exp = expected(maps, shuffles, slot_area, exp_start, end)

    # Expected and measured placement over time.
    write_csv(out / "expected.csv", [{"tray": k, "map": e["map"], "from": ams(e["from"]), "to": ams(e["to"]),
                                      "slot": e["slot"], "A1": e["a1"], "area": e["area"]}
                                     for k in trays for e in exp[k]])
    write_csv(out / "measured_area_stays.csv", [
        {"tray": k, "area": s["key"], "from": ams(s["first"]), "to": ams(s["last"]),
         "hours": round((s["last"] - s["first"]).total_seconds() / 3600, 1), "photos": s["n"]}
        for k in trays for s in area_stays[k]])
    write_csv(out / "measured_slot_stays.csv", [
        {"tray": k, "slot": s["key"][0], "A1": s["key"][1], "area": slot_area[s["key"][0]],
         "from": ams(s["first"]), "to": ams(s["last"]),
         "hours": round((s["last"] - s["first"]).total_seconds() / 3600, 1), "photos": s["n"]}
        for k in trays for s in slot_stays[k]])

    comp = compare(maps, shuffles, slot_area, slot_stays, area_stays,
                   {k: [(r[0], r[1], r[2]) for r in v] for k, v in by_tray.items()}, end)
    write_csv(out / "comparison.csv", comp)
    wins = windows(shuffles)
    outs = outside(raw_slot, slot_stays, wins, "slot/A1") + outside(raw_area, area_stays, wins, "area")
    outs.sort(key=lambda r: (r["_t"], r["tray"]))
    write_csv(out / "outside_shuffles.csv", outs)

    # Times when plan area and rig area differ (rig stays, 1-hour rule), per tray.
    diff = {}
    for k in trays:
        for e in exp[k]:
            for s in area_stays[k]:
                a, b = max(e["from"], s["first"]), min(e["to"], s["last"])
                if a < b and e["area"] != s["key"]:
                    diff.setdefault(k, []).append((a, b))
        # gaps between stays (tray changing area) after a planned change count too, but only the
        # time where the next stay is in a different area than the plan; already covered above.

    t0, t1 = exp_start - timedelta(hours=2), end + timedelta(hours=2)
    timelines(out / "timelines_trays_1-6.png", trays[:6], exp, area_stays, diff, t0, t1, shuffles[1:])
    timelines(out / "timelines_trays_7-12.png", trays[6:], exp, area_stays, diff, t0, t1, shuffles[1:])
    marey(out / "marey_trays_1-6.png", trays[:6], exp, area_stays, t0, t1, shuffles[1:])
    marey(out / "marey_trays_7-12.png", trays[6:], exp, area_stays, t0, t1, shuffles[1:])
    table_picture(out / "comparison.png", comp, shuffles, trays)
    outside_picture(out / "outside_shuffles.png", outs)
    grid_picture(out / "areas_on_photo.png", info, slot_layout, slot_area)

    # Numbers for the summary.
    n = len(comp)
    print(f"photos read with trays: {len({r[0] for v in by_tray.values() for r in v})}; data "
          f"{ams(exp_start)} to {ams(end)}")
    print("slot areas:", slot_area)
    for k in ("slot ok", "A1 ok", "area ok"):
        print(f"{k}: {sum(r[k] for r in comp)} of {n}")
    ch = [r["change, min"] for r in comp if r["change, min"] != ""]
    for sh in shuffles[1:]:
        c = [r["change, min"] for r in comp if r["shuffle"] == sh["shuffle"]]
        print(f"shuffle {sh['shuffle']}: change min {min(c)} to {max(c)}, "
              f"agreeing photos {sum(r['photos agreeing'] for r in comp if r['shuffle'] == sh['shuffle'])}"
              f" of {sum(r['photos read in period'] for r in comp if r['shuffle'] == sh['shuffle'])}")
    print(f"all changes: {min(ch)} to {max(ch)} min")
    print(f"area stays per tray: { {k: len(v) for k, v in area_stays.items()} }")
    print(f"slot stays per tray: { {k: len(v) for k, v in slot_stays.items()} }")
    print(f"outside-shuffle raw runs: {len(outs)}; area moves counted: "
          f"{sum(r['counts as a move'] == 'yes' for r in outs)}")
    for r in outs:
        print("  ", {k: v for k, v in r.items() if not k.startswith('_')})
    print("diff hours per tray:", {k: round(sum((b - a).total_seconds() for a, b in v) / 3600, 2)
                                   for k, v in diff.items()})


if __name__ == "__main__":
    main()
