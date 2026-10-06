/* ---------------------------------------------------------------------------
   Auto-focus bracket and tag: two parts printed together, one file, one
   revision.
     - `af_bracket_2020()`: 90-degree bracket, 20x20 rail  <->  20x20 rail.
     - `af_tag_body()` / `af_tag_graphic()`: a 50 mm 36h11 AprilTag plate
       with a leg that bolts to a vertical 20x20 rail.

   Built from `l_bracket_4020.scad`'s 20-leg: both legs are plates keyed to
   a 20x20 T-slot rail, two bolts each.  The ridge, bolt relief and
   clearance values are `apriltag_corner_mount.scad`'s (measured 5.10 mm
   slot mouth, 0.15 mm clearance per side).

   Coordinate convention:
     - Flat leg lies in the XY plane on the rail's top face, X in [0,len_h],
       Y centred on its width (`leg_w`).  Mating face = Z0, pointing down.
       Its ridge runs along X, the rail's axis, so that rail runs along X
       under the bracket.
     - Upright leg stands on the flat leg's -Y long edge, in the XZ plane,
       at the flat leg's X=0 end by default (`upright_offset`, measured
       from the flat leg's centre), `upright_w` wide along X, Z in
       [0,len_v].  The flat leg's X=0 end is rounded only when the upright
       is not flush with it.  Mating face = Y = -leg_w/2,
       pointing -Y.  Its ridge runs along Z, the second rail's axis.
   Both legs are built by one `leg_solid()` / `leg_cuts()` pair in the flat
   leg's frame; the upright's `upright_frame()` rotates that frame so
   local X (run) -> Z, local Y (width) -> X, local Z (thickness) -> Y.

   Each ridge has a relief cut centred on every bolt so the ridge does not
   block the T-nuts, same construction as `l_bracket_4020.scad`'s
   `ridge20_relief()`.

   Bolt size: `bolt_size` picks the clearance hole (ISO 273 normal fit) and
   the bolt stand-in in `af_bracket_2020_bolted()`.  `bolt_dia` > 0
   overrides the table.  Bolt positions are lists, one entry per bolt.

   The [Revision] stamp is engraved into the flat leg's top face beside the
   upright, between the fillet and the +Y edge.  The part name
   (`part_name`, the file name without .scad) is engraved into the flat
   leg's +Y long side face, the one face with room for it.

   Tag: same rules as `apriltag_corner_mount.scad`.  50 mm tag, 6.3 mm
   quiet zone of flat white plate on every side, 4 mm plate, dark layer
   standing `tag_raise_h` proud and sunk `tag_embed` into the plate.  Two
   colors, no assembly; export with `scad_to_3mf.py`.  The plate is only
   the tag and its quiet zone, centred on X = Y = 0 in its own frame, top
   face at Z = 0.
     - Leg: at the Quadrant IV (+X, -Y) corner, hanging below the plate
       from its top face to Z = -tag_leg_len.  Same form as the bracket's
       upright (`upright_w` wide along X, `thk_v` thick, same ridge,
       relief, fillet and corner rounding), one bolt.  Mating face is the
       plate's -Y edge, pointing -Y, away from the tag; ridge along Z.
       That plate corner is left square where the leg meets it.
     - ID label: the tag id, small, engraved into the top face in the
       quiet zone's top-left corner (-X, +Y, viewed from above), `id_inset`
       in from both plate edges.  Same pattern and values as
       `apriltag_tray_tag.scad`'s `id_engrave()`, inside the quiet zone by
       the same choice (Aaron, tray tag REV 1.2).  Diagonally opposite the
       leg.
     - Part name and revision are engraved into the plate's underside,
       mirrored so they read from below, clear of the tag face.  Printed
       face down, the tag lies flat on the bed and the leg stands up with
       no supports.
   Tag id 500 is outside every range PLAN.md reserves (trays 1-299,
   calibration sheets 300-449, corner mounts 450-499).  Its bit data comes
   from `libraries/apriltags-36h11-0-586.scad`, the full 36h11 family.

   Print orientation: `on_side = true` stands both parts on an edge, like
   apriltag_tray_tag.scad's `on_side` (Aaron, REV 0.7):
     - Tag: turned 90 deg about Y, so it stands on its +X edge (the plate's
       +X edge and the leg's +X side), tag face toward +X.  Plan: the plate
       is a 4.6 mm wall along Y, the leg runs off it toward -X.
     - Bracket: from the flat layout, turned 90 deg about X (upright's
       mating face down), then 90 deg clockwise about Y viewed from +Y, so
       it stands on its X=0 end: flat leg vertical, upright lying on its
       X=0 side edge.  Plan: a leg_w x (thk_h + ridge_h) block with the
       upright running off it toward -Y.
   Ridges then run parallel to the bed and print as side overhangs.  The
   tag stands left of the bracket, `tag_gap` clear, centred on it in Y.
   The convention above describes the unrotated parts, which is what every
   module builds; only the final placement is rotated.

   [Build Plate] `copies` lays out that many bracket + tag sets in a grid,
   centred on the origin.  `part` picks what renders.  The layout loop sits
   at the top level, not in a module, so every colored statement is its own
   lazy-union 3MF object (see apriltag_corner_mount.scad REV 1.6).

   REV 0.5: upright moved to the flat leg's X=0 end (`upright_offset`
     0 -> -30, flush with that end, which is square again while the upright
     sits there).  Flat leg bolts [15, 65] -> [32, 62], both on the +X
     side of the upright.
   REV 0.4: added the AprilTag plate with its Quadrant IV leg, printed with
     the bracket.  `part` selector.  `copies` now lays out sets; `plate()`
     replaced by the top-level loop and `slot()`.  Tag id engraved in the
     quiet zone's top-left corner ([ID Label] group, from the tray tags).
   REV 0.7: print orientation changed (Aaron): tag turned 90 deg clockwise
     about X viewed from +X, bracket 90 deg clockwise about Y viewed from
     +Y, so both stand on an edge.  Tag now beside the bracket, no longer
     tucked into its corner.  Geometry unchanged.
   REV 0.6: print orientation (Aaron): `on_side`, both vertical arms flat on
     the bed, tag nested in the bracket's open corner (`orient_bracket()`,
     `place_tag()`).  `tag_gap` 10 -> 5.  Geometry unchanged.

   REV 0.3: upright leg centred on the flat leg's length (`upright_offset`
     shifts it); its fillet, holes and bolts move with it.  Flat leg bolts
     now either side of the upright, [32, 62] -> [15, 65].  Revision stamp
     moved beside the upright.  Flat leg's X=0 end rounded too, now that
     both its ends are free.  Part name engraved on the flat leg's +Y
     side face ([Label] group).

   REV 0.2: upright leg moved from the X=0 end to the flat leg's -Y long
     edge (XZ plane, ridge facing -Y).  Two bolts per leg (`holes_h`,
     `holes_v` replace `hole_x`, `hole_z`).  Flat leg 45 -> 80 mm, upright
     38 -> 75 mm.  Added `upright_w`.  Revision stamp moved between the
     flat leg's bolts.
   REV 0.1: initial.
   --------------------------------------------------------------------------- */

use <../libraries/t_slot_bolt.scad>
use <../libraries/apriltag_36h11.scad>
include <../libraries/BOSL2/std.scad> // t_slot_bolt() calls BOSL2's screw(); `use` alone
                          // wouldn't run t_slot_bolt.scad's own top-level
                          // include, so its special variables never init

/* [Revision] */
revision  = "RV0.7"; // revision stamp, engraved in the flat leg top face and the tag underside ("" = none)
rev_size  = 4;       // text cap height, mm  [2:0.5:8]
rev_depth = 1.0;     // how far the text is inset below the surface, mm  [0.4:0.1:2]

/* [Label] */
part_name  = "auto-focus_bracket_2020"; // file name without .scad, engraved on the flat leg's +Y side face and the tag underside ("" = none)
name_size  = 3.5; // text cap height, mm -- must fit thk_h  [2:0.5:6]
name_depth = 0.6; // how far the text is inset below the surface, mm  [0.4:0.1:1.5]

/* [Plates] */
leg_w     = 20;   // flat leg width, Y (matches the 20x20 face), mm  [10:0.5:30]
len_h     = 80;   // flat leg length along X, mm  [20:1:150]
thk_h     = 7;    // flat leg thickness, mm  [3:0.5:12]
upright_w = 20;   // upright leg width along X (matches the 20x20 face), mm  [10:0.5:30]
upright_offset = -30; // upright centre, from the flat leg's centre along X, mm (0 = centred, -(len_h - upright_w)/2 = flush with the X=0 end)
len_v     = 75;   // upright leg height along Z, mm  [20:1:150]
thk_v     = 7;    // upright leg thickness, Y, mm  [3:0.5:12]
fillet_r  = 3;    // inside-corner fillet radius, mm  [0:0.5:8]
corner_r  = 5;    // rounding on the free-end corners of both legs, mm  [0:0.5:9]

/* [Fasteners] */
bolt_size = "M5";     // bolt size, sets the clearance hole and the bolt stand-in  ["M3","M4","M5","M6"]
bolt_dia  = 0;        // clearance hole override, mm (0 = ISO 273 normal fit for bolt_size)  [0:0.1:8]
holes_h   = [32, 62]; // flat leg bolt centres, along X from X=0, mm -- keep them clear of the upright
holes_v   = [24, 54]; // upright leg bolt centres, along Z from Z=0, mm
hole_cham = 1.0;      // 45-deg relief at the bolt entry face, mm (0 = none)  [0:0.25:2]

lip_depth_20    = 1.8;  // 20x20 T-slot lip depth (see t_slot_20x20.scad's header)
foot_thk_ref_20 = 1.5;  // must match t_slot_bolt.scad's foot_thk_20
bolt_color      = "DarkSlateGray"; // color for the bolt stand-ins

/* [Ridge] */
ridge_w         = 5.1;  // slot-mouth width, mm -- measured 5.10 on the rail (see apriltag_corner_mount.scad)
ridge_clearance = 0.15; // gap per side between the ridge root and the slot mouth, mm  [0:0.05:0.5]
ridge_h         = 3;    // drop depth into the channel, mm  [1:0.5:5]
ridge_draft     = 0.4;  // per-side taper at the tip, mm  [0:0.1:1]
ridge_relief    = 22;   // relief length at each bolt, along the ridge, mm (0 = none)  [0:1:40]
ridge_relief_r  = 1.5;  // transition curve at each relief end, mm (0 = square step)

/* [Tag] */
tag_id        = 500;  // 36h11 id -- outside PLAN.md's reserved ranges; needs regenerated bit data, see header
tag_size      = 50;   // 36h11 tag width, mm
tag_border    = 6.3;  // quiet-zone margin each side, flat surface, mm -- corner mount value, not yet measured  [4:0.1:25]
tag_plate_thk = 4;    // tag plate thickness, mm  [2:0.5:6]
tag_raise_h   = 0.6;  // dark tag layer height above the plate's top face, mm  [0.2:0.1:2]
tag_embed     = 0.2;  // how far the dark layer sinks into the plate so the parts overlap, mm  [0:0.05:1]
tag_corner_r  = 3;    // rounding on the plate's three free corners, mm  [0:0.5:8]

/* [ID Label] */
id_label = true;  // engrave the tag id on the top face, in the quiet zone's top-left corner
id_size  = 2.5;   // label text cap height, mm  [1.5:0.5:6]
id_inset = 2;     // label's distance in from the plate's -X and +Y edges, mm  [0.5:0.25:5]
id_depth = 0.6;   // how far the label is inset into the top face, mm  [0.2:0.1:2]
id_font  = "Liberation Sans:style=Bold";

/* [Tag Leg] */
tag_leg_len  = 38;  // leg length below the tag's top face, mm  [20:1:100]
tag_leg_hole = 20;  // bolt centre, below the tag's top face, mm

/* [Colors] */
body_color        = "White"; // bracket, and the tag's background and quiet zone
tag_pattern_color = "Black"; // the tag's dark modules

/* [Render Select] */
part = "set"; // what to render  ["set","bracket","tag","bolted"]

/* [Build Plate] */
on_side    = true; // print orientation: stand both parts on an edge on Z = 0 (tag on its +X edge, bracket on its X=0 end), tag beside the bracket
copies     = 1;   // how many bracket + tag sets to lay out  [1:200]
tag_gap    = 5;   // clear space between the bracket and the tag, mm  [0:1:50]
plate_gap  = 5;   // clear space between neighbouring sets, mm
plate_cols = 0;   // columns across X; 0 = auto (near-square grid)

/* [Render] */
$fn = $preview ? 32 : 96;
eps = 0.01;

/* [Hidden] */
// ISO 273 normal-fit clearance holes
clearance_table = [["M3", 3.4], ["M4", 4.5], ["M5", 5.5], ["M6", 6.6]];
hole_dia = bolt_dia > 0 ? bolt_dia
         : clearance_table[search([bolt_size], clearance_table)[0]][1];
hole_r_out = hole_dia / 2 + hole_cham; // hole radius at the entry face
rw = ridge_w - 2 * ridge_clearance;    // ridge width at its root
y_mate_v = -leg_w / 2;                 // upright leg mating face, Y
ux  = len_h / 2 + upright_offset;      // upright centre, X
ux0 = ux - upright_w / 2;              // upright -X edge

// revision stamp centre: on the flat leg's top face beside the upright,
// midway between the fillet's edge and the +Y edge
rev_y = (y_mate_v + thk_v + fillet_r + leg_w / 2) / 2;

// tag plate: pw square, leg at the +X/-Y corner, mating face on the -Y edge
pw      = tag_size + 2 * tag_border;   // plate width, X and Y
tlx     = pw / 2 - upright_w / 2;      // leg centre, X
y_mate_t = -pw / 2;                    // leg mating face, Y

// On the side, plan footprints in each part's placed frame:
//   bracket, turned so X' = -y, Y' = -z, Z' = x:
//     X' [-leg_w/2, leg_w/2 + ridge_h], Y' [-len_v, ridge_h]
//   tag, turned 90 deg about Y and lifted pw/2, so X' = z, Y' = y,
//   Z' = pw/2 - x:
//     X' [-tag_leg_len, tag_raise_h], Y' [-pw/2 - ridge_h, pw/2]
br_x0 = -leg_w / 2;  br_x1 = leg_w / 2 + ridge_h;
br_y0 = -len_v;      br_y1 = ridge_h;
tg_x0 = -tag_leg_len;       tg_x1 = tag_raise_h;
tg_y0 = -pw / 2 - ridge_h;  tg_y1 = pw / 2;
// tag shift in the set: on the side, left of the bracket `tag_gap` clear,
// centred on it in Y; flat layout: beside the bracket's +Y edge
tag_pos = on_side
    ? [br_x0 - tag_gap - tg_x1, (br_y0 + br_y1) / 2 - (tg_y0 + tg_y1) / 2, 0]
    : [len_h / 2, leg_w / 2 + tag_gap + ridge_h + pw / 2, 0];

// set footprint
set_x0 = on_side ? tag_pos.x + tg_x0 : min(0, tag_pos.x - pw / 2);
set_x1 = on_side ? br_x1 : max(len_h, tag_pos.x + pw / 2);
set_y0 = on_side ? min(br_y0, tag_pos.y + tg_y0) : -leg_w / 2 - ridge_h;
set_y1 = on_side ? max(br_y1, tag_pos.y + tg_y1) : tag_pos.y + pw / 2;
set_dx = set_x1 - set_x0;
set_dy = set_y1 - set_y0;
grid_cols = plate_cols > 0 ? plate_cols : ceil(sqrt(copies));
grid_rows = ceil(copies / grid_cols);
pitch_x   = set_dx + plate_gap;
pitch_y   = set_dy + plate_gap;

// set i's footprint centred on its grid cell, the block centred on the origin
function slot(i) = [
    ((i % grid_cols) - (grid_cols - 1) / 2) * pitch_x - (set_x0 + set_dx / 2),
    (floor(i / grid_cols) - (grid_rows - 1) / 2) * pitch_y - (set_y0 + set_dy / 2),
    0
];

assert(search([bolt_size], clearance_table)[0] != [], "bolt_size must be M3, M4, M5 or M6");
assert(ux0 >= 0 && ux0 + upright_w <= len_h, "upright_offset puts the upright off the flat leg");
assert(min([for (xc = holes_h) abs(xc - ux)]) - hole_r_out > upright_w / 2,
       "a flat leg bolt sits beside the upright, its head would hit the upright or fillet");
assert(min(holes_h) - hole_r_out > 0, "a flat leg bolt runs off the X=0 end");
assert(max(holes_h) + hole_r_out < len_h, "a flat leg bolt runs off the free end");
assert(min(holes_v) - hole_r_out > thk_h + fillet_r,
       "an upright bolt sits in the flat leg or its fillet");
assert(max(holes_v) + hole_r_out < len_v, "an upright bolt runs off the free end");
assert(tag_leg_hole - hole_r_out > tag_plate_thk + fillet_r,
       "the tag leg bolt sits in the tag plate or its fillet");
assert(tag_leg_hole + hole_r_out < tag_leg_len, "the tag leg bolt runs off the free end");
assert(upright_w <= pw, "the tag leg is wider than the tag plate");
assert(id_depth < tag_plate_thk, "id engraving deeper than the tag plate");

// ---------------------------------------------------------------------------

module chamfered_hole(dia, len, cham) {
    // bore along +Z starting at Z=0, with a cone relief at the Z=0 entry
    cylinder(d = dia, h = len);
    if (cham > 0)
        translate([0, 0, -eps])
            cylinder(d1 = dia + 2 * cham, d2 = dia, h = cham + eps);
}

module leg_profile(len, w, round_start) {
    // plan view (XY), centred on Y: rounded at the free (X=len) end, and at
    // the X=0 end too when round_start is set
    hull() {
        if (round_start) {
            translate([corner_r,  w / 2 - corner_r]) circle(corner_r);
            translate([corner_r, -w / 2 + corner_r]) circle(corner_r);
        } else
            translate([0, -w / 2]) square([eps, w]);
        translate([len - corner_r,  w / 2 - corner_r]) circle(corner_r);
        translate([len - corner_r, -w / 2 + corner_r]) circle(corner_r);
    }
}

module ridge_along_x(len) {
    // keying ridge, grows downward from Z=0, runs X in [0,len], centred on Y
    wt = rw - 2 * ridge_draft;
    hull() {
        translate([0, -rw / 2, -eps])     cube([len, rw, eps]);
        translate([0, -wt / 2, -ridge_h]) cube([len, wt, eps]);
    }
}

module relief_cove(xc, run) {
    // 2D (X run, Z depth): quarter-ellipse blending the relief floor at xc out
    // to full ridge depth.  run > 0 puts material toward +X, run < 0 toward -X.
    difference() {
        translate([min(xc, xc - run), -ridge_h]) square([abs(run), ridge_h]);
        translate([xc, -ridge_h]) scale([abs(run), ridge_h]) circle(1);
    }
}

module ridge_relief_at(xc) {
    // subtract solid: clears the ridge either side of xc, then curves back out
    // to full depth.  Stops at Z=0, so the plate's mating face is untouched.
    x0 = xc - ridge_relief / 2;
    x1 = xc + ridge_relief / 2;
    r  = ridge_relief_r;
    wy = ridge_w + 2; // overshoot the ridge width on both sides
    translate([0, wy / 2, 0]) rotate([90, 0, 0]) linear_extrude(wy)
        difference() {
            translate([x0 - r, -ridge_h - eps]) square([ridge_relief + 2 * r, ridge_h + eps]);
            if (r > 0) {
                relief_cove(x0,  r);
                relief_cove(x1, -r);
            }
        }
}

module leg_solid(len, w, thk, round_start = false) {
    // flat-leg frame: plate on Z in [0,thk] plus its ridge below Z=0
    linear_extrude(thk) leg_profile(len, w, round_start);
    ridge_along_x(len);
}

module leg_cuts(holes, thk) {
    // bolt holes through the plate and ridge, chamfer on the top (head)
    // face, plus a ridge relief at each
    for (xc = holes) {
        translate([xc, 0, thk]) mirror([0, 0, 1])
            chamfered_hole(hole_dia, thk + ridge_h + 1, hole_cham);
        if (ridge_relief > 0) ridge_relief_at(xc);
    }
}

module upright_frame() {
    // flat-leg frame -> upright leg: local X (run) -> Z, local Y (width) -> X
    // (centred on ux), local Z (thickness) -> Y from the mating face
    multmatrix([[0, 1, 0, ux],
                [0, 0, 1, y_mate_v],
                [1, 0, 0, 0],
                [0, 0, 0, 1]])
        children();
}

module inner_fillet() {
    // square-minus-circle cross-section in YZ, extruded along the upright's width
    translate([ux0, 0, 0]) rotate([90, 0, 90]) linear_extrude(upright_w)
        difference() {
            translate([y_mate_v + thk_v, thk_h]) square(fillet_r);
            translate([y_mate_v + thk_v + fillet_r, thk_h + fillet_r]) circle(fillet_r);
        }
}

module revision_stamp() {
    // engraved into the flat leg's top face beside the upright, reading along +X
    translate([ux, rev_y, thk_h - rev_depth])
        linear_extrude(rev_depth + eps)
            text(revision, size = rev_size, halign = "center", valign = "center");
}

module name_label() {
    // engraved into the flat leg's +Y side face, reading left to right when
    // seen from +Y, centred on the leg's length and thickness
    translate([len_h / 2, leg_w / 2 - name_depth, thk_h / 2])
        rotate([90, 0, 180]) linear_extrude(name_depth + eps)
            text(part_name, size = name_size, halign = "center", valign = "center");
}

module af_bracket_2020() {
    difference() {
        union() {
            leg_solid(len_h, leg_w, thk_h, round_start = ux0 > 0); // flat leg; X=0 end square when the upright is flush with it
            upright_frame() leg_solid(len_v, upright_w, thk_v); // upright leg
            if (fillet_r > 0) inner_fillet();
        }
        leg_cuts(holes_h, thk_h);
        upright_frame() leg_cuts(holes_v, thk_v);
        if (revision != "") revision_stamp();
        if (part_name != "") name_label();
    }
}

module af_bracket_2020_bolted() {
    // assembly view: the bracket plus its bolts, feet seated under each
    // mating face's T-slot lip, heads landing flush on the inner faces
    af_bracket_2020();

    for (xc = holes_h)
        color(bolt_color)
            translate([xc, 0, -(lip_depth_20 + foot_thk_ref_20)])
                t_slot_bolt(screw_size = bolt_size, profile = 20,
                            shaft_length = thk_h + lip_depth_20);

    for (zc = holes_v)
        color(bolt_color)
            translate([ux, y_mate_v - (lip_depth_20 + foot_thk_ref_20), zc])
                rotate([-90, 0, 0])
                    t_slot_bolt(screw_size = bolt_size, profile = 20,
                                shaft_length = thk_v + lip_depth_20);
}

module tag_leg_frame() {
    // flat-leg frame -> tag leg: local X (run) -> -Z (down from the tag's top
    // face), local Y (width) -> -X (centred on tlx), local Z (thickness) -> Y
    // from the mating face.  A rotation, not a reflection
    multmatrix([[ 0, -1, 0, tlx],
                [ 0,  0, 1, y_mate_t],
                [-1,  0, 0, 0],
                [ 0,  0, 0, 1]])
        children();
}

module tag_plate_profile() {
    // XY plan view, centred: three rounded corners, square at the +X/-Y
    // corner where the leg meets it
    r = tag_corner_r;
    hull() {
        translate([-pw / 2 + r,  pw / 2 - r]) circle(r);
        translate([ pw / 2 - r,  pw / 2 - r]) circle(r);
        translate([-pw / 2 + r, -pw / 2 + r]) circle(r);
        translate([ pw / 2 - eps, -pw / 2]) square(eps);
    }
}

module tag_leg_fillet() {
    // square-minus-circle cross-section in YZ, between the plate's underside
    // and the leg's inner face, extruded along the leg's width
    yi = y_mate_t + thk_v;
    zb = -tag_plate_thk;
    translate([tlx - upright_w / 2, 0, 0]) rotate([90, 0, 90]) linear_extrude(upright_w)
        difference() {
            translate([yi, zb - fillet_r]) square(fillet_r);
            translate([yi + fillet_r, zb - fillet_r]) circle(fillet_r);
        }
}

module tag_underside_label() {
    // part name and revision engraved into the plate's underside, mirrored so
    // they read from below; centred on the plate, clear of the leg's fillet
    lines = [for (t = [part_name, revision]) if (t != "") t];
    pitch = name_size * 1.6;
    for (i = [0 : len(lines) - 1])
        translate([0, ((len(lines) - 1) / 2 - i) * pitch, -tag_plate_thk - eps])
            linear_extrude(name_depth + eps)
                mirror([1, 0, 0])
                    text(lines[i], size = name_size, halign = "center", valign = "center");
}

module id_engrave() {
    // engraved into the top face in the quiet zone's top-left corner viewed
    // from above, its top-left corner `id_inset` in from both plate edges
    // (apriltag_tray_tag.scad's id_engrave())
    translate([-pw / 2 + id_inset, pw / 2 - id_inset, -id_depth])
        linear_extrude(id_depth + eps)
            text(str(tag_id), size = id_size, font = id_font, halign = "left", valign = "top");
}

module af_tag_body() {
    // plate + leg, one color.  Tag frame: centred on X = Y = 0, top face Z = 0
    difference() {
        union() {
            translate([0, 0, -tag_plate_thk]) linear_extrude(tag_plate_thk) tag_plate_profile();
            tag_leg_frame() leg_solid(tag_leg_len, upright_w, thk_v);
            if (fillet_r > 0) tag_leg_fillet();
        }
        tag_leg_frame() leg_cuts([tag_leg_hole], thk_v);
        if (part_name != "" || revision != "") tag_underside_label();
        if (id_label) id_engrave();
    }
}

module af_tag_graphic() {
    // dark tag layer, Z from -tag_embed to tag_raise_h.  Uncolored: the caller
    // applies color(), which keeps it a separate 3MF object under lazy union
    // (see apriltag_corner_mount.scad's tag_mount_graphic())
    translate([0, 0, -tag_embed])
        april_tag_pattern(id = tag_id, edge = tag_size, thickness = 0,
                          raise_h = tag_raise_h + tag_embed);
}

module orient_bracket() {
    // print placement, on_side: turn 90 deg about X (upright's mating face
    // down), then 90 deg clockwise about Y viewed from +Y, so the bracket
    // stands on its X=0 end, which lands on Z = 0
    if (on_side)
        rotate([0, -90, 0]) rotate([90, 0, 0]) children();
    else
        children();
}

module place_tag() {
    // print placement in the set: on_side, turn 90 deg about Y so the tag
    // stands on its +X edge, lift that edge onto Z = 0, then move it to
    // tag_pos
    translate(tag_pos)
        if (on_side)
            translate([0, 0, pw / 2]) rotate([0, 90, 0]) children();
        else
            children();
}

// ---------------------------------------------------------------------------

// Layout loop stays at the top level, not in a module: every colored
// statement inside a top-level for() is its own lazy-union 3MF object, which
// scad_to_3mf.py then pairs back up by footprint (bracket alone, tag body +
// graphic together).
if (part == "bolted") {
    af_bracket_2020_bolted();
} else {
    for (i = [0 : copies - 1]) {
        if (part == "set" || part == "bracket")
            translate(slot(i)) color(body_color) orient_bracket() af_bracket_2020();
        if (part == "set" || part == "tag") {
            translate(slot(i)) color(body_color) place_tag() af_tag_body();
            translate(slot(i)) color(tag_pattern_color) place_tag() af_tag_graphic();
        }
    }
}
