# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A collection of parametric OpenSCAD models: 3D-printed mounting hardware (brackets, camera
mounts, cable/slide pockets) plus T-slot aluminum extrusion stock and bolt standins, built up for
a BUAS course CAD mockup. Lives at `hardware/` inside the `npec-camera-rig` repo — tracked by
that repo's git history and covered by its top-level `CONTRIBUTING.md` (branching, PR, push
discipline). This file only covers conventions specific to the CAD files in this directory.

Layout: printable rig parts (and the `rig_assembly.scad` mockup) in `camera_rig/`, tray tags in
`tray_tags/`, everything that is only `use`d or `include`d in `libraries/` (BOSL2, T-slot stock,
bolt and purchased-part stand-ins, AprilTag geometry and bit data), exports in `exports/` mirroring
the source folders, preview renders in `images/`. Scripts stay at the top level and resolve paths
from their own location. Docs and `reference/` stay at the top level.

The [BOSL2](https://github.com/BelfrySCAD/BOSL2) library is vendored (source only, no `.git`) at
`libraries/BOSL2/` for realistic screw/bolt geometry. `libraries/t_slot_bolt.scad` uses it via
`include <BOSL2/std.scad>` + `include <BOSL2/screws.scad>`; note `std.scad` does *not* pull in
`screws.scad` on its own. OpenSCAD resolves `use`/`include` paths relative to the file that
contains them, including nested includes, so files in `camera_rig/` or `tray_tags/` write
`include <../libraries/BOSL2/std.scad>` and `use <../libraries/t_slot_bolt.scad>`. A broken
`use <>` path only prints a WARNING and still renders with the module missing, so treat any
WARNING in the render log as a failure.

## Commands

Render a part to check it compiles and is manifold before calling it done:

```
/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD --render=cgal -o /tmp/check.stl <folder>/<part>.scad
```

Look for `Status: NoError` and a nonzero `Facets` count in the output. A bare `-o out.stl`
(without `--render=cgal`) also renders but doesn't print the manifold check. PNG export needs
`--render=cgal` too — a bare `--render` flag errors out.

**Only export a `.stl` when the user actually asks for one** (e.g. to print or hand off). Most
iteration happens by regenerating/editing the `.scad` and re-rendering to verify; don't leave
throwaway STLs around from routine checks — render to `/tmp` or delete them after confirming. A
`.stl` the user does want to keep (for printing or handoff) goes in the `exports/` subfolder
matching its source folder (e.g. `exports/camera_rig/`).

## Workflow

The user proposes a part/change, Claude generates or edits the OpenSCAD source, the user then
requests revisions iteratively — often by tweaking the Customizer sliders themselves. Every
tunable dimension should be a top-level variable grouped under a `/* [Group] */` Customizer
header with a `// unit/purpose [min:max]` or `[a, b, c]` comment, so it's editable from
OpenSCAD's Customizer UI without a code round-trip. Push derived (non-user-facing) values into
a trailing `/* [Hidden] */` group.

## House style

Established by `camera_rig/l_bracket_4020.scad`; new parts should match it:

- A `/* ... */` block comment header (never `//` line comments) explaining the part, its
  coordinate convention, and a `REV n:` changelog.
- 2D cross-sections built as small named modules, generally `hull()` of squares/circles then
  `linear_extrude()`d — **except** when the true geometry comes from a manufacturer drawing (see
  below), where an approximated hull would be wrong.
- `/* [Render] */` group with `$fn = $preview ? 32 : 96;` and an `eps = 0.01;` fudge constant for
  overlapping boolean ops, kept separate from `/* [Hidden] */`.
- Printed parts additionally carry:
  - `/* [Build Plate] */`: `copies` (`[1:200]`), `plate_gap`, `plate_cols` (`0` = auto
    near-square grid), with derived `grid_cols`/`grid_rows`/`pitch_x`/`pitch_y` under
    `[Hidden]`, a `plate(n)` module centering the grid on the origin, and
    `if (copies > 1) plate(copies); else <part>();` as the file's last line.
  - `/* [Revision] */`: a `revision` string plus size/depth/placement, engraved into a flat
    face.
- **Purchased-stock exception**: parts that represent off-the-shelf hardware for
  assembly/mockup purposes rather than something printed (`t_slot_40x40.scad`, `t_slot_20x20.scad`,
  `t_slot_bolt.scad`) skip the `[Build Plate]` and `[Revision]` groups entirely — there's
  nothing to lay out on a print bed or stamp a rev number into raw stock or purchased hardware.
- When a part's cross-section is defined by a manufacturer drawing rather than designed from
  scratch, reconstruct it as an exact `polygon()` from the vendor's own vector data (tessellate
  any arcs) instead of approximating with `hull()` of primitives — see `t_slot_40x40.scad`, whose
  132-point profile was reconstructed point-for-point from
  `reference/40x40_profile/54.01.0100(00-00-0)(000)_right.dxf`. Only expose Customizer params for
  dimensions that are genuinely independent of that baked-in outline (e.g. a bore diameter
  subtracted as a live `circle()`, or extrusion length) — don't add sliders that don't actually
  do anything to the fixed polygon. When no vector source exists (`t_slot_20x20.scad` had only a
  raster drawing in a PDF), say so in the header and be explicit about which figures are
  vendor-labelled vs. approximated — don't present a guess with the same confidence as a DXF
  reconstruction.
- For hardware standins (bolts, screws), use the vendored BOSL2 library's `screw()` with
  `thread="none"` rather than hand-rolling head/shaft geometry — it gets standard M-series head
  proportions right for free. Build a `screw_info()` spec and override fields with `struct_set()`
  (e.g. a custom hole/shaft diameter) rather than modifying the resulting mesh.

## Trusting physical measurements

When a stated dimension is described as calipers-verified (or similarly directly measured),
treat it as ground truth rather than re-deriving it from indirect evidence (photos, printed
rulers, etc.). Put verification effort into *relative* measurements instead.

## Vendor reference subdirectories

All vendored CAD reference material lives under the top-level `reference/` directory, one
subdirectory per catalog part (e.g. `reference/40x40_profile/`), kept as the source of truth for
the corresponding `.scad` model — see `reference/README.md` for what's kept for each part and
why. Not all of a manufacturer's exported views are cross-sections — for the 40x40 extrusion,
only the `_right` DXF/DWG contains the actual profile geometry (ARC/CIRCLE entities); `_front`/
`_top` are plain rectangles of the cut length. Check entity types, not just filenames, before
assuming which view to reconstruct from. PDF datasheets are generally not kept once their
relevant content is captured in vector data (DXF/DWG) or in the write-up in
`reference/README.md` — they're large and duplicate what's already preserved elsewhere.
