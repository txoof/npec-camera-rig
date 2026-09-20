# Calibration and corner tag sheets

Generated with `apriltag-gen`, now at <https://github.com/txoof/apriltag-gen>
(commit `34d076f864ed7c63d1c45e13e84eb6f428b9a2eb`), which is a separate
dev-time tool — not a runtime dependency of this project. Sizes confirmed by
Aaron on 2026-09-20 (see `TODO.md`'s tag ID allocation entry for the ranges:
300–449 calibration, 450–499 corner/reference).

Each PDF carries a `--title` on every page ("Calibration Sheet" /
"Corner / Reference Sheet") — cosmetic only, filenames are unchanged from
the previous version.

Reproduce with:

```
uv run apriltag-gen --start 300 --end 449 -s 30mm --title "Calibration Sheet" \
    -o apriltags-36h11-30mm-a4-300-449.pdf --manifest

uv run apriltag-gen --start 450 --end 499 -s 50mm --title "Corner / Reference Sheet" \
    -o apriltags-36h11-50mm-a4-450-499.pdf --manifest
```

Each `.manifest.json` gives every tag's page, black-square centre (mm, page
bottom-left origin, y up), and nominal design size — see apriltag-gen's
README for the format. Sizes are nominal, not measured; printed tags still
need a calliper check, same as the 29.3106 mm finding in `CLAUDE.md`.

Print at 100% / actual size and verify against the ruler on page 1 of each
PDF before using either sheet.
