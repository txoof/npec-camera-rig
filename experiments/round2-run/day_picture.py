"""One picture per chamber day of a run (metrology log 16): for each tray, every photo where its tag
was found or missed, dark photos, the shuffling window, shuffles and events. For Aaron's
check-ins; drawn with OpenCV, as overnight.py in round1-trays.

    python day_picture.py WORKDIR --experiment 18 --shuffles sessions/shuffles-2026-10-22.csv \
        [--events sessions/events-2026-10-22.csv] --out DIR

Reads the copy of rig.db in WORKDIR (read_photos.py), writes DIR/day-<experiment>-<date>.png.
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np

import analyse
from analysis import CHAMBER, MOVING_FROM, MOVING_TO, window

W, LEFT, RIGHT, TOP, ROW = 2400, 190, 30, 110, 40
FONT = cv2.FONT_HERSHEY_SIMPLEX
INK, MUTED, GRID = (20, 20, 20), (90, 90, 90), (225, 225, 225)
SURFACE, WINDOW = (251, 252, 252), (238, 244, 247)
FOUND, MISSED, DARK, SHUFFLE = (230, 196, 150), (30, 30, 180), (70, 70, 70), (0, 161, 237)  # BGR


def x_of(local, day_start):
    return LEFT + int((local - day_start).total_seconds() / 86400 * (W - LEFT - RIGHT))


def text(img, words, xy, scale=0.5, colour=INK, thick=1):
    cv2.putText(img, words, xy, FONT, scale, colour, thick, cv2.LINE_AA)


def draw_day(day, photos, centres, shuffles, events, trays, experiment):
    day_start = datetime.fromisoformat(day).replace(tzinfo=CHAMBER)
    mine = [p for p in photos if window(p["taken_at"])[0] == day]
    misses = []
    height = TOP + ROW * len(trays) + 150
    img = np.full((height, W, 3), SURFACE, np.uint8)
    bottom = TOP + ROW * len(trays)

    # The shuffling window, by the clock (16.3).
    x0 = x_of(day_start.replace(hour=MOVING_FROM.hour, minute=MOVING_FROM.minute), day_start)
    x1 = x_of(day_start.replace(hour=MOVING_TO.hour, minute=MOVING_TO.minute), day_start)
    cv2.rectangle(img, (x0, TOP - 8), (x1, bottom), WINDOW, -1)
    text(img, "trays may move (09:30 to 17:00)", (x0 + 6, TOP - 14), 0.45, MUTED)

    for hour in range(25):
        x = x_of(day_start + timedelta(hours=hour), day_start)
        cv2.line(img, (x, TOP - 8), (x, bottom), GRID, 1)
        if hour % 2 == 0:
            text(img, f"{hour:02d}:00", (x - 20, bottom + 20), 0.45, MUTED)
    text(img, "chamber time", (W - RIGHT - 110, bottom + 42), 0.45, MUTED)

    for n, tray in enumerate(trays):
        y = TOP + ROW * n + ROW // 2
        kind = "plant" if tray in analyse.PLANT_TRAYS else "pots"
        text(img, f"tray {tray} ({kind})", (14, y + 5), 0.5)
        cv2.line(img, (LEFT, y + ROW // 2), (W - RIGHT, y + ROW // 2), GRID, 1)

    dark = other = 0
    for p in mine:
        x = x_of(p["taken_at"].astimezone(CHAMBER), day_start)
        if p["status"] == "no tags found":
            dark += 1
            cv2.line(img, (x, TOP), (x, bottom), DARK, 1)
            continue
        if p["status"] != "read":
            # Not read yet, or not readable (no calibration): says nothing about light or trays.
            other += 1
            cv2.line(img, (x, TOP - 8), (x, TOP - 2), DARK, 1)
            continue
        here = centres.get(p["capture_id"], {})
        for n, tray in enumerate(trays):
            y = TOP + ROW * n + ROW // 2
            if tray in here:
                cv2.line(img, (x, y - 4), (x, y + 4), FOUND, 1)
            elif here:
                misses.append((p["taken_at"], tray, x, y))
    # Misses drawn last, over the found lines: a dark line the height of the row, under a triangle.
    for _, _, x, y in misses:
        cv2.line(img, (x, y - ROW // 2 + 3), (x, y + ROW // 2 - 3), MISSED, 3)
        cv2.fillPoly(img, [np.array([(x - 6, y - ROW // 2 - 6), (x + 6, y - ROW // 2 - 6), (x, y - ROW // 2 + 3)])], MISSED)

    for s in shuffles:
        finish = s["finish"].astimezone(CHAMBER)
        start = (s["start"] or s["finish"]).astimezone(CHAMBER)
        if finish.date().isoformat() != day:
            continue
        xs, xf = x_of(start, day_start), x_of(finish, day_start)
        cv2.rectangle(img, (xs, TOP - 4), (max(xf, xs + 2), bottom), SHUFFLE, 2)
        text(img, f"map {s['shuffle']}", (xs + 4, TOP - 34), 0.5, INK)
    for t, words in events:
        local = t.astimezone(CHAMBER)
        if local.date().isoformat() == day:
            x = x_of(local, day_start)
            cv2.line(img, (x, TOP - 4), (x, bottom), INK, 1)
            text(img, words[:30], (x + 4, TOP - 48), 0.42, INK)

    read = sum(p["status"] == "read" for p in mine)
    text(img, f"Experiment {experiment}, {day} (chamber time): {len(mine)} photos, {read} read, "
              f"{dark} dark, {other} not read, {len(misses)} tray tags missed while others were found",
         (14, 32), 0.65, INK, 2)
    text(img, "Pale line: a photo with that tray's tag found.  Dark red line under a triangle: tag missed while others were found.  "
              "Grey line across all trays: dark (no tag found).  Grey tick at the top: not read.  "
              "Box: shuffle, start to finish.",
         (14, 60), 0.45, MUTED)
    y = bottom + 70
    text(img, "Missed, chamber time (UTC):", (14, y), 0.5, INK, 1)
    for i, (t, tray, _, _) in enumerate(misses[:7]):
        local = t.astimezone(CHAMBER)
        text(img, f"tray {tray} {local:%H:%M:%S} ({t:%H:%M:%S})", (14 + 250 * i, y + 24), 0.5)
    if len(misses) > 7:
        text(img, f"and {len(misses) - 7} more, in the misses CSV", (14, y + 48), 0.5, MUTED)
    return img


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workdir", type=Path)
    parser.add_argument("--experiment", type=int, required=True)
    parser.add_argument("--shuffles", type=Path, required=True)
    parser.add_argument("--events", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    workdir = args.workdir.resolve()
    photos, centres, _, _ = analyse.load(workdir, args.experiment)
    shuffles = analyse.read_shuffles(args.shuffles)
    events = analyse.read_events(args.events)
    trays = sorted({t for found in centres.values() for t in found})
    args.out.mkdir(parents=True, exist_ok=True)
    for day in sorted({window(p["taken_at"])[0] for p in photos}):
        path = args.out / f"day-{args.experiment}-{day}.png"
        cv2.imwrite(str(path), draw_day(day, photos, centres, shuffles, events, trays, args.experiment))
        print(path)


if __name__ == "__main__":
    main()
