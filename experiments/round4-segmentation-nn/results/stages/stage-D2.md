# Stage D2: pre-trained on all 7 public sets, then trained on ours

Written by `train_cv.py compare --stage D2` (2026-11-21 01:22 UTC). Development check. Training cells only (42: production 17, development 25); no test cell was opened.
Half resolution (S = 2), the stage A recipe otherwise. Every cell is scored once, by the fold model that never saw its UTC day. Production cells: network on the whole photo; development cells: on the crop alone. Threshold probability 0.5, float32.

What changed: only the starting weights, as in D1 but with all seven public sets. The same network (U-Net, MobileNetV2 encoder from ImageNet) was first trained on public tiles of vegann, aradeepopsis, aled, potato_leaf, potato_canopy, we3ds, sugarbeets (ARADEEPOPSIS with Aaron's labels of 2026-11-21: healthy and purple = plant, senescent = not plant), 29139 patches, each set drawn with probability 1/7 per sample, 30 epochs of 400 steps (12000 steps, batch 24), the stage A optimiser, schedule, loss and augmentation, no truth cells, no early stopping (length fixed in advance; the D1 recipe). Then, for each of the 5 folds, trained on ours exactly as stage A (same photos, cells, seeds, 15 epochs, lr 5e-4 with warm-up and cosine), starting from those weights, with the B21 truth as edited on 2026-11-21. Read as stage A (stride 192, middle kept). Compared with the current best (stage A) by the rule, and with D1 as information.

## The B21 truth edit, and how far it moved stage A and D1

Before this stage, one training truth was changed (Aaron, 2026-11-21: purple, anthocyanin, tissue is plant): B21, 896 px of reddish-purple leaf stalk filled as plant (129,099 -> 129,995 truth px; log in `analysis/labels/truth_edits/`). The half-resolution truth cells used in training were rebuilt from the truth files: only B21's target changed (41 cells identical). Stage A, D1 (and B, C) were **not retrained**: their saved predictions were re-scored against the new truth; only B21's rows changed (cells changed: B21; grow from leaf cores: B21). Every score in this file uses the new truth. Stage A and D1 models were trained with the old B21 label, D2 with the new one.

| Rig | Method | Pooled IoU before -> after | Mean IoU before -> after | Mean abs(area ratio - 1) before -> after | B21 IoU / area ratio before -> after |
|---|---|---|---|---|---|
| prod | grow from leaf cores | 0.9452 -> 0.9452 | 0.8848 -> 0.8848 | 0.1135 -> 0.1135 |  |
| prod | stage A, half resolution (current best) | 0.8944 -> 0.8944 | 0.8474 -> 0.8474 | 0.1249 -> 0.1249 |  |
| prod | stage A, full resolution | 0.9073 -> 0.9073 | 0.8731 -> 0.8731 | 0.1103 -> 0.1103 |  |
| prod | D1: 6 public sets first, then ours | 0.9018 -> 0.9018 | 0.8715 -> 0.8715 | 0.1033 -> 0.1033 |  |
| dev | grow from leaf cores | 0.9771 -> 0.9761 | 0.9680 -> 0.9677 | 0.0291 -> 0.0290 | 1.00 / 1.00 -> 0.99 / 1.00 |
| dev | stage A, half resolution (current best) | 0.9286 -> 0.9278 | 0.9363 -> 0.9362 | 0.0368 -> 0.0365 | 0.81 / 1.16 -> 0.81 / 1.16 |
| dev | stage A, full resolution | 0.9164 -> 0.9159 | 0.9298 -> 0.9297 | 0.0390 -> 0.0387 | 0.81 / 1.12 -> 0.80 / 1.11 |
| dev | D1: 6 public sets first, then ours | 0.9276 -> 0.9269 | 0.9372 -> 0.9370 | 0.0382 -> 0.0379 | 0.81 / 1.21 -> 0.81 / 1.20 |

The rule's numbers, before -> after (difference / SD over folds):

| Comparison | Rig | Mean IoU difference | SD | Mean abs(ratio-1) difference | SD | Passes? |
|---|---|---|---|---|---|---|
| stage A: full against half resolution | prod | +0.0257 -> +0.0257 | 0.0272 -> 0.0272 | +0.0146 -> +0.0146 | 0.0465 -> 0.0465 | no -> no |
| stage A: full against half resolution | dev | -0.0065 -> -0.0065 | 0.0185 -> 0.0185 | -0.0022 -> -0.0022 | 0.0230 -> 0.0230 | no -> no |
| D1 against stage A | prod | +0.0241 -> +0.0241 | 0.0313 -> 0.0313 | +0.0216 -> +0.0216 | 0.0427 -> 0.0427 | no -> no |
| D1 against stage A | dev | +0.0009 -> +0.0008 | 0.0051 -> 0.0051 | -0.0014 -> -0.0014 | 0.0113 -> 0.0113 | no -> no |

## Results per rig

| Rig | Method | Pooled IoU | Mean IoU | Lowest IoU | Mean abs(area ratio - 1) | Pooled area ratio |
|---|---|---|---|---|---|---|
| production (17) | grow from leaf cores | 0.945 | 0.885 | 0.000 | 0.114 | 0.982 |
| production (17) | current best: ImageNet start, ours only | 0.894 | 0.847 | 0.388 | 0.125 | 0.953 |
| production (17) | D1: 6 public sets first, then ours | 0.902 | 0.872 | 0.668 | 0.103 | 0.961 |
| production (17) | D2: all 7 public sets first, then ours | 0.903 | 0.871 | 0.679 | 0.108 | 0.963 |
| development (25) | grow from leaf cores | 0.976 | 0.968 | 0.838 | 0.029 | 1.006 |
| development (25) | current best: ImageNet start, ours only | 0.928 | 0.936 | 0.807 | 0.036 | 1.039 |
| development (25) | D1: 6 public sets first, then ours | 0.927 | 0.937 | 0.809 | 0.038 | 1.046 |
| development (25) | D2: all 7 public sets first, then ours | 0.930 | 0.939 | 0.814 | 0.036 | 1.044 |

**Corrected cells only** (the 30 truths Aaron corrected; on the other 12, grow from leaf cores scores 1.000 by construction):

| Rig | Method | Pooled IoU | Mean IoU | Lowest IoU | Mean abs(area ratio - 1) | Pooled area ratio |
|---|---|---|---|---|---|---|
| production (10) | grow from leaf cores | 0.926 | 0.804 | 0.000 | 0.193 | 0.975 |
| production (10) | current best: ImageNet start, ours only | 0.896 | 0.816 | 0.388 | 0.153 | 0.956 |
| production (10) | D1: 6 public sets first, then ours | 0.902 | 0.849 | 0.668 | 0.124 | 0.966 |
| production (10) | D2: all 7 public sets first, then ours | 0.906 | 0.850 | 0.679 | 0.126 | 0.969 |
| development (20) | grow from leaf cores | 0.974 | 0.960 | 0.838 | 0.036 | 1.007 |
| development (20) | current best: ImageNet start, ours only | 0.925 | 0.934 | 0.807 | 0.038 | 1.042 |
| development (20) | D1: 6 public sets first, then ours | 0.924 | 0.935 | 0.809 | 0.041 | 1.049 |
| development (20) | D2: all 7 public sets first, then ours | 0.927 | 0.935 | 0.814 | 0.041 | 1.047 |

## Fold to fold

Mean IoU / mean abs(area ratio - 1) of each fold's held-out cells (cells per fold in brackets).

| Rig | Method | fold 1 | fold 2 | fold 3 | fold 4 | fold 5 | SD of folds |
|---|---|---|---|---|---|---|---|
| prod | grow from leaf cores | 0.931 / 0.083 (3) | 1.000 / 0.000 (3) | 0.900 / 0.095 (3) | 0.723 / 0.273 (4) | 0.914 / 0.076 (4) | 0.103 / 0.101 |
| prod | current best: ImageNet start, ours only | 0.878 / 0.098 (3) | 0.894 / 0.077 (3) | 0.882 / 0.079 (3) | 0.779 / 0.183 (4) | 0.831 / 0.158 (4) | 0.048 / 0.048 |
| prod | D1: 6 public sets first, then ours | 0.884 / 0.099 (3) | 0.905 / 0.064 (3) | 0.879 / 0.112 (3) | 0.854 / 0.100 (4) | 0.848 / 0.133 (4) | 0.023 / 0.025 |
| prod | D2: all 7 public sets first, then ours | 0.883 / 0.099 (3) | 0.904 / 0.077 (3) | 0.871 / 0.127 (3) | 0.861 / 0.096 (4) | 0.846 / 0.136 (4) | 0.022 / 0.024 |
| dev | grow from leaf cores | 0.969 / 0.028 (7) | 0.934 / 0.063 (6) | 0.991 / 0.006 (5) | 0.964 / 0.031 (4) | 0.998 / 0.001 (3) | 0.025 / 0.025 |
| dev | current best: ImageNet start, ours only | 0.954 / 0.021 (7) | 0.953 / 0.024 (6) | 0.897 / 0.081 (5) | 0.922 / 0.027 (4) | 0.946 / 0.036 (3) | 0.025 / 0.025 |
| dev | D1: 6 public sets first, then ours | 0.956 / 0.016 (7) | 0.951 / 0.027 (6) | 0.897 / 0.100 (5) | 0.930 / 0.016 (4) | 0.939 / 0.038 (3) | 0.023 / 0.035 |
| dev | D2: all 7 public sets first, then ours | 0.961 / 0.015 (7) | 0.944 / 0.034 (6) | 0.899 / 0.093 (5) | 0.940 / 0.009 (4) | 0.946 / 0.030 (3) | 0.023 / 0.033 |

## Decision by the agreed rule

Rule: keep D2 only if it beats A for both rigs, in mean IoU and in mean abs(area ratio - 1), each by more than the fold-to-fold variation: the standard deviation over the 5 folds of the per-fold difference (the same cells under both, so the paired difference is the fair spread). Otherwise A stays.

| Rig | Mean IoU D2 - A | SD over folds | Mean abs(ratio-1) A - D2 | SD over folds | Per-fold IoU differences | Per-fold abs(ratio-1) differences | D2 better by more than the spread? |
|---|---|---|---|---|---|---|---|
| prod | +0.0233 | 0.0363 | +0.0169 | 0.0492 | +0.005 +0.009 -0.012 +0.082 +0.015 | -0.001 -0.000 -0.049 +0.087 +0.022 | no |
| dev | +0.0031 | 0.0096 | +0.0005 | 0.0123 | +0.007 -0.008 +0.002 +0.018 +0.000 | +0.006 -0.010 -0.012 +0.018 +0.005 | no |

**Decision by the rule: no public pre-training (the simpler setting).**

**D2 against D1, information only** (not a decision: D1 did not pass the rule, so it is not the current best). Same rule and spread; positive means D2 better.

| Rig | Mean IoU D2 - D1 | SD over folds | Mean abs(ratio-1) D1 - D2 | SD over folds | Per-fold IoU differences | Per-fold abs(ratio-1) differences | D2 better than D1 by more than the spread? |
|---|---|---|---|---|---|---|---|
| prod | -0.0008 | 0.0054 | -0.0047 | 0.0084 | -0.001 -0.002 -0.008 +0.007 -0.002 | +0.000 -0.013 -0.015 +0.004 -0.002 | no |
| dev | +0.0023 | 0.0066 | +0.0019 | 0.0062 | +0.004 -0.007 +0.002 +0.010 +0.007 | +0.001 -0.007 +0.007 +0.007 +0.007 | no |

## Seedlings on their own

Production "empty" cells (seedlings, A01, A02, A17) and every "size 1 of 5" cell. IoU / area ratio.

| Cell | Rig | Stratum | Truth px | grow from leaf cores | current best: ImageNet start, ours only | D1: 6 public sets first, then ours | D2: all 7 public sets first, then ours |
|---|---|---|---|---|---|---|---|
| A01 | prod | empty | 237 | 0.00 / 0.00 | 0.39 / 0.39 | 0.67 / 0.70 | 0.68 / 0.70 |
| A02 | prod | empty | 233 | 0.76 / 1.23 | 0.76 / 1.18 | 0.75 / 1.28 | 0.73 / 1.32 |
| A17 | prod | empty | 1376 | 0.77 / 0.80 | 0.78 / 0.81 | 0.79 / 0.82 | 0.80 / 0.83 |
| A05 | prod | size 1 of 5 | 704 | 1.00 / 1.00 | 0.85 / 1.15 | 0.87 / 1.14 | 0.85 / 1.17 |
| A06 | prod | size 1 of 5 | 677 | 1.00 / 1.00 | 0.92 / 1.05 | 0.93 / 1.04 | 0.92 / 1.04 |
| A30 | prod | blue mat, size 1 of 5 | 1124 | 0.94 / 0.94 | 0.89 / 0.94 | 0.89 / 0.94 | 0.90 / 0.94 |
| B02 | dev | size 1 of 5 | 5956 | 1.00 / 1.00 | 0.97 / 1.01 | 0.97 / 1.01 | 0.97 / 1.00 |
| B18 | dev | size 1 of 5 | 12076 | 0.99 / 1.00 | 0.90 / 0.95 | 0.90 / 0.96 | 0.89 / 0.95 |
| B27 | dev | size 1 of 5 | 7737 | 0.92 / 0.92 | 0.91 / 1.00 | 0.91 / 0.99 | 0.92 / 1.00 |
| B30 | dev | size 1 of 5 | 3483 | 1.00 / 1.00 | 0.88 / 1.09 | 0.91 / 1.05 | 0.93 / 1.02 |
| all 10 | | mean | |  | 0.83 / 0.140 (mean abs(ratio-1)) |  |  |
| all 10 | | mean | |  |  |  | 0.86 / 0.114 (mean abs(ratio-1)) |

## Training time

Public pre-training on 7 sets (once): 20.1 min, peak GPU 4301 MiB (D1, 6 sets: 17.2 min). Reading time is unchanged (same network, same read).

| Fold | A (ImageNet start) min | D1 min | D2 min |
|---|---|---|---|
| 1 | 8.9 | 8.8 | 9.7 |
| 2 | 8.8 | 8.8 | 9.6 |
| 3 | 8.8 | 8.8 | 8.8 |
| 4 | 8.8 | 8.8 | 8.7 |
| 5 | 8.8 | 9.4 | 8.7 |

## D2 on ARADEEPOPSIS photos (seen in training, information only)

D2 was pre-trained on ARADEEPOPSIS: every one of its 1899 photos gave one tile (nearly the whole photo at x0.45) to the pre-training, so D2's rows are **seen in training** and say only how well the network learned purple rosettes it was shown, not how it does on unseen plants. The other rows are D1u's (none of those networks saw ARADEEPOPSIS). Same reading as D1u: mean of the 5 fold models, x0.45, tiles 256 stride 192 middle kept, threshold 0.5, labelled pixels only; our labels (healthy and purple = plant, senescent = not plant).

| Photos (n) | Method | Pooled IoU | Mean IoU | Mean abs(area ratio - 1) | Pooled area ratio |
|---|---|---|---|---|---|
| anthoSet, purple-rich (class 3 > 25% of plant) (444) | grow from leaf cores | 0.352 | 0.351 | 0.448 | 0.682 |
| anthoSet, purple-rich (class 3 > 25% of plant) (444) | current best (no public data) | 0.407 | 0.402 | 0.537 | 0.467 |
| anthoSet, purple-rich (class 3 > 25% of plant) (444) | D1 (6 public sets, then ours) | 0.428 | 0.424 | 0.536 | 0.500 |
| anthoSet, purple-rich (class 3 > 25% of plant) (444) | D2 (all 7 public sets, then ours): SEEN IN TRAINING | 0.453 | 0.451 | 0.509 | 0.528 |
| anthoSet, not purple-rich (class 3 <= 25%) (1134) | grow from leaf cores | 0.513 | 0.456 | 7.745 | 1.628 |
| anthoSet, not purple-rich (class 3 <= 25%) (1134) | current best (no public data) | 0.766 | 0.694 | 1.054 | 0.968 |
| anthoSet, not purple-rich (class 3 <= 25%) (1134) | D1 (6 public sets, then ours) | 0.770 | 0.671 | 1.873 | 1.049 |
| anthoSet, not purple-rich (class 3 <= 25%) (1134) | D2 (all 7 public sets, then ours): SEEN IN TRAINING | 0.786 | 0.692 | 1.873 | 1.047 |
| all photos (each once) (1899) | grow from leaf cores | 0.396 | 0.406 | 7.563 | 1.348 |
| all photos (each once) (1899) | current best (no public data) | 0.591 | 0.617 | 0.926 | 0.714 |
| all photos (each once) (1899) | D1 (6 public sets, then ours) | 0.610 | 0.612 | 1.461 | 0.772 |
| all photos (each once) (1899) | D2 (all 7 public sets, then ours): SEEN IN TRAINING | 0.627 | 0.627 | 1.443 | 0.782 |

Per-image scores `results/d2u_per_image.csv`; masks `analysis/train/pred/d2u/`.


## Picture

`stage-D2.png`: columns crop | truth | grow from leaf cores | old (current best: ImageNet start, ours only) | new (D2: all 7 public sets first, then ours). The same 8 cells as stage A, by the same rules (the best/worst rules use stage A's half-resolution IoU, so they pick the same cells):

- A02: seedling: production "empty" cell with the smallest truth
- A27: blue mat: median truth size of the blue-mat cells
- A12: green soil, production: median truth size
- B03: green soil / moss, development: median truth size
- B24: "empty" development cell (dead or tiny plant): median truth size
- B23: largest plants (size 5 of 5): median truth size, both rigs
- B19: network best: highest half-resolution IoU of the cells not picked above
- A01: network worst: lowest half-resolution IoU of the cells not picked above

Files: `experiments/round4-segmentation-nn/code/train_cv.py` (method in its docstring), driver `~/temp.nobackup/npec-406-nn/analysis/train/run_de.sh`; per-fold scores `runs/<run>/scores*.csv`, predictions `pred/<run>/`, under `~/temp.nobackup/npec-406-nn/analysis/train/`.
