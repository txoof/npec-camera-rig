"""Charts for metrology log 38 (#394), from cells.py's outputs and the slim copy.

    python charts.py SLIM_DB RESTART_PAIRS_JSON OUT_DIR

Per tray (`tray_<n>.png`): one small chart per cell, laid out as the tray (columns A to D, rows 1
to 5; A1 holds the tag). Faint dots: every usable photo, fixed green cutoff. Lines: hourly
medians, both rules. Grey bands: shuffle windows. Green line: mats laid (6 Nov). Yellow: harvest and moves from 9 Nov, not recorded. Log area axis.
Summary (`noise.png`): the photo-to-photo and hour-to-hour change against cell size.
"""
import collections
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

import cells as C  # noqa: E402

BLUE, ORANGE = "#2a78d6", "#eb6834"   # categorical slots 1 and 2 (fixed green cutoff, grow from leaf cores)
INK, MUTED = "#222222", "#6b6b6b"
MAT, HARVEST = "#1b7a1b", "#fff1c2"
# From the last recorded shuffle (12, 9 Nov) the researcher harvests and moves plants with no record (Aaron, 2026-11-17).
HARVEST_FROM = datetime(2026, 11, 9, 10, 41, tzinfo=C.UTC)


def small(fig, path):
    """A copy for docs/figures: lower resolution, 64-colour palette (under about 200 KB)."""
    from PIL import Image
    fig.savefig(path, dpi=60)
    Image.open(path).convert("RGB").quantize(64).save(path, optimize=True)


def read_csv(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def fnum(x):
    return float(x) if x not in ("", None) else None


def tray_charts(db, restart_json, out):
    breaks = C.shuffles()
    photos, _, _, trays, cells, _ = C.load(db, json.load(open(restart_json)))
    dots = collections.defaultdict(list)
    for p in photos:
        if not C.photo_ok(p, breaks):
            continue
        cs = cells.get(p["capture_id"], {})
        for tray in C.TRAYS:
            if C.tray_in_study(tray, p["taken_at"]) and C.tray_ok(trays.get((p["capture_id"], tray))):
                for key, v in cs.items():
                    if key[0] == tray and v[0][0]:
                        dots[key].append((p["taken_at"], v[0][0]))
    del cells, trays
    lines = collections.defaultdict(list)
    for r in read_csv(out / "hourly.csv"):
        lines[(int(r["tray"]), r["cell"])].append(
            (datetime.fromisoformat(r["hour_utc"]), fnum(r["fixed green cutoff median"]),
             fnum(r["grow from leaf cores median"])))
    t0 = min(p["taken_at"] for p in photos)
    t1 = max(p["taken_at"] for p in photos)
    for tray in C.TRAYS:
        fig, axes = plt.subplots(5, 4, figsize=(16, 15), sharex=True, sharey=True)
        for col, letter in enumerate("ABCD"):
            for row in range(5):
                ax = axes[row][col]
                cell = f"{letter}{row + 1}"
                ax.set_title(cell, loc="left", fontsize=10, color=INK)
                for s, e in breaks:
                    ax.axvspan(s, e, color="#d9d9d9", lw=0)
                ax.axvspan(HARVEST_FROM, t1, color=HARVEST, lw=0)
                ax.axvline(C.MATS[0], color=MAT, lw=1.6)
                if cell == "A1":
                    ax.text(0.5, 0.5, "tag", transform=ax.transAxes, ha="center", color=MUTED)
                    continue
                pts = dots.get((tray, cell), [])
                if pts:
                    ax.scatter([t for t, _ in pts], [a for _, a in pts], s=1, color=BLUE, alpha=0.08,
                               lw=0, rasterized=True)
                ln = sorted(lines.get((tray, cell), []))
                for i, colr, name in ((1, BLUE, "fixed green cutoff"), (2, ORANGE, "grow from leaf cores")):
                    xs = [x[0] for x in ln if x[i]]
                    ys = [x[i] for x in ln if x[i]]
                    ax.plot(xs, ys, color=colr, lw=1.2, label=f"{name}, hourly median")
                ax.set_yscale("log")
                ax.set_ylim(0.5, 5000)
                ax.set_xlim(t0, t1)
                ax.grid(True, which="major", color="#eeeeee", lw=0.6)
                ax.tick_params(labelsize=8, colors=MUTED)
        for ax in axes[-1]:
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=4))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        for ax in axes[:, 0]:
            ax.set_ylabel("area, mm² (log)", fontsize=9, color=MUTED)
        handles, labels = axes[0][1].get_legend_handles_labels()
        handles += [plt.Rectangle((0, 0), 1, 1, color="#d9d9d9"), plt.Line2D([], [], color=MAT, lw=1.6),
                    plt.Rectangle((0, 0), 1, 1, color=HARVEST)]
        labels += ["shuffle window", "blue mats laid, 6 Nov 08:10 UTC", "harvest and moves, not recorded"]
        fig.legend(handles, labels, loc="upper right", ncol=5, frameon=False, fontsize=10)
        until = " (to 5 Nov 11:00 UTC)" if tray == 7 else ""
        fig.suptitle(f"Tray {tray}{until}: plant area per cell, experiment 18 (production). "
                     "Dots: every usable photo, fixed green cutoff. Times UTC.", x=0.01, ha="left", fontsize=12)
        fig.tight_layout(rect=(0, 0, 1, 0.97))
        fig.savefig(out / f"tray_{tray}.png", dpi=90)
        small(fig, out / f"tray_{tray}_small.png")
        plt.close(fig)
        print("tray", tray)


def noise_chart(out):
    p2p = read_csv(out / "photo_to_photo.csv")
    h2h = read_csv(out / "hour_to_hour.csv")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    for ax, rule in zip(axes, C.RULES):
        for rows, style, name in (
                ([r for r in p2p if r["rule"] == rule], "o-", "photo to photo (1 min)"),
                ([r for r in h2h if r["rule"] == rule and r["kind"] == "one photo per hour"], "s--",
                 "one photo per hour, hour to hour"),
                ([r for r in h2h if r["rule"] == rule and r["kind"] == "hourly median"], "^-",
                 "hourly median, hour to hour")):
            rows = [r for r in rows if float(r["band_lo"]) >= 1]
            xs = [(float(r["band_lo"]) * float(r["band_hi"])) ** 0.5 for r in rows]
            ax.plot(xs, [float(r["rms"]) for r in rows], style, ms=6, lw=1.5, label=name)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_title(rule, loc="left")
        ax.set_xlabel("cell area, mm² (size band, log)")
        ax.grid(True, color="#eeeeee")
    axes[0].set_ylabel("root mean square change, mm² (log)")
    axes[1].legend(frameon=False)
    fig.suptitle("How much a cell's area changes, by cell size: trays 1 to 6 (7 to 5 Nov), whole run",
                 x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(out / "noise.png", dpi=90)
    small(fig, out / "noise_small.png")


if __name__ == "__main__":
    out = Path(sys.argv[3])
    noise_chart(out)
    tray_charts(sys.argv[1], sys.argv[2], out)
