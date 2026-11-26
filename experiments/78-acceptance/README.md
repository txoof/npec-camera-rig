# 78-acceptance: green squares of known area in all 12 slots (issue #78)

Read-only analysis for `docs/metrology-log.md` section 51, run on 2026-11-26 against the production
rig's API (`d6-daylight`, experiment 1 "I78 Milestone"). Nothing here writes to the rig.

| File | What |
|---|---|
| `analyse78g.py` | Reads each still of the three runs from `/api/captures` and `/api/captures/trays/...` and writes `rows78g.json`: cell C3 of every slot, green threshold area and grown area, the slot's band |
| `rows78g.json` | The result of `analyse78g.py`: 312 readings (26 stills x 12 slots) |
| `score78g.py` | Scores each square per run against its calliper area (log 18.5) and the band; writes `score78g.json` |
| `jump78.py` | Measures the greenness inside each square and on the blue ring around it, in two stills (full-size photos fetched from the rig); writes `jump78.json` |
| `fig51.py` | Draws `docs/figures/51/errors-by-slot-2026-11-26.png` from `score78g.json` (needs Pillow) |

The scripts were run from a scratch folder, so file names are relative to the working directory. The
photos stay on the rig in `experiments/2026-11-26_a6eb8878/`.
