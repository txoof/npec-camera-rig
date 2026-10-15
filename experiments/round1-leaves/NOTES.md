# Round 1: real leaves of known area on the trays (issue #162)

Run on 2026-10-15. Round 1 bar: it runs end to end and gives a number. Recorded, not judged.
Method written at 11:53 UTC, before the photos (`~/scratch/round1-leaves-method.md`, copied into
`docs/metrology-log.md` section 15.5b).

## Data

- **Leaves.** 3 garden leaves, labelled on the underside by Aaron: L001, L002, L003.
- **Scans.** Epson flatbed, 300 dpi, each leaf with a 180 mm scale and 5 x 30 mm AprilTags:
  before the photos 11:49 to 11:51 UTC (`L001.jpg` to `L003.jpg`), after 12:05 to 12:07 UTC
  (`L001_after.jpg` to `L003_after.jpg`). Kept in `scans/` here and, read only, in
  `/var/lib/npec-rig/scans/2026-10-15_leaves/`, both with `SHA256SUMS`. Scan times
  (`scans/scan_times.csv`) are the files' modification times on the Pi, in UTC.
- **Stills.** 32, taken by Aaron, 11:54 to 12:03 UTC, experiment `2026-10-15_44a9e96e`,
  calibration `20261014T111147292361`. Positions recorded by Aaron:
  - stills 1 to 10: blue trays, the 3 leaves in a line, one slot per still along South 1 to
    South 6 then North 6 to North 1. Still k: L001 on the k-th slot of that path, L002 on the
    next, L003 on the one after. (Aaron recalled 12 stills; there are 10, ending on North 3,
    North 2, North 1.)
  - stills 11 to 21: the 3 leaves together on a black sheet, South 1 to South 6, then North 6
    to North 1, skipping North 3 (the benchmark, not moved). 003 north west, 001 north east,
    002 south.
  - stills 22 to 32: the same, leaves turned over (underside up).
- Scripts: `scan_area.py` (scan areas, `scan_areas.csv`), `leaves.py` (rig areas,
  `results.csv`). Overlays are made by the scripts and not committed.

## Method

**Known area (scan).** Leaf = the round 1 green test (excess green above 0.1, green above red),
largest piece; holes stay holes. Scale measured from the 5 tags in each scan, separately along
the scanner's two axes: 11.643 to 11.663 px/mm across, 11.777 to 11.790 px/mm along (the axes
differ by 1.1%; the nominal 300 dpi is 11.811). Spread of the per-tag scale: 0.46% to 0.61%.

| Leaf | Before (mm²) | After (mm²) | Change |
|---|---|---|---|
| L001 | 7331.3 | 6779.9 | -7.5% |
| L002 | 7448.4 | 7081.0 | -4.9% |
| L003 | 7898.5 | 7532.8 | -4.6% |

The leaves shrank 4.6% to 7.5% in the 16 minutes between scans (visible in the scan overlays).
The known area at each photo is read off a straight line between the two scans. That line is an
assumption: the shrinking may not be steady, so each result is also given against the before
and the after scan (`err_pct_vs_before`, `err_pct_vs_after`).

**Rig area.** The round 1 green test unchanged, on the trays only: the two rows across the full
image width (the aisle with the moss pots and the floor left out), the benchmark's base and a
small margin left out. Pieces of one leaf are joined across gaps up to 4 px (on a 1/8 decode)
for grouping; pale midribs split leaves otherwise. A piece joins a leaf only within about 65 mm
of it. Tags masked from `detect_tags`. Area through the calibration scale field at the leaf's
centre, no height correction. On the black sheet the 3 leaves lie almost touching and cannot be
split by colour, so they are measured together against the sum of their known areas.

**Identity.** From Aaron's record. Cross-check: a shape match against the scans
(`cv2.matchShapes`) agrees in 26 of 30 blue tray readings; the 4 that differ are stills 7 and 8,
where it swaps two leaves, and Aaron's record gives the smaller errors there. Shape matching is
not reliable enough to replace the record.

## Results

Error = rig area against the known area at the photo, in %.

**Blue trays, each leaf on its own** (27 readings, leaving out 3 where the leaf lay against the
benchmark): mean -2.49%, SD 3.15, range -9.10% to +3.43%. Against the before scan: mean -4.44%;
against the after scan: mean +1.33%.

| Leaf | n | Mean | SD | Range |
|---|---|---|---|---|
| L001 | 9 | -3.07% | 2.29 | -7.03% to +0.59% |
| L002 | 9 | -4.58% | 2.67 | -9.10% to -0.96% |
| L003 | 9 | +0.17% | 2.57 | -3.82% to +3.43% |

Against the benchmark (North 3, stills 8 to 10): -5.42% (L003), -10.4% (L002), -15.89% (L001).
The benchmark's base is left out, and part of the leaf lay on or next to it (visible in the
overlays).

**Black sheet, 3 leaves together** (11 slots each):

| Side up | Mean | SD | Range | Against before | Against after |
|---|---|---|---|---|---|
| Top | +2.99% | 2.26 | -0.02% to +6.90% | -0.54% | +5.43% |
| Underside | +2.45% | 2.47 | -1.19% to +7.05% | -2.11% | +3.77% |

Per slot (top / underside): South 1 +1.6 / +0.4, South 2 +1.2 / -1.2, South 3 0.0 / -0.3, South 4
+1.8 / +1.5, South 5 +4.6 / +3.2, South 6 +6.8 / +5.2, North 6 +6.9 / +7.1, North 5 +3.3 / +2.6,
North 4 +1.7 / +1.3, North 2 +1.9 / +2.8, North 1 +3.1 / +4.5.

**Against the validation bands** (session `20261014T111253582634`, in force for all 32 stills;
band = p95 of |tag area error| per slot, 1.26% to 2.55%). Nothing is corrected.
`within_band`: |error| at most the slot's band. `band_overlaps_scans`: the band overlaps the range
from "against the before scan" to "against the after scan", which allows for the unknown shrink.

| Readings | n | Within band | Band overlaps the scan range |
|---|---|---|---|
| Blue trays, not at the benchmark | 27 | 8 | 22 |
| Blue trays, against the benchmark | 3 | 0 | 0 |
| Black sheet, top side | 11 | 5 | 9 |
| Black sheet, underside | 11 | 5 | 10 |

A band holds 95% of tag readings, so about 26 of 27 would fall inside it if it covered these
leaves. It does not settle the question: the uncertainty in the known area (the 4.6% to 7.5%
shrink between scans) is larger than the bands themselves. The 5 blue readings outside even the
scan range are L001 in still 2, L002 in stills 4, 8 and 10, and L003 in still 5.

## Surprises and things to look at

- **Blue reads small, black reads large.** The same leaves read 2.5% small on blue trays and
  2.5% to 3.0% large on the black sheet. The black sheet lifted the leaves about 3 to 10 mm above
  the tray top (Aaron's estimate, not measured), which at 0.145% of area per mm adds about 0.4% to
  1.5%: part of the 5 to 5.5 point gap. The rest is not measured. One possibility: at a leaf's edge a
  pixel mixes leaf with background, and a green and blue mix fails the green test while a green
  and black mix passes it.
- **The east end reads large on black.** South 5, South 6 and North 6 read +3.2% to +7.1%, the
  rest -1.2% to +4.5%. Not seen as clearly on the blue trays.
- **L002 reads smaller in its later stills.** -1.0% to -5.8% in stills 1 to 6; -4.3%, -8.3% and
  -9.1% in stills 7, 8 and 10 (still 9 lay against the benchmark). A leaf that curls as it dries shows less area from above than flat on the
  scanner glass. The scanner flattens the leaf; the trays do not.
- **Midribs and stems.** Pale midribs fail the green test, on the scans and in the stills alike.
- **First run cut the black sheet at the row box ends** (South 1 and South 6, a straight cut
  visible in the overlays). Fixed by using the full image width for each row; results above are
  after the fix.

## What this does and does not cover

Covers 3 leaves of one garden plant, flat or nearly flat on the tray top, one day, one
calibration, one lens position, about 10 minutes of photos. Does not cover leaves standing above
the tray (real plants), other plants, or overlapping leaves. The known areas depend on the
straight-line shrink assumption: the true error lies somewhere between the "against before" and
"against after" columns.
