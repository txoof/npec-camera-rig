/* ---------------------------------------------------------------------------
   T-slot extruded aluminum, 40x40 mm — mk Technology Group profile 2040.01
   (article 54.01.0100), "Nut 10" series: one 10.1 mm T-slot per face, a
   center M8-clearance through-bore, and 1 mm fillets throughout.

   The cross-section polygon below is not a hand-modelled approximation: it
   was reconstructed point-for-point from the manufacturer's own DXF cross-
   section drawing (`40x40_profile/54.01.0100(00-00-0)(000)_right.dxf`,
   confirmed to be the true section view since it's the only one of the three
   DXFs carrying ARC/CIRCLE entities — front/top are just plain rectangles).
   Each 1 mm fillet arc was tessellated to 8 segments. The bore is instead
   subtracted as a live `circle()`, so bore_dia is the one dimension that is
   genuinely adjustable in the Customizer without touching the polygon.

   Coordinate convention: cross-section centred on the bore axis (X=Y=0,
   profile spans -20..+20 both ways), extruded from Z=0 to Z=length — so a
   bar sits with one cut end on the Z=0 plane, ready to translate into an
   assembly.

   This is purchased stock, not a printed part, so unlike the other files in
   this directory it carries no [Build Plate] or [Revision] engraving group
   — there's nothing to lay out on a print bed or stamp a rev number into.

   REV 1.0: initial — 1.5 m stock length to block in the mockup.
   --------------------------------------------------------------------------- */

/* [Extrusion] */
length   = 1500; // cut length along Z, mm  [50:50:6100]
bore_dia = 10;    // center through-bore diameter, mm (0 = solid, no bore)

/* [Render] */
$fn = $preview ? 32 : 96;

/* [Hidden] */
// Profile polygon, centred on the bore axis. Reconstructed from the mfr DXF;
// see header. Do not hand-edit — regenerate from the DXF if the physical
// part is ever re-measured and found to differ.
profile_pts = [
    [-17.000,-5.050], [-20.000,-5.050], [-20.000,-20.000], [-5.050,-20.000], [-5.050,-17.000], [-11.050,-17.000],
    [-11.341,-16.957], [-11.606,-16.831], [-11.823,-16.634], [-11.974,-16.383], [-12.045,-16.098], [-12.031,-15.805],
    [-11.932,-15.529], [-11.757,-15.293], [-10.500,-14.036], [-10.500,-13.328], [-6.172,-9.000], [-4.757,-9.000],
    [-3.757,-8.000], [3.757,-8.000], [4.757,-9.000], [6.172,-9.000], [10.500,-13.328], [10.500,-14.036],
    [11.757,-15.293], [11.932,-15.529], [12.031,-15.805], [12.045,-16.098], [11.974,-16.383], [11.823,-16.634],
    [11.606,-16.831], [11.341,-16.957], [11.050,-17.000], [5.050,-17.000], [5.050,-20.000], [20.000,-20.000],
    [20.000,-5.050], [17.000,-5.050], [17.000,-11.050], [16.957,-11.341], [16.831,-11.606], [16.634,-11.823],
    [16.383,-11.974], [16.098,-12.045], [15.805,-12.031], [15.529,-11.932], [15.293,-11.757], [14.036,-10.500],
    [13.328,-10.500], [9.000,-6.172], [9.000,-4.757], [8.000,-3.757], [8.000,3.757], [9.000,4.757],
    [9.000,6.172], [13.328,10.500], [14.036,10.500], [15.293,11.757], [15.529,11.932], [15.805,12.031],
    [16.098,12.045], [16.383,11.974], [16.634,11.823], [16.831,11.606], [16.957,11.341], [17.000,11.050],
    [17.000,5.050], [20.000,5.050], [20.000,20.000], [5.050,20.000], [5.050,17.000], [11.050,17.000],
    [11.341,16.957], [11.606,16.831], [11.823,16.634], [11.974,16.383], [12.045,16.098], [12.031,15.805],
    [11.932,15.529], [11.757,15.293], [10.500,14.036], [10.500,13.328], [6.172,9.000], [4.757,9.000],
    [3.757,8.000], [-3.757,8.000], [-4.757,9.000], [-6.172,9.000], [-10.500,13.328], [-10.500,14.036],
    [-11.757,15.293], [-11.932,15.529], [-12.031,15.805], [-12.045,16.098], [-11.974,16.383], [-11.823,16.634],
    [-11.606,16.831], [-11.341,16.957], [-11.050,17.000], [-5.050,17.000], [-5.050,20.000], [-20.000,20.000],
    [-20.000,5.050], [-17.000,5.050], [-17.000,11.050], [-16.957,11.341], [-16.831,11.606], [-16.634,11.823],
    [-16.383,11.974], [-16.098,12.045], [-15.805,12.031], [-15.529,11.932], [-15.293,11.757], [-14.036,10.500],
    [-13.328,10.500], [-9.000,6.172], [-9.000,4.757], [-8.000,3.757], [-8.000,-3.757], [-9.000,-4.757],
    [-9.000,-6.172], [-13.328,-10.500], [-14.036,-10.500], [-15.293,-11.757], [-15.529,-11.932], [-15.805,-12.031],
    [-16.098,-12.045], [-16.383,-11.974], [-16.634,-11.823], [-16.831,-11.606], [-16.957,-11.341], [-17.000,-11.050],
];

// ---------------------------------------------------------------------------

module t_slot_40x40_profile() {
    difference() {
        polygon(points = profile_pts);
        if (bore_dia > 0) circle(d = bore_dia);
    }
}

module t_slot_40x40(len = length) {
    linear_extrude(height = len) t_slot_40x40_profile();
}

t_slot_40x40();
