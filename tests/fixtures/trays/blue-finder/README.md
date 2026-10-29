# Blue finder fixtures (#331)

Quarter-size copies (1/4 linear, `cv2.INTER_AREA`, JPEG quality 90) of six stills, for the tray
finder's tests. Full-size px = 4 x fixture px. Made by the fixtures agent of #331 on 2026-10-29
from copies of the rigs' photos (script kept outside the repo; it only resizes and reads rig.db).

Expected values come from outside the finder (CLAUDE.md, *Test-first* rule 4): production
`tray_reading` rows, the rig's tag placement where Aaron's inspection accepted it, tray corners
marked by eye, and Aaron's tray counts from the held-out inspection (metrology log 20.1,
`experiments/round3-tray-outlines/heldout-truth.json` on branch `328-tray-outlines`). None comes
from running a tray finder.

| Fixture | Still (UTC) | What it shows | Expected |
|---|---|---|---|
| `pots-touching` | production `17cb7bfb`, 2026-10-19 11:38:54 (held-out 07) | 12 4x5 trays of black pots, touching in two rows, 30 mm tags in cell A1 | 12 centres, the rig's tag placement (Aaron: right) |
| `sheets-every-tray` | production `631bb6b5`, 2026-10-12 13:31:17 (held-out 14) | a calibration sheet on every tray | count 12 |
| `edge-tags` | production `44a9e96e`, 2026-10-15 12:03:50 (held-out 09) | 20 mm edge tags beside the trays, 30 mm tags in pots, a leaf sheet, a yellow card, empty trays | count 12 |
| `dev-2x2-untagged` | development `8cb40de9`, 2026-10-29 12:00:05 (#328 tuning still, layout L1) | 9 untagged 2x2 trays, N1 partly outside the frame | 9 centres from by-eye corners |
| `dark` | production `df206967`, 2026-10-29 05:16:53 (held-out 23) | lights off | count 0 |
| `a1-tags-sheet-on-tray` | production `df206967`, 2026-10-28 11:59:53 (held-out 22) | 12 trays of soil, 40 mm tags in cell A1, sheets on 3 trays | 12 centres from production `tray_reading` |

`expected.json`, per fixture: `full_size`, `factor` (4), `calibration` (the photo's) and
`calibration_used` (after twins), `scale_field` (`coeffs`, `mean_px_per_mm`, `residual_std_pct`:
`ScaleField(_coeffs=tuple(coeffs), _mean_px_per_mm=..., residual_std_pct=...)` rebuilds it),
`px_per_mm_centre`, `slots` (the calibration's slot layout), `tags` (every tag, full-size px,
`tag_id`, `centre`, `corners`, `side_mm_approx`; detected on the controller by #328, for faking
`detect_tags`), `count`, `trays` (centres, or null for count only), `truth` (the source),
`centre_tolerance_mm` (30, as in #328), and a `note` where useful.

Limits: the counts are one person's inspection of quarter-size pictures; tag placement is good to
about 10 mm (metrology log 15.5l); by-eye corners have the precision written in `truth`. No 1x1
or black tray is in any fixture.
