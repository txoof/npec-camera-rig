# Stage G: the final network compiled for both Hailo chips, and the 8-bit loss on the truth cells

Written by `final_fg.py stage_g` (2026-11-21 11:56 UTC). Development check, Hailo's emulator only: no HEF has run on a chip and no rig was touched. Training cells only (42: production 17, development 25); no test cell was opened.

## 1. Method

- Compiled at optimisation level 1 on the CPU, compression level 0, the trial A way (`hailo_final.py`, `notes/hailo.md` section 13): ONNX opset 13, ImageNet normalisation in the model script, so the HEF takes uint8 RGB 256 x 256 tiles. Hailo-8 with DFC 3.33.1, Hailo-10H with DFC 5.1.0.
- Calibration: **1024 tiles** per model (the DFC's suggested 1024), from the training photo patches only (`cache/s2/mm`, centre 256 px), half with plant and half without, shared equally over the UTC dates. Each stage E fold model was calibrated only on tiles of its own training dates, never its held-out dates; the final network on tiles of every training date.
- Models: the final network (compiled to HEFs, the network that ships) and the 5 stage E fold models (quantised and emulated only, not compiled to HEFs: they exist to measure the 8-bit loss by cross-validation).
- Scoring: each training cell scored by the stage E fold model that never saw its day, exactly as the float scores are made: production cells from the **whole photo** at half resolution, development cells from the crop; 256 px tiles at stride 192, logits blended keeping each tile's middle, bilinear resize back to full size, threshold at logit 0 (probability 0.5). The quantised logits come from the emulator (SDK_QUANTIZED) on the same tiles, stitched by the same code. Before any quantised run, the float logits of the same tiles were stitched with this code and compared with stage E's saved masks: 0 pixels differ over all 42 cells, so the only change between float and quantised is the network.
- Float = the stage E fold models in float32 (torch), scored on the current truths (after the purple check).

## 2. Compile results (final network)

| | Hailo-8 (DFC 3.33.1) | Hailo-10H (DFC 5.1.0) |
|---|---|---|
| compile result | HEF written, no errors | HEF written, no errors |
| optimise time (level 1, CPU) | 25.8 min | 46.8 min |
| optimise peak memory (process + largest child) | 11.1 GiB | 11.3 GiB |
| output signal-to-noise ratio after quantisation | 24.35 dB | 24.45 dB |
| compile time | 1.8 min | 17.0 min |
| contexts | 1 | 3 |
| compiler speed estimate (profiler) | 147.37 FPS, latency 13.26 ms | N/A, latency N/A |
| HEF | `hailo/final/hailo8_L1/plantseg_s2_final_e40_hailo8.hef` | `hailo/final/hailo10h_L1/plantseg_s2_final_e40_hailo10h.hef` |
| HEF size | 6,171,502 bytes | 6,083,944 bytes |
| HEF sha256 | `6c0cedd31ec70260ea96c7b62658ac6a445941ec0de28aa8585fa638372ce0ee` | `5c54fe40bab1de0504b7e7405f35ea11bf16589e09534ca6bda861d8d429a2d2` |
| quantised against float, 200 check tiles: mean abs logit difference | 0.576 | 0.575 |
| quantised against float, 200 check tiles: mask IoU at 0.5 | 0.9864 | 0.9865 |

Copies of both HEFs sit directly in `hailo/final/`. The 200 check tiles are training patches not used for calibration (seen in training; 100 with plant), compared with the float network, as in trial A (level 1 there: mean abs logit difference 0.342, mask IoU 0.985).

Arithmetic, not measured: one half-resolution photo read as in stage A (432 tiles) is 432 / 147 = 2.9 s of Hailo-8 time at the compiler's estimate.

Stage E fold models (quantised for the cross-validation, not compiled):

| Fold | Held-out dates | Calibration tiles | Calibration dates | Optimise min, Hailo-8 | Optimise min, Hailo-10H | SNR dB, Hailo-8 | SNR dB, Hailo-10H | Cell tiles emulated | Emulator s per tile, Hailo-8 | Emulator s per tile, Hailo-10H |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 10-12, 10-19, 10-28, 11-04, 11-13, 11-18 | 1024 | 24 | 24.1 | 49.7 | 27.59 | 27.54 | 895 | 0.198 | 0.323 |
| 2 | 10-14, 10-20, 10-25, 10-26, 11-03, 11-14, 11-19 | 1024 | 24 | 33.3 | 46.4 | 24.82 | 24.83 | 891 | 0.31 | 0.333 |
| 3 | 10-15, 10-23, 11-07, 11-10, 11-15, 11-20 | 1024 | 24 | 29.9 | 49.7 | 26.17 | 26.02 | 887 | 0.335 | 0.29 |
| 4 | 10-16, 10-22, 10-31, 11-09, 11-11, 11-16 | 1024 | 24 | 32.0 | 46.5 | 23.68 | 23.64 | 1316 | 0.296 | 0.326 |
| 5 | 10-18, 10-29, 11-01, 11-06, 11-12, 11-17 | 1024 | 24 | 31.3 | 47.5 | 28.89 | 28.84 | 1312 | 0.324 | 0.205 |

## 3. 8-bit loss on the truth cells, cross-validated

Each cell scored by the stage E fold model that never saw its day. Whole photos for production cells.

| Rig | Network | Mean IoU (0 to 1, higher is better) | Mean area error (%, lower is better) | Pooled IoU (0 to 1, higher is better) | Lowest IoU | Pooled area ratio |
|---|---|---|---|---|---|---|
| production (17) | float32 (torch) | 0.8784 | 9.40 | 0.9090 | 0.689 | 0.9667 |
| production (17) | Hailo-8, quantised (emulator) | 0.8790 | 8.81 | 0.9079 | 0.722 | 0.9833 |
| production (17) | Hailo-10H, quantised (emulator) | 0.8792 | 8.83 | 0.9077 | 0.724 | 0.9826 |
| development (25) | float32 (torch) | 0.9394 | 3.31 | 0.9312 | 0.805 | 1.0266 |
| development (25) | Hailo-8, quantised (emulator) | 0.9356 | 4.10 | 0.9310 | 0.813 | 1.0321 |
| development (25) | Hailo-10H, quantised (emulator) | 0.9355 | 4.10 | 0.9308 | 0.813 | 1.0320 |

The difference, quantised minus float (negative IoU and positive area error mean the 8-bit network is worse), with the spread over the 5 folds (standard deviation of the per-fold differences, same cells under both):

| Rig | Chip | Mean IoU difference | SD over folds (IoU) | Mean area error difference (percentage points) | SD over folds (percentage points) | Pooled IoU difference |
|---|---|---|---|---|---|---|
| production | Hailo-8 | +0.0006 | 0.0049 | -0.59 | 2.31 | -0.0011 |
| production | Hailo-10H | +0.0008 | 0.0040 | -0.57 | 2.24 | -0.0013 |
| development | Hailo-8 | -0.0038 | 0.0081 | +0.79 | 1.43 | -0.0002 |
| development | Hailo-10H | -0.0039 | 0.0083 | +0.79 | 1.47 | -0.0004 |

Per fold, quantised minus float:

| Rig | Chip | Measure | fold 1 | fold 2 | fold 3 | fold 4 | fold 5 |
|---|---|---|---|---|---|---|---|
| production | Hailo-8 | mean IoU | +0.0003 | -0.0019 | -0.0069 | +0.0060 | +0.0028 |
| production | Hailo-8 | mean area error (percentage points) | -0.71 | +1.05 | +2.36 | -3.77 | -0.77 |
| production | Hailo-10H | mean IoU | +0.0001 | +0.0004 | -0.0056 | +0.0057 | +0.0014 |
| production | Hailo-10H | mean area error (percentage points) | -0.72 | +1.05 | +2.24 | -3.70 | -0.67 |
| development | Hailo-8 | mean IoU | -0.0013 | -0.0019 | -0.0006 | -0.0187 | +0.0011 |
| development | Hailo-8 | mean area error (percentage points) | +0.22 | +0.15 | +0.94 | +3.34 | -0.21 |
| development | Hailo-10H | mean IoU | -0.0014 | -0.0019 | -0.0009 | -0.0191 | +0.0012 |
| development | Hailo-10H | mean area error (percentage points) | +0.21 | +0.16 | +0.91 | +3.40 | -0.25 |

How far quantisation moves the masks themselves (pooled IoU of the quantised mask against the float mask, over the cells of the rig; 1 = identical):

| Rig | Hailo-8 | Hailo-10H |
|---|---|---|
| production | 0.9779 | 0.9783 |
| development | 0.9901 | 0.9901 |

## 4. Seedlings on their own

Production "empty" cells (seedlings, A01, A02, A17) and every "size 1 of 5" cell, each scored by its held-out stage E fold model.

| Cell | Rig | Truth px | IoU, float | IoU, Hailo-8 | IoU, Hailo-10H | Area ratio, float | Area ratio, Hailo-8 | Area ratio, Hailo-10H |
|---|---|---|---|---|---|---|---|---|
| A01 | production | 237 | 0.689 | 0.722 | 0.724 | 0.717 | 0.852 | 0.848 |
| A02 | production | 233 | 0.789 | 0.771 | 0.774 | 1.150 | 1.227 | 1.223 |
| A17 | production | 1376 | 0.768 | 0.767 | 0.767 | 0.795 | 0.793 | 0.794 |
| A05 | production | 704 | 0.868 | 0.862 | 0.862 | 1.146 | 1.151 | 1.151 |
| A06 | production | 677 | 0.904 | 0.903 | 0.906 | 1.084 | 1.097 | 1.097 |
| A30 | production | 1124 | 0.885 | 0.892 | 0.889 | 0.939 | 0.993 | 0.993 |
| B02 | development | 5956 | 0.967 | 0.963 | 0.963 | 1.030 | 1.033 | 1.034 |
| B18 | development | 12076 | 0.934 | 0.938 | 0.938 | 0.988 | 0.995 | 0.995 |
| B27 | development | 7737 | 0.918 | 0.924 | 0.924 | 0.997 | 1.019 | 1.019 |
| B30 | development | 3483 | 0.896 | 0.857 | 0.857 | 1.076 | 1.133 | 1.133 |

| All 10 seedling cells | Mean IoU (0 to 1, higher is better) | Mean area error (%, lower is better) |
|---|---|---|
| float32 (torch) | 0.8618 | 10.50 |
| Hailo-8, quantised (emulator) | 0.8599 | 10.28 |
| Hailo-10H, quantised (emulator) | 0.8603 | 10.27 |

## Picture

`stage-G.png`: colour crop | truth | float | Hailo-8 quantised | Hailo-10H quantised, the same 8 cells as stage A:

- A02: seedling: production "empty" cell with the smallest truth
- A27: blue mat: median truth size of the blue-mat cells
- A12: green soil, production: median truth size
- B03: green soil / moss, development: median truth size
- B24: "empty" development cell (dead or tiny plant): median truth size
- B23: largest plants (size 5 of 5): median truth size, both rigs
- B19: network best in stage A: highest half-resolution IoU of the cells not picked above
- A01: network worst in stage A: lowest half-resolution IoU of the cells not picked above

Files: `experiments/round4-segmentation-nn/code/hailo_final.py` (method in its docstring) and `final_fg.py`; driver `~/temp.nobackup/npec-406-nn/analysis/train/run_fg.sh`; final network HEFs, HARs and logs in `~/temp.nobackup/npec-406-nn/hailo/final/`; fold models in `hailo/stage-G/f<k>/` (k = fold - 1); quantised masks in `analysis/train/pred/s2_e40_q_<chip>/`.

## Notes (added by hand after the run, 2026-11-21)

- **Quantisation marks slightly more plant.** Pooled area ratio rises on both rigs (production 0.967 to 0.983, development 1.027 to 1.032). On production this cancels part of the float network's under-marking, which is why production area error falls; on development it adds to over-marking, so development area error rises by 0.8 percentage points.
- **The loss depends on the model.** Most of the development loss comes from fold 4's model (held-out day 2026-11-09): quantised, it marks 4 to 6% more area on B28, B29 and B30 (B30 IoU 0.896 to 0.857). Its SNR after quantisation is the lowest of the five (23.7 dB). The other folds move development mean IoU by 0.002 or less. Every difference is inside one fold-to-fold standard deviation.
- **The final network's own 8-bit loss cannot be scored on the truth cells**, because it saw all of them. Its SNR (24.4 dB) falls inside the fold models' range (23.7 to 28.9 dB). On the 200 check tiles its quantised masks match its float masks at IoU 0.986. Trial A's 0.985 was measured on a check set that was only 1% plant, so the two figures are not directly comparable. The mean absolute logit difference is also larger than in trial A (0.58 against 0.34). The check sets differ (half plant here), and the cause was not looked into further.
- **The two chips quantise the same way** to the third decimal, as in trial A.
