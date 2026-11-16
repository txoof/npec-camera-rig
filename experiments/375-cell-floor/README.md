# Wall fringe in the cells (#375)

Metrology log section 28. Scripts as run on 2026-11-07 on the controller against a dataset in
`~/scratch/375-cell-floor/data/` (not kept): `code/process.py` builds the cell pictures and the
index from read-only copies of the stills, `code/labels_make.py` and `code/labelview.py` the labels,
`code/evaluate.py` scores a rule's verdicts, `code/blue_share.py` measures 28.3. `code/rules/` holds
the five rules tried; `data/rules/` their verdicts and notes. `data/index.csv.gz` and
`data/pieces.csv.gz` are the picture index and the per-piece table.
