# d-same-photo: compare a pot with the other pots in the same photo

## Rule (variant E, "photo walls, lower-half spread", in results.csv)
For every pot, two numbers from the crop: the greenest 0.5 mm patch in the pot centre
(inner 60% of the opening side) and the greenest 0.5 mm patch in the band against the wall
(outer 80% to 100%). Green = ExG, kept where G > 0.9 R (day 0 seedlings are yellow green:
G a little below R). Each photo then sets its own fringe level from the wall bands of all its
pots: F = median, S = (median - P25) / 0.6745. A pot is "plant" when its centre peak is above
F + 1.5 S, "possible" above F + 0.75 S, else "empty". Each photo is judged alone (no earlier
or later photos).

## Parameters
| Parameter | Value | Kind | Sensitivity (tune set) |
|---|---|---|---|
| centre / wall band split | d < 0.6, 0.8 to 1.0 of the half side | geometric (pot outline) | not varied |
| patch size | 0.5 mm box | geometric (mm per px) | 1 mm box gave about the same |
| G > 0.9 R gate | 0.9 | tuned constant | no gate (upeak): day 0 63% to 42%; G > R: lower still |
| fringe level, spread | photo median, lower-half spread | adaptive | MAD (A) equals E on prod; differs on dev |
| KP (plant) | 1.5 | tuned constant | KP 2: day 0 63% to 34%, days 3 to 6 97% to 88%; KP 3: 2%, 45% |
| KQ (possible) | 0.75 | tuned constant | |

Fringe proxy on the tune set (no empty pots exist there): tune pots' own wall bands, days 0 to
6, judged as if they were a centre: 1% plant, 2% possible.

## Score set (plant % / possible %)
| Group | baseline now | floor 100 | A photo walls MAD | B tray walls | C photo cores | E (chosen) | F lowest quarter |
|---|---|---|---|---|---|---|---|
| dev empty open grid | 29.4 | 8.8 | 11.8 / 1.5 | 1.5 / 1.5 | 1.5 / 0 | 11.8 / 1.5 | 29.4 / 11.8 |
| prod empty bare cell | 33.7 | 9.5 | 11.9 / 2.9 | 11.9 / 0.3 | 0 / 1.1 | 12.2 / 3.4 | 14.3 / 10.9 |
| prod empty test objects | 29.4 | 13.2 | 17.9 / 9.9 | 15.2 / 3.9 | 3.6 / 8.5 | 18.8 / 11.4 | 23.8 / 29.7 |
| dev seedling d0-2 | 100 | 95.8 | 100 / 0 | 64.6 / 9.4 | 6.2 / 13.5 | 100 / 0 | 100 / 0 |
| dev seedling d3-6 | 99.7 | 94.7 | 66.6 / 13.7 | 55.8 / 6.1 | 6.8 / 16.3 | 70.0 / 11.1 | 96.8 / 0.3 |
| dev seedling d7-13 | 98.4 | 96.9 | 0 / 14.1 | 54.7 / 4.7 | 9.4 / 15.6 | 0 / 1.6 | 90.6 / 1.6 |
| prod seedling d0-2 | 83.3 | 0 | 94.4 / 0 | 66.7 / 22.2 | 0 / 38.9 | 94.4 / 0 | 94.4 / 0 |
| prod seedling d3-6 | 100 | 0 | 100 / 0 | 84.7 / 15.3 | 0 / 12.5 | 100 / 0 | 100 / 0 |
| prod seedling d7-13 | 100 | 0 | 100 / 0 | 100 / 0 | 0 / 12.1 | 100 / 0 | 100 / 0 |
| prod seedling d14+ (mats) | 100 | 22.2 | 100 / 0 | 100 / 0 | 0 / 0 | 100 / 0 | 100 / 0 |

Variant D (E plus "plant when half the centre is masked") is in results_D.csv: dev d7-13 7.8%.
Parameters were chosen on the tune set; after seeing the E score table, variant F was added to
address the dev failure, so F's score is not a clean held-out result.

## What the examples show
* `4_`, `5_`: almost all prod "empty" plants are green paper squares in bare cells (real green
  objects, not fringe). No colour rule can reject them.
* `7_`: E's dev empty plants are a neighbour's leaves over tray 87 B2. F also flags two open
  grids with no mask at all: its spread (P25 to P5) is so tight that noise passes.
* `6_`: E fails on dev late photos: leaves cover more than half of all wall bands, the photo's
  fringe level becomes leaf green, and plants no longer stand apart. This is the "every pot
  holds a plant" case, and the wall bands stop being a reference too.
* `2_`: missed day 0 seedlings are a few faint pixels; tray 6 day 0 cells sit off the pots.
* `3_`: day 4 exposure drop and day 15 blue mats: no change (tune plant rate day 3 94%, day 4
  99%, day 15 100%).

## Lighting
F and S move with the photo, so a uniform brightness or colour shift moves the reference with
the pots. Fixed: the 0.9 R gate and KP, KQ (in units of the photo's spread).
