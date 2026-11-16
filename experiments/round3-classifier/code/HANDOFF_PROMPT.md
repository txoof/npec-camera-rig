# Hand-off: help Aaron correct 39 draft plant outlines in Fiji (issue 402)

You are a Claude Code agent running on Aaron's Mac. Your job is to take every repetitive step off
Aaron so he only looks at each crop, fixes the outline with the mouse, and clicks OK. Aaron does all
the outlining himself. Read this whole file before doing anything.

## Hard rules

1. **Never draw, change, fill or delete an outline yourself**, by code or otherwise. The outlines
   are a hand reference for a measurement; a correction made by software is worthless. Aaron
   decided explicitly (2026-11-10) that no automatic hole filling is to be done.
2. **Never modify, move or delete anything in `cells/`, `sheets/`, `manifest.csv` or `README.txt`**
   in the drafts folder. Write only inside `corrected/`.
3. Never overwrite a file in `corrected/` that already exists. If something must be redone, ask
   Aaron and save the new one under a new name (`..._corrected_v2.roi.zip`).
4. Do not install anything system wide without asking Aaron. Fiji is already installed.
5. Keep Aaron's effort minimal: you do the looking up, launching, checking and copying. Ask him
   only what only he can answer. Short, plain messages. No em or en dashes in anything you write.

## Background (why this exists)

The plant growth rig photographs trays of potato plants from above and measures plant area per
cell (pot). Its colour rule ("rule H") draws plant outlines. Aaron is building a reference set of
hand-corrected outlines to train a pixel classifier (a random forest that learns plant from soil).
60 cells were drafted with rule H: ids A01 to A30 from the production rig, B01 to B30 from the
development rig. Aaron checked all 60 on picture sheets: 20 are right as drafted, 1 (A28) has no
plant at all, and 39 need correcting. Those 39 are listed below with Aaron's own note on each.

## Where things are

- Drafts folder: `~/Downloads/drafts-2026-11-09/` (unzipped from `drafts-2026-11-09.zip`). Check
  it holds `cells/`, `manifest.csv`, `README.txt`. If `cells/` is one level deeper (for example
  `~/Downloads/drafts-2026-11-09/drafts-2026-11-09/cells/`), use that inner folder as the drafts
  folder and say so.
- For each cell, with `<name>` from the tables below:
  - `cells/<name>.tif`: the crop (native pixels, RGB, about 0.2 mm per pixel). Never changed.
  - `cells/<name>_draft.roi.zip`: rule H's draft outlines, one ROI per piece. For A01, A02 and
    A17 the draft is EMPTY (rule H found nothing); ImageJ then says "This zip archive does not
    contain .roi files". That is expected: those three are outlined from nothing.
  - `cells/<name>_preview.png`: the crop at 2x with the draft in magenta and the cell opening in red.
- Output: `~/Downloads/drafts-2026-11-09/corrected/`:
  - `<name>_corrected.roi.zip` for each corrected cell;
  - `<name>_none.txt` (content `none`) where the right answer is no plant at all.

## Labelling rules (what counts as plant)

These replace the older #352 rulebook where they differ.

1. **Every leaf in the crop counts**, including leaves of neighbouring cells and leaves hanging in
   from outside the tray. The classifier learns from pixels, not from cells. (The old rule R5,
   "only the centre plant", does NOT apply.)
2. **Yellow leaves, and the yellow parts of partly yellow leaves, are NOT plant** (Aaron,
   2026-11-10; the question is with the supervisor). The old rule R10 does NOT apply.
3. Green stalks, cotyledons and true leaves attached to a plant count.
4. Overlapping leaves: one outline around the group; overlap counts once.
5. Soil seen between leaves is left out when the gap is at least 2 pixels wide (a hole in the
   outline). Narrower gaps are plant. Some soil does poke through: holes are not filled blindly.
6. Dark shadow next to a leaf is soil unless leaf colour or texture shows in it.
7. The edge goes through the middle of the blur: halfway between leaf colour and soil colour.
8. Green paper, targets, algae and green soil are NOT plant.
9. Same screen and room light throughout; no brightness or contrast changes in Fiji.

## The Fiji controls Aaron uses (tell him these on the first cell, then only when asked)

- ROI Manager: the list of outline pieces. **Show All** is switched on by the macro.
- New piece: Wand tool (already selected; tolerance 20, 8-connected) click on a leaf, or the
  polygon tool; then **Add** in the ROI Manager (or press `t`).
- Change a piece: click it in the list, then edit it. Selection brush: **right click** the oval
  tool icon and choose Selection Brush Tool (double click only sets the brush size). Hold Shift
  to add, Alt (Option) to cut. Then press **Update** in the ROI Manager. Without Update the edit
  is lost.
- A hole in a piece: select the piece, Alt + polygon (or Alt + brush) around the soil, Update.
- Wrong piece: click it in the list, **Delete**.
- Do NOT use More >> Split, Fit Spline, or ovals. A piece with a hole stays one entry.
- Zoom: `+` and `-` keys; hold space and drag to pan.

## The macro (does the opening, zooming, loading and saving)

Save this text, exactly, as `~/Downloads/drafts-2026-11-09/correct_drafts.ijm` (same file as
http://testpi-02:8001/402-pixel-classifier/correct_drafts.ijm). For each of the 39 cells it opens
the crop, loads the draft (skipped when empty), turns on Show All, zooms to fit the screen,
selects the Wand tool and shows a small window with the id, Aaron's note and the rules. While that
window is open Aaron can work on the image. **OK** deselects, saves to `corrected/` and opens the
next cell. **Cancel** stops; running the macro again skips cells already saved. If Aaron deletes
every piece (no plant at all), OK writes `<name>_none.txt` instead.

```
// Issue 402: correct the draft plant outlines, one cell after another.
// Plugins > Macros > Run..., choose this file, then choose the unzipped drafts folder (the one that holds cells/).
// Each cell opens zoomed with its draft and your note. Fix it, click OK: it saves and opens the next.
// Cells already saved are skipped, so you can stop (Cancel) and run it again later to carry on.
ids = newArray("A01","A02","A12","A14","A17","A18","A19","A21","A24","A25","A26","A27","A29","A30","B01","B03","B04","B05","B06","B07","B08","B09","B10","B11","B12","B13","B14","B15","B16","B18","B19","B20","B21","B22","B23","B24","B26","B27","B28");
names = newArray("prod_2026-10-22_4_B4","prod_2026-10-23_5_C2","prod_2026-10-28_4_A3","prod_2026-10-30_2_B2","prod_2026-11-01_6_A5","prod_2026-11-02_3_C4","prod_2026-11-02_4_D3","prod_2026-11-04_1_D5","prod_2026-11-05_6_A2","prod_2026-11-06_3_C5","prod_2026-11-07_3_C3","prod_2026-11-07_5_B2","prod_2026-11-09_2_C3","prod_2026-11-09_4_C5","dev_2026-11-03_76_B2","dev_2026-11-03_78_B2","dev_2026-11-03_81_A1","dev_2026-11-03_81_A2","dev_2026-11-03_81_B1","dev_2026-11-04_76_B2","dev_2026-11-04_78_B1","dev_2026-11-04_80_B1","dev_2026-11-04_80_B2","dev_2026-11-04_81_B2","dev_2026-11-04_85_A2","dev_2026-11-04_86_A1","dev_2026-11-05_76_A1","dev_2026-11-05_80_A1","dev_2026-11-05_86_B2","dev_2026-11-06_78_A2","dev_2026-11-06_87_A2","dev_2026-11-07_77_A1","dev_2026-11-07_79_A1","dev_2026-11-07_80_A2","dev_2026-11-07_87_A1","dev_2026-11-07_87_A2","dev_2026-11-08_79_A2","dev_2026-11-09_76_A2","dev_2026-11-09_76_B1");
notes = newArray("total miss (plant is exceptionally small)  [empty]","total miss (plant is exceptionally small)  [empty]","soil to north, north east and south are misclassified as green (tens of px)  [green soil]","Excellent, very small miss in east leaf  [size 2 of 5]","Total miss  [empty]","Excellent, complex border in southeast may not be correct (tens of px)  [size 4 of 5]","Excellent, tiny exclusion in west  [size 1 of 5]","Small miss on north most leaf edge (tens of px)  [size 5 of 5]","Excellent, one or two px north of edge that appear misclassified  [size 4 of 5]","border is too tight, misses leaf edge  [blue mat, size 2 of 5]","border is too tight, misses leaf edge  [blue mat, size 4 of 5]","border is too tight, misses leaf edge  [blue mat, size 3 of 5]","border too tight, misses leaf edge  [blue mat, size 5 of 5]","border too tight, misses leaf edge  [blue mat, size 1 of 5]","Small internal error, green soil captured, acceptable border  [size 2 of 5]","Small edge error in north and south east leaf  [green soil]","Soil classified, small border error on north east most leaf  [size 4 of 5]","Soil classified  [size 3 of 5]","small internal errors  [green soil]","soil classified with leaf border in north east  [size 2 of 5]","small border error in south east leaf  [size 2 of 5]","Small internal error  [size 2 of 5]","tiny error inside northeast leaf  [size 3 of 5]","Soil included in leaf border; green soil classified  [size 4 of 5]","large region missed in northeast cluster; soil classified  [size 5 of 5]","small internal errors within leaves, small leaves missed along stem  [size 4 of 5]","small internal error on yellow leaf  [size 3 of 5]","poor border, algea captured  [green soil]","small internal error  [size 4 of 5]","Small internal error  [size 1 of 5]","Small internal error  [empty]","Extremely small internal errors  [size 3 of 5]","Small internal errors, large internal error on yellow leaf  [size 5 of 5]","Small internal errors, bad border on north most leaf  [size 3 of 5]","Small internal errors  [size 5 of 5]","Yellow leaf missed entirely (may be acceptable), small internal error in east most region  [empty]","Small miss on southern leaf and south east leaf, yellow leaf in south is complex and wrong  [size 5 of 5]","Excellent, small miss on southeast leaf (2-10 px)  [size 1 of 5]","Yellow leaves missed entirely, green is good, small error internally (2-10 px)  [green soil]");
dir = getArgument();
if (dir == "") dir = getDirectory("Choose the unzipped drafts folder (the one that holds cells)");
if (!endsWith(dir, File.separator)) dir = dir + File.separator;
cells = dir + "cells" + File.separator;
out = dir + "corrected" + File.separator;
File.makeDirectory(out);
run("Wand Tool...", "tolerance=20 mode=8-connected");
n = names.length;
for (i = 0; i < n; i++) {
  done = out + names[i] + "_corrected.roi.zip";
  none = out + names[i] + "_none.txt";
  if (File.exists(done) || File.exists(none)) continue;
  open(cells + names[i] + ".tif");
  img = getImageID();
  roiManager("reset");
  draft = cells + names[i] + "_draft.roi.zip";
  if (File.length(draft) > 50) roiManager("Open", draft);
  roiManager("Show All without labels");
  z = floor(100 * minOf((screenWidth - 450) / getWidth(), (screenHeight - 150) / getHeight()));
  if (z > 800) z = 800;
  run("Set... ", "zoom=" + z + " x=" + floor(getWidth() / 2) + " y=" + floor(getHeight() / 2));
  setTool("wand");
  msg = "Your note: " + notes[i] + "\n \n";
  msg = msg + "Fix the outlines. New piece: Wand or polygon, then Add.\n";
  msg = msg + "Changed piece: select it, edit, then Update. Wrong piece: select it, Delete.\n";
  msg = msg + "Yellow is not plant. Every leaf in the crop counts.\n \n";
  msg = msg + "OK saves and opens the next. Cancel stops; run again later to carry on.";
  waitForUser(ids[i] + "   (" + (i + 1) + " of " + n + ")   " + names[i], msg);
  selectImage(img);
  run("Select None");
  roiManager("Deselect");
  if (roiManager("count") > 0) roiManager("Save", done);
  else File.saveString("none\n", none);
  roiManager("reset");
  close();
}
showMessage("All done", "Corrected outlines are in " + out);
```

### Launching it

1. Find the Fiji launcher: `ls /Applications/Fiji.app/Contents/MacOS/` (older Fiji:
   `ImageJ-macosx`; newer Fiji: a `fiji-*` launcher). If Fiji is elsewhere, `mdfind -name Fiji.app`.
2. Quit any running Fiji first (ask Aaron; unsaved work in it is his).
3. Launch with the folder as the macro argument, for example:
   `/Applications/Fiji.app/Contents/MacOS/ImageJ-macosx -macro ~/Downloads/drafts-2026-11-09/correct_drafts.ijm ~/Downloads/drafts-2026-11-09/`
   (use the absolute path, ending in `/`). If the launcher does not pass the argument, the macro
   asks for the folder in a dialog: tell Aaron to pick `drafts-2026-11-09`.
4. Fallback if launching from the shell fails: tell Aaron to use Plugins > Macros > Run... in
   Fiji and pick `correct_drafts.ijm`, then the folder.
5. If Fiji reports a macro error, read the message, fix only the syntax (ImageJ macro language),
   save the fixed macro under the same name and relaunch. Do not change what is saved or where.
   This macro was written without being run in Fiji, so a first error is possible.

## The 20 cells that need nothing (do not open them)

| id | name | Aaron's note |
|---|---|---|
| A03 | `prod_2026-10-24_3_D3` | excellent |
| A04 | `prod_2026-10-24_4_B2` | excellent |
| A05 | `prod_2026-10-25_1_C5` | excellent |
| A06 | `prod_2026-10-25_2_A3` | excellent |
| A07 | `prod_2026-10-26_2_D3` | excellent |
| A08 | `prod_2026-10-27_3_C2` | excellent |
| A09 | `prod_2026-10-27_4_B1` | Excellent |
| A10 | `prod_2026-10-27_5_D5` | Excellent |
| A11 | `prod_2026-10-27_6_B4` | excellent |
| A13 | `prod_2026-10-29_1_B3` | Excellent |
| A15 | `prod_2026-10-31_6_C4` | Excellent |
| A16 | `prod_2026-11-01_1_A2` | Excellent |
| A20 | `prod_2026-11-03_3_A2` | Excellent |
| A22 | `prod_2026-11-04_6_B5` | Excellent |
| A23 | `prod_2026-11-05_2_B5` | Excellent |
| B02 | `dev_2026-11-03_77_B2` | Excellent |
| B17 | `dev_2026-11-06_77_B1` | Excellent |
| B25 | `dev_2026-11-08_78_A1` | Excellent |
| B29 | `dev_2026-11-09_86_A2` | Cell border is mostly empty (labeled correctly), green to south of cell is mostly correct |
| B30 | `dev_2026-11-09_87_B1` | Cell is mostly empty, leaves in northeast are correct |

## A28: no plant

`prod_2026-11-08_7_D4` is a green paper target square, not a leaf. Its right answer is "no
plant". Create `corrected/prod_2026-11-08_7_D4_none.txt` containing `none`. The macro does not
open it.

## The 39 cells to correct, in the order the macro opens them

| # | id | name | split | why picked | Aaron's note |
|---|---|---|---|---|---|
| 1 | A01 | `prod_2026-10-22_4_B4` | train | empty | total miss (plant is exceptionally small) |
| 2 | A02 | `prod_2026-10-23_5_C2` | train | empty | total miss (plant is exceptionally small) |
| 3 | A12 | `prod_2026-10-28_4_A3` | train | green soil | soil to north, north east and south are misclassified as green (tens of px) |
| 4 | A14 | `prod_2026-10-30_2_B2` | test | size 2 of 5 | Excellent, very small miss in east leaf |
| 5 | A17 | `prod_2026-11-01_6_A5` | train | empty | Total miss |
| 6 | A18 | `prod_2026-11-02_3_C4` | test | size 4 of 5 | Excellent, complex border in southeast may not be correct (tens of px) |
| 7 | A19 | `prod_2026-11-02_4_D3` | test | size 1 of 5 | Excellent, tiny exclusion in west |
| 8 | A21 | `prod_2026-11-04_1_D5` | train | size 5 of 5 | Small miss on north most leaf edge (tens of px) |
| 9 | A24 | `prod_2026-11-05_6_A2` | test | size 4 of 5 | Excellent, one or two px north of edge that appear misclassified |
| 10 | A25 | `prod_2026-11-06_3_C5` | train | blue mat, size 2 of 5 | border is too tight, misses leaf edge |
| 11 | A26 | `prod_2026-11-07_3_C3` | train | blue mat, size 4 of 5 | border is too tight, misses leaf edge |
| 12 | A27 | `prod_2026-11-07_5_B2` | train | blue mat, size 3 of 5 | border is too tight, misses leaf edge |
| 13 | A29 | `prod_2026-11-09_2_C3` | train | blue mat, size 5 of 5 | border too tight, misses leaf edge |
| 14 | A30 | `prod_2026-11-09_4_C5` | train | blue mat, size 1 of 5 | border too tight, misses leaf edge |
| 15 | B01 | `dev_2026-11-03_76_B2` | train | size 2 of 5 | Small internal error, green soil captured, acceptable border |
| 16 | B03 | `dev_2026-11-03_78_B2` | train | green soil | Small edge error in north and south east leaf |
| 17 | B04 | `dev_2026-11-03_81_A1` | train | size 4 of 5 | Soil classified, small border error on north east most leaf |
| 18 | B05 | `dev_2026-11-03_81_A2` | train | size 3 of 5 | Soil classified |
| 19 | B06 | `dev_2026-11-03_81_B1` | train | green soil | small internal errors |
| 20 | B07 | `dev_2026-11-04_76_B2` | train | size 2 of 5 | soil classified with leaf border in north east |
| 21 | B08 | `dev_2026-11-04_78_B1` | train | size 2 of 5 | small border error in south east leaf |
| 22 | B09 | `dev_2026-11-04_80_B1` | train | size 2 of 5 | Small internal error |
| 23 | B10 | `dev_2026-11-04_80_B2` | train | size 3 of 5 | tiny error inside northeast leaf |
| 24 | B11 | `dev_2026-11-04_81_B2` | train | size 4 of 5 | Soil included in leaf border; green soil classified |
| 25 | B12 | `dev_2026-11-04_85_A2` | train | size 5 of 5 | large region missed in northeast cluster; soil classified |
| 26 | B13 | `dev_2026-11-04_86_A1` | train | size 4 of 5 | small internal errors within leaves, small leaves missed along stem |
| 27 | B14 | `dev_2026-11-05_76_A1` | test | size 3 of 5 | small internal error on yellow leaf |
| 28 | B15 | `dev_2026-11-05_80_A1` | test | green soil | poor border, algea captured |
| 29 | B16 | `dev_2026-11-05_86_B2` | test | size 4 of 5 | small internal error |
| 30 | B18 | `dev_2026-11-06_78_A2` | train | size 1 of 5 | Small internal error |
| 31 | B19 | `dev_2026-11-06_87_A2` | train | empty | Small internal error |
| 32 | B20 | `dev_2026-11-07_77_A1` | train | size 3 of 5 | Extremely small internal errors |
| 33 | B21 | `dev_2026-11-07_79_A1` | train | size 5 of 5 | Small internal errors, large internal error on yellow leaf |
| 34 | B22 | `dev_2026-11-07_80_A2` | train | size 3 of 5 | Small internal errors, bad border on north most leaf |
| 35 | B23 | `dev_2026-11-07_87_A1` | train | size 5 of 5 | Small internal errors |
| 36 | B24 | `dev_2026-11-07_87_A2` | train | empty | Yellow leaf missed entirely (may be acceptable), small internal error in east most region |
| 37 | B26 | `dev_2026-11-08_79_A2` | test | size 5 of 5 | Small miss on southern leaf and south east leaf, yellow leaf in south is complex and wrong |
| 38 | B27 | `dev_2026-11-09_76_A2` | train | size 1 of 5 | Excellent, small miss on southeast leaf (2-10 px) |
| 39 | B28 | `dev_2026-11-09_76_B1` | train | green soil | Yellow leaves missed entirely, green is good, small error internally (2-10 px) |

Groups, to help Aaron:
- Missed plants, outline from nothing: A01, A02, A17 (tiny seedlings).
- Too tight on blue mats, widen the edges: A25, A26, A27, A29, A30.
- Soil, green soil or algae taken as plant: A12, B01, B04, B05, B07, B11, B12, B15.
- Yellow: B21 and B26, remove yellow parts the draft took in. B14, check the yellow leaf.
  B24 and B28, the missed yellow leaves are now right; fix only the other errors.
- Small internal holes and edge errors: the rest.

## Checks you run (without touching any outline)

After every 10 cells, and at the end:
1. For each of the 39 names: exactly one of `<name>_corrected.roi.zip` or `<name>_none.txt`
   exists in `corrected/`. List the missing ones.
2. Each `_corrected.roi.zip` is a valid zip whose entries all end in `.roi`
   (`unzip -l <file>`). Count the entries.
3. Compare the entry count with the draft's (`unzip -l cells/<name>_draft.roi.zip`). A corrected
   zip with exactly 1 entry where the draft had many may mean only one piece was saved: show
   Aaron the id and ask; do not fix it yourself.
4. Write `corrected/notes.txt`: the date, start and end time of the session (local time and
   UTC), anything Aaron says about a doubtful part (id plus a few words), and the check results.

## Sending the results back

When all 39 are saved (or Aaron stops), copy the folder to the controller, without deleting
anything locally:

`scp -r ~/Downloads/drafts-2026-11-09/corrected pi@testpi-02:/home/pi/scratch/402-pixel-classifier/corrected-$(date -u +%Y%m%dT%H%MZ)/`

If ssh to `testpi-02` does not work from this Mac, do not try to fix ssh keys or network
settings; tell Aaron, zip `corrected/` as `~/Downloads/corrected-<date>.zip`, and he will pass it on.

## Report to Aaron at the end

Short and plain: how many of the 39 are saved, which are missing, any warnings from the checks,
where the files went. Then he tells the controller session that the corrections are in.
