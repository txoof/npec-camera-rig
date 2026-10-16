# Benchy Yellow-4 from the supervisor's photogrammetry mesh (issue #206)

Run on 2026-10-16. Purpose: reference measurements of the benchmark (metrology log 15.1) from a
second instrument, for checking the rig's Benchy captures (15.5). Method written after the
analysis, not before.

## Source files

Made by the academic supervisor's custom iPhone software, which merges the phone's time-of-flight
(TOF) depth sensor with its camera images. Handed over by Aaron; copies kept outside the repo in
`~/scratch/`. Not committed (9 MB, not ours).

| File | Size | sha256 |
|---|---|---|
| `photogrammetry_mesh 4.usdz` | 8,170,739 bytes | `ba69dfa2bc9b64a9bbd5d5c23761ef7745b31bc611f8e1abd5967a5f2aa69894` |
| `photogrammetry_mesh.stl` | 1,250,084 bytes | `a63c33224af625dafdf28b989b8c62c06c817e9a5153ac55627fef2eab1d23f0` |

The zip entries in the USDZ are dated 2026-10-15 15:32 with no time zone; the time of the capture
itself is not in the files.

- **No area is stored in either file.** The USDZ holds one mesh (`baked_mesh_022ec3d0.usdc`) and 3
  textures (colour, normals, occlusion). Its metadata: `metersPerUnit = 1`, `upAxis = "Y"`,
  creator `RealityKit Object Capture <11.3.2.> <3.9.4>`, config `detail level: .mobile,
  geometry: {nil}, isObjectMaskingEnabled: true, sampleOrdering: .sequential, featureSensitivity:
  .high, ignoreBoundingBox: true, isQuadmeshModelRequest: false`.
- The STL header reads `iPhonotype geometry only; source coordinates preserved; STL has no
  units`. Its 25,000 triangles are the same as the USDZ's (checked by the script), so its units
  are the USDZ's metres.
- The mesh: 12,500 vertices, 25,000 triangles, closed (watertight), mean triangle 3.39 mm².
  Features narrower than about 2 to 3 mm cannot be shown faithfully at that size.

## Method

`mesh_area.py` (run command in its docstring; it needs `trimesh`, `scipy`, `rtree` and `tinyusdz`
in a throwaway venv, not the project's). Full output in `results.txt`.

1. Rays straight down the Y axis every 0.2 mm; the first hit gives the top surface height. This
   is the view from directly above with no perspective, unlike the rig's camera.
2. The board top is fitted as a plane to the lower 60% of cells, 3 passes dropping cells more
   than 3 SD away. Tilt 9.9 and 5.1 mm per metre; the board cells lie 0.36 mm (SD) about it.
3. An object is every cell more than a cut-off height above that plane, holes filled. Cut-offs
   1, 2, 3 and 5 mm. Area = cells x 0.04 mm².
4. Per object: height of its top above the median board height in a ring 4 to 10 mm around it;
   widest span (largest distance between two outline points); smallest enclosing rectangle.
5. Corners named as in 15.1. The largest rosette is NE (as in 15.5). The red solids confirm it on
   their own: the prism stands next to NW, the cylinder next to SW, the sphere next to SE, and
   nothing stands next to NE, where the flat embedded circle is.

## Results

**Rosettes.** Same at every cut-off from 1 to 5 mm (their sides are close to vertical).

| Rosette | Mesh area seen from above | Rig 15.5 mean (92 stills) | Mesh / rig | Upper limit (15.1) |
|---|---|---|---|---|
| NE | 2009.9 mm² | 1823.8 mm² | +10.2% | 3547 mm² |
| SE | 1343.7 mm² | 1123.6 mm² | +19.6% | 2794 mm² |
| NW | 753.4 mm² | 619.4 mm² | +21.6% | 2032 mm² |
| SW | 413.7 mm² | 298.2 mm² | +38.7% | 1175 mm² |

| Rosette | Mesh widest span | Calliper ⌀-max (15.1) | Difference | Rig outline (15.5) | Mesh top | Calliper h-max | Difference |
|---|---|---|---|---|---|---|---|
| NE | 67.02 mm | 67.20 mm | -0.3% | 68.0 to 72.0 | 28.57 mm | 28.00 mm | +2.0% |
| SE | 58.32 mm | 59.64 mm | -2.2% | 58.9 to 63.4 | 23.62 mm | 24.21 mm | -2.4% |
| NW | 50.62 mm | 50.87 mm | -0.5% | 49.5 to 54.2 | 20.80 mm | 21.88 mm | -4.9% |
| SW | 41.00 mm | 38.68 mm | +6.0% | 41.2 to 43.6 | 18.80 mm | 19.35 mm | -2.8% |

**Red solids** (2 mm cut-off unless stated).

| Solid | Mesh area | Known area (15.1) | Difference | Mesh size | Calliper size | Mesh height | Calliper h |
|---|---|---|---|---|---|---|---|
| Prism, NW | 55.1 mm² | 51.6 mm² | +6.8% | 6.65 x 9.33 mm | 6.34 x 8.14 mm | 11.23 mm | 10.77 mm |
| Cylinder, SW | 49.8 mm² | 55.3 mm² | -9.9% | span 8.34 mm | ⌀ 8.39 mm | 7.79 mm | 7.73 mm |
| Sphere, SE | 45.4 mm² (59.6 at 1 mm, 38.6 at 3 mm, none at 5 mm) | 61.5 mm² | -26% (at 2 mm) | span 8.94 mm | ⌀ 8.85 mm | 5.71 mm | 6.78 mm |
| Circle, NE | not found | 78.5 mm² | | | | | |

**Base.** Seen from above 188.3 x 188.3 mm. No calliper or tape reading of it exists yet.

## What this shows and what it does not

- **Scale.** Where the mesh can resolve the feature, its lengths agree with the callipers: NE and
  NW spans and the cylinder diameter within 0.6%, SE -2.2%. Heights within -4.9% to +2.0%. No
  sign of a scale error larger than that. A tape reading of the 188.3 mm base side would be the
  best single check.
- **SW diameter.** The mesh reads 41.00 mm, the rig's photos 41.2 to 43.6, the callipers 38.68.
  Two instruments agree against the calliper figure, which 15.1 already calls an estimate. Open.
- **Rosette areas disagree with the rig by 10% to 39%, and neither is known to be right.** Known
  differences: the mesh is geometry only, so it counts the white centre beads, which the rig's
  green threshold leaves out; the rig's photos see the tops about 3.4% to 4.7% large from height
  (15.1), which goes the other way and makes the gap larger; the rig's colour thresholds miss
  blurred edges (shown on the red solids, 15.5). Likely, not measured: at a mean triangle of 3.39
  mm² the mesh widens thin leaves, which fits the largest gap being the thin-leaved SW.
- **Small solids depend on the method.** The prism and cylinder are within 10% of their known
  areas, but the sphere's area changes by half between cut-offs, and the flat circle is invisible
  to geometry. At this mesh size the red solids are not a useful area reference.
- **Use for validating the rig's captures.** The spans and heights are usable as a second check
  on the calliper figures. The rosette areas are not a reference area until the gap with the rig
  is explained; a capture at a finer detail level than `.mobile`, if the supervisor's software
  offers one, would be the first step.

Covers: one capture of one benchmark, one mesh. Does not cover repeatability of the
photogrammetry (one capture only), or any plant.
