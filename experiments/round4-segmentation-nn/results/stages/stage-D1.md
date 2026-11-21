# Stage D1: pre-trained on 6 public sets, then trained on ours

Written by `train_cv.py compare --stage D1` (2026-11-21 00:00 UTC). Development check. Training cells only (42: production 17, development 25); no test cell was opened.
Half resolution (S = 2), the stage A recipe otherwise. Every cell is scored once, by the fold model that never saw its UTC day. Production cells: network on the whole photo; development cells: on the crop alone. Threshold probability 0.5, float32.

What changed: only the starting weights. The same network (U-Net, MobileNetV2 encoder from ImageNet) was first trained on public tiles of six sets (vegann, aled, potato_leaf, potato_canopy, we3ds, sugarbeets; ARADEEPOPSIS left out for D1u), 27240 patches, each set drawn with equal probability per sample, 30 epochs of 400 steps (12000 steps, batch 24), the stage A optimiser, schedule, loss and augmentation, no truth cells, no early stopping (length fixed in advance). Then, for each of the 5 folds, trained on ours exactly as stage A (same photos, cells, seeds, 15 epochs, lr 5e-4 with warm-up and cosine), starting from those weights. Read as stage A (stride 192, middle kept, the stage B winner; jitter 32, stage C kept it). Public sets, scales and tile counts: D0, `public_prep.py` and `results/public_tiles.csv`.

## Results per rig

| Rig | Method | Pooled IoU | Mean IoU | Lowest IoU | Mean abs(area ratio - 1) | Pooled area ratio |
|---|---|---|---|---|---|---|
| production (17) | grow from leaf cores | 0.945 | 0.885 | 0.000 | 0.114 | 0.982 |
| production (17) | current best: ImageNet start, ours only | 0.894 | 0.847 | 0.388 | 0.125 | 0.953 |
| production (17) | D1: 6 public sets first, then ours | 0.902 | 0.872 | 0.668 | 0.103 | 0.961 |
| development (25) | grow from leaf cores | 0.977 | 0.968 | 0.838 | 0.029 | 1.007 |
| development (25) | current best: ImageNet start, ours only | 0.929 | 0.936 | 0.811 | 0.037 | 1.040 |
| development (25) | D1: 6 public sets first, then ours | 0.928 | 0.937 | 0.812 | 0.038 | 1.047 |

**Corrected cells only** (the 30 truths Aaron corrected; on the other 12, grow from leaf cores scores 1.000 by construction):

| Rig | Method | Pooled IoU | Mean IoU | Lowest IoU | Mean abs(area ratio - 1) | Pooled area ratio |
|---|---|---|---|---|---|---|
| production (10) | grow from leaf cores | 0.926 | 0.804 | 0.000 | 0.193 | 0.975 |
| production (10) | current best: ImageNet start, ours only | 0.896 | 0.816 | 0.388 | 0.153 | 0.956 |
| production (10) | D1: 6 public sets first, then ours | 0.902 | 0.849 | 0.668 | 0.124 | 0.966 |
| development (20) | grow from leaf cores | 0.975 | 0.960 | 0.838 | 0.036 | 1.008 |
| development (20) | current best: ImageNet start, ours only | 0.926 | 0.935 | 0.811 | 0.038 | 1.043 |
| development (20) | D1: 6 public sets first, then ours | 0.925 | 0.935 | 0.812 | 0.041 | 1.050 |

## Fold to fold

Mean IoU / mean abs(area ratio - 1) of each fold's held-out cells (cells per fold in brackets).

| Rig | Method | fold 1 | fold 2 | fold 3 | fold 4 | fold 5 | SD of folds |
|---|---|---|---|---|---|---|---|
| prod | grow from leaf cores | 0.931 / 0.083 (3) | 1.000 / 0.000 (3) | 0.900 / 0.095 (3) | 0.723 / 0.273 (4) | 0.914 / 0.076 (4) | 0.103 / 0.101 |
| prod | current best: ImageNet start, ours only | 0.878 / 0.098 (3) | 0.894 / 0.077 (3) | 0.882 / 0.079 (3) | 0.779 / 0.183 (4) | 0.831 / 0.158 (4) | 0.048 / 0.048 |
| prod | D1: 6 public sets first, then ours | 0.884 / 0.099 (3) | 0.905 / 0.064 (3) | 0.879 / 0.112 (3) | 0.854 / 0.100 (4) | 0.848 / 0.133 (4) | 0.023 / 0.025 |
| dev | grow from leaf cores | 0.969 / 0.028 (7) | 0.934 / 0.063 (6) | 0.993 / 0.006 (5) | 0.964 / 0.031 (4) | 0.998 / 0.001 (3) | 0.026 / 0.025 |
| dev | current best: ImageNet start, ours only | 0.954 / 0.021 (7) | 0.953 / 0.024 (6) | 0.897 / 0.083 (5) | 0.922 / 0.027 (4) | 0.946 / 0.036 (3) | 0.024 / 0.026 |
| dev | D1: 6 public sets first, then ours | 0.956 / 0.016 (7) | 0.951 / 0.027 (6) | 0.898 / 0.102 (5) | 0.930 / 0.016 (4) | 0.939 / 0.038 (3) | 0.023 / 0.036 |

## Decision by the agreed rule

Rule: keep D1 only if it beats A for both rigs, in mean IoU and in mean abs(area ratio - 1), each by more than the fold-to-fold variation: the standard deviation over the 5 folds of the per-fold difference (the same cells under both, so the paired difference is the fair spread). Otherwise A stays.

| Rig | Mean IoU D1 - A | SD over folds | Mean abs(ratio-1) A - D1 | SD over folds | Per-fold IoU differences | Per-fold abs(ratio-1) differences | D1 better by more than the spread? |
|---|---|---|---|---|---|---|---|
| prod | +0.0241 | 0.0313 | +0.0216 | 0.0427 | +0.006 +0.011 -0.003 +0.076 +0.017 | -0.001 +0.013 -0.033 +0.083 +0.024 | no |
| dev | +0.0009 | 0.0051 | -0.0014 | 0.0113 | +0.003 -0.001 +0.000 +0.007 -0.006 | +0.005 -0.003 -0.019 +0.011 -0.002 | no |

**Decision by the rule: no public pre-training (the simpler setting).**

## Seedlings on their own

Production "empty" cells (seedlings, A01, A02, A17) and every "size 1 of 5" cell. IoU / area ratio.

| Cell | Rig | Stratum | Truth px | grow from leaf cores | current best: ImageNet start, ours only | D1: 6 public sets first, then ours |
|---|---|---|---|---|---|---|
| A01 | prod | empty | 237 | 0.00 / 0.00 | 0.39 / 0.39 | 0.67 / 0.70 |
| A02 | prod | empty | 233 | 0.76 / 1.23 | 0.76 / 1.18 | 0.75 / 1.28 |
| A17 | prod | empty | 1376 | 0.77 / 0.80 | 0.78 / 0.81 | 0.79 / 0.82 |
| A05 | prod | size 1 of 5 | 704 | 1.00 / 1.00 | 0.85 / 1.15 | 0.87 / 1.14 |
| A06 | prod | size 1 of 5 | 677 | 1.00 / 1.00 | 0.92 / 1.05 | 0.93 / 1.04 |
| A30 | prod | blue mat, size 1 of 5 | 1124 | 0.94 / 0.94 | 0.89 / 0.94 | 0.89 / 0.94 |
| B02 | dev | size 1 of 5 | 5956 | 1.00 / 1.00 | 0.97 / 1.01 | 0.97 / 1.01 |
| B18 | dev | size 1 of 5 | 12076 | 0.99 / 1.00 | 0.90 / 0.95 | 0.90 / 0.96 |
| B27 | dev | size 1 of 5 | 7737 | 0.92 / 0.92 | 0.91 / 1.00 | 0.91 / 0.99 |
| B30 | dev | size 1 of 5 | 3483 | 1.00 / 1.00 | 0.88 / 1.09 | 0.91 / 1.05 |
| all 10 | | mean | |  | 0.83 / 0.140 (mean abs(ratio-1)) |  |
| all 10 | | mean | |  |  | 0.86 / 0.111 (mean abs(ratio-1)) |

## Training time

Public pre-training (once): 17.2 min, peak GPU 4301 MiB. Reading time is unchanged (same network, same read).

| Fold | A (ImageNet start) min | D1 (from pre-training) min |
|---|---|---|
| 1 | 8.9 | 8.8 |
| 2 | 8.8 | 8.8 |
| 3 | 8.8 | 8.8 |
| 4 | 8.8 | 8.8 |
| 5 | 8.8 | 9.4 |

## Picture

`stage-D1.png`: columns crop | truth | grow from leaf cores | old (current best: ImageNet start, ours only) | new (D1: 6 public sets first, then ours). The same 8 cells as stage A, by the same rules (the best/worst rules use stage A's half-resolution IoU, so they pick the same cells):

- A02: seedling: production "empty" cell with the smallest truth
- A27: blue mat: median truth size of the blue-mat cells
- A12: green soil, production: median truth size
- B03: green soil / moss, development: median truth size
- B24: "empty" development cell (dead or tiny plant): median truth size
- B23: largest plants (size 5 of 5): median truth size, both rigs
- B19: network best: highest half-resolution IoU of the cells not picked above
- A01: network worst: lowest half-resolution IoU of the cells not picked above

Files: `experiments/round4-segmentation-nn/code/train_cv.py` (method in its docstring), driver `~/temp.nobackup/npec-406-nn/analysis/train/run_d.sh`; per-fold scores `runs/<run>/scores*.csv`, predictions `pred/<run>/`, under `~/temp.nobackup/npec-406-nn/analysis/train/`.
