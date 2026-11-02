/* ---------------------------------------------------------------------------
   AprilTag tray tag -- one 36h11 tag on a plate for each growth tray.
   Six styles, chosen once for the whole layout with `tag_style`; each
   tray type has a default (tray_tags.py). Each style has its own tag
   size: the largest its plate allows, except the tab style, where the
   space at the tray's side sets it, and "lip_round", which keeps version
   2's 40 mm (43.6 mm would fit, set by the lip).
     - "lip_round" (4x5): version 2's 4x5 design from
       tray_tags_alternative/ (REV 1.19): a 60.5 mm square plate with
       9.33 mm corners copied from a physical part
       (tray_tags_alternative/tag_outline_61.scad, derived radius), a
       40 mm tag and the lip described under "lip" below. Same as "lip"
       but for the plate and tag size.
     - "tab": 20 mm tag (reference/trays.md). The plate sits on the
       tray's rim, with a tab hanging 90 deg over the tray's edge to
       locate it. The 4x5 default until REV 1.19.
     - "bolt": a tab in the plate's own plane, `bolt_tab_len` past the
       plate's -Y edge, with a round end and an M8 clearance hole
       concentric with it. Centred on X, or with `bolt_tab_flush` flush
       with the plate's +X edge -- the face that rests on the bed when
       `on_side` is set, so the tab prints on the bed instead of hanging
       above it. All four plate corners are rounded and the
       tab-to-plate corners are filleted (`bolt_tab_fillet`).
     - "lip" (2x2) and "lip_bolt" (1x1): version 2's designs from
       tray_tags_alternative/ (REV 1.18), sized to those trays: a 61 mm
       square plate, 3 mm corners, 42 mm tag, and a lip along the +Y
       edge, `lip_h` above the top face and `lip_thk` thick, its outer
       face flush with the plate's +Y edge (the band of the outline
       within `lip_thk` of that edge, so its ends follow the corners).
       "lip_bolt" adds the bolt style's tab, flush with the +X edge. The
       42 mm tag is limited by the lip: its one-bit quiet zone must stay
       clear of it (assert).
     - "disc" (black_tray): version 2's 51 mm disc with a 30 mm tag, no
       tab (REV 1.16, 1.18). Always printed flat, whatever `on_side`
       says. The one-bit white square's corners reach 26.5 mm from the
       centre, so the disc cuts about 1 mm off each; along the edges the
       quiet zone is a full bit (3.75 mm, assert). Version 2 called 30 mm
       a trial, still to be tested for detection.

   Plate size: `pw` wide (X) and `pd` deep (Y). Tab and bolt styles: the
   width is the tag plus `tag_border` each side; the depth is
   `plate_depth`, set by the space at the tray's side, with the tab inside
   it (REV 1.17). The quiet zone above and below the tag is what the
   depth leaves, at least one bit. Lip styles: `lip_plate_w` square
   ("lip_round": `round_plate_w`). Disc: `disc_dia` across.

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

   ID label: small, engraved into the top face in the left side border
   (-X), turned 90 deg to run along Y and reading from the bottom up,
   its end `id_inset` in from the +Y edge, centred across the border
   (REV 1.17). Lip styles: the id and type are centred on the top
   corners' diagonals, halfway between the black border's corner and the
   rounded edge (version 2). Disc style: the id is centred above the
   tag and the tray type below it, each halfway between the white
   square's edge and the disc's edge. Lip and disc styles also engrave
   the tag's size ("42.0 x 42.0 mm", `size_label`) in the quiet zone
   below the tag: the size the model draws; measure the print.

   Part name and revision: engraved into the plate's underside, the face
   opposite the tag, as two lines (name above revision, viewed from below),
   mirrored so they read correctly from below. Centred in X; in Y, centred
   on the underside's flat area (tab style: from the tab's inner face to
   the +Y edge; bolt style: the whole plate), so the flat -Y outer face
   and the bolt tab stay unmarked. Lip styles: on the lip's inner face
   instead, one line, revision left and part name right, `lip_text_inset`
   in from its ends. Disc: the revision alone, centred on the underside
   (version 2).

   Tray type label: the tray type for the id (`tray_type()`), engraved in
   the right side border (+X), mirroring the ID label (reading from the
   top down, starting `id_inset` in from the +Y edge) and in the same
   font, size and depth. Id ranges (Aaron, REV 1.13, 1.16):
   1-75 "4x5", 76-150 "2x2", 151-225 "1x1", 226-250 "black_tray",
   251-299 "OTHER". Ids above 299
   fail the id assert: 300-449 are the calibration sheets and 450-499 the
   corner tags (PLAN.md's tag ID allocation, src/npec_rig/tags.py).

   Open assumption, not yet measured: `tag_border` (quiet-zone margin) and
   `tag_embed` are starting values, same status as in
   `apriltag_corner_mount.scad`.

   REV 1.20: tray type "4x4" renamed "2x2" (ids 76-150 unchanged): these
     trays have 2 x 2 cells, 4 plants; "4x4" was a mislabel (Aaron,
     2026-10-29, #327). The engraved type label changes with it.
     Geometry unchanged.
   REV 1.19: style "lip_round", version 2's 4x5 design (60.5 mm plate,
     9.33 mm corners, 40 mm tag), now the 4x5 default in place of "tab"
     (Aaron, 2026-10-21). Its exports match version 2's RV2.1 4x5
     exports except for the revision. The "tab" style is kept unchanged.
     Leftover overrides at the end of the file removed (they set the
     Customizer default to "lip"). Other styles' geometry unchanged, and
     their exports stay at RV1.18: rebuilding them changes only the
     revision stamp.
   REV 1.18: styles "lip" (4x4) and "lip_bolt" (1x1) from
     tray_tags_alternative/ (version 2), and the disc's tag is version
     2's 30 mm (`disc_tag_size`) with its clipped quiet-zone corners and
     labels (Aaron: version 2's sizes are fitted to the trays; only 4x5
     differs). Each style has its own tag size (`ts`); `tag_size` is now
     the tab and bolt styles' only. Lip style on the side stands on the
     lip's outer face; lip_bolt on its +X edge, as bolt. Flat layouts now
     rest on Z = 0 (they sat with the top face at Z = 0). Tab and bolt
     geometry unchanged.
   REV 1.17: plate depth (Y, tab included) set by `plate_depth`, 26 mm,
     instead of the tag plus two borders (Aaron, 2026-10-16: the tag may
     not reach more than 27 mm in from the tray's side; measured
     clearance 27.39 mm, 26 mm for margin). Width unchanged at 32 mm.
     With a 20 mm tag that leaves a 3 mm (1.2 bit) quiet zone above and
     below it (assert: at least one bit). The id and type labels move
     out of the quiet zone into the 6 mm side borders, turned 90 deg.
     Applies to all three styles.
   REV 1.16: style "disc" and tray type "black_tray", ids 226-250, from
     tray_tags_alternative/ (version 2's black_tray design); "OTHER" is
     now 251-299. `disc_dia` default 51 mm as in version 2. Version 2's
     30 mm trial tag clipped the quiet zone's corners; here the tag is
     `tag_size` (20 mm) and the whole quiet zone must fit the disc
     (assert). Tab and bolt geometry unchanged.
   REV 1.15: `tag_size` 30 -> 20 mm (Aaron, 2026-10-16;
     reference/trays.md, final tray tags about 20 mm). Plate 42 -> 32 mm
     square with the 6 mm border unchanged. Geometry otherwise unchanged.
   REV 1.14: part name (`part_name`, the file name without .scad) and
     revision engraved into the plate's underside, mirrored, two lines
     ([Label] group). The revision moves there from the tab's inner face
     (tab style) and the bolt tab's top face (bolt style); `tab_text()`,
     `bolt_rev_stamp()`, `label_z`, `rev_x` and `bolt_rev_y` removed.
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
tag_style = "lip_round"; // ["lip_round", "tab", "bolt", "lip", "lip_bolt", "disc"]
// lip_round: lip with 9.33 mm corners, 40 mm tag (4x5); tab: 90 deg tab over the tray edge; bolt: in-plane tab with an M8 hole; lip: square plate with a lip (2x2); lip_bolt: lip plus the M8 tab (1x1); disc: round plate, always flat (black_tray)

/* [Tag] */
tag_ids       = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]; // 36h11 ids, one tray tag each, laid out in this order -- tray id allocation not yet confirmed (PLAN.md open questions)
tag_size      = 20;    // 36h11 tag width, tab and bolt styles, mm -- 4x5 tray tags (reference/trays.md)
tag_border    = 6;     // side border, X, tab and bolt styles, mm -- informed default, not yet measured [4:0.1:25]
tag_plate_thk = 3;     // total plate thickness, mm  [2:0.5:6]
tag_raise_h   = 0.6;   // dark tag layer height above the plate's top face, mm  [0.2:0.1:2]
tag_embed     = 0.2;   // how far the dark layer sinks into the plate so the parts overlap, mm  [0:0.05:1]
plate_depth   = 26;    // plate depth, Y, tab included, tab and bolt styles, mm -- tray side clearance measured 27.39 mm (Aaron), 26 for margin  [20:0.5:60]
corner_r      = 3;     // rounding on the plate's vertical corners, tab and bolt styles (tab: +Y corners only, the -Y edge stays square), mm  [0:0.5:10]

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

/* [Lip] */
lip_plate_w    = 61;  // plate side, X and Y, lip and lip_bolt styles, mm -- version 2, sized to the 2x2 and 1x1 trays  [40:0.5:100]
lip_corner_r   = 3;   // rounding on the plate's four vertical corners, mm  [0:0.5:20]
lip_tag_size   = 42;  // 36h11 tag width, lip and lip_bolt styles, mm -- version 2  [20:0.5:44]
lip_h          = 5;   // how far the lip stands above the plate's top face, mm  [2:0.5:30]
lip_thk        = 3;   // lip thickness, Y, mm  [1:0.5:6]
lip_text_size  = 3;   // revision and part name on the lip's inner face, cap height, mm  [1:0.25:4]
lip_text_depth = 0.6; // how far that text is inset into the lip, mm  [0.2:0.1:1.5]
lip_text_inset = 3;   // revision's and part name's distance in from the ends of the lip's inner face, mm  [0:0.5:10]

/* [Lip Round] */
round_plate_w  = 60.5; // plate side, X and Y, lip_round style, mm -- version 2's 4x5: the physical part's 61, less 0.5  [40:0.5:100]
round_corner_r = 9.33; // rounding on the plate's four vertical corners, mm -- derived from the physical part, see header  [0:0.01:20]
round_tag_size = 40;   // 36h11 tag width, lip_round style, mm -- version 2; above 43.5 the quiet zone runs under the lip (assert)  [20:0.5:43.5]

/* [Disc] */
disc_dia      = 51; // disc diameter, mm -- version 2's black_tray disc  [30:0.5:100]
disc_tag_size = 30; // 36h11 tag width, disc style, mm -- version 2; the disc clips the quiet zone's corners (header)  [20:0.5:36]

/* [ID Label] */
id_label  = true;                      // engrave each tag's id on the top face, in the left side border (lip styles: top-left corner, disc: above the tag)
id_size   = 2.5;                       // label text cap height, mm  [1.5:0.5:6]
id_inset  = 2;                         // label's end, distance in from the plate's +Y edge, mm  [0.5:0.25:5]
id_depth  = 0.6;                       // how far the label is inset into the top face, mm  [0.2:0.1:2]
id_font   = "Liberation Sans:style=Bold";
type_label = true;                     // engrave each tag's tray type (4x5, 2x2, 1x1, black_tray, OTHER) in the right side border (lip styles: top-right corner, disc: below the tag), same size and depth as the id
size_label = true;                     // lip styles and disc: engrave the tag's size ("42.0 x 42.0 mm") in the quiet zone below the tag

/* [Label] */
part_name  = "apriltag_tray_tag"; // file name without .scad, engraved in the plate underside above the revision ("" = none)
name_size  = 2.5; // text cap height, mm  [1.5:0.5:4]
name_depth = 0.6; // how far the text is inset into the underside, mm  [0.2:0.1:1.5]
label_gap  = 1.5; // space between the name and the revision lines, mm  [0.5:0.25:4]

/* [Colors] */
body_color        = "White"; // also the tag's background and quiet zone
tag_pattern_color = "Black"; // the tag's dark modules

/* [Render Select] */
part = "assembly"; // what to render  ["assembly","body","graphic"]

/* [Build Plate] */
on_side    = true; // stand each tag on an edge: tab, bolt and lip_bolt on the +X edge, lip and lip_round on the lip's outer face; disc always lies flat
plate_gap  = 2;   // clear space between neighbouring tags, flat layout, mm  [0:0.5:50]
side_gap   = 5;   // clear space between neighbouring tags, side layout, mm  [0.2:0.1:10]
side_plate_gap = 5; // space between the two plates of a nested pair, side layout, mm  [0.2:0.1:10]
plate_cols = 0;   // tags per row; 0 = auto (block closest to square)  [0:1:20]

/* [Revision] */
revision  = "RV1.20"; // revision stamp, engraved in the plate underside below the part name ("" = none)
rev_size  = 3;       // text cap height, mm  [2:0.5:8]
rev_depth = 1.0;     // how far the text is inset below the surface, mm  [0.4:0.1:2]

/* [Render] */
$fn = $preview ? 32 : 96;
eps = 0.01;

/* [Hidden] */
tabbed   = tag_style == "tab";
bolted   = tag_style == "bolt";
rounded  = tag_style == "lip_round";
lipped   = tag_style == "lip" || tag_style == "lip_bolt" || rounded;
disc     = tag_style == "disc";
has_bolt = bolted || tag_style == "lip_bolt";

// tag and plate by style (header, Plate size)
ts = rounded ? round_tag_size : lipped ? lip_tag_size : disc ? disc_tag_size : tag_size; // tag width, black border
pw = rounded ? round_plate_w : lipped ? lip_plate_w : disc ? disc_dia : tag_size + 2 * tag_border; // plate width, X (disc: diameter)
pd = rounded ? round_plate_w : lipped ? lip_plate_w : disc ? disc_dia : plate_depth;               // plate depth, Y, tab included
wh = ts / 2 + ts / 8;     // half-width of the one-bit white square (36h11 is 8 bits across its black border)
qy = (pd - ts) / 2;       // quiet zone above and below the tag, Y
cr = min(rounded ? round_corner_r : lipped ? lip_corner_r : corner_r, pw / 2, pd / 2); // clamp: rounding can't exceed half the plate
tr = min(tab_r, tab_h, pw / 2); // clamp: rounding can't exceed the tab's height or half its width

sided    = on_side && !disc;          // discs always lie flat
side_lip = sided && lipped && !has_bolt; // lip styles without a bolt tab stand on the lip's outer face; other sided styles on the +X edge

// side labels (tab, bolt), X: centred across the side border
side_lx = pw / 2 - tag_border / 2;
// disc labels, Y: halfway between the white square's edge and the disc's edge
disc_ly = (wh + disc_dia / 2) / 2;
// lip corner labels: on the top corners' diagonals, halfway between the
// black border's corner and the rounded edge. corner_h is the outline's
// distance from the centre along the diagonal, as a half-width.
flat_e   = pw / 2 - cr;                   // where the straight edges end, from the centre
corner_h = flat_e + cr / sqrt(2);
id_c     = (ts / 2 + corner_h) / 2;
// the lip's inner face, Y, and its ends, X: where the outline crosses it
lip_in_y = pd / 2 - lip_thk;
lip_in_x = lip_in_y <= flat_e ? pw / 2 : flat_e + sqrt(cr * cr - (lip_in_y - flat_e) ^ 2);
// lip text baseline, Z: the line (cap height plus 0.3 of it for
// descenders) centred on the lip face's height
lip_bz   = lip_h / 2 - 1.3 * lip_text_size / 2 + 0.3 * lip_text_size;
// size label: centre Y in the middle of the one-bit quiet zone below the tag
size_y   = -(ts / 2 + ts / 16);
function fmt1(x) = let(r = round(x * 10)) str(floor(r / 10), ".", r % 10); // x to 0.1
size_txt = str(fmt1(ts), " x ", fmt1(ts), " mm");

bolt_tab_x = bolt_tab_flush ? pw / 2 - bolt_tab_w / 2 : 0; // tab centre line, X
bolt_y   = -pd / 2 - bolt_tab_len + bolt_tab_w / 2; // hole and round-end centre, Y
tab_ext  = has_bolt ? bolt_tab_len : 0; // how far the part reaches past the plate's -Y edge
// underside labels, tab and bolt: the block (name, gap, revision) is
// centred in Y on the underside's flat area -- tab style from the tab's
// inner face to the +Y edge, bolt style the whole plate. name_size * 1.3
// allows for descenders.
lbl_cy  = tabbed ? tab_thk / 2 : 0;
lbl_h   = (part_name == "" ? 0 : 1.3 * name_size + label_gap) + (revision == "" ? 0 : rev_size);
name_ly = lbl_cy + lbl_h / 2;                 // name line top, Y
rev_ly  = lbl_cy - lbl_h / 2;                 // revision line bottom, Y

// tray type for a tag id; the id ranges are the allocation (header)
function tray_type(id) = id <= 75  ? "4x5"
                       : id <= 150 ? "2x2"
                       : id <= 225 ? "1x1"
                       : id <= 250 ? "black_tray"
                       : "OTHER";

assert(tabbed || bolted || lipped || disc,
       "tag_style must be \"lip_round\", \"tab\", \"bolt\", \"lip\", \"lip_bolt\" or \"disc\"");
assert(len(tag_ids) > 0, "tag_ids must list at least one id");
assert(min(tag_ids) >= 1 && max(tag_ids) <= 299,
       "tag_ids must be within 1-299, the tray tag ids (tray_type()); 300-449 are calibration sheets");
assert(id_depth + tag_embed < tag_plate_thk, "id engraving reaches the tag layer");
// tab and bolt
assert(!(tabbed || bolted) || qy >= ts / 8, "plate_depth leaves under one bit of quiet zone above and below the tag");
assert(!(tabbed || bolted) || id_size < tag_border - 1, "side border too narrow for the id and type labels");
assert(!tabbed || tab_thk < pd / 2, "tab too thick for the plate");
assert(!(tabbed || bolted) || rev_depth + tag_embed < tag_plate_thk, "revision engraving reaches the tag layer");
assert(!(tabbed || bolted) || name_depth + tag_embed < tag_plate_thk, "name engraving reaches the tag layer");
assert(!(tabbed || bolted) || lbl_h < pd - 2 * (tabbed ? tab_thk : 0), "name and revision do not fit the underside");
// lip and lip_bolt
assert(!lipped || wh <= corner_h, "tag's quiet zone runs past the rounded corners");
assert(!lipped || wh <= lip_in_y, "tag's quiet zone runs under the lip");
assert(!lipped || 1.3 * lip_text_size < lip_h, "revision and part name too tall for the lip's inner face");
assert(!lipped || lip_text_depth < lip_thk, "lip engraving deeper than the lip");
// disc: the quiet zone's corners may be clipped (header); its edges may not
assert(!disc || wh <= disc_dia / 2, "tag's quiet zone runs past the disc's edge");
assert(!disc || disc_dia / 2 - wh > id_size + 1, "no room for the id and type labels between the quiet zone and the disc's edge");
assert(!disc || rev_depth + tag_embed < tag_plate_thk, "revision engraving reaches the tag layer");
assert(!(size_label && (lipped || disc)) || id_size < ts / 8, "size label taller than the quiet zone (one bit)");
// bolt tab
assert(!has_bolt || bolt_tab_len >= bolt_tab_w / 2, "bolt tab shorter than its round end");
assert(!has_bolt || bolt_dia < bolt_tab_w - 2, "M8 hole leaves under 1 mm of wall in the bolt tab");
assert(!has_bolt || bolt_tab_w + (lipped ? bolt_tab_fillet + cr : 0) <= pw, "bolt tab wider than the plate");

// full Z extent of the unrotated part: bottom (tab style: tab, others:
// plate) to the top (lip styles: the lip, others: the tag layer)
z_lo = tabbed ? -(tag_plate_thk + tab_h) : -tag_plate_thk;
z_hi = lipped ? max(lip_h, tag_raise_h) : tag_raise_h;

n_tags  = len(tag_ids);
gap     = sided ? side_gap : plate_gap;
// footprint: on the +X edge the part's height becomes X; on the lip it
// becomes Y; flat, the plate plus any bolt tab
part_dx = sided && !side_lip ? z_hi - z_lo : pw;
part_dy = side_lip ? z_hi - z_lo : pd + tab_ext;
tp      = tag_plate_thk + tag_raise_h; // plate plus tag layer, the part's X thickness on the side
nest    = sided && tabbed; // flip-and-raise pairs: tab style on the side only
pitch_x = part_dx + (sided && !side_lip ? side_plate_gap : gap); // bolt styles on the edge: plates side by side
pitch_y = part_dy + gap;

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
        + (side_lip ? 0 : tab_ext / 2), // centre the footprint, tab included, on the cell
    0
];

// ---------------------------------------------------------------------------

module square_profile() {
    // XY plan view, bolt and lip styles: pw x pd, all four corners rounded
    offset(r = cr) offset(delta = -cr) square([pw, pd], center = true);
}

module bolt_profile() {
    // XY plan view, bolt and lip_bolt styles: square_profile() plus the tab
    // off the -Y edge ending in a semicircle around the hole. A flush tab
    // covers the plate's rounded +X/-Y corner, so that edge runs straight
    // from plate to tab.
    // The outer offset pair fillets the concave tab/plate corners
    // (offset(delta=+f) then offset(r=-f) rounds only concave corners).
    offset(r = -bolt_tab_fillet) offset(delta = bolt_tab_fillet)
        union() {
            square_profile();
            hull() {
                translate([bolt_tab_x - bolt_tab_w / 2, -pd / 2 + cr]) square([bolt_tab_w, eps]);
                translate([bolt_tab_x, bolt_y]) circle(d = bolt_tab_w);
            }
        }
}

module lip_profile() {
    // XY plan view: the plate outline within lip_thk of the +Y edge
    intersection() {
        square_profile();
        translate([-pw / 2, lip_in_y]) square([pw, lip_thk]);
    }
}

module lip_text(t, x, halign) {
    // engraved into the lip's inner (-Y) face on the lip text baseline,
    // reading correctly viewed from the tag side (-Y), where +X is to the
    // right. rotate([90, 0, 0]) extrudes toward -Y, so the text starts
    // `lip_text_depth` inside the lip and ends eps past the face.
    translate([x, lip_in_y + lip_text_depth, lip_bz]) rotate([90, 0, 0])
        linear_extrude(lip_text_depth + eps)
            text(t, size = lip_text_size, halign = halign, valign = "baseline");
}

module plate_profile() {
    // XY plan view: pw x pd, rounded at the two +Y corners only. The -Y
    // edge stays square so it is flush with the tab's flat outer face.
    hull() {
        translate([-pw / 2, -pd / 2]) square([pw, eps]);
        translate([-pw / 2 + cr, pd / 2 - cr]) circle(cr);
        translate([ pw / 2 - cr, pd / 2 - cr]) circle(cr);
    }
}

module tab() {
    // XZ profile extruded along +Y from the plate's -Y edge: square at the
    // top (overlapping the plate by eps), rounded at the two bottom corners
    zb = -(tag_plate_thk + tab_h);
    translate([0, -pd / 2 + tab_thk, 0]) rotate([90, 0, 0]) linear_extrude(tab_thk)
        hull() {
            translate([-pw / 2, -tag_plate_thk - eps]) square([pw, eps]);
            translate([-pw / 2 + tr, zb + tr]) circle(tr);
            translate([ pw / 2 - tr, zb + tr]) circle(tr);
        }
}

module underside_text(t, y, valign, size, depth) {
    // engraved up into the plate's underside, mirrored in X so it reads
    // correctly viewed from below, centred on X
    translate([0, y, -tag_plate_thk - eps])
        linear_extrude(depth + eps)
            mirror([1, 0, 0])
                text(t, size = size, halign = "center", valign = valign);
}

module id_engrave(id) {
    // engraved into the top face. Tab and bolt: in the left side border
    // viewed from above, turned to read from the bottom up, ending
    // `id_inset` in from the +Y edge. Lip: top-left corner. Disc: above
    // the tag
    if (disc)
        top_engrave(str(id), 0, disc_ly);
    else if (lipped)
        top_engrave(str(id), -id_c, id_c);
    else
        translate([-side_lx, pd / 2 - id_inset, -id_depth]) rotate(90)
            linear_extrude(id_depth + eps)
                text(str(id), size = id_size, font = id_font, halign = "right", valign = "center");
}

module type_engrave(id) {
    // engraved into the top face, mirroring id_engrave(). Tab and bolt: in
    // the right side border, reading from the top down, starting
    // `id_inset` in from the +Y edge. Lip: top-right corner. Disc: below
    // the tag
    if (disc)
        top_engrave(tray_type(id), 0, -disc_ly);
    else if (lipped)
        top_engrave(tray_type(id), id_c, id_c);
    else
        translate([side_lx, pd / 2 - id_inset, -id_depth]) rotate(-90)
            linear_extrude(id_depth + eps)
                text(tray_type(id), size = id_size, font = id_font, halign = "left", valign = "center");
}

module top_engrave(t, x, y) {
    // engraved into the top face, centred on (x, y)
    translate([x, y, -id_depth])
        linear_extrude(id_depth + eps)
            text(t, size = id_size, font = id_font, halign = "center", valign = "center");
}

module plate_body() {
    // the solid before engraving: plate, plus the tab or the lip
    translate([0, 0, -tag_plate_thk])
        linear_extrude(tag_plate_thk)
            if (tabbed) plate_profile();
            else if (disc) circle(d = disc_dia);
            else if (has_bolt) bolt_profile();
            else square_profile();
    if (tabbed) tab();
    if (lipped)
        translate([0, 0, -tag_plate_thk])
            linear_extrude(tag_plate_thk + lip_h) lip_profile();
}

module tray_tag_body(id = tag_ids[0]) {
    difference() {
        plate_body();

        if (has_bolt)
            translate([bolt_tab_x, bolt_y, -tag_plate_thk - eps])
                cylinder(d = bolt_dia, h = tag_plate_thk + 2 * eps);
        if (tabbed || bolted) {
            if (part_name != "") underside_text(part_name, name_ly, "top", name_size, name_depth);
            if (revision != "")  underside_text(revision, rev_ly, "bottom", rev_size, rev_depth);
        }
        if (lipped) {
            if (part_name != "") lip_text(part_name, lip_in_x - lip_text_inset, "right");
            if (revision != "")  lip_text(revision, -lip_in_x + lip_text_inset, "left");
        }
        if (disc && revision != "") underside_text(revision, 0, "center", rev_size, rev_depth);
        if (id_label)
            id_engrave(id);
        if (type_label)
            type_engrave(id);
        if (size_label && (lipped || disc))
            top_engrave(size_txt, 0, size_y);
    }
}

module tray_tag_graphic(id = tag_ids[0]) {
    // dark tag layer, Z from -tag_embed to tag_raise_h, centred on the plate.
    // Uncolored: the caller applies color(), which is what keeps it a
    // separate 3MF object under lazy union (see apriltag_corner_mount.scad).
    translate([0, 0, -tag_embed])
        april_tag_pattern(id = id, edge = ts, thickness = 0,
                          raise_h = tag_raise_h + tag_embed);
}

module orient(flip = false) {
    // print placement for the children. on_side: rotate 90 deg about Y
    // (the top face turns to +X, the +X edge face to -Z), lift that edge
    // face onto Z = 0, and centre the rotated footprint on X = 0. flip
    // first turns the part 180 deg about its own X axis and shifts it back
    // into the same Z range [z_lo, z_hi], so both versions share a footprint.
    // Lip style on the side instead rotates -90 deg about X (the lip's
    // outer +Y face turns to -Z, the top face to +Y), lifts that face onto
    // Z = 0 and centres on Y = 0. Flat (and discs, always): the lowest
    // face rests on Z = 0.
    if (side_lip)
        translate([0, -(z_lo + z_hi) / 2, pd / 2]) rotate([-90, 0, 0]) children();
    else if (sided)
        translate([-(z_lo + z_hi) / 2, 0, pw / 2]) rotate([0, 90, 0])
            if (flip)
                translate([0, 0, z_lo + z_hi]) rotate([180, 0, 0]) children();
            else
                children();
    else
        translate([0, 0, -z_lo]) children();
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
