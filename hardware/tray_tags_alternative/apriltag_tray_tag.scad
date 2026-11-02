/* ---------------------------------------------------------------------------
   AprilTag tray tag, version 2 -- one 36h11 tag per growth tray, the
   design chosen from the id's tray type (see Designs by tray type below).
   Replaces `apriltag_tray_tags_v1.scad` (Aaron, REV 2.0), kept for
   reference. The description below starts from the first design, "4x5":
   a 40 mm tag on a 60.5 mm square plate with rounded corners, and a lip
   standing 90 deg up from the plate's +Y edge. The plate outline is
   copied from a physical part (`tag_outline_61.scad`, checked on paper at
   1:1), then made 0.5 mm smaller overall: 60.5 mm (Aaron, REV 2.1).

   One continuous multi-material print, two colors, no assembly step, same
   construction as `apriltag_tray_tags_v1.scad`:
     - `lip_tag_body(id)` -- the plate and lip. The plate's top face is the
       tag's white background and quiet zone. One color (`body_color`).
     - `lip_tag_graphic(id)` -- the dark 36h11 layer for one id, via
       `apriltag_36h11.scad`'s `april_tag_pattern()`, standing `tag_raise_h`
       proud of the plate and sunk `tag_embed` into it so the two parts
       overlap rather than merely touch. One color (`tag_pattern_color`).

   Export with `scad_to_3mf.py` so Orca loads both as parts of one object
   with a filament each; see that script.

   The bit data and row/col-to-XY placement are `apriltag_36h11.scad`'s
   responsibility, verified there. This file only centres that graphic on
   the plate; it does not re-derive or re-check the pattern.

   Coordinate convention: the plate is centred on X = Y = 0. Z = 0 is the
   plate's flat top face; the plate spans Z = -plate_thk to 0 and the dark
   tag layer spans Z = -tag_embed to Z = tag_raise_h. The lip is the band
   of the plate outline within `lip_thk` of the +Y edge, extruded from the
   plate's underside up to `lip_h` above the top face, so it follows the
   rounded corners at its ends. Its outer (+Y) face is one surface with
   the plate's +Y edge.

   Corner radius: derived from the physical part, not measured directly
   (see `tag_outline_61.scad`): 9.33 mm, from a 14.85 mm gap across the
   corner to a 48.84 mm reference circle. The circle was reference only
   and is not part of this model.

   Tag size: 40 mm black border, so 5 mm bits and a 50 mm white square
   (one bit of quiet zone) with 5.25 mm of plate past it on the flat sides
   and 2.25 mm clear of the lip. The largest that fits with one bit of
   quiet zone is 43.6 mm, set by the lip; the asserts check the quiet zone
   against the outline and the lip.

   Print orientation: `on_side = true` rotates each tag -90 deg about X,
   so the lip's outer (+Y) face rests on the bed at Z = 0 (Aaron, REV 1.1),
   the lip lies flat in the XY plane and the plate stands up from it with
   the top face (and the dark tag layer) facing +Y. The lip covers the
   plate's whole thickness, so each tag's footprint is a plain
   plate_w x (plate_thk + lip_h) rectangle and the tags lay out in a
   straight grid: no flip-and-raise pairs as in `apriltag_tray_tags_v1.scad`.
   The convention above describes the unrotated part, which is what every
   module builds; only the final placement is rotated. With all four
   corners rounded, only the flat part of the lip's outer face
   (plate_w - 2 * corner_r) rests on the bed; its rounded ends rise off it.
   "1x1" is the exception (Aaron, REV 1.9): it rotates 90 deg about Y
   instead, so its +X edge, the one the bolt tab is flush with, rests on
   the bed, the top face faces +X and the lip reaches +X along the top
   of the footprint; the tab lies along the bed at -Y. Footprints then
   differ by design, and the grid pitch is the largest of them.

   ID label: small, engraved into the top face in the top-left corner (-X,
   +Y, viewed from above), centred on the corner's diagonal halfway between
   the black border's corner and the plate's rounded edge, so it sits in
   the quiet zone as on the tray tag (Aaron, tray tag REV 1.2).

   File name and revision: engraved into the lip's inner (-Y) face, the
   face toward the tag (Aaron, REV 1.1), on one line reading correctly
   viewed from the tag side: the revision left-justified and the file name
   right-justified (Aaron, REV 1.2), each `lbl_inset` in from the face's
   ends, on a shared baseline that centres the line on the face's height
   (from the plate's top face to the lip's top).

   Designs by tray type (Aaron, REV 1.3): each tag's design follows its
   id through `tray_type()`, the same id ranges as `apriltag_tray_tags_v1.scad`:
   1-75 "4x5", 76-150 "2x2", 151-225 "1x1", 226-250 "black_tray",
   251-299 "OTHER" (black_tray, Aaron, REV 1.6). Ids above
   299 fail the id assert: 300-449 are the calibration sheets and 450-499
   the corner tags. Each design's dimensions are its own Customizer group;
   the `t_*()` functions return them for a type. Designs so far:
     - "4x5": the rounded square above (60.5 mm, 9.33 mm corners, 40 mm
       tag).
     - "2x2": a 61 mm square with 3 mm corners, as on the tray tag
       (Aaron, REV 1.4), and a 42 mm tag: 5.25 mm bits, its one-bit white
       square 1.25 mm clear of the lip. The lip, not the corners, limits
       the tag here (44 mm at most with one bit of quiet zone).
     - "1x1": the "2x2" (its Customizer group sets both) plus the tray
       tag's bolt tab (Aaron, REV 1.5): a tab in the plate's own plane,
       `bolt_tab_len` past the -Y edge (opposite the lip), with a round
       end and an M8 clearance hole concentric with it, and the
       tab-to-plate corner filleted (`bolt_tab_fillet`). The tab is flush
       with the +X edge, the same side as the type label (Aaron, REV 1.7),
       so the tab covers that plate corner and the edge runs straight from
       plate to tab. On the side the tag stands on that +X edge, with the
       tab on the bed (print orientation, below).
     - "black_tray": a 51 mm disc with a 30 mm tag, no lip, flat print
       only (Aaron, REV 1.6): it lies flat whatever `on_side` says
       (REV 1.8). The one-bit white square's corners reach
       26.5 mm from the centre, so the disc cuts about 1 mm off each of
       them; along the edges the quiet zone is a full bit (3.75 mm). The
       largest tag with the whole white square inside the disc is
       28.8 mm; 30 mm is a trial (Aaron: "see if it works"). With no lip,
       the revision alone is engraved into the underside, centred and
       mirrored as on the tray tag; no file name (Aaron, REV 1.7). The id
       and type labels are
       centred in the disc's strips above and below the white square
       (id at +Y, type at -Y), outside the quiet zone: the top corners are
       too small for them on a disc.
   Ids whose type has no design yet fail an assert.

   Tray type label: the tray type for the id, engraved in the top-right
   corner (+X, +Y), mirroring the ID label, in the same font, size and
   depth, as on the tray tag.

   Tag size label (Aaron, REV 1.10): the tag's own size, its black border
   edge to edge (`t_tag()`, the black and white modules in total, not the
   plate), as "W x H mm" to 0.1 mm, e.g. "40.0 x 40.0 mm". Engraved in the
   quiet zone below the tag (-Y), centred on X and on the one-bit quiet
   zone's width, in the same font, size and depth as the id. It is the
   size the model draws; the printed tag should be checked with callipers.

   Open assumption, not yet measured: `tag_embed` is a starting value, same
   status as in `apriltag_tray_tags_v1.scad`.

   REV 2.2: tray type "4x4" renamed "2x2" (ids 76-150 unchanged): these
     trays have 2 x 2 cells, 4 plants; "4x4" was a mislabel (Aaron,
     2026-10-29, #327). The engraved type label changes with it.
     Geometry unchanged.
   REV 2.1: "4x5" plate 61 -> 60.5 mm, still square, corners and tag
     unchanged (Aaron). Other designs unchanged.
   REV 2.0: revision 1.10 renumbered for the first test prints of all
     four designs (Aaron). Renamed from `apriltag_lip_tag.scad` to
     `apriltag_tray_tag.scad`, replacing the previous tray tag, now
     `apriltag_tray_tags_v1.scad`; `part_name` follows. Geometry
     unchanged.
   REV 1.10: tag size label in the quiet zone below the tag, every design
     (Aaron). Geometry otherwise unchanged.
   REV 1.9: on the side, "1x1" stands on its +X edge (the bolt tab's
     flush edge) instead of the lip (Aaron). Grid pitch from each
     design's footprint. Flat tags are lifted so their underside is on
     Z = 0, level with sided tags in a mixed layout (with REV 1.8 a flat
     black_tray sat 3 mm below them). Geometry unchanged.
   REV 1.8: "black_tray" lies flat even with `on_side` set, instead of
     failing an assert; `on_side` applies to the lipped designs only.
     Geometry unchanged.
   REV 1.7: "1x1" bolt tab flush with the +X edge instead of centred;
     "black_tray" underside has the revision only, no file name, and
     `under_gap` is removed (Aaron). Other designs unchanged.
   REV 1.6: "black_tray" design, ids 226-250 (Aaron); "OTHER" is now
     251-299. Other designs unchanged.
   REV 1.5: "1x1" design, the "4x4" with the tray tag's bolt tab centred
     on the -Y edge (Aaron). Other designs unchanged.
   REV 1.4: "4x4" design, 61 mm, 3 mm corners, 42 mm tag (Aaron).
     Geometry of "4x5" unchanged.
   REV 1.3: design chosen by tray type from the id (`tray_type()`), id
     ranges as `apriltag_tray_tags_v1.scad` (Aaron). The current design is
     "4x5"; `plate_w`, `corner_r` and `tag_size` become `t45_plate_w`,
     `t45_corner_r` and `t45_tag_size`. Tray type label in the top-right
     corner. Ids limited to 1-299. Geometry unchanged.
   REV 1.2: file name and revision on one line, 3 mm text, revision at
     the left end, file name right-justified (Aaron). `label_gap`
     replaced by `lbl_inset`. Geometry otherwise unchanged.
   REV 1.1: file name and revision moved to the lip's inner face, text
     1.5 mm (Aaron). On the side, tags rest on the lip's outer face
     instead of the plate's +X edge, laid out in a straight grid;
     `side_plate_gap` and the flip-and-raise pairs removed. Geometry
     otherwise unchanged.
   REV 1.0: initial (Aaron): 61 mm plate, 9.33 mm corners, 3 mm thick,
     40 mm tag, 5 mm lip at +Y, ids 1-12, file name and revision on the
     lip, id in the top-left corner, flat or on-side layout. No bolt hole.
   --------------------------------------------------------------------------- */

use <../libraries/apriltag_36h11.scad>

/* [Tag] */
tag_ids     = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]; // 36h11 ids, one lip tag each, laid out in this order; the id picks the design (tray_type())
tag_raise_h = 0.6;  // dark tag layer height above the plate's top face, mm  [0.2:0.1:2]
tag_embed   = 0.2;  // how far the dark layer sinks into the plate so the parts overlap, mm  [0:0.05:1]

/* [Plate] */
plate_thk = 3;     // plate thickness, all designs, mm  [2:0.5:6]

/* [4x5 Design] */
t45_plate_w  = 60.5;  // plate side, X and Y, mm -- the physical part's 61, less 0.5 (REV 2.1)  [40:0.5:100]
t45_corner_r = 9.33;  // rounding on the plate's four vertical corners, mm -- derived, see header  [0:0.01:20]
t45_tag_size = 40;    // 36h11 tag width (black border), mm  [20:0.5:44]

/* [2x2 and 1x1 Design] */
t22_plate_w  = 61;    // plate side, X and Y, mm  [40:0.5:100]
t22_corner_r = 3;     // rounding on the plate's four vertical corners, mm -- as on the tray tag  [0:0.5:20]
t22_tag_size = 42;    // 36h11 tag width (black border), mm  [20:0.5:44]

/* [black_tray Design] */
tbk_dia      = 51;  // disc diameter, mm  [30:0.5:100]
tbk_tag_size = 30;  // 36h11 tag width (black border), mm -- trial, see header  [20:0.5:36]

/* [1x1 Bolt Tab] */
bolt_tab_len    = 25;  // tab length past the plate's -Y edge, mm  [10:0.5:60]
bolt_tab_w      = 20;  // tab width, X; also the diameter of its round end, mm  [10:0.5:42]
bolt_dia        = 8.4; // M8 clearance hole, concentric with the round end, mm -- ISO 273 fine 8.4, medium 9.0
bolt_tab_fillet = 3;   // fillet in the corners where the tab meets the plate, mm  [0:0.5:10]

/* [Lip] */
lip_h   = 5;  // how far the lip stands above the plate's top face, mm  [2:0.5:30]
lip_thk = 3;  // lip thickness, Y, mm  [1:0.5:6]

/* [ID Label] */
id_label = true;                      // engrave each tag's id on the top face, in the top-left corner
id_size  = 2.5;                       // label text cap height, mm  [1.5:0.5:6]
id_depth = 0.6;                       // how far the label is inset into the top face, mm  [0.2:0.1:2]
id_font  = "Liberation Sans:style=Bold";
size_label = true;                    // engrave each tag's size (black border edge to edge, "40.0 x 40.0 mm") in the quiet zone below the tag, same size and depth as the id
type_label = true;                    // engrave each tag's tray type (4x5, 2x2, 1x1, black_tray) in the top-right corner (black_tray: below the tag), same size and depth as the id

/* [Label] */
part_name  = "apriltag_tray_tag"; // file name without .scad, engraved right-justified in the lip's inner face ("" = none)
name_size  = 3;    // text cap height, mm  [1:0.25:4]
name_depth = 0.6;  // how far the text is inset into the lip's inner face, mm  [0.2:0.1:1.5]
lbl_inset  = 3;    // revision's and file name's distance in from the ends of the lip's inner face, mm  [0:0.5:10]

/* [Colors] */
body_color        = "White"; // also the tag's background and quiet zone
tag_pattern_color = "Black"; // the tag's dark modules

/* [Render Select] */
part = "assembly"; // what to render  ["assembly","body","graphic"]

/* [Build Plate] */
on_side    = true; // rotate each lipped tag -90 deg about X so it rests on the lip's outer face at Z = 0 (black_tray always lies flat)
plate_gap  = 2;    // clear space between neighbouring tags, flat layout, mm  [0:0.5:50]
side_gap   = 5;    // clear space between neighbouring tags, side layout, mm  [0.2:0.1:10]
plate_cols = 0;    // tags per row; 0 = auto (block closest to square)  [0:1:20]

/* [Revision] */
revision  = "RV2.2"; // revision stamp, engraved left-justified in the lip's inner face ("" = none)
rev_size  = 3;       // text cap height, mm  [1:0.25:4]
rev_depth = 0.6;     // how far the text is inset into the lip's inner face, mm  [0.2:0.1:1.5]

/* [Render] */
$fn = $preview ? 32 : 96;
eps = 0.01;

/* [Hidden] */
// tray type for a tag id; the id ranges are the allocation (header)
function tray_type(id) = id <= 75  ? "4x5"
                       : id <= 150 ? "2x2"
                       : id <= 225 ? "1x1"
                       : id <= 250 ? "black_tray"
                       : "OTHER";
designed = ["4x5", "2x2", "1x1", "black_tray"]; // tray types with a design in this file

// per-design dimensions, by tray type
// ("1x1" is the "2x2" plus the bolt tab)
function sq22(t)  = t == "2x2" || t == "1x1";
function t_disc(t) = t == "black_tray"; // round, no lip, flat print only
function t_w(t)   = t == "4x5" ? t45_plate_w  : sq22(t) ? t22_plate_w  : t_disc(t) ? tbk_dia : undef; // plate side (disc: diameter), X and Y
function t_tag(t) = t == "4x5" ? t45_tag_size : sq22(t) ? t22_tag_size : t_disc(t) ? tbk_tag_size : undef; // tag width (black border)
function t_cr(t)  = min(t == "4x5" ? t45_corner_r : sq22(t) ? t22_corner_r : t_disc(t) ? tbk_dia / 2 : undef,
                        t_w(t) / 2); // clamp: rounding can't exceed half the plate
function t_bolt(t) = t == "1x1";                     // has the bolt tab
function t_ext(t)  = t_bolt(t) ? bolt_tab_len : 0;   // how far the part reaches past the plate's -Y edge
function t_bolt_y(t) = -t_w(t) / 2 - bolt_tab_len + bolt_tab_w / 2; // hole and round-end centre, Y
function t_bolt_x(t) = t_w(t) / 2 - bolt_tab_w / 2; // tab centre line, X: flush with the +X edge

// derived, by tray type
function t_flat(t) = t_w(t) / 2 - t_cr(t); // where the straight edges end, from the centre
function t_wh(t)   = t_tag(t) / 2 + t_tag(t) / 8; // half-width of the white square: one bit (36h11 is 8 bits across its black border)
// the outline's distance from the centre along the diagonal, as a half-width:
// a square of half-width h fits inside the rounded corners while h <= this
function t_corner_h(t) = t_flat(t) + t_cr(t) / sqrt(2);
// id and type label centres: on the top corners' diagonals, halfway
// between the black border's corner and the rounded edge
function t_id_c(t) = (t_tag(t) / 2 + t_corner_h(t)) / 2;
// the lip's inner face, Y, and its ends, X: where the plate outline
// crosses Y = lip_in_y
function t_lip_in_y(t) = t_w(t) / 2 - lip_thk;
function t_lip_in_x(t) = let(y = t_lip_in_y(t), f = t_flat(t), r = t_cr(t))
    y <= f ? t_w(t) / 2 : f + sqrt(r * r - (y - f) ^ 2);

// lip inner-face label: one line, revision and file name on a shared
// baseline. The line's height is the larger cap height plus 0.3 of it for
// descenders, centred on the face's height.
face_lo = 0;
face_hi = lip_h;
lbl_sz  = max(part_name == "" ? 0 : name_size, revision == "" ? 0 : rev_size);
lbl_h   = 1.3 * lbl_sz;
lbl_bz  = (face_lo + face_hi) / 2 - lbl_h / 2 + 0.3 * lbl_sz; // baseline, Z

assert(len(tag_ids) > 0, "tag_ids must list at least one id");
assert(min(tag_ids) >= 1 && max(tag_ids) <= 299,
       "tag_ids must be within 1-299, the tray tag ids (tray_type()); 300-449 are calibration sheets");
for (id = tag_ids) let(t = tray_type(id)) {
    assert(len([for (d = designed) if (d == t) d]) > 0,
           str("tag id ", id, ": tray type ", t, " has no design yet"));
    if (t_disc(t)) {
        // disc: the quiet zone's corners may be clipped (header); its
        // edges may not
        assert(t_wh(t) <= t_w(t) / 2, str(t, ": tag's quiet zone runs past the disc's edge"));
    } else {
        assert(t_wh(t) <= t_corner_h(t), str(t, ": tag's quiet zone runs past the rounded corners"));
        assert(t_wh(t) <= t_lip_in_y(t), str(t, ": tag's quiet zone runs under the lip"));
    }
}
// disc label centres, Y: halfway between the white square's edge and the disc's edge
function t_disc_lbl_y(t) = (t_wh(t) + t_w(t) / 2) / 2;
// size label: centre Y, in the middle of the one-bit quiet zone below the
// tag, and its text
function t_size_y(t) = -(t_tag(t) / 2 + t_tag(t) / 16);
function fmt1(x) = let(r = round(x * 10)) str(floor(r / 10), ".", r % 10); // x to 0.1
function t_size_txt(t) = str(fmt1(t_tag(t)), " x ", fmt1(t_tag(t)), " mm");
assert(!size_label || id_size < min([for (id = tag_ids) t_tag(tray_type(id))]) / 8,
       "size label taller than the quiet zone (one bit)");
assert(rev_depth + tag_embed < plate_thk, "underside engraving reaches the tag layer");
assert(bolt_tab_len >= bolt_tab_w / 2, "bolt tab shorter than its round end");
assert(bolt_dia < bolt_tab_w - 2, "M8 hole leaves under 1 mm of wall in the bolt tab");
for (id = tag_ids) let(t = tray_type(id))
    assert(!t_bolt(t) || bolt_tab_w + bolt_tab_fillet <= t_w(t) - t_cr(t),
           str(t, ": bolt tab and fillet wider than the plate's -Y edge"));
assert(lip_thk < min([for (id = tag_ids) t_w(tray_type(id))]) / 2, "lip too thick for the plate");
assert(id_depth + tag_embed < plate_thk, "id engraving reaches the tag layer");
assert(lbl_h < face_hi - face_lo, "file name and revision too tall for the lip's inner face");
assert(max(name_depth, rev_depth) < lip_thk, "lip engraving deeper than the lip");

// full Z extent of the unrotated part: plate underside to the lip's top
z_lo = -plate_thk;
z_hi = max(lip_h, tag_raise_h);

n_tags  = len(tag_ids);
// a tag goes on its side only when on_side is set and it has a lip:
// "black_tray" discs always lie flat (REV 1.8)
function sided(t) = on_side && !t_disc(t);
any_sided = len([for (id = tag_ids) if (sided(tray_type(id))) id]) > 0;
gap     = any_sided ? side_gap : plate_gap;
// on the side, "1x1" stands on its +X edge rather than the lip (header)
function on_edge(t) = sided(t) && t_bolt(t);
// footprint by design: the part's height (z_hi - z_lo) becomes X standing
// on an edge, Y standing on the lip; flat, the plate plus any bolt tab
function foot_x(t) = on_edge(t) ? z_hi - z_lo : t_w(t);
function foot_y(t) = sided(t) && !on_edge(t) ? z_hi - z_lo : t_w(t) + t_ext(t);
pitch_x = max([for (id = tag_ids) foot_x(tray_type(id))]) + gap;
pitch_y = max([for (id = tag_ids) foot_y(tray_type(id))]) + gap;

// auto columns: the count whose block fits the smallest enclosing square
// (fewest columns wins a tie)
block_side = [for (c = [1 : n_tags]) max(c * pitch_x, ceil(n_tags / c) * pitch_y)];
grid_cols = plate_cols > 0 ? min(plate_cols, n_tags)
                           : search(min(block_side), block_side)[0] + 1;
grid_rows = ceil(n_tags / grid_cols);

// centre of tag i lands on the block's grid cell, block centred on the
// origin; row 0 at +Y so the list reads left to right, top to bottom
function slot(i) = [
    ((i % grid_cols) - (grid_cols - 1) / 2) * pitch_x,
    ((grid_rows - 1) / 2 - floor(i / grid_cols)) * pitch_y
        + (sided(tray_type(tag_ids[i])) && !on_edge(tray_type(tag_ids[i]))
           ? 0 : t_ext(tray_type(tag_ids[i])) / 2), // centre the footprint, tab included, on the cell
    0
];

// ---------------------------------------------------------------------------

module plate_profile(t) {
    // XY plan view: square, all four corners rounded
    offset(r = t_cr(t)) offset(delta = -t_cr(t)) square(t_w(t), center = true);
}

module bolt_profile(t) {
    // XY plan view, "1x1": the plate outline plus the tab off the -Y edge,
    // flush with the +X edge, ending in a semicircle around the hole. The
    // tab starts at the corner's tangent point (-Y edge + cr), so it covers
    // the rounded +X/-Y corner and that edge runs straight. The outer
    // offset pair fillets the concave tab/plate corner (offset(delta=+f)
    // then offset(r=-f) rounds only concave corners), as on the tray tag.
    offset(r = -bolt_tab_fillet) offset(delta = bolt_tab_fillet)
        union() {
            plate_profile(t);
            hull() {
                translate([t_bolt_x(t) - bolt_tab_w / 2, -t_w(t) / 2 + t_cr(t)]) square([bolt_tab_w, eps]);
                translate([t_bolt_x(t), t_bolt_y(t)]) circle(d = bolt_tab_w);
            }
        }
}

module lip_profile(t) {
    // XY plan view: the plate outline within lip_thk of the +Y edge
    intersection() {
        plate_profile(t);
        translate([-t_w(t) / 2, t_lip_in_y(t)]) square([t_w(t), lip_thk]);
    }
}

module lip_text(t, txt, x, halign, size, depth) {
    // engraved into the lip's inner (-Y) face on the label baseline,
    // reading correctly viewed from the tag side (-Y), where +X is to the
    // right. rotate([90, 0, 0]) extrudes toward -Y, so the text starts
    // `depth` inside the lip and ends eps past the face.
    translate([x, t_lip_in_y(t) + depth, lbl_bz]) rotate([90, 0, 0])
        linear_extrude(depth + eps)
            text(txt, size = size, halign = halign, valign = "baseline");
}

module corner_engrave(txt, x, y) {
    // engraved into the top face, centred on (x, y)
    translate([x, y, -id_depth])
        linear_extrude(id_depth + eps)
            text(txt, size = id_size, font = id_font, halign = "center", valign = "center");
}

module underside_text(txt, y, valign, size, depth) {
    // engraved up into the plate's underside, mirrored in X so it reads
    // correctly viewed from below, centred on X (as on the tray tag)
    translate([0, y, -plate_thk - eps])
        linear_extrude(depth + eps)
            mirror([1, 0, 0])
                text(txt, size = size, halign = "center", valign = valign);
}

module disc_tag_body(id) {
    // "black_tray": disc, no lip; labels per the header
    t = tray_type(id);
    ly = t_disc_lbl_y(t);
    difference() {
        translate([0, 0, -plate_thk])
            linear_extrude(plate_thk) circle(d = t_w(t));
        if (revision != "") underside_text(revision, 0, "center", rev_size, rev_depth);
        if (id_label)   corner_engrave(str(id), 0, ly);   // above the tag
        if (type_label) corner_engrave(t, 0, -ly);        // below the tag
        if (size_label) corner_engrave(t_size_txt(t), 0, t_size_y(t));
    }
}

module lip_tag_body(id = tag_ids[0]) {
    t = tray_type(id);
    c = t_id_c(t);
    if (t_disc(t)) disc_tag_body(id);
    else difference() {
        union() {
            translate([0, 0, -plate_thk])
                linear_extrude(plate_thk)
                    if (t_bolt(t)) bolt_profile(t); else plate_profile(t);
            translate([0, 0, -plate_thk])
                linear_extrude(plate_thk + lip_h) lip_profile(t);
        }
        if (t_bolt(t))
            translate([t_bolt_x(t), t_bolt_y(t), -plate_thk - eps])
                cylinder(d = bolt_dia, h = plate_thk + 2 * eps);
        if (part_name != "") lip_text(t, part_name, t_lip_in_x(t) - lbl_inset, "right", name_size, name_depth);
        if (revision != "")  lip_text(t, revision, -t_lip_in_x(t) + lbl_inset, "left", rev_size, rev_depth);
        if (id_label)   corner_engrave(str(id), -c, c);       // top-left
        if (type_label) corner_engrave(tray_type(id), c, c);  // top-right
        if (size_label) corner_engrave(t_size_txt(t), 0, t_size_y(t)); // below the tag
    }
}

module lip_tag_graphic(id = tag_ids[0]) {
    // dark tag layer, Z from -tag_embed to tag_raise_h, centred on the plate.
    // Uncolored: the caller applies color(), which is what keeps it a
    // separate 3MF object under lazy union (see apriltag_corner_mount.scad).
    translate([0, 0, -tag_embed])
        april_tag_pattern(id = id, edge = t_tag(tray_type(id)), thickness = 0,
                          raise_h = tag_raise_h + tag_embed);
}

module orient(t) {
    // print placement for the children, a tag of tray type t. On its +X
    // edge (on_edge(t)): rotate 90 deg about Y (the +X edge face turns to
    // -Z, the top face to +X), lift that face onto Z = 0, and centre the
    // rotated footprint on X = 0. On the lip (other sided(t)): rotate -90
    // deg about X (the lip's outer +Y face turns to -Z, the top face to
    // +Y), lift that face onto Z = 0, and centre on Y = 0. Flat: lift the
    // underside onto Z = 0.
    w = t_w(t);
    if (on_edge(t))
        translate([-(z_lo + z_hi) / 2, 0, w / 2]) rotate([0, 90, 0]) children();
    else if (sided(t))
        translate([0, -(z_lo + z_hi) / 2, w / 2]) rotate([-90, 0, 0]) children();
    else
        translate([0, 0, plate_thk]) children(); // flat: underside on Z = 0, level with the sided tags
}

// ---------------------------------------------------------------------------

// Layout loop stays here at the top level, not in a module: every colored
// statement inside a top-level for() is its own lazy-union 3MF object, which
// scad_to_3mf.py then pairs back up into one Orca object per tag.
for (i = [0 : n_tags - 1]) {
    if (part != "graphic")
        translate(slot(i)) color(body_color) orient(tray_type(tag_ids[i])) lip_tag_body(tag_ids[i]);
    if (part != "body")
        translate(slot(i)) color(tag_pattern_color) orient(tray_type(tag_ids[i])) lip_tag_graphic(tag_ids[i]);
}
