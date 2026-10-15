# Round 1: tray splitting and tray ID (issue #164)

Method, decision rule and results: `docs/metrology-log.md` section 15.5c. This file says how to run it.

## What was run

    PYTHONPATH=src python3 experiments/round1-trays/trays.py --set gaps        # 33 stills
    PYTHONPATH=src python3 experiments/round1-trays/trays.py --set touching    # 143 stills (not yet run)
    PYTHONPATH=src python3 experiments/round1-trays/trays.py --set gaps --limit 1   # quick check

Stills and `rig.db` are read only. Nothing is written into the experiment folder. Tag detections are
cached in `~/scratch/round1-trays/tags/` (delete to detect again); overlays go to
`~/scratch/round1-trays/<set>/<step>_<still>.jpg`. About 6 s per still the first time (full
resolution tag detection), under 1 s with the cache.

FastSAM on the Hailo-8 (needs the accelerator; the HEF in `~/scratch/round1-trays/hailo/`, from
`https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v2.17.0/hailo8/fast_sam_s.hef`):

    PYTHONPATH=src python3 experiments/round1-trays/fastsam.py --name NAME --margin 1.15 STILL [STILL ...]
    PYTHONPATH=src python3 experiments/round1-trays/fastsam.py --name NAME --tiles grid STILL [STILL ...]
    PYTHONPATH=src python3 experiments/round1-trays/diagnose.py fastsam-NAME.csv

- `--tiles tags` (default): 2-tray tiles placed from the A1 tags, reaching `--margin` trays past the
  outer tags. Use 1.15: at the old 0.75 the tiles cut trays off (27 of 54 missing trays).
- `--tiles grid`: 3000 px tiles every 1000 px over the table rows, no tag positions used.
- The fallback runs by default after the first pass (`--no-fallback` turns it off): around each
  tag whose tray was not found, 8 windows of 2600 px with the found trays painted grey.
- `diagnose.py` follows every tray without a mask through the stages (cut by the tile, low score,
  duplicate, never proposed, mask test) and writes `diagnose-NAME.csv`.

About 1.3 s per still with tag tiles and cached tags, 3.6 s with the grid; add about 4.5 s for the
first tag detection of a still. HailoRT writes `hailort.log` in the working directory (not tracked).

Overlays: `~/scratch/round1-trays/fastsam-stills-m<margin>[-fb]/` or `fastsam-stills-grid[-fb]/`, one per
still at 1/8 size (green OK, orange NO TAG, red MERGED; magenta line from each tag to its tray);
per tile `~/scratch/round1-trays/fastsam/<still>/<tile>.jpg` from the first version.

## Files

- `results-<set>.csv`: one row per still: calibration, validation, lens, tags found, method A and B
  counts, and `b_pass` (the decision rule in 15.5c).
- `fastsam-masks.csv`: first 2-still FastSAM test, one row per mask.
- `fastsam-NAME.csv`: one row per still: trays right, masks, no tag, merged, trays without mask,
  ambiguous tags, time per stage. `fastsam-NAME-masks.csv`: one row per tray mask kept.
- `diagnose-NAME.csv`: per tray without a mask, the furthest stage a candidate reached.
- `shapes-<set>.csv`: one row per blue shape: verdict (one tray, several trays, no tray), trays and
  tag IDs inside, slot by method A and B, fitted size east-west and north-south in mm, area in trays.

## Overlay key

Outline green: one tray. Red: several trays (MERGED). Orange: no tray tag (NO TAG). White: the
fitted rectangle. Magenta dot and number: a tray tag's centre and ID. Text: tray, slot by method B,
fitted size.
