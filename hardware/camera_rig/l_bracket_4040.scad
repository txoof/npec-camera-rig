/* ---------------------------------------------------------------------------
   90-degree L bracket: 40x40 extrusion  <->  40x40 extrusion

   Leg A lies flat on one 40x40 profile face (mating face = Z0, pointing
   down).  Leg B stands vertically against the other 40x40 profile face
   (mating face = X0, pointing -X).  Both legs are the same width (40 mm) so
   the bracket is symmetric across the fold.

   Unlike `l_bracket_4020.scad`, this bracket has no T-slot keying ridges —
   just flat mating faces and a through-hole per leg for an M6 bolt into a
   T-nut in the extrusion channel.

   Set `copies` under [Build Plate] to lay out that many brackets in a grid,
   centred on the origin.  copies = 1 renders the single part at the origin.

   The part name and [Revision] stamp are engraved into leg A's top face,
   one each side of the M6 hole (name +Y, revision -Y), both reading along
   +X and centred on the flat run past the fillet; that face points up in
   the print orientation.

   `bracket_4040_bolted()` adds this bracket's own two M6 bolts (from
   `t_slot_bolt.scad`), one per leg, sized so each head lands flush on its
   leg's outer face (shaft_length = leg thickness + lip_depth, no extra
   margin) — an assembly-view convenience, not part of the printable
   `bracket_4040()` part. Named `bracket_4040()` rather than plain
   `bracket()` so it can live in the same file/namespace as
   `l_bracket_4020.scad`'s own bracket module without colliding.

   REV 1.4: part name (`part_name`, the file name without .scad) engraved
     into leg A's top face, +Y of the M6 hole ([Label] group).  Revision
     stamp moved to the matching -Y side, reading along +X like the name;
     `rev_x` replaced by the derived `label_x`/`label_y`.
   REV 1.3: bracket()/bracket_bolted() renamed to bracket_4040()/
     bracket_4040_bolted() so this file can be `use`d alongside
     l_bracket_4020.scad (which has its own same-named modules) from one
     assembly file; bolt color now the shared `bolt_color` variable.
   REV 1.2: added bracket_bolted() — the two joining M6 bolts now live here
     instead of being re-derived (with duplicated leg/lip constants) in
     every assembly file that places this bracket.
   REV 1.1: hole position corrected to the real-hardware convention — 20mm
     in from each leg's outside (free) edge — via `hole_edge_dist`, instead
     of an arbitrary offset from the corner.
   REV 1.0: initial.
   --------------------------------------------------------------------------- */

use <../libraries/t_slot_bolt.scad>
include <../libraries/BOSL2/std.scad> // t_slot_bolt() calls BOSL2's screw(); `use` alone
                          // wouldn't run t_slot_bolt.scad's own top-level
                          // include, so its special variables never init

/* [Revision] */
revision  = "RV1.2"; // revision stamp, engraved in leg A's top face ("" = none)
rev_size  = 5;        // text cap height, mm  [2:0.5:12]
rev_depth = 1.2;      // how far the text is inset below the surface, mm  [0.4:0.1:2]

/* [Label] */
part_name  = "l_bracket_4040"; // file name without .scad, engraved in leg A's top face, +Y of the M6 hole ("" = none)
name_size  = 2.5; // text cap height, mm -- the name must fit between the fillet edge and the free end  [2:0.5:6]
name_depth = 0.6; // how far the text is inset below the surface, mm  [0.4:0.1:1.5]

/* [Plates] */
w_a    = 40;   // leg A width  (matches 40x40 face)
len_a  = 40;   // leg A length, measured from the corner (X=0)
thk_a  = 8;    // leg A plate thickness

w_b    = 40;   // leg B width  (matches 40x40 face)
len_b  = 40;   // leg B length, measured from the corner (Z=0)
thk_b  = 8;    // leg B plate thickness

fillet_r = 3;  // inside-corner fillet radius
corner_r = 5;  // rounding on the free-end corners of both legs

/* [Fasteners] */
m6_dia         = 6.6;  // M6 clearance (normal fit)
hole_edge_dist = 20;   // hole centre, from each leg's outside (free) edge, mm
hole_cham      = 1.0;  // 45-deg relief at the entry face, 0 to disable

lip_depth    = 3;    // 40x40 T-slot lip depth, from the face to the underside of the
                      // overhanging lip (see t_slot_40x40.scad's profile) — this is
                      // where a bolt's foot/T-nut sits snug
foot_thk_ref = 2.6;  // must match t_slot_bolt.scad's foot_thk_40
bolt_color   = "DarkSlateGray"; // color for all bolt standins

/* [Build Plate] */
copies       = 1;   // how many brackets to lay out  [1:200]
plate_gap    = 5;   // clear space between neighbours, mm
plate_cols   = 0;   // columns across X; 0 = auto (near-square grid)

/* [Render] */
$fn = $preview ? 32 : 96;
eps = 0.01;

/* [Hidden] */
// bracket footprint: X runs 0 .. len_a (leg B's thickness fits within that
// span), Y is centred on the leg width
part_dx   = len_a;
part_dy   = w_a;
grid_cols = plate_cols > 0 ? plate_cols : ceil(sqrt(copies));
grid_rows = ceil(copies / grid_cols);
pitch_x   = part_dx + plate_gap;
pitch_y   = part_dy + plate_gap;

// hole centres, derived from hole_edge_dist so they stay correct if len_a/
// len_b are ever tuned away from the 40mm default
m6_ax = len_a - hole_edge_dist;
m6_bz = len_b - hole_edge_dist;

// name and revision centres on leg A's top face: X midway between the
// fillet edge and the free end (the corner rounding only reaches the text's
// Y band in the last ~0.3 mm), Y midway between the M6 hole's chamfer edge
// and the leg's side edge (+Y name, -Y revision)
label_x = (thk_b + fillet_r + len_a) / 2;
label_y = (m6_dia / 2 + hole_cham + w_a / 2) / 2;

// ---------------------------------------------------------------------------

module leg_a_profile() {
    // plan view (XY): square at the corner end, rounded at the free end
    hull() {
        translate([0, -w_a / 2]) square([eps, w_a]);
        translate([len_a - corner_r,  w_a / 2 - corner_r]) circle(corner_r);
        translate([len_a - corner_r, -w_a / 2 + corner_r]) circle(corner_r);
    }
}

module leg_b_profile() {
    // face view (YZ): square at the corner end, rounded at the free end
    hull() {
        translate([-w_b / 2, 0]) square([w_b, eps]);
        translate([-w_b / 2 + corner_r, len_b - corner_r]) circle(corner_r);
        translate([ w_b / 2 - corner_r, len_b - corner_r]) circle(corner_r);
    }
}

module inner_fillet() {
    // square-minus-cylinder cross-section in XZ, extruded across leg B
    translate([0, w_b / 2, 0]) rotate([90, 0, 0]) linear_extrude(w_b)
        difference() {
            translate([thk_b, thk_a]) square(fillet_r);
            translate([thk_b + fillet_r, thk_a + fillet_r]) circle(fillet_r);
        }
}

module chamfered_hole(dia, len, cham) {
    // bore along +Z starting at Z=0, with a cone relief at the Z=0 entry
    cylinder(d = dia, h = len);
    if (cham > 0)
        translate([0, 0, -eps])
            cylinder(d1 = dia + 2 * cham, d2 = dia, h = cham + eps);
}

module revision_stamp() {
    // engraved into leg A's top face, -Y of the M6 hole, reading along +X
    // opposite the part name; overshoots the face by eps for a clean difference
    translate([label_x, -label_y, thk_a - rev_depth])
        linear_extrude(rev_depth + eps)
            text(revision, size = rev_size,
                 halign = "center", valign = "center");
}

module name_label() {
    // engraved into leg A's top face, +Y of the M6 hole, reading along +X
    translate([label_x, label_y, thk_a - name_depth])
        linear_extrude(name_depth + eps)
            text(part_name, size = name_size, halign = "center", valign = "center");
}

module bracket_4040() {
    difference() {
        union() {
            // leg A
            linear_extrude(thk_a) leg_a_profile();
            // leg B  (local x -> Y, local y -> Z, extrude -> +X)
            rotate([90, 0, 90]) linear_extrude(thk_b) leg_b_profile();
            inner_fillet();
        }

        // M6 through leg A, chamfer on the top (bolt head) face
        translate([m6_ax, 0, thk_a]) mirror([0, 0, 1])
            chamfered_hole(m6_dia, thk_a + 1, hole_cham);

        // M6 through leg B, chamfer on the outer face
        translate([thk_b, 0, m6_bz]) rotate([0, -90, 0])
            chamfered_hole(m6_dia, thk_b + 1, hole_cham);

        // revision stamp
        if (revision != "") revision_stamp();
        if (part_name != "") name_label();
    }
}

module bracket_4040_bolted() {
    // assembly view: bracket_4040() plus its own two M6 bolts, one per leg,
    // feet seated lip_depth+foot_thk_ref under each mating face's T-slot
    // lip, heads landing flush (shaft_length = leg thickness + lip_depth).
    bracket_4040();

    color(bolt_color)
        translate([m6_ax, 0, -(lip_depth + foot_thk_ref)])
            t_slot_bolt(shaft_length = thk_a + lip_depth);

    color(bolt_color)
        translate([-(lip_depth + foot_thk_ref), 0, m6_bz])
            rotate([90, 0, 90])
                t_slot_bolt(shaft_length = thk_b + lip_depth);
}

module plate(n) {
    // grid is centred on the origin; index 0 is the -X/-Y corner
    x0 = -(grid_cols * pitch_x - plate_gap) / 2;
    y0 = -(grid_rows * pitch_y - plate_gap) / 2 + part_dy / 2;
    for (i = [0 : n - 1])
        translate([x0 + (i % grid_cols)     * pitch_x,
                   y0 + floor(i / grid_cols) * pitch_y,
                   0])
            bracket_4040();
}

if (copies > 1) plate(copies); else bracket_4040();
