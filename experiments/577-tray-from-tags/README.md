# Placing each tray from its own tag (#577, metrology log 56)

Research scripts for the comparison of metrology log section 56. They import `npec_rig`; nothing
in `src/` imports them, and they are not deployed.

- `methods.py` — methods B (each tray placed from its own tag) and C (B, then each tray nudged
  onto the blue rim beside it, with blue no tray covers and overlapping trays reported as
  leftover). Method A is the app itself, `tray_placement.find_outlines` and `name_trays`.
- `compare.py STILLS_DIR INDEX` — one still through A, B and C, one JSON line out. Scoring as
  section 20: a tray matches when the centres lie within 30 mm and the outlines overlap by at
  least 0.80.
- `draw.py STILLS_DIR INDEX OUT.jpg CAPTION` — the side-by-side sheet, A left and C right,
  outlines in red and numbered (never blue or cyan: they cannot be seen on blue trays).
- `one_photo.py STILLS_DIR INDEX` — the app alone, used to measure how often the
  "fewer tags than trays" warning of #579 fires on real stills.

`STILLS_DIR` holds `meta.json` (one record per still: its path, calibration id, stored tags and
stored tray readings, pulled read only from a rig's `rig.db`) and `files/` with the photos and
`calibration/<id>.json`. Nothing here reads a rig directly.

The stills of section 56 came from three places, all read only: the `ac-testing` disk image on the
T7 backup (read with `debugfs`, not mounted), production `d6-daylight`, and development
`npec-rig-01`. The photos themselves are not in the repository.

The three decisions in `methods.py` — how far the nudge may move a tray (25 mm), the width of the
rim band it scores (9 mm) and how much leftover blue is too much (a quarter of a tray) — are
decisions, not measurements, and are recorded as such in metrology log 56.
