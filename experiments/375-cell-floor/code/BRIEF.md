# Shared brief for the #375 rule agents

Project: npec-camera-rig, plant growth monitoring. A Raspberry Pi camera photographs growth trays
from above. A green threshold (ExG >= 0.1 and G > R, `src/npec_rig/segmentation.py` in
`~/wt/npec-375-cell-floor`, read only) makes a plant mask. Each tray's cells (pots) are placed
from its AprilTag. A cell's area is the plant pixels counted for it (`segmentation.measure_cells`).

## The problem
An empty cell reads "plant" because the tray walls leave a thin green fringe in the mask near
the pot's edge. Seedlings' first leaves are as small as that fringe (both 0 to 10 mm2). The
owner, Aaron, describes a grow: days 1 to 3 a few green pixels round the edge and no plant; day 4
tiny leaves on the soil; day 5 most green in the centre of the pot with a solid core; day 10
obviously a plant. He does NOT want a fixed, hard-coded minimum area (mm2 or pixels): it breaks
when lighting changes or researchers do something new. Rules must adapt to the data or rest on
geometry the rig already knows (the pot outline, mm per px), not on tuned absolute sizes.

Baseline (any plant pixel = plant): 29 to 34% of empty-cell crops read plant; 71% of production
seedlings on days 0 to 2 found. A 100 mm2 minimum: 9 to 13% false, 0% of seedlings found until
day 14. Beat both.

## The dataset (read only): `~/scratch/375-cell-floor/data/`
Read `data/README.md` first. `index.csv` / `index.jsonl`: one row per crop (photo x cell) with the
RGB crop, the mask crop, the pot opening polygon in crop px, mm per px, day number, exposure, the
current rule's reading. `labels.csv`: hand labels from the RGB images (plant / empty per cell
series, emergence day). `sheets/` contact sheets. Limits: no pot with soil and no plant exists;
112 of 120 production seedlings were already visible on day 0; development plants were planted
as small plants; exposure dropped from about 5200 to 4400 on day 4 (production); blue mats on
every production soil pot on day 15; algae on development tray 80 from about day 5. Empty cells
are bare plastic cells, cells with test objects (some green), or open tray grid.

## Rules for your work
- Tune ONLY on the tune set: production trays 1 to 6. Production trays 7 to 12 and all of
  development are the score set: do not look at their labels while choosing parameters.
- Write everything under `~/scratch/375-cell-floor/solutions/<your-name>/`: your script(s),
  `results.csv` (columns rig, experiment_id, tray_id, cell, taken_at_utc, verdict, score; one row
  for EVERY row of data/index.csv; verdict is one of empty, possible, plant: "possible" means
  green that may be a plant and is not yet trusted), and `notes.md`.
- Score with `python3 ~/scratch/375-cell-floor/tools/evaluate.py results.csv --set score |
  python3 ~/scratch/375-cell-floor/tools/table.py` (also `--set tune`). Do not edit tools/.
- A rule may use a cell's earlier photos (causal: only photos taken before or at this one) but
  must say so. If you also try a hindsight version (using later photos), report it separately.
- Make 4 to 8 example images in your folder (`examples/*.png`, each under 1600 px wide): crops
  where your rule is right and where it is wrong, with the mask in magenta and the pot opening in
  red (never cyan), the verdict written on it.
- Memory: the controller has 4 GB shared with 4 other agents. Work only on the small crops, never
  decode the full photos in `raw/`. Keep your process under about 500 MB (`ulimit -v 1500000`).
  Use 1 CPU core (no multiprocessing).
- Never touch the rigs (no ssh), the code checkout, or other agents' folders.
- No em or en dashes in any text.
- Finish within about 45 minutes of work.

## Report back (under 250 words)
The rule in 2 or 3 plain sentences; every parameter and whether it is geometric, adaptive, or a
tuned constant (and how sensitive the result is to it); the score-set table (empty groups:
% plant and % possible; seedling groups: % plant and % plant+possible), compared with the
baseline; where it fails, with an example file name; how it would behave if lighting changed.
