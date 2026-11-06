#352 ImageJ reference outlines
Still 2026-11-03 10:58:53 UTC, capture 19380 (production). 15 crops, 5 plants each on trays 1, 3, 6.
index.png shows where each crop sits. Crops are the rig's own pixels, no outlines drawn on them.

Read RULES.txt first. It decides what counts as plant and where the edge is.
Where RULES.txt and these steps differ, RULES.txt wins (polygon tool, 800% zoom, two passes).

Steps, once
1. Analyze > Set Measurements: tick "Area" and "Display label". OK.
2. Leave the scale in pixels (do not use Set Scale). manifest.csv converts pixels to mm2.

Steps, per crop
1. File > Open the .tif. Zoom in to 600% or more (Image > Zoom > In, or the + key).
2. Freehand tool. Draw around the leaves of the plant in the middle only.
   Hold Shift to add each further leaf to the same selection.
   Follow the edge where you judge leaf ends and soil begins; include the pale and dark leaf edges.
3. Analyze > Measure (Ctrl+M). One row per crop.
4. Analyze > Tools > ROI Manager > Add (Ctrl+T), so the outline is kept.

At the end
- Results window: File > Save As > results.csv, in this folder.
- ROI Manager: More > Save, roi.zip, in this folder.
The outlines in roi.zip let the rules be drawn next to yours on the same plant.
