# Small plant network on the Hailo, issue #406 (metrology log 44)

This folder holds the scripts and small results of section 44. Large outputs (masks for every
cell, logs, the photos) are on the work machine under `~/temp.nobackup/npec-406-nn/`.

## Step 1: labels. Three label sources scored on the training cells

**Label: development check.** Written 2026-11-20 before any source was run on a cell.

### What is scored

Which of three label sources comes closest to Aaron's truth masks, so that the best of them can
label the copied photos (log 44, *Labels*):

1. **Grow from leaf cores** at the setting chosen in log 34.1: core greenness above 0.07 with
   G > R, lower cutoff soil level + 0.07 with floor -0.045, blue margin 0, no edge widening, no gap
   filling, no smoothing.
2. **SAM 3** (image model, `sam3.pt`, fp16 autocast), text prompts `plant`, `leaf` (union of all
   leaf masks) and `potato plant`. Every instance mask whose score is above the threshold is
   kept and the masks are joined. Thresholds 0.3, 0.4 and 0.5.
3. **SAM 2.1** (`sam2.1_hiera_large`, the largest checkpoint, fp16 autocast; it fits in 8 GB, see
   `notes/sam.md` on the work machine) prompted by points from grow from leaf cores. Cores are the
   pixels of the source 1 mask with greenness above 0.07 and G > R. Each connected core (8
   neighbours) is one prompt; the masks of all prompts are joined. Three prompt variants:
   - `p1m`: one positive point per core at its most interior pixel (largest distance to the core
     edge), three masks out, the one with the highest predicted IoU kept;
   - `p1s`: the same point, one mask out;
   - `p5s`: up to 5 positive points per core (the interior point and up to 4 more core pixels
     drawn at random, seed 0), one mask out.

Choosing a threshold, prompt or variant on training cells is the method (log 44).

### Which cells

The **training cells only**: production 17 and development 25 (42 in all; the manifest has 25
development training cells, not 24, see the correction in log 34.2). The list is
`../round3-grow-tuning/data/manifest_train.csv`, which holds only training rows. A first script
copies the training crops, truth masks and drafts named in that list, and nothing else, into a
staging folder on the work machine (`analysis/labels/ref/`); every later script reads only from
there and checks that every row is `train`. No test cell crop, truth or draft is loaded, looked at
or scored. The 15 outlines of section 24 are not used.

Of the 42 training cells, 30 have truths corrected by Aaron and 12 are accepted drafts, as
`../round3-grow-tuning/data/truth_index_train.csv` counts them (A01, A02 and A17 count as
corrected). *Lean:* the accepted drafts were made by grow from leaf cores (core 0.1), so that
source scores almost perfectly on them. The comparison is made mainly on the 30 corrected cells.

### How

**Score, exactly as 33 and 34**, with the scoring code of `../round3-grow-tuning/code/score363.py`
(its `group` and `stats` functions are imported, not copied). Per cell, over the whole crop (cell
plus 40 px margin): IoU with the truth mask (pixels in both / pixels in either; a cell with neither
counts as 1) and area ratio (source px / truth px; left out where the truth is empty). Reported
per rig and per group of 34 (size 1 to 5, green soil, blue mat, empty), separately for all
training cells, corrected cells and accepted drafts: mean IoU, median and pooled area ratio.

**Grow from leaf cores: what is reused.** Log 34.1 stored per-cell counts (intersection, union,
source px, truth px) for every setting on the 42 training cells in
`../round3-grow-tuning/data/oat_scores.csv`; setting 2 is core 0.07, the chosen one. Those counts
are reused as the scores of source 1. The masks themselves were not stored (the tray cache stayed
on the development rig, and the development photos were purged on 13 November). They are needed
for the SAM 2.1 points and the pictures, so they are rebuilt per crop: the stored draft (core 0.1,
equal pixel for pixel to the method at core 0.1, log 34.1 harness), joined with every connected
region of the crop above the cell's stored lower cutoff (`cut_h` in the manifest), not blue, that
holds a pixel above greenness 0.07 with G > R and does not touch the draft (a region touching
the draft was grown already; in the crop it can reach past the tray outline or into the tray tag,
which the crop does not know). A rebuilt mask is used only if its intersection,
union and pixel count equal the stored setting-2 counts exactly; a cell where they do not is
named in the results.

**Yellow.** Yellow is not plant. Where a source marks yellow leaves is noted from the picture
sheet by eye, and counted roughly: pixels a source marks that the truth does not, and whose colour
is yellow (HSV hue 24 to 60 degrees, saturation and value at least 60 of 255). A rough rule for
pointing at cells, not a measurement of yellow.

*Change after the first scoring, before anything was chosen:* the hue band above took in most of the
truths' own green (truth hue: 5th percentile 38 degrees, median 78). It was narrowed to 16 to 38
degrees with saturation at least 120 (the yellow leaves SAM 3 adds on B21 and B24 have median hue 32
to 36 degrees). Only this count changed; no score depends on it.

**Time per crop**, on the work machine (RTX 2060 SUPER 8 GB), after one warm-up crop: SAM 3 image
encoding and each prompt; SAM 2.1 image encoding and all prompts of a crop. Grow from leaf cores
runs per tray on the full photo; its time is the one of log 34.1 (Pi 5), not re-measured.

**Picture sheet.** For the 8 training cells where the sources disagree most (lowest mean IoU
between the masks of the three sources at their best setting, cells with plant only): the crop with
the truth outline, and each source's mask outlined on the crop.

**Result.** The best source by mean IoU on the corrected training cells, and its weaknesses. No
choice is made here; a recommendation with its reasons.

### Files

| File | What |
|---|---|
| `code/stage_ref.py` | Copies the training crops, truths and drafts to the staging folder |
| `code/grow_masks.py` | Rebuilds grow from leaf cores at core 0.07 per crop, checks it, writes cores and points |
| `code/sam3_run.py`, `code/sam2_run.py` | Run the two SAM models on the staged crops, write masks and times |
| `code/score_sources.py` | Scores every source, writes the tables and the picture sheets |

Run (work machine): `stage_ref.py`, `grow_masks.py` with the training env (`env.sh`);
`sam3_run.py LABELS models/sam3/sam3.pt` and `sam2_run.py LABELS models/sam2` with `env-sam`
after `models/smoke/env.sh`, one at a time; then `score_sources.py LABELS results`.
LABELS is `~/temp.nobackup/npec-406-nn/analysis/labels/` (staged cells, masks of every source,
run logs).

### Results (2026-11-20)

**What was reused for grow from leaf cores.** The per-cell counts of log 34.1, setting 2 (core 0.07)
of `../round3-grow-tuning/data/oat_scores.csv`, as its scores, and `score363.group` and
`score363.stats` for every source. The masks were not stored, so they were rebuilt per crop
(above); on all 42 training cells the rebuilt mask gives the stored intersection, union and pixel
count exactly (`results/grow_rebuild_check.csv`; 10 cells gain 1 to 1100 px over the core-0.1 draft,
A02 and A17 the most). A first rebuild that also added regions touching the draft failed on B06 and
B21 and was replaced before any scoring.

**Every setting, training cells** (mean IoU; pooled area ratio source / truth in brackets).
Corrected: production 10, development 20. Accepted drafts: 12.

| Setting | Corrected, production | Corrected, development | Corrected, both | Accepted drafts | All 42 |
|---|---|---|---|---|---|
| grow core 0.07 | 0.804 (0.975) | 0.960 (1.008) | **0.908** (1.007) | 1.000 (1.000) | 0.934 |
| SAM 3 `plant` 0.3 | 0.722 (1.140) | 0.829 (1.109) | 0.793 (1.110) | 0.757 (1.601) | 0.783 |
| SAM 3 `plant` 0.4 | 0.635 (1.132) | 0.830 (1.109) | 0.765 (1.110) | 0.666 (1.250) | 0.737 |
| SAM 3 `plant` 0.5 | 0.635 (1.132) | 0.834 (1.103) | 0.768 (1.104) | 0.666 (1.250) | 0.739 |
| SAM 3 `leaf` 0.3 | 0.693 (1.068) | 0.841 (1.038) | 0.791 (1.039) | 0.661 (1.245) | 0.754 |
| SAM 3 `leaf` 0.4 | 0.672 (1.037) | 0.850 (1.019) | 0.791 (1.019) | 0.678 (1.172) | 0.759 |
| SAM 3 `leaf` 0.5 | 0.589 (1.025) | 0.857 (1.004) | 0.768 (1.004) | 0.690 (1.031) | 0.745 |
| SAM 3 `potato plant`, any | 0 (nothing found) | 0 | 0 | 0 | 0 |
| SAM 2.1 `p1m` | 0.624 (1.061) | 0.532 (1.647) | 0.563 (1.628) | 0.669 (0.547) | 0.593 |
| SAM 2.1 `p1s` | 0.631 (1.065) | 0.533 (1.647) | 0.566 (1.628) | 0.685 (0.545) | 0.600 |
| SAM 2.1 `p5s` | 0.651 (1.104) | 0.705 (1.477) | 0.687 (1.465) | 0.735 (0.802) | 0.701 |

`potato plant` kept no mask above 0.3 on any crop. Checked on A29, B12 and B21 with no threshold: its
best score was 0.02 to 0.22, against 0.79 to 0.94 for `plant` on the same crops. Best of each source
on the corrected cells: grow core 0.07 (0.908), SAM 3 `plant` 0.3 (0.793; `leaf` 0.3 and 0.4 within
0.002), SAM 2.1 `p5s` (0.687).

**Per group, corrected cells, best setting of each source** (mean IoU / pooled ratio; full table
`results/groups.csv`):

| Rig, group | n | grow core 0.07 | SAM 3 `plant` 0.3 | SAM 3 `leaf` 0.4 | SAM 2.1 `p5s` |
|---|---|---|---|---|---|
| production, blue mat | 5 | 0.943 / 0.961 | 0.764 / 1.258 | 0.757 / 1.168 | 0.734 / 1.269 |
| production, empty (seedlings A01, A02, A17) | 3 | 0.511 / 0.751 | 0.577 / 0.824 | 0.521 / 0.689 | 0.427 / 0.449 |
| production, green soil | 1 | 0.813 / 1.229 | 0.757 / 0.757 | 0.556 / 0.556 | 0.754 / 0.756 |
| production, size 5 | 1 | 0.979 / 1.019 | 0.914 / 0.930 | 0.817 / 0.831 | 0.807 / 0.826 |
| development, empty | 2 | 1.000 / 1.000 | 0.850 / 1.104 | 0.824 / 1.094 | 0.900 / 0.942 |
| development, green soil | 3 | 0.915 / 0.912 | 0.582 / 1.002 | 0.716 / 1.074 | 0.557 / 1.697 |
| development, size 1 | 2 | 0.957 / 0.967 | 0.918 / 1.063 | 0.922 / 1.036 | 0.537 / 2.539 |
| development, size 2 | 4 | 0.961 / 1.032 | 0.915 / 1.003 | 0.890 / 0.926 | 0.741 / 2.057 |
| development, size 3 | 4 | 0.954 / 1.051 | 0.877 / 1.025 | 0.872 / 0.980 | 0.757 / 1.628 |
| development, size 4 | 2 | 0.946 / 1.044 | 0.883 / 1.087 | 0.912 / 0.947 | 0.446 / 2.706 |
| development, size 5 | 3 | 0.997 / 1.003 | 0.790 / 1.163 | 0.832 / 1.021 | 0.888 / 1.084 |

On the 12 accepted drafts grow from leaf cores scores 1.000 by construction; SAM 3 `plant` 0.3
scores 0.757 there, pulled down by B29 (0.21) and B30 (0.18), where it takes in a dead stem and soil.

**Yellow** (rough rule above; pixels marked yellow by the source and not by the truth, all 42 cells):
grow core 0.07 923 px, SAM 3 `plant` 0.3 63,645, SAM 3 `leaf` 0.4 52,104, SAM 2.1 `p5s` 52,339. By eye on
the sheets: both SAM models take whole yellow leaves (B21, B24, B13, B12); SAM 2.1 does so when a core
lies on a leaf's green tip. Grow from leaf cores takes only the greenish parts. The yellow count on
B21 is uncertain: 17,811 truth pixels pass the same rule, so its hue band overlaps yellow-green leaf.

**Time per crop**, RTX 2060 SUPER, fp16, median of 42 (range within 3%): SAM 3 encoder 0.607 s plus
0.070 s per prompt; SAM 2.1 large encoder 0.151 s plus 0.011 to 0.014 s for all prompts of a crop
(up to 0.24 s for 44 cores). Peak GPU memory: SAM 3 5,194 MiB, SAM 2.1 2,503 MiB. Grow from leaf
cores: 2.86 to 2.91 s per full production photo of 12 trays on the Pi 5 (log 34.1), not re-measured.

**Picture sheet** `results/sheet_disagree.png`: the 8 cells where the three best settings disagree
most (B28, A02, A01, B30, B04, B27, B08, B05); `results/sheet_mats_yellow.png`: A30 and A25 on blue
mats, B21 and B24 with yellow leaves. Column 1 the truth (cyan fill); each source column filled
green where source and truth agree, magenta where the source marks more (extra), yellow where it
misses truth; zoomed inset where the truth is under 2% of the crop.

**Weaknesses seen.**
- *Grow from leaf cores:* finds no plant where no pixel passes greenness 0.07 (A01, a 237 px
  seedling, IoU 0); takes in green soil and algae (A12 ratio 1.23, B05 1.18); low on production
  seedlings (empty group 0.511). Its blue-mat score here (0.943) is against truths that were made
  from its own drafts and loosened by hand; log 33.1's step at a mat stays.
- *SAM 3 `plant`:* draws edges looser than the truth on blue mats (pooled 1.26) and takes stems
  (B05, B24, B30) and whole yellow leaves; misses B28 and A02 entirely (no mask above 0.3); finds A01
  (IoU 0.87), which grow from leaf cores misses. Its masks are smooth and do not leave soil gaps
  between leaves where the truth does (B21).
- *SAM 2.1 points:* a core on soil or at a tray edge returns the whole tray or soil square (B04,
  B08, B27, B28: IoU 0.09 to 0.20, ratio up to 7.8), so it is the worst on development. It inherits
  every miss of grow from leaf cores (no core, no prompt) and adds its own.

**Recommendation, not a decision.** Grow from leaf cores at core 0.07, for the copied photos. It is
best on the corrected cells of both rigs (0.908 against 0.793) and in every group but the
production seedlings, it hardly marks yellow, and it needs no GPU. Its cost: the network learns its
errors (green soil, algae, missed seedlings), and the 15 outlines of section 24 are then the only
check of that, as log 44 says. Two things could change this and were not tried: (1) SAM 3 `plant`
joined with grow from leaf cores only where the latter finds nothing (seedlings like A01), and (2)
SAM 2.1 with prompts dropped whose mask is far larger than its core, which would remove its
whole-tray failures. Both add rules, which is what log 44 wants to move away from.

**Doubts.** 30 corrected cells, 10 of them production; production empty and green soil groups are
1 to 3 cells. The truths of corrected cells began as drafts of grow from leaf cores, so even the
corrected cells lean towards it (log 33). SAM 3 was run on crops upscaled to 1008 px (production
2.7x, development 1.6x); a labelling run on full photos would tile at another scale and may score
differently.

## Step 2: training labels for the copied full photos, by grow from leaf cores

**Label: development check.** Written 2026-11-20 before any label was made. Aaron approved grow
from leaf cores as the label source (2026-11-20). No network is trained in this step.

### Which photos

From `data/rigs/MANIFEST.csv` and the set lists `data/rigs/<rig>/lists/<set>.tsv` on the work
machine. Every copied full-size photo is listed in `results/labels_photos.csv` with its rig, set,
capture id, UTC time, UTC day, experiment, lit state, and whether it is labelled and why not.

- **Test days left out.** The reference split (`../round3-classifier/data/manifest.csv`, log 33:
  per rig, every third day of the reference set, and production 3 November in any case). Test
  days, production: 24, 27 and 30 October, 2, 3, 5 and 8 November. Development: 5 and 8 November
  (experiment 3, purged; no copied full photo is from it). **No photo taken on a production test
  day (UTC date of `taken_at`, as the manifest's `day`) is labelled**: this leaves out the whole
  steadiness run of 3 November (61 photos), capture 19440 (`spread_extra`), the 7 reference photos
  of test cells, and every spread photo of those 7 days. Days after 9 November, development
  experiment 4 and production experiments 9 to 16 hold no reference cell, so no test day; nothing
  there is left out for this reason. Each labelled photo's UTC day is recorded, so later
  cross-validation can hold out whole days.
- **Lit photos only.** Left out: the rig's own exclusion labels `lights off` and `light changing`
  (in the set lists). Experiments 9 to 16 predate the exclusion table; there the one photo the copy
  notes record as dark (capture 1620, experiment 16, 21 October 01:53 UTC, exposure 66,465 us at
  gain 4, against 3,429 to 8,366 us at gain 1 for the other 18) is left out.
- **Development steadiness run** (19 November, 61 photos 5 minutes apart): labelled, but flagged
  `steadiness` in the list, because it is the data of measure 4 for development. Whether it may be
  used in training is decided in stage 2, not here.

### Label per photo

Single-channel PNG at full resolution (9152 x 6944): **0 not plant, 1 plant, 255 ignore**.

- **Trays.** Experiment 18 and development experiment 4: the trays the rig itself read and stored
  in `tray_reading` (`placement = 'placed'` and an outline), from the rig dumps loaded into local
  SQLite files (`code/load_dump.py`). This is the app's own placement (`tray_placement.find_outlines`
  and `name_trays`, #331), as saved; it is not worked out again. Trays found from the photo
  without a tag (`found = 'photo, no tag'`) are trays the app grew too and are included. The
  calibration in effect (`capture.calibration`) is recorded per photo; labels need no mm.
- **Inside the trays:** grow from leaf cores with the app's own code,
  `npec_rig.segmentation.grow_trays` (each tray box, its outline, its own tray tag's corners from
  the photo's stored tag detections, `capture_analysis` kind `tags`). That is the setting of log
  34.1 (core 0.07 with G > R, gap 0.07, floor -0.045, blue margin 0, tag square 1.6x, white paper
  left out, no widening, filling or smoothing), plus the rule decided on 2026-11-17 (log 39): a soil
  level in the histogram's top bin is no soil level and the floor is used. The app has run with that
  rule since; without it blue-mat trays lose most of each leaf (tray 1, 8,005 against 83,003 px,
  log 39). Pixels inside any tray outline and not plant are 0, including the tag square and white
  paper.
- **Check against the rig.** Per tray, the plant pixels inside its outline are compared with the
  rig's stored `grown_plant_px`, and the soil level with `grown_soil_level`. Readings saved before
  the rule of log 39 may differ on trays whose soil level lies in the top bin; any other difference
  is reported.
- **Outside every tray: 255 (ignore)**, not 0: leaves hang over tray edges (44.1), and grow from
  leaf cores was not tuned there.
- **Production experiments 9 to 16 (no plants):** negatives. These photos were never read for
  trays and their calibrations were not copied. Trays are found with the app's
  `tray_placement.find_outlines` on the photo decoded at 1/4 (JPEG draft mode, as
  `tray_readings` does, `FINDER_FACTOR` 4), with the scale field of production calibration
  `20261022T072523939958` (the nearest copied one; the scale field only sets the expected tray
  size in pixels). Every outline found is labelled 0 inside; nothing is grown; everything else 255.
- **Development experiment 4** (tiny seedlings): included; its plant pixel total is reported on
  its own.

**Recorded per photo** (`results/labels_photos.csv`, `results/labels_trays.csv`): trays labelled,
pixels 0, 1 and 255, plant share of tray pixels, seconds (decode, grow, write) on the work machine
(not the Pi), and per tray its soil level, lower cutoff, plant pixels and the rig's stored values.
Masks: `~/temp.nobackup/npec-406-nn/analysis/labels-grow/masks/<rig>/<capture_id>.png`.

**Check sheet for Aaron.** 12 labelled photos across rigs, days and plant sizes (chosen by plant
share and day, not by look), each the whole photo downscaled and 2 tray crops zoomed, filled
translucent: green plant, grey ignore, nothing for not plant. Header in words: rig, day, number of
trays, plant share. Also the photo with the most plant pixels and one with blue mats.

### Files

| File | What |
|---|---|
| `code/load_dump.py` | Loads a rig's `rig_dump.sql` into a local SQLite file |
| `code/select_photos.py` | Lists every copied full photo with its day, set, lit state and why it is or is not labelled |
| `code/make_labels.py` | Makes the label PNGs and the per-photo and per-tray tables |
| `code/check_sheet.py` | The check sheet pictures |
| `code/grow_loose.py` | Grow from leaf cores with loose seeds for small pieces (rule 2) |
| `code/tray7_sheet.py` | Tray 7 of experiment 18 on 4 days, with tray 1, before and after the tray rule |

### Results (2026-11-20)

**Photos** (`results/labels_photos.csv`, 594 copied full photos (449 production, 145 development); labelled list `results/labels_done.csv`):

| Rig, set | Labelled | Left out: test day | Left out: lights off or changing | Other |
|---|---|---|---|---|
| production, spread (experiment 18) | 154 | 84 (28 of them also dark, 7 light changing) | 112 | |
| production, reference | 12 | 7 (the source photos of test cells) | | |
| production, steadiness 3 November | 0 | 61 | | |
| production, spread_extra (19440, 3 November) | 0 | 1 | | |
| production, variety (experiments 9 to 16) | 18 (negatives) | | | 1 dark (capture 1620) |
| development, spread (experiment 4) | 50 | | 36 | |
| development, steadiness 19 November | 59 (+2 also in spread), flagged | | | |

293 photos labelled: production 184 (166 grown, 18 negatives) over 33 UTC days, development 109
over 8 days. Production test days, with every photo of them left out: 24, 27 and 30 October, 2, 3,
5 and 8 November.

**Reproduces the rig.** 2,345 trays grown (5 to 12 per photo). On 2,278 the plant pixels inside the
outline equal the rig's stored `grown_plant_px` exactly, and the soil level and lower cutoff equal the
stored ones. The other 67 (all production) are trays with the soil level in the top bin, stored
before the rule of log 39 with the cutoff +0.115; here the floor is used, as the app does now.
Nothing else differs. Experiments 9 to 16: `find_outlines` found 12 trays on 17 photos and 13 on
one; all labelled 0 inside.

**First run: printed targets and green paper labelled plant.** With grow from leaf cores in every
tray, production held 294,970,658 plant pixels, 224,272,633 (76%) of them in trays 7 to 12: the yellow
target with the synthetic plant on tray 8 (whole sheet, median 863,147 px a photo; the green paper
"plants" make cores and the yellow sheet lies above the lower cutoff) and the green paper squares
on trays 7 and 10 (medians 289,590 and 570,929 px). Trays 1 to 6 held 68,199,469.

**Decision (Aaron, 2026-11-20), applied to every labelled photo of production experiment 18:**
- trays 9, 10, 11 and 12: every pixel inside the tray 0 (not plant): paper squares, labels,
  empty pots;
- tray 8: every pixel inside the tray 255 (ignore). It holds a synthetic plant made to look like an
  Arabidopsis (with the yellow target). Synthetic plants may be used in future tests, so the network
  must learn nothing from it either way, neither plant nor not plant;
- tray 7 (decided later the same day, from `tray7_exp18.png`, after log 17's truth showed it holds
  real plants): cells B1, C1, D1, A2, B2 and C2 hold real potato plants in pots; every other cell holds
  an empty slot, an empty pot or green calibration samples (22 October plants only; 4 November one
  green target added in D2; from 12 November many targets, D5 an empty pot). Grow from leaf cores
  over the whole tray, then 0 inside the opening of every other cell, A1 (the tag cell) included.
  Between cells a mark stays only when its connected piece (8 neighbours, within tray 7's own part
  of its outline) reaches into one of the six plant cells, so leaves overhanging from the plant cells
  stay plant and paper edges sticking out past the openings become 0 (this last part added the
  same day, after `tray7_exp18.png` showed green rims round two squares on 20 November). The cells are the app's own, as stored in `cell_reading` (20 per photo, every photo);
  D2 is the cell with the single green square on 4 November (12,270 px there, the whole drop from
  37,472 to 25,202).
- A first version of the decision (tray 7 all not plant) was applied and replaced.

*Tray numbers* are the tray tag ids, the numbers the app stores in `tray_reading.tray_id` and
shows; log 33's amendment and drafts402 (`PLANT_TRAYS`) use the same ids, and log 17 names tray 8
as the one with the plastic rosettes. Where two outlines overlap, a pixel goes to the tray whose
centre is nearer (the app's rule, `segmentation.measure_trays`). *Untagged trays* (7 of 1,691 on
production): named by the rig's own readings of the 30 photos either side (a tagged tray stored
within 150 px): 3537 tray 8, 32524 tray 10. The other 5 by eye: 23643 the target tray, tag outside
the photo (ignore); 20821 a tag-sheet tray carried in by hand, 38164 and 38284 empty black pots
(not plant); 39483 a plant tray in tray 6's place with a camera held over it (grown). Applied in
`code/make_labels.py` (`OVERRIDE`, `CELLS_KEPT`, `BY_EYE`); the whole run was made again from scratch
after each decision (all 293 PNGs checked after the second: single channel 9152 x 6944, values 0, 1
and 255 only, counts equal to the table).

*Tray 7's own part* of its outline: where it overlaps a neighbour's, a pixel nearer the neighbour's
centre is the neighbour's (as `segmentation.measure_trays`) and is not touched by the tray 7 rule.

**Plant pixels after the decisions** (label 1): 84,137,719 in all.
- Production 72,233,414 (1.67% of tray pixels): trays 1 to 6 68,199,469; tray 7 3,867,588 (grow
  from leaf cores gave 30,595,580 there); the untagged plant tray 166,357; trays 9 to 12 0 (grow
  from leaf cores gave 99,212,945 there); tray 8 0,
  ignored (was 94,464,108).
- Development experiment 4: 11,904,305 (14.1% of the total; 0.26% of tray pixels on the spread
  photos, 1.0% on the steadiness run, which is 9,876,593 of them).
- Negatives: 0.

**Time per photo** (work machine, 6 processes at once, so slower than alone): first run, grown
photos median 2.54 s (1.52 to 3.74; decode 0.91, grow 1.01, PNG write 0.33); negatives 0.73 s;
whole run 172 s. The run with the decision took 269 s (the override and a second count per tray).
Masks: 98 MB.

**Check sheet** `~/temp.nobackup/scratch/406-label-sources/labels/` (`index.html`, `labels-01.png`
to `labels-15.png`; list in `results/check_sheet_index.csv`), made again after the decision: 7
production, 1 negative, 4 development photos chosen evenly in time; 13 the photo with the most plant
pixels (37084, 15 November, blue mats); 14 the next one from the mat days (36964); 15 tray 8 with the
synthetic plant shown as ignore, beside tray 7 (2517, 22 October). Tray 7 alone, 4 days, before and after the rule: `~/temp.nobackup/scratch/406-label-sources/tray7_exp18.png` (`code/tray7_sheet.py`).

**Aaron's check of the sheet (2026-11-20).** Plant drawn solid magenta (green on green could not be
told apart), one question per tray shown close up, 26 answers in
`~/temp.nobackup/npec-406-nn/analysis/labels-grow/aaron_check.csv`. 17 trays without problems.
The other 9, in four kinds:
- *glare marked plant:* 09 and 10 (light reflected by the clear domes over unsprouted seeds on
  development), 12 tray 8 (water pooled in the empty slot C2);
- *smallest seedlings missed:* 01 tray 5 (C1 C2 C3 B2 A2 D1 D2 D3) and tray 4 (D1 C1 D5 C4 B4),
  22 October;
- *leaves partly covered:* 04 tray 3 (D1 D4 C1 C5 B1 B4), 05 tray 1 (D1, one leaf);
- *specks at cell borders:* 07 trays 5 and 6, a few pixels of blue tray and black pot.

Much of the "magenta" in 09, 10 and 12 was the rig's own lights reflected pink in the domes and the
water, part of the photo; pictures for checking now show the photo in grey under the label.

**Rule 1, glare** (`make_labels.py`, `GLARE_V`): a plant piece (8 neighbours) whose mean brightest
channel is 160 or more becomes 0. Over the 24,620 plant pieces of the 293 labels (per-piece table
`analysis/labels-grow/pieces.csv`), plants lie below 160 (the brightest, 150 to 159, 50 production
pieces), none lies from 160 to 169, and the 51 pieces from 170 up hold 12,401 pixels: 12,169 on 33
development photos (dome glare, the 2 px in C2 among them) and 232 on 3 production photos (a white
label stick among them). Removed: 12,401 px of 84,137,719 (0.015%). Picture:
`scratch/406-label-sources/glare_removed.png`, approved by Aaron.

**Rule 2, smallest seedlings** (`code/grow_loose.py`): grow from leaf cores also seeds a piece of at
most 600 px from a pixel above the core cutoff with G - R above -10 (the app needs G > R). The
missed 22 October shoots are olive in the photo, peak G - R -8 to 0, in pieces of 186 to 402 px at
the tray's lower cutoff. On the training reference cells (grow on each crop at its stored cutoff,
pooled IoU): production 0.9452 to 0.9496 (the same for limits 200 to 1000 px); development 0.9785
to 0.9685 at 600 px (moss on experiment 3's soil grows from loose seeds; the development photos
labelled are experiment 4, brown soil). Every tray is checked: with the loose seeds off the mask
equals the app's pixel for pixel. Added: 154,195 px on 202 photos (production 127,223 on 119,
development 26,972 on 83), none removed; photo 2037 18,083 to 28,059 px. Tray 5 of 2037 gained the
8 shoots Aaron listed, tray 4 2 of 5; the 3 left are very small (Aaron). Picture:
`scratch/406-label-sources/seedlings_before_after.png`.

**Partly covered leaves and border specks: left as they are.** Filling holes inside plant pieces
lowers the pooled IoU on the training reference cells (0.965 to 0.955 with every hole filled):
Aaron's truths leave the soil between leaves out. The reddish-purple leaf parts look like soil to the
rule. The network is scored against Aaron's truths, not these labels, so what these errors cost
shows in its score.

**Labels approved** (Aaron, 2026-11-20): "These are not perfect, but I think they're good enough
to move on." Plant pixels now 84,279,513.

## Step 3: training, decisions fixed before the results

**Full or half resolution** (Aaron, 2026-11-20, agreed before any cross-validation score was seen):
half resolution unless full resolution is clearly better. Clearly better: on the held-out days of the
cross-validation, full beats half for both rigs in IoU and in area error, by more than the scores
vary from fold to fold. Seedlings a few pixels across are looked at on their own: if only full
resolution finds them, that counts for it even when the overall scores are close. Time does not
decide (both well under 60 s on the Hailo; measure 6 checks it on the Pi).

**Queued after the baseline** (Aaron, 2026-11-20, from his root-segmentation U-Net, where training
on tiles without overlap segmented worse than with half-tile overlap): (1) reading a photo with
tiles at half-tile stride (128 px), predictions averaged where tiles overlap, against the
baseline's 192 px stride keeping each tile's middle; (2) training windows shifted up to half a tile
(128 px) instead of 32 px. Both scored by the same cross-validation.

**Plan of stages** (approved by Aaron, 2026-11-20, to run to the end; copy of
`scratch/406-train/plan.md`): A half and full resolution; B reading with 50% tile overlap,
averaged; C training windows shifted up to half a tile; D0 the 7 public sets prepared, ARADEEPOPSIS
yellow and brown leaf parts relabelled not plant; D1 pre-trained on 6 public sets (ARADEEPOPSIS
out), then ours; D1u unseen-species check: D1's network and the best without public data scored
on ARADEEPOPSIS, beside grow from leaf cores; D2 pre-trained on all 7, then ours; E 15 against 40
epochs; F final network on all training days; G compiled for each chip, 8-bit loss in Hailo's
emulator. Every encoder starts from ImageNet weights (MobileNetV2). Trained twice for the
unseen-species check (Aaron's choice): the check uses a network that never saw ARADEEPOPSIS, the
network used may include it. Same keep rule for every stage as for resolution. Stops before the test
cells, the steadiness runs and anything on the development rig. A picture of segmentations with
scores and a short table per stage in `scratch/406-train/` (Aaron, 2026-11-20).

**Purple (anthocyanin) leaf tissue is plant** (Aaron, 2026-11-21). Stressed potato plants also turn
purple, though none of our photos show whole purple leaves yet.
- *ARADEEPOPSIS:* the first colour rule moved whole purple rosettes to not plant, so it was replaced by
  the authors' own per-pixel classes: healthy and anthocyanin-rich count as plant; senescent
  (yellowing or dying) counts as not plant, as in our labels.
- *Our truth, cell B21:* the reddish-purple stalk and vein base of a green leaf (896 px, closed by the
  leaf blade) was not plant; it becomes plant. Picture: `scratch/406-train/purple_B21_spot.png`. The
  change was made after D1 (whose training used the old label). D2 and E were trained on the new
  label, and every earlier stage was re-scored on it from its saved predictions: only B21 moved
  (development mean IoU of stage A 0.9363 to 0.9362), and no decision changed.

**Not done.** No network trained (stage 2). The development steadiness photos are labelled but
flagged; whether they may train is for stage 2.

**Final settings: stage E** (Aaron, 2026-11-21): stage A's settings (half resolution, training shifts
±32 px, no public data, read with stride 192 keeping the middle) trained for 40 epochs instead of 15.
Any of C, D1, D2 or E lifted stage A's weakest fold (fold 4, production 24 to 27 October, seedling
A01) from 0.779 to about 0.86 mean IoU and moved the other folds by 0.02 or less; none passed the
keep test (the gain had to exceed the fold-to-fold standard deviation; E missed by 0.0013). E was
chosen because it was better than stage A in all 5 folds and adds no outside data. Truth edits from
the purple check (B12, B13, B19, B21; `analysis/labels/truth_edits/`) apply to the final network.
