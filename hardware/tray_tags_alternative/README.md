# Alternative tray tags (version 2)

A second generation of tray tags, developed on 2026-10-08 and parked here. It is **not** the tray
tag in use. The tray tag in use is `../tray_tags/apriltag_tray_tag.scad`, which `../tray_tags.py`
exports. Nothing in the repo uses or exports the files in this folder.

All four designs have since been carried into that file as styles, with the same geometry: 4x4
as `lip` and 1x1 as `lip_bolt` (RV1.18), black_tray as `disc` (RV1.16, RV1.18), and 4x5 as
`lip_round` (RV1.19), now the 4x5 default. Their exports match this file's except for the
revision engraved on them. This file is kept as the record of how the designs were made.

## Files

| File | What |
|---|---|
| `apriltag_tray_tag.scad` | The version 2 tray tag, RV2.1. Four designs, chosen from the tag id. Its header holds the full description and change history (REV 1.0 to 2.1) |
| `tag_outline_61.scad` | 2D outline of the physical 61 mm part the 4x5 design is copied from, with its 48.84 mm reference circle. For a 1:1 paper check |
| `tag_outline_61.pdf` | That outline exported on A4 with OpenSCAD's mm rulers. Print at 100% |

## How it works

### The id picks the design

Each tag's id gives its tray type through `tray_type()`, and the tray type picks the design.
There is no style setting: one layout can hold several designs.

| IDs | Tray type | Design | On the bed |
|---|---|---|---|
| 1-75 | `4x5` | 60.5 mm square, 9.33 mm corners, 40 mm tag, lip | standing on the lip |
| 76-150 | `4x4` | 61 mm square, 3 mm corners, 42 mm tag, lip | standing on the lip |
| 151-225 | `1x1` | the 4x4 plus an M8 bolt tab, flush with the +X edge | standing on the tab's edge |
| 226-250 | `black_tray` | 51 mm disc, 30 mm tag, no lip | flat |
| 251-299 | `OTHER` | no design: the render stops with an assert | |

All plates are 3 mm thick (`plate_thk`). Tag sizes are the black border edge to edge.

**The 226-250 black_tray range is not in the official allocation.** PLAN.md and `tray_tags.py`
still have 226-299 as `OTHER`. Adopting this file means adding the range there too (see
*Adopting version 2*).

### The designs

- **4x5.** The outline of the physical part. Its 9.33 mm corner radius was derived, not
  measured: the physical part's gap across the corner to the 48.84 mm reference circle measured
  14.8 to 14.9 mm, and `r = (s/2 * sqrt(2) - d/2 - g) / (sqrt(2) - 1)` gives 9.33 mm for
  14.85 mm. Each 0.1 mm in that gap moves r by 0.24 mm. The plate was later made 0.5 mm smaller
  overall (61 to 60.5 mm, REV 2.1). The 40 mm tag's white border has 5.25 mm of plate past it on
  the flat sides and is 2.25 mm clear of the lip.
- **4x4.** A 61 mm square with 3 mm corners and a 42 mm tag (5.25 mm bits). The lip limits the
  tag size here: 44 mm at most with a 1-bit white border; 42 mm leaves 1.25 mm clear of the lip.
- **1x1.** The 4x4 plus the version 1 bolt tab: 25 mm long, 20 mm wide, round end, 8.4 mm M8
  clearance hole (ISO 273 fine), 3 mm fillet where it meets the plate. It leaves the -Y edge
  (opposite the lip), flush with the +X edge, on the same side as the type label.
- **black_tray.** A 51 mm disc with a 30 mm tag and no lip. The largest tag with its whole white
  border inside the disc is 28.8 mm. At 30 mm the disc cuts about 1 mm off each corner of the
  white border, while along the edges the border is a full bit (3.75 mm). The 30 mm size is a
  trial, still to be tested for detection.

### The lip

The 4x5, 4x4 and 1x1 have a lip along the +Y edge: 5 mm above the top face (`lip_h`), 3 mm thick
(`lip_thk`). It is the band of the plate outline within `lip_thk` of the +Y edge, so its ends
follow the rounded corners. Its outer face is flush with the plate's +Y edge.

### Labels

All engraved, 0.6 mm deep, in the white body, so they print in the body color.

| Label | 4x5, 4x4, 1x1 | black_tray |
|---|---|---|
| Tag id | top face, top-left corner | top face, centred above the tag |
| Tray type | top face, top-right corner | top face, centred below the tag |
| Tag size, e.g. `40.0 x 40.0 mm` | in the white border below the tag | in the white border below the tag |
| Revision | lip's inner face, left end, 3 mm | underside, centred, mirrored |
| File name (`part_name`) | lip's inner face, right end, 3 mm | none |

The tag size label is the size the model draws. Measure the printed tag with callipers; the
measured value is the one the software should use.

### Print orientation

With `on_side = true` (the default):

- 4x5 and 4x4 rotate -90 deg about X and stand on the lip's outer face. The tag faces +Y.
- 1x1 rotates 90 deg about Y and stands on its +X edge, the edge the bolt tab is flush with, so
  the tab lies along the bed.
- black_tray always lies flat, whatever `on_side` says.

With `on_side = false` every tag lies flat. Every tag rests on Z = 0 in both cases. A layout that
mixes designs spaces every tag by the largest footprint in it.

### Construction

Two colors, one print, as in version 1: `lip_tag_body(id)` is the white body (plate, lip, tab,
engravings), `lip_tag_graphic(id)` the black tag layer from `../libraries/apriltag_36h11.scad`.
The black layer stands 0.6 mm proud (`tag_raise_h`) and sinks 0.2 mm into the plate
(`tag_embed`, a starting value, not measured). The layout loop stays at the top level so each
colored solid is its own lazy-union object for `scad_to_3mf.py`.

### Customizer groups

| Group | Sets |
|---|---|
| Tag | `tag_ids`, `tag_raise_h`, `tag_embed` |
| Plate | `plate_thk`, all designs |
| 4x5 Design | `t45_plate_w`, `t45_corner_r`, `t45_tag_size` |
| 4x4 and 1x1 Design | `t44_plate_w`, `t44_corner_r`, `t44_tag_size` |
| black_tray Design | `tbk_dia`, `tbk_tag_size` |
| 1x1 Bolt Tab | `bolt_tab_len`, `bolt_tab_w`, `bolt_dia`, `bolt_tab_fillet` |
| Lip | `lip_h`, `lip_thk` |
| ID Label | `id_label`, `id_size`, `id_depth`, `id_font`, `size_label`, `type_label` |
| Label | `part_name`, `name_size`, `name_depth`, `lbl_inset` |
| Build Plate | `on_side`, `plate_gap`, `side_gap`, `plate_cols` |
| Revision | `revision`, `rev_size`, `rev_depth` |

Asserts stop the render when a white border would run past the outline or under the lip, a
label would not fit, an id is outside 1-299, or an id's type has no design.

## Rendering and exporting

From `hardware/`. `tray_tags.py` does not drive this file, so export with `scad_to_3mf.py`
directly, one group at a time:

```sh
# one 4x5 tag, standing; writes exports/tray_tags_alternative/4x5/apriltag_tray_tag_4x5_1.3mf
uv run scad_to_3mf.py tray_tags_alternative/apriltag_tray_tag.scad \
    -o exports/tray_tags_alternative/4x5 -n apriltag_tray_tag_4x5_1 -D 'tag_ids=[1]'

# twelve black_tray tags
uv run scad_to_3mf.py tray_tags_alternative/apriltag_tray_tag.scad \
    -o exports/tray_tags_alternative/black_tray -n apriltag_tray_tag_black_tray_226-237 \
    -D 'tag_ids=[for (i = [226:237]) i]'

# the paper outline, A4 with rulers
/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD -o tray_tags_alternative/tag_outline_61.pdf \
    tray_tags_alternative/tag_outline_61.scad
```

Keep each group inside one tray type so the file name says which. Expect `1 object(s), 2 parts`
per tag.

## Name references in the header

The header was written while this file was being made, so some of its names refer to that time:

- `apriltag_lip_tag.scad` was this file's name until REV 2.0.
- `apriltag_tray_tags_v1.scad` means version 1, which is `../tray_tags/apriltag_tray_tag.scad`
  (RV1.14). The v1 file name was never kept.
- `part_name` is `apriltag_tray_tag`, the same engraving as version 1. The revision (RV2.x
  against RV1.x) tells the prints apart. Change `part_name` if that is not enough.

## Adopting version 2

On 2026-10-08 this file briefly replaced the tray tag in use. That change was reverted; only the
`.scad` files and this write-up were kept. To adopt it again:

1. Rename `../tray_tags/apriltag_tray_tag.scad` to a v1 name and move this file into its place.
2. `../tray_tags.py`: add `(226, 250, "black_tray")` and make `OTHER` 251-299 in `TRAY_TYPES`;
   replace `STYLES` and `DEFAULT_STYLE` with a table of designed types (`designed` in the
   `.scad`), refuse groups of an undesigned type and any `:style` suffix, drop the style from
   the file name and the `tag_style` define.
3. PLAN.md's tag ID allocation and `../README.md`'s tray type table: add 226-250 black_tray.
4. Version 1's `tray_type()` and header: add 226-250 black_tray, and refuse those ids (its
   corner is too small for the "black_tray" label).
5. Re-export every range.

## Open items

- black_tray: does a 30 mm tag with clipped white-border corners detect reliably?
- Is the 3 mm lip text legible in print?
- How well does the 1x1 stand on its edge?
- `OTHER` has no design.
- Possible next step, discussed and not started: a single file with a style setting (L tag from
  version 1 with a set total Y depth, lip, bolt without lip, flat, round), the tag size derived
  from the plate, and a manifest that `tray_tags.py --all` rebuilds after every change.
