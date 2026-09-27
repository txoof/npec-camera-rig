## confidence-heatmap

Colour is the local uncertainty field at that position — how much neighbouring calibration tags
disagree with the fitted scale, blended over the actual photo (so the sheets and table are still
visible underneath). Blue/dark = tags there agree closely with each other and the model — trust
readings from that area. Green through red = growing disagreement — the fixed 0–8% scale is used
every time so a hotter run really is worse, not just redrawn to look worse. Red doesn't mean
"wrong," it means "least measured" — usually because coverage is thin there; add a sheet in a red
area to bring it down.

Every calibration tag's real size is measured with callipers, not taken from the packaging (the
single biggest source of error found in this project's history — a "30 mm" tag actually measured
29.3106 mm, a ~4.7% error in area if trusted). From that measured size and the tag's four detected
corners, each tag gives a real, measured scale (pixels per millimetre) at its own spot in the
photo.

Those measured scales are fitted to a single tilted plane (a camera looking down at an angle sees
things nearer the lens as "bigger per millimetre" than things farther away — a plane is the
simplest shape that captures that). The percentage shown at any point on the photo is not that fit
directly: it is how far off the fit was for the 5 calibration tags physically nearest that point,
combined so that tags reading slightly big and slightly small don't cancel each other out to zero
— an even split either way still counts as real disagreement.

What it means: a direct, measured estimate of how far a canopy-area reading at that spot could be
off, based on how consistent the real calibration tags near it actually were — not a theoretical
lens or camera error estimate. Blue genuinely means "several nearby tags agreed closely." Red
usually means thin coverage nearby, not a fault in the camera or the maths.

Caveat: "5 nearest tags" has no distance limit. A spot with no real coverage anywhere near it
still gets a colour, borrowed from whichever tags happen to be closest in the photo, however far
that really is. Blue in a completely uncovered area (e.g. off the edge of the table) means "the
nearest real measurements happened to agree," not "this spot was actually measured."

## accuracy-shape

Same real per-tag measurements as the confidence heatmap, averaged over many more neighbouring
tags (40, instead of 5) — trading the "exactly where is coverage thin" detail for the overall
accuracy shape across the frame. Round means the falloff toward the edges is even; lopsided toward
one side means something physically off that direction. Nothing here is fitted or idealized — it's
the same honest measurements, just averaged more widely.

## area-shape-heatmap

Area-scale shape check — each tag's real pixel area (exact, from its four corners) compared to
treating it as a perfect square, isolated from the ordinary scale residual shown above. Note the
scale here is 0–0.5%, not 0–8% like the confidence heatmap — a much narrower range, measured from
17 real calibration runs on this rig (2026-09-21). Flat/near-zero everywhere means squaring the
scale field is fine for area, not just length. Structured, growing toward the corners, is real
evidence area needs its own fit before canopy-area measurement relies on it — as opposed to the
confidence heatmap being hot in the same place, which just means "add coverage there," not "area
needs its own fit."

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

Caveat: this heatmap uses a much narrower colour scale (0–0.5%) than the confidence heatmap
(0–8%), stretched to fill the same blue-to-red range either way. The two images can look equally
"hot" by eye at completely different real magnitudes — only the printed percentages say which is
actually bigger. The two numbers also measure different things and aren't copies of each other.

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
specific outlier tag can be found by ID and frame position rather than only seeing the two
heatmaps' averages. Each plot's vertical axis is that run's own spread, not the heatmaps' fixed
0–8%/0–0.5% scale — read the axis label baked into each image, not the colours above. Green marks
the best tag, red the worst, on both the sorted plot and the actual photo below it.

## radial-plot

A lens/parallax distortion signature is structured — residual trends with distance from the image
centre, with a consistent sign — not random scatter. That's the specific measurement that decides
whether picking up lens-distortion modelling is justified, so it's plotted directly rather than
guessed at: every tag's own signed residual (not folded to a percentage magnitude — a real
distortion trend has a sign) against its distance from the image centre, with an unweighted linear
fit and its R². No judgement is baked in here about whether a given R² counts as "structured" —
read the scatter and the fit yourself.

## certainty-dome

Claimed uncertainty (already computed and saved by this run) sampled at each calibration tag's own
position, plotted against distance from the image centre, with an unweighted linear fit and its
R². Certainty should be highest at the centre and fall toward the edges — a "dome" shape. This
shows whether the claimed number actually behaves that way, or is flat/noisy instead.
