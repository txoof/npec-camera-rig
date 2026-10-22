"""Printable shuffle maps for the Round 2 run, and their known answer (metrology log 16, #221).

Each map is one random layout of trays 1 to 12 in the slots North 1..6 and South 1..6, with cell
A1 (and the tray's AprilTag) at the south-west or north-east corner. Drawn from a fixed seed, so
the maps can be made again exactly.

Rules (Aaron, 2026-10-22):
- Trays 1 to 7 hold plants and go in 7 of the 8 middle slots, North and South 2 to 5: the
  collaborator's experiment prefers them there. Trays 8 to 12 hold pots and fill the rest.
- Every tray moves: no tray is in the slot it had on the map before (for map 1, the layout read
  by the rig at the start, FIRST below).

Writes the known answer as JSON (committed before any tray is moved; never rewritten) and an A4 landscape PDF, one
map per page, for a black and white printer: nothing is told apart by colour alone.

    python shuffle_maps.py OUT_DIR
"""

import json
import random
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

SEED, N_MAPS = 20261022, 12
ROWS = ("North", "South")
SLOTS = [f"{row} {i}" for row in ROWS for i in range(1, 7)]
MIDDLE = [f"{row} {i}" for row in ROWS for i in range(2, 6)]
PLANTS, POTS = list(range(1, 8)), list(range(8, 13))
BENCHMARK = 8  # the plastic benchmark "Benchy Yellow-4" is taped to this pot tray for the run (Aaron, 2026-10-22)
# Map 0: the layout at the start of the run, not drawn but read by the rig (tray readings, #222)
# from the still taken at 2026-10-22 09:11:53 UTC, experiment "Potato Plants v001"; every photo of
# the run from 08:41:20 had the trays in these slots (one, 08:55:53, missed tray 2). Slot -> tray, A1.
MAP_0 = {
    "North 1": (12, "NE"), "North 2": (10, "NE"), "North 3": (6, "SW"), "North 4": (3, "SW"),
    "North 5": (5, "NE"), "North 6": (9, "SW"), "South 1": (11, "SW"), "South 2": (2, "SW"),
    "South 3": (4, "NE"), "South 4": (1, "NE"), "South 5": (7, "NE"), "South 6": (8, "NE"),
}
FIRST = {s: tray for s, (tray, _a1) in MAP_0.items()}


def draw_layout(rng: random.Random, before: dict[str, int]) -> dict[str, dict]:
    """One layout: plants in 7 random middle slots, pots in the other 5 slots, A1 corner random;
    drawn again until no tray is in its slot of `before`."""
    while True:
        plant_slots = rng.sample(MIDDLE, len(PLANTS))
        pot_slots = [s for s in SLOTS if s not in plant_slots]
        trays = dict(zip(plant_slots, rng.sample(PLANTS, len(PLANTS))))
        trays |= dict(zip(pot_slots, rng.sample(POTS, len(POTS))))
        if all(before[s] != trays[s] for s in SLOTS):
            return {s: {"tray": trays[s], "a1": rng.choice(["SW", "NE"])} for s in SLOTS}


def plan() -> dict:
    rng = random.Random(SEED)
    maps, before = [], FIRST
    start = {"map": 0, "slots": {s: {"tray": t, "a1": a1} for s, (t, a1) in MAP_0.items()},
             "source": "read by the rig from the still of 2026-10-22 09:11:53 UTC; the layout at the start, not a shuffle"}
    for n in range(1, N_MAPS + 1):
        layout = draw_layout(rng, before)
        maps.append({"map": n, "slots": layout})
        before = {s: v["tray"] for s, v in layout.items()}
    before = FIRST
    for m in maps:  # the rules, checked on the result
        slots = m["slots"]
        assert sorted(v["tray"] for v in slots.values()) == list(range(1, 13))
        assert all(slots[s]["tray"] not in PLANTS for s in SLOTS if s not in MIDDLE)  # no plants at the ends
        assert all(slots[s]["a1"] in ("SW", "NE") for s in SLOTS)
        assert all(slots[s]["tray"] != before[s] for s in SLOTS)  # every tray moves
        before = {s: v["tray"] for s, v in slots.items()}
    return {
        "seed": SEED, "date": "2026-10-22", "experiment": "Potato Plants v001",
        "generator": "python random.Random(seed): per map, trays 1-7 into 7 of North/South 2-5, trays 8-12 "
                     "into the other slots, A1 corner SW or NE per tray; redrawn until no tray keeps its slot",
        "first_layout": FIRST,
        "turn": "SW: A1 and its tag at the lower left (south-west); NE: tray turned 180, A1 at the upper right",
        "plants": PLANTS, "pots": POTS, "benchmark": f"taped to tray {BENCHMARK}", "maps": [start, *maps],
    }


# --- Drawing (A4 landscape, points) ---

PAGE_W, PAGE_H = landscape(A4)
MARGIN = 28
TRAY_W, TRAY_H = 112.0, 134.0  # 305 x 366 mm, portrait
GAP_X, GAP_Y = 14.0, 66.0
GRID_X = (PAGE_W - 6 * TRAY_W - 5 * GAP_X) / 2


def tag(c: canvas.Canvas, x: float, y: float, s: float) -> None:
    """A drawn AprilTag: black square, white inner square, a few black blocks."""
    c.setFillGray(0); c.rect(x, y, s, s, stroke=0, fill=1)
    b = s / 8
    c.setFillGray(1); c.rect(x + b, y + b, s - 2 * b, s - 2 * b, stroke=0, fill=1)
    c.setFillGray(0)
    for i, j in ((1, 1), (1, 4), (2, 2), (3, 5), (4, 1), (4, 3), (5, 4), (2, 5), (5, 2)):
        c.rect(x + b * (1 + i), y + b * (1 + j) - b, b, b, stroke=0, fill=1)


def tray(c: canvas.Canvas, x: float, y: float, slot: str, number: int, a1: str) -> None:
    plants = number in PLANTS
    c.setStrokeGray(0); c.setFillGray(1)
    c.setLineWidth(2.2)
    c.rect(x, y, TRAY_W, TRAY_H, stroke=1, fill=1)
    if plants:  # a second border inside: plant trays are told apart without colour
        c.setLineWidth(1.4)
        c.rect(x + 4, y + 4, TRAY_W - 8, TRAY_H - 8, stroke=1, fill=0)
    # Cells, 4 across and 5 down, light lines.
    cw, ch = TRAY_W / 4, TRAY_H / 5
    c.setLineWidth(0.5); c.setStrokeGray(0.6)
    for i in range(1, 4):
        c.line(x + i * cw, y, x + i * cw, y + TRAY_H)
    for j in range(1, 5):
        c.line(x, y + j * ch, x + TRAY_W, y + j * ch)
    # Cell A1 and its tag: lower left (SW) or upper right (NE).
    ax, ay = (x, y) if a1 == "SW" else (x + 3 * cw, y + 4 * ch)
    c.saveState()
    p = c.beginPath(); p.rect(ax, ay, cw, ch); c.clipPath(p, stroke=0)
    c.setStrokeGray(0.45); c.setLineWidth(0.8)
    for k in range(-10, 14):  # diagonal hatching
        c.line(ax + k * 5, ay, ax + k * 5 + ch, ay + ch)
    c.restoreState()
    c.setStrokeGray(0); c.setLineWidth(2.4)
    c.rect(ax, ay, cw, ch, stroke=1, fill=0)
    s = min(cw, ch) * 0.7
    c.setFillGray(1); c.rect(ax + (cw - s) / 2 - 2, ay + (ch - s) / 2 - 2, s + 4, s + 4, stroke=0, fill=1)
    tag(c, ax + (cw - s) / 2, ay + (ch - s) / 2, s)
    # Tray number, large, in the middle, and what it holds.
    c.setFillGray(0); c.setFont("Bold", 40)
    c.drawCentredString(x + TRAY_W / 2, y + TRAY_H / 2 - 8, str(number))
    if plants:
        c.setFont("Bold", 12)
        c.drawCentredString(x + TRAY_W / 2, y + TRAY_H / 2 - 26, "PLANTS")
    else:
        c.setFont("Sans", 11)
        label = "pots, \u2605 benchmark" if number == BENCHMARK else "pots"
        c.drawCentredString(x + TRAY_W / 2, y + TRAY_H / 2 - 26, label)
    # Slot name above, tick box and time below.
    c.setFont("Bold", 12)
    c.drawCentredString(x + TRAY_W / 2, y + TRAY_H + 6, slot)
    c.setFont("Sans", 10); c.setLineWidth(1); c.setFillGray(1)
    c.rect(x, y - 22, 14, 14, stroke=1, fill=1)
    c.setFillGray(0)
    c.drawString(x + 20, y - 19, "done")


def page(c: canvas.Canvas, m: dict) -> None:
    c.setFont("Bold", 20)
    c.drawString(MARGIN, PAGE_H - MARGIN - 14, f"Shuffle map {m['map']} of {N_MAPS}")
    if m["map"] == 0:
        c.setFont("Bold", 11)
        c.drawString(MARGIN, PAGE_H - MARGIN - 64,
                     "Map 0 is the layout at the start, read by the rig at 11:11 on 22 October (09:11 UTC). Nothing to move.")
    c.setFont("Sans", 11)
    c.drawString(MARGIN + 250, PAGE_H - MARGIN - 12, "Date ____________   Started ________   Finished ________")
    c.drawString(MARGIN, PAGE_H - MARGIN - 34,
                 "Put each tray in the slot shown. Its tag (the black square in the striped cell A1) goes in the corner")
    c.drawString(MARGIN, PAGE_H - MARGIN - 48,
                 "shown: lower left, or upper right (tray turned around). Tick each tray when it is in place.")
    top = PAGE_H - MARGIN - 92
    c.setFont("Bold", 16)
    c.drawCentredString(PAGE_W / 2, top + 6, "NORTH")
    for r, row in enumerate(ROWS):
        y = top - 22 - TRAY_H - r * (TRAY_H + GAP_Y)
        for i in range(6):
            slot = f"{row} {i + 1}"
            v = m["slots"][slot]
            tray(c, GRID_X + i * (TRAY_W + GAP_X), y, slot, v["tray"], v["a1"])
    c.setFont("Bold", 16)
    c.drawCentredString(PAGE_W / 2, MARGIN + 18, "SOUTH")
    c.setFont("Sans", 9)
    c.drawRightString(PAGE_W - MARGIN, MARGIN + 4,
                      f"Double border: PLANTS (trays 1 to 7). Single border: pots (8 to 12); the benchmark is on tray {BENCHMARK}. "
                      f"Seed {SEED}. Known answer: shuffle-maps-2026-10-22.json")


def main(out: Path) -> None:
    p = plan()
    stem = out / "shuffle-maps-2026-10-22"
    answer = stem.with_suffix(".json")
    # The known answer never changes once trays have moved: a second run only draws the PDF again.
    if answer.exists():
        if json.loads(answer.read_text())["maps"] != p["maps"]:
            sys.exit(f"REFUSED: the layouts differ from {answer}; the known answer is not changed")
    else:
        answer.write_text(json.dumps(p, indent=1))
    pdfmetrics.registerFont(TTFont("Sans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
    c = canvas.Canvas(str(stem.with_suffix(".pdf")), pagesize=landscape(A4))
    for m in p["maps"]:
        page(c, m)
        c.showPage()
    c.save()
    print(stem)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
