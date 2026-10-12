## tag-map

The table, straightened on the four corner tags, so a spot on the map is the same real spot on the
table in every calibration run. Each calibration tag is filled with how far its size reads from the
middle (median) tag of this run: blue reads small, orange-red reads large, pale is normal. Tags more
than 1.5% off are also outlined in black. Grey means no tag: nothing is guessed between tags.

What to look for: a whole sheet in one colour usually means that sheet printed at the wrong size,
so measure it with callipers. Colour spread over the whole table, rather than one sheet, points at
the camera instead. The histogram under the map counts the tags at each distance from the median,
so one stray tag can be told from a group of them.

The colour range (2%) and the outline line (1.5%) are fixed choices, not measurements: a good run
stays pale. The scale is fitted to these same tags, so a whole bad sheet pulls the fit toward
itself and reads somewhat less far off than it really is. This is for setup only. How far a
measurement can be trusted comes from validation.

The map's proportions are those of the corner tags in the photo. The camera looks straight down,
so they are close to the real table, but they are not measured. Positions on the table are right
either way.

## radial-plot

Each dot is one calibration tag. Across: its distance from the centre of the photo, in pixels. Up
and down: how far its size reads from the fitted scale, in percent, with its sign kept. The line is
a straight fit through the dots.

Dots that climb or fall steadily toward the right (the frame corners) would mean lens distortion.
This is the one measurement that would justify modelling the lens (CLAUDE.md). A cloud with no
trend means no lens model is needed. The known low reading near the centre of the frame is a dip
at the left end, not a trend toward the corners, and does not count.

R² says how much of the up-and-down spread the straight line explains, from 0 (none) to 1 (all of
it). It ignores size: read the slope, in percent per pixel, with it. It only sees straight trends,
so read the dots too.
