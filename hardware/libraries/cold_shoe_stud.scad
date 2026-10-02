/* ---------------------------------------------------------------------------
   Cold shoe stud -- purchased-hardware standin for the square-flange, two-
   step threaded stud that slides into a cold shoe channel: a
   thin square plate with a 3/8" post rising from it, and a 1/4" post rising
   further from the top of that post (the common flash-stud / umbrella-screw
   shape -- see reference photo). Thread geometry is skipped by request:
   both posts are plain cylinders standing in for the 3/8"-16 and 1/4"-20
   threaded sections, not modeled threads.

   No Customizer settings: the flange fits a standard ISO 518 accessory
   shoe and the posts are the nominal 3/8" and 1/4" diameters; see the
   [Hidden] group. Post heights and corner rounding have no standard and
   are mockup values, not measured from the purchased stud.

   Coordinate convention: origin centred on the flange in X/Y. Z0 = the
   underside of the flange (the face that rests on the shoe's channel
   floor); both posts rise in +Z from there, the 3/8" post first and the
   1/4" post stacked on top of it.

   Purchased-hardware standin, not a printed structural part -- no
   [Build Plate] or [Revision] group, same reasoning as `t_slot_bolt.scad`.

   REV 1.0: initial.
   REV 1.1: comments only; dropped references to the removed cold_shoe.scad.
   REV 1.2: all dimensions fixed in [Hidden], no Customizer settings.
            Flange to ISO 518 shoe limits; 3/8" post 9.5 -> 9.525 mm.
   --------------------------------------------------------------------------- */

/* [Render] */
$fn = $preview ? 32 : 96;
eps = 0.01;

/* [Hidden] */
// Nothing here is a Customizer setting: the stud follows the standards.
// Flange fits an ISO 518 shoe: inside width 18.6 mm (+0.2/-0), gap between
// the lips 12.5 mm (+0.4/-0), slot height 2 mm (+0.15/-0). ISO 518 gives
// no foot dimensions; these fit those shoe limits.
plate_w   = 18;      // square flange width, mm: under 18.6, over 12.5
plate_thk = 2;       // flange thickness, mm: the slot's minimum height
corner_r  = 1;       // flange corner rounding, mm (not standardised)

// Posts: nominal 3/8"-16 and 1/4"-20 UNC major diameters, unthreaded.
c38_dia = 3/8 * 25.4;   // 9.525 mm
qtr_dia = 1/4 * 25.4;   // 6.35 mm
c38_len = 10;           // 3/8" post height above the flange, mm (not standardised)
qtr_len = 8;            // 1/4" post height above the 3/8" post, mm (not standardised)

// ---------------------------------------------------------------------------

module rounded_square(w, r) {
    // plan view (XY): square of side w, centred, corners rounded to r
    hull() for (sx = [-1, 1], sy = [-1, 1])
        translate([sx * (w / 2 - r), sy * (w / 2 - r)]) circle(r);
}

module cold_shoe_stud() {
color("DimGray") {
    linear_extrude(plate_thk) rounded_square(plate_w, corner_r);

    translate([0, 0, plate_thk - eps])
        cylinder(d = c38_dia, h = c38_len + eps);

    translate([0, 0, plate_thk + c38_len - eps])
        cylinder(d = qtr_dia, h = qtr_len + eps);
    }
}

cold_shoe_stud();
