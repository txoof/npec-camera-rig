# Calibration and corner tag sheets

Generated with `apriltag-gen` (`~/apriltag-gen`, commit
`61b237d49656d8a66c8dfc3863788c32d4b27b47`), which is a separate dev-time
tool — not a runtime dependency of this project. Sizes confirmed by Aaron on
2026-09-20 (see `TODO.md`'s tag ID allocation entry for the ranges: 300–449
calibration, 450–499 corner/reference).

Reproduce with:

```
uv run apriltag-gen --start 300 --end 449 -s 30mm \
    -o apriltags-36h11-30mm-a4-300-449.pdf --manifest

uv run apriltag-gen --start 450 --end 499 -s 50mm \
    -o apriltags-36h11-50mm-a4-450-499.pdf --manifest
```

Each `.manifest.json` gives every tag's page, black-square centre (mm, page
bottom-left origin, y up), and nominal design size — see apriltag-gen's
README for the format. Sizes are nominal, not measured; printed tags still
need a calliper check, same as the 29.3106 mm finding in `CLAUDE.md`.

Print at 100% / actual size and verify against the ruler on page 1 of each
PDF before using either sheet.
