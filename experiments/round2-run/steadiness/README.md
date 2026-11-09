# Round 2 steadiness with area (metrology log 16.9, #223)

Scripts behind the 16.9 results: the change in plant area from one photo to the next on the
Round 2 run (experiment 18, production), for the green threshold 0.1. Kept so the study can be run
again with other plant-area rules (#395). All read a read-only copy of production's `rig.db`; none
writes to a rig. Paths to the copy, the slot layout and the outputs are set at the top of each
script (under `~/scratch`).

| Script | What it does |
|---|---|
| `script_a.py` | Undisturbed pairs (16.3 and 16.9 rules, through `../analysis.py`), the tray tables of Question 1, tags found (Question 2), the 20 largest changes. Writes `tray_pairs_all.csv` |
| `script_b.py` | The same pairs and tray tables, written separately from the method text alone, as a cross-check. `test_script_b.py` holds its hand-worked examples |
| `restarts.py` | Pairs that span an app restart before 2 Nov 16:19 UTC, from the photos' sidecars (`app_up_s`); these are left out of the results |
| `cell_pairs.py`, `cells.py` | The cell table, 6 Nov 12:28 UTC on |
| `slot_turn.py` | The benchmark by map, slot and turn, with the turn checked from the benchmark's offset in its tray |

Order: `script_a.py`, then `restarts.py` on its `tray_pairs_all.csv`, then the rest. Two agreed
choices go into `script_b.py` for the cross-check: shuffle 0 gets a 60 minute window, and tray 8
pairs before 22 Oct 09:34:53 UTC are left out. The pictures of the by-eye checks and the area
against distance from the photo centre were made by short helpers that are not kept; how they were
made is in 16.9.
