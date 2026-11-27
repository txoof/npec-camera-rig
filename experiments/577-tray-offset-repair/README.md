# Tray boundaries on the production rig (investigation, 2026-11-27)

Issue #577. **Work in progress**: research scripts only, nothing in `src/` is changed, nothing was written on production.
The write-up below was made on 2026-11-27 and its paths point at the controller's `~/scratch/tray-boundaries/`.

Picture: `compare_319.png` in this folder (the app now, left; the prototype, right).

## What happens

Production, experiment 2 ("Preliminary test parent lines"), photo 319 (2026-11-27 13:20 UTC). Ten trays lie touching in
two rows of five. An eleventh tray (tag 27) lies to their left, shifted down by about half a tray, so it straddles the
boundary between the two rows. The same 12 outlines are found in all 41 daytime photos of this layout (09:40 to 13:20 UTC).

Cause (`tray_placement.find_outlines`, `_cells`): the blue rims of touching trays form one blob. The blob's bounding
rectangle is cut into a uniform grid of tray-sized cells (here 6 x 2 = 12). A tray that does not sit on that grid cannot be
represented. The app reproduces exactly: I ran the app's own finder on the copied photo with the production calibration and got
the same 12 outlines as `tray_reading` in production's `rig.db`.

## What it costs in the numbers

Known answer for the left tray, by eye on the full-size crop: x 257 to 1746, y 2774 to 4564 px (centre 1001, 3669).
The app's two outlines are centred at y = 2696 and y = 4504, which is 970 px and 835 px (about 196 mm and 169 mm) off.

- Tag 27 gets the upper outline. Its 20 cells span y 2010 to 3382; the tray really spans 2774 to 4564. Only 4 of the 20 cells hold any
  green, while the plants are in the lower rows. Tray 27's cell areas are wrong.
- The lower outline has no tag ("no tag"): 82.3 mm2 of plant is counted there, not in tray 27 (6.6 mm2).
- No warning says so. Tray 27 only carries "partly outside the photo", which is also false for it. That warning is on all 12 outlines,
  because the frame-edge flag belongs to the whole blob, not to each cell. That is a separate small bug.

By the rules in CLAUDE.md this is "wrong numbers with no warning": a High priority, current round issue. I have not filed it.

## Options tried (all on copied data, nothing on a rig)

| Option | Photo 319 | Old test stills (44, with known answers) | Time | Verdict |
|---|---|---|---|---|
| A. The app now (blue rim, uniform grid cut) | 12 outlines, left tray split | prod 12/12, dev 8/8, hard 11/11 (+0.22 extra per still) | 0.4 s | Fails on this layout |
| B. Method E from log section 20 (rectangles fitted to the picture, tags off) | 7 of 11 trays, 1 false; left tray at (1008, 3680), right | not rerun | 26 s | Too slow, loses trays |
| C. Ring fit only: tray-sized rectangle whose outer rim loop the blue rim covers | 11 trays, left tray at (1006, 3672) | prod 11/12, dev 6/8: worse than A | 0.6 s | Do not replace A |
| D. A, then repair only cells the blue rim does not support (ring score under 0.45 after clipping for the frame edge), repair must move the tray by at least a quarter of its size | 11 trays, one per tray; left tray at (1006, 3672), 1 mm from the known centre | identical to A on all 44 stills; on 24 held-out stills (Aaron judged A right on 22 lit ones) outlines identical to A, one cell labelled "weak" | 6 to 9 s here (can be made faster) | Best so far |

Three things D shows besides the fix. (1) The ring score separates well on 319: the two bad cells score 0.38 and the regular trays 0.61 to 0.92 once the
frame edge is allowed for. (2) A lattice cell that the rim does not support can carry a "weak" warning, even where it cannot be repaired.
(3) The first version of D (no minimum move) moved one edge tray by about 20 px at quarter size on a held-out still where A was right; the minimum move removed that.
The 0.45, 0.60 and quarter-tray values are decisions, not measurements.

## Limits of the evidence

- One real failing layout, one production photo (the other 40 are repeats of it). Repair is shown to work on one case. Nothing here shows it works on other offset layouts (tray turned sideways, two offset trays, a tray offset along the row).
- The old 44 + 24 stills prove D does no harm there (outlines unchanged), not that D fixes anything there: none of them has a lattice failure.
- Known answer for the left tray is one person's (agent's) reading of a full-size crop, good to about 10 px. The top and bottom plastic edges of the ten regular trays are within 6 mm of the app's outlines in y. The left-right positions of regular trays were not measured independently:
  A and C differ by 3 to 18 mm there, and which is closer is not known. Not claimed either way.
- Right-edge trays (partly outside the frame) are the weak spot of any ring fit; D leaves them to the lattice.
- Timing is on the controller with 800 MB free memory; production (Pi 5, 4 GB, no Hailo) was not tried.
- These are development checks, not validations. Nothing is written into `docs/metrology-log.md` yet; it should be, with the method written first, if this goes ahead.

## Not tried

- Using the tags (each tray holds one tag; here 11 tags and 12 outlines is itself a signal). Section 20.1 found tag-led placement failed when tags lay anywhere in the tray.
- Asking researchers to leave a gap or keep trays on a grid: ruled out by CLAUDE.md (trays touch, researchers will not reliably leave gaps).

## Reproduce

```
export PYTHONPATH=~/npec_camera_rig/src   # venv: uv venv --system-site-packages, then opencv-python-headless numpy pillow
python scripts/reproduce.py prod-copy/photos/132050_172958.jpg prod-copy/calibration/20261125T132847632943.json prod-copy/photos/319_tags.json repro_319.png
python scripts/hybrid_319.py prod-copy/photos/132050_172958.jpg hybrid_319.png
python scripts/score_rig.py prod|dev|hard      # needs the old stills in ~/.claude/jobs/44c5d2e5/tmp
```

## Picking this up (#577)

- What is in this folder: `scripts/hybrid.py` is the repair (the core to port into `tray_placement.py`, test-first, once Aaron agrees the seams); `scripts/methods_ring.py` and `scripts/methods_hybrid.py` are finders in the interface of `experiments/round3-tray-outlines/harness.py`; `scripts/score_rig.py` scores one set (prod, dev, hard); the rest are one-off checks. `data/` holds the production calibration of 2026-11-25 (`20261125T132847632943.json`), the saved tag detections of photo 319 and its capture record.
- Not in the repo: the 10 MB photo `132050_172958.jpg` (production, `experiments/2026-11-26_0d21bcf9/stills/2026-11-27/`, copy it again from `d6-daylight`, read only) and the `rig.db` copy.
- Hard-coded paths: the scripts point at the controller (`/home/pi/.claude/jobs/44c5d2e5/tmp` for the old stills of log 20, `~/scratch/tray-boundaries/` for the photo). Those stills are not kept: re-make them from the rigs or take the held-out and hard sets named in metrology log 20 and 20.1.
- Run scripts with a venv that has opencv-python-headless, numpy and pillow, and `PYTHONPATH=<worktree>/src`. Run the harness scripts one rig at a time in the foreground: a single 44-still batch run was killed twice on the controller (memory, about 800 MB free).
- First step in the issue: test against more stills from the potato-free production experiment backed up on `media-server`.
