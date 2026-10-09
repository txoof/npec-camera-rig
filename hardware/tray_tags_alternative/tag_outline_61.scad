/* ---------------------------------------------------------------------------
   Tag outline, 61 mm -- 2D outline of a rounded-corner square with a
   centre circle, copied from a physical part, to print on paper at 1:1 and
   lay over that part to check the dimensions before it becomes an
   AprilTag plate.

   2D only. Export with -o out.dxf (CAD), -o out.svg or -o out.pdf (paper).
   Print at 100% / "actual size", never "fit to page".

   Corner radius is derived, not measured directly. On the physical part:
     - square side                         61 mm
     - centre circle diameter              48.84 mm
     - circle edge to the outline, across
       the corner (the widest point)       14.8 to 14.9 mm
   Along the diagonal, the outline sits at (s/2 - r) * sqrt(2) + r from
   the centre, so
       r = (s/2 * sqrt(2) - d/2 - g) / (sqrt(2) - 1)
   with s = 61, d = 48.84, g = 14.85 gives r = 9.33 mm. The 0.1 mm spread
   in g moves r by 0.24 mm (9.21 to 9.45): every 0.1 mm in g is 0.24 mm
   in r. `corner_r` below is a starting value to check on paper, not a
   measurement.

   Coordinate convention: centred on X = Y = 0, outline in the XY plane.

   REV 1: first outline, corner radius derived from the diagonal gap.
   --------------------------------------------------------------------------- */

/* [Outline] */
// mm, side of the square [20:200]
side = 61;
// mm, corner radius; 9.33 derived from the 14.85 mm diagonal gap [0:30]
corner_r = 9.33;

/* [Centre Circle] */
// cut the centre circle (true) or print the solid outline (false)
show_circle = true;
// mm, diameter of the centre circle [0:150]
circle_d = 48.84;

/* [Render] */
$fn = $preview ? 64 : 360;
eps = 0.01;

/* [Hidden] */
// mm, diagonal gap this radius predicts; compare with the 14.8 to 14.9 measured
predicted_gap = (side / 2 - corner_r) * sqrt(2) + corner_r - circle_d / 2;
echo(str("corner_r = ", corner_r, " mm, predicted diagonal gap = ",
         predicted_gap, " mm"));

module rounded_square(s, r) {
    hull()
        for (x = [-1, 1], y = [-1, 1])
            translate([x * (s / 2 - r), y * (s / 2 - r)])
                circle(r = r);
}

module tag_outline() {
    difference() {
        rounded_square(side, corner_r);
        if (show_circle) circle(d = circle_d);
    }
}

tag_outline();
