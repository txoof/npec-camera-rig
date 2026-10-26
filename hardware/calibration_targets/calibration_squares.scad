/* ---------------------------------------------------------------------------
   Calibration squares: flat squares of known area, one build plate

   PRINT IN GREEN FILAMENT.  The squares stand in for plant canopy, so they
   must be the colour the segmenter looks for.

   Twelve thin squares on one plate: four 10x10, four 20x20, two 40x40 and
   two 55x55 (mm), all `thickness` thick.  Z0 is the bed; every square lies
   flat on it.  The plate is centred on the origin.

   Layout, three columns, each separated by `gap`:
     left   - the two 55 squares, stacked
     middle - the two 40 squares, stacked, with the four 10 squares in a
              2 x 2 block below them
     right  - the four 20 squares, stacked
   Overall about 121 x 113 mm with the default gap.

   No [Build Plate] group: the file is already the whole plate, and the
   counts are fixed by the layout above.  No [Revision] stamp: engraving
   would remove green from the face and change the area being measured.

   REV 1.0: first version.
   --------------------------------------------------------------------------- */

/* [Squares] */
thickness = 0.568; // square thickness, mm  [0.2:0.001:3]
size_xl   = 55;    // largest square side, two copies, mm  [40:1:80]
size_l    = 40;    // large square side, two copies, mm  [20:1:55]
size_m    = 20;    // medium square side, four copies, mm  [10:1:40]
size_s    = 10;    // small square side, four copies, mm  [5:1:20]

/* [Layout] */
gap = 3; // space between squares, mm  [1:0.5:10]

/* [Render] */
$fn = $preview ? 32 : 96;
eps = 0.01;

/* [Hidden] */
col_l_x = 0;                        // left column's -X edge
col_m_x = col_l_x + size_xl + gap;  // middle column's -X edge
col_r_x = col_m_x + size_l + gap;   // right column's -X edge
small_y = 2 * (size_l + gap);       // bottom of the 2 x 2 block of small squares

plate_w = col_r_x + size_m;
plate_h = max(2 * size_xl + gap,
              small_y + 2 * size_s + gap,
              4 * size_m + 3 * gap);

module square_target(side) {
    color("green") cube([side, side, thickness]);
}

// n squares of `side`, stacked along +Y from (x, y)
module column_of(side, n, x, y = 0) {
    for (i = [0 : n - 1])
        translate([x, y + i * (side + gap), 0]) square_target(side);
}

module calibration_plate() {
    translate([-plate_w / 2, -plate_h / 2, 0]) {
        column_of(size_xl, 2, col_l_x);
        column_of(size_l, 2, col_m_x);
        for (i = [0 : 1])
            column_of(size_s, 2, col_m_x + i * (size_s + gap), small_y);
        column_of(size_m, 4, col_r_x);
    }
}

calibration_plate();
