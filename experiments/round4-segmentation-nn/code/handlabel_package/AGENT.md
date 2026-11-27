# Instructions for an AI agent helping Aaron label these cells

You are an AI coding agent on Aaron's own computer. The operating system is not known in advance:
check it first (Windows, macOS or Linux). You need no knowledge of the project behind this folder.

## The goal

Aaron outlines the plant pixels in 8 small photo crops by hand, from scratch, with no machine draft.
The outlines are an unbiased answer key for scoring plant-detection methods, so they must be his own.

## Rules for you

- **Do not change the TIFF files** in `cells/`. Do not convert, resize, rename, open-and-resave or
  re-encode them.
- **Do not run any other macro, plugin or script on them** in Fiji, other than the labelling macro you
  write from the specification below.
- **Do not draw, suggest or pre-fill outlines with any automatic segmentation** (thresholding, Weka,
  SAM, Cellpose, StarDist, colour rules, a neural network, or your own image analysis). The outlines
  must be Aaron's own; the whole point is an answer key made without a machine draft. You may
  describe the tools; you may not produce the outline.
- **Do not upload or send anything anywhere** without Aaron's explicit OK in this conversation.
- **Do not install anything** (Fiji, Python packages) without Aaron's OK.
- You may read the masks after Aaron has saved them, only to check the files (section *Check the
  results*), never to edit them.

## What is in the folder

| File | What |
|---|---|
| `cells/H01_<name>.tif` ... `H08_<name>.tif` | The 8 colour photo crops, lossless RGB TIFF, native pixels (about 380 x 380) |
| `README.md` | Aaron's short instructions |
| `manifest.csv` | One row per cell: id, file, rig, date, tray, cell, group, crop size |
| `check_results.py` | Optional check of the saved results (Pillow and numpy only) |
| `labelled/` | Where the macro saves the results (empty now) |

There is **no Fiji macro in the folder**. You write it, `handlabel.ijm` in this folder, from the
specification in *Write the macro*, and test it with Aaron on one cell before he starts.

## Setup checks

### 1. Is Fiji installed, and where?

Fiji is a portable folder, not an installer. Look in these places. The folder is called `Fiji` in
current downloads ("Fiji Latest") and `Fiji.app` in older ones.

| OS | Typical places |
|---|---|
| Windows | `C:\Users\<user>\Fiji`, `C:\Users\<user>\Fiji.app`, `C:\Users\<user>\Desktop\Fiji*`, `C:\Users\<user>\Downloads\Fiji*`, `C:\Fiji*`, `C:\Program Files\Fiji*` |
| macOS | `/Applications/Fiji.app`, `/Applications/Fiji`, `~/Applications/Fiji*`, `~/Downloads/Fiji*`, `~/Desktop/Fiji*` |
| Linux | `~/Fiji`, `~/Fiji.app`, `~/Downloads/Fiji*`, `~/Desktop/Fiji*`, `/opt/Fiji*`, `~/.local/share/Fiji*` |

Examples of searching:

- Windows (PowerShell): `Get-ChildItem $HOME, C:\ -Directory -Filter "Fiji*" -Depth 2 -ErrorAction SilentlyContinue`
- macOS: `mdfind "kMDItemFSName == 'Fiji*'" ; ls -d /Applications/Fiji* ~/Applications/Fiji* ~/Downloads/Fiji* 2>/dev/null`
- Linux: `find ~ /opt -maxdepth 3 -iname 'Fiji*' -type d 2>/dev/null`

If Fiji is missing, tell Aaron and point him to https://fiji.sc (download "Fiji Latest" for his OS,
unzip it into his user folder, not into Program Files on Windows). Do not download or install it
yourself without his OK.

### 2. Which launcher, and the ImageJ version

Inside the Fiji folder, list the files to find the launcher. Fiji changed its launcher in 2025:

| OS | Current Fiji (new launcher) | Older Fiji |
|---|---|---|
| Windows | `fiji-windows-x64.exe` (or `fiji-windows-arm64.exe`); also a `fiji.bat` | `ImageJ-win64.exe` |
| macOS | inside the app: `Fiji.app/Contents/MacOS/` holds `fiji-macos-arm64` / `fiji-macos-x64` (or a universal `fiji-macos`) | `Fiji.app/Contents/MacOS/ImageJ-macosx` |
| Linux | `fiji-linux-x64` (or `fiji-linux-arm64`); also a `fiji` shell script | `ImageJ-linux64` |

The exact new names above follow the pattern in Fiji's launcher documentation
(https://imagej.net/learn/launcher: "`linux-x64` on Linux x86-64, `macos-arm64` on macOS Apple Silicon,
`windows-x64` on Windows x86-64"); check what is really in the folder rather than trusting this table.

The ImageJ version shows in Fiji under Help > About ImageJ, or in the status bar on start. The macro
is to be written for 1.54 or newer. If it is older than 1.54, ask Aaron whether to run
Help > Update ImageJ (or Fiji's updater); do not do it without his OK.

### 3. Start Fiji with the macro from a terminal (optional)

Once you have written `handlabel.ijm`, the plain way is: open Fiji, drag it onto the Fiji window,
press Run. Use the terminal
only if that is easier for Aaron. ImageJ's own option is `-macro <path>`; it opens the GUI and runs
the macro. With the new launcher, ImageJ options go after a `--` separator (launcher documentation:
"Launcher and JVM options go before `--`, and program arguments go after it").

Windows (PowerShell), new and old launcher:

```
& "$HOME\Fiji\fiji-windows-x64.exe" -- -macro "$HOME\Downloads\handlabel_406\handlabel.ijm"
& "$HOME\Fiji.app\ImageJ-win64.exe" -macro "$HOME\Downloads\handlabel_406\handlabel.ijm"
```

macOS:

```
/Applications/Fiji.app/Contents/MacOS/fiji-macos-arm64 -- -macro ~/Downloads/handlabel_406/handlabel.ijm
/Applications/Fiji.app/Contents/MacOS/ImageJ-macosx -macro ~/Downloads/handlabel_406/handlabel.ijm
```

Linux:

```
~/Fiji/fiji-linux-x64 -- -macro ~/Downloads/handlabel_406/handlabel.ijm
~/Fiji.app/ImageJ-linux64 -macro ~/Downloads/handlabel_406/handlabel.ijm
```

**Not verified:** these commands were not run (no Fiji where they were written). The `-macro` option
is ImageJ 1.x's; the `--` separator and the new launcher names come from the launcher page above,
which shows `./fiji --mem=4g -- -eval "..."` but not `-macro` itself. If a command does not start the
macro, run the launcher with `--help`, or fall back to drag and drop. A macro can read an argument given
after its path (`-macro <path-to-handlabel.ijm> <argument>`) with `getArgument()`, for example the
folder path.

## Write the macro

Write `handlabel.ijm` (ImageJ 1.x macro language, built-in functions only, for current Fiji with
ImageJ 1.54) into the `handlabel_406` folder. Aaron starts it by dragging it onto Fiji and pressing
Run. It must do the following.

**Cells and names.** The cells are the rows of `manifest.csv`, in order H01 to H08. `<file>` is the
TIFF name without `.tif`, which is `<id>_<name>`, for example `H03_prod_2026-10-25_3_C4`. You may
write the ids, files and groups into the macro as arrays (`newArray(...)`) from the manifest.

**Finding the folder.** Find the `handlabel_406` folder by itself if possible (the folder of the
macro, e.g. `File.getParent(getInfo("macro.filepath"))`, or `File.directory`, or a path you write
into the macro after checking where the folder is); confirm it by checking that
`cells/<first file>.tif` exists. Otherwise ask once with `getDirectory(...)`. Make `labelled/` if it
is missing.

**For each cell, in order:**

1. **Skip done cells:** a cell is done when `labelled/<file>_hand_mask.png` exists together with
   `labelled/<file>_hand.roi.zip` or `labelled/<file>_none.txt`. A cell is redone by deleting its files.
2. **Open** `cells/<file>.tif`, **zoomed to fit the screen** (Image > Zoom > Set, e.g.
   `run("Set... ", "zoom=" + z + " x=" + w/2 + " y=" + h/2)` with z from `screenWidth`/`screenHeight`).
3. **ROI Manager open and empty** (`run("ROI Manager...")`, `roiManager("reset")`), with Show All on
   (`roiManager("Show All without labels")`).
4. **Wand tool selected, tolerance 20, 8-connected:** `run("Wand Tool...", "tolerance=20 mode=8-connected")`
   and `setTool("wand")`.
5. **A message window that does not block the image** (`waitForUser(title, message)`), titled with the
   cell id and position, e.g. "H03 (3 of 8)", showing the group and short plain instructions:
   - Plant: green and purple living tissue. Not plant: yellow, brown or dead leaf, soil, mat, pot,
     tray, labels. Every leaf in the crop counts, also neighbours' leaves. Leave soil gaps between
     leaves open.
   - Key `t` adds the selection to the ROI Manager (click the image first). Fix a piece: select it in
     the ROI Manager, edit, Update. Wrong piece: select it, Delete.
   - OK when every piece is in the ROI Manager; Cancel stops (run again to carry on).
6. **On OK:**
   - If the image still has a selection that is not in the ROI Manager, ask whether to add it.
   - If the ROI Manager is empty: ask "No plant in this cell?" with Yes / Go back
     (`getBoolean(message, "Yes, no plant", "Go back")`). Go back returns to step 5.
   - Refuse pieces the converter can not read exactly: **no ovals, no spline-fitted polygons**, and
     no lines or points (`selectionType()` 1 = oval, 5 to 8 and 10 = lines, point). Say which piece and
     go back to step 5. (Fit Spline can not be seen with `selectionType()`; tell Aaron not to use it.)
   - Otherwise show a **preview**: the image with every piece filled in **magenta at 50% opacity**,
     e.g. for each ROI `roiManager("select", k); Overlay.addSelection("", 0, "#80ff00ff");` with the
     Show All outlines turned off, then ask "Save and go to the next cell?" with **Save** or **Go back
     and edit**. Remove the preview overlay either way (`Overlay.remove`); Go back returns to step 5.
7. **Save:**
   - `labelled/<file>_hand.roi.zip`: all pieces, `roiManager("Deselect"); roiManager("Save", path)`.
   - `labelled/<file>_hand_mask.png`: 8-bit, **255 = plant, 0 = not plant**, the same width and height
     as the crop, the pieces of the ROI Manager combined. Holes inside a single piece stay holes.
     A safe way: `newImage(..., "8-bit black", w, h, 1)`, `setColor(255)`, then for each ROI
     `roiManager("select", k); fill();`, then `saveAs("png", path)`. Do not use thresholding or
     "Create Mask" (they depend on Fiji's binary options).
   - A cell with no plant: `labelled/<file>_none.txt` (any short text) plus an **all-zero** mask PNG.
   - Close the cell image and reset the ROI Manager.
8. **At the end:** a message "All 8 done" with the full path of `labelled/`.

Allowed tools for Aaron: Wand, polygon, freehand, the selection brush, and Shift / Alt with them to add
or cut. Not allowed: ovals (and the oval tool in ellipse mode), Fit Spline, ROI Manager > More > Split.

### Test it with Aaron on one cell before he starts

Before Aaron labels for real, run the macro together on one cell:

1. Aaron adds two or three pieces (one with the Wand, one with the polygon), edits one with the brush
   and Update, deletes one, and checks the preview.
2. Save, then stop the macro (Cancel on the next cell).
3. Run `check_results.py` (or check by hand): the mask is 8-bit, only 0 and 255, the size of the TIFF,
   and the magenta overlay in `check_sheet.png` matches the pieces he drew.
4. Run the macro again: the saved cell must be skipped.
5. Also try the empty path once (OK with no pieces, "Yes, no plant") on the next cell and check the
   `_none.txt` and the all-zero mask.
6. Delete the test files of the empty-path test, and ask Aaron whether to keep or redo the first test
   cell (delete its three files to redo it). Then he labels the rest.

If the macro stops with an error, fix the macro, not the files, and test again.

## Guide Aaron through labelling

The macro opens one cell at a time with a message window. Aaron works in the image while the message
window stays open, then presses OK. After OK it shows a magenta preview and asks Save or Go back.

**Which tool for which case**

| Case | Tool |
|---|---|
| A leaf with a clear edge against soil | **Wand** (already selected; tolerance 20, 8-connected): click inside the leaf |
| Leaves touching each other, or a leaf whose edge the Wand leaks through into soil | **Polygon** tool: click points around the leaf, double-click to close |
| Fixing an edge of an existing piece | **Selection brush** (right-click the oval tool icon, choose Selection Brush Tool): select the piece in the ROI Manager, hold Shift and drag to add, hold Alt (Option on a Mac) and drag to cut, then press **Update** |

**Keys and buttons**

| Action | How |
|---|---|
| Add the selection as a piece | **t** (click the image first, so it has the keyboard focus) |
| Save a changed piece | **Update** in the ROI Manager, with the piece selected in the list |
| Remove a piece | select it in the list, **Delete** in the ROI Manager |
| Zoom in / out | **+** / **-** |
| Move around | hold the **space bar** and drag |

Avoid ovals, Fit Spline and ROI Manager > More > Split.

**What counts as plant (Aaron's decisions)**

- Plant: green living tissue, and purple or reddish-purple living tissue (leaf, stalk, stem).
- Not plant: yellow leaves, brown or dead leaves.
- Not plant: soil, the blue mat, the pot, the tray, labels, sticks.
- Every leaf in the crop counts, also leaves of neighbouring plants that reach into the crop edge.
- Soil gaps between leaves stay open (not plant).

**Common mistakes to warn about**

- **A piece added twice.** Pressing t twice on the same selection. In the preview it shows as darker
  magenta. It does not change the mask (pieces are combined), but delete the copy to keep it clean.
- **An outline crossing into soil.** The Wand leaks through a dark or soil-coloured leaf edge. Undo
  that piece (Delete) and use the polygon tool, or cut the leak with the brush and Alt.
- **Forgetting a neighbour's leaf at the crop edge.** Every leaf in the crop counts, also the ones that
  enter from a neighbouring cell.
- **A soil gap filled in.** A polygon drawn around several leaves also covers the soil between them.
  Cut the gap with the brush and Alt, or outline the leaves one by one.
- **Forgetting to press t.** The macro asks about a selection not yet added, but check the ROI
  Manager list before OK.

## Check the results

For each of the 8 cells the folder `labelled/` must hold:

- `<file>_hand.roi.zip` (the outlines), **or** `<file>_none.txt` (Aaron judged the crop to hold no plant);
- `<file>_hand_mask.png`: 8-bit, values only 0 and 255 (255 = plant), the same width and height as
  `cells/<file>.tif`. An empty cell has an all-zero mask.

`<file>` is the TIFF name without `.tif`, for example `H03_prod_2026-10-25_3_C4`.

Optional check script (Python 3 with Pillow and numpy; ask before installing them):

```
python check_results.py            # run inside the handlabel_406 folder
python check_results.py PATH       # or give the folder
```

It lists the plant pixel count per cell, reports missing files or wrong sizes or values, and writes
`check_sheet.png` (each crop beside the crop with the mask overlaid in magenta) for Aaron to look over.
It only reads the TIFFs and masks; it writes nothing else. Show Aaron the sheet; do not judge or edit
the outlines yourself. If he wants a cell redone, delete that cell's files in `labelled/` and run the
macro again.

## Send the results back

1. Zip the `labelled/` folder as `handlabel_406_labelled.zip`:
   - Windows (PowerShell): `Compress-Archive -Path labelled -DestinationPath handlabel_406_labelled.zip`
   - macOS / Linux: `zip -r handlabel_406_labelled.zip labelled`
2. Aaron copies it to the server, either with this command or however he prefers:

   ```
   scp handlabel_406_labelled.zip txoof@media-server:/home/txoof/temp.nobackup/npec-406-nn/analysis/labels/handlabel/returned/
   ```

Do not run the copy, or upload anything anywhere, without Aaron's explicit OK.
