# Stage E: training length, 15 against 40 epochs

Written by `train_cv.py compare --stage E` (2026-11-21 03:18 UTC). Development check. Training cells only (42: production 17, development 25); no test cell was opened.
Half resolution (S = 2), the stage A recipe otherwise. Every cell is scored once, by the fold model that never saw its UTC day. Production cells: network on the whole photo; development cells: on the crop alone. Threshold probability 0.5, float32.

What changed: only the training length. The 5 half-resolution folds trained for 40 epochs of 400 steps (16000 steps) instead of 15 (6000 steps), the same warm-up and cosine schedule stretched over the longer run (lr 5e-4 falling to zero at the last step), last weights kept, no early stopping. Everything else is the setting that stood after D2: **stage A (ImageNet start, ours only)**. The 40-epoch models were trained with the B21 truth as edited on 2026-11-21; the 15-epoch models (stage A) were trained before the edit, with the old B21 truth (896 px of one of 34 training cells per fold); every score here is against the new truth. Longer training is the less simple setting, so it is kept only if it beats 15 epochs by the rule.

## Results per rig

| Rig | Method | Pooled IoU | Mean IoU | Lowest IoU | Mean abs(area ratio - 1) | Pooled area ratio |
|---|---|---|---|---|---|---|
| production (17) | grow from leaf cores | 0.945 | 0.885 | 0.000 | 0.114 | 0.982 |
| production (17) | 15 epochs (current best: ImageNet start) | 0.894 | 0.847 | 0.388 | 0.125 | 0.953 |
| production (17) | 40 epochs (otherwise the same) | 0.909 | 0.878 | 0.689 | 0.094 | 0.967 |
| development (25) | grow from leaf cores | 0.976 | 0.968 | 0.838 | 0.029 | 1.006 |
| development (25) | 15 epochs (current best: ImageNet start) | 0.928 | 0.936 | 0.807 | 0.036 | 1.039 |
| development (25) | 40 epochs (otherwise the same) | 0.933 | 0.940 | 0.805 | 0.033 | 1.030 |

**Corrected cells only** (the 30 truths Aaron corrected; on the other 12, grow from leaf cores scores 1.000 by construction):

| Rig | Method | Pooled IoU | Mean IoU | Lowest IoU | Mean abs(area ratio - 1) | Pooled area ratio |
|---|---|---|---|---|---|---|
| production (10) | grow from leaf cores | 0.926 | 0.804 | 0.000 | 0.193 | 0.975 |
| production (10) | 15 epochs (current best: ImageNet start) | 0.896 | 0.816 | 0.388 | 0.153 | 0.956 |
| production (10) | 40 epochs (otherwise the same) | 0.911 | 0.860 | 0.689 | 0.106 | 0.970 |
| development (20) | grow from leaf cores | 0.974 | 0.960 | 0.838 | 0.036 | 1.007 |
| development (20) | 15 epochs (current best: ImageNet start) | 0.925 | 0.934 | 0.807 | 0.038 | 1.042 |
| development (20) | 40 epochs (otherwise the same) | 0.930 | 0.939 | 0.805 | 0.032 | 1.031 |

## Fold to fold

Mean IoU / mean abs(area ratio - 1) of each fold's held-out cells (cells per fold in brackets).

| Rig | Method | fold 1 | fold 2 | fold 3 | fold 4 | fold 5 | SD of folds |
|---|---|---|---|---|---|---|---|
| prod | grow from leaf cores | 0.931 / 0.083 (3) | 1.000 / 0.000 (3) | 0.900 / 0.095 (3) | 0.723 / 0.273 (4) | 0.914 / 0.076 (4) | 0.103 / 0.101 |
| prod | 15 epochs (current best: ImageNet start) | 0.878 / 0.098 (3) | 0.894 / 0.077 (3) | 0.882 / 0.079 (3) | 0.779 / 0.183 (4) | 0.831 / 0.158 (4) | 0.048 / 0.048 |
| prod | 40 epochs (otherwise the same) | 0.903 / 0.081 (3) | 0.901 / 0.081 (3) | 0.894 / 0.067 (3) | 0.864 / 0.091 (4) | 0.847 / 0.137 (4) | 0.025 / 0.027 |
| dev | grow from leaf cores | 0.969 / 0.028 (7) | 0.934 / 0.063 (6) | 0.991 / 0.006 (5) | 0.964 / 0.031 (4) | 0.998 / 0.001 (3) | 0.025 / 0.025 |
| dev | 15 epochs (current best: ImageNet start) | 0.954 / 0.021 (7) | 0.953 / 0.024 (6) | 0.897 / 0.081 (5) | 0.922 / 0.027 (4) | 0.946 / 0.036 (3) | 0.025 / 0.025 |
| dev | 40 epochs (otherwise the same) | 0.959 / 0.018 (7) | 0.947 / 0.037 (6) | 0.906 / 0.058 (5) | 0.926 / 0.030 (4) | 0.961 / 0.019 (3) | 0.023 / 0.016 |

## Decision by the agreed rule

Rule: keep 40 ep only if it beats 15 ep for both rigs, in mean IoU and in mean abs(area ratio - 1), each by more than the fold-to-fold variation: the standard deviation over the 5 folds of the per-fold difference (the same cells under both, so the paired difference is the fair spread). Otherwise 15 ep stays.

| Rig | Mean IoU 40 ep - 15 ep | SD over folds | Mean abs(ratio-1) 15 ep - 40 ep | SD over folds | Per-fold IoU differences | Per-fold abs(ratio-1) differences | 40 ep better by more than the spread? |
|---|---|---|---|---|---|---|---|
| prod | +0.0310 | 0.0323 | +0.0309 | 0.0374 | +0.024 +0.007 +0.011 +0.085 +0.015 | +0.017 -0.004 +0.012 +0.092 +0.020 | no |
| dev | +0.0040 | 0.0079 | +0.0037 | 0.0151 | +0.005 -0.006 +0.009 +0.003 +0.015 | +0.003 -0.013 +0.024 -0.004 +0.017 | no |

**Decision by the rule: 15 epochs (the simpler setting).**

(Stage D2 decision, read from `stage_D2_decision.txt`: no public pre-training.)

## Seedlings on their own

Production "empty" cells (seedlings, A01, A02, A17) and every "size 1 of 5" cell. IoU / area ratio.

| Cell | Rig | Stratum | Truth px | grow from leaf cores | 15 epochs (current best: ImageNet start) | 40 epochs (otherwise the same) |
|---|---|---|---|---|---|---|
| A01 | prod | empty | 237 | 0.00 / 0.00 | 0.39 / 0.39 | 0.69 / 0.72 |
| A02 | prod | empty | 233 | 0.76 / 1.23 | 0.76 / 1.18 | 0.79 / 1.15 |
| A17 | prod | empty | 1376 | 0.77 / 0.80 | 0.78 / 0.81 | 0.77 / 0.80 |
| A05 | prod | size 1 of 5 | 704 | 1.00 / 1.00 | 0.85 / 1.15 | 0.87 / 1.15 |
| A06 | prod | size 1 of 5 | 677 | 1.00 / 1.00 | 0.92 / 1.05 | 0.90 / 1.08 |
| A30 | prod | blue mat, size 1 of 5 | 1124 | 0.94 / 0.94 | 0.89 / 0.94 | 0.88 / 0.94 |
| B02 | dev | size 1 of 5 | 5956 | 1.00 / 1.00 | 0.97 / 1.01 | 0.97 / 1.03 |
| B18 | dev | size 1 of 5 | 12076 | 0.99 / 1.00 | 0.90 / 0.95 | 0.93 / 0.99 |
| B27 | dev | size 1 of 5 | 7737 | 0.92 / 0.92 | 0.91 / 1.00 | 0.92 / 1.00 |
| B30 | dev | size 1 of 5 | 3483 | 1.00 / 1.00 | 0.88 / 1.09 | 0.90 / 1.08 |
| all 10 | | mean | |  | 0.83 / 0.140 (mean abs(ratio-1)) |  |
| all 10 | | mean | |  |  | 0.86 / 0.105 (mean abs(ratio-1)) |

## Training time per fold

| Fold | 15 epochs min | 40 epochs min | 40 epochs peak GPU MiB |
|---|---|---|---|
| 1 | 8.9 | 22.7 | 4301 |
| 2 | 8.8 | 22.9 | 4301 |
| 3 | 8.8 | 23.1 | 4301 |
| 4 | 8.8 | 22.8 | 4301 |
| 5 | 8.8 | 22.8 | 4301 |

## Training loss per epoch

`stage-E-loss.png`. Mean over the 5 folds of the training loss (BCE + dice on the training samples, with augmentation; not a held-out score). Both runs end with the learning rate at zero, so the last epochs flatten by construction; what matters is the level reached and whether the held-out scores above follow it.

| Epoch | 15 epochs | 40 epochs |
|---|---|---|
| 1 | 0.6268 | 0.6226 |
| 2 | 0.1037 | 0.1032 |
| 3 | 0.0808 | 0.0864 |
| 4 | 0.0674 | 0.0714 |
| 5 | 0.0659 | 0.0690 |
| 6 | 0.0615 | 0.0677 |
| 7 | 0.0571 | 0.0629 |
| 8 | 0.0543 | 0.0586 |
| 9 | 0.0529 | 0.0584 |
| 10 | 0.0508 | 0.0562 |
| 11 | 0.0489 | 0.0538 |
| 12 | 0.0481 | 0.0525 |
| 13 | 0.0467 | 0.0515 |
| 14 | 0.0458 | 0.0507 |
| 15 | 0.0460 | 0.0503 |
| 16 | | 0.0510 |
| 17 | | 0.0486 |
| 18 | | 0.0472 |
| 19 | | 0.0471 |
| 20 | | 0.0458 |
| 21 | | 0.0455 |
| 22 | | 0.0451 |
| 23 | | 0.0441 |
| 24 | | 0.0440 |
| 25 | | 0.0442 |
| 26 | | 0.0429 |
| 27 | | 0.0423 |
| 28 | | 0.0414 |
| 29 | | 0.0415 |
| 30 | | 0.0408 |
| 31 | | 0.0403 |
| 32 | | 0.0401 |
| 33 | | 0.0397 |
| 34 | | 0.0394 |
| 35 | | 0.0391 |
| 36 | | 0.0390 |
| 37 | | 0.0393 |
| 38 | | 0.0390 |
| 39 | | 0.0387 |
| 40 | | 0.0393 |

40 epochs, change of the mean loss over each quarter of the run: epochs 1-10: -0.5664, epochs 11-20: -0.0103, epochs 21-30: -0.0050, epochs 31-40: -0.0016. Last 5 epochs: +0.0002. 15 epochs ended at 0.0460; 40 epochs passed that level at epoch 20.


## Picture

`stage-E.png`: columns crop | truth | grow from leaf cores | old (15 epochs (current best: ImageNet start)) | new (40 epochs (otherwise the same)). The same 8 cells as stage A, by the same rules (the best/worst rules use stage A's half-resolution IoU, so they pick the same cells):

- A02: seedling: production "empty" cell with the smallest truth
- A27: blue mat: median truth size of the blue-mat cells
- A12: green soil, production: median truth size
- B03: green soil / moss, development: median truth size
- B24: "empty" development cell (dead or tiny plant): median truth size
- B23: largest plants (size 5 of 5): median truth size, both rigs
- B19: network best: highest half-resolution IoU of the cells not picked above
- A01: network worst: lowest half-resolution IoU of the cells not picked above

Files: `experiments/round4-segmentation-nn/code/train_cv.py` (method in its docstring), driver `~/temp.nobackup/npec-406-nn/analysis/train/run_de.sh`; per-fold scores `runs/<run>/scores*.csv`, predictions `pred/<run>/`, under `~/temp.nobackup/npec-406-nn/analysis/train/`.
