"""Tray tags missed while others were found (metrology log 16.4, question 2), for Aaron's
check-ins: a table per tray, and bar charts of the misses outside shuffles by tray ID and by the
slot each tray was last read in. Drawn with OpenCV, as overnight.py in round1-trays.

    python misses_chart.py WORKDIR --experiment 18 --shuffles sessions/shuffles-2026-10-22.csv \
        --out DIR

Reads the copy of rig.db in WORKDIR (read_photos.py), the whole experiment so far. Writes
DIR/misses-<experiment>.png and .md (the table).
"""

import argparse
from pathlib import Path

import cv2
import numpy as np

import analyse
import analysis

SLOTS = [f"{side} {n}" for side in ("North", "South") for n in range(1, 7)]
FONT = cv2.FONT_HERSHEY_SIMPLEX
INK, MUTED, GRID, SURFACE, BAR = (20, 20, 20), (110, 110, 110), (225, 225, 225), (251, 252, 252), (214, 120, 42)
PANEL_W, PANEL_H, BAR_GAP = 760, 380, 14


def text(img, words, xy, scale=0.5, colour=INK, thick=1):
    cv2.putText(img, words, xy, FONT, scale, colour, thick, cv2.LINE_AA)


def centred(img, words, x, y, scale=0.5, colour=INK, thick=1):
    (w, _), _ = cv2.getTextSize(words, FONT, scale, thick)
    text(img, words, (x - w // 2, y), scale, colour, thick)


def bars(img, x0, y0, title, labels, values, top):
    """One bar chart: a bar per label, its count above it, from a baseline at zero."""
    text(img, title, (x0, y0 + 24), 0.6, INK, 2)
    left, right, base, roof = x0 + 40, x0 + PANEL_W - 10, y0 + PANEL_H - 50, y0 + 60
    for tick in range(top + 1):
        y = base - int((base - roof) * tick / top)
        cv2.line(img, (left, y), (right, y), GRID, 1)
        text(img, str(tick), (x0 + 10, y + 5), 0.45, MUTED)
    width = (right - left) / len(labels)
    for i, (label, value) in enumerate(zip(labels, values)):
        xa, xb = int(left + i * width + BAR_GAP / 2), int(left + (i + 1) * width - BAR_GAP / 2)
        if value:
            y = base - int((base - roof) * value / top)
            cv2.rectangle(img, (xa, y), (xb, base), BAR, -1)
            centred(img, str(value), (xa + xb) // 2, y - 8, 0.5, INK)
        for n, part in enumerate(str(label).split(" ")):
            centred(img, part, (xa + xb) // 2, base + 22 + 18 * n, 0.45, INK)
    cv2.line(img, (left, base), (right, base), INK, 1)


def chart(result, trays, title):
    outside = {k: v["outside shuffles"] for k, v in result["by_tray"].items()}
    by_slot = {k: v["outside shuffles"] for k, v in result["by_slot"].items()}
    slots = SLOTS + sorted(set(by_slot) - set(SLOTS))
    top = max([1, *outside.values(), *by_slot.values()])
    img = np.full((PANEL_H + 60, 2 * PANEL_W + 40, 3), SURFACE, np.uint8)
    text(img, title, (14, 34), 0.7, INK, 2)
    bars(img, 10, 50, "Misses by tray ID", trays, [outside.get(t, 0) for t in trays], top)
    bars(img, PANEL_W + 30, 50, "Misses by slot last read in", slots, [by_slot.get(s, 0) for s in slots], top)
    return img


def table(photos, centres, result, trays):
    read = [p for p in photos if p["status"] == "read"]
    rows = ["| Tray | Photos read | Tag found | Missed, outside shuffles | Missed, during shuffles |",
            "|---|---|---|---|---|"]
    for tray in trays:
        found = sum(tray in centres.get(p["capture_id"], {}) for p in read)
        counts = result["by_tray"].get(tray, {"outside shuffles": 0, "during shuffles": 0})
        rows.append(f"| {tray} | {len(read)} | {found} | {counts['outside shuffles']} | {counts['during shuffles']} |")
    rows += ["", "| Time, chamber (UTC) | Tray | Slot last read in | During a shuffle |", "|---|---|---|---|"]
    for m in result["misses"]:
        local = m["taken_at"].astimezone(analysis.CHAMBER)
        rows.append(f"| {local:%Y-%m-%d %H:%M:%S} ({m['taken_at']:%H:%M:%S}) | {m['tray']} | {m['slot']} | "
                    f"{'yes' if m['during_shuffle'] else 'no'} |")
    return "\n".join(rows) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workdir", type=Path)
    parser.add_argument("--experiment", type=int, required=True)
    parser.add_argument("--shuffles", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    photos, centres, placements, _ = analyse.load(args.workdir.resolve(), args.experiment)
    trays = sorted({t for found in centres.values() for t in found})
    shuffles = analyse.read_shuffles(args.shuffles)
    result = analysis.misses(photos, placements, shuffles, trays)
    n = sum(v["outside shuffles"] for v in result["by_tray"].values())
    first, last = (photos[i]["taken_at"].astimezone(analysis.CHAMBER) for i in (0, -1))
    title = f"Experiment {args.experiment}, {first:%d %b %H:%M} to {last:%d %b %H:%M}: {n} tray tags missed outside shuffles"
    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.out / f"misses-{args.experiment}"
    cv2.imwrite(f"{stem}.png", chart(result, trays, title))
    Path(f"{stem}.md").write_text(f"# {title}\n\n" + table(photos, centres, result, trays))
    print(f"{stem}.png\n{stem}.md")


if __name__ == "__main__":
    main()
