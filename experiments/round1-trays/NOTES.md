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

FastSAM on the Hailo-8 (needs the accelerator; the HEF in `~/scratch/round1-trays/hailo/`):

    PYTHONPATH=src python3 experiments/round1-trays/fastsam.py STILL [STILL ...]

Overlays: `~/scratch/round1-trays/fastsam/<still>/<tile>.jpg`, the tile on the left and the tray-shaped
masks on the right (green: one tray, orange: no tag, red: several trays).

## Files

- `results-<set>.csv`: one row per still: calibration, validation, lens, tags found, method A and B
  counts, and `b_pass` (the decision rule in 15.5c).
- `fastsam-masks.csv`: one row per FastSAM mask: area in trays, fill, size, whether tray-shaped, tags, verdict.
- `shapes-<set>.csv`: one row per blue shape: verdict (one tray, several trays, no tray), trays and
  tag IDs inside, slot by method A and B, fitted size east-west and north-south in mm, area in trays.

## Overlay key

Outline green: one tray. Red: several trays (MERGED). Orange: no tray tag (NO TAG). White: the
fitted rectangle. Magenta dot and number: a tray tag's centre and ID. Text: tray, slot by method B,
fitted size.
