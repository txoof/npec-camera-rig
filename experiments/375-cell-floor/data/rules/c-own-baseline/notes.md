# c-own-baseline: the pot's own wall fringe as a baseline (#375)

## Method

`extract.py` resamples every crop's ExG mask into pot coordinates: the pot opening polygon is
mapped to the unit square (homography), and a 70 x 70 grid covers u, v from -0.2 to 1.2 (one
bin = 0.02 of the pot side, 4 x 4 samples per bin). `d` = distance from the pot wall as a share
of the pot side (0 at the wall, 0.5 at the centre). Only bins inside the opening count. A bin is
green when any of its samples is in the mask.

`rule.py VARIANT` gives each crop a verdict:

* "new" green = green bins not in the cell's learned fringe map;
* plant = new green in the centre zone (d >= 0.25), possible = new green only in the wall band
  (0 < d < 0.25), empty = no new green.

| Letter | Name | Fringe map |
|---|---|---|
| A | own-fringe-map | wall-band bins green in at least 1/3 of this cell's earlier photos (causal) |
| B | wall-band-only | none (no history); band green is "possible" |
| C | own-map-everywhere | any bin green in at least 1/3 of earlier photos, centre included (causal) |
| AH | own-fringe-map-hindsight | as A, learning from all other photos of the cell |

A cell series follows (rig, tray, cell); dev experiments 2 and 3 are one series.

Parameters: centre zone d >= 0.25 (geometric, a share of the pot side; tune set flat from 0.15 to
0.30, seedlings lost from 0.35); repeat share 1/3 (adaptive to the cell's own history; NOT
tunable on the tune set, which has no wall green inside soil pots; checked afterwards on the score
set at 0.1 and 0.5: possible on prod test-object cells 13.7% / 16.3%, everything else unchanged).

## What the data showed (tune set and empty cells, before choosing)

* Tune set (soil pots with seedlings): 100% of in-opening green lies at d > 0.25; the wall
  band holds no green at all. The fringe outside the opening (d < 0) is not counted anyway.
* Empty bare cells (prod tray 7): 90% of their small green lies at d < 0.04.
* **The fringe does not repeat in the same pixels.** On prod bare cells, band green appears in a
  median 21% of a cell's photos, and of 8325 band-green bins only 37 (0.4%) had been green in
  at least 1/3 of the cell's earlier photos; 48% had been green in at least one. Likely cause:
  the trays are moved round the table, so the camera sees each wall from a different angle.
  So the own-history map (A) adds almost nothing over plain geometry (B).

## Score set (variant A; baseline = any plant pixel)

| Group | n | A plant | A possible | A plant+possible | baseline plant |
|---|---|---|---|---|---|
| dev empty: open tray grid | 68 | 8.8 | 13.2 | | 29.4 |
| prod empty: bare cell | 377 | 11.7 | 18.0 | | 33.7 |
| prod empty: test objects | 2755 | 16.7 | 15.6 | | 29.4 |
| dev seedling days 0-2 | 96 | 97.9 | | 100.0 | 100.0 |
| dev seedling days 3-6 | 380 | 91.3 | | 99.7 | 99.7 |
| dev seedling days 7-13 | 64 | 85.9 | | 100.0 | 98.4 |
| prod seedling days 0-2 | 18 | 83.3 | | 83.3 | 83.3 |
| prod seedling days 3-6 / 7-13 / 14+ | 72 / 66 / 18 | 100 | | 100 | 100 |

B is the same to 1 point (prod test objects possible 16.5%). C cuts test-object plant to 10.7%
but loses seedlings (dev days 3-6 plant 87.6%, prod days 3-6 95.8%): the learned map swallows the
plant itself. AH (hindsight) moves dev open grid possible from 13.2% to 4.4%, nothing else.
Tune set A: seedlings days 0-2 69.6% (baseline 70.5%; the gap is the bin resampling).

## Failures

* `examples/wrong_testobject_plant.png`: green test objects in the centre are "plant". No
  fringe rule can fix these; they are real green things.
* `examples/wrong_dev_seedling_possible.png`: dev 2 x 2 pots, the plant sits off-centre or the
  green is a neighbour's leaf over the band: "possible", not "plant".
* `examples/wrong_seedling_day0_empty.png`: a day 0 seedling with no mask pixels at all; a mask
  problem, not a floor problem.
* prod tray 6 day 0 (placement a third of a cell off) would push seedlings into the band.

Right: `right_bare_fringe_possible.png`, `right_bare_empty.png`, `right_seedling_day0_plant.png`.

## A brand new experiment

A starts with an empty map: every photo is judged by geometry alone (B) until the cell has
photos to learn from; band green is "possible" from the first photo. It needs no plant-free
photo, so seedlings visible on day 0 do no harm: the map is restricted to the wall band and the
seedlings sit in the centre.

## Lighting

No size or colour constant is added beyond the existing ExG mask. If lighting changes so that the
fringe gets stronger, it stays in the band and stays "possible"; if the mask itself changes, every
rule built on it changes with it. The repeat share is relative to the cell's own photos.
