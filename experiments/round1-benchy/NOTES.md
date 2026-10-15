# Round 1: red and green area on the Benchy benchmark stills (issue #154)

Run on 2026-10-15. Part of CRISP-DM round 1 (#153). Round 1 bar: it runs end to end and gives a
number. Everything below is recorded, nothing is judged against a target.

## What was run

- **Stills.** 92, read only: experiment `2026-10-12_631bb6b5` (12 stills dated 15 October),
  `2026-10-15_83acd97d` (27) and `2026-10-15_44a9e96e` "tag-testing" (53: session 1 and the
  second tag round, steps from `experiments/round1/session-2026-10-15.csv` on branch
  `153-round1-benchmark`). Aaron agreed to "all 73" when there were 73; 19 more tag round 2
  stills (step names starting `R2`) were added to tag-testing during the day and are included.
  The benchmark is in all 92. Leaving the R2 rows out (73 stills) changes the rosette means by
  at most 3.5 mm² and the mean solid errors by at most 1.7 points.
- **Calibration.** All 92 were taken under calibration `20261014T111147292361`, validation
  `20261014T111253582634`, lens position 6.05 (calibration lens 6.05), no capture flags (`rig.db`).
- **Command.** `PYTHONPATH=src python3 experiments/round1-benchy/benchy.py --session-csv
  <session csv> <stills>`. About 4 s per still. Outputs: `results.csv` (one row per still),
  `overlays/<experiment>_<still>.jpg` (half size crop of the benchmark with the masks drawn).
  The overlays are not kept in the repo; the script makes them again from the stills.

## Method

1. Find the yellow base on a 1/8 size decode: the largest square yellow blob (HSV hue 15 to 35,
   saturation and value at least 120), square against its own turned rectangle so a turned base
   is found. Decode the full 64MP frame and cut out the base with a 250 px margin.
2. Region: the base's convex hull, grown by 20 px on each side. Only colour inside it counts, so
   the moss pots in the aisle, the yellow bin and the green tray tags are left out.
3. Tags: `npec_rig.tags.detect_tags` on the crop, the tag squares masked out of both colours.
4. Red: HSV hue 0 to 8 or 170 to 180, saturation at least 120, value at least 80. Each red piece
   of at least 300 px is filled (glare holes closed).
5. Green: normalised excess green (2g minus r minus b, over r plus g plus b) above 0.1, and green
   above red. The red test keeps the yellow base out. Pieces under 300 px are dropped (at most
   345 px in any still).
6. Orientation: the largest green piece is the NE rosette. The other corners follow clockwise
   seen from above (NE, SE, SW, NW). Each red and green piece goes to its nearest corner; the
   green pieces in one corner are merged into one rosette.
7. Area: pixel count divided by the square of the calibration's local scale (`ScaleField.px_per_mm`)
   at the piece's centre, the same way as `certainty_map.py`. The app has no pixel to mm
   homography; this scale field is how it maps pixels to mm. No height correction.
8. Static groups: a still is a repeat of the one before it (same experiment) when the base
   centre moved less than 20 px (about 4 mm) and the turn changed less than 1 degree.

`turn_deg` in `results.csv` and on the overlays is not the angle from upright. It is the image
angle (degrees, y down) of the NW direction, set from the NE rosette's centre, so it carries an
offset from where that rosette sits on the base and from parallax. It is used only to find
repeats and to count quarter turns.

The thresholds, margins, minimum sizes and the static limits are decisions, picked by looking at
one probe still (`2026-10-15_83acd97d` `065407_243036`). They were not tuned against the results.

## Known values used

Red solid areas and heights are from `docs/metrology-log.md` section 15.1 (branch
`153-round1-benchmark`): prism 51.6 mm² (top 15.04 mm above tray), circle 78.5 mm² (4.27 mm),
sphere 61.5 mm² (about 6.6 mm), cylinder 55.3 mm² (12.00 mm).

**Rosette diameters, corrected.** 15.1 has the SE and SW diameters swapped. Aaron, 2026-10-15:
NW 50.87, NE 67.20, **SW 38.68, SE 59.64** mm (heights unchanged). The #153 session should copy
this into 15.1. The diameters are vernier calliper estimates with no check of their accuracy,
so the upper limits made from them (a full circle of that diameter: NW 2032, NE 3547, SE 2794,
SW 1175 mm²) are estimates too.

Expected effect of height alone (0.145% of area per mm, metrology log section 4): 0.6% to 2.2%
on the solids, 3.4% to 4.7% at the rosette tops.

## Results

### Rosettes (92 stills)

| Rosette | Mean mm² | SD mm² | SD % | Min to max mm² | Widest ⌀ mm | Calliper ⌀ | Below limit |
|---|---|---|---|---|---|---|---|
| NE | 1823.8 | 26.8 | 1.5 | 1745 to 1886 | 68.0 to 72.0 | 67.20 | 92 of 92 |
| SE | 1123.6 | 20.8 | 1.9 | 1075 to 1161 | 58.9 to 63.4 | 59.64 | 92 of 92 |
| NW | 619.4 | 19.6 | 3.2 | 588 to 668 | 49.5 to 54.2 | 50.87 | 92 of 92 |
| SW | 298.2 | 10.8 | 3.6 | 262 to 326 | 41.2 to 43.6 | 38.68 | 92 of 92 |

Mean area as a share of the upper limit: NE 51%, SE 40%, NW 30%, SW 25%.

**Same position, repeated (repeatability over time).** 9 static groups of 3 to 11 stills. Within
a group, the rosette SD is 0.02% to 0.79% of its mean; the red solid SD is 0.07 to 0.83 mm².
The largest group is 11 stills on South 6 (step 6 plus the 10 "Round 2: nothing moved" stills),
SD 0.21% (NE) to 0.57% (SW).

**Across slots.** Mean rosette area per slot, range between the lowest and highest slot as a
share of the mean: NE 3.8%, SE 5.7%, NW 9.8%, SW 13.1%. North 1 reads highest for all four
rosettes; no other pattern is claimed from 4 to 21 stills per slot.

### Red solids (92 stills, all 4 found in every still, each as one piece)

| Solid | Known mm² | Mean mm² | SD mm² | Mean error | Error range |
|---|---|---|---|---|---|
| Prism | 51.6 | 71.9 | 13.5 | +39.4% | -14.7% to +83.2% |
| Circle | 78.5 | 62.3 | 4.2 | -20.7% | -32.1% to -11.5% |
| Sphere | 61.5 | 51.5 | 2.1 | -16.4% | -23.0% to -9.4% |
| Cylinder | 55.3 | 65.6 | 8.2 | +18.6% | -22.3% to +44.4% |

Mean error per slot:

| Slot | Prism | Circle | Sphere | Cylinder |
|---|---|---|---|---|
| North 1 | +47.7 | -30.3 | -18.9 | +25.1 |
| North 2 | +32.5 | -22.2 | -19.1 | +14.0 |
| North 3 | -6.8 | -18.6 | -17.5 | +0.3 |
| North 4 | +3.9 | -19.0 | -18.9 | +1.0 |
| North 5 | +23.3 | -20.3 | -18.7 | +12.8 |
| North 6 | +64.8 | -25.3 | -15.0 | +34.6 |
| South 1 | +75.5 | -25.8 | -12.6 | +25.6 |
| South 2 | +50.6 | -14.6 | -11.5 | +28.2 |
| South 3 | +13.5 | -15.4 | -15.4 | -3.7 |
| South 4 | +20.2 | -16.9 | -19.8 | -0.2 |
| South 5 | +29.8 | -23.6 | -19.5 | +5.9 |
| South 6 | +68.4 | -26.6 | -18.5 | +31.6 |

### Coverage

Stills per slot: North 1 4, North 2 9, North 3 10, North 4 4, North 5 7, North 6 7, South 1 4,
South 2 21, South 3 4, South 4 4, South 5 4, South 6 14. South 1 was seen at one turn only; every
other slot at 2 or 3 of the 4 quarter turns. 57 distinct positions (47 single stills, 10 groups).

## Visual check

Aaron looked at all 92 overlays on 2026-10-15, three of them closely (`2026-10-15_83acd97d`
`065407_243036`, `2026-10-15_44a9e96e` `082210_013542` and `082446_183501`). In every one the
rosette masks, the red solid outlines and the corner names were correct. A check by eye, one
person, one pass: it confirms what was found and named, not the areas.

## Surprises and things to look at

- **The tall solids grow toward the ends of the rows.** The prism and the cylinder read close
  to their known area in the middle slots (North 3, North 4, South 3, South 4: -6.8% to +20.2%)
  and up to +75.5% at the ends. Away from the middle the camera sees their sides as well as their
  tops (visible in the overlays). Height alone predicts only 1.7% to 2.2%.
- **The flat circle reads small everywhere.** It has no sides to show, yet reads -11.5% to
  -32.1%; the sphere reads -9.4% to -23.0%. Likely cause, not measured: the red threshold drops
  the blurred edge. The red hue cut-off is 8, the solids sit at hue 4 (median) and the base at
  27, so the cut falls inside the red, not halfway to the yellow. At about 4.85 px/mm the 10 mm
  circle is about 48 px across, so a ring 2 px wide at its edge is about 17% of its area (a
  calculation). This is the edge effect 15.1 warned about, and part of it is a threshold choice.
- **Orientation.** The first run oriented by the least round red piece (meant to be the prism).
  In 6 of 92 stills the cylinder, seen from the side, was less round, and those stills were named
  a quarter turn off. Orienting by the largest rosette fixed all 6. In the final run the least
  round red piece is in NW in 86 stills and in SW (the cylinder) in 6 (column `least_round_red_at`).
- **The SW rosette comes apart.** Its thin leaves break into 2 or 3 green pieces in 82 of 92
  stills, so the pieces are merged per corner. Before merging, it read 34.3 mm across instead of
  about 42 mm.
- **3 stills had the base turned about 18 degrees from square** (tag-testing step 4,
  `minAreaRect` 71.8 degrees) and were not found until the base test was changed to use the
  turned rectangle.
- **Tags.** A tray tag was in the crop in 5 stills (IDs 8, 10, 12), always outside the base
  region: 0 tag pixels were masked inside it, and no tag was counted as plant.
- **The white centre beads** of the rosettes are not green and are not counted. They appear as
  holes in the overlays.
- **The plastic** is a pale mint green, much paler than leaves (about RGB 151, 211, 149).
- **Base side** measured 189.9 to 194.7 mm from the scale field. Not checked with a ruler.

## What this does and does not cover

Covers the benchmark on a blue tray at tray-top height, under one calibration and one lens
position, in one day's stills. Does not cover real leaves, other lighting, or accuracy of the
rosette area (its true area is not known; only repeatability and the upper limit). The red solid
errors mix three things that this round does not separate: edge pixels, side faces seen at an
angle, and height.
