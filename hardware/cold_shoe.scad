/* ---------------------------------------------------------------------------
   Cold shoe mount -- a single printed foot carrying a slide-in accessory
   shoe (cold-shoe / "hot shoe" style rail) plus two independent threaded
   mounting holes:

     - 1/4"-20, tapped into the floor of the shoe channel itself, tucked
       back near the closed end -- lets a 1/4" threaded accessory (mic
       mount, small ball head, etc.) screw straight into the shoe even
       without a shoe-foot plug, or backs up one that does.
     - 3/8"-16, tapped up into the underside of the foot -- the part's main
       mounting point, onto a stand, ball head or rig plate.

   The two holes sit offset in Y rather than stacked coaxially, so their
   BOSL2 thread geometry never has to share material; each gets its own
   comfortable blind-hole depth regardless of the other.

   Footprint follows the same idea as `m5_slide_pocket.scad`: rather than a
   separate carrier plate, the "foot" is just the shoe's own footprint
   carried all the way down to Z0, the same way that file's pocket block
   doubles as its own base footprint. No manufacturer drawing exists for a
   generic cold shoe, so the rail dimensions below (channel width/height,
   lip reach, wall thickness) are ordinary hand-picked sizes for a universal
   accessory foot, not pulled from a vendor spec -- treat them as a starting
   point to check against whatever accessory actually has to slide in.

   Coordinate convention: origin centred on the footprint in X/Y. Z0 = the
   underside of the foot (mating face, where the 3/8" hole opens), which is
   also the print bed; material grows in +Z. The shoe channel opens toward
   +Y and is closed off at -Y.

   Uses the BOSL2 library (vendored in `BOSL2/`) for both threaded holes via
   `screw_hole()` with real modeled thread geometry (thread=true, tolerance
   "2B" -- the standard UTS internal-thread tolerance), rather than an
   undersized self-tap bore.

   Set `copies` under [Build Plate] to lay out that many parts in a grid,
   centred on the origin. copies = 1 renders the single part at the origin.

   REV 1.0: initial.
   --------------------------------------------------------------------------- */

include <BOSL2/std.scad>
include <BOSL2/screws.scad>

/* [Revision] */
revision  = "RV1.0"; // revision stamp, engraved in the top of the closed (-Y) end wall ("" = none)
rev_size  = 3;       // cap height of the text, mm  [2:0.5:5]
rev_depth = 1.0;     // how far the text is inset below the surface, mm  [0.5:0.1:1.5]

/* [Cold Shoe] */
shoe_len     = 34;   // overall footprint length along the slide axis (Y), mm  [20:1:60]
channel_w    = 15;   // clear width between the lips the accessory foot slides through, mm  [8:0.5:25]
channel_h    = 5.5;  // clear height of the slot an accessory foot rides in, mm  [3:0.5:10]
rail_wall    = 3;    // side-wall thickness outboard of the channel, mm  [1.5:0.5:6]
lip_overhang = 3;    // how far each lip reaches inward over the channel, mm  [1:0.5:6]
lip_thk      = 2;    // lip thickness, mm  [1:0.5:4]
floor_thk    = 3;    // channel floor thickness, above the foot, mm  [2:0.5:6]
back_wall    = 5;    // closed (-Y) end wall thickness, mm  [2:0.5:10]
mouth_lead   = 1.0;  // lead-in flare at the open (+Y) mouth, mm (0 = square mouth)
corner_r     = 3;    // rounding on the footprint corners, mm  [0:0.5:6]

/* [Foot] */
foot_thk = 10;  // solid foot beneath the channel floor, carries the 3/8" thread, mm  [6:0.5:16]

/* [Fasteners] */
qtr_depth  = 7;           // 1/4-20 threaded blind-hole depth, from the channel floor down, mm  [4:0.5:12]
qtr_y      = 0;           // 1/4-20 hole centre, Y from the origin; 0 = auto (clear of the 3/8" hole below)
c38_depth  = 9;           // 3/8-16 threaded blind-hole depth, from the underside of the foot up, mm  [5:0.5:14]
thread_fit = "2B";        // BOSL2 internal-thread tolerance for the modeled UTS threads  ["2B","1B","3B"]

/* [Build Plate] */
copies     = 1;  // how many parts to lay out  [1:200]
plate_gap  = 5;  // clear space between neighbours, mm
plate_cols = 0;  // columns across X; 0 = auto (near-square grid)

/* [Render] */
$fn = $preview ? 24 : 48;  // BOSL2 thread geometry on two holes gets expensive fast at high $fn
eps = 0.01;

/* [Hidden] */
shoe_width   = channel_w + 2 * rail_wall;   // outer footprint width, matches the channel + walls
plate_top_z  = foot_thk;                    // top of the solid foot / bottom of the channel floor
floor_top_z  = plate_top_z + floor_thk;     // channel floor surface, where an accessory foot slides
lip_bottom_z = floor_top_z + channel_h;     // underside of the lips
top_z        = lip_bottom_z + lip_thk;      // overall part height

y_mouth = shoe_len / 2;               // open (+Y) end, flush with the outer face
y_back  = -shoe_len / 2 + back_wall;  // cavity backstop, inside the closed end wall

// tucks the 1/4" hole clear of the 3/8" hole's footprint below, without
// requiring the two holes to be coaxial or share depth
qtr_y_eff = qtr_y != 0 ? qtr_y : -shoe_len * 0.3;

rev_cy = (-shoe_len / 2 + y_back) / 2;  // centred in the solid backstop, clear of the cavity

part_dx   = shoe_width;
part_dy   = shoe_len;
grid_cols = plate_cols > 0 ? plate_cols : ceil(sqrt(copies));
grid_rows = ceil(copies / grid_cols);
pitch_x   = part_dx + plate_gap;
pitch_y   = part_dy + plate_gap;

// ---------------------------------------------------------------------------

module rounded_rect(w, l, r) {
    // plan view (XY): rectangle w (X) x l (Y), centred, corners rounded to r
    hull() for (sx = [-1, 1], sy = [-1, 1])
        translate([sx * (w / 2 - r), sy * (l / 2 - r)]) circle(r);
}

module footprint() {
    rounded_rect(shoe_width, shoe_len, corner_r);
}

module channel_cavity() {
    // the slide-in slot: back face at y_back, open through the +Y face,
    // flush with the outer wall -- same pattern as m5_slide_pocket's pocket_cavity
    translate([-channel_w / 2, y_back, floor_top_z])
        cube([channel_w, y_mouth - y_back + eps, channel_h]);

    // lead-in flare: widens the mouth sideways and upward, floor left flat
    // so an accessory foot slides in on one continuous surface
    if (mouth_lead > 0)
        hull() {
            translate([-channel_w / 2, y_mouth - mouth_lead, floor_top_z])
                cube([channel_w, eps, channel_h]);
            translate([-channel_w / 2 - mouth_lead, y_mouth, floor_top_z])
                cube([channel_w + 2 * mouth_lead, eps, channel_h + mouth_lead]);
        }
}

module lip_gap_cavity() {
    // gap between the two lip tips, directly above the channel
    gap_w = channel_w - 2 * lip_overhang;
    translate([-gap_w / 2, y_back, lip_bottom_z])
        cube([gap_w, y_mouth - y_back + eps, lip_thk + eps]);
}

module qtr_hole() {
    // opens at the channel floor, blind downward -- local "top" end is open
    translate([0, qtr_y_eff, floor_top_z - qtr_depth])
        screw_hole("1/4-20", thread=true, tolerance=thread_fit, length=qtr_depth + eps,
                   bevel1=false, bevel2=true, anchor=BOTTOM);
}

module c38_hole() {
    // opens at the foot's underside, blind upward -- local "bottom" end is open
    translate([0, 0, -eps])
        screw_hole("3/8-16", thread=true, tolerance=thread_fit, length=c38_depth + eps,
                   bevel1=true, bevel2=false, anchor=BOTTOM);
}

module revision_stamp() {
    translate([0, rev_cy, top_z - rev_depth])
        linear_extrude(rev_depth + eps)
            text(revision, size = rev_size,
                 halign = "center", valign = "center");
}

module cold_shoe() {
    difference() {
        linear_extrude(top_z) footprint();
        channel_cavity();
        lip_gap_cavity();
        qtr_hole();
        c38_hole();
        if (revision != "") revision_stamp();
    }
}

module plate(n) {
    // grid is centred on the origin; index 0 is the -X/-Y corner
    x0 = -(grid_cols * pitch_x - plate_gap) / 2 + part_dx / 2;
    y0 = -(grid_rows * pitch_y - plate_gap) / 2 + part_dy / 2;
    for (i = [0 : n - 1])
        translate([x0 + (i % grid_cols)      * pitch_x,
                   y0 + floor(i / grid_cols) * pitch_y,
                   0])
            cold_shoe();
}

if (copies > 1) plate(copies); else cold_shoe();
