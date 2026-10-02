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
     - `tag_mount_graphic(id)` -- the dark 36h11 layer for one id, via
       `apriltag_36h11.scad`'s `april_tag_pattern()`, standing `tag_raise_h`
       proud of the plate and sunk `tag_embed` into it so the two parts
       overlap rather than merely touch. One color (`tag_pattern_color`).
   `apriltag_36h11.scad`'s `april_tag_base()` is not used here: the body
   already supplies the background.

   Export with `scad_to_3mf.py` so Orca loads both as parts of one object
   with a filament each; see that script.

   The bit data and the row/col-to-XY placement are `apriltag_36h11.scad`'s
   responsibility, verified there (point-containment check against
   apriltag_gen.tags.tag_bits(), see that file's header) against the
   project's governing principle -- a silently wrong pattern fails
   "undetectable", not "loud". This file only positions that already-verified
   graphic within the frame; it does not re-derive or re-check the pattern.

   Coordinate convention: X runs along the rail's length, parallel to the
   T-slot channel; the single M4 bolt sits at X=0. Y runs away from
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

   Fastening: one M4 bolt, centred on the foot, into a type-6
   (spring-loaded ball) T-nut dropped into the rail's channel -- the same
   channel `t_slot_bolt.scad` models with `profile=20`. The keying ridge in
   the channel stops the mount rotating about that single bolt. This file
   doesn't model the T-nut itself; see `tag_mount_bolted()` for an
   assembly-view standin.

   Alignment lip: a keying ridge under the foot, sized to the 20x20
   profile's slot mouth (6.1 mm, per `t_slot_20x20.scad`'s header) -- the
   same figure `l_bracket_4020.scad`'s `ridge20_w` reuses for its own 20-leg
   ridge. Runs along X (the channel direction), with a relief cut at the
   bolt so the ridge doesn't block the T-nut/bolt shaft -- same construction
   as that file's `ridge20_relief()`/`ridge20_cove()`, ported to a ridge that
   runs along X instead of Z.

   ID label: each mount's id engraved `id_depth` into the foot's top face
   (cut from `tag_mount_body(id)`, so no extra filament), on the -X side of
   the bolt -- mirroring the engraved revision stamp on the +X side. Off the
   tag plate entirely, so the quiet zone is untouched.

   Open assumption, not yet measured: `tag_border` (quiet-zone margin) is an
   informed starting point -- general AprilTag detection guidance, not a
   calliper reading or a live detector result. Revisit once a printed mount
   and a real detection pass exist, same as any other unmeasured number in
   this project. `tag_embed` is likewise a starting value for part overlap
   in the slicer, not a measured one.

   REV 1.11: `tag_ids` limited to 450-499, the corner/reference range
     (Aaron), so corner ids can't overlap tray ids (1-399, see
     apriltag_tray_tag.scad). Geometry unchanged.
   REV 1.10: the quiet zone now clears the transition chamfer. The chamfer
     rises off the plate's top face over Y in [-tr,0], so with the tag at
     Y=-tag_border the flat margin on the foot side was tag_border - tr (and
     negative when tr > tag_border: the chamfer overlapped the tag). The
     tag plate is now `tr` deeper (pd = tag_size + 2*tag_border + tr) and the
     tag sits `tr` further out, so every side has `tag_border` of flat
     surface. Aaron's tuning in the same revision: `tag_border` 10 -> 6.3,
     `bolt_dia` 4.5 -> 5.5, `ridge_w` 6.0 -> 5.1, `ridge_relief` 14 -> 22.
     Added `ridge_clearance` (0.15 mm per side): `ridge_w` is now the
     measured slot mouth (5.10 mm) and the ridge root is ridge_w -
     2*ridge_clearance = 4.8 mm, tip 4.0 mm. Previously the root equalled
     the mouth, zero clearance.
   REV 1.9: Aaron's tuning (2026-09-29): `tag_plate_thk` 3 -> 4 mm and
     `ridge_relief` 8 -> 14 mm (wider clearance in the ridge at the bolt).
   REV 1.8: ID label engraved (recessed) instead of embossed, matching the
     revision stamp; `id_height` replaced by `id_depth`.
   REV 1.7: ID label moved from the plate's far edge to the foot's top
     face, opposite the revision stamp, embossed in the body color rather
     than printed in the tag color. Removed `id_band` (the plate is back to
     70 x 70 mm, the mount footprint to 70 x 90 mm); added `id_height`.
     `tag_mount_body()` now takes the id; `tag_mount_graphic()` is the tag
     pattern only.
   REV 1.6: batch layout. `tag_ids` (a list) replaces `tag_id` and
     `copies`: one mount per id, laid out in list order, left to right then
     top to bottom, `plate_gap` apart (default leaves room for the supports
     under the foot). Columns default to the count whose block fits the
     smallest enclosing square, allowing for the mount's 70 x 98 mm
     footprint (4 ids -> 2 x 2, 6 -> 3 x 2). The
     layout loop sits directly in the render block rather than in
     `plate()`: a top-level for() keeps every colored statement a separate
     lazy-union 3MF object (checked 2026-09-29, 3 iterations x 2 statements
     exported as 6 objects), while a module wrapper would merge them.
     `plate()` is removed.
   REV 1.5: one centred M4 bolt instead of two (removed `bolt_spacing`);
     revision stamp moved off-centre to clear it (`rev_x`, derived). Added
     the tag-color ID label on a new `id_band` strip beyond the quiet zone
     (`id_label`, `id_band`, `id_size`, `id_font`), which lengthens the tag
     plate by `id_band`.
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
tag_ids       = [450, 451, 452, 453]; // 36h11 ids, one mount each, laid out in this order -- corner/reference tags, 450-499 (PLAN.md)
tag_size      = 50;    // 36h11 tag width, mm -- corner/reference tags (PLAN.md, IDs 450-499)
tag_border    = 6.3;   // quiet-zone margin each side, flat surface only (measured from the chamfer's foot on the rail side), mm -- informed default, not yet measured [4:1:25]
tag_plate_thk = 4;     // total tag-plate thickness, mm  [2:0.5:6]
tag_raise_h   = 0.6;   // dark tag layer height above the plate's top face, mm  [0.2:0.1:2]
tag_embed     = 0.2;   // how far the dark layer sinks into the plate so the parts overlap, mm  [0:0.05:1]

/* [ID Label] */
id_label  = true;                      // engrave each mount's id on the foot, opposite the revision stamp
id_size   = 5;                         // label text cap height, mm  [2:0.5:10]
id_depth  = 1.0;                       // how far the label is inset below the foot's top face, mm  [0.4:0.1:2]
id_font   = "Liberation Sans:style=Bold";

/* [Rail Foot] */
foot_width   = 20;    // Y depth -- matches the 20x20 rail's face width, mm
foot_thk     = 7;     // Z thickness, mm
corner_r     = 3;     // rounding on the two free (outer) corners of the foot and tag plate, mm

/* [Fasteners] */
bolt_dia     = 5.5;   // M4 clearance hole, centred on the foot, mm
hole_cham    = 1.0;   // 45-deg relief at the bolt entry face, mm (0 = none)
bolt_color   = "DarkSlateGray"; // color for the assembly-view bolt standins

lip_depth_20    = 1.8; // 20x20 T-slot lip depth -- must match t_slot_20x20.scad's header figure
foot_thk_ref_20 = 1.5; // must match t_slot_bolt.scad's foot_thk_20

/* [Ridge] */
ridge_w        = 5.1;  // slot-mouth width, mm -- measured 5.10 on the rail; the ridge itself is ridge_w - 2*ridge_clearance
ridge_clearance = 0.15; // gap per side between the ridge root and the slot mouth, mm -- starting value, not yet test-printed  [0:0.05:0.5]
ridge_h        = 3;    // drop depth into the channel, mm
ridge_draft    = 0.4;  // per-side taper at the tip, mm
ridge_relief   = 22;    // relief width at the bolt, along X, mm
ridge_relief_r = 1.5;  // transition curve at each relief end, mm (0 = square step)

/* [Transition] */
transition_r = 7;  // chamfer radius at the foot/tag-plate step, mm -- should match foot_thk
                    // (the full step height) so the chamfer sweeps the whole step with no
                    // leftover vertical wall above it; 0 = sharp corner [0:0.5:10]

/* [Colors] */
body_color        = "White";     // also the tag's background and quiet zone
tag_pattern_color = "Black"; // the tag's dark modules

/* [Render Select] */
part = "assembly"; // what to render  ["assembly","body","graphic","bolted"]

/* [Build Plate] */
plate_gap  = 10;  // clear space between neighbouring mounts, mm -- leave room for supports under the foot  [0:1:50]
plate_cols = 0;   // mounts per row; 0 = auto (block closest to square)  [0:1:20]

/* [Revision] */
revision  = "RV1.11"; // revision stamp, engraved in the foot's top face beside the bolt ("" = none)
rev_size  = 4;        // text cap height, mm  [2:0.5:8]
rev_depth = 1.0;      // how far the text is inset below the surface, mm  [0.4:0.1:2]

/* [Render] */
$fn = $preview ? 32 : 96;
eps = 0.01;

/* [Hidden] */
// plate footprint: X shared by foot and tag plate, Y split at the Y=0 joint
// (foot spans [0,foot_width], tag plate spans [-pd,0])
rw = ridge_w - 2 * ridge_clearance; // ridge width at its root (Z=0, level with the slot mouth)
tr = min(transition_r, foot_thk); // clamp: a chamfer taller than the foot has nothing to blend into
// the chamfer covers Y in [-tr,0] of the plate's top face, so the flat face
// (and the quiet zone measured on it) only starts at Y=-tr
pw = tag_size + 2 * tag_border;         // plate width, X
pd = tag_size + 2 * tag_border + tr;    // tag plate depth, Y
tag_cy = -(tr + tag_border + tag_size / 2); // tag centre, Y
bolt_x = [0];
// revision stamp centre (+X) and ID label centre (-X): midway between the
// bolt's chamfer edge and the foot's end
rev_x = (pw / 2 + bolt_dia / 2 + hole_cham) / 2;

assert(len(tag_ids) > 0, "tag_ids must list at least one id");
assert(min(tag_ids) >= 450 && max(tag_ids) <= 499,
       "tag_ids must be within 450-499, the corner/reference range (PLAN.md)");

n_mounts  = len(tag_ids);
part_dx   = pw;
part_dy   = foot_width + pd;
pitch_x   = part_dx + plate_gap;
pitch_y   = part_dy + plate_gap;
// auto columns: the count whose block fits the smallest enclosing square,
// accounting for the non-square footprint (fewest columns wins a tie)
block_side = [for (c = [1 : n_mounts]) max(c * pitch_x, ceil(n_mounts / c) * pitch_y)];
grid_cols = plate_cols > 0 ? min(plate_cols, n_mounts)
                           : search(min(block_side), block_side)[0] + 1;
grid_rows = ceil(n_mounts / grid_cols);

// centre of mount i's footprint lands on the block's grid cell, block centred
// on the origin; row 0 at +Y so the list reads left to right, top to bottom
function slot(i) = [
    ((i % grid_cols) - (grid_cols - 1) / 2) * pitch_x,
    ((grid_rows - 1) / 2 - floor(i / grid_cols)) * pitch_y - (foot_width - pd) / 2,
    0
];

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
    wt = rw - 2 * ridge_draft;
    hull() {
        translate([-pw / 2, foot_width / 2 - rw / 2, -eps])
            cube([pw, rw, eps]);
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
    // engraved into the foot's top face, reading along +X, off to the +X
    // side of the centred bolt
    translate([rev_x, foot_width / 2, foot_thk - rev_depth])
        linear_extrude(rev_depth + eps)
            text(revision, size = rev_size, halign = "center", valign = "center");
}

module id_engrave(id) {
    // engraved into the foot's top face, reading along +X, on the -X side of
    // the bolt opposite the revision stamp
    translate([-rev_x, foot_width / 2, foot_thk - id_depth])
        linear_extrude(id_depth + eps)
            text(str(id), size = id_size, font = id_font, halign = "center", valign = "center");
}

module tag_mount_body(id = tag_ids[0]) {
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

        // relief: clear the ridge either side of the bolt
        for (bx = bolt_x) ridge_relief_at(bx);

        if (revision != "") revision_stamp();
        if (id_label) id_engrave(id);
    }
}

module tag_mount_graphic(id = tag_ids[0]) {
    // dark tag layer, Z from -tag_embed to tag_raise_h. Uncolored: the
    // caller applies color(), which is what keeps it a separate 3MF object
    // under lazy union -- a module that colors its own children internally
    // collapses into one object when called plain (confirmed empirically
    // 2026-09-28).
    translate([0, tag_cy, -tag_embed])
        april_tag_pattern(id = id, edge = tag_size, thickness = 0,
                          raise_h = tag_raise_h + tag_embed);
}

module tag_mount_bolted() {
    // assembly view: body + graphic + this mount's M4 bolt, foot
    // seated lip_depth_20+foot_thk_ref_20 under the channel, heads landing
    // flush on the foot's top face (shaft_length = foot_thk + that depth).
    // Preview only, first id in tag_ids: called plain from the root, this
    // whole module becomes one 3MF object. Export the assembly view instead.
    color(body_color)        tag_mount_body();
    color(tag_pattern_color) tag_mount_graphic();

    for (bx = bolt_x)
        color(bolt_color)
            translate([bx, foot_width / 2, -(lip_depth_20 + foot_thk_ref_20)])
                t_slot_bolt(screw_size = "M4", profile = 20,
                            shaft_length = foot_thk + lip_depth_20 + foot_thk_ref_20);
}

// ---------------------------------------------------------------------------

// Layout loops stay here at the top level, not in a module: every colored
// statement inside a top-level for() is its own lazy-union 3MF object, which
// scad_to_3mf.py then pairs back up into one Orca object per mount.
if (part == "bolted") {
    tag_mount_bolted();
} else {
    for (i = [0 : n_mounts - 1]) {
        if (part != "graphic")
            translate(slot(i)) color(body_color) tag_mount_body(tag_ids[i]);
        if (part != "body")
            translate(slot(i)) color(tag_pattern_color) tag_mount_graphic(tag_ids[i]);
    }
}
