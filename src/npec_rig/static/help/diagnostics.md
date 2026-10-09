## area-shape-heatmap

Area-scale shape check — each tag's real pixel area (exact, from its four corners) compared to
treating it as a perfect square. The colour scale runs 0 to 0.5%, a range measured from
17 real calibration runs on this rig (2026-09-21). Flat/near-zero everywhere means squaring the
scale field is fine for area, not just length. Structured, growing toward the corners, is real
evidence area needs its own fit before canopy-area measurement relies on it.

The scale field only ever measures length (pixels per millimetre in one direction). Turning that
into an area conversion means squaring it, which is only exactly right if every tag's photographed
shape is a perfect square. Near a tilted table's edges, a real square can photograph as a slightly
non-square quadrilateral (a "keystone" shape), and squaring the length scale would silently miss
that.

Rather than model the lens or the table's tilt angle to predict this, it's measured directly: each
tag's real pixel area, computed exactly from its four detected corners, compared to what a perfect
square with that tag's own average side length would cover. A square is the largest-area shape
possible for a given average side length, so this comparison can only ever come out as zero (a
genuine square) or negative (some real distortion) — never positive.

What it means: answers "is squaring the length scale good enough for area, or does area need its
own correction before canopy-area measurement relies on it?" Flat/near-zero everywhere means
squaring is fine. Measured across 17 real calibration runs on this rig (2026-09-21): the worst tag
anywhere came out at -0.46%, and the pattern gets worse toward the table's corners in a way that
tracks position, not tag size or image noise — so it reads as a real, if very small, geometric
effect, not noise.

## table-position-view

Anchored to the four corner tags, which don't move, so "this spot on the picture" is the same real
spot on the table across different calibration runs, not tied to one specific photo's own tilt and
framing. Grey means no calibration tag was ever near that spot — not measured, regardless of
colour, never a guessed or smoothed-in value.

NOT TO SCALE (a square canvas) unless both table width and length were entered when this
calibration was run — relative position within the table is correct either way, but the
rectangle's own proportions only match the real table when both were measured and entered.

## best-worst-tag

Every calibration tag's own scale residual and area-shape distortion, sorted best to worst, so a
specific outlier tag can be found by ID and frame position rather than only seeing the heatmap's
average. Each plot's vertical axis is that run's own spread, not the heatmap's fixed 0 to 0.5%
scale — read the axis label baked into each image, not the colours above. Green marks
the best tag, red the worst, on both the sorted plot and the actual photo below it.

## radial-plot

A lens/parallax distortion signature is structured — residual trends with distance from the image
centre, with a consistent sign — not random scatter. That's the specific measurement that decides
whether picking up lens-distortion modelling is justified, so it's plotted directly rather than
guessed at: every tag's own signed residual (not folded to a percentage magnitude — a real
distortion trend has a sign) against its distance from the image centre, with an unweighted linear
fit and its R². No judgement is baked in here about whether a given R² counts as "structured" —
read the scatter and the fit yourself.
