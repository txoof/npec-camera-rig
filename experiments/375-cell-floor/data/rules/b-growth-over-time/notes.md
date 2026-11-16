# b-growth-over-time: "stays and grows"

`results.csv` = variant E. Scripts: `extract.py` (each crop's mask mapped into the pot's own unit
square, 32 x 32 bins, by the homography of the 4 opening corners; checks against
`mask_px_in_opening`: mean difference 0.08 px), `rule.py` (variants A to F), `examples.py`.
Series = (rig, tray, cell); dev experiments 2 and 3 joined. Persistence counts photos, not hours.

## Variants
- A "recurring in place" (causal): green now overlapping green (1 bin tolerance) in >= 2 of the
  previous 6 photos -> plant; stays plant until 5 photos in a row with no green.
- B "recurring and growing" (causal): A plus median area of last 3 green photos > first 3.
- C "recurring, hindsight": A with 6 photos either side.
- D "recurring and growing, hindsight".
- E "recurring and rising" (causal, chosen): A plus area (as share of the opening) rank
  correlated with photo order over the last 10 photos at >= 0.5. Recurring, not rising -> possible.
- F "recurring and rising, hindsight".

## Score set (plant% / possible%)
| group | baseline | A | B | E | C (hind) | F (hind) |
|---|---|---|---|---|---|---|
| dev empty open grid | 29.4/0 | 22.1/14.7 | 20.6/16.2 | 20.6/16.2 | 25.0/11.8 | 25.0/11.8 |
| prod empty bare cell | 33.7/0 | 23.9/19.1 | 21.2/21.8 | 17.2/25.7 | 44.8/6.1 | 44.8/6.1 |
| prod empty test objects | 29.4/0 | 29.5/10.2 | 24.0/15.7 | 23.4/16.3 | 35.1/6.3 | 31.8/9.7 |
| dev seedling d0-2 | 100/0 | 33.3/66.7 | 0/100 | 0/100 | 100/0 | 87.5/12.5 |
| dev seedling d3-6 | 99.7/0 | 100/0 | 75.5/24.5 | 61.1/38.9 | 100/0 | 87.4/12.6 |
| prod seedling d0-2 | 83.3/0 | 22.2/61.1 | 0/83.3 | 0/83.3 | 83.3/0 | 83.3/0 |
| prod seedling d3-6 | 100/0 | 98.6/1.4 | 95.8/4.2 | 98.6/1.4 | 100/0 | 100/0 |

## Findings
- The premise "fringe comes and goes" does not hold here: wall fringe sits at the same wall spot
  photo after photo (examples/wrong_bare_cell_fringe_plant.png), so "recurring in place" alone
  barely separates it. Growth adds a little. Most false plants are green test objects that
  appear on a given day and stay (a step from 0 to large reads as "rising").
- Causal rules cannot call a plant on day 0 to 2 (no history yet): seedlings go to possible.
- Hindsight with a sticky "plant" spreads false plants over bare-cell series (44.8%).
- Sensitivity (E, score): K=3 cuts bare cells to 10.6% plant, seedlings d3-6 95.8%; R=3 cuts
  dev empties to 13.2%; N and RHO barely matter.
- Tune set (trays 1 to 6) holds no empty cells, so parameters are a priori small counts, not tuned.
