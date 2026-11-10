Draft plant masks for checking, issue 402 (metrology log section 33)
=====================================================================

What is here
------------
About 30 cells from each rig: production (ids A01, A02, ...) and development (ids B01, B02, ...).
For each cell, with <name> = <rig>_<day>_<tray>_<cell>, for example prod_2026-10-29_4_C3:

  cells/<name>.tif              the crop: the cell opening (or pot rim) plus 40 px around it,
                                native pixels, lossless RGB
  cells/<name>_draft.roi.zip    the draft outlines for ImageJ / Fiji, made by rule H
  cells/<name>_draft.png        the same draft as a black and white mask (kept apart from your
                                corrections, do not edit it)
  cells/<name>_preview.png      the crop at 2x, draft outline in magenta, cell opening in red
  sheets/sheet_A1_prod.png ...  picture sheets, 12 previews each, labelled with the id
  sheets/overview_<rig>_<day>.png   each photo, small, every cell in thin magenta, the picked
                                cells in red with their id
  manifest.csv                  one row per cell: id, file, rig, day, train or test, photo,
                                tray, cell, where the crop sits in the photo, mm2 per pixel,
                                rule H and current rule pixels, soil peak, blue share, and why
                                the cell was picked (stratum)

The draft covers every plant pixel rule H finds in the crop, also leaves of the neighbouring
cells, because the classifier learns from pixels, not from cells. Every leaf in the crop counts.

Leaves that hang past the tray's outer edge are NOT in the draft: rule H is only run inside the
trays. Where a crop shows such a leaf, the draft is wrong and the leaf must be added.

Why each cell was picked (the stratum column and the line under each id on the sheets):
  size 1 of 5 ... size 5 of 5   plant size by rule H, from seedling to large
  green soil                    from the trays with the greenest soil, where rule H takes soil
  blue mat, size n of 5         production photos from 6 November on, when every plant cell
                                lies on a blue mat
  empty                         an empty pot in a plant tray: the right answer is no plant
                                at all, unless a leaf from a neighbour reaches in
  not plant: green paper        one green paper square on production, kept on purpose; its
                                draft takes the paper as plant, which is wrong: delete it
Only plant trays were used: production trays 1 to 6, development trays with pots.

Step 1: look at the sheets
--------------------------
Open the sheets (sheet_A1, A2, A3 for production, B1, B2, B3 for development). For each tile,
check the magenta outline against the leaves. Write down the ids whose draft is wrong: a leaf
or part of a leaf missed, soil, mat or wall taken as plant, or edges clearly too wide or too
narrow. Ids judged right need nothing more.

Step 2: correct only the wrong ones, in Fiji
--------------------------------------------
For each id on your list (the manifest gives its file name):

 1. Open <name>.tif.
 2. Analyze > Tools > ROI Manager. In the ROI Manager: More > Open, choose <name>_draft.roi.zip.
 3. Tick Show All.
 4. Fix the outlines:
    - a wrong piece: select it in the list, press Delete;
    - a missed leaf: Wand tool, or the polygon tool, then press Add in the ROI Manager;
    - to change a piece: select it, then the selection brush (right click the oval tool icon
      and choose Selection Brush Tool; a double click only sets the brush size), hold Shift to add, hold Alt to cut;
    - press Update after each edit of a piece.
    Do not use More > Split. Do not use Fit Spline. Do not use ovals.
 5. Outline EVERY leaf in the crop, also the leaves of neighbouring cells, not only the
    plant of the cell in the middle.
 6. In the ROI Manager: More > Save, as <name>_corrected.roi.zip, next to the draft.

Yellow leaves, and the yellow parts of leaves, are not plant (Aaron, 2026-11-10).

Before More > Save, press Deselect, or only the highlighted entries are saved.

Send back the list of wrong ids and the _corrected.roi.zip files.

Notes
-----
Train or test: per rig, days in date order, every third day (3rd, 6th, 9th, ...) is a test
day, and production 3 November is a test day as well. Test cells are never used for training.
Blue share: the share of pixels in the cell opening that are strongly blue (blue above red and
above green by more than 20 on the 0 to 255 scale), a sign of a blue mat.
