# Cell dataset for #375 (empty pot or seedling?)

Built 2026-11-07 on the controller (testpi-02) from read-only copies of both rigs' photos and
`rig.db`. Code checkout: `~/wt/npec-375-cell-floor` at d0ea11a. Nothing was written on either rig.

## What is here

| Path | What |
|---|---|
| `index.jsonl` | One row per crop (photo x cell), full detail (see *Fields*) |
| `index.csv` | The same rows, flattened |
| `labels.csv` | One row per cell series (rig, experiment, tray, cell): what the pot holds, the hindsight outcome, the emergence day, a note |
| `crops/<rig>/exp<N>/tray<T>/<cell>/<UTC>_rgb.png` | RGB crop: the pot opening plus a margin of half a cell side on every side (clipped at the photo edge), lossless PNG cut from the original JPEG |
| `crops/.../<UTC>_mask.png` | The ExG mask for the same crop (1-bit, white = plant) |
| `sheets/<rig>_<exp>_tray<T>.png` | Contact sheets: rows = cells, columns = the daily photo of each day plus the late photos. Mask outline magenta, pot opening red |

Raw inputs (not part of the dataset, kept for re-runs): `../raw/<rig>/experiments/...jpg` (46 full
photos, 273 MB) and `../raw/calibration/<rig>/` (the calibrations used). Scripts: `../tools/`
(`process.py` builds crops and index rows, `sheets.py`, `labels_make.py`, `finalize.py`), the
photo selection in `../work/selection.json` (`../work/select_photos.py`).

## Counts

| Rig | Experiment(s) | Photos | Trays | Cell series | Crops | Days covered |
|---|---|---|---|---|---|---|
| prod (`ac-testing`) | 18 "Potato Plants v001" | 29 (15 daily, 12 extra, 2 late) | 12 (4 x 5) | 228 | 6612 | day 0 (22 Oct) to day 15 (6 Nov) |
| dev (`npec-rig-01`) | 2 "development rig" then 3 "development 002" | 17 (8 daily, 7 extra, 2 late) | 9 (2 x 2) | 36 physical pots (72 rows: exp 2 and exp 3) | 608 | day 0 (30 Oct) to day 7 (6 Nov) |

No sampling: every plant cell (not the tag cell) of every tray in every selected photo is in.

## How photos were chosen

* Day number: `day_since_grow_start` = local (Dutch) calendar date minus the grow's start date.
  prod: start of experiment 18 (22 Oct). dev: the first photo with the 2 x 2 trays on the table
  (30 Oct 08:13 UTC, inside experiment 2); experiment 3 (from 3 Nov 12:23 UTC) continues the same
  trays and plants, so dev days run on across the two experiments. Local time is UTC+2 before
  25 Oct 01:00 UTC, UTC+1 after.
* Daily: the photo nearest 12:00 local each day, status `read`, no exclusion (lights on, not
  light changing, no visit, on the light norm), purpose `capture`.
* Extra: nearest 10:00 and 16:00 local on days 3 to 6 (dev) and 3 to 8 (prod).
* Late (hindsight): 6 Nov about 13:00 and 19:00 local, both rigs; these are the photos with the
  rig's own stored cell readings. On prod every 6 Nov photo is `light off norm` (exposure 4105
  us against about 4400 before; the blue mats arrived between day 14 and 15); they were kept
  anyway because the lights were on and they are the only photos with stored cells.

## How cells were placed and measured

The rig stores cell readings only from 6 Nov (#364), so for every photo the cells were computed
again on the controller with the project's own code: the tray outline (`tray_reading.outline`)
and tag detections (`capture_analysis`) from the rig's `rig.db`, the photo's calibration (its
twin, `calibration_for_photos`), `tray_placement.place_cells`, `segmentation.ExGSegmenter`
(ExG >= 0.1 and G > R) on the full photo, and `segmentation.measure_cells` with the tray outline.
For dev 2 x 2 trays the A1 bearing is the one stored for each tray in experiment 3 (one value
per tray over 842 photos), used for experiment 2 too.

Check against the rig: on the 4 photos with stored cells (528 cell readings) the recomputed cell
corners match exactly (0.0 px) and `plant_px` matches in 527; one dev cell differs by 3 px of
63135 (JPEG decoder versions). Masks are recomputed, not copied, so every photo uses the same rule.

## Fields (index.jsonl)

`rig`, `experiment_id`, `capture_id`, `photo_path` (relative to `/var/lib/npec-rig/` on the rig),
`taken_at_utc`, `local_time`, `day_since_grow_start`, `role` (daily, extra, late), `tray_id`,
`tray_type`, `cell`, `rgb_png`, `mask_png`, `crop_origin_px` (x, y of the crop's top left in
the full photo), `crop_size_px`, `opening_polygon_crop_px` (the 4 corners of the pot opening
(4 x 5) or pot rim (2 x 2) in crop pixels), `opening_centre_full_px`, `opening_px`,
`opening_mm2`, `mm_per_px_calibration` (at the cell centre), `mm_per_px_from_stored`
(sqrt(area_mm2 / plant_px) of the stored reading, when there is one), `calibration`,
`scale_calibration`, `recomputed` (plant_px, area_mm2, over_other_cells, plant_centre_px,
status: the current rule's reading of this photo), `stored` (the rig's own reading, 6 Nov only,
with `corners_max_diff_px`), `mask_px_in_opening`, `mask_px_in_crop` (raw mask counts with no
piece rule), `blue_fraction_in_opening` (share of opening pixels with B > R + 30 and B > G + 10),
`blue_mat` (soil pot with blue_fraction >= 0.3), `exposure_us`, `analogue_gain`,
`exposure_x_gain`, `exclusion`, `flags`, `lens_position`, `jpeg_quality`, `jpeg_chroma` (null =
the old 75, 4:2:0), `tray_placement` (found, warnings, outside_mm, tilt_deg), `a1_bearing_deg`,
and from the labels `label_outcome`, `label_contents`, `label_visible_plant` (true when the crop
is on or after the cell's `emerged_day`).

Status words follow `tray_readings._cell_status`: `plant`, `missing` (plant_px 0), `leaves over
other cells`.

## How the labels were made

By eye from the RGB crops only (no masks, no areas), by the agent that built the dataset, on
2026-11-07: tray-level views of days 0, 7 and 15, then the centre of every soil pot at 4x zoom for
days 0 to 2, and days 3 to 14 for cells with late seedlings. `outcome`: `plant` (a plant clearly
present in the late photos), `empty` (none by the end), `unclear` (none used). `emerged_day`:
the first day a seedling is clearly visible; a faint trace the day before is in the note.
`contents` says what the opening holds: `soil`, `sand-filled pot`, `bare cell (no soil)`,
`no soil, test objects`, `no pot (open tray grid)`.

| Rig | plant | empty | unclear |
|---|---|---|---|
| prod | 120 (trays 1 to 6 all 19 cells, tray 7 A2 B1 B2 C1 C2 D1) | 108 (tray 7's 13 bare cells, trays 8 to 12) | 0 |
| dev | 32 physical pots | 4 (no pot: 85 B1 B2, 86 B1, 87 B2) | 0 |

prod emergence: 112 of 120 seedlings were already visible in the first photo (`emerged_day` 0,
4 of them faint); day 1: 5 (tray 3 A4 D5, tray 4 A4 C1, tray 6 D2), day 2: tray 3 D3, day 3:
tray 6 A2, day 4: tray 4 A5. dev: every plant was a transplanted plantlet present
from the first photo.

## Known gaps and cautions

* **No empty soil pot in the dataset.** Every soil pot on prod and every sand pot on dev grew a
  plant. The empty cells are bare plastic cells, test objects, or open tray grid with no pot.
  The case the issue describes (soil only, wall fringe) is covered only by 16 pre-emergence
  crops of 8 late-emerging prod cells, and by the bare cells' walls.
* **No pre-emergence period.** prod experiment 18 started after sowing: 112 of 120 seedlings are
  already up at day 0. Earlier prod experiments (9 to 16, 12 to 21 Oct) were tag and tray tests
  with no plants, so there is no earlier grow. dev holds transplanted plantlets only.
* **Test objects read as plant.** Trays 7 to 12 on prod carry green paper squares, large green
  sheets, plastic plant models on a yellow board and tag sheets; these give most of the large
  "empty" areas (up to 23600 mm2). They are real empty cells for the question "is there a
  plant", but not fringe.
* **Blue mats** cover every prod soil pot in the late photos (day 15) and none before (day 14 and
  earlier). Lighting: prod exposure x gain fell from about 5200 (days 0 to 3) to about 4400
  (from day 4, 26 Oct); 6 Nov is `light off norm`. dev runs at about 3400 to 3800. Photo quality
  changed on 5 Nov (#362): prod late photos are JPEG 75 4:2:0, dev late photos 85 4:4:4.
* **Green algae** grow on the sand of dev tray 80 from about day 5 and raise its area.
* **Placement:** prod tray 6 on day 0 has its cells about a third of a cell south of the real
  openings (seedlings off-centre, see its sheet). dev 2 x 2 trays: the pot under a cell name
  appears to change on some days (trays 78, 81, 85, 86, 87 around days 3 to 5), so compare dev
  pots by appearance, not only by name. dev photo 11311 (day 6, 10:00) has only 8 of 9 trays
  (tag not seen), so 4 cells are missing there.
* **Extra photos are not on the contact sheets** (daily and late only); they are in the index
  and the crops.

## Size of the problem: what the current rule reads on cells with no plant

`recomputed` = the current code's reading (identical to the rig's stored reading where both
exist). Bins in mm2.

| Rig | Cells | Photos | Crops | Cell series | Area 0 | (0, 1) | [1, 10) | [10, 30) | [30, 100) | [100, 1000) | >= 1000 | Max mm2 | Stored readings (crops, with plant_px > 0) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dev | empty to the end: no pot (open tray grid) | daily and extra | 60 | 8 | 44 | 10 | 1 | 1 | 0 | 0 | 4 | 9154.8 | 0, 0 |
| dev | empty to the end: no pot (open tray grid) | late (day 15 / 7) | 8 | 4 | 4 | 2 | 0 | 0 | 0 | 0 | 2 | 7984.1 | 8, 4 |
| prod | empty to the end: bare cell (no soil) | daily and extra | 351 | 13 | 248 | 53 | 30 | 0 | 0 | 20 | 0 | 460.4 | 0, 0 |
| prod | empty to the end: bare cell (no soil) | late (day 15 / 7) | 26 | 13 | 2 | 0 | 0 | 0 | 8 | 8 | 8 | 3027.1 | 26, 24 |
| prod | empty to the end: no soil, test objects | daily and extra | 2565 | 95 | 1785 | 322 | 76 | 12 | 16 | 195 | 159 | 23599.3 | 0, 0 |
| prod | empty to the end: no soil, test objects | late (day 15 / 7) | 190 | 95 | 159 | 14 | 6 | 1 | 0 | 6 | 4 | 23352.3 | 190, 31 |
| prod | for comparison: visible seedling | day 0 | 112 | 112 | 65 | 28 | 19 | 0 | 0 | 0 | 0 | 5.4 | 0, 0 |
| prod | for comparison: visible seedling | day 1 | 117 | 117 | 22 | 29 | 64 | 1 | 1 | 0 | 0 | 41.3 | 0, 0 |
| prod | for comparison: visible seedling | day 2 | 118 | 118 | 13 | 7 | 91 | 6 | 1 | 0 | 0 | 36.1 | 0, 0 |
| prod | soil pot before its seedling emerged | all | 16 | 8 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0, 0 |

What it says:

* On bare cells with no soil (prod tray 7, days 0 to 14, blue plastic and walls) 103 of 351
  crops read above 0: 83 under 10 mm2, and 20 between 100 and 460 mm2 (green test squares and
  pots laid in the cells from about day 7). On dev open tray grids, 12 of 60 crops read under 30 mm2; the
  4 crops at 1000 mm2 and more are a neighbour's leaves over tray 87 B2.
* The 16 crops of soil pots before their seedling emerged (8 prod cells) all read 0.
* Visible seedlings on prod read about the same as the fringe: on day 0, 65 of 112 crops read 0
  and the rest under 10 mm2; day 1 median 1.3 mm2, day 2 median 3.5 mm2. A fixed floor of
  100 mm2 (`FLOORS_MM2`) would call every prod seedling empty on days 0 to 2, and 164 of the 240
  late (day 15) seedling crops are still under 100 mm2.
* Large "empty" areas on prod trays 8 to 12 (up to 23600 mm2) are the test objects (green
  squares, green sheets, plastic plant models), not fringe.

