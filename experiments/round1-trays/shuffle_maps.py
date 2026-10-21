"""Printable shuffle maps and their known answer (metrology log 15.5l).

Draws N random layouts of trays 1 to 12 in slots North 1..6 and South 1..6, each with cell A1 at
the south-west or north-east corner, from a fixed seed. Writes the known answer as JSON and the
maps as text and as an A4 PDF, 3 per page. Trays are drawn portrait; X marks the corner holding
cell A1; tray 1 carries the benchmark (star).

    python shuffle_maps.py ~/Documents

The JSON is copied to sessions/ and committed before any tray is moved.
"""
import json, random, sys
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

SEED, N, PER_PAGE = 20261020, 21, 3
SLOTS = [f"North {i}" for i in range(1, 7)] + [f"South {i}" for i in range(1, 7)]
rng = random.Random(SEED)
rounds = []
for r in range(1, N + 1):
    trays = list(range(1, 13)); rng.shuffle(trays)
    rounds.append({"round": r, "slots": {s: {"tray": t, "a1": rng.choice(["SW", "NE"])} for s, t in zip(SLOTS, trays)}})
plan = {"seed": SEED, "date": "2026-10-20",
        "generator": "python random.Random(seed): per round, shuffle trays 1-12 into North 1..6, South 1..6, then A1 corner SW or NE per slot",
        "turn": "SW: A1 and its tag at the lower left (south-west); NE: tray turned 180, A1 at the upper right",
        "benchmark": "taped to tray 1", "rounds": rounds}

W, H = 7, 7
def cell(t, c):
    blank = "│" + " " * W + "│"; lines = [blank] * H
    if c == "NE": lines[0] = "│" + " " * (W - 2) + "X │"
    else: lines[-1] = "│ X" + " " * (W - 2) + "│"
    lines[H // 2] = "│" + (f"{t}★" if t == 1 else str(t)).center(W) + "│"
    return ["┌" + "─" * W + "┐"] + lines + ["└" + "─" * W + "┘"]
def row(items):
    cells = [cell(v["tray"], v["a1"]) for v in items]
    return [" ".join(c[k] for c in cells) for k in range(H + 2)]
def drawing(rd):
    v = list(rd["slots"].values())
    return [f"Shuffle {rd['round']}", "North".center(59)] + row(v[:6]) + row(v[6:]) + ["South".center(59)]

out = Path(sys.argv[1]); stem = out / "shuffle-maps-2026-10-20"
(stem.with_suffix(".json")).write_text(json.dumps(plan, indent=1))
text = []
for rd in rounds: text += drawing(rd) + ["", ""]
(stem.with_suffix(".txt")).write_text("\n".join(text))

pdfmetrics.registerFont(TTFont("Mono", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"))
c = canvas.Canvas(str(stem.with_suffix(".pdf")), pagesize=A4)
pw, ph = A4; size = 9.2; lead = size * 1.17
for i, rd in enumerate(rounds):
    if i and i % PER_PAGE == 0: c.showPage()
    y = ph - 50 - (i % PER_PAGE) * (ph - 80) / PER_PAGE
    c.setFont("Mono", size)
    for line in drawing(rd):
        c.drawString(80, y, line); y -= lead
c.save()
print(stem)
