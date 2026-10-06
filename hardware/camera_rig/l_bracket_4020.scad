/* ---------------------------------------------------------------------------
   90-degree L bracket: 40x40 extrusion  <->  20x20 extrusion

   The 40-leg lies flat on the 40x40 profile face (mating face = Z0, pointing
   down).  The 20-leg stands vertically against the 20x20 profile face
   (mating face = X0, pointing -X).

   Ridges: the 40-leg's runs across the leg (along Y), centred on the M8 hole,
   so the 40x40 bar runs left-right under the bracket.  The 20-leg's runs up
   the leg (along Z), along the 20x20 bar's axis.

   Set `copies` under [Build Plate] to lay out that many brackets in a grid,
   centred on the origin.  copies = 1 renders the single part at the origin.

   The part name and [Revision] stamp are engraved into the 40-leg top
   face, one each side of the M8 hole (name +Y, revision -Y), both reading
   along +X; that face points up in the print orientation.

   `bracket_4020_bolted()` adds this bracket's own two joining bolts (from
   `t_slot_bolt.scad`): M6 through the 40-leg (note the hole is still sized
   `m8_dia` — that wasn't revisited when the rest of the rig standardized on
   M6; the bolt here is M6, not M8), M5 through the 20-leg, each sized so
   its head lands flush on the leg's outer face (shaft_length = leg
   thickness + that profile's T-slot lip depth, no extra margin). Named
   `bracket_4020()` rather than plain `bracket()` so it can live in the
   same file/namespace as `l_bracket_4040.scad`'s own bracket module
   without colliding.

   REV 1.3: part name (`part_name`, the file name without .scad) engraved
     into the 40-leg top face beside the M8 hole, +Y side ([Label] group).
     Revision stamp moved to the matching -Y side, reading along +X like
     the name; `rev_x` replaced by the derived `label_x`/`label_y`.
   REV 1.2: bracket()/bracket_bolted() renamed to bracket_4020()/
     bracket_4020_bolted() so this file can be `use`d alongside
     l_bracket_4040.scad from one assembly file; bolt color now the shared
     `bolt_color` variable.
   REV 1.1: added bracket_bolted() — the two joining bolts now live here
     instead of being re-derived in every assembly file that places this
     bracket.
   REV 1.0:
     - increase thickness of 20 and 40mm plates to better work with hardware
     - add cutout under 20mm ridge to accomodate t-nuts
   --------------------------------------------------------------------------- */

use <../libraries/t_slot_bolt.scad>
include <../libraries/BOSL2/std.scad> // t_slot_bolt() calls BOSL2's screw(); `use` alone
                          // wouldn't run t_slot_bolt.scad's own top-level
                          // include, so its special variables never init

/* [Revision] */
revision  = "RV0.2"; // revision stamp, engraved in the 40-leg top face ("" = none)
rev_size  = 5;       // text cap height, mm  [2:0.5:12]
rev_depth = 1.2;     // how far the text is inset below the surface, mm  [0.4:0.1:2]

/* [Label] */
part_name  = "l_bracket_4020"; // file name without .scad, engraved in the 40-leg top face, +Y of the M8 hole ("" = none)
name_size  = 3.5; // text cap height, mm  [2:0.5:6]
name_depth = 0.6; // how far the text is inset below the surface, mm  [0.4:0.1:1.5]

/* [Plates] */
w40    = 40;   // 40-leg width  (matches 40x40 face)
len40  = 45;   // 40-leg length, measured from the corner (X=0)
thk40  = 8;    // 40-leg plate thickness

w20    = 20;   // 20-leg width  (matches 20x20 face)
len20  = 38;   // 20-leg length, measured from the corner (Z=0)
thk20  = 7;    // 20-leg plate thickness

fillet_r = 3;  // inside-corner fillet radius
corner_r = 5;  // rounding on the free-end corners of both legs

/* [Ridges] */
ridge40_w     = 7.8;  // slightly under the 8 mm slot of the 40-series profile
ridge40_h     = 3;    // how far it drops into the slot
ridge20_w     = 6.0;  // 6 mm slot of the 20-series profile
ridge20_h     = 3;
ridge_draft   = 0.4;  // per-side taper at the tip: lead-in + printability
ridge40_len   = w40;  // spans the leg width; shorten to pull it in from the edges
ridge20_inset = 0;    // pull the 20-leg ridge back from the corner, if needed
ridge20_cut   = 20;   // relief cut in the 20-leg ridge, centred on the M5 hole (0 = none)
ridge20_cut_r = 1.5;    // transition curve at each end of the relief: run along Z (0 = square step)

/* [Fasteners] */
m8_dia     = 9.0;   // M8 clearance (normal fit)
m8_x       = 25;    // hole centre, from the corner along X
m5_dia     = 5.5;   // M5 clearance (normal fit)
m5_z       = 24;    // hole centre, from the corner along Z
hole_cham  = 1.0;   // 45-deg relief at the entry face, 0 to disable

lip_depth_40    = 3;    // 40x40 T-slot lip depth (see t_slot_40x40.scad's profile)
lip_depth_20    = 1.8;  // 20x20 T-slot lip depth (see t_slot_20x20.scad's header)
foot_thk_ref_40 = 2.6;  // must match t_slot_bolt.scad's foot_thk_40
foot_thk_ref_20 = 1.5;  // must match t_slot_bolt.scad's foot_thk_20
bolt_color      = "DarkSlateGray"; // color for all bolt standins

/* [Build Plate] */
copies       = 1;   // how many brackets to lay out  [1:200]
plate_gap    = 5;   // clear space between neighbours, mm
plate_cols   = 0;   // columns across X; 0 = auto (near-square grid)

/* [Render] */
$fn = $preview ? 32 : 96;
eps = 0.01;

/* [Hidden] */
// name and revision centres on the 40-leg top face: X midway along its flat
// run (corner to the free-end rounding), Y midway between the M8 hole's
// chamfer edge and the leg's side edge (+Y name, -Y revision)
label_x = (len40 - corner_r) / 2;
label_y = (m8_dia / 2 + hole_cham + w40 / 2) / 2;
// bracket footprint: X runs -ridge20_h .. len40, Y is centred on the 40-leg width
part_dx   = len40 + ridge20_h;
part_dy   = w40;
grid_cols = plate_cols > 0 ? plate_cols : ceil(sqrt(copies));
grid_rows = ceil(copies / grid_cols);
pitch_x   = part_dx + plate_gap;
pitch_y   = part_dy + plate_gap;

// ---------------------------------------------------------------------------

module leg40_profile() {
    // plan view (XY): square at the corner end, rounded at the free end
    hull() {
        translate([0, -w40 / 2]) square([eps, w40]);
        translate([len40 - corner_r,  w40 / 2 - corner_r]) circle(corner_r);
        translate([len40 - corner_r, -w40 / 2 + corner_r]) circle(corner_r);
    }
}

module leg20_profile() {
    // face view (YZ): square at the corner end, rounded at the free end
    hull() {
        translate([-w20 / 2, 0]) square([w20, eps]);
        translate([-w20 / 2 + corner_r, len20 - corner_r]) circle(corner_r);
        translate([ w20 / 2 - corner_r, len20 - corner_r]) circle(corner_r);
    }
}

module ridge_along_y(len, w, h, xc) {
    // grows downward from Z=0, running along Y, centred on X=xc
    wt = w - 2 * ridge_draft;
    hull() {
        translate([xc - w  / 2, -len / 2, -eps]) cube([w,  len, eps]);
        translate([xc - wt / 2, -len / 2, -h  ]) cube([wt, len, eps]);
    }
}

module ridge_along_z(len, w, h, z0) {
    // grows in -X from X=0, centred on Y
    wt = w - 2 * ridge_draft;
    hull() {
        translate([-eps, -w  / 2, z0]) cube([eps, w,  len]);
        translate([-h,   -wt / 2, z0]) cube([eps, wt, len]);
    }
}

module inner_fillet() {
    // square-minus-cylinder cross-section in XZ, extruded across the 20-leg
    translate([0, w20 / 2, 0]) rotate([90, 0, 0]) linear_extrude(w20)
        difference() {
            translate([thk20, thk40]) square(fillet_r);
            translate([thk20 + fillet_r, thk40 + fillet_r]) circle(fillet_r);
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
    // engraved into the 40-leg top face, -Y of the M8 hole, reading along +X
    // opposite the part name; overshoots the face by eps for a clean difference
    translate([label_x, -label_y, thk40 - rev_depth])
        linear_extrude(rev_depth + eps)
            text(revision, size = rev_size,
                 halign = "center", valign = "center");
}

module name_label() {
    // engraved into the 40-leg top face, +Y of the M8 hole, reading along +X
    translate([label_x, label_y, thk40 - name_depth])
        linear_extrude(name_depth + eps)
            text(part_name, size = name_size, halign = "center", valign = "center");
}

module ridge20_cove(zc, run) {
    // 2D (X,Z): quarter-ellipse of ridge material blending the relief floor at
    // X=0 out to full ridge depth at X=-ridge20_h, tangent to the floor at Z=zc.
    // run > 0 puts the material below zc, run < 0 above it.
    difference() {
        translate([-ridge20_h, min(zc, zc - run)]) square([ridge20_h, abs(run)]);
        translate([-ridge20_h, zc]) scale([ridge20_h, abs(run)]) circle(1);
    }
}

module ridge20_relief() {
    // subtract solid: clears the ridge between the cut ends, then curves back
    // out to full depth.  Stops at X=0, so the 20-leg plate face is untouched.
    z0 = m5_z - ridge20_cut / 2;
    z1 = m5_z + ridge20_cut / 2;
    r  = ridge20_cut_r;
    wy = ridge20_w + 2;          // overshoot the ridge width on both sides
    translate([0, wy / 2, 0]) rotate([90, 0, 0]) linear_extrude(wy)
        difference() {
            translate([-ridge20_h - eps, z0 - r])
                square([ridge20_h + eps, ridge20_cut + 2 * r]);
            if (r > 0) {
                ridge20_cove(z0,  r);
                ridge20_cove(z1, -r);
            }
        }
}

module bracket_4020() {
    difference() {
        union() {
            // 40-leg
            linear_extrude(thk40) leg40_profile();
            // 20-leg  (local x -> Y, local y -> Z, extrude -> +X)
            rotate([90, 0, 90]) linear_extrude(thk20) leg20_profile();
            inner_fillet();
            // keying ridges
            ridge_along_y(ridge40_len, ridge40_w, ridge40_h, m8_x);
            ridge_along_z(len20 - ridge20_inset, ridge20_w, ridge20_h, ridge20_inset);
        }

        // M8 through the 40-leg and its ridge, chamfer on the top (bolt head) face
        translate([m8_x, 0, thk40]) mirror([0, 0, 1])
            chamfered_hole(m8_dia, thk40 + ridge40_h + 1, hole_cham);

        // M5 through the 20-leg and its ridge, chamfer on the outer face
        translate([thk20, 0, m5_z]) rotate([0, -90, 0])
            chamfered_hole(m5_dia, thk20 + ridge20_h + 1, hole_cham);

        // relief: clear the 20-leg ridge either side of the M5 hole
        if (ridge20_cut > 0) ridge20_relief();

        // revision stamp
        if (revision != "") revision_stamp();
        if (part_name != "") name_label();
    }
}

module bracket_4020_bolted() {
    // assembly view: bracket_4020() plus its own two joining bolts, feet
    // seated lip_depth+foot_thk_ref under each mating face's T-slot lip,
    // heads landing flush (shaft_length = leg thickness + that lip depth).
    bracket_4020();

    color(bolt_color)
        translate([m8_x, 0, -(lip_depth_40 + foot_thk_ref_40)])
            t_slot_bolt(screw_size = "M6", shaft_length = thk40 + lip_depth_40);

    color(bolt_color)
        translate([-(lip_depth_20 + foot_thk_ref_20), 0, m5_z])
            rotate([90, 0, 90])
                t_slot_bolt(screw_size = "M5", profile = 20,
                            shaft_length = thk20 + lip_depth_20);
}

module plate(n) {
    // grid is centred on the origin; index 0 is the -X/-Y corner
    x0 = -(grid_cols * pitch_x - plate_gap) / 2 + ridge20_h;
    y0 = -(grid_rows * pitch_y - plate_gap) / 2 + part_dy / 2;
    for (i = [0 : n - 1])
        translate([x0 + (i % grid_cols)     * pitch_x,
                   y0 + floor(i / grid_cols) * pitch_y,
                   0])
            bracket_4020();
}

if (copies > 1) plate(copies); else bracket_4020();
