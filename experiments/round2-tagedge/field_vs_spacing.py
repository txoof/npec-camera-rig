"""The calibration's fitted scale field (what the rig measures areas with) against the spacing
scale of the sheets in a photo, at each sheet's centre. Metrology log 18.1 and 18.2. Read only.

    PYTHONPATH=src python experiments/round2-tagedge/field_vs_spacing.py SHEETS.csv CAL_STEM PHOTO [X Y SPACING]

PHOTO is a photo name as in SHEETS.csv (measure.py). X Y SPACING: one extra point (for example the
green target's centre and the spacing scale of the tags beside it).
"""

import csv
import sys

from npec_rig import calibration_store


def main(sheets, stem, photo, *extra):
    field = calibration_store.load_saved_calibration(stem).scale_field
    print(f"{'slot':8} {'field px/mm':>11} {'spacing px/mm':>13} {'field/spacing':>13} {'area read high by':>17}")
    for r in csv.DictReader(open(sheets)):
        if r["photo"] != photo:
            continue
        f = field.px_per_mm(float(r["sheet_x"]), float(r["sheet_y"]))
        s = float(r["spacing_scale_px_per_mm"])
        print(f"{r['slot']:8} {f:11.4f} {s:13.4f} {f / s:13.4f} {100 * ((s / f) ** 2 - 1):+16.2f}%")
    if extra:
        x, y, s = map(float, extra)
        f = field.px_per_mm(x, y)
        print(f"{'point':8} {f:11.4f} {s:13.4f} {f / s:13.4f} {100 * ((s / f) ** 2 - 1):+16.2f}%")


if __name__ == "__main__":
    main(*sys.argv[1:])
