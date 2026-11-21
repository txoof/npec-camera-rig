# Outline the plant in 8 cells (#406)

You outline the plant in 8 photo crops yourself, from an empty picture. No machine draft is shown.
The outlines are an answer key, used only for scoring, never for training.

## Start

1. Download `handlabel_package.zip` from http://media-server:8001/406-train/ and unzip it.
   You get one folder, `handlabel_406`.
2. The Fiji macro is not in the package. Ask the AI agent on your computer: "Read AGENT.md in the
   handlabel_406 folder and help me label these cells." It writes `handlabel.ijm` into the folder
   and tests it with you on one cell before you start.
3. Open Fiji.
4. Drag `handlabel.ijm` from the `handlabel_406` folder onto the Fiji window. An editor window opens.
5. Press **Run** in the editor window.

The first cell opens, zoomed, with the ROI Manager empty and the Wand tool selected.

## Each cell

1. Outline every piece of plant:
   - **Wand** (selected for you): click inside a leaf with a clear edge.
   - **Polygon** tool: click around leaves that touch each other or the soil.
   - Press **t** to add the selection to the ROI Manager. Click on the image first, so it has the
     keyboard.
2. Press **OK** in the message window when every piece is in the ROI Manager.
3. A preview shows what will be saved, in magenta. Choose **Save** or **Go back and edit**.
4. The next cell opens.

If you added no piece, the macro asks "No plant in this cell?". Yes saves the cell as empty.

## What counts as plant

- **Plant:** green living tissue, and purple or reddish-purple living tissue (leaf, stalk, stem).
- **Not plant:** yellow leaves, brown or dead leaves.
- **Not plant:** soil, the blue mat, the pot, the tray, labels, sticks.
- **Every leaf in the crop counts**, also leaves of neighbouring plants that reach into the crop.
- **Soil gaps between leaves stay open.** Where you see soil between leaves, leave it out.

## Fix a piece

- **Change a piece:** click it in the ROI Manager list. Use the selection brush (right-click the oval
  tool icon, choose Selection Brush Tool): hold **Shift** and drag to add, hold **Alt** (Option on a
  Mac) and drag to cut. Then press **Update** in the ROI Manager.
- **Remove a piece:** click it in the list, press **Delete**.
- Zoom with **+** and **-**. Hold the **space bar** and drag to move around.
- Do not use ovals, Fit Spline or More > Split.

## Stop and carry on

**Cancel** stops the macro. Run it again later: cells already saved are skipped.
To redo a cell, delete its files in `labelled/` and run the macro again.
When all 8 are saved, the macro says "All 8 done".

## Send the results back

Zip the `labelled` folder as `handlabel_406_labelled.zip` and copy it to media-server, for example:

```
scp handlabel_406_labelled.zip txoof@media-server:/home/txoof/temp.nobackup/npec-406-nn/analysis/labels/handlabel/returned/
```

## The 8 cells

@CELL_TABLE@
