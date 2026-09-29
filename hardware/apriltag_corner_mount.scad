/* ---------------------------------------------------------------------------
   AprilTag corner/reference mount -- 50 mm 36h11 tag, bolted to a 20x20
   T-slot rail at the table's outer edge (PLAN.md's four permanent corner
   fiducials, IDs 450-499; see
   reference/calibration-sheets/apriltags-36h11-50mm-a4-450-499.pdf for the
   confirmed tag size and family).

   One continuous multi-material print, two colors, no assembly step:
     - `tag_mount_body()` -- the structural bracket: rail foot, keying ridge,
       and a flat tag plate whose top face is the tag's white background
       and quiet zone. One color (`body_color`).
     - `tag_mount_graphic()` -- the dark 36h11 layer for `tag_id`, via
       `apriltag_36h11.scad`'s `april_tag_pattern()`, standing `tag_raise_h`
       proud of the plate and sunk `tag_embed` into it so the two parts
       overlap rather than merely touch. One color (`tag_pattern_color`).
   `apriltag_36h11.scad`'s `april_tag_base()` is not used here: the body
   already supplies the background.

   Export with `scad_to_3mf.py` so Orca loads both as parts of one object
   with a filament each; see that script and `3mf_test.scad`.

   The bit data and the row/col-to-XY placement are `apriltag_36h11.scad`'s
   responsibility, verified there (point-containment check against
   apriltag_gen.tags.tag_bits(), see that file's header) against the
   project's governing principle -- a silently wrong pattern fails
   "undetectable", not "loud". This file only positions that already-verified
   graphic within the frame; it does not re-derive or re-check the pattern.

   Coordinate convention: X runs along the rail's length, parallel to the
   T-slot channel and to the line joining the two M4 bolts. Y runs away from
   the rail, across the tag plate's long axis -- perpendicular to the
   channel, per Aaron's correction 2026-09-28 (the channel must run
   perpendicular to the tag's longest dimension, and the foot's 20mm width
   is measured in Y, not X). Z is vertical; Z=0 is the rail's top face,
   which is also the tag plate's flat top face once bolted down (the dark
   tag layer spans Z=-tag_embed to Z=tag_raise_h -- see
   `tag_mount_graphic()`). The foot's mating (underside) face is at Z=0,
   rising to Z=foot_thk; the tag plate hangs from that same Z=0 plane down to
   Z=-tag_plate_thk, so stepping down from the foot's top face by foot_thk
   lands exactly on the plate's flush top surface.

   Fastening: two M4 bolts into type-6 (spring-loaded ball) T-nuts dropped
   into the rail's channel -- the same channel `t_slot_bolt.scad` models
   with `profile=20`. This file doesn't model the T-nut itself; see
   `tag_mount_bolted()` for an assembly-view standin.

   Alignment lip: a keying ridge under the foot, sized to the 20x20
   profile's slot mouth (6.1 mm, per `t_slot_20x20.scad`'s header) -- the
   same figure `l_bracket_4020.scad`'s `ridge20_w` reuses for its own 20-leg
   ridge. Runs along X (the channel direction), with a relief cut at each
   bolt so the ridge doesn't block the T-nut/bolt shaft -- same construction
   as that file's `ridge20_relief()`/`ridge20_cove()`, ported to a ridge that
   runs along X instead of Z, and widened to two cuts instead of one.

   Open assumption, not yet measured: `tag_border` (quiet-zone margin) is an
   informed starting point -- general AprilTag detection guidance, not a
   calliper reading or a live detector result. Revisit once a printed mount
   and a real detection pass exist, same as any other unmeasured number in
   this project. `tag_embed` is likewise a starting value for part overlap
   in the slicer, not a measured one.

   REV 1.4: two colors instead of three (2026-09-29). The body is now the
     tag's white background, so the separate white base plate and the pocket
     it sat in are gone; the dark layer sits on the flat plate, sunk
     `tag_embed` into it. Removed `tag_base_thk`, `tag_base_color`,
     `tag_mount_graphic_base()`/`_pattern()`; added `tag_embed`. Defaults
     changed to a White body and DarkGreen tag.
   REV 1.3: switched `tag_mount_face()` (a blank, clearance-fit insert) for
     `tag_mount_graphic()` (the real `tag_id` pattern, flush, no clearance)
     now that the actual target is a multi-material printer doing one
     continuous print, not a single-extruder print needing a separately
     glued-in piece. Removed `tag_clearance` (nothing left to fit) and
     renamed `insert_thk` to `tag_base_thk` (it is the graphic's own base
     thickness now, not an insert depth); added `tag_id`, `tag_raise_h`,
     `tag_pattern_color`; renamed `tag_color` to `tag_base_color`.
   REV 1.2: Aaron replaced `transition_fillet()` with `transition_chamfer()`
     (2026-09-28) -- REV 1.1's concave fillet was a "square minus circle"
     sliver, thin by construction near both tangent points. The chamfer is a
     solid convex quarter-disc instead: same corner, same tangent
     constraints, but filled rather than carved, so it doesn't pinch down to
     a feather edge. Default `transition_r` set to match `foot_thk` (7mm) so
     the chamfer sweeps the full step height by default, with no leftover
     sharp vertical wall above it -- `tr = min(transition_r, foot_thk)`
     still caps it if the two are ever set to disagree.
   REV 1.1: fixed an impossible joint -- REV 1.0's foot (Y>=0) and tag plate
     (Y<=0) only ever shared the single line Y=0,Z=0, since the two solids
     occupied disjoint Z ranges that merely touched at that line. Zero
     contact area, not a real face: two lobes of a single printed part
     cannot be connected by a knife-edge. Fixed by adding
     `transition_fillet()` -- concave, radius `transition_r`, same
     construction as `l_bracket_4020.scad`'s `inner_fillet()` -- occupying
     Y in [-transition_r,0] and rising from Z=0 to Z=transition_r, so it
     shares a genuine 2D face with the foot's Y=0 wall AND with the tag
     plate's Z=0 top, gluing the two into one solid. Deliberately does not
     extend into Y>0 (under the foot): that footprint is where the physical
     20x20 rail sits, and material there beyond the keying ridge (shaped to
     enter the rail's own channel groove) would collide with solid
     aluminum, not air.
   REV 1.0: initial.
   --------------------------------------------------------------------------- */

use <t_slot_bolt.scad>
use <apriltag_36h11.scad>
include <BOSL2/std.scad> // t_slot_bolt() calls BOSL2's screw(); `use` alone
                          // wouldn't run t_slot_bolt.scad's own top-level
                          // include, so its special variables never init

/* [Tag] */
tag_id        = 450;   // which 36h11 id this mount instance carries -- corner/reference tags (PLAN.md, IDs 450-499) [1:499]
tag_size      = 50;    // 36h11 tag width, mm -- corner/reference tags (PLAN.md, IDs 450-499)
tag_border    = 10;    // quiet-zone margin each side, mm -- informed default, not yet measured [4:1:25]
tag_plate_thk = 3;     // total tag-plate thickness, mm  [2:0.5:6]
tag_raise_h   = 0.6;   // dark tag layer height above the plate's top face, mm  [0.2:0.1:2]
tag_embed     = 0.2;   // how far the dark layer sinks into the plate so the parts overlap, mm  [0:0.05:1]

/* [Rail Foot] */
foot_width   = 20;    // Y depth -- matches the 20x20 rail's face width, mm
foot_thk     = 7;     // Z thickness, mm
corner_r     = 3;     // rounding on the two free (outer) corners of the foot and tag plate, mm

/* [Fasteners] */
bolt_dia     = 4.5;   // M4 clearance hole, mm
bolt_spacing = 40;    // X distance between the two bolts, mm  [20:5:60]
hole_cham    = 1.0;   // 45-deg relief at the bolt entry face, mm (0 = none)
bolt_color   = "DarkSlateGray"; // color for the assembly-view bolt standins

lip_depth_20    = 1.8; // 20x20 T-slot lip depth -- must match t_slot_20x20.scad's header figure
foot_thk_ref_20 = 1.5; // must match t_slot_bolt.scad's foot_thk_20

/* [Ridge] */
ridge_w        = 6.0;  // slot-mouth width, mm -- see t_slot_20x20.scad header
ridge_h        = 3;    // drop depth into the channel, mm
ridge_draft    = 0.4;  // per-side taper at the tip, mm
ridge_relief   = 8;    // relief width at each bolt, along X, mm
ridge_relief_r = 1.5;  // transition curve at each relief end, mm (0 = square step)

/* [Transition] */
transition_r = 7;  // chamfer radius at the foot/tag-plate step, mm -- should match foot_thk
                    // (the full step height) so the chamfer sweeps the whole step with no
                    // leftover vertical wall above it; 0 = sharp corner [0:0.5:10]

/* [Colors] */
body_color        = "White";     // also the tag's background and quiet zone
tag_pattern_color = "DarkGreen"; // the tag's dark modules

/* [Render Select] */
part = "assembly"; // what to render  ["assembly","body","graphic","bolted"]

/* [Build Plate] */
copies     = 1;   // how many bodies to lay out when part="body"  [1:8]
plate_gap  = 10;  // clear space between neighbours, mm
plate_cols = 0;   // columns across X; 0 = auto (near-square grid)

/* [Revision] */
revision  = "RV1.0"; // revision stamp, engraved in the foot's top face ("" = none)
rev_size  = 4;        // text cap height, mm  [2:0.5:8]
rev_depth = 1.0;      // how far the text is inset below the surface, mm  [0.4:0.1:2]

/* [Render] */
$fn = $preview ? 32 : 96;
eps = 0.01;

/* [Hidden] */
// plate footprint: X shared by foot and tag plate, Y split at the Y=0 joint
// (foot spans [0,foot_width], tag plate spans [-pd,0])
pw = tag_size + 2 * tag_border; // plate width, X
pd = tag_size + 2 * tag_border; // tag plate depth, Y
bolt_x = [-bolt_spacing / 2, bolt_spacing / 2];
tr = min(transition_r, foot_thk); // clamp: a chamfer taller than the foot has nothing to blend into

part_dx   = pw;
part_dy   = foot_width + pd;
grid_cols = plate_cols > 0 ? plate_cols : ceil(sqrt(copies));
grid_rows = ceil(copies / grid_cols);
pitch_x   = part_dx + plate_gap;
pitch_y   = part_dy + plate_gap;

// ---------------------------------------------------------------------------

module chamfered_hole(dia, len, cham) {
    // bore along +Z starting at Z=0, with a cone relief at the Z=0 entry
    cylinder(d = dia, h = len);
    if (cham > 0)
        translate([0, 0, -eps])
            cylinder(d1 = dia + 2 * cham, d2 = dia, h = cham + eps);
}

module foot_profile() {
    // XY plan view: square at the Y=0 joint, rounded at the free (Y=foot_width) edge
    hull() {
        translate([-pw / 2, 0]) square([pw, eps]);
        translate([-pw / 2 + corner_r, foot_width - corner_r]) circle(corner_r);
        translate([ pw / 2 - corner_r, foot_width - corner_r]) circle(corner_r);
    }
}

module tag_plate_profile() {
    // XY plan view: square at the Y=0 joint, rounded at the free (Y=-pd) edge.
    // Stops at Y=0 -- must NOT extend under the foot: that footprint is
    // where the physical 20x20 rail sits, so any plastic there beyond the
    // ridge (which is shaped to enter the rail's own channel groove) would
    // collide with solid aluminum, not air.
    hull() {
        translate([-pw / 2, 0]) square([pw, eps]);
        translate([-pw / 2 + corner_r, -pd + corner_r]) circle(corner_r);
        translate([ pw / 2 - corner_r, -pd + corner_r]) circle(corner_r);
    }
}

module transition_chamfer() {
    // fills the concave corner where the tag plate's flush top face (Y<0,
    // Z=0) meets the foot's rising face (Y=0, Z>0) -- a solid quarter-disc,
    // radius `tr`, running the full plate width (X). Convex, not a carved
    // "square minus circle" sliver (see REV 1.2 in the file header): this
    // fills the whole corner, so it doesn't taper to a feather edge at the
    // tangent points the way REV 1.1's `transition_fillet()` did.
    translate([-pw / 2, 0, 0])
        rotate([0, 90, 0]) linear_extrude(pw)
            difference() {
                circle(tr);
                translate([0, -tr]) square(tr * 2);
                translate([-tr, 0]) square(tr * 2);
            }
}

module ridge_along_x() {
    // keying tongue, foot's underside: runs the full foot length (X),
    // centred on the rail's channel (Y = foot_width/2), dropping ridge_h
    // below the foot's mating face (Z=0). Tapered per ridge_draft, same
    // trapezoidal-keel construction as l_bracket_4020.scad's ridge_along_*.
    wt = ridge_w - 2 * ridge_draft;
    hull() {
        translate([-pw / 2, foot_width / 2 - ridge_w / 2, -eps])
            cube([pw, ridge_w, eps]);
        translate([-pw / 2, foot_width / 2 - wt / 2, -ridge_h])
            cube([pw, wt, eps]);
    }
}

module relief_cove(xc, run) {
    // 2D (a=X run position, b=Z depth): quarter-ellipse blending the relief
    // floor at xc out to full ridge depth, tangent to the floor at X=xc.
    // run > 0 puts material toward +X, run < 0 toward -X.
    difference() {
        translate([min(xc, xc - run), -ridge_h]) square([abs(run), ridge_h]);
        translate([xc, -ridge_h]) scale([abs(run), ridge_h]) circle(1);
    }
}

module ridge_relief_at(xc) {
    // subtract solid: clears the ridge between x0..x1, then curves back out
    // to full depth -- ported from l_bracket_4020.scad's ridge20_relief(),
    // with the run axis swapped from Z to X and re-centred on Y=foot_width/2
    // instead of Y=0.
    x0 = xc - ridge_relief / 2;
    x1 = xc + ridge_relief / 2;
    r  = ridge_relief_r;
    wy = ridge_w + 2; // overshoot the ridge width on both sides
    translate([0, foot_width / 2 + wy / 2, 0]) rotate([90, 0, 0]) linear_extrude(wy)
        difference() {
            translate([x0 - r, -ridge_h - eps]) square([ridge_relief + 2 * r, ridge_h + eps]);
            if (r > 0) {
                relief_cove(x0,  r);
                relief_cove(x1, -r);
            }
        }
}

module revision_stamp() {
    // engraved into the foot's top face, reading along +X
    translate([0, foot_width / 2, foot_thk - rev_depth])
        linear_extrude(rev_depth + eps)
            text(revision, size = rev_size, halign = "center", valign = "center");
}

module tag_mount_body() {
    difference() {
        union() {
            linear_extrude(foot_thk) foot_profile();
            translate([0, 0, -tag_plate_thk])
                linear_extrude(tag_plate_thk) tag_plate_profile();
            ridge_along_x();
            if (tr > 0) transition_chamfer();
        }

        // M4 through the foot and ridge, chamfer on the top (bolt head) face
        for (bx = bolt_x)
            translate([bx, foot_width / 2, foot_thk]) mirror([0, 0, 1])
                chamfered_hole(bolt_dia, foot_thk + ridge_h + 1, hole_cham);

        // relief: clear the ridge either side of each bolt
        for (bx = bolt_x) ridge_relief_at(bx);

        if (revision != "") revision_stamp();
    }
}

module tag_mount_graphic(id = tag_id) {
    // dark tag layer, centred in the tag plate, Z from -tag_embed to
    // tag_raise_h. Uncolored: the caller applies color(), which is what
    // keeps it a separate 3MF object under lazy union -- a module that
    // colors its own children internally collapses into one object when
    // called plain (confirmed empirically 2026-09-28).
    translate([0, -pd / 2, -tag_embed])
        april_tag_pattern(id = id, edge = tag_size, thickness = 0,
                          raise_h = tag_raise_h + tag_embed);
}

module tag_mount_bolted() {
    // assembly view: body + graphic + this mount's own two M4 bolts, feet
    // seated lip_depth_20+foot_thk_ref_20 under the channel, heads landing
    // flush on the foot's top face (shaft_length = foot_thk + that depth).
    // Preview only: called plain from the root, this whole module becomes
    // one 3MF object. Export the default assembly view instead.
    color(body_color)        tag_mount_body();
    color(tag_pattern_color) tag_mount_graphic();

    for (bx = bolt_x)
        color(bolt_color)
            translate([bx, foot_width / 2, -(lip_depth_20 + foot_thk_ref_20)])
                t_slot_bolt(screw_size = "M4", profile = 20,
                            shaft_length = foot_thk + lip_depth_20 + foot_thk_ref_20);
}

module plate(n) {
    // grid is centred on the origin; index 0 is the -X/-Y corner
    x0 = -(grid_cols * pitch_x - plate_gap) / 2 + part_dx / 2;
    y0 = -(grid_rows * pitch_y - plate_gap) / 2 + part_dy / 2 - pd;
    for (i = [0 : n - 1])
        translate([x0 + (i % grid_cols)     * pitch_x,
                   y0 + floor(i / grid_cols) * pitch_y,
                   0])
            tag_mount_body();
}

// ---------------------------------------------------------------------------

if (part == "body") {
    if (copies > 1) color(body_color) plate(copies);
    else color(body_color) tag_mount_body();
} else if (part == "graphic") {
    color(tag_pattern_color) tag_mount_graphic();
} else if (part == "bolted") {
    tag_mount_bolted();
} else {
    // default/"assembly": two direct top-level colored statements, so a
    // lazy-union 3MF export keeps them as two objects
    color(body_color)        tag_mount_body();
    color(tag_pattern_color) tag_mount_graphic();
}
