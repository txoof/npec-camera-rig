# a-centre-core: "a solid part away from the walls"

Single photo only (no earlier or later photos). Uses only the mask crop and the pot opening polygon.

Scripts: `features.py` (per crop: mask pixels in inner windows, erosion depth, per-piece size,
depth and share inside each window; reads no labels) then `rules.py <letter> [k=v ...]`.
`montage.py` makes the examples. `results.csv` = variant B.

## Variants

* **A, "centre window, any green"**: any mask pixel inside the opening shrunk to S of its linear size
  about its centre = plant; green only nearer the walls = possible.
* **B, "solid piece centred" (chosen)**: a mask piece (8-connected) that survives one 3x3 erosion
  (DEPTH 2, so at least a 3x3 block of plant pixels) with at least half its pixels (SHARE 0.5) inside
  the centre window (S 0.5) = plant. Green in the window that fails that = possible. Green only
  near the walls = empty.
* **C, "core scaled to the opening"**: a pixel in the window that survives erosion by 1% of the
  opening side. Too strict: prod seedling masks are 8 to 40 px even on days 7 to 13.
* **D, "B or any thick piece"**: B plus any piece at least 2% of the opening side thick anywhere.
  Made after seeing B's dev misses on the score set, so not a clean test.

## Parameters (B)

| Parameter | Value | Kind | Sensitivity |
|---|---|---|---|
| S, centre window | 0.5 of the opening's linear size | geometric | tune set: no change from 0.4 to 0.8 (seedlings are central). Chosen a priori |
| SHARE | 0.5 of a piece inside the window | geometric | 0.3 gave the same tune rows |
| DEPTH | survives 1 erosion (3x3 block) | tuned constant in pixels (about 0.6 mm here) | depth 1 = rule A; depth 2 moves 11% of day 0 to 2 seedlings to possible |

## Score set (prod trays 7 to 12, all dev)

| Group | n | baseline plant | A (S 0.5) plant / poss | **B plant / poss** | C plant / poss | D plant / poss |
|---|---|---|---|---|---|---|
| dev empty: open tray grid | 68 | 29.4 | 8.8 / 22.1 | **1.5 / 7.4** | 8.8 / 0.0 | 19.1 / 0.0 |
| prod empty: bare cell | 377 | 33.7 | 11.9 / 21.2 | **10.3 / 1.6** | 11.7 / 0.3 | 11.7 / 0.3 |
| prod empty: test objects | 2755 | 29.4 | 17.0 / 18.3 | **7.3 / 9.7** | 15.5 / 1.4 | 22.2 / 0.9 |
| dev seedling days 0-2 | 96 | 100 | 96.9 / 3.1 | **77.1 / 19.8** | 92.7 / 4.2 | 100 / 0 |
| dev seedling days 3-6 | 380 | 99.7 | 90.8 / 9.2 | **72.1 / 18.7** | 85.5 / 5.3 | 98.9 / 0.3 |
| dev seedling days 7-13 | 64 | 98.4 | 87.5 / 12.5 | **73.4 / 14.1** | 84.4 / 3.1 | 100 / 0 |
| prod seedling days 0-2 | 18 | 83.3 | 83.3 / 0 | **72.2 / 11.1** | 33.3 / 50.0 | 72.2 / 11.1 |
| prod seedling days 3-6 | 72 | 100 | 100 / 0 | **98.6 / 1.4** | 61.1 / 38.9 | 98.6 / 1.4 |
| prod seedling days 7-13 | 66 | 100 | 100 / 0 | **100 / 0** | 90.9 / 9.1 | 100 / 0 |
| prod seedling days 14+ | 18 | 100 | 100 / 0 | **100 / 0** | 100 / 0 | 100 / 0 |

Tune set (prod trays 1 to 6), B: seedlings days 0-2 59.6 plant + 10.9 possible = 70.5 (baseline 70.5;
the other 29.5% have no mask pixels at all), days 3-6 87.0 + 7.8, days 7-13 89.4 + 7.3, 14+ 97.4 + 2.0;
the 16 pre-emergence crops all empty.

## Where it fails

* Green objects placed in the middle of a pot read plant: green squares in bare cells
  (`examples/wrong_bare_plant.png`), test objects (`wrong_testobj_plant.png`). No geometric rule
  separates a centred green square from a plant.
* Large dev plants whose leaves lie mostly outside the centre window, or that sit off-centre or under
  the wrong cell name, read possible (`wrong_dev_possible.png`). D fixes these but lets a neighbour's
  leaves over an open grid read plant (dev empty 19%).
* Seedlings the mask misses entirely read empty (`wrong_seedling_empty.png`): a segmentation limit,
  no piece rule can recover them.
* Placement errors (prod tray 6 day 0, a third of a cell off) push real seedlings out of the window.
* Right: `right_bare_fringe_empty.png` (wall fringe on bare cells, empty), `right_seedling_plant.png`.

## If lighting changed

The rule has no area or colour threshold of its own: the window and share are fractions of the pot
opening, and the depth is a 3x3 block. A lighting change acts only through the green mask: if the
mask grows more fringe, the fringe still sits at the walls and stays empty; if the mask thins the
seedlings, more of them fall from plant to possible (DEPTH 2 is the part most exposed). The 3x3
block is in pixels, so a different camera height or resolution would need it rescaled by mm per px.
