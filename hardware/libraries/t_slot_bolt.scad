/* ---------------------------------------------------------------------------
   T-slot bolt standin — slides into the channel of `t_slot_40x40.scad` or
   `t_slot_20x20.scad` for mockup/assembly purposes. `thread_len` controls
   how much of the shaft (measured from the tip) shows real BOSL2 thread
   geometry; the rest of the shaft stays a plain smooth rod. thread_len = 0
   keeps the whole shaft smooth (a plain clearance-rod standin, not
   something you'd actually thread a nut onto).

   Uses the BOSL2 library (vendored in `BOSL2/`, https://github.com/BelfrySCAD/BOSL2)
   for the head + shaft, via `screw()`, so head proportions (socket/hex/
   button, etc.) match real M-series hardware. The `hole_dia` override lets
   the shaft/hole diameter be dialled to any value, decoupled from the
   chosen `screw_size` — i.e. pick `screw_size` for head proportions and
   `hole_dia` for the actual clearance hole it stands in for.

   The part is two pieces unioned together:
     - a rounded slider "foot" that sits in the profile's channel, under the
       slot's overhanging lip, sized to slide in from the extrusion's open
       end (not through the narrow mouth) — see the width/thickness figures
       in the [Hidden] section, taken directly from the channel geometry in
       t_slot_40x40.scad / t_slot_20x20.scad;
     - a BOSL2 screw (head + shaft, partly threaded per `thread_len`) rising
       from the foot, through the slot mouth, to whatever
       `screw_size`/`head_style` is selected.

   Coordinate convention: foot centred on X=Y=0, foot's underside (the face
   that rests against the channel floor) at Z=0; the shaft/head rise in +Z
   from there.

   Purchased-hardware standin, not a printed structural part — no
   [Build Plate] or [Revision] group, same reasoning as the two profile files.

   REV 1.2: t_slot_bolt()/t_slot_bolt_foot() take explicit parameters
     (defaulting to the Customizer globals) so `use`-ing files can override
     shaft_length etc. per instance instead of always getting this file's
     own defaults.
   REV 1.1: add thread_len so the modeled thread length is Customizer-tunable
     instead of hardcoded thread="none".
   REV 1.0: initial.
   --------------------------------------------------------------------------- */

include <BOSL2/std.scad>
include <BOSL2/screws.scad>

/* [Bolt] */
profile      = 40;      // which T-slot profile the foot is sized for  [40,20]
screw_size   = "M6";     // nominal screw size — sets head + thread proportions  ["M3","M4","M5","M6","M8","M10"]
head_style   = "socket"; // head shape  ["socket","hex","button","pan"]
hole_dia     = 0;        // override shaft/hole diameter, mm (0 = use screw_size's nominal diameter)
shaft_length = 20;       // total shaft length above the foot, mm  [5:1:100]
thread_len   = 10;       // threaded portion, measured from the tip, mm (0 = fully smooth stand-in)  [0:1:100]
foot_length  = 0;        // foot length along the slide axis, mm (0 = auto, ~1.2x foot width)

/* [Render] */
$fn = $preview ? 24 : 48;
eps = 0.01;

/* [Hidden] */
// Channel clearance figures, read off the profile polygons in
// t_slot_40x40.scad / t_slot_20x20.scad: foot_width is a bit under the
// channel width measured right at the slot lip's underside (22.1mm for
// 40x40, 11.8mm for 20x20); foot_thk is a bit under the lip thickness
// itself (3mm / 1.8mm) so the foot slides freely underneath it.
foot_width_40 = 20;
foot_thk_40   = 2.6;
foot_width_20 = 10.5;
foot_thk_20   = 1.5;

// ---------------------------------------------------------------------------

module t_slot_bolt_foot(profile = profile, foot_length = foot_length) {
    fw     = profile == 40 ? foot_width_40 : foot_width_20;
    ft     = profile == 40 ? foot_thk_40   : foot_thk_20;
    fl_ef  = foot_length > 0 ? foot_length : fw * 1.2;
    // rounded slider, house-style hull() of two circles capped by a rectangle
    linear_extrude(ft)
        hull() {
            translate([-(fl_ef - fw) / 2, 0]) circle(d = fw);
            translate([ (fl_ef - fw) / 2, 0]) circle(d = fw);
        }
}

// Explicit parameters (defaulting to the Customizer globals above) so a
// caller doing `use <t_slot_bolt.scad>` can override any of them per
// instance — `use` does not expose this file's own global variables.
module t_slot_bolt(profile = profile, screw_size = screw_size, head_style = head_style,
                    hole_dia = hole_dia, shaft_length = shaft_length, thread_len = thread_len,
                    foot_length = foot_length) {
    ft        = profile == 40 ? foot_thk_40 : foot_thk_20;
    threaded  = thread_len > 0;
    len_ef    = min(thread_len, shaft_length); // can't thread more than the shaft
    base_spec = screw_info(screw_size, head = head_style, thread = threaded ? true : "none");
    spec = hole_dia > 0 ? struct_set(base_spec, ["diameter", hole_dia]) : base_spec;
    union() {
        t_slot_bolt_foot(profile = profile, foot_length = foot_length);
        translate([0, 0, ft - eps])
            screw(spec, length = shaft_length, thread_len = threaded ? len_ef : undef, anchor = BOTTOM);
    }
}

t_slot_bolt();
