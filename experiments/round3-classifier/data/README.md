# Reference set of plant masks, issue #402 (metrology log 33 and 33.1)

60 cells (production A01 to A30, development B01 to B30), one photo per day, chosen by the method of
log 33 and its amendment. Checked and corrected by Aaron on 2026-11-10. Yellow leaves are not plant
(decision of 2026-11-10, question with the supervisor in #106). Every leaf in a crop counts, also
neighbours' leaves.

| Folder or file | What |
|---|---|
| `photos_manifest.csv` | The 26 photos the cells come from (one per day per rig) |
| `manifest.csv` | One row per cell: id, file, rig, day, train or test, photo, tray, cell, crop position in the full photo, mm2 per px, stratum |
| `crops/<name>.png` | The crop, lossless, pixel-identical to the TIFF that was outlined (converted 2026-11-10, checked) |
| `drafts/<name>_draft.roi.zip`, `_draft.png` | The drafts by grow from leaf cores, as sent |
| `corrected-20261110T1109Z/` | Aaron's 39 corrections (ImageJ ROI zips), `notes.txt` of the session; `*_MISTAKE*` files are superseded first attempts, not used |
| `truth/<name>_truth.png`, `truth_index.csv` | The final answer per cell: Aaron's correction, or the draft he accepted (21, B13 among them), or empty (A28, a green printed square). White = plant |
| `check_2026-11-10_aaron.csv` | Aaron's note on every draft |
| `README_drafts_as_sent.txt` | The instructions sent with the drafts |

Read the ROI zips with `../code/mask_rois.py` (`roi_zip_to_mask`), which fills them exactly as ImageJ
does. The full zip as sent was `drafts-2026-11-09.zip`, sha256 starting a6b3989264992f80 (scratch, not
kept). The photos the crops come from stay on the rigs (production experiment 18, development
experiment 3); the capture ids are in the manifest.

**Lean.** 21 truths are accepted drafts, so any comparison favours grow from leaf cores. The 15
outlines of log 24 (`../../352-green-threshold/data/imagej/`) were drawn from nothing and are the
independent check.
