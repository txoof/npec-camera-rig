# Stage C: training windows shifted up to 128 px

Written by `train_cv.py compare --stage C` (2026-11-20 22:38 UTC). Development check. Training cells only (42: production 17, development 25); no test cell was opened.
Half resolution (S = 2), the stage A recipe otherwise. Every cell is scored once, by the fold model that never saw its UTC day. Production cells: network on the whole photo; development cells: on the crop alone. Threshold probability 0.5, float32.

What changed: only the training crop jitter. The 5 half-resolution folds retrained with patches of 512 px (256 + 2 x 128) around the same grid squares as stage A (same photos, same squares kept, same seed for the square selection), so a training window can be shifted up to 128 px from its square instead of 32. Everything else as stage A. Read the way that won stage B: **stride 192, middle kept**. Compared with the best of A and B by the rule (A).

## Results per rig

| Rig | Method | Pooled IoU | Mean IoU | Lowest IoU | Mean abs(area ratio - 1) | Pooled area ratio |
|---|---|---|---|---|---|---|
| production (17) | grow from leaf cores | 0.945 | 0.885 | 0.000 | 0.114 | 0.982 |
| production (17) | A: jitter 32, stride 192 middle kept | 0.894 | 0.847 | 0.388 | 0.125 | 0.953 |
| production (17) | B: jitter 32, stride 128 averaged | 0.894 | 0.848 | 0.409 | 0.125 | 0.953 |
| production (17) | C: jitter 128, read stride 192 middle kept | 0.896 | 0.864 | 0.689 | 0.112 | 0.962 |
| development (25) | grow from leaf cores | 0.977 | 0.968 | 0.838 | 0.029 | 1.007 |
| development (25) | A: jitter 32, stride 192 middle kept | 0.929 | 0.936 | 0.811 | 0.037 | 1.040 |
| development (25) | B: jitter 32, stride 128 averaged | 0.928 | 0.936 | 0.810 | 0.037 | 1.040 |
| development (25) | C: jitter 128, read stride 192 middle kept | 0.935 | 0.942 | 0.828 | 0.031 | 1.039 |

**Corrected cells only** (the 30 truths Aaron corrected; on the other 12, grow from leaf cores scores 1.000 by construction):

| Rig | Method | Pooled IoU | Mean IoU | Lowest IoU | Mean abs(area ratio - 1) | Pooled area ratio |
|---|---|---|---|---|---|---|
| production (10) | grow from leaf cores | 0.926 | 0.804 | 0.000 | 0.193 | 0.975 |
| production (10) | A: jitter 32, stride 192 middle kept | 0.896 | 0.816 | 0.388 | 0.153 | 0.956 |
| production (10) | B: jitter 32, stride 128 averaged | 0.895 | 0.817 | 0.409 | 0.153 | 0.956 |
| production (10) | C: jitter 128, read stride 192 middle kept | 0.900 | 0.846 | 0.689 | 0.125 | 0.969 |
| development (20) | grow from leaf cores | 0.975 | 0.960 | 0.838 | 0.036 | 1.008 |
| development (20) | A: jitter 32, stride 192 middle kept | 0.926 | 0.935 | 0.811 | 0.038 | 1.043 |
| development (20) | B: jitter 32, stride 128 averaged | 0.926 | 0.934 | 0.810 | 0.038 | 1.043 |
| development (20) | C: jitter 128, read stride 192 middle kept | 0.932 | 0.940 | 0.828 | 0.034 | 1.042 |

## Fold to fold

Mean IoU / mean abs(area ratio - 1) of each fold's held-out cells (cells per fold in brackets).

| Rig | Method | fold 1 | fold 2 | fold 3 | fold 4 | fold 5 | SD of folds |
|---|---|---|---|---|---|---|---|
| prod | grow from leaf cores | 0.931 / 0.083 (3) | 1.000 / 0.000 (3) | 0.900 / 0.095 (3) | 0.723 / 0.273 (4) | 0.914 / 0.076 (4) | 0.103 / 0.101 |
| prod | A: jitter 32, stride 192 middle kept | 0.878 / 0.098 (3) | 0.894 / 0.077 (3) | 0.882 / 0.079 (3) | 0.779 / 0.183 (4) | 0.831 / 0.158 (4) | 0.048 / 0.048 |
| prod | B: jitter 32, stride 128 averaged | 0.879 / 0.099 (3) | 0.895 / 0.075 (3) | 0.883 / 0.081 (3) | 0.784 / 0.178 (4) | 0.829 / 0.160 (4) | 0.047 / 0.047 |
| prod | C: jitter 128, read stride 192 middle kept | 0.876 / 0.102 (3) | 0.895 / 0.088 (3) | 0.871 / 0.112 (3) | 0.857 / 0.095 (4) | 0.833 / 0.154 (4) | 0.023 / 0.026 |
| dev | grow from leaf cores | 0.969 / 0.028 (7) | 0.934 / 0.063 (6) | 0.993 / 0.006 (5) | 0.964 / 0.031 (4) | 0.998 / 0.001 (3) | 0.026 / 0.025 |
| dev | A: jitter 32, stride 192 middle kept | 0.954 / 0.021 (7) | 0.953 / 0.024 (6) | 0.897 / 0.083 (5) | 0.922 / 0.027 (4) | 0.946 / 0.036 (3) | 0.024 / 0.026 |
| dev | B: jitter 32, stride 128 averaged | 0.953 / 0.022 (7) | 0.953 / 0.024 (6) | 0.898 / 0.082 (5) | 0.922 / 0.028 (4) | 0.945 / 0.036 (3) | 0.024 / 0.025 |
| dev | C: jitter 128, read stride 192 middle kept | 0.959 / 0.013 (7) | 0.950 / 0.027 (6) | 0.904 / 0.081 (5) | 0.934 / 0.012 (4) | 0.964 / 0.021 (3) | 0.024 / 0.028 |

## Decision by the agreed rule

Rule: keep C only if it beats A for both rigs, in mean IoU and in mean abs(area ratio - 1), each by more than the fold-to-fold variation: the standard deviation over the 5 folds of the per-fold difference (the same cells under both, so the paired difference is the fair spread). Otherwise A stays.

| Rig | Mean IoU C - A | SD over folds | Mean abs(ratio-1) A - C | SD over folds | Per-fold IoU differences | Per-fold abs(ratio-1) differences | C better by more than the spread? |
|---|---|---|---|---|---|---|---|
| prod | +0.0165 | 0.0366 | +0.0132 | 0.0465 | -0.002 +0.001 -0.012 +0.078 +0.002 | -0.004 -0.011 -0.033 +0.088 +0.004 | no |
| dev | +0.0059 | 0.0075 | +0.0061 | 0.0077 | +0.005 -0.002 +0.006 +0.011 +0.018 | +0.008 -0.003 +0.002 +0.014 +0.015 | no |

**Decision by the rule: jitter 32 (the simpler setting).**

(Stage B decision, recomputed here from the same scores: A kept.)

## Seedlings on their own

Production "empty" cells (seedlings, A01, A02, A17) and every "size 1 of 5" cell. IoU / area ratio.

| Cell | Rig | Stratum | Truth px | grow from leaf cores | A: jitter 32, stride 192 middle kept | B: jitter 32, stride 128 averaged | C: jitter 128, read stride 192 middle kept |
|---|---|---|---|---|---|---|---|
| A01 | prod | empty | 237 | 0.00 / 0.00 | 0.39 / 0.39 | 0.41 / 0.41 | 0.69 / 0.72 |
| A02 | prod | empty | 233 | 0.76 / 1.23 | 0.76 / 1.18 | 0.76 / 1.19 | 0.73 / 1.29 |
| A17 | prod | empty | 1376 | 0.77 / 0.80 | 0.78 / 0.81 | 0.78 / 0.81 | 0.78 / 0.80 |
| A05 | prod | size 1 of 5 | 704 | 1.00 / 1.00 | 0.85 / 1.15 | 0.85 / 1.16 | 0.86 / 1.15 |
| A06 | prod | size 1 of 5 | 677 | 1.00 / 1.00 | 0.92 / 1.05 | 0.92 / 1.05 | 0.90 / 1.06 |
| A30 | prod | blue mat, size 1 of 5 | 1124 | 0.94 / 0.94 | 0.89 / 0.94 | 0.89 / 0.94 | 0.90 / 0.95 |
| B02 | dev | size 1 of 5 | 5956 | 1.00 / 1.00 | 0.97 / 1.01 | 0.97 / 1.01 | 0.97 / 1.01 |
| B18 | dev | size 1 of 5 | 12076 | 0.99 / 1.00 | 0.90 / 0.95 | 0.90 / 0.95 | 0.95 / 1.02 |
| B27 | dev | size 1 of 5 | 7737 | 0.92 / 0.92 | 0.91 / 1.00 | 0.91 / 1.00 | 0.92 / 1.00 |
| B30 | dev | size 1 of 5 | 3483 | 1.00 / 1.00 | 0.88 / 1.09 | 0.88 / 1.09 | 0.92 / 0.97 |
| all 10 | | mean | |  | 0.83 / 0.140 (mean abs(ratio-1)) |  |  |
| all 10 | | mean | |  |  |  | 0.86 / 0.110 (mean abs(ratio-1)) |

## Time per full photo, float32 network on the RTX 2060 SUPER, half resolution

| Read | Tiles (256) | Stride | Seconds (median of 3, after warm-up; excludes JPEG decode) | JPEG decode s |
|---|---|---|---|---|
| A, middle kept | 432 | 192 | 1.19 (1.18 1.19 1.19) | 0.4 |
| B, averaged | 945 | 128 | 2.59 (2.54 2.65 2.59) | 0.4 |

Measured the same way as stage A (one production photo, scale, tiles, blend and resize back to full size included), both in this session. Stage A measured the middle-kept read at 1.71 s per photo in its own session; the same code here took about 1.2 s, so compare B with A only within this table. Stage C changes only training, so its reading time is that of the read it uses.

## Training time per fold

| Fold | A (jitter 32) min | C (jitter 128) min | C peak GPU MiB |
|---|---|---|---|
| 1 | 8.9 | 8.8 | 4301 |
| 2 | 8.8 | 8.8 | 4301 |
| 3 | 8.8 | 8.8 | 4301 |
| 4 | 8.8 | 8.8 | 4301 |
| 5 | 8.8 | 8.8 | 4301 |

## Picture

`stage-C.png`: columns crop | truth | grow from leaf cores | old (A: jitter 32, stride 192 middle kept) | new (C: jitter 128, read stride 192 middle kept). The same 8 cells as stage A, by the same rules (the best/worst rules use stage A's half-resolution IoU, so they pick the same cells):

- A02: seedling: production "empty" cell with the smallest truth
- A27: blue mat: median truth size of the blue-mat cells
- A12: green soil, production: median truth size
- B03: green soil / moss, development: median truth size
- B24: "empty" development cell (dead or tiny plant): median truth size
- B23: largest plants (size 5 of 5): median truth size, both rigs
- B19: network best: highest half-resolution IoU of the cells not picked above
- A01: network worst: lowest half-resolution IoU of the cells not picked above

Files: `experiments/round4-segmentation-nn/code/train_cv.py` (method in its docstring), driver `~/temp.nobackup/npec-406-nn/analysis/train/run_bc.sh`; per-fold scores `runs/<run>/scores*.csv`, predictions `pred/<run>/`, under `~/temp.nobackup/npec-406-nn/analysis/train/`.
