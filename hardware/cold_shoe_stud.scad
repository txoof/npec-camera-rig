/* ---------------------------------------------------------------------------
   Cold shoe stud -- purchased-hardware standin for the square-flange, two-
   step threaded stud that slides into `cold_shoe.scad`'s shoe channel: a
   thin square plate with a 3/8" post rising from it, and a 1/4" post rising
   further from the top of that post (the common flash-stud / umbrella-screw
   shape -- see reference photo). Thread geometry is skipped by request:
   both posts are plain cylinders standing in for the 3/8"-16 and 1/4"-20
   threaded sections, not modeled threads.

   The flange is sized to slide under `cold_shoe.scad`'s lips and be caught
   by them: narrower than that file's channel_w (15mm clear width between
   the side walls) but wider than its gap_w (channel_w - 2*lip_overhang =
   9mm, the open gap between the lip tips) -- read those figures off that
   file rather than `use`-ing it, same as `t_slot_bolt.scad` does for the
   T-slot profile files.

   Coordinate convention: origin centred on the flange in X/Y. Z0 = the
   underside of the flange (the face that rests on the shoe's channel
   floor); both posts rise in +Z from there, the 3/8" post first and the
   1/4" post stacked on top of it.

   Purchased-hardware standin, not a printed structural part -- no
   [Build Plate] or [Revision] group, same reasoning as `t_slot_bolt.scad`.

   REV 1.0: initial.
   --------------------------------------------------------------------------- */

/* [Plate] */
plate_w   = 18;   // square flange width, mm -- fits inside cold_shoe.scad's channel_w (15) and outside its gap_w (9)  [8:0.5:14]
plate_thk = 2;    // flange thickness, mm  [1:0.25:4]
corner_r  = 1;    // corner rounding on the flange, mm (0 = square corners)  [0:0.25:3]

/* [Stud] */
c38_dia = 9.5;   // 3/8" post diameter standin, mm (3/8 in = 9.525mm)  [6:0.5:12]
c38_len = 10;    // 3/8" post height above the plate, mm  [4:0.5:20]
qtr_dia = 6.35;  // 1/4" post diameter standin, mm (1/4 in = 6.35mm)  [4:0.25:8]
qtr_len = 8;     // 1/4" post height above the 3/8" post, mm  [3:0.5:16]

/* [Render] */
$fn = $preview ? 32 : 96;
eps = 0.01;

// ---------------------------------------------------------------------------

module rounded_square(w, r) {
    // plan view (XY): square of side w, centred, corners rounded to r
    hull() for (sx = [-1, 1], sy = [-1, 1])
        translate([sx * (w / 2 - r), sy * (w / 2 - r)]) circle(r);
}

module cold_shoe_stud() {
    linear_extrude(plate_thk) rounded_square(plate_w, corner_r);

    translate([0, 0, plate_thk - eps])
        cylinder(d = c38_dia, h = c38_len + eps);

    translate([0, 0, plate_thk + c38_len - eps])
        cylinder(d = qtr_dia, h = qtr_len + eps);
}

cold_shoe_stud();
