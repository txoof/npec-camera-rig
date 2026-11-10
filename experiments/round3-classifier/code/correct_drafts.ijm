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
  if (parseInt(File.length(draft)) > 50) roiManager("Open", draft);
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
