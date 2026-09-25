/* ---------------------------------------------------------------------------
   T-slot extruded aluminum, 20x20 mm — generic "M6 groove" profile matching
   Conrad/TRU Components item 2623292 (20 x 20 x 1000 mm, 6063-T6, groove M6).

   Unlike `t_slot_40x40.scad`, no vendor DXF exists for this part — only a
   raster technical drawing inside a PDF datasheet
   (`40x40_profile/20x20_profile.pdf`, despite the directory name; it was
   dropped in alongside the 40x40 vendor files). The clearly labelled figures
   from that drawing are used directly: overall 20x20 mm, 4x R1.5 outer
   corner fillets, a Ø5 mm center bore, and a 1.8 mm slot-lip thickness; the
   slot mouth is taken as 6.1 mm both because it's explicitly dimensioned and
   because it matches the datasheet's "Groove size m6" spec (mirroring how
   the 40x40's "Nut 10" spec matched its dimensioned 10.1 mm mouth). The
   internal channel geometry beyond those labelled figures (the diagonal
   undercut walls that key a T-nut in place) reuses the exact proportions
   validated from the 40x40's real vendor DXF, scaled so the boss depth
   lands on this drawing's own 6.1 mm figure — i.e. the *shape family* is
   exact, the last few tenths of a mm on the undercut walls are an informed
   approximation, not a vendor-verified value. Re-derive from a real DXF if
   one turns up, or correct from calipers per the house style's caliper-trust
   rule.

   Coordinate convention: cross-section centred on the bore axis (X=Y=0,
   profile spans -10..+10 both ways), extruded from Z=0 to Z=length.

   Purchased stock, not a printed part — no [Build Plate] or [Revision]
   group, same as `t_slot_40x40.scad`.

   REV 1.0: initial — 1.5 m stock length to match the 40x40 piece.
   --------------------------------------------------------------------------- */

/* [Extrusion] */
length   = 1500; // cut length along Z, mm  [50:50:6000]
bore_dia = 5;     // center through-bore diameter, mm (0 = solid, no bore)

/* [Render] */
$fn = $preview ? 32 : 96;

/* [Hidden] */
// Profile polygon, centred on the bore axis. See header for how this was
// derived (labelled datasheet figures + 40x40-proportioned undercut). Do not
// hand-edit — regenerate if a real vendor DXF or caliper measurements turn up.
profile_pts = [
    [-8.500,-10.000], [-3.050,-10.000], [-3.050,-8.200], [-5.916,-8.200], [-6.055,-8.179], [-6.182,-8.120],
    [-6.286,-8.025], [-6.358,-7.905], [-6.392,-7.769], [-6.385,-7.629], [-6.338,-7.497], [-6.254,-7.384],
    [-5.654,-6.784], [-5.654,-6.446], [-3.586,-4.378], [-2.910,-4.378], [-2.432,-3.900], [2.910,-4.378],
    [3.586,-4.378], [5.654,-6.446], [5.654,-6.784], [6.254,-7.384], [6.338,-7.497], [6.385,-7.629],
    [6.392,-7.769], [6.358,-7.905], [6.286,-8.025], [6.182,-8.120], [6.055,-8.179], [5.916,-8.200],
    [3.050,-8.200], [3.050,-10.000], [8.500,-10.000], [8.793,-9.971], [9.074,-9.886], [9.333,-9.747],
    [9.561,-9.561], [9.747,-9.333], [9.886,-9.074], [9.971,-8.793], [10.000,-8.500], [10.000,-3.050],
    [8.200,-3.050], [8.200,-5.916], [8.179,-6.055], [8.120,-6.182], [8.025,-6.286], [7.905,-6.358],
    [7.769,-6.392], [7.629,-6.385], [7.497,-6.338], [7.384,-6.254], [6.784,-5.654], [6.446,-5.654],
    [4.378,-3.586], [4.378,-2.910], [3.900,-2.432], [4.378,2.910], [4.378,3.586], [6.446,5.654],
    [6.784,5.654], [7.384,6.254], [7.497,6.338], [7.629,6.385], [7.769,6.392], [7.905,6.358],
    [8.025,6.286], [8.120,6.182], [8.179,6.055], [8.200,5.916], [8.200,3.050], [10.000,3.050],
    [10.000,8.500], [9.971,8.793], [9.886,9.074], [9.747,9.333], [9.561,9.561], [9.333,9.747],
    [9.074,9.886], [8.793,9.971], [8.500,10.000], [3.050,10.000], [3.050,8.200], [5.916,8.200],
    [6.055,8.179], [6.182,8.120], [6.286,8.025], [6.358,7.905], [6.392,7.769], [6.385,7.629],
    [6.338,7.497], [6.254,7.384], [5.654,6.784], [5.654,6.446], [3.586,4.378], [2.910,4.378],
    [2.432,3.900], [-2.910,4.378], [-3.586,4.378], [-5.654,6.446], [-5.654,6.784], [-6.254,7.384],
    [-6.338,7.497], [-6.385,7.629], [-6.392,7.769], [-6.358,7.905], [-6.286,8.025], [-6.182,8.120],
    [-6.055,8.179], [-5.916,8.200], [-3.050,8.200], [-3.050,10.000], [-8.500,10.000], [-8.793,9.971],
    [-9.074,9.886], [-9.333,9.747], [-9.561,9.561], [-9.747,9.333], [-9.886,9.074], [-9.971,8.793],
    [-10.000,8.500], [-10.000,3.050], [-8.200,3.050], [-8.200,5.916], [-8.179,6.055], [-8.120,6.182],
    [-8.025,6.286], [-7.905,6.358], [-7.769,6.392], [-7.629,6.385], [-7.497,6.338], [-7.384,6.254],
    [-6.784,5.654], [-6.446,5.654], [-4.378,3.586], [-4.378,2.910], [-3.900,2.432], [-4.378,-2.910],
    [-4.378,-3.586], [-6.446,-5.654], [-6.784,-5.654], [-7.384,-6.254], [-7.497,-6.338], [-7.629,-6.385],
    [-7.769,-6.392], [-7.905,-6.358], [-8.025,-6.286], [-8.120,-6.182], [-8.179,-6.055], [-8.200,-5.916],
    [-8.200,-3.050], [-10.000,-3.050], [-10.000,-8.500], [-9.971,-8.793], [-9.886,-9.074], [-9.747,-9.333],
    [-9.561,-9.561], [-9.333,-9.747], [-9.074,-9.886], [-8.793,-9.971],
];

// ---------------------------------------------------------------------------

module t_slot_20x20_profile() {
    difference() {
        polygon(points = profile_pts);
        if (bore_dia > 0) circle(d = bore_dia);
    }
}

module t_slot_20x20(len = length) {
    linear_extrude(height = len) t_slot_20x20_profile();
}

t_slot_20x20();
