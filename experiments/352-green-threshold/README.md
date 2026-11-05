# Green area detection: hand outlines and colour rules (#352)

Research scripts and data behind metrology log sections 24 to 24.8 (2026-11-04 and 05). The
write-up, the numbers and their limits are in `docs/metrology-log.md`; this folder keeps what is
needed to check them.

## Data

- `data/imagej/`: the 15 plant crops cut from production still `2026-11-03_105853_597207`
  (capture 19380) at native pixels (plus `t6_p1b`, the replacement for the cut-off `t6_p1`),
  `manifest.csv` (each crop's corner in the full still and the tray's mm2 per px), Aaron's
  rulebook `RULES.txt` and instructions `README.txt`, and his two passes of outlines
  (`pass_1_2026.11.04_Results.csv` and `.roi.zip`, `pass_2_2026.11.05_Results.csv` and `.roi.zip`).
  Pass 1 row 17 is the `t6_p1b` outline that was saved; row 16 is a first try without a saved
  outline; row 11 (`t6_p1`) is not used. One outline per pass was saved only as its box.
- `data/results/`: per-plant, per-tray and per-photo outputs, named by log section.
  `check-2026-11-03-rows.jsonl` is the #352 development check of 2026-11-03 (the issue comment).

The production photos are not copied here; they stay in experiment 18's folder on `ac-testing`.
The JPEG frames of 24.6 stay on `npec-rig-01` (`~/jpegq-355/run-20261105T122904Z/`).

## Code

Written for one investigation, not for reuse: paths point at `/home/pi/scratch/thr-352/` on the
controller (`testpi-02`), where the photos were copied read-only. They were run with uv in a
throwaway environment, for example

    uv run --no-project --with numpy --with pillow --with opencv-python-headless --with scipy python -I code/ts.py ...

| Script | Section | What it does |
|---|---|---|
| `analyse.py` | issue check | Greenness peaks and cuts per tray on six production stills |
| `imagej_crops.py` | 24 | Cuts the plant crops for ImageJ |
| `rois.py` | 24 on | Reads ImageJ `.roi` files and turns outlines into pixels as ImageJ counts them |
| `compare.py` | 24 | Rules A to D against both passes, the picture sheets |
| `whole_tray.py`, `whole_tray_notag.py`, `tray4.py` | 24 | Rules over whole trays, tray 4 histograms |
| `fixed_cut.py` | 24.1 | Rule E (fixed low cutoff) on the crops and six days |
| `core_grow.py`, `sequence.py` | 24.2 | Grow from cores, and the 31-photo sequence |
| `ts.py`, `ts_summary.py`, `ts_lost_sheet.py`, `bench.py` | 24.3 | Time series, lost plants, time and memory per photo |
| `mats.py`, `mats_summary.py`, `leaf_colour.py` | 24.4 | Green squares on blue mats, colours of plastic, mat and leaf |
| `sam_crops.py` | 24.5 | SAM 2.1 small (ONNX) on the crops |
| `jpegq.py` | 24.6 | Rules on the #355 same-frame JPEG versions |
| `ruleg.py`, `check_dev.py`, `check_prod_crops.py` | 24.7 | Rule G and its three checks |
| `check_dev_h.py`, `check_prod_crops_h.py` | 24.8 | Rule H and its three checks |

`ruleg.py` imports the app's tray-tag detector (`npec_rig.tags`); nothing in `src/` imports this
folder.
