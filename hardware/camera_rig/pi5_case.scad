/* ---------------------------------------------------------------------------
   Pi 5 case for the NPEC camera rig, adapted from the raspberry.tips v2.0
   case.

   Case for Raspberry Pi 5 by raspberry.tips, CC BY 4.0
   https://raspberry.tips/en/3d-druck/raspberry-pi-5-case-3d-print

   The original (German) is kept unchanged in reference/raspberry_tips_pi5_case/
   rpi5_case.scad. Check the fit with camera_rig/pi5_case_fit_check.scad.

   Variant A: Pi 5 + official Active Cooler
   Variant B: Pi 5 + AI HAT with heatsink, on its spacers

   From the original header (raspberry.tips v2.0, 2026-08-13): connector
   positions come from RASPBERRY_PI_5_WITH_ACTIVE_COOLER.stl, with the parts
   separated by component analysis and identified by their real dimensions.
   Their v1.0 took the numbers from the official STEP but guessed which part
   was which, and swapped the micro-HDMI and FPC connectors: a bounding box
   says something is there, not what it is. Their v1.2 fixed a mirror: the
   conversion x<-X, y<-Z, z<-Y swaps two axes, which flips handedness. Build
   heights from the official drawings:
     datasheets.raspberrypi.com/rpi5/raspberry-pi-5-mechanical-drawing.pdf
     datasheets.raspberrypi.com/cooling/raspberry-pi-active-cooler-mechanical-drawing.pdf
   OpenSCAD 2021.01 or newer. All dimensions in mm.

   COORDINATES: origin = outer corner of the tub, z = 0 is the outside of the
   tub floor. The PCB corner sits at (pcb_x0, pcb_y0).
     x        = long direction (85 mm)
     y        = short direction (56 mm)
     x = 85   -> Ethernet + 4x USB
     y = 0    -> USB-C, micro-HDMI, camera/display FPC
     y = 56   -> GPIO header, stays closed
     x = 0    -> microSD under the PCB, PCIe FPC on top of it
   (The original header puts the PCIe FPC on the y = 56 side; it is at x = 0.)

   REV 13 (RV0.13): part name and revision moved from the lid to the outside
     of the y = 0 (USB-C) wall, between the port recess and the x = 85 lug;
     the lid vents now also cover the strip the labels used. GPIO wall
     honeycomb raised so every hole's bottom is vent_keep (3 mm) above the
     mounting fillet; before, the lowest row reached into the fillet.
   REV 12 (RV0.12): lid vents laid out for the usual mounting (USB-C side
     down, GPIO wall on top): a honeycomb over the whole heatsink area (the
     PCB except the Ethernet/USB-A block), whole hexagons only, with 3 mm
     kept solid around the camera opening, screw ears and labels and a
     5 mm solid border. Part name and revision engraved over the USB-C
     ports. Old fixed 48 x 36 grille and cooler-centre values removed.
   REV 11 (RV0.11): camera cable opening in the lid over both FPC connectors
     (official STEP footprint plus 1.5 mm), open through the lid's y = 0
     edge and skirt, so the lid is a U and comes off over the cables
     ([Camera cables] group). Tub not cut.
   REV 10 (RV0.10): mounting holes moved 1 mm further out from the GPIO
     wall (5.5 -> 6.5 mm) for heads or washers up to 12 mm (mount_head
     10 -> 12); the flat seat cut into the fillet grows to 13 mm.
   REV 9 (RV0.9): x = 85 end mounting hole moved 87.75 -> 83.75, so the
     flange stops where that corner's curve starts. Holes 71.25 mm apart.
   REV 8 (RV0.8): stronger base. The two mounting ears are one 5 mm flange
     along the GPIO side, following the rounded corner at the x = 85 end
     (hole moved 88 -> 87.75 so it ends flush), with a 5 mm 45 degree
     fillet to the wall, cut away around the bolt heads. Floor 2 -> 3 mm.
     Wall honeycomb starts above the fillet. Port walls not thickened: the
     plugs must still reach their sockets through them.
   REV 7 (RV0.7): M5 mounting ears on the base along the y = 56 (GPIO) side,
     opposite the USB-C and HDMI ports, for bolts into T-slot nuts. Holes at
     x = 12.5 (just past the lid lug) and x = 88 (flush with the x = 85
     end), 75.5 mm apart, 4 mm thick, flush with the bottom ([Mounting]).
   REV 6 (RV0.6): AI HAT headroom. Variant B height is now the measured
     hat_h = 26.5 mm (Pi PCB top to heatsink top) instead of the original's
     M.2 HAT estimate (16 mm spacers + 1.4 mm PCB + 3 mm SSD = 20.4 mm).
     top_clearance 1.5 -> 3.0 mm, for both variants. Tub 7.6 mm taller.
   REV 5 (RV0.5): revision stamp engraved in the lid top face, beside the
     grille ([Revision] group).
   REV 4: lid held by two M3 screws into captive nuts. Lugs on two diagonal
     outside corners (x = 0 / y = 56, x = 85 / y = 0), each with a hex
     pocket and a slot out of its outer side to slide the nut in; matching
     ears with clearance holes on the lid. Snap fit removed.
   REV 3: no lid label. Removed the engraved text and the calibration
     piece's text test strip.
   REV 2: translated to English: names, part values, comments and echo text.
     Geometry unchanged (every part, both variants, all three post types
     render to identical STLs). Dropped radius_aussen, which nothing used.
     Fixed two wrong comments from the original: the PCIe FPC side, and
     the port gauge cuts the y = 0 wall, not y = 56.
   REV 1: through-bolts and SD finger access. New post_type "through"
     (default): M2.5 clearance hole up through each post, pan-head recess
     in the floor, and a 9 mm foot so the post is not hanging on a thin
     ring of floor. Bolt from below into a nut, or into the AI HAT's
     threaded risers. New sd_grip (default on): wide notch in the x = 0
     wall up to the PCB top and a scoop through the floor under the card,
     replacing the original card-sized slot.
   REV 0: exact copy of raspberry.tips v2.0 (2026-08-13), no changes.
--------------------------------------------------------------------------- */

/* [What to print] */
part = "calibration"; // [tub, lid, calibration, port_gauge, preview]
// A = Active Cooler only, B = AI HAT on its spacers (height hat_h)
variant = "B"; // [A, B]

/* [PCB - official drawing] */
pcb_l     = 85.0;
pcb_w     = 56.0;
pcb_t     = 1.4;
hole_edge = 3.5;
hole_dx   = 58.0;
hole_dy   = 49.0;

/* [Build heights] */
cooler_h      = 13.7;  // Active Cooler above the PCB top
hat_h         = 26.5;  // Pi PCB top to the top of the AI HAT heatsink; Aaron, 2026-10-22
under_pcb     = 3.0;   // air under the PCB
top_clearance = 3.0;   // air between the tallest part and the lid underside

/* [Connector overhang past the PCB edge] */
// MEASURED on RASPBERRY_PI_5_WITH_ACTIVE_COOLER.stl. The interior must take
// this overhang, or the connectors hit the wall above their openings when the
// board is lowered in, and the board does not go in. Their v1.0 to v1.5
// failed on exactly this.
overhang_x1 = 3.9;   // USB stacks past the x = 85 edge
overhang_x0 = 0.0;   // microSD socket flush
overhang_y0 = 1.2;   // USB-C and micro-HDMI past the y = 0 edge
overhang_y1 = 0.0;   // GPIO side flush

/* [Case] */
wall     = 2.4;
floor_t  = 3.0;   // 3 mm (original 2.0): stiffer base, and 1 mm left under the bolt recesses
lid_t    = 2.0;
pcb_gap  = 0.4;   // gap around the PCB
radius   = 4.0;   // outer corner radius
rebate_h = 3.0;   // depth of the lid rebate

/* [Posts] */
// "pin"     = centring pin that goes into the PCB hole. No screws, the board
//             cannot slide. The original's default.
// "screw"   = flat post with a pilot hole for M2.5 self-tapping screws.
// "through" = through-bolt from below (rig change, REV 1): M2.5 bolt up
//             through the post and the PCB into a nut or a HAT riser.
post_type  = "through"; // [pin, screw, through]
boss_d     = 6.0;
pin_d      = 2.4;  // PCB hole is 2.7, minus 0.3 for print tolerance
pin_h      = 2.0;
boss_pilot = 2.2;  // pilot hole for an M2.5 self-tapping screw. 2.7 is the
                   // hole IN THE PCB; in plastic the thread strips at that.
// Through-bolt (post_type = "through"). M2.5: the PCB hole is 2.7 mm.
bolt_clear_d = 2.9;   // clearance hole, ISO 273 medium for M2.5
bolt_head_d  = 5.6;   // recess for an ISO 7045 pan head (dk 5.0) plus 0.6
bolt_head_h  = 2.0;   // recess depth: pan head k = 1.75 plus 0.25
bolt_foot_d  = 9.0;   // foot that ties the post to the floor around the recess
bolt_foot_h  = 1.0;   // foot height above the floor
nut_h        = 2.0;   // ISO 4032 M2.5 nut, for the bolt length echo

/* [Lid screws] */
// Two M3 screws down through ears on the lid into captive nuts in lugs on
// two diagonal outside corners: x = 0 / y = 56 and x = 85 / y = 0. The other
// diagonal is not used: a lug at x = 85 / y = 56 would sit in the space a
// plug body needs outside the upper USB stack.
lid_screw_d  = 3.4;   // clearance hole, ISO 273 medium for M3
lid_nut_af   = 5.5;   // ISO 4032 M3 nut, across flats
lid_nut_h    = 2.4;   // ISO 4032 M3 nut, height
nut_fit      = 0.3;   // added to the nut's flats and height for the pocket
lid_nut_down = 5.0;   // from the lug top to the top of the nut pocket
lug_wall     = 1.6;   // plastic around the nut pocket, inside and outside

/* [Cutouts] */
port_gap = 0.5;     // added on every side. A little more generous than in
                    // their earlier versions, because the connectors now sit
                    // behind the wall and plug bodies would otherwise hit the
                    // edge of the opening.
// FPC slots for camera/display. Closed by default: in variant B the PCIe
// cable runs inside, and an open slot only lets dust in.
fpc_slots   = false;
sd_slot     = true;   // original card-sized slot; replaced when sd_grip is on
// microSD finger access (rig change, REV 1)
sd_grip     = true;
sd_card_out = 2.25;   // card past the board edge when inserted; Aaron, calipers, 2026-10-22
sd_grip_w   = 20;     // notch and scoop width, centred on the card
sd_grip_r   = 2.0;    // corner radius of notch and scoop
sd_scoop_l  = 10;     // floor scoop length, from the outer wall face inward

/* [Ventilation] */
// Designed for the usual mounting: USB-C side (y = 0) facing the floor, lid
// vertical, GPIO wall (y = 56) on top. Warm air rises from the y = 0 end to
// the GPIO wall. Air comes in low (camera opening, floor slots) and leaves
// high (GPIO wall honeycomb, the top face). The lid vents sit over the AI
// HAT heatsink, which covers the PCB except the Ethernet and USB-A block, so
// they open the whole hot area to the air rising past it. No vents in the
// y = 0 (USB-C) face.
floor_slots    = true;
lid_grille     = true;
wall_honeycomb = true;   // honeycomb field in the closed GPIO wall: the exhaust
heatsink_x1    = 66.45;  // heatsink end along x, PCB coordinates: where the Ethernet socket starts (STEP)
vent_border    = 5.0;    // solid lid border, clear of the skirt (which joins the plate 1.4 to 3.8 mm in)
vent_keep      = 3.0;    // solid plastic kept around the camera opening, screw ears and labels
slot_w         = 3.0;
slot_pitch     = 6.0;
hex_af         = 5.0;    // hexagon size across flats
hex_web        = 1.8;    // web width between hexagons

/* [Looks] */
port_corner_r = 1.0;   // corner rounding of the port openings
bezel_depth   = 0.8;   // depth of the recess around the port group, 0 = off
bezel_margin  = 2.5;   // how far the recess reaches past the openings

/* [Mounting] */
// One flange on the base along the y = 56 (GPIO) side, opposite the USB-C
// and HDMI ports, flush with the bottom, with two M5 clearance holes for
// bolts into T-slot nuts. Both holes are on one line along x, so they go
// into one slot. The flange runs from just past the lid lug on the x = 0
// corner to where the rounded corner at the x = 85 end starts. A
// 45 degree fillet joins it to the wall along its whole length, cut away
// around each hole so the bolt heads seat flat.
mount       = true;
mount_x     = [12.5, 83.75];  // hole centres along x; 83.75 ends the flange where the x = 85 corner's curve starts
mount_hole  = 5.5;      // clearance hole, ISO 273 medium for M5
mount_t     = 5.0;      // flange thickness
mount_head  = 12.0;     // M5 head or washer diameter kept clear of the wall; 12 takes a flange head (11.8)
mount_rim   = 4.0;      // plastic around the hole
mount_fillet = 5.0;     // height and depth of the 45 degree fillet along the wall

/* [Camera cables] */
// One opening in the lid over both camera/display FPC connectors, running
// out through the lid's y = 0 edge (skirt included), so the lid is a U and
// lifts off over the cables without unplugging them. The tub is not cut.
cam_slot   = true;
cam_margin = 1.5;   // added on every side of the connector footprint
cam_r      = 2.0;   // radius of the two inner corners

/* [Revision] */
revision  = "RV0.13"; // revision stamp, engraved in the y = 0 (USB-C) wall, under the part name ("" = none)
rev_size  = 5;       // text cap height, mm  [2:0.5:12]
rev_depth = 0.6;     // how far the text is inset below the surface, mm; the wall is 2.4 mm  [0.4:0.1:1.2]

/* [Label] */
part_name  = "pi5_case"; // file name without .scad, engraved in the y = 0 (USB-C) wall ("" = none)
name_size  = 5;      // text cap height, mm  [2:0.5:12]
name_depth = 0.6;    // how far the text is inset below the surface, mm  [0.4:0.1:1.2]

/* [Hidden] */
$fn = 48;
eps = 0.01;

// =============================================================================
// Connector dimensions from the official reference model
// Reference: PCB corner = (0,0), z = 0 is the PCB top.
// Format: [ from, to, z_bottom, z_top, "name" ]
// =============================================================================

// CORRECTED 2026-08-13 (original author). Source: component analysis of
// RASPBERRY_PI_5_WITH_ACTIVE_COOLER.stl, parts identified by their size
// instead of guessed. In their v1.0 the micro-HDMI and FPC connectors were
// swapped: the long narrow bodies (3.3 x 15.9 mm) are the camera/display
// connectors, micro-HDMI measures 6.5 x 3.5 mm.

// x = 85 edge (the 56 mm short side)
ports_right = [
    // Both USB stacks as one opening: only 2.8 mm between them.
    [ 22.30, 54.66, -3.50, 16.78, "4x USB (both stacks)" ],
    [  2.25, 18.15, -2.05, 13.70, "Ethernet RJ45" ]
];

// y = 0 (85 mm long side with power and video)
ports_front = [
    [  6.73, 15.67, -0.80,  3.16, "USB-C power" ],
    [ 22.55, 29.05, -0.55,  2.97, "micro-HDMI 0" ],
    [ 35.95, 42.45, -0.55,  2.97, "micro-HDMI 1" ]
];

// Both camera/display FPC connectors together, from the official STEP
// (libraries/pi5_ghost.scad frame): [x_from, x_to, y_from, y_to], PCB corner
// at (0,0). CAM/DISP 0 is x 47.10..50.65, CAM/DISP 1 x 53.30..56.85.
cam_footprint = [47.10, 56.85, 0.14, 16.84];

// optional FPC slots on the same edge
ports_fpc = [
    [ 47.40, 50.70,  0.00,  3.90, "FPC CAM/DISP 0" ],
    [ 53.60, 56.90,  0.00,  3.90, "FPC CAM/DISP 1" ]
];

// x = 0 (short side opposite the USB)
ports_left = [
    [ 22.00, 33.95, -3.05, -1.60, "microSD" ]
];

// --- derived dimensions ------------------------------------------------------
stack_h = (variant == "B") ? hat_h : cooler_h;

inner_h = under_pcb + pcb_t + stack_h + top_clearance;
inner_l = pcb_l + overhang_x0 + overhang_x1 + 2 * pcb_gap;
inner_w = pcb_w + overhang_y0 + overhang_y1 + 2 * pcb_gap;
outer_l = inner_l + 2 * wall;
outer_w = inner_w + 2 * wall;
tub_h   = floor_t + inner_h;

pcb_x0 = wall + pcb_gap + overhang_x0;
pcb_y0 = wall + pcb_gap + overhang_y0;
pcb_z_top = floor_t + under_pcb + pcb_t;   // z = 0 of the connector tables

hole_pos = [
    [hole_edge,           hole_edge],
    [hole_edge + hole_dx, hole_edge],
    [hole_edge,           hole_edge + hole_dy],
    [hole_edge + hole_dx, hole_edge + hole_dy]
];

// =============================================================================
// Helper modules
// =============================================================================

module box_r(l, w, h, r) {
    hull() {
        translate([r,     r,     0]) cylinder(h = h, r = r);
        translate([l - r, r,     0]) cylinder(h = h, r = r);
        translate([r,     w - r, 0]) cylinder(h = h, r = r);
        translate([l - r, w - r, 0]) cylinder(h = h, r = r);
    }
}

// Rectangle with rounded corners, 2D
module rrect(b, h, r) {
    hull() for (x = [r, b - r], y = [r, h - r]) translate([x, y]) circle(r = r, $fn = 24);
}

// Honeycomb field: staggered hexagons, as a cutter along +z
module hex_grid(bx, by, depth, af = 5.0, web = 1.8) {
    dx = af + web;
    dy = dx * 0.866;
    nx = floor(bx / dx);
    ny = floor(by / dy);
    for (j = [0 : max(ny - 1, 0)])
        for (i = [0 : max(nx - 1, 0)]) {
            px = i * dx + (j % 2) * dx / 2;
            py = j * dy;
            if (px + af / 2 <= bx && py + af / 2 <= by)
                translate([px, py, -eps])
                    rotate([0, 0, 30]) cylinder(h = depth + 2 * eps, d = af, $fn = 6);
        }
}

module posts() {
    for (p = hole_pos)
        translate([pcb_x0 + p[0], pcb_y0 + p[1], floor_t - eps])
            if (post_type == "pin") {
                // Base plus centring pin with a chamfer, so the board slides
                // into place by itself when it is put in.
                cylinder(h = under_pcb + eps, d = boss_d);
                translate([0, 0, under_pcb]) {
                    cylinder(h = pin_h - 0.6, d = pin_d);
                    translate([0, 0, pin_h - 0.6])
                        cylinder(h = 0.6, d1 = pin_d, d2 = pin_d - 0.8);
                }
            } else if (post_type == "through") {
                // Hole and recess are cut in tub(), after the union
                cylinder(h = under_pcb + eps, d = boss_d);
                cylinder(h = bolt_foot_h + eps, d = bolt_foot_d);
            } else {
                difference() {
                    cylinder(h = under_pcb + eps, d = boss_d);
                    translate([0, 0, -1]) cylinder(h = under_pcb + 3, d = boss_pilot);
                }
            }
}

// Port openings with rounded corners. Deliberately built as a hull of four
// cylinders whose axis points straight along the cut: nested rotate() on a
// 2D profile swapped width and height in their v1.3.
function port_r(p) = min(port_corner_r,
                         (p[3] - p[2] + 2 * port_gap) / 2 - 0.05,
                         (p[1] - p[0] + 2 * port_gap) / 2 - 0.05);

// Axis along +x (cuts the walls at x = 0 and x = max)
module slot_x(x_start, a0, a1, b0, b1, r, depth) {
    hull() for (a = [a0 + r, a1 - r], b = [b0 + r, b1 - r])
        translate([x_start, a, b]) rotate([0, 90, 0])
            cylinder(h = depth, r = r, $fn = 24);
}

// Axis along +y (cuts the walls at y = 0 and y = max)
module slot_y(y_start, a0, a1, b0, b1, r, depth) {
    hull() for (a = [a0 + r, a1 - r], b = [b0 + r, b1 - r])
        translate([a, y_start, b]) rotate([-90, 0, 0])
            cylinder(h = depth, r = r, $fn = 24);
}

module cut_right(p) {
    slot_x(outer_l - wall - eps,
           pcb_y0 + p[0] - port_gap, pcb_y0 + p[1] + port_gap,
           pcb_z_top + p[2] - port_gap, pcb_z_top + p[3] + port_gap,
           port_r(p), wall + 2 * eps);
}

module cut_left(p) {
    slot_x(-eps,
           pcb_y0 + p[0] - port_gap, pcb_y0 + p[1] + port_gap,
           pcb_z_top + p[2] - port_gap, pcb_z_top + p[3] + port_gap,
           port_r(p), wall + 2 * eps);
}

module cut_front(p) {
    slot_y(-eps,
           pcb_x0 + p[0] - port_gap, pcb_x0 + p[1] + port_gap,
           pcb_z_top + p[2] - port_gap, pcb_z_top + p[3] + port_gap,
           port_r(p), wall + 2 * eps);
}

// Shallow recess around the port group
module port_bezel() {
    if (bezel_depth > 0)
        slot_y(-eps,
               pcb_x0 + ports_front[0][0] - bezel_margin,
               pcb_x0 + ports_front[len(ports_front) - 1][1] + bezel_margin,
               pcb_z_top + ports_front[0][2] - bezel_margin,
               pcb_z_top + ports_front[1][3] + bezel_margin,
               2.0, bezel_depth + eps);
}

module all_cutouts() {
    port_bezel();
    for (p = ports_right) cut_right(p);
    for (p = ports_front) cut_front(p);
    if (fpc_slots) for (p = ports_fpc) cut_front(p);
    if (sd_slot && !sd_grip) for (p = ports_left) cut_left(p);
    if (sd_grip) sd_grip_cut();
}

// Floor slots: intake side. Kept clear of the posts.
module floor_vents() {
    n = floor((inner_l - 24) / slot_pitch);
    len = inner_w - 20;
    for (i = [0 : n - 1])
        translate([wall + 14 + i * slot_pitch, wall + 10, -eps])
            linear_extrude(height = floor_t + 2 * eps)
                rrect(slot_w, len, slot_w / 2 - 0.01);
}

// Lid vents: a honeycomb over the heatsink, holding only whole hexagons that
// keep clear of the border, the camera opening and the screw ears. The lid prints flat, so the holes need no supports; a honeycomb
// keeps an even web everywhere, the stiffest hole pattern for a thin plate.
hex_r = hex_af / sqrt(3);                 // hexagon corner radius

// Camera opening extents (see cam_outline())
cam_x0  = pcb_x0 + cam_footprint[0] - cam_margin;
cam_x1  = pcb_x0 + cam_footprint[1] + cam_margin;
cam_y1  = pcb_y0 + cam_footprint[3] + cam_margin;

function vent_ok(x, y) =
    let(k = vent_keep + hex_r)
    x - hex_r >= vent_border && x + hex_r <= min(outer_l - vent_border, pcb_x0 + heatsink_x1)
    && y - hex_r >= vent_border && y + hex_r <= outer_w - vent_border
    // camera opening, which reaches the y = 0 edge
    && !(x > cam_x0 - k && x < cam_x1 + k && y < cam_y1 + k)
    // screw ears
    && min([for (c = lug_pos) norm([x - c[0], y - c[1]])]) > lug_d / 2 + k;

module lid_vents() {
    dx = hex_af + hex_web;
    dy = dx * sqrt(3) / 2;
    for (j = [0 : floor(outer_w / dy)], i = [-1 : floor(outer_l / dx)]) {
        x = i * dx + (j % 2) * dx / 2;
        y = j * dy;
        if (vent_ok(x, y))
            translate([x, y, -eps])
                rotate([0, 0, 30]) cylinder(h = lid_t + 2 * eps, d = hex_af / cos(30), $fn = 6);
    }
}

// Honeycomb field in the closed GPIO wall (y = 56). Sits between the floor
// and the rebate, so neither the stiffness nor the lid edge is weakened,
// and above the mounting fillet, which would otherwise cover its lower row.
// Hexagons with a flat top and bottom (a 2.9 mm bridge, prints without
// supports). Every hole's bottom stays vent_keep above the mounting fillet,
// its top 3 mm under the rebate.
module wall_vents() {
    half = hex_af / 2 * cos(30);              // centre to flat, top and bottom
    zlo  = max(floor_t + 3, mount ? mount_t + mount_fillet + vent_keep : 0);
    zhi  = tub_h - rebate_h - 3;
    x0 = 17; x1 = outer_l - 17;
    dx = hex_af + hex_web;
    dz = dx * sqrt(3) / 2;
    for (j = [0 : floor((zhi - zlo) / dz)], i = [0 : floor((x1 - x0) / dx)]) {
        x = x0 + hex_af / 2 + i * dx + (j % 2) * dx / 2;
        z = zlo + half + j * dz;
        if (x + hex_af / 2 <= x1 && z + half <= zhi)
            translate([x, outer_w - wall - eps, z])
                rotate([-90, 0, 0])
                    cylinder(h = wall + 2 * eps, d = hex_af, $fn = 6);
    }
}

// =============================================================================
// Lid screw lugs
// =============================================================================
lug_nut_r = (lid_nut_af + nut_fit) / cos(30) / 2;   // pocket corner radius
lug_d     = 2 * (lug_nut_r + lug_wall);
inner_r   = max(radius - wall, 0.6);                 // interior corner radius
// Lug centre sits on the corner diagonal, far enough out that lug_wall of
// plastic is left between the nut pocket and the interior corner.
lug_off   = (inner_r + lug_wall + lug_nut_r) / sqrt(2);
// [x, y, outward x, outward y] for each lug
lug_pos = [
    [wall + inner_r - lug_off, outer_w - wall - inner_r + lug_off, -1,  1],
    [outer_l - wall - inner_r + lug_off, wall + inner_r - lug_off,  1, -1]
];

// Lug bodies, hulled onto the rounded outer corner. h = tub_h for the tub,
// lid_t for the ears on the lid.
module lugs(h) {
    for (c = lug_pos)
        hull() {
            translate([c[0], c[1], 0]) cylinder(h = h, d = lug_d);
            translate([c[2] < 0 ? radius : outer_l - radius,
                       c[3] < 0 ? radius : outer_w - radius, 0])
                cylinder(h = h, r = radius);
        }
}

// Screw hole down each lug, and a hex pocket with a slot out of the lug's
// outer side for sliding the nut in. The pocket's flats run along the slot.
module lug_cuts() {
    screw_depth = lid_nut_down + lid_nut_h + 4;
    pocket_h    = lid_nut_h + nut_fit;
    for (c = lug_pos) {
        a = atan2(c[3], c[2]);
        translate([c[0], c[1], 0]) {
            translate([0, 0, tub_h - screw_depth]) cylinder(h = screw_depth + 1, d = lid_screw_d);
            translate([0, 0, tub_h - lid_nut_down - pocket_h]) {
                rotate([0, 0, a + 60]) cylinder(h = pocket_h, r = lug_nut_r, $fn = 6);
                rotate([0, 0, a])
                    translate([0, -(lid_nut_af + nut_fit) / 2, 0])
                        cube([lug_d, lid_nut_af + nut_fit, pocket_h]);
            }
        }
    }
}

// For the fit check, which use<>s this file (use<> exports functions, not
// variables): where the PCB corner sits, z at the PCB top.
function case_board_at() = [pcb_x0, pcb_y0, pcb_z_top];

// =============================================================================
// Mounting ears
// =============================================================================
// Hole centre out from the y = 56 wall face far enough that the bolt head
// or washer clears the wall.
mount_y = outer_w + mount_head / 2 + 0.5;
mount_r = mount_hole / 2 + mount_rim;

// Flange outline: a disc around each hole and a strip inside the wall,
// hulled. If a disc reaches into a rounded corner, the corner's own circle
// joins the hull so the flange follows it without a step; with the default
// positions neither disc does. What the hull puts inside the tub is removed
// with the interior in tub().
module mount_outline() {
    hull() {
        for (x = mount_x) translate([x, mount_y]) circle(r = mount_r);
        translate([mount_x[0] - mount_r, outer_w - wall / 2])
            square([mount_x[1] - mount_x[0] + 2 * mount_r, wall / 2 + eps]);
        if (mount_x[1] + mount_r > outer_l - radius + eps)
            translate([outer_l - radius, outer_w - radius]) circle(r = radius);
        if (mount_x[0] - mount_r < radius - eps)
            translate([radius, outer_w - radius]) circle(r = radius);
    }
}

module mount_ears() {
    linear_extrude(mount_t) mount_outline();
    // Fillet along the wall, trimmed to the flange outline
    intersection() {
        linear_extrude(mount_t + mount_fillet) mount_outline();
        translate([0, outer_w - eps, mount_t - eps])
            rotate([90, 0, 90])
                linear_extrude(outer_l)
                    polygon([[0, 0], [mount_fillet, 0], [0, mount_fillet]]);
    }
}

// Through holes, and room above each for the bolt head (the fillet is cut
// away there, so the head seats on the flat flange top)
module mount_holes() {
    for (x = mount_x)
        translate([x, mount_y, 0]) {
            translate([0, 0, -1]) cylinder(h = mount_t + 2, d = mount_hole);
            translate([0, 0, mount_t]) cylinder(h = mount_fillet + 1, d = mount_head + 1);
        }
}

// =============================================================================
// Labels
// =============================================================================
// Part name over the revision, engraved into the outside of the y = 0 wall
// (the USB-C face), in the plain stretch between the port recess and the
// lid lug at the x = 85 corner, reading along +x from outside, upright with
// the tub standing on its floor.
label_x0 = pcb_x0 + ports_front[len(ports_front) - 1][1] + bezel_margin + vent_keep;
label_x1 = lug_pos[1][0] - lug_d / 2 - vent_keep;
label_x  = (label_x0 + label_x1) / 2;
label_zc = (floor_t + tub_h - rebate_h) / 2;          // middle of the plain wall
name_z   = label_zc + 1 + name_size / 2;
rev_z    = label_zc - 1 - rev_size / 2;

module wall_labels() {
    if (part_name != "")
        translate([label_x, name_depth, part_name != "" && revision != "" ? name_z : label_zc])
            rotate([90, 0, 0]) linear_extrude(name_depth + eps)
                text(part_name, size = name_size, halign = "center", valign = "center");
    if (revision != "")
        translate([label_x, rev_depth, part_name != "" ? rev_z : label_zc])
            rotate([90, 0, 0]) linear_extrude(rev_depth + eps)
                text(revision, size = rev_size, halign = "center", valign = "center");
}

// =============================================================================
// Tub
// =============================================================================

// Through-bolt holes and head recesses, cut through floor and posts
module bolt_cuts() {
    for (p = hole_pos)
        translate([pcb_x0 + p[0], pcb_y0 + p[1], -eps]) {
            cylinder(h = floor_t + under_pcb + 1, d = bolt_clear_d);
            cylinder(h = bolt_head_h + eps, d = bolt_head_d);
        }
}

// microSD access: notch in the x = 0 wall from below the floor up to the
// PCB top, so a fingernail reaches the top edge of the card, plus a scoop
// through the floor under the card for the thumb.
module sd_grip_cut() {
    yc = pcb_y0 + (ports_left[0][0] + ports_left[0][1]) / 2;
    r  = sd_grip_r;
    hull() {
        translate([-eps, yc - sd_grip_w / 2, -1]) cube([wall + 2 * eps, sd_grip_w, 1]);
        for (s = [-1, 1])
            translate([-eps, yc + s * (sd_grip_w / 2 - r), pcb_z_top - r])
                rotate([0, 90, 0]) cylinder(h = wall + 2 * eps, r = r);
    }
    translate([-1, yc - sd_grip_w / 2, -eps])
        linear_extrude(height = floor_t + 2 * eps)
            rrect(sd_scoop_l + 1, sd_grip_w, r);
}

module tub() {
    difference() {
    union() {
    difference() {
        union() {
            box_r(outer_l, outer_w, tub_h, radius);
            lugs(tub_h);
            if (mount) mount_ears();
        }

        // Interior
        translate([wall, wall, floor_t])
            box_r(inner_l, inner_w, inner_h + 1, max(radius - wall, 0.6));

        // Lid rebate: the top rebate_h of the wall cut to half thickness inside
        translate([wall / 2, wall / 2, tub_h - rebate_h])
            box_r(outer_l - wall, outer_w - wall, rebate_h + 1, radius);

        all_cutouts();
        if (floor_slots) floor_vents();
        if (wall_honeycomb) wall_vents();
        lug_cuts();
        if (mount) mount_holes();
        wall_labels();
    }

    posts();
    }
    if (post_type == "through") bolt_cuts();
    }
}

// =============================================================================
// Lid
// =============================================================================

// Camera cable opening, 2D: the connector footprint plus cam_margin, open
// past the y = 0 edge, inner corners rounded
module cam_outline() {
    x0 = pcb_x0 + cam_footprint[0] - cam_margin;
    x1 = pcb_x0 + cam_footprint[1] + cam_margin;
    y1 = pcb_y0 + cam_footprint[3] + cam_margin;
    hull() {
        translate([x0, -1]) square([x1 - x0, 1]);
        translate([x0 + cam_r, y1 - cam_r]) circle(r = cam_r);
        translate([x1 - cam_r, y1 - cam_r]) circle(r = cam_r);
    }
}


module lid() {
    difference() {
        union() {
            box_r(outer_l, outer_w, lid_t, radius);
            lugs(lid_t);

            // Skirt. It deliberately overlaps into the plate: if the two only
            // touch face to face, OpenSCAD gives two separate bodies instead
            // of one closed volume.
            translate([wall / 2 + 0.2, wall / 2 + 0.2, -(rebate_h - 0.3)])
                difference() {
                    box_r(outer_l - wall - 0.4, outer_w - wall - 0.4,
                          rebate_h - 0.3 + 0.6, radius);
                    translate([wall / 2, wall / 2, -1])
                        box_r(outer_l - 2 * wall - 0.4, outer_w - 2 * wall - 0.4,
                              rebate_h + 2, max(radius - wall, 0.6));
                }
        }

        if (lid_grille) lid_vents();
        if (cam_slot)
            translate([0, 0, -rebate_h - 1]) linear_extrude(lid_t + rebate_h + 2) cam_outline();
        for (c = lug_pos)
            translate([c[0], c[1], -1]) cylinder(h = lid_t + 2, d = lid_screw_d);
    }
}

// =============================================================================
// Calibration piece
// =============================================================================
// Cuts out the real corner where the USB edge meets the HDMI edge: one short
// print checks wall thickness, post height, pilot hole, rebate depth, the
// position of the most expensive cutouts, and the lid nut pocket.
module calibration() {
    width = 42;
    depth = 30;

    // Reaches past the corner far enough to hold the whole lid lug, so the
    // piece also checks the captive nut fit
    intersection() {
        tub();
        translate([outer_l - width, -lug_d - 1, -1])
            cube([width + lug_d + 1, depth + lug_d + 1, tub_h + 2]);
    }
}

// =============================================================================
// Port gauge
// =============================================================================
// Only the strip of the y = 0 wall with USB-C and both micro-HDMI, with a
// strip of floor as a foot. Hold it against the real Pi before printing a
// large part: it checks exactly the spot that was wrong in their v1.0.
module port_gauge() {
    // 18 rather than 10 mm deep: the first version was 90.6 x 10 mm, a long
    // narrow strip with a big lever and little bed contact that lifted at the
    // ends as it cooled. At 18 mm the footprint is nearly twice as large and
    // the part also stands more steadily when held against the board.
    depth = 18;
    intersection() {
        tub();
        cube([outer_l, depth, pcb_z_top + 8]);
    }
}

// =============================================================================
// Output
// =============================================================================
if (part == "port_gauge") {
    port_gauge();
} else if (part == "tub") {
    tub();
} else if (part == "lid") {
    // flipped: plate on the bed, skirt up
    rotate([180, 0, 0]) translate([0, 0, -lid_t]) lid();
} else if (part == "calibration") {
    calibration();
} else if (part == "preview") {
    tub();
    translate([0, 0, tub_h + 6]) lid();
} else {
    echo("Unknown value for part");
}

// Shortest stock screw length that is at least l, ISO preferred lengths
function stock_len(l) = [for (s = [6, 8, 10, 12, 14, 16, 20, 25]) if (s >= l) s][0];

if (post_type == "through") {
    grip = pcb_z_top - bolt_head_h;   // head seat to PCB top
    need = grip + nut_h + 1;          // through the nut, 1 mm spare
    echo(str("M2.5 bolt: ", grip, " mm from head seat to PCB top; with a nut use at least ",
             need, " mm (M2.5 x ", stock_len(need), "). Into a HAT riser: ",
             grip, " mm plus the riser's thread depth."));
}
echo(str("Lid: M3 screw, at least ", lid_t + lid_nut_down + lid_nut_h,
         " mm to pass the nut (M3 x ", stock_len(lid_t + lid_nut_down + lid_nut_h), ")"));
if (cam_slot)
    echo(str("Camera opening: x ", pcb_x0 + cam_footprint[0] - cam_margin, " to ",
             pcb_x0 + cam_footprint[1] + cam_margin, ", from the y = 0 edge to y ",
             pcb_y0 + cam_footprint[3] + cam_margin));
if (sd_grip)
    echo(str("microSD: card end ", sd_card_out - (pcb_x0 - wall), " mm into the wall, ",
             wall - (sd_card_out - (pcb_x0 - wall)), " mm inside the outer face"));

if (mount)
    echo(str("Mounting: M5 holes at x = ", mount_x, ", ", mount_x[1] - mount_x[0],
             " mm apart, ", mount_y - outer_w, " mm out from the y = 56 wall face"));

echo(str("Variant ", variant,
         " | outer ", outer_l, " x ", outer_w, " x ", tub_h + lid_t,
         " mm | inner height ", inner_h, " | stack ", stack_h));
