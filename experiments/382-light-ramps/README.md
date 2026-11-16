# Light ramps: which photos to leave out (#382)

Raw data and scripts behind metrology log section 29. Read-only analysis of production experiment
18 (`ac-testing`, 22 October to 7 November 2026) and development experiment 3 (`npec-rig-01`,
3 to 7 November 2026). Nothing was written on either rig.

## Data (`data/`, xz-compressed CSV)

| File | What |
|---|---|
| `abc_prod_captures`, `abc_dev_captures` | Every photo of the experiment: id, time (UTC), path, exposure (us), analogue gain. Read from each rig's `rig.db` with `mode=ro` |
| `abc_prod_tags`, `abc_dev_tags` | Per photo and corner tag: the tag's white cells, black cells and outer white ring (mean green, linear green, share at 250 or more), and the whole frame's linear green. Production: 4,982 photos (every photo within 75 min of a dark one, every 5th otherwise); development: all 3,690 lit photos |
| `abc_prod_scored`, `abc_dev_scored` | Per photo: E, the reference light level L, the corner-tag index, the current rule's name and each candidate rule's verdict |
| `corner_*` | The first corner-tag check: 317 production photos (one an hour plus the 5 November 00:00 ramp) and 95 development photos |
| `light_norm_samples`, `samples_raw` | The earlier read-only check of the white table strip and back wall (issue #382 comment, 2026-11-06) |
| `abc_results.txt`, `nrule_results.txt` | The printed score tables of log 29.2 |

## Code (`code/`)

Run with Python 3 and OpenCV 4.10 or later. The paths at the top of each script point at the
working folders used on 2026-11-07 (`~/scratch/382-light-norm/` and the session's temporary folder
on testpi-02); change them to `data/` to run again.

- `tagcheck.py ROOT LIST OUT`: finds the corner tags (IDs 450 to 456) in each photo, decoded at half
  size, and measures their cells.
- `analyse.py`, `plot.py`: the first corner-tag check and its figure (`docs/figures/29/`).
- `score.py`: the reference light level and rules A, B and C; `split.py` splits ramps from daytime
  dips; `nrule.py` scores the neighbour rules N, N-pad and N-any.

Photos copied to the controller for the analysis (about 29 GB) were not kept; they stay in their
experiment folders on the rigs.
