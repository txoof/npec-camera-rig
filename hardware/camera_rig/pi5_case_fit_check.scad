/* ---------------------------------------------------------------------------
   Fit check: the official Pi 5 model in our case tub (pi5_case.scad).

   Not a printed part. Shows the tub from camera_rig/pi5_case.scad (variant
   B) with the Pi 5 ghost from libraries/pi5_ghost.scad sitting on its domes,
   so the port cutouts can be checked by eye from any angle.

   view = "fit"           see-through tub, board in green, overlaps in red
   view = "interference"  only the overlaps, in red. Empty is a pass.
   board = "simple"       about 140 boxes, fast (default)
   board = "mesh"         the full STEP mesh, slow; overlaps still use boxes
   board = "boxes"        one box per STEP part, for a final check
   Overlaps are computed against boxes, so a hit can be the box, not the
   part: look at it before changing the case.

   Needs reference/pi5_step/, which is not committed: run
   `uv run fetch_pi5_model.py` once.
   Case for Raspberry Pi 5 by raspberry.tips, CC BY 4.0
   https://raspberry.tips/en/3d-druck/raspberry-pi-5-case-3d-print

   Board placement copies pi5_case.scad's derived values for variant B
   (use<> does not export variables): board corner at
   x = wand + spiel = 2.8, y = wand + spiel + ueber_y0 = 4.0, board bottom
   on the domes at z = boden + unter_pcb = 5.0.

   REV 3: checks our copy, pi5_case.scad, not the reference original.
   REV 2: board choice, simple board by default.
   REV 1: first version.
--------------------------------------------------------------------------- */

include <../libraries/pi5_ghost.scad>
use <pi5_case.scad>

/* [View] */
view = "fit"; // [fit, interference]
board = "simple"; // [simple, mesh, boxes]
tub_alpha = 0.3; // see-through amount of the tub [0:0.1:1]
show_hits = true; // also draw the interference in red in the fit view

/* [Hidden] */
// Lifted by eps: the board resting on the domes is contact, not overlap,
// and would otherwise show as zero-thickness hits on every dome top.
eps = 0.01;
board_at = [2.8, 4.0, 5.0 + pi5_pcb_t + eps];

// The closed-solid board used for overlaps
module solid_board() {
    translate(board_at)
        if (board == "boxes") pi5_boxes();
        else pi5_simple();
}

// render() so the preview shows the computed overlap, not both operands
module hits() {
    color("red") render() intersection() { wanne(); solid_board(); }
}

if (view == "interference") {
    hits();
} else {
    color("grey", tub_alpha) wanne();
    color("green")
        if (board == "mesh") translate(board_at) pi5_ghost();
        else solid_board();
    if (show_hits) hits();
}
