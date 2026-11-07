# e-colour-shape: what each green piece looks like (#375)

## Rule (variant A, "blue tint", the one in results.csv)
Split the mask inside the pot opening into connected pieces. A piece whose mean blue is at least
as strong as its mean green (B/G >= 1) is tray plastic seen through the green threshold (wall
fringe, colour edge, reflection), not a leaf. The crop is `plant` if any piece is left, else
`empty`. Uses only the photo itself (no earlier or later photos).

Parameter: B/G = 1, a physical boundary (equal channels), not tuned. Sensitivity: any value from
0.9 to 1.2 gives the same tune-set seedling result (70.5% days 0 to 2, 96.1% later) and on the
score set bare cells stay at 11.7%; test-object cells move from 24.5% (0.9) to 28.5% (1.2).

## Features tried (pieces.csv, from features.py)
area (fraction of opening), elongation (axis ratio), distance to opening edge (fraction of the
side), ExG, ExG relative to the ring of pixels round the piece, ExG z-score against the
opening's own soil (median and MAD), hue, saturation, brightness relative to soil, B/G, share of
blue pixels in the ring round the piece.

Tune set (prod trays 1 to 6, 11825 pieces): pieces touching the wall band (outer 4% of the
side, 37 pieces) have median hue 99 (OpenCV 0 to 180, blue-green), B/G 1.23, ring all blue;
pieces away from the wall have hue 40 (yellow-green), B/G 0.75, no blue ring. Elongation does
not separate them (medians 1.5 and 1.5): the fringe in these photos is mostly small round blobs,
not long slivers. ExG contrast also does not separate them (fringe is as strong as leaves on the
ExG scale). Plot: `examples/scatter_blue_green_vs_elongation.png`.

## Variants (score set: prod trays 7 to 12 and all dev)
| Group | baseline | floor 100 mm2 | A blue tint | B blue tint + wall sliver, rim-only = possible | C wall sliver shape only |
|---|---|---|---|---|---|
| dev empty open grid, plant / possible | 29.4 / 0 | 8.8 | 19.1 / 0 | 17.6 / 1.5 | 29.4 / 0 |
| prod empty bare cell | 33.7 / 0 | 9.5 | 11.7 / 0 | 10.9 / 0.8 | 19.6 / 0 |
| prod empty test objects | 29.4 / 0 | 13.2 | 26.5 / 0 | 9.6 / 12.3 | 29.3 / 0 |
| prod seedling days 0-2, plant (+possible) | 83.3 | 0 | 83.3 | 83.3 | 83.3 |
| prod seedling days 3-14+ | 100 | 0 to 22 | 100 | 100 | 100 |
| dev seedling days 0-2 / 3-6 / 7-13 | 100 / 99.7 / 98.4 | 96 / 95 / 97 | 100 / 100 / 100 | 99+1 / 95.8+3.2 / 89.1+6.2 | 100 / 98.9 / 95.3 |
Tune set: all three variants equal the baseline on seedlings (70.5% days 0 to 2; the other
29.5% have no mask pixels at all, so no piece rule can find them).

## Where it fails
* Real green objects are green: test squares, paper stars, sheets (`wrong_bare_cell_still_plant.png`,
  `wrong_test_object_plant.png`) and a neighbour's leaves over dev tray 87 B2. Of the 57 false
  `plant` crops on bare cells and open grid, 49 are such objects of 100 mm2 or more; the other 8 are
  late prod photos (6 Nov, JPEG 75 4:2:0, lights off norm).
* Seedlings the threshold never caught (`wrong_seedling_day0_no_mask.png`): a piece rule cannot
  add pixels.
* `wrong_seedling_day3_empty.png`: the seedling is not in the mask; the baseline's `plant` came
  from a blue blob at the corner, which this rule correctly drops.

## Lighting
B/G is a ratio, so brightness and exposure changes cancel. A change in light colour (a warmer or
bluer lamp, a white balance change) shifts B/G of everything; leaves sit at 0.6 to 0.9 and fringe
at 1.2 to 1.6 here, so a shift of about 0.2 is tolerated. A redder light would push fringe below 1.
An adaptive form would compare each piece's B/G with the B/G of the tray plastic in the same crop.
