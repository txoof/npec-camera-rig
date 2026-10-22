# Growth trays: size, configurations, tags and layout

Everything physical about the growth trays in one place, for anyone finding, splitting or naming
trays in the rig's photos. Measurements and their method are in `docs/metrology-log.md` section
15.5c; this page collects them. Started 2026-10-16 (issue #164). A value that is a decision or a
statement by Aaron, not a measurement, says so.

## Size (one 4 x 5 tray, measured by Aaron, 2026-10-15)

Number of readings per value not recorded.

| What | Value | Instrument |
|---|---|---|
| Outside size, lip included, east-west (short side, tray in portrait) | 305.0 mm | tape measure |
| Outside size, lip included, north-south (long side) | 366.0 mm | tape measure |
| Height of the grid surface (cell openings) above the gray table | 99.89 mm | tape measure |
| Height of the top of the lip above the gray table | 104.78 mm | tape measure |
| Cell opening, both directions | 59.5 mm | callipers |
| Wall between cells | 10.1 to 10.3 mm | callipers |
| Outer grid wall at the lip, on the edges running north-south (west, east) | 13 mm | callipers |
| Outer grid wall at the lip, on the edges running east-west (north, south) | 11 mm | callipers |

- Cells are not all the same size and the wall width varies a little (Aaron).
- The grid sits wholly inside the lip (Aaron). Derived, not measured: cell centres about 69.7 mm
  apart; the lip reaches about 5.2 mm beyond the grid on each side east-west, 2.9 mm north-south.
- The lip is 4.89 mm above the grid surface, so in the photo it reads about 0.35% larger in length
  than something at grid height (0.145% of area per mm, `docs/metrology-log.md` section 4).
- In the photos (calibration `20261014T111147292361`, 4.83 to 4.89 px/mm) a tray is about
  1,480 x 1,780 px at full resolution.
- **From the photos, not the tape measure:** the blue outline of a tray standing clear reads
  306.0 x 373.6 mm (SD 1.4 and 1.3 mm, 66 sightings of 14 positions); north-south is 7.6 mm (2%)
  longer than the tape measure, not explained (metrology log 15.5c).

## Configurations (Aaron, 2026-10-16)

| Configuration | Cells | Where the tray tag sits | Grid spacing |
|---|---|---|---|
| 4 x 5 | columns A to D, rows 1 to 5 | in cell A1, roughly centred, any rotation; A1 holds no plant (Aaron, 2026-10-21). Until then: outside the tray at the A1 corner, never inside a cell (Aaron, 2026-10-17) | measured above |
| 4 x 4 | 16 | in the middle of the tray (Aaron, 2026-10-21) | not yet measured |
| 1 x 1 | one large well | bolted to a corner of the tray, the whole tag inside the tray's footprint (Aaron, 2026-10-21) | not yet measured |

All three use the same outer tray and the same colours. Black trays have their tag (the disc) in a
pot (Aaron, 2026-10-21).

- **A1 is the south-west corner** when the tray is seen from above in portrait (4 x 5, Aaron).
- Wells: from the week of 2026-10-19 the wells hold black pots; later soil and plants (green,
  black and brown). The cell grid stays visible.

## Tags

- Family 36h11. Tray IDs 0 to 299 (`src/npec_rig/tags.py`).
- **Final tray tags:** about 20 mm, 3D printed, on the outside edge; hard clearance at the tray side
  27 mm; 30 mm edge tags ruled out (Aaron, 2026-10-15, metrology log 15.3a).
- **From the week of 2026-10-19:** the green 30 mm tags go; every tray tag is a 20 mm paper tag at
  A1 (statement by Aaron, 2026-10-15); on 4 x 5 trays outside the tray at the A1 corner (Aaron,
  2026-10-17).
- **4 x 5 tray tags from 2026-10-21:** the 3D-printed default is the `lip_round` tag, a 40 mm tag
  on a 60.5 mm plate with a lip (version 2's 4x5 design, `hardware/tray_tags/`, RV1.19). It is
  larger than the 27 mm side clearance above; Aaron decided the 27 mm limit no longer applies to
  it (2026-10-21). The 20 mm `tab` tag is still available as a style.
- Every printed tag sheet is measured with callipers (CLAUDE.md, *Facts not to rediscover*).
- 20 mm tags need the detector's finer bit sampling (setting C, #156: 171 of 171 found against 121
  of 171).

## Layout in the chamber (Aaron, 2026-10-15)

- **12 trays:** always portrait (short edges north and south), two rows, North 1 to 6 and South 1
  to 6, each tray at 0 or 180 degrees in its slot. So A1 is at the south-west or north-east corner.
- **Fewer trays:** a tray can be at any angle.
- **Gaps cannot be relied on.** Researchers are asked to leave gaps and will not reliably do so;
  even "with gaps" the trays touch in places (15 October photos).

## Finding trays in a photo (round 1 result, issue #164)

- Blue thresholding cannot split touching trays (10% of trays on the gap set).
- FastSAM on the Hailo-8, on 2-tray tiles placed from the tags plus a fallback search around
  missed trays, got 2085 of 2112 trays right on 176 stills (98.7%); all failures were the tray
  carrying the benchmark, its tag on the seam with a neighbour. Method and numbers: metrology log
  15.5c; scripts in `experiments/round1-trays/`.

## Not yet known

- Grid spacing of the 4 x 4 and 1 x 1 configurations.
- How many trays of each configuration exist, and whether 4 x 4 and 1 x 1 are used in the 12-tray
  layout or with fewer trays.
- Whether FastSAM finds a 1 x 1 tray (no cell pattern) and trays with pots, soil and plants.
- Number of readings behind each tray measurement; the tray size of a second tray (one tray
  measured).
