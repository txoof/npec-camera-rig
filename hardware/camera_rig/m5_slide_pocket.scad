
/* ---------------------------------------------------------------------------
   M5 slide-in pocket plate

   A 4 mm base plate carrying a shallow, roofed pocket that captures an
   18 x 18 x 2 mm square plate -- the flange of a square-flange bolt / stud,
   or a loose square washer with an M5 bolt through it.

   The pocket opens toward +Y.  The square plate is pushed in along -Y until
   it bottoms against the back wall; the roof holds it down so it cannot lift
   out, and a channel milled through the roof lets the M5 shaft standing
   perpendicular to that plate ride in with it, ending up on the part axis.
   That channel is sized to pass the bolt head, not just the shaft, so the
   bolt can go in already seated in its flange.

   The base plate reaches out past the pocket block on both +X and -X into a
   pair of ears that repeat the block's own footprint, giving a plain
   rounded-rectangle plate with an M5 clearance hole at each end.  Those holes
   sit far enough out that a bolt head on the top face keeps `head_clear`
   head-radii of clear space between its rim and the side wall of the pocket
   block -- room for a socket or a finger.  The offset is derived, so changing
   the head size, the wall thickness or the pocket size moves the holes to
   suit.

   The revision is engraved into the top face of the -X ear, clear of the bolt
   hole and clear of the pocket block.

   Origin = pocket axis (the captured bolt).  Z0 = the underside of the base
   plate (mating face), which is also the print bed: all material grows in +Z.

   Set `copies` under [Build Plate] to lay out that many parts in a grid,
   centred on the origin.  copies = 1 renders the single part at the origin.

   `slide_pocket_bolted()` adds this part's own two mounting bolts (M5,
   from `t_slot_bolt.scad`) through the ear holes, into whatever 20x20
   T-slot extrusion it's riding on — sized so each head lands flush on the
   top face (shaft_length = base_thk + that profile's T-slot lip depth, no
   extra margin).

   Rev 2: added slide_pocket_bolted() — the two mounting bolts now live
     here instead of being re-derived (with a hand-duplicated `bolt_x`) in
     every assembly file that places this part.
   Rev 1:
    - increase base plate to 7mm (works better with stock hardware)
    - increase roof thickness
   --------------------------------------------------------------------------- */

use <../libraries/t_slot_bolt.scad>
include <../libraries/BOSL2/std.scad> // t_slot_bolt() calls BOSL2's screw(); `use` alone
                          // wouldn't run t_slot_bolt.scad's own top-level
                          // include, so its special variables never init

/* [Revision] */
revision  = "RV1.0"; // revision stamp, engraved in the -X ear top face ("" = none)
rev_size  = 4;       // cap height of the text, mm; past ~6 it crowds the block  [2:0.5:6]
rev_depth = 1.2;     // how far the text is inset below the surface, mm  [1:0.1:1.5]

/* [Base Plate] */
base_thk = 7;    // plate thickness under the pocket floor
corner_r = 3;    // rounding on the plate and pocket-block corners (plan view)
ear_w    = 0;    // bolt-ear footprint, square, mm; 0 = match the pocket block

/* [Insert Pocket] */
insert_w   = 18;   // square plate width, nominal
insert_thk = 2;    // square plate thickness, nominal
fit_xy     = 0.4;  // total side-to-side slop across the pocket (0.4 = snug slide)
fit_z      = 0.3;  // total slop over the plate thickness
wall_thk   = 4;    // pocket side/back wall thickness  [1:0.5:10]
roof_thk   = 4;    // roof over the pocket; 0 leaves an open recess  [0:0.5:8]
mouth_lead = 0.8;  // lead-in flare at the pocket mouth (0 = square mouth)

/* [Fasteners] */
m5_dia     = 5.5;  // M5 clearance through the base plate (normal fit)
channel_w  = 10;   // roof channel: >= 10 passes the M5 head, not just the shaft  [6:0.5:16]
hole_cham  = 0.6;  // 45-deg relief at both ends of every bore, 0 to disable
head_dia   = 8.5;  // M5 socket cap head; hex across corners 9.3, plain washer 10
head_clear = 0.75; // clear space from the head rim out to the pocket wall, in head radii
mount_x    = 0;    // ear hole centre from the axis, mm; 0 = auto (minimum clearance)
center_bore = false; // also bore the axis, so a long bolt can pass through the stack

lip_depth_20    = 1.8; // 20x20 T-slot lip depth (see t_slot_20x20.scad's header)
foot_thk_ref_20 = 1.5; // must match t_slot_bolt.scad's foot_thk_20
bolt_color      = "DarkSlateGray"; // color for all bolt standins

/* [Build Plate] */
copies     = 1;    // how many parts to lay out  [1:200]
plate_gap  = 5;    // clear space between neighbours, mm
plate_cols = 0;    // columns across X; 0 = auto (near-square grid)

/* [Render] */
$fn = $preview ? 32 : 96;
eps = 0.01;

/* [Hidden] */
pocket_w  = insert_w + fit_xy;            // pocket footprint, square
pocket_h  = insert_thk + fit_z;           // pocket height
block_w   = pocket_w + 2 * wall_thk;      // pocket block footprint, square
floor_z   = base_thk;                     // pocket floor
roof_z    = base_thk + pocket_h;          // underside of the roof
top_z     = roof_z + roof_thk;            // overall height
y_mouth   = block_w / 2;                  // +Y face: where the plate goes in

head_r    = head_dia / 2;
ear_size  = ear_w > 0 ? ear_w : block_w;  // ears repeat the block footprint
// hole centre far enough out that the head rim clears the block side wall by
// head_clear head-radii.  A hand-set mount_x is held to that same minimum.
mount_min = block_w / 2 + head_r * (1 + head_clear);
bolt_x    = mount_x > 0 ? max(mount_x, mount_min) : mount_min;
chan_w    = max(channel_w, m5_dia);       // the shaft has to fit regardless

rev_gap    = 1.5;                         // clear space between the bolt head and the text
// text centre clears the head rim, not just the bore, so a seated bolt or
// washer never sits over the engraving
rev_cy     = head_r + rev_gap + rev_size / 2;

part_dx   = 2 * bolt_x + ear_size;
part_dy   = max(block_w, ear_size);
grid_cols = plate_cols > 0 ? plate_cols : ceil(sqrt(copies));
grid_rows = ceil(copies / grid_cols);
pitch_x   = part_dx + plate_gap;
pitch_y   = part_dy + plate_gap;

// ---------------------------------------------------------------------------

module rounded_square(w, r) {
    // plan view (XY): square of side w, centred, corners rounded to r
    hull() for (sx = [-1, 1], sy = [-1, 1])
        translate([sx * (w / 2 - r), sy * (w / 2 - r)]) circle(r);
}

module block_profile() {
    // the walled pocket block
    rounded_square(block_w, corner_r);
}

module base_profile() {
    // the block footprint stretched out to an equal-sized ear each side
    hull() {
        block_profile();
        for (sx = [-1, 1])
            translate([sx * bolt_x, 0]) rounded_square(ear_size, corner_r);
    }
}

module pocket_cavity() {
    // the slide-in slot: back face at -pocket_w/2, open through the +Y face.
    // Runs the full way out so the mouth is flush with the outer wall.
    translate([-pocket_w / 2, -pocket_w / 2, floor_z])
        cube([pocket_w, y_mouth + pocket_w / 2 + eps, pocket_h]);

    // lead-in flare: widens the mouth sideways and upward, floor left flat so
    // the plate slides in on one continuous surface
    if (mouth_lead > 0)
        hull() {
            translate([-pocket_w / 2, y_mouth - mouth_lead, floor_z])
                cube([pocket_w, eps, pocket_h]);
            translate([-pocket_w / 2 - mouth_lead, y_mouth, floor_z])
                cube([pocket_w + 2 * mouth_lead, eps, pocket_h + mouth_lead]);
        }
}

module channel_profile() {
    // plan view (XY): round seat on the axis, opening out through the +Y face
    hull() {
        circle(d = chan_w);
        translate([-chan_w / 2, 0]) square([chan_w, y_mouth + eps]);
    }
}

module bolt_channel() {
    // slot through the roof only: the bolt head and shaft ride this while the
    // square plate slides along the pocket floor
    translate([0, 0, roof_z - eps])
        linear_extrude(roof_thk + 2 * eps) channel_profile();
}

module m5_bore() {
    // M5 clearance through the base plate, relieved at both faces
    translate([0, 0, -eps]) cylinder(d = m5_dia, h = base_thk + 2 * eps);
    if (hole_cham > 0) {
        translate([0, 0, -eps])
            cylinder(d1 = m5_dia + 2 * hole_cham, d2 = m5_dia, h = hole_cham + eps);
        translate([0, 0, base_thk - hole_cham])
            cylinder(d1 = m5_dia, d2 = m5_dia + 2 * hole_cham, h = hole_cham + eps);
    }
}

module revision_stamp() {
    // engraved into the -X ear top face: centred on the bolt hole in X, sitting
    // clear of the bolt head in +Y; overshoots the face by eps for a clean cut
    translate([-bolt_x, rev_cy, base_thk - rev_depth])
        linear_extrude(rev_depth + eps)
            text(revision, size = rev_size,
                 halign = "center", valign = "center");
}

module slide_pocket() {
    difference() {
        union() {
            linear_extrude(base_thk) base_profile();
            linear_extrude(top_z)    block_profile();
        }
        pocket_cavity();
        bolt_channel();
        for (sx = [-1, 1]) translate([sx * bolt_x, 0, 0]) m5_bore();
        if (center_bore) m5_bore();
        if (revision != "") revision_stamp();
    }
}

module slide_pocket_bolted() {
    // assembly view: slide_pocket() plus its own two M5 mounting bolts,
    // feet seated lip_depth+foot_thk_ref under the T-slot lip, heads
    // landing flush (shaft_length = base_thk + lip_depth).
    slide_pocket();

    for (sx = [-1, 1])
        color(bolt_color)
            translate([sx * bolt_x, 0, -(lip_depth_20 + foot_thk_ref_20)])
                t_slot_bolt(screw_size = "M5", profile = 20,
                            shaft_length = base_thk + lip_depth_20);
}

module plate(n) {
    // grid is centred on the origin; index 0 is the -X/-Y corner
    x0 = -(grid_cols * pitch_x - plate_gap) / 2 + part_dx / 2;
    y0 = -(grid_rows * pitch_y - plate_gap) / 2 + part_dy / 2;
    for (i = [0 : n - 1])
        translate([x0 + (i % grid_cols)      * pitch_x,
                   y0 + floor(i / grid_cols) * pitch_y,
                   0])
            slide_pocket();
}

if (copies > 1) plate(copies); else slide_pocket();
