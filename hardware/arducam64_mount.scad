/* ---------------------------------------------------------------------------
   Arducam 64MP camera mount plate  (RPi v1/v2 camera form factor)

   Flat plate, camera sits on four proud posts at the +Y end, ribbon cable
   drops straight through a slot just inboard of the posts, and the -Y end
   thickens into a boss that houses a 1/4"-20 UNC threaded insert.

   Footprint is from the official Raspberry Pi Camera Module 2 mechanical
   drawing (RP-008149-DS): PCB 25 x 23.862, R2.0 corners, 4 x 2.2 dia holes
   on a 21.0 x 12.5 pattern, inset 2.0 from three edges and 9.362 from the
   FPC-connector edge.  Arducam's 64MP boards share this form factor.

   A plumb-bob hole runs through the plate on the lens's optical axis, derived
   from the measured module geometry under [Lens / optical axis].  lens_ref_edge
   picks which PCB edge that measurement was taken from.

   The revision string under [Revision] is cut into the plate's +Z face, lying
   flat in XY with the baseline running along Y.

   Set `copies` under [Build Plate] to lay out that many mounts in a grid,
   centred on the origin.  copies = 1 renders the single part at the origin.

   Geometry: plate bottom on Z0, long axis along +Y, tripod end at Y0.

   REV 1:
     - move plumb bob hole to align with lens
     -
   --------------------------------------------------------------------------- */

/* [Revision] */
// Lies flat in the XY plane on the +Z face, reading along the Y axis (bottom to
// top in plan view).  On the underside it is mirrored so it reads the right way
// round with the part turned over.  revision = "" leaves the part unmarked.
revision      = "RV1.0";
rev_face      = "top";   // [top, bottom]
rev_size      = 4;       // cap height, mm - across X, since the text runs along Y  [2:0.5:12]
rev_depth     = 1.2;     // how deep it is cut in, mm  [0.4:0.1:2.5]
// Auto centres it in the clear patch of flat top plate beside the boss and its
// ramp, at the 1/4"-20 end - clear of the PCB, so it stays readable with the
// camera fitted.
rev_auto      = true;
rev_x         = 14.5;    // across X, used when rev_auto = false  [-20:0.1:20]
rev_y         = 14.9;    // along Y,  used when rev_auto = false  [0:0.1:80]

/* [Tripod mount] */
// Which way the 1/4"-20 axis runs: through the end face (in the plane of the
// plate) or through the flat face (normal to the plate)
tripod_axis   = "edge";  // [edge, face]
insert_od     = 9.25;     // measured OD of the brass insert's body
// How far under the OD to bore.  A heat-set insert wants the plastic to be
// squeezed into its knurls: ~0.4-0.6.  Press-fit/epoxy-in: ~0.05-0.1.
// Negative gives clearance, e.g. for a bolt passing through.
insert_grip   = 0.5;     // [-0.5:0.05:1]
insert_depth  = 13.5;    // bore depth (1/4"-20 heat-set inserts are ~12.7 long)
insert_lead   = 0.8;     // 45-deg lead-in: eases entry and takes the displaced plastic
// THE wall knob: minimum material left around the bore, measured at the bore's
// widest point and above the teardrop apex.  boss_h and boss_w derive from it.
boss_wall     = 3.6;     // [1.5:0.2:8]
boss_w_min    = 18;      // floor on the boss width; boss_wall widens it past this if needed
boss_len      = 18;      // boss length along Y; minus insert_depth = wall behind the bore
boss_ramp     = 11;      // length of the blend from boss down to plate
boss_r        = 1.5;     // plan-view rounding on the boss's end face
teardrop_bore = true;    // edge mode: apex on the bore so it bridges without support
teardrop_apex = 1.15;    // apex height / bore radius; 1.414 = full 90-deg point, less = truncated
face_y        = 9;       // face mode only: bore centre along Y

/* [Plate] */
plate_len     = 70;      // overall length along Y
plate_w       = 40;      // overall width across X
plate_t       = 5;       // plate thickness
plate_r       = 3;       // plan-view corner rounding

/* [Camera footprint] */
hole_dx       = 21;      // hole pattern across X  (the 25 mm PCB dimension)
hole_dy       = 12.5;    // hole pattern along Y   (the 23.862 mm PCB dimension)
cam_y         = 56;      // Y of the hole-pattern centre
pcb_x         = 25;      // PCB width  (ghost only)
pcb_y         = 23.95;   // PCB length in Y, measured (ghost only)
// Hole CENTRE inset from the PCB's top edge - the edge the lens module is
// referenced from.  Measured: screw-hole edge 0.96-1.0 from that edge, plus the
// 1.1 hole radius, so 2.06-2.10.  The RPi drawing's nominal is 2.0; 2.08 is the
// value that makes pcb_y and the drawing's 9.362 connector-side inset agree.
pcb_edge      = 2.08;

/* [Lens / optical axis] */
plumb_hole    = true;    // through-hole on the lens's optical axis, for a plumb line
plumb_dia     = 4;     // string or hook clearance
plumb_cham    = 0.6;     // 45-deg lead-in on both faces, 0 to disable
// Optical axis.  Y is not guessed - it is worked back from the measured module:
// the lens sits centred in a housing lens_mod_y deep, whose near edge is
// lens_mod_gap from the PCB's top edge, and that edge is pcb_edge beyond the
// +Y screw-hole row.  Change a measurement and the plumb hole follows.
lens_mod_y    = 13.14;   // camera module housing, Y dimension (measured)
lens_mod_gap  = 0.3;     // reference PCB edge to the module's near edge (measured)
// Which PCB edge lens_mod_gap is measured from.  "connector" is the edge nearest
// the cable slot, 9.37 in from its hole row; "far" is the opposite edge, 2.08 in
// from its hole row.  The two put the lens 10.2 mm apart, so get this right.
lens_ref_edge = "connector";  // [connector, far]
lens_off_x    = 0;       // lens is centred across the board in X  [-12:0.1:12]

/* [Posts] */
post_od       = 5;     // post outside diameter
post_h        = 4;       // how far the posts stand proud of the plate
post_pilot    = 1.7;     // pilot bore for an M2 thread-forming screw
post_pilot_d  = 8;       // pilot depth measured down from the post top
post_cham     = 1.0;     // 45-deg chamfer skirt at the post base, 0 to disable

/* [Cable opening] */
cable_slot_w  = 30;      // across X; clears a 20-pin 1.0 mm FFC (20.5) and the connector
cable_slot_l  = 9;       // along Y
cable_slot_r  = 2;       // corner rounding
cable_slot_gap = 7.5;    // flat left between the slot and the nearest post's base chamfer

/* [Build Plate] */
copies        = 1;       // how many mounts to lay out  [1:200]
plate_gap     = 5;       // clear space between neighbours, mm
plate_cols    = 0;       // columns across X; 0 = auto (near-square grid)

/* [Preview] */
show_pcb_ghost = false;  // transparent mock-up of the camera board

/* [Render] */
$fn = $preview ? 32 : 96;
eps = 0.01;

/* [Hidden] */
// build-plate grid: the part spans X -plate_w/2..+plate_w/2 and Y 0..plate_len
part_dx   = plate_w;
part_dy   = plate_len;
grid_cols = plate_cols > 0 ? plate_cols : ceil(sqrt(copies));
grid_rows = ceil(copies / grid_cols);
pitch_x   = part_dx + plate_gap;
pitch_y   = part_dy + plate_gap;

// boss is sized from boss_wall, not dialled in by hand.  bore_half is the bore's
// widest point (the lead-in cone at the mouth); apex_up is how far the teardrop
// reaches above the axis.  Both have to be walled.
insert_dia = insert_od - insert_grip;              // the bore actually cut
bore_r    = insert_dia / 2;
bore_half = bore_r + insert_lead;
apex_up   = teardrop_bore ? max(bore_r * teardrop_apex, bore_half) : bore_half;
bore_z    = bore_half + boss_wall;                 // edge mode: bore axis height
boss_h    = tripod_axis == "edge" ? bore_z + apex_up + boss_wall
                                  : insert_depth + boss_wall;
boss_w    = max(boss_w_min, 2 * (bore_half + boss_wall));

// slot sits just inboard of the connector-side post row
slot_y  = cam_y - hole_dy / 2 - post_od / 2 - post_cham - cable_slot_gap - cable_slot_l / 2;
slot_y0 = slot_y - cable_slot_l / 2;
ramp_end = boss_len + boss_ramp;

// PCB edges, as insets from their nearest hole row
pcb_conn_edge = pcb_y - hole_dy - pcb_edge;        // connector-side hole inset

// optical axis, in plate coordinates.  lens_in is the lens centre measured in
// from whichever PCB edge lens_ref_edge names.
lens_in       = lens_mod_gap + lens_mod_y / 2;
lens_off_y    = lens_ref_edge == "connector"
                  ? lens_in - (hole_dy / 2 + pcb_conn_edge)
                  : (hole_dy / 2 + pcb_edge) - lens_in;
lens_cx = lens_off_x;
lens_cy = cam_y + lens_off_y;
plumb_r = plumb_dia / 2 + plumb_cham;
post_skirt = post_od / 2 + post_cham;
post_clear = min([ for (x = [-1, 1], y = [-1, 1])
                   sqrt(pow(lens_off_x - x * hole_dx / 2, 2) +
                        pow(lens_off_y - y * hole_dy / 2, 2)) ])
             - plumb_r - post_skirt;

// revision text band.  On the top face the clear strip runs from the far side of
// the cable slot up to whichever comes first, the plumb hole or the near posts;
// on the underside the band under the boss ramp is clear of everything.
// rev_w is a rough glyph advance, good enough to check it fits across the plate.
pilot_floor = plate_t + post_h - post_pilot_d;

// The text runs along Y, so its length is in Y and its cap height is across X.
rev_len    = len(revision) * rev_size * 0.72;
// The clear rectangle of flat top plate beside the boss and ramp: they are only
// boss_w wide, so it runs from there out to the plate edge, and up to where the
// cable slot starts.  Auto sits the text in the middle of it, both ways.
rev_zone_x0 = boss_w / 2;
rev_zone_x1 = plate_w / 2;
rev_zone_y1 = slot_y0;
rev_x_auto  = (rev_zone_x0 + rev_zone_x1) / 2;
rev_y_auto  = rev_zone_y1 / 2;
rev_xx = rev_auto ? rev_x_auto : rev_x;
rev_yy = rev_auto ? rev_y_auto : rev_y;
rev_x0 = rev_xx - rev_size / 2;   rev_x1 = rev_xx + rev_size / 2;
rev_y0 = rev_yy - rev_len  / 2;   rev_y1 = rev_yy + rev_len  / 2;

// footprint clashes, as plain rectangle overlaps
rev_hit_slot  = rev_x1 > -cable_slot_w / 2 && rev_x0 < cable_slot_w / 2 &&
                rev_y1 > slot_y0 && rev_y0 < slot_y0 + cable_slot_l;
rev_hit_plumb = rev_x1 > lens_cx - plumb_r && rev_x0 < lens_cx + plumb_r &&
                rev_y1 > lens_cy - plumb_r && rev_y0 < lens_cy + plumb_r;
// the ramp is only boss_w wide, so text out on the rail clears it even at low Y
rev_hit_ramp  = rev_x1 > -boss_w / 2 && rev_x0 < boss_w / 2 && rev_y0 < ramp_end;
rev_hit_post  = len([ for (x = [-1, 1], y = [-1, 1])
                      if (rev_x1 > x * hole_dx / 2 - post_skirt &&
                          rev_x0 < x * hole_dx / 2 + post_skirt &&
                          rev_y1 > cam_y + y * hole_dy / 2 - post_skirt &&
                          rev_y0 < cam_y + y * hole_dy / 2 + post_skirt) 1 ]) > 0;
// PCB extents, for the ghost
pcb_y0  = cam_y - hole_dy / 2 - pcb_conn_edge;
pcb_y1  = cam_y + hole_dy / 2 + pcb_edge;

echo(str("hole pattern  : ", hole_dx, " x ", hole_dy, " mm, posts at Y=",
         cam_y - hole_dy / 2, " and ", cam_y + hole_dy / 2));
echo(str("cable slot    : Y ", slot_y - cable_slot_l / 2, " .. ", slot_y + cable_slot_l / 2));
echo(str("PCB occupies  : Y ", pcb_y0, " .. ", pcb_y1, "  (plate ends at ", plate_len, ")"));
echo(str("screw         : M2 thread-forming, ", post_h + 1 + 4, " mm long, ",
         post_pilot, " mm pilot"));
echo(str("insert        : ", insert_od, " OD -> ", insert_dia, " bore (", insert_grip,
         " grip), ", insert_depth, " deep"));
echo(str("boss          : ", boss_w, " wide x ", boss_len, " long x ", boss_h, " tall"));
echo(str("wall  boss side   : ", (boss_w - 2 * bore_half) / 2, "   <- boss_wall, boss_w_min"));
if (tripod_axis == "edge") {
    echo(str("wall  boss bottom : ", bore_z - bore_half, "   <- boss_wall"));
    echo(str("wall  boss top    : ", boss_h - bore_z - apex_up, "   <- boss_wall, teardrop_apex"));
    echo(str("wall  bore back   : ", boss_len - insert_depth, "   <- boss_len, insert_depth"));
} else {
    echo(str("wall  bore ceiling: ", boss_h - insert_depth, "   <- boss_wall, insert_depth"));
    echo(str("wall  bore Y ends : ", min(face_y, boss_len - face_y) - bore_half,
             "   <- boss_len, face_y"));
}
echo(str("wall  post        : ", (post_od - post_pilot) / 2, "   <- post_od, post_pilot"));
echo(str("wall  slot rail   : ", (plate_w - cable_slot_w) / 2, "   <- plate_w, cable_slot_w"));
echo(str("wall  plate       : ", plate_t, "   <- plate_t"));
if (plumb_hole) {
    echo(str("optical axis  : ", lens_in, " mm in from the ", lens_ref_edge,
             " edge -> ", lens_off_y, " mm off the hole-pattern centre"));
    echo(str("plumb hole    : dia ", plumb_dia, " at (", lens_cx, ", ", lens_cy,
             "), clear of the posts by ", post_clear, " mm"));
    if (post_clear < 0)
        echo("WARNING: the plumb hole runs into a mounting post - check lens_mod_* / lens_off_x");
    if (abs(lens_cx) < cable_slot_w / 2 + plumb_r && lens_cy - plumb_r < slot_y0 + cable_slot_l)
        echo("WARNING: the plumb hole runs into the cable slot");
    if (abs(lens_cx) + plumb_r > plate_w / 2 || lens_cy + plumb_r > plate_len)
        echo("WARNING: the plumb hole runs off the edge of the plate");
}
if (revision != "") {
    echo(str("revision      : \"", revision, "\"  ", rev_size, " mm cap, ", rev_len,
             " mm long along Y, cut ", rev_depth, " mm into the ", rev_face, " face"));
    echo(str("              : X ", rev_x0, " .. ", rev_x1, ", Y ", rev_y0, " .. ", rev_y1,
             rev_auto ? "  (auto placed)" : ""));
    if (rev_auto)
        echo(str("              : zone X ", rev_zone_x0, "..", rev_zone_x1, " Y 0..",
                 rev_zone_y1, ", margins ", rev_x0 - rev_zone_x0, " across / ",
                 rev_y0, " along"));
    if (rev_hit_slot)  echo("WARNING: the revision text runs into the cable slot");
    if (rev_hit_plumb) echo("WARNING: the revision text runs into the plumb hole");
    if (rev_hit_post)
        echo(rev_face == "bottom" && rev_depth > pilot_floor
             ? str("WARNING: at ", rev_depth, " deep the text breaks into a post pilot hole",
                   " (only ", pilot_floor, " mm of floor under it) - move it or cut shallower")
             : "WARNING: the revision text runs into a mounting post");
    if (rev_face == "top" && rev_hit_ramp)
        echo(str("WARNING: the text crosses the boss ramp (X +/-", boss_w / 2, " below Y",
                 ramp_end, "), where the top surface is sloped - it would be buried"));
    if (rev_x1 > plate_w / 2 || rev_x0 < -plate_w / 2 || rev_y1 > plate_len || rev_y0 < 0)
        echo(str("WARNING: the revision text runs off the plate (X +/-", plate_w / 2,
                 ", Y 0..", plate_len, ") - reduce rev_size or move it"));
}
if (copies > 1)
    echo(str("build plate   : ", copies, " copies in ", grid_cols, " x ", grid_rows,
             " grid, ", grid_cols * pitch_x - plate_gap, " x ",
             grid_rows * pitch_y - plate_gap, " mm overall"));

if (ramp_end > slot_y0)
    echo(str("WARNING: the boss ramp reaches Y", ramp_end, " but the cable slot starts at Y",
             slot_y0, " - shorten boss_ramp, or push cam_y / plate_len out"));

// ---------------------------------------------------------------------------
// 2D profiles
// ---------------------------------------------------------------------------

module rrect(w, l, r) {
    // X-centred, Y from 0 to l, all four corners rounded
    translate([0, l / 2]) offset(r = r) square([w - 2 * r, l - 2 * r], center = true);
}

module boss_plan() {
    // rounded at the free end (Y0), full width where the ramp picks it up, so
    // the two meet without a step
    hull() {
        translate([-boss_w / 2, boss_len - eps]) square([boss_w, eps]);
        translate([-boss_w / 2 + boss_r, boss_r]) circle(boss_r);
        translate([ boss_w / 2 - boss_r, boss_r]) circle(boss_r);
    }
}

module teardrop(d, h) {
    // Bore along +Y with an apex pointing +Z so it bridges when printed flat.
    // Truncated at apex_up: a full 90-deg point costs 1.414r of height, all of
    // which would have to be walled, and the 2-3 mm flat left by truncating
    // bridges perfectly well.
    r = d / 2;
    rotate([-90, 0, 0]) linear_extrude(h) {
        if (teardrop_bore)
            intersection() {
                union() {
                    circle(r);
                    rotate(225) square([r, r]);
                }
                translate([-2 * r, -apex_up]) square([4 * r, 4 * r]);
            }
        else
            circle(r);
    }
}

// ---------------------------------------------------------------------------
// Solids
// ---------------------------------------------------------------------------

module base_plate() {
    linear_extrude(plate_t) rrect(plate_w, plate_len, plate_r);
}

module boss() {
    union() {
        linear_extrude(boss_h) boss_plan();
        // ramp down to the plate, ~37 deg on the defaults: prints unsupported
        hull() {
            translate([-boss_w / 2, boss_len - eps, 0]) cube([boss_w, eps, boss_h]);
            translate([-boss_w / 2, boss_len + boss_ramp, 0]) cube([boss_w, eps, plate_t]);
        }
    }
}

module post() {
    translate([0, 0, plate_t]) {
        cylinder(d = post_od, h = post_h);
        if (post_cham > 0)
            cylinder(d1 = post_od + 2 * post_cham, d2 = post_od, h = post_cham);
    }
}

module posts() {
    for (x = [-1, 1], y = [-1, 1])
        translate([x * hole_dx / 2, cam_y + y * hole_dy / 2, 0]) post();
}

// ---------------------------------------------------------------------------
// Cuts
// ---------------------------------------------------------------------------

module pilot_holes() {
    z_top = plate_t + post_h;
    for (x = [-1, 1], y = [-1, 1])
        translate([x * hole_dx / 2, cam_y + y * hole_dy / 2, z_top + eps])
            mirror([0, 0, 1]) cylinder(d = post_pilot, h = post_pilot_d + eps);
}

module cable_slot() {
    translate([0, slot_y0, -eps])
        linear_extrude(max(plate_t, boss_h) + 2 * eps)
            rrect(cable_slot_w, cable_slot_l, cable_slot_r);
}

module rev_glyphs() {
    text(revision, size = rev_size, halign = "center", valign = "center");
}

module rev_mark() {
    // rotate([0,0,90]) turns the baseline from +X onto +Y, so the text reads
    // bottom-to-top in plan view
    if (rev_face == "bottom")
        // mirrored in X so it reads correctly with the part turned over
        translate([rev_xx, rev_yy, -eps]) mirror([1, 0, 0]) rotate([0, 0, 90])
            linear_extrude(rev_depth + eps) rev_glyphs();
    else
        translate([rev_xx, rev_yy, plate_t - rev_depth]) rotate([0, 0, 90])
            linear_extrude(rev_depth + eps) rev_glyphs();
}

module plumb_bore() {
    // straight through the plate, on the optical axis, chamfered both faces so a
    // line or hook seats without a burr
    translate([lens_cx, lens_cy, 0]) {
        translate([0, 0, -eps]) cylinder(d = plumb_dia, h = plate_t + 2 * eps);
        if (plumb_cham > 0) {
            translate([0, 0, -eps])
                cylinder(d1 = plumb_dia + 2 * plumb_cham, d2 = plumb_dia,
                         h = plumb_cham + eps);
            translate([0, 0, plate_t + eps]) mirror([0, 0, 1])
                cylinder(d1 = plumb_dia + 2 * plumb_cham, d2 = plumb_dia,
                         h = plumb_cham + eps);
        }
    }
}

module insert_bore() {
    if (tripod_axis == "edge") {
        translate([0, -eps, bore_z]) {
            teardrop(insert_dia, insert_depth + eps);
            if (insert_lead > 0)
                rotate([-90, 0, 0])
                    cylinder(d1 = insert_dia + 2 * insert_lead, d2 = insert_dia,
                             h = insert_lead);
        }
    } else {
        translate([0, face_y, -eps]) {
            cylinder(d = insert_dia, h = insert_depth + eps);
            if (insert_lead > 0)
                cylinder(d1 = insert_dia + 2 * insert_lead, d2 = insert_dia,
                         h = insert_lead + eps);
        }
    }
}

// ---------------------------------------------------------------------------

module mount() {
    difference() {
        union() {
            base_plate();
            boss();
            posts();
        }
        pilot_holes();
        cable_slot();
        insert_bore();
        if (plumb_hole) plumb_bore();
        if (revision != "") rev_mark();
    }
}

module pcb_ghost() {
    z = plate_t + post_h;
    %union() {
        // board
        translate([0, pcb_y0, z]) linear_extrude(1) rrect(pcb_x, pcb_y, 2);
        // FPC connector, along the board's cable edge
        translate([-20.8 / 2, pcb_y0 + 1, z + 1]) cube([20.8, 5, 1.5]);
        // lens module, sized in Y from the measurement, on the optical axis
        translate([lens_cx, lens_cy, z + 1]) cylinder(d = lens_mod_y, h = 11);
        // the optical axis itself, carried down through the plumb hole
        translate([lens_cx, lens_cy, -12]) cylinder(d = 0.6, h = z + 14);
    }
}

module one() {
    mount();
    if (show_pcb_ghost) pcb_ghost();
}

module plate(n) {
    // grid is centred on the origin; index 0 is the -X/-Y corner
    x0 = -(grid_cols * pitch_x - plate_gap) / 2 + part_dx / 2;
    y0 = -(grid_rows * pitch_y - plate_gap) / 2;
    for (i = [0 : n - 1])
        translate([x0 + (i % grid_cols)      * pitch_x,
                   y0 + floor(i / grid_cols) * pitch_y,
                   0])
            one();
}

if (copies > 1) plate(copies); else one();
