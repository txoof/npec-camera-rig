"""One picture per chamber day of a run (metrology log 16): an hour grid of tray tags missed while
others were found, with dark hours, shuffles and events. For Aaron's check-ins; drawn with OpenCV,
as overnight.py in round1-trays.

    python day_picture.py WORKDIR --experiment 18 --shuffles sessions/shuffles-2026-10-22.csv \
        [--events sessions/events-2026-10-22.csv] --out DIR

Reads the copy of rig.db in WORKDIR (read_photos.py), writes DIR/day-<experiment>-<date>.png.
"""

import argparse
from pathlib import Path

import cv2
import numpy as np

import analyse
from analysis import CHAMBER, window

LEFT, COL, ROW, TOP = 170, 56, 34, 96
W = LEFT + 24 * COL + 20
FONT = cv2.FONT_HERSHEY_SIMPLEX
INK, MUTED, GRID = (20, 20, 20), (110, 110, 110), (215, 215, 215)
SURFACE, NO_PHOTO, DARK_FILL, SHUFFLE_FILL, MISS_FILL = (
    (251, 252, 252), (240, 240, 240), (200, 200, 200), (240, 228, 205), (205, 210, 250))  # BGR


def text(img, words, xy, scale=0.5, colour=INK, thick=1):
    cv2.putText(img, words, xy, FONT, scale, colour, thick, cv2.LINE_AA)


def centred(img, words, x, y, scale=0.5, colour=INK, thick=1):
    (w, _), _ = cv2.getTextSize(words, FONT, scale, thick)
    text(img, words, (x - w // 2, y), scale, colour, thick)


def shuffle_hours(shuffles, day):
    """{hour: [map numbers]} for the shuffles of `day` (chamber time), each in every hour it spans.
    A layout with no start (map 0, the layout at the experiment's start) is not a shuffle."""
    hours = {}
    for s in shuffles:
        if s["start"] is None:
            continue
        start = (s["start"] or s["finish"]).astimezone(CHAMBER)
        finish = s["finish"].astimezone(CHAMBER)
        if finish.date().isoformat() != day and start.date().isoformat() != day:
            continue
        first = start.hour if start.date().isoformat() == day else 0
        last = finish.hour if finish.date().isoformat() == day else 23
        for hour in range(first, last + 1):
            hours.setdefault(hour, []).append(s["shuffle"])
    return hours


def draw_day(day, photos, centres, shuffles, events, trays, experiment):
    """An hour grid: a row per tray, a column per hour of the chamber day. Each cell is the number
    of photos in that hour where the tray's tag was missed while others were found ("." when none);
    "dark" when every photo of the hour found no tag; blank when the hour has no photo."""
    mine = [p for p in photos if window(p["taken_at"])[0] == day]
    hour_of = {p["capture_id"]: p["taken_at"].astimezone(CHAMBER).hour for p in mine}
    lit, dark, misses = [0] * 24, [0] * 24, {}
    missed_at = []
    for p in mine:
        h = hour_of[p["capture_id"]]
        if p["status"] == "no tags found":
            dark[h] += 1
        elif p["status"] == "read":
            lit[h] += 1
            here = centres.get(p["capture_id"], {})
            for tray in trays:
                if here and tray not in here:
                    misses[(tray, h)] = misses.get((tray, h), 0) + 1
                    missed_at.append((p["taken_at"], tray, h))
    shuffled = shuffle_hours(shuffles, day)
    evented = {}
    for t, words in events:
        local = t.astimezone(CHAMBER)
        if local.date().isoformat() == day:
            evented.setdefault(local.hour, []).append(words)

    header = ["lit photos", "dark photos", "shuffles", "events"]
    grid_top = TOP + ROW * len(header)
    bottom = grid_top + ROW * len(trays)
    quiet = [m for m in missed_at if m[2] not in shuffled]
    day_shuffles = [s for s in shuffles if s["finish"].astimezone(CHAMBER).date().isoformat() == day]
    day_events = [(t, w) for t, w in events if t.astimezone(CHAMBER).date().isoformat() == day]
    listed = len(day_shuffles) + len(day_events)
    height = bottom + 130 + 24 * ((len(quiet) + 5) // 6) + 24 * ((listed + 5) // 6)
    img = np.full((height, W, 3), SURFACE, np.uint8)

    for h in range(24):
        x = LEFT + COL * h
        centred(img, f"{h:02d}", x + COL // 2, TOP - 10, 0.5, MUTED)
        values = [str(lit[h]) if lit[h] else "", str(dark[h]) if dark[h] else "",
                  str(len(shuffled[h])) if h in shuffled else "", str(len(evented[h])) if h in evented else ""]
        for r, v in enumerate(values):
            centred(img, v, x + COL // 2, TOP + ROW * r + 22, 0.45, INK)
        for n, tray in enumerate(trays):
            y = grid_top + ROW * n
            if not lit[h] and not dark[h]:
                fill, words, colour = NO_PHOTO, "", MUTED
            elif not lit[h]:
                fill, words, colour = DARK_FILL, "dark", INK
            elif (tray, h) in misses:
                fill, words, colour = MISS_FILL, str(misses[(tray, h)]), INK
            else:
                fill, words, colour = SHUFFLE_FILL if h in shuffled else SURFACE, ".", MUTED
            if fill == SURFACE and h in shuffled:
                fill = SHUFFLE_FILL
            cv2.rectangle(img, (x, y), (x + COL, y + ROW), fill, -1)
            centred(img, words, x + COL // 2, y + 23, 0.55, colour, 2 if colour == INK else 1)
    for r in range(len(header) + len(trays) + 1):
        y = TOP + ROW * r
        cv2.line(img, (LEFT, y), (LEFT + 24 * COL, y), GRID, 1)
    for h in range(25):
        cv2.line(img, (LEFT + COL * h, TOP), (LEFT + COL * h, bottom), GRID, 1)
    cv2.line(img, (14, grid_top), (LEFT + 24 * COL, grid_top), INK, 1)
    for r, words in enumerate(header):
        text(img, words, (14, TOP + ROW * r + 22), 0.45, MUTED)
    for n, tray in enumerate(trays):
        kind = "plant" if tray in analyse.PLANT_TRAYS else "pots"
        text(img, f"tray {tray} ({kind})", (14, grid_top + ROW * n + 22), 0.5)

    text(img, f"Experiment {experiment}, {day}, chamber time by hour: {len(mine)} photos, "
              f"{len(missed_at)} tray tags missed while others were found, {len(quiet)} of them in hours with no shuffle",
         (14, 30), 0.6, INK, 2)
    text(img, "Number: photos that hour with the tag missed while others were found.  .: found in every lit photo.  "
              "dark: no tag in any photo.  Tinted column: a shuffle that hour.  Blank: no photo.",
         (14, 58), 0.45, MUTED)
    y = bottom + 36
    text(img, "Missed in hours with no shuffle, chamber time (UTC):", (14, y), 0.5, INK)
    for i, (t, tray, _) in enumerate(quiet):
        local = t.astimezone(CHAMBER)
        text(img, f"tray {tray} {local:%H:%M:%S} ({t:%H:%M:%S})", (14 + 250 * (i % 6), y + 26 + 24 * (i // 6)), 0.5)
    if not quiet:
        text(img, "none", (14, y + 26), 0.5, MUTED)
    y += 26 + 24 * max(1, (len(quiet) + 5) // 6) + 20
    text(img, "Shuffles (map, start to finish) and events, chamber time:", (14, y), 0.5, INK)
    items = [f"map {s['shuffle']} {s['start'].astimezone(CHAMBER):%H:%M} to {s['finish'].astimezone(CHAMBER):%H:%M}"
             if s["start"] else f"map {s['shuffle']} (start) from {s['finish'].astimezone(CHAMBER):%H:%M}"
             for s in day_shuffles] + [f"{t.astimezone(CHAMBER):%H:%M} {w[:24]}" for t, w in day_events]
    for i, words in enumerate(items):
        text(img, words, (14 + 250 * (i % 6), y + 26 + 24 * (i // 6)), 0.5)
    if not items:
        text(img, "none", (14, y + 26), 0.5, MUTED)
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
