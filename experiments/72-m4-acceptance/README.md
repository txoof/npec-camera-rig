# 72-m4-acceptance

Scripts for the M4 acceptance session of 2026-11-27 (issue #72, `docs/metrology-log.md` section 54).
Read only: GET requests to the development rig (and one ssh read for the version and disk).
Run from this folder.

- `m4.py`: the checker used during the session (`preflight`, `snapshot`, `look`, `dwell`, `restore`, `note`). It writes
  `session-log.txt` and `before/` beside itself. The rig address, tag numbers of experiment 4's trays and the layouts
  are at the top of the file.
- `analyse72.py`: reads every photo of the session from the rig and writes `photos72.csv` and `data72.json`. The state
  of each photo (what lay on tag 49) is inferred from the burst times and Aaron's messages: see `STATES`.
- `make_figure72.py`: draws `timeline-54.png` from `photos72.csv`.
- `make_layouts.py`: draws `layout-1.png` and `layout-2.png` from the layouts in `m4.py`.

The outputs of the session are in `docs/figures/54/`. The spare tray tags (55, 29, 49, 36, 50, 33) were set with
`m4 spares`, which writes `spares.txt` here and is not kept.
