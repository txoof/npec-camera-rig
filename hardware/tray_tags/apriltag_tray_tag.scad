/* ---------------------------------------------------------------------------
   AprilTag tray tag -- 30 mm 36h11 tag on a square plate for each growth
   tray (PLAN.md's fixed 30 mm tag on each tray). Two styles, chosen once
   for the whole layout with `tag_style`:
     - "tab": the plate sits on the tray's rim, with a tab hanging 90 deg
       over the tray's edge to locate it.
     - "bolt": a tab in the plate's own plane, `bolt_tab_len` past the
       plate's -Y edge, with a round end and an M8 clearance hole
       concentric with it. Centred on X, or with `bolt_tab_flush` flush
       with the plate's +X edge -- the face that rests on the bed when
       `on_side` is set, so the tab prints on the bed instead of hanging
       above it. All four plate corners are rounded and the
       tab-to-plate corners are filleted (`bolt_tab_fillet`).

   One continuous multi-material print, two colors, no assembly step, same
   construction as `apriltag_corner_mount.scad`:
     - `tray_tag_body(id)` -- the plate and tab. The plate's top face is
       the tag's white background and quiet zone. One color (`body_color`).
     - `tray_tag_graphic(id)` -- the dark 36h11 layer for one id, via
       `apriltag_36h11.scad`'s `april_tag_pattern()`, standing `tag_raise_h`
       proud of the plate and sunk `tag_embed` into it so the two parts
       overlap rather than merely touch. One color (`tag_pattern_color`).

   Export with `scad_to_3mf.py` so Orca loads both as parts of one object
   with a filament each; see that script.

   The bit data and row/col-to-XY placement are `apriltag_36h11.scad`'s
   responsibility, verified there. This file only centres that graphic on
   the plate; it does not re-derive or re-check the pattern.

   Coordinate convention: the plate is centred on X = Y = 0. Z = 0 is the
   plate's flat top face; the plate spans Z = -tag_plate_thk to 0 and the
   dark tag layer spans Z = -tag_embed to Z = tag_raise_h. Tab style: the
   tab runs along X on the plate's -Y edge and hangs `tab_h` below the
   plate's underside. The plate's -Y edge and the tab's outer face form one
   continuous flat face: no rounding in XY on that edge, no engraving.
   Bolt style: the tab leaves the plate's -Y edge at the plate's
   thickness, so the part is one flat slab; its centre line is at
   X = bolt_tab_x (0, or flush with +X).

   Print orientation: `on_side = true` rotates each tag 90 deg about Y, so
   the top face (and the dark tag layer) faces +X and the plate's +X edge
   face rests on the bed at Z = 0. On the side, each tag's footprint is an
   L (the plate as a bar along Y, the tab as a stub at one end), so every
   other tag (0-based even columns: 0, 2, 4, ...) is also turned 180 deg
   about the part's own X axis before standing it up. That puts its tab at
   the opposite end (+Y), pointing the other way (+X). The flipped tag is
   also raised `side_dy` (tab thickness plus `side_gap`) so the two plates
   can stand `side_plate_gap` apart: the flipped tag's tab passes over the
   top of its neighbour's plate, and the neighbour's tab passes under the
   flipped tag's plate. No solids intersect; every other clearance is
   `side_gap`. Plates
   read left to right as (flipped, unflipped). The
   convention above describes the unrotated part, which is what every
   module builds; only the final placement is rotated. Bolt style has no
   L to nest (its footprint on the side is a straight strip), so its tags
   are not flipped or raised: they stand `side_plate_gap` apart.

   ID label: small, engraved into the top face in the quiet zone's top-left
   corner (-X, +Y, viewed from above), `id_inset` in from both plate edges.
   It sits inside the quiet zone by choice (Aaron, REV 1.2): small enough
   to accept for this application. Revision stamp: tab style, engraved
   into the tab's inner (+Y) face, under the plate, so the flat outer face
   is untouched; bolt style, engraved into the tab's top face between the
   plate edge and the hole.

   Tray type label: the tray type for the id (`tray_type()`), engraved in
   the quiet zone's top-right corner (+X, +Y), mirroring the ID label and
   in the same font, size and depth. Id ranges (Aaron, REV 1.13): 1-75
   "4x5", 76-150 "4x4", 151-225 "1x1", 226-299 "OTHER". Ids above 299
   fail the id assert: 300-449 are the calibration sheets and 450-499 the
   corner tags (PLAN.md's tag ID allocation, src/npec_rig/tags.py).

   Open assumption, not yet measured: `tag_border` (quiet-zone margin) and
   `tag_embed` are starting values, same status as in
   `apriltag_corner_mount.scad`.

   REV 1.13: tray ids moved into 1-299 (Aaron): 1-75 4x5, 76-150 4x4,
     151-225 1x1, 226-299 OTHER. REV 1.11's 1-399 overlapped the
     calibration sheets (300-449). Geometry unchanged.
   REV 1.12: style "clip" renamed "tab" (Aaron); `tag_style` must be "tab"
     or "bolt". Geometry unchanged.
   REV 1.11: tray type label in the quiet zone's top-right corner, from the
     id (Aaron). Ids limited to 1-399. Geometry otherwise unchanged.
   REV 1.10: fix -- on the side in clip style, a tag's flip followed its
     list index but its raise followed its column. With an odd column
     count, every other row started on an odd index, so its column-0 tag
     was raised but not flipped and collided with its neighbour (Aaron;
     reproduced with 6 tags in 3 columns: 5 solids, not 6). Both now
     follow the column (`flipped()`).
   REV 1.9: `bolt_tab_flush` (Aaron): puts the bolt tab flush with the
     plate's +X edge, so on the side it rests on the bed rather than
     overhanging 11 mm above it. The tab covers that plate corner, so the
     edge runs straight from plate to tab.
   REV 1.8: `tag_style` (Aaron): "clip" is the existing 90 deg tab; new
     "bolt" style with an in-plane 25 mm tab and an M8 clearance hole
     (`bolt_dia` 8.4, ISO 273 fine series). Either style lays out flat or
     on its side; styles are not mixed in one layout.
   REV 1.7: added `side_plate_gap` (default 3 mm), the space between the
     two plates of a pair, which was `side_gap` (1 mm) (Aaron). Up to the
     tab's reach past its own plate minus the partner's thickness (4.4 mm
     at defaults) it costs no X; beyond that the pair pitch grows to keep
     `side_gap` to the next pair. Geometry unchanged.
   REV 1.6: tighter side layout (Aaron): the flipped (even) tag is raised
     `side_dy` so the pair's tabs cross over and under each other's plates
     instead of facing each other across an open gap. New `side_gap`
     (default 1 mm) for the side layout; `plate_gap` is now flat only.
     Pair pitch with 1 mm gaps: 12.6 mm, was 17.2 mm. Geometry
     unchanged.
   REV 1.5: `plate_gap` default 10 -> 2. A staircase ("stagger") layout on
     the side was tried in this revision and reverted (did not work as
     intended); the REV 1.4 flipped pairs remain the side layout. Geometry
     unchanged.
   REV 1.4: on the side, even-indexed tags flip 180 deg about the part's X
     axis and nest with their right-hand neighbour (Aaron). Pair spacing
     `nest_dx`; `col_x()` replaces the fixed X pitch. Geometry unchanged.
   REV 1.3: added `on_side` and `orient()` (Aaron): optional print
     orientation rotated 90 deg about Y, resting on the XY plane. Geometry
     unchanged.
   REV 1.2: ID label moved to the top face, into the quiet zone's top-left
     corner, smaller (`id_size` 4 -> 2.5, `id_depth` 1.0 -> 0.6), placed
     `id_inset` from the plate's -X and +Y edges (Aaron). Plate size
     unchanged. Revision stays on the tab's inner face.
   REV 1.1: the outer (-Y) face is completely flat (Aaron): the ID label and
     revision stamp moved to the tab's inner (+Y) face, and the plate's two
     -Y corners are square in XY so the face has no curved ends. The tab's
     two bottom corners are rounded in XZ instead (`tab_r`). `corner_r` now
     applies to the plate's two +Y corners only.
   REV 1.0: initial, from Aaron's sketch (30 mm tag, 6 mm quiet zone, 3 mm
     plate, 8 mm tab). Sketch names mapped to the corner mount's:
     `tag_quiet` -> `tag_border`, `tag_thick` -> `tag_plate_thk`,
     `mount_z` -> `tab_h`, `base_size` -> `pw`. The sketch's tab overlapped
     the plate by 1 mm and dropped 7 mm below it; here it drops the full
     `tab_h` below the underside. Added `tab_thk` (the sketch reused the
     plate thickness for it).
   --------------------------------------------------------------------------- */

use <../libraries/apriltag_36h11.scad>

/* [Style] */
tag_style = "tab"; // ["tab", "bolt"]
// tab: 90 deg tab over the tray edge; bolt: in-plane tab with an M8 hole  ["tab","bolt"]

/* [Tag] */
tag_ids       = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]; // 36h11 ids, one tray tag each, laid out in this order -- tray id allocation not yet confirmed (PLAN.md open questions)
tag_size      = 30;    // 36h11 tag width, mm -- tray tags (PLAN.md)
tag_border    = 6;     // quiet-zone margin each side, mm -- informed default, not yet measured [4:0.1:25]
tag_plate_thk = 3;     // total plate thickness, mm  [2:0.5:6]
tag_raise_h   = 0.6;   // dark tag layer height above the plate's top face, mm  [0.2:0.1:2]
tag_embed     = 0.2;   // how far the dark layer sinks into the plate so the parts overlap, mm  [0:0.05:1]
corner_r      = 3;     // rounding on the plate's vertical corners (tab style: +Y corners only, the -Y edge stays square), mm  [0:0.5:10]

/* [Tab] */
tab_h   = 8;   // how far the tab hangs below the plate's underside, mm  [2:0.5:30]
tab_thk = 3;   // tab thickness, Y, mm  [1:0.5:6]
tab_r   = 3;   // rounding on the tab's two bottom corners, XZ plane, mm  [0:0.5:10]

/* [Bolt Tab] */
bolt_tab_len    = 25;  // tab length past the plate's -Y edge, mm  [10:0.5:60]
bolt_tab_w      = 20;  // tab width, X; also the diameter of its round end, mm  [10:0.5:42]
bolt_dia        = 8.4; // M8 clearance hole, concentric with the round end, mm -- ISO 273 fine 8.4, medium 9.0
bolt_tab_fillet = 3;   // fillet in the corners where the tab meets the plate, mm  [0:0.5:10]
bolt_tab_flush  = true; // tab flush with the plate's +X edge (the bed face when on_side) instead of centred

/* [ID Label] */
id_label  = true;                      // engrave each tag's id on the top face, in the quiet zone's top-left corner
id_size   = 2.5;                       // label text cap height, mm  [1.5:0.5:6]
id_inset  = 2;                         // label's distance in from the plate's -X and +Y edges, mm  [0.5:0.25:5]
id_depth  = 0.6;                       // how far the label is inset into the top face, mm  [0.2:0.1:2]
id_font   = "Liberation Sans:style=Bold";
type_label = true;                     // engrave each tag's tray type (4x5, 4x4, 1x1, OTHER) in the quiet zone's top-right corner, same size, inset and depth as the id

/* [Colors] */
body_color        = "White"; // also the tag's background and quiet zone
tag_pattern_color = "Black"; // the tag's dark modules

/* [Render Select] */
part = "assembly"; // what to render  ["assembly","body","graphic"]

/* [Build Plate] */
on_side    = true; // rotate each tag 90 deg about Y so it stands on its +X edge, resting on Z = 0
plate_gap  = 2;   // clear space between neighbouring tags, flat layout, mm  [0:0.5:50]
side_gap   = 5;   // clear space between neighbouring tags, side layout, mm  [0.2:0.1:10]
side_plate_gap = 5; // space between the two plates of a nested pair, side layout, mm  [0.2:0.1:10]
plate_cols = 0;   // tags per row; 0 = auto (block closest to square)  [0:1:20]

/* [Revision] */
revision  = "RV1.13"; // revision stamp, engraved on the tab: tab style inner face, bolt style top face ("" = none)
rev_size  = 3;       // text cap height, mm  [2:0.5:8]
rev_depth = 1.0;     // how far the text is inset below the surface, mm  [0.4:0.1:2]

/* [Render] */
$fn = $preview ? 32 : 96;
eps = 0.01;

/* [Hidden] */
pw = tag_size + 2 * tag_border; // plate width, X and Y
cr = min(corner_r, pw / 2);     // clamp: rounding can't exceed half the plate
tr = min(tab_r, tab_h, pw / 2); // clamp: rounding can't exceed the tab's height or half its width
tabbed = tag_style == "tab"; // false: bolt
bolt_tab_x = bolt_tab_flush ? pw / 2 - bolt_tab_w / 2 : 0; // tab centre line, X
bolt_y   = -pw / 2 - bolt_tab_len + bolt_tab_w / 2; // hole and round-end centre, Y
bolt_rev_y = (-pw / 2 + bolt_y + bolt_dia / 2) / 2; // revision centre: midway between plate edge and hole edge
tab_ext  = tabbed ? 0 : bolt_tab_len; // how far the part reaches past the plate's -Y edge
label_z = -(tag_plate_thk + tab_h / 2); // text centre height, middle of the tab's exposed inner face
rev_x = pw / 4;                         // revision stamp, X centre on the tab's inner face

// tray type for a tag id; the id ranges are the allocation (header)
function tray_type(id) = id <= 75  ? "4x5"
                       : id <= 150 ? "4x4"
                       : id <= 225 ? "1x1"
                       : "OTHER";

assert(tag_style == "tab" || tag_style == "bolt", "tag_style must be \"tab\" or \"bolt\"");
assert(len(tag_ids) > 0, "tag_ids must list at least one id");
assert(min(tag_ids) >= 1 && max(tag_ids) <= 299,
       "tag_ids must be within 1-299, the tray tag ids (tray_type()); 300-449 are calibration sheets");
assert(tab_thk < pw / 2, "tab too thick for the plate");
assert(!tabbed || rev_depth < tab_thk, "revision engraving deeper than the tab");
assert(tabbed || rev_depth < tag_plate_thk, "revision engraving deeper than the bolt tab");
assert(tabbed || bolt_tab_len >= bolt_tab_w / 2, "bolt tab shorter than its round end");
assert(tabbed || bolt_dia < bolt_tab_w - 2, "M8 hole leaves under 1 mm of wall in the bolt tab");
assert(tabbed || bolt_tab_w <= pw, "bolt tab wider than the plate");
assert(id_depth < tag_plate_thk, "id engraving deeper than the plate");

// full Z extent of the unrotated part: bottom (tab style: tab, bolt: plate) to
// the tag layer's top
z_lo = tabbed ? -(tag_plate_thk + tab_h) : -tag_plate_thk;
z_hi = tag_raise_h;

n_tags  = len(tag_ids);
gap     = on_side ? side_gap : plate_gap;
part_dx = on_side ? z_hi - z_lo : pw; // footprint in X; rotating about Y turns the part's height into X
tp      = tag_plate_thk + tag_raise_h; // plate plus tag layer, the part's X thickness on the side
nest    = on_side && tabbed; // flip-and-raise pairs: tab style on the side only
pitch_x = part_dx + (on_side ? side_plate_gap : gap); // bolt style on the side: plates side by side
pitch_y = pw + tab_ext + gap;

// Side layout, in footprint centres. A flipped tag's plate is at the -X end
// of its footprint with the tab reaching +X; an unflipped tag's plate is at
// the +X end with the tab reaching -X.
// side_dy: the flipped tag sits this much higher, so its tab clears the top
// of its partner's plate and the partner's tab clears its bottom.
side_dy = tab_thk + gap;
// nest_dx: flipped centre to unflipped centre, putting the unflipped plate
// `side_plate_gap` right of the flipped plate. Negative for plate gaps under
// part_dx - 2*tp: the footprints cross, the plates still read
// flipped-then-unflipped.
nest_dx = side_plate_gap - (part_dx - 2 * tp);
// pair_dx: pair to pair. The flipped tab sticks out past its partner's tag
// face and must clear the next pair's flipped plate (same height); the next
// pair's unflipped tab must clear this pair's unflipped plate. Both give
// one footprint plus the gap. The unflipped plate itself must also keep
// `gap` from the next flipped plate, which only binds once nest_dx > 0.
pair_dx = part_dx + gap + max(0, nest_dx);

// X centre of column c relative to column 0, and the Y raise of column c
function col_x(c)  = nest ? floor(c / 2) * pair_dx + (c % 2) * nest_dx
                          : c * pitch_x;
function col_dy(c) = nest && c % 2 == 0 ? side_dy : 0;
// tag i is flipped by its column, matching col_dy -- not by its list index,
// which disagrees with the column on every other row when grid_cols is odd
function flipped(i) = nest && (i % grid_cols) % 2 == 0;
// X extent of a row of c columns' footprints
function row_lo(c) = min([for (k = [0 : c - 1]) col_x(k)]) - part_dx / 2;
function row_hi(c) = max([for (k = [0 : c - 1]) col_x(k)]) + part_dx / 2;
// row to row, Y: a raised flipped tag adds side_dy to the row's height
function row_dy(c) = pitch_y + (nest && c > 1 ? side_dy : 0);
// block size for c columns, each including one trailing gap
function span_x(c) = row_hi(c) - row_lo(c) + gap;
function span_y(c) = ceil(n_tags / c) * row_dy(c);

// auto columns: the count whose block fits the smallest enclosing square
// (fewest columns wins a tie)
block_side = [for (c = [1 : n_tags]) max(span_x(c), span_y(c))];
grid_cols = plate_cols > 0 ? min(plate_cols, n_tags)
                           : search(min(block_side), block_side)[0] + 1;
grid_rows = ceil(n_tags / grid_cols);

// centre of tag i lands on the block's grid cell, block centred on the
// origin; row 0 at +Y so the list reads left to right, top to bottom
function slot(i) = let(c = i % grid_cols) [
    col_x(c) - (row_lo(grid_cols) + row_hi(grid_cols)) / 2,
    ((grid_rows - 1) / 2 - floor(i / grid_cols)) * row_dy(grid_cols)
        + col_dy(c) - (grid_cols > 1 ? col_dy(0) / 2 : 0)
        + tab_ext / 2, // centre the footprint, tab included, on the cell
    0
];

// ---------------------------------------------------------------------------

module bolt_profile() {
    // XY plan view, bolt style: pw square with all four corners rounded,
    // plus the tab off the -Y edge ending in a semicircle around the hole.
    // A flush tab covers the plate's rounded +X/-Y corner, so that edge
    // runs straight from plate to tab.
    // The outer offset pair fillets the two concave tab/plate corners
    // (offset(delta=+f) then offset(r=-f) rounds only concave corners).
    offset(r = -bolt_tab_fillet) offset(delta = bolt_tab_fillet)
        union() {
            offset(r = cr) offset(delta = -cr) square(pw, center = true);
            hull() {
                translate([bolt_tab_x - bolt_tab_w / 2, -pw / 2 + cr]) square([bolt_tab_w, eps]);
                translate([bolt_tab_x, bolt_y]) circle(d = bolt_tab_w);
            }
        }
}

module bolt_rev_stamp() {
    // engraved into the bolt tab's top face, reading along +X, between the
    // plate edge and the hole
    translate([bolt_tab_x, bolt_rev_y, -rev_depth])
        linear_extrude(rev_depth + eps)
            text(revision, size = rev_size, halign = "center", valign = "center");
}

module plate_profile() {
    // XY plan view: pw square, rounded at the two +Y corners only. The -Y
    // edge stays square so it is flush with the tab's flat outer face.
    hull() {
        translate([-pw / 2, -pw / 2]) square([pw, eps]);
        translate([-pw / 2 + cr, pw / 2 - cr]) circle(cr);
        translate([ pw / 2 - cr, pw / 2 - cr]) circle(cr);
    }
}

module tab() {
    // XZ profile extruded along +Y from the plate's -Y edge: square at the
    // top (overlapping the plate by eps), rounded at the two bottom corners
    zb = -(tag_plate_thk + tab_h);
    translate([0, -pw / 2 + tab_thk, 0]) rotate([90, 0, 0]) linear_extrude(tab_thk)
        hull() {
            translate([-pw / 2, -tag_plate_thk - eps]) square([pw, eps]);
            translate([-pw / 2 + tr, zb + tr]) circle(tr);
            translate([ pw / 2 - tr, zb + tr]) circle(tr);
        }
}

module tab_text(s, x, size, depth, font) {
    // engraved into the tab's inner (+Y) face, reading correctly when viewed
    // from +Y (from under the plate). rotate([90, 0, 180]) maps text X to
    // world -X, text Y to world +Z, and the extrusion to +Y.
    translate([x, -pw / 2 + tab_thk - depth, label_z]) rotate([90, 0, 180])
        linear_extrude(depth + eps)
            text(s, size = size, font = font, halign = "center", valign = "center");
}

module id_engrave(id) {
    // engraved into the top face in the quiet zone's top-left corner viewed
    // from above, its top-left corner `id_inset` in from both plate edges
    translate([-pw / 2 + id_inset, pw / 2 - id_inset, -id_depth])
        linear_extrude(id_depth + eps)
            text(str(id), size = id_size, font = id_font, halign = "left", valign = "top");
}

module type_engrave(id) {
    // engraved into the top face in the quiet zone's top-right corner viewed
    // from above, mirroring id_engrave(): its top-right corner `id_inset` in
    // from the plate's +X and +Y edges
    translate([pw / 2 - id_inset, pw / 2 - id_inset, -id_depth])
        linear_extrude(id_depth + eps)
            text(tray_type(id), size = id_size, font = id_font, halign = "right", valign = "top");
}

module tray_tag_body(id = tag_ids[0]) {
    difference() {
        if (tabbed)
            union() {
                translate([0, 0, -tag_plate_thk])
                    linear_extrude(tag_plate_thk) plate_profile();
                tab();
            }
        else
            translate([0, 0, -tag_plate_thk])
                linear_extrude(tag_plate_thk) bolt_profile();

        if (!tabbed)
            translate([bolt_tab_x, bolt_y, -tag_plate_thk - eps])
                cylinder(d = bolt_dia, h = tag_plate_thk + 2 * eps);
        if (revision != "") {
            if (tabbed) tab_text(revision, rev_x, rev_size, rev_depth, "Liberation Sans");
            else      bolt_rev_stamp();
        }
        if (id_label)
            id_engrave(id);
        if (type_label)
            type_engrave(id);
    }
}

module tray_tag_graphic(id = tag_ids[0]) {
    // dark tag layer, Z from -tag_embed to tag_raise_h, centred on the plate.
    // Uncolored: the caller applies color(), which is what keeps it a
    // separate 3MF object under lazy union (see apriltag_corner_mount.scad).
    translate([0, 0, -tag_embed])
        april_tag_pattern(id = id, edge = tag_size, thickness = 0,
                          raise_h = tag_raise_h + tag_embed);
}

module orient(flip = false) {
    // print placement for the children. on_side: rotate 90 deg about Y
    // (the top face turns to +X, the +X edge face to -Z), lift that edge
    // face onto Z = 0, and centre the rotated footprint on X = 0. flip
    // first turns the part 180 deg about its own X axis and shifts it back
    // into the same Z range [z_lo, z_hi], so both versions share a footprint.
    if (on_side)
        translate([-(z_lo + z_hi) / 2, 0, pw / 2]) rotate([0, 90, 0])
            if (flip)
                translate([0, 0, z_lo + z_hi]) rotate([180, 0, 0]) children();
            else
                children();
    else
        children();
}

// ---------------------------------------------------------------------------

// Layout loop stays here at the top level, not in a module: every colored
// statement inside a top-level for() is its own lazy-union 3MF object, which
// scad_to_3mf.py then pairs back up into one Orca object per tag.
for (i = [0 : n_tags - 1]) {
    if (part != "graphic")
        translate(slot(i)) color(body_color) orient(flipped(i)) tray_tag_body(tag_ids[i]);
    if (part != "body")
        translate(slot(i)) color(tag_pattern_color) orient(flipped(i)) tray_tag_graphic(tag_ids[i]);
}
