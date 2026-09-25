/* ---------------------------------------------------------------------------
   Rig assembly: an "I" made of 40x40 extrusion, plus a camera mount.

   Main rig — one 1500mm beam lies along Y, centred on the origin. Two
   250mm feet lie along X, centred under each end of the beam, stacked
   directly underneath it (foot top face flush against the beam's bottom
   face — zero gap, per "touching"). Overall it reads as a capital "I":
   the long beam is the vertical stroke, the two feet are the serifs.

   Each foot/beam joint is secured with one `bracket_4040_bolted()` (from
   `l_bracket_4040.scad`), mounted on the beam's +X side at the very corner
   where "foot top" meets "beam side": leg A lies flat on the foot's top
   face (bolting straight down into the foot's top T-slot); leg B stands up
   the beam's +X side face (bolting sideways into the beam's side T-slot).
   The bracket carries its own two M6 bolts — see l_bracket_4040.scad.

   The bracket positions below are derived from `l_bracket_4040.scad`'s own
   Customizer defaults (hole centred `hole_edge_dist = 20` mm in from each
   leg's free edge, i.e. `len_a/len_b - 20` from the corner; corner at the
   local origin) via `use`, which does not expose that file's variables —
   so `bracket_hole_a`/`bracket_hole_b` duplicate that derived number by
   hand. Keep them in sync if the bracket's defaults ever change. (They're
   only used for reference/comments now, not for bolt placement.)

   Camera mount — two `bracket_4020_bolted()` (from `l_bracket_4020.scad`)
   clamp a 400mm 20x20 crossbar to the main beam, and an
   `slide_pocket_bolted()` (from `m5_slide_pocket.scad`) rides on that
   crossbar. Each part carries its own joining bolts, same as the main rig.

   Component parts (l_bracket_4040/4020, m5_slide_pocket, t_slot_40x40/
   20x20, t_slot_bolt) stay in their own files; this assembly itself is one
   file. l_bracket_4040.scad and l_bracket_4020.scad each name their
   bracket module `bracket_4040()`/`bracket_4020()` (not plain `bracket()`)
   specifically so both can be `use`d here without one clobbering the
   other's module of the same name.

   Colors: beam, feet, and crossbar silver (aluminum stock); main brackets
   light gray; camera-mount brackets and slide pocket yellow; all bolts
   `bolt_color` (DarkSlateGray, set inside each component file, since
   that's where each bolt call lives — see l_bracket_4040.scad,
   l_bracket_4020.scad, m5_slide_pocket.scad).

   REV 1.4: camera_mount.scad merged back into this file (was split out
     only to dodge the bracket()/bracket() name collision, which is now
     resolved by renaming each bracket file's own module instead); bolt
     color changed from a hardcoded gray to the shared DarkSlateGray
     `bolt_color` variable in each component file.
   REV 1.3: joint bolts moved into l_bracket_4040.scad's bracket_bolted()
     — this file no longer computes bolt length/embedment at all.
   REV 1.2: camera mount modularized into camera_mount.scad.
   REV 1.1: bolt foot embedment derived from the T-slot's actual lip depth,
     shaft length computed per joint instead of a fixed default.
   REV 1.0: initial.
   --------------------------------------------------------------------------- */

use <t_slot_40x40.scad>
use <t_slot_20x20.scad>
use <l_bracket_4040.scad>
use <l_bracket_4020.scad>
use <m5_slide_pocket.scad>

// bracket_4040_bolted()/bracket_4020_bolted()/slide_pocket_bolted() all
// eventually call BOSL2's screw() (via t_slot_bolt.scad), which needs
// BOSL2's special variables ($tags_shown etc.) initialized somewhere in
// the call chain. `use` never runs a dependency's own top-level
// statements — including each component file's own
// `include <BOSL2/std.scad>` — so the file that's actually rendered (this
// one) has to include it directly, no matter how many `use` layers sit
// between here and screw().
include <BOSL2/std.scad>

/* [Rig] */
beam_length = 500; // main beam length along Y, mm
foot_length = 250;  // each foot's length along X, mm

/* [Render] */
$fn = $preview ? 32 : 96;

/* [Hidden] */
profile_half   = 20;   // half of the 40x40 cross-section
bracket_hole_a = 20;   // must match l_bracket_4040.scad's m6_ax (len_a - hole_edge_dist)
bracket_hole_b = 20;   // must match l_bracket_4040.scad's m6_bz (len_b - hole_edge_dist)

corner_x      = profile_half;                 // bracket X: beam's +X side face
foot_z_top    = -profile_half;                // foot top = beam bottom seam
foot_z_center = foot_z_top - profile_half;
foot_x_start  = -foot_length / 2;
beam_y_ends   = [beam_length / 2 - profile_half, -beam_length / 2 + profile_half];

// ---------------------------------------------------------------------------

module beam() {
    color("Silver")
        translate([0, -beam_length / 2, 0])
            rotate([-90, 0, 0])
                t_slot_40x40(len = beam_length);
}

module foot(yc) {
    color("Gray")
        translate([foot_x_start, yc, foot_z_center])
            rotate([0, 90, 0])
                t_slot_40x40(len = foot_length);
}

module joint_bracket(yc) {

        translate([corner_x, yc, foot_z_top])
            bracket_4040_bolted();
}

module camera_mount() {
    translate([20, 0, 25.5])
        rotate([0, 90, 0])
            bracket_4020_bolted();

    translate([-20, 0, 25.5])
        rotate([0, 90, 180])
            bracket_4020_bolted();

    color("silver")
        translate([-400 + 60, 0, 35])
            rotate([0, 90, 0])
                t_slot_20x20(400);

    translate([-400 + 100, -10, 35])
        rotate([90, 0, 0])
            slide_pocket_bolted();
}

beam();
for (yc = beam_y_ends) {
    foot(yc);
    joint_bracket(yc);
}
camera_mount();
