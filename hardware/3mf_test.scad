/* ---------------------------------------------------------------------------
   3MF multi-color workflow test -- three 10 mm cubes stacked in Z, each
   overlapping the one below by eps, one color each. Small enough to check
   an export in the slicer in seconds before trying it on a real part.

   Lazy union is an export setting, not something this file can switch on.
   Each color only survives as its own object if it is a direct top-level
   statement (if/for blocks are fine); anything drawn inside a module that
   is called without its own color() collapses into one object.

   Workflows to try:
     1. Script (Orca-ready, filaments pre-assigned, parts stay stacked):
          uv run scad_to_3mf.py 3mf_test.scad
     2. GUI 3MF: Preferences > Features > lazy-union on, F6, File > Export >
        Export as 3MF. Orca drops each object to the bed unless combined on
        import, and then filaments must be set per part by hand.
     3. CLI 3MF, same result as 2:
          openscad --enable=lazy-union -o 3mf_test.3mf 3mf_test.scad
     4. Three STLs: export once per `part` value below ("blue", "red",
        "yellow"), select all three in one Orca import and answer yes to
        loading them as a single object with multiple parts. STL
        coordinates are absolute, so the parts stay stacked.

   REV 1.0: initial.
   --------------------------------------------------------------------------- */

/* [Test] */
s   = 10;   // cube edge, mm
eps = 0.05; // overlap between neighbouring cubes, mm

/* [Render Select] */
part = "all"; // what to render  ["all","blue","red","yellow"]

// ---------------------------------------------------------------------------

if (part == "all" || part == "blue")
    color("blue") cube(s);
if (part == "all" || part == "red")
    translate([0, 0, s - eps]) color("red") cube(s);
if (part == "all" || part == "yellow")
    translate([0, 0, 2 * (s - eps)]) color("yellow") cube(s);
