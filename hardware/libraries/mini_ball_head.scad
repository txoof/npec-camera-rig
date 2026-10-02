/* ---------------------------------------------------------------------------
   Mini ball head -- purchased-hardware standin for the small SmallRig-style
   cold-shoe ball head (BOM: "Ball Head Cold Shoe Mount (small)"): a squat
   cylindrical housing with a flip lock lever on the side, a pivot ball
   sitting mostly proud of the housing top, and a knurled cap on the ball
   carrying a 1/4" mounting stud. By request this model is a static
   representation for documentation/instructions only, not a working
   articulated joint -- the ball is fixed in one pose, there is no captured
   socket cavity or lock mechanism, and (matching the same call made in
   `cold_shoe_stud.scad`) no thread geometry is modeled: the female socket
   at the bottom and the male stud on top are both plain, unthreaded
   cylinders standing in for 1/4"-20 UNC.

   Dimensions are approximate, hand-picked to read as the right size and
   shape in a render -- no manufacturer drawing exists for this generic
   part, same situation as `cold_shoe.scad`. Do not treat any figure here as
   measured.

   Coordinate convention: origin centred on the housing in X/Y. Z0 = the
   underside of the housing (where the female-thread standin bore opens),
   the housing rises in +Z, the ball sits on top of it (partly overlapping
   into the housing for a captured look), and the cap + stud rise further
   in +Z from the top of the ball. The lock lever sticks out radially in
   +X from the housing wall.

   Purchased-hardware standin, not a printed structural part -- no
   [Build Plate] or [Revision] group, same reasoning as `cold_shoe_stud.scad`
   and `t_slot_bolt.scad`.

   REV 1.0: initial.
   --------------------------------------------------------------------------- */

/* [Housing] */
base_dia     = 22;    // main housing diameter, mm  [15:1:30]
base_h       = 10;    // main housing height, mm  [6:1:18]
socket_dia   = 6.35;  // female 1/4" thread standin bore diameter, mm (1/4 in = 6.35mm; plain bore, no thread modeled)  [5:0.25:8]
socket_depth = 8;     // female thread standin bore depth, mm, blind upward from Z0  [4:0.5:16]

/* [Lock Lever] */
lever_len = 11;  // paddle length, measured out from the housing wall, mm  [6:0.5:18]
lever_w   = 5;   // paddle width at the base (near the housing), mm  [3:0.5:8]
lever_thk = 4;   // paddle thickness (extrusion height), mm  [2:0.5:6]
lever_z   = 6;   // paddle centre height above Z0, mm  [3:0.5:14]

/* [Ball] */
ball_dia      = 18;  // pivot ball diameter, mm  [12:1:26]
ball_center_z = 11;  // height of the ball's centre above Z0, mm -- kept below base_h so the lower part of the sphere reads as captured inside the housing  [6:0.5:22]

/* [Stud] */
cap_dia = 10;    // knurled cap diameter atop the ball, mm  [7:0.5:16]
cap_h   = 4;     // knurled cap height, mm  [2:0.5:8]
qtr_dia = 6.35;  // male 1/4" stud standin diameter, mm (1/4 in = 6.35mm)  [4:0.25:8]
qtr_len = 7;     // male 1/4" stud standin height above the cap, mm  [3:0.5:14]

/* [Render] */
$fn = $preview ? 32 : 96;
eps = 0.01;

/* [Hidden] */
cap_z = ball_center_z + ball_dia / 2 - eps;  // cap base sits right on the ball's top pole, slight overlap for a clean union

// ---------------------------------------------------------------------------

module housing() {
    cylinder(d = base_dia, h = base_h);
}

module socket_bore() {
    translate([0, 0, -eps])
        cylinder(d = socket_dia, h = socket_depth + eps);
}

module lever_profile() {
    // plan view (XY): paddle shape, hull of a narrow circle at the wall and
    // a wider one at the tip
    hull() {
        circle(d = lever_w);
        translate([lever_len, 0]) circle(d = lever_w * 1.4);
    }
}

module lever() {
    translate([base_dia / 2 - eps, 0, lever_z - lever_thk / 2])
        linear_extrude(lever_thk)
            lever_profile();
}

module ball() {
    translate([0, 0, ball_center_z]) sphere(d = ball_dia);
}

module cap_and_stud() {
    translate([0, 0, cap_z])
        cylinder(d = cap_dia, h = cap_h);

    translate([0, 0, cap_z + cap_h - eps])
        cylinder(d = qtr_dia, h = qtr_len + eps);
}

module mini_ball_head() {
    color("SteelBlue")
        difference() {
            union() {
                housing();
                lever();
                ball();
                cap_and_stud();
            }
            socket_bore();
        }
}

mini_ball_head();
