/* ---------------------------------------------------------------------------
   Raspberry Pi 5 ghost: the official STEP model, for visual and
   interference checks only. Never part of a printed body.

   The mesh is not in the repo. Raspberry Pi Ltd owns the model: its
   dimensions may be used, but the STEP and the STL made from it are not
   committed. Run `uv run fetch_pi5_model.py` from hardware/ once; it writes
   reference/pi5_step/pi5.stl and pi5_boxes.scad (both gitignored).

   Coordinates (the case convention, same as the raspberry.tips case table):
     origin   = board corner, z = 0 is the top face of the PCB
     x 0..85  = long edge; x = 85 end holds Ethernet and the 4 USB ports
     y = 0    = USB-C, both micro-HDMI, both camera/display FPC connectors
     y = 56   = GPIO header
     x = 0    = microSD (under the board) and the PCIe FPC (on top)
   The STEP's own frame already has this x/y layout with the board bottom at
   z = 0.03, so the only move is down by the board top height. Checked
   against the STEP: USB-C body x 6.73..15.67, reaching y = -1.20.

   Three versions of the board:
     pi5_ghost()   the full mesh. Slow, and cannot go into booleans.
     pi5_simple()  about 140 boxes. Fast; use it while designing.
     pi5_boxes()   one box per STEP solid (2678). For a final check.
   pi5_simple() keeps every part of 1 mm^3 or more, every part within 1 mm
   of the board edge or past it, every part more than 3 mm above the board
   and every part more than 0.7 mm below it (fetch_pi5_model.py, simplify()).
   The small SMD parts left under the board become one slab as deep as the
   deepest of them (pi5_under_t), with the 6 mm mounting pads kept clear.

   include<> this file (not use<>) to read pi5_pcb_t and the hole data.

   REV 2: pi5_simple(), rounded board outline.
   REV 1: first version, from RP-010083-CA rpi-5b_no_graphics.step.
--------------------------------------------------------------------------- */

/* [Hidden] */
pi5_l = 85;
pi5_w = 56;
pi5_pcb_t = 1.28;          // PCB solid in the STEP, z 0.03..1.31
pi5_step_top = 1.31;       // PCB top face in the STEP's own frame
pi5_hole_d = 2.7;
pi5_pad_d = 6.0;           // copper keep-out around each mounting hole
pi5_corner_r = 3.0;        // board corner radius, mechanical drawing
pi5_holes = [[3.5, 3.5], [61.5, 3.5], [3.5, 52.5], [61.5, 52.5]];
pi5_stl = "../reference/pi5_step/pi5.stl";

include <../reference/pi5_step/pi5_boxes.scad>

// Depth of the underside slab below the board bottom
pi5_under_t = pi5_step_board[2] - pi5_step_under_z;

// The real board, to look at. Its parts are not closed solids, so it cannot
// go into intersection() or difference().
module pi5_ghost() {
    translate([0, 0, -pi5_step_top]) import(pi5_stl);
}

// One box per STEP solid, for interference checks. Each box holds its part,
// so an empty intersection is a pass; a hit can be the box, not the part.
// The mounting holes are cut through so case pins in them do not count.
module pi5_boxes() {
    difference() {
        translate([0, 0, -pi5_step_top]) pi5_step_boxes();
        for (h = pi5_holes)
            translate([h[0], h[1], -50]) cylinder(h = 100, d = pi5_hole_d, $fn = 32);
    }
}

// The board outline with rounded corners and holes, z = -pi5_pcb_t..0
module pi5_board() {
    translate([0, 0, -pi5_pcb_t]) linear_extrude(pi5_pcb_t)
        difference() {
            offset(r = pi5_corner_r) offset(delta = -pi5_corner_r) square([pi5_l, pi5_w]);
            for (h = pi5_holes) translate(h) circle(d = pi5_hole_d, $fn = 32);
        }
}

// Fast stand-in for design work: board, kept part boxes, underside slab.
// Safe in intersection() and difference().
module pi5_simple() {
    pi5_board();
    difference() {
        union() {
            translate([0, 0, -pi5_step_top]) pi5_step_simple_parts();
            translate([0, 0, -pi5_pcb_t - pi5_under_t]) linear_extrude(pi5_under_t)
                offset(r = pi5_corner_r) offset(delta = -pi5_corner_r) square([pi5_l, pi5_w]);
        }
        for (h = pi5_holes)
            translate([h[0], h[1], -pi5_pcb_t - pi5_under_t - 1])
                // circumscribed, so the polygon clears the full 6 mm circle
                cylinder(h = pi5_under_t + 1, d = pi5_pad_d / cos(180 / 96), $fn = 96);
        for (h = pi5_holes)
            translate([h[0], h[1], -50]) cylinder(h = 100, d = pi5_hole_d, $fn = 32);
    }
}
