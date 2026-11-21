# Stage F: the final network, trained on every training day

Written by `final_fg.py stage_f` (2026-11-21 11:55 UTC). Development check. Training cells only (42: production 17, development 25); no test cell was opened. Half resolution, threshold probability 0.5, float32.

## 1. The purple-check truth edit

Aaron decided that purple stalk tissue is plant. After stage E was trained, three more development truths were edited (B12, B13, B19; B21 was edited earlier and was already in E's training). Record: `analysis/labels/truth_edits/`.

- Half-resolution truth cells (`cache/s2/truth_cells.npz`) rebuilt from the truth files; the old file is kept as `truth_cells_before_purple_check.npz`. Cells that changed: B12 (377 target px changed, plant share 43389 -> 43707 px); B13 (211 target px changed, plant share 11944 -> 12090 px); B19 (242 target px changed, plant share 23456 -> 23659 px). The other 39 cells are identical.
- Every earlier run re-scored from its saved predictions, with no network run and no retraining (35 score files; the old ones kept as `scores*_before_purple_check.csv`). Cells whose scores changed: B12, B13, B19. Grow from leaf cores was scored from its masks.
- Stage E's fold models were trained with the old B12, B13 and B19 labels. The final network uses the new ones.

Development cells, before and after the edit (production cells did not change):

| Method | Mean IoU (0 to 1, higher is better), before | Mean IoU (0 to 1, higher is better), after | Mean area error (%, lower is better), before | Mean area error (%, lower is better), after | Pooled IoU (0 to 1, higher is better), before | Pooled IoU (0 to 1, higher is better), after |
|---|---|---|---|---|---|---|
| grow from leaf cores | 0.9677 | 0.9666 | 2.90 | 2.98 | 0.9761 | 0.9732 |
| stage A (15 epochs), half resolution | 0.9362 | 0.9353 | 3.65 | 3.70 | 0.9278 | 0.9261 |
| stage E (40 epochs), the final settings | 0.9402 | 0.9394 | 3.28 | 3.31 | 0.9328 | 0.9312 |

The three edited cells:

| Cell | Truth px, before | Truth px, after | Method | IoU, before | IoU, after | Area ratio, before | Area ratio, after |
|---|---|---|---|---|---|---|---|
| B12 | 174094 | 175372 | grow from leaf cores | 0.996 | 0.989 | 1.003 | 0.996 |
| B12 | 174094 | 175372 | stage A (15 epochs), half resolution | 0.976 | 0.974 | 1.011 | 1.003 |
| B12 | 174094 | 175372 | stage E (40 epochs), the final settings | 0.980 | 0.978 | 1.008 | 1.001 |
| B13 | 47927 | 48513 | grow from leaf cores | 1.000 | 0.988 | 1.000 | 0.988 |
| B13 | 47927 | 48513 | stage A (15 epochs), half resolution | 0.963 | 0.952 | 0.997 | 0.985 |
| B13 | 47927 | 48513 | stage E (40 epochs), the final settings | 0.967 | 0.956 | 1.004 | 0.992 |
| B19 | 93681 | 94488 | grow from leaf cores | 1.000 | 0.991 | 1.000 | 0.991 |
| B19 | 93681 | 94488 | stage A (15 epochs), half resolution | 0.987 | 0.979 | 0.994 | 0.985 |
| B19 | 93681 | 94488 | stage E (40 epochs), the final settings | 0.993 | 0.985 | 0.997 | 0.988 |

Stage E against stage A by the agreed rule, on the new truths (information only; Aaron chose E on 2026-11-21):

| Rig | Mean IoU, E minus A | SD over folds | Mean area error, A minus E (percentage points) | SD over folds (percentage points) | E better by more than the spread? |
|---|---|---|---|---|---|
| production | +0.0310 | 0.0323 | +3.09 | 3.74 | no |
| development | +0.0041 | 0.0079 | +0.39 | 1.50 | no |

## 2. Training the final network

Stage E's settings: U-Net with a MobileNetV2 encoder from ImageNet weights, half resolution, 256 px tiles, crop shifts up to 32 px, no public data, AdamW lr 5e-4, 150 warm-up steps then cosine to zero over 40 epochs of 400 steps (16000 steps), batch 24, BCE + dice, truth-cell share 0.125, the same augmentation. Trained on every training day: 232 photos (24413 patches; the flagged steadiness photos left out) and all 42 training truth cells with the current truths. Seed 199 (the fold formula with no fold). A checkpoint every epoch; the last weights kept, no early stopping.

- Model: `analysis/train/runs/s2_final_e40/model.pt`.
- Training time 25.9 min on the RTX 2060 SUPER, peak GPU memory 4301 MiB.
- Final training loss (mean of the last epoch, BCE + dice with augmentation): **0.0405** (last logged stretch: loss 0.0405, BCE 0.0054, dice 0.0352). The 5 stage E fold models ended at 0.0393 on average.

| Epoch | Final network, training loss | Stage E fold models, mean training loss |
|---|---|---|
| 1 | 0.4126 | 0.6226 |
| 6 | 0.0867 | 0.0677 |
| 11 | 0.0551 | 0.0538 |
| 16 | 0.0520 | 0.0510 |
| 21 | 0.0479 | 0.0455 |
| 26 | 0.0427 | 0.0429 |
| 31 | 0.0417 | 0.0403 |
| 36 | 0.0407 | 0.0390 |
| 40 | 0.0405 | 0.0393 |

No NaN or infinite loss in the log: yes.

## 3. Sanity check on the 42 training cells: seen in training, not a score

The final network has no held-out score: every training cell was seen in training. These numbers only show that it learned what it was given. The cross-validated figure for the final settings is the stage E fold model row (each cell scored by the model that never saw its day). Production cells: network on the whole photo; development cells: on the crop alone.

| Rig | Method | Mean IoU (0 to 1, higher is better) | Mean area error (%, lower is better) | Pooled IoU (0 to 1, higher is better) | Lowest IoU |
|---|---|---|---|---|---|
| production (17) | grow from leaf cores | 0.885 | 11.3 | 0.945 | 0.000 |
| production (17) | stage E fold model, not trained on the cell's day (held out) | 0.878 | 9.4 | 0.909 | 0.689 |
| production (17) | final network, trained on these cells (seen in training) | 0.894 | 7.6 | 0.919 | 0.743 |
| development (25) | grow from leaf cores | 0.967 | 3.0 | 0.973 | 0.838 |
| development (25) | stage E fold model, not trained on the cell's day (held out) | 0.939 | 3.3 | 0.931 | 0.805 |
| development (25) | final network, trained on these cells (seen in training) | 0.965 | 1.3 | 0.974 | 0.935 |

Seedlings (production "empty" cells and every "size 1 of 5" cell), seen in training for the final network:

| Cell | Rig | Truth px | IoU, stage E fold model (held out) | IoU, final network (seen) | Area ratio, stage E fold model (held out) | Area ratio, final network (seen) |
|---|---|---|---|---|---|---|
| A01 | production | 237 | 0.689 | 0.743 | 0.717 | 0.802 |
| A02 | production | 233 | 0.789 | 0.779 | 1.150 | 1.137 |
| A17 | production | 1376 | 0.768 | 0.807 | 0.795 | 0.852 |
| A05 | production | 704 | 0.868 | 0.884 | 1.146 | 1.125 |
| A06 | production | 677 | 0.904 | 0.934 | 1.084 | 1.031 |
| A30 | production | 1124 | 0.885 | 0.910 | 0.939 | 0.936 |
| B02 | development | 5956 | 0.967 | 0.965 | 1.030 | 1.027 |
| B18 | development | 12076 | 0.934 | 0.964 | 0.988 | 1.008 |
| B27 | development | 7737 | 0.918 | 0.940 | 0.997 | 0.991 |
| B30 | development | 3483 | 0.896 | 0.935 | 1.076 | 1.017 |

## 4. One whole production photo (production_28022, 2026-11-09), seen in training

Read at half resolution (stride 192, middle kept) by the stage E fold model that held out its day (fold 4) and by the final network (this photo was one of its training photos). Plant pixels at half resolution: fold model 109,926 (0.69% of the photo), final network 109,342 (0.69%). Agreement between the two masks: IoU 0.970.

## Picture

`stage-F.png`: colour crop | truth | grow from leaf cores | stage E fold model, not trained on this cell's day | final network, trained on this cell (seen in training); then the whole photo. The same 8 cells as stage A:

- A02: seedling: production "empty" cell with the smallest truth
- A27: blue mat: median truth size of the blue-mat cells
- A12: green soil, production: median truth size
- B03: green soil / moss, development: median truth size
- B24: "empty" development cell (dead or tiny plant): median truth size
- B23: largest plants (size 5 of 5): median truth size, both rigs
- B19: network best in stage A: highest half-resolution IoU of the cells not picked above
- A01: network worst in stage A: lowest half-resolution IoU of the cells not picked above

Files: `experiments/round4-segmentation-nn/code/train_cv.py` (method in its docstring) and `final_fg.py`; driver `~/temp.nobackup/npec-406-nn/analysis/train/run_fg.sh`; final network `runs/s2_final_e40/` (model.pt, meta.json, scores.csv), its masks `pred/s2_final_e40/`, under `~/temp.nobackup/npec-406-nn/analysis/train/`.
