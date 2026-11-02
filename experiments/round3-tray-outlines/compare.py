"""Issue #328: one comparison of the finders' best runs, for the image viewer.

    python compare.py OUT_NAME run-folder [run-folder ...]

Each run folder is a `328-<name>-<version>` under harness.VIEW written by run.py. Writes
VIEW/OUT_NAME/: notes.txt (the score table as text), table.png, and one sheet per chosen still
with that still's picture from every run side by side.
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import VIEW  # noqa: E402

SHEETS = {"hard-121231_081714": "hard: 12 trays full of pots, touching in rows of six",
          "dev-143005_878937": "development: 9 untagged 2x2 trays, two north trays touching",
          "prod-143053_610338": "production: 12 tagged trays, sheets and cards on 5"}


def cell(r, key):
    s = r.get(key)
    if not s:
        return "-"
    return f"{s['worst']:g} / {s['mean']:g} of {s['of']}"


def main():
    out = VIEW / sys.argv[1]
    out.mkdir(parents=True, exist_ok=False)
    runs = []
    for name in sys.argv[2:]:
        p = VIEW / name / "summary.json"
        if p.exists():
            runs.append((name, json.loads(p.read_text())))
    head = ["run", "prod worst/mean", "dev worst/mean", "hard worst/mean", "extra per still (p/d/h)",
            "median mm (p/d/h)", "s per still"]
    rows = [head]
    for name, r in runs:
        rows.append([name.removeprefix("328-"), cell(r, "prod"), cell(r, "dev"), cell(r, "hard"),
                     " / ".join(f"{r[k]['extra_mean']:g}" if k in r else "-" for k in ("prod", "dev", "hard")),
                     " / ".join(f"{r[k]['centre_mm_median']:g}" if k in r else "-" for k in ("prod", "dev", "hard")),
                     f"{r['seconds_per_still']:g}"])
    widths = [max(len(row[i]) for row in rows) for i in range(len(head))]
    text = "\n".join("  ".join(c.ljust(w) for c, w in zip(row, widths)) for row in rows)
    (out / "notes.txt").write_text(
        "328 comparison: each method's best run. worst / mean = trays found on the worst still / on average.\n"
        "Targets: prod 12 of 12, dev 7 or more of 8, hard 12 of 12 (11 where a tag is not read).\n"
        "The time does not include FastSAM's own 15 to 20 s per still on the development rig's Hailo.\n\n" + text + "\n")
    # The table as a picture.
    lh, cw = 34, 15
    im = np.full((lh * (len(rows) + 1), cw * (sum(widths) + 2 * len(widths)) + 20, 3), 255, np.uint8)
    for i, row in enumerate(rows):
        x = 10
        for c, w in zip(row, widths):
            cv2.putText(im, c, (x, lh * (i + 1)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2 if i == 0 else 1)
            x += cw * (w + 2)
    cv2.imwrite(str(out / "table.png"), im)
    # One sheet per still: that still's picture from every run, two per row.
    for stem, title in SHEETS.items():
        tiles = []
        for name, _ in runs:
            p = VIEW / name / f"{stem}.jpg"
            if p.exists():
                tiles.append(cv2.resize(cv2.imread(str(p)), (858, 651), interpolation=cv2.INTER_AREA))
        if not tiles:
            continue
        if len(tiles) % 2:
            tiles.append(np.full_like(tiles[0], 255))
        sheet = cv2.vconcat([cv2.hconcat(tiles[i : i + 2]) for i in range(0, len(tiles), 2)])
        band = np.zeros((40, sheet.shape[1], 3), np.uint8)
        cv2.putText(band, title, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        cv2.imwrite(str(out / f"sheet-{stem}.jpg"), cv2.vconcat([band, sheet]), [cv2.IMWRITE_JPEG_QUALITY, 80])
    print(text)


if __name__ == "__main__":
    main()
