# Outlines for the Helios comparison (#411)

Twenty crops, `plant01.png` to `plant20.png`. Each shows one potato plant in one tray cell.
Outline the plant in each, in ImageJ. These outlines are the answer the cameras get measured
against.

**Do not look at any mask, area or ratio first.** An outline drawn after seeing a number is pulled
toward it. The files are shuffled; two crops of the same plant are at least five apart, so you
can't tell which are pairs. Don't work it out.

## Zoom

Two cameras, so match the apparent size:

| Image width | Zoom |
|---|---|
| about 930 px | 400% |
| about 485 px | 800% |

## What counts as plant

- Only the plant nearest the middle of the crop. Leave out a neighbour's leaves reaching in.
- Everything green attached to it: leaves, cotyledons, stalks. Overlapping leaves are outlined
  once, from outside.
- **Yellow leaves and yellow parts of leaves do not count.** Pale green does; brown does not.
- The white label stick is never plant. A leaf lying over it still counts.
- Soil or mat between leaves: leave it out if the gap is 2 px or more. Narrower gaps count.
- Trace through the middle of the blurred edge. Polygon tool, not freehand.
- Same screen and light throughout; no brightness or contrast changes.

## Output

**Areas in pixels, not mm.** Each image has its own scale; the conversion happens later.

`Analyze > Set Scale` → *Remove Scale*. `Analyze > Set Measurements` → *Area*, *Perimeter*,
*Display label*. One region per image in the ROI Manager, named after the file (`plant07`).

Send back the Results table as `results.csv` and the regions as `rois.zip`.
