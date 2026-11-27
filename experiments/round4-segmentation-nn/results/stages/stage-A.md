# Stage A: first plant network, cross-validation on the training cells

Written by `train_cv.py stage` (2026-11-20 21:43 UTC). Development check. Training cells only (42: production 17, development 25); no test cell was opened.
Every cell is scored once, by the model of the fold that held out its UTC day (5 folds, `results/train_cv_folds.csv`).
Production cells: network on the whole photo; development cells: network on the crop alone (their photos were purged).
Grow from leaf cores: the step 1 counts of the same cells (`results/per_cell.csv`). Threshold probability 0.5, float32.

## Results per rig

| Rig | Method | Pooled IoU | Mean IoU | Lowest IoU | Mean abs(area ratio - 1) | Pooled area ratio |
|---|---|---|---|---|---|---|
| production (17) | grow from leaf cores | 0.945 | 0.885 | 0.000 | 0.114 | 0.982 |
| production (17) | network, half resolution | 0.894 | 0.847 | 0.388 | 0.125 | 0.953 |
| production (17) | network, full resolution | 0.907 | 0.873 | 0.584 | 0.110 | 0.961 |
| development (25) | grow from leaf cores | 0.977 | 0.968 | 0.838 | 0.029 | 1.007 |
| development (25) | network, half resolution | 0.929 | 0.936 | 0.811 | 0.037 | 1.040 |
| development (25) | network, full resolution | 0.916 | 0.930 | 0.806 | 0.039 | 1.010 |

No training truth is empty, so every cell has an area ratio.

**Corrected cells only.** 12 of the 42 truths are accepted drafts of grow from leaf cores, where it scores 1.000 by construction (step 1). The fairer comparison is on the 30 truths Aaron corrected:

| Rig | Method | Pooled IoU | Mean IoU | Lowest IoU | Mean abs(area ratio - 1) | Pooled area ratio |
|---|---|---|---|---|---|---|
| production (10) | grow from leaf cores | 0.926 | 0.804 | 0.000 | 0.193 | 0.975 |
| production (10) | network, half resolution | 0.896 | 0.816 | 0.388 | 0.153 | 0.956 |
| production (10) | network, full resolution | 0.906 | 0.847 | 0.584 | 0.131 | 0.958 |
| development (20) | grow from leaf cores | 0.975 | 0.960 | 0.838 | 0.036 | 1.008 |
| development (20) | network, half resolution | 0.926 | 0.935 | 0.811 | 0.038 | 1.043 |
| development (20) | network, full resolution | 0.913 | 0.925 | 0.806 | 0.043 | 1.011 |

## Fold to fold

Mean IoU / mean abs(area ratio - 1) of each fold's held-out cells (cells per fold in brackets).

| Rig | Method | fold 1 | fold 2 | fold 3 | fold 4 | fold 5 | SD of folds |
|---|---|---|---|---|---|---|---|
| prod | grow from leaf cores | 0.931 / 0.083 (3) | 1.000 / 0.000 (3) | 0.900 / 0.095 (3) | 0.723 / 0.273 (4) | 0.914 / 0.076 (4) | 0.103 / 0.101 |
| prod | network, half resolution | 0.878 / 0.098 (3) | 0.894 / 0.077 (3) | 0.882 / 0.079 (3) | 0.779 / 0.183 (4) | 0.831 / 0.158 (4) | 0.048 / 0.048 |
| prod | network, full resolution | 0.888 / 0.098 (3) | 0.903 / 0.096 (3) | 0.878 / 0.124 (3) | 0.843 / 0.110 (4) | 0.866 / 0.121 (4) | 0.023 / 0.013 |
| dev | grow from leaf cores | 0.969 / 0.028 (7) | 0.934 / 0.063 (6) | 0.993 / 0.006 (5) | 0.964 / 0.031 (4) | 0.998 / 0.001 (3) | 0.026 / 0.025 |
| dev | network, half resolution | 0.954 / 0.021 (7) | 0.953 / 0.024 (6) | 0.897 / 0.083 (5) | 0.922 / 0.027 (4) | 0.946 / 0.036 (3) | 0.024 / 0.026 |
| dev | network, full resolution | 0.954 / 0.021 (7) | 0.938 / 0.035 (6) | 0.895 / 0.070 (5) | 0.934 / 0.008 (4) | 0.909 / 0.076 (3) | 0.024 / 0.030 |

## Scale, by the agreed rule

Rule: half resolution, unless full resolution beats half for both rigs, in mean IoU and in mean abs(area ratio - 1), each by more than the fold-to-fold variation. Fold-to-fold variation, as computed here: the standard deviation over folds of the per-fold difference full minus half (the same cells under both, so the paired difference is the fair spread).

| Rig | Mean IoU full - half | SD over folds | Mean abs(ratio-1) half - full | SD over folds | Full better by more than the spread? |
|---|---|---|---|---|---|
| prod | +0.0257 | 0.0272 | +0.0146 | 0.0465 | no |
| dev | -0.0065 | 0.0185 | -0.0022 | 0.0230 | no |

**Decision by the rule: half resolution.**

## Seedlings on their own

Production "empty" cells (seedlings, A01, A02, A17) and every "size 1 of 5" cell. IoU / area ratio.

| Cell | Rig | Stratum | Truth px | Grow from leaf cores | Network half | Network full |
|---|---|---|---|---|---|---|
| A01 | prod | empty | 237 | 0.00 / 0.00 | 0.39 / 0.39 | 0.58 / 0.64 |
| A02 | prod | empty | 233 | 0.76 / 1.23 | 0.76 / 1.18 | 0.78 / 1.24 |
| A17 | prod | empty | 1376 | 0.77 / 0.80 | 0.78 / 0.81 | 0.79 / 0.82 |
| A05 | prod | size 1 of 5 | 704 | 1.00 / 1.00 | 0.85 / 1.15 | 0.86 / 1.15 |
| A06 | prod | size 1 of 5 | 677 | 1.00 / 1.00 | 0.92 / 1.05 | 0.91 / 1.09 |
| A30 | prod | blue mat, size 1 of 5 | 1124 | 0.94 / 0.94 | 0.89 / 0.94 | 0.91 / 0.95 |
| B02 | dev | size 1 of 5 | 5956 | 1.00 / 1.00 | 0.97 / 1.01 | 0.97 / 1.01 |
| B18 | dev | size 1 of 5 | 12076 | 0.99 / 1.00 | 0.90 / 0.95 | 0.90 / 0.94 |
| B27 | dev | size 1 of 5 | 7737 | 0.92 / 0.92 | 0.91 / 1.00 | 0.92 / 1.00 |
| B30 | dev | size 1 of 5 | 3483 | 1.00 / 1.00 | 0.88 / 1.09 | 0.93 / 0.99 |

## Time per full photo, float32 network on the RTX 2060 SUPER

| Scale | Tiles (256, stride 192) | Seconds (median of 3, after warm-up; excludes JPEG decode) | JPEG decode s |
|---|---|---|---|
| full | 1728 | 4.73 | 0.42 |
| half | 432 | 1.71 | 0.42 |

## Picture

`stage-A.png`: 8 cells picked by these rules, not by look:

- A02: seedling: production "empty" cell with the smallest truth
- A27: blue mat: median truth size of the blue-mat cells
- A12: green soil, production: median truth size
- B03: green soil / moss, development: median truth size
- B24: "empty" development cell (dead or tiny plant): median truth size
- B23: largest plants (size 5 of 5): median truth size, both rigs
- B19: network best: highest half-resolution IoU of the cells not picked above
- A01: network worst: lowest half-resolution IoU of the cells not picked above

Files: `experiments/round4-segmentation-nn/code/train_cv.py` (method in its docstring), tables `results/train_cv_summary.csv`, `train_cv_per_cell.csv`, `train_cv_folds.csv`, `train_cv_timing.csv`; models, predictions and logs under `~/temp.nobackup/npec-406-nn/analysis/train/`.
