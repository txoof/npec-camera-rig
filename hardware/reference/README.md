# Vendor reference material

This directory holds manufacturer-supplied source files kept for provenance and future
re-derivation — they are not build inputs themselves. Each subdirectory corresponds to a specific
catalog part used by one of the `.scad` models at the repo root.

PDFs are generally not retained once their useful content has either been captured in a vector
file (DXF/DWG) or already encoded into the corresponding `.scad` model — they're large and
duplicate what the vector data or the model's own header comments already say.

## 40x40_profile/ — 40x40 T-slot extrusion (`libraries/t_slot_40x40.scad`)

Part number `54.01.0100(00-00-0)(000)`, sourced from CADENAS/3dfindit (downloaded 2026-09-24).
Kept:

- `54.01.0100(00-00-0)(000)_right.dxf` / `.dwg` — the actual cross-section geometry (ARC/CIRCLE
  entities). This is the exact vector data `t_slot_40x40.scad`'s 132-point profile polygon was
  reconstructed point-for-point from.
- `54.01.0100(00-00-0)(000)_front.dxf` / `.dwg` and `_top.dxf` / `.dwg` — plain rectangles of the
  cut length, kept alongside the profile view for completeness. (Only the `_right` view contains
  real profile geometry — check entity types, not filenames, before assuming a view is the
  cross-section.)
- `readme-and-terms-of-use-3d-cad-models.txt` — CADENAS licensing/attribution terms for these
  files.

Dropped: `54.01.0100(00-00-0)(000).pdf`, the 1.6MB datasheet — everything usable from it is
either in the DXF/DWG above or already encoded in `t_slot_40x40.scad`.

## 20x20 T-slot extrusion (`libraries/t_slot_20x20.scad`)

No vector source was ever available for this part — only a raster drawing inside a PDF
datasheet (`20x20_profile.pdf`). That PDF has been discarded; `t_slot_20x20.scad`'s header
already documents which figures are vendor-labelled (e.g. the M6 groove size) vs. visually
approximated from the raster image, so nothing is lost by removing it. If higher-fidelity
geometry is needed later, a DXF/DWG would need to be re-sourced from the vendor.

## raspberry_tips_pi5_case/ — Pi 5 case base (`camera_rig/pi5_case.scad`)

The raspberry.tips v2.0 Pi 5 case (2026-08-13), from
`https://cdn.raspberry.tips/2026/08/raspberry-tips-pi5-case-v2.0.zip` (downloaded 2026-10-22).
Licence CC BY 4.0. Attribution, which every derived file carries:

    Case for Raspberry Pi 5 by raspberry.tips, CC BY 4.0
    https://raspberry.tips/en/3d-druck/raspberry-pi-5-case-3d-print

Kept, unchanged:

- `rpi5_case.scad` — the parametric source. `camera_rig/pi5_case.scad` started as an exact copy
  of it; diff the two to see every change made for the rig.
- `README.txt` — their licence, print settings and calibration notes (German).

Dropped: their STL and 3MF exports (rebuilt from the source) and `pi5_referenz.scad`, their Pi 5
ghost, which is drawn mirrored in y. `libraries/pi5_ghost.scad` uses the official STEP instead.

## pi5_step/ — Raspberry Pi 5 STEP model (not committed)

Gitignored. Raspberry Pi Ltd owns the model, so it is fetched, not kept: `uv run
fetch_pi5_model.py` downloads `RP-010083-CA` and writes the STL and box sets that
`libraries/pi5_ghost.scad` reads.
