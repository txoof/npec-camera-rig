"""Visual renderings of calibration confidence: a heatmap of `UncertaintyField` over a
calibration frame, the claimed-vs-actual scatter for PLAN.md's M2 "honesty plot" acceptance
test, and a sorted best-vs-worst-tag rank plot. Pure rendering -- every number drawn here already
exists in `calibration.py`; nothing here measures or derives anything new.
"""

from __future__ import annotations

from collections.abc import Callable

import cv2
import numpy as np

from npec_rig.calibration import AreaScaleField, TableFrame, UncertaintyField
from npec_rig.text_render import draw_text, text_layer, text_width
from npec_rig.tripwire import CornerLevelReading

# Fixed color scale, not per-image min/max: a heatmap that always stretches to fill its own
# range would look equally "hot" whether the worst spot is 2% or 20% uncertain, hiding exactly
# the honesty this feature exists to show. 0-8% covers every regional-coverage reading seen on
# this rig so far (tripwire.py's own DEFAULT_SCALE_FAIL_PCT is 8%, chosen independently) --
# revisit if a real reading exceeds it.
HEATMAP_MIN_PCT = 0.0
HEATMAP_MAX_PCT = 8.0

# The area-shape heatmap's own range, on a different scale entirely: `shape_factor_pct` is a
# pure quadrilateral-shape measure (kappa = shoelace area / mean-side-length**2 <= 1 always, a
# square is the max-area case for a given mean side), not a scale/coverage residual -- on this
# rig's actual geometry (top-down, small per-tag perspective) it is tiny. Measured, not guessed:
# reprocessing all 17 real calibration frames saved 2026-09-21 (2104 calibration tags total, no
# bench time -- TODO.md) gave |shape_factor_pct| in [0, 0.45], mean 0.05. 0.5 rounds that up;
# revisit if a real reading exceeds it, same as HEATMAP_MAX_PCT above.
AREA_SHAPE_HEATMAP_MIN_PCT = 0.0
AREA_SHAPE_HEATMAP_MAX_PCT = 0.5

HEATMAP_GRID = (40, 30)  # (columns, rows) -- coarse is fine, it's smoothly upsampled after
# A confidence heatmap is for a human to glance at in a browser, not a measurement -- there is
# no reason to carry a real 64MP frame (and its ~190MB-plus of uint8 copies) through a resize,
# colour-map and blend just to shrink it back down for display. Capped well below the display's
# own resolution.
HEATMAP_MAX_WIDTH = 1600

# `render_uncertainty_heatmap`'s `k` for the accuracy-shape view (Aaron/supervisor, 2026-09-25):
# how many nearby tags each pixel's estimate averages over. Chosen by comparing k=5/15/40/80/150
# against a real saved calibration (352 tags) -- 5 is the existing coverage-gap heatmap's own
# patchy default; 150 washed out a real, confirmed corner effect along with everything else; 40
# kept that real signal legible without the patch-to-patch noise. Revisit per-rig if tag count or
# coverage density differs enough that this balance stops holding.
ACCURACY_SHAPE_HEATMAP_K = 40

# The table view's own canvas scale -- matches the other diagnostic plots' scale in this module
# (RANK_PLOT_SIZE, RADIAL_PLOT_SIZE), not the frame's own resolution: a straightened floor-plan
# view is for a human to glance at, same reasoning as HEATMAP_MAX_WIDTH above.
TABLE_VIEW_CANVAS_DIM = 900
TABLE_VIEW_GRID = HEATMAP_GRID  # same coarse-then-upsample pattern as every heatmap in this file


def _grid_to_colormap(grid: np.ndarray, vmin: float, vmax: float, width: int, height: int) -> np.ndarray:
    """`grid` (coarse, already in the field's own units) clipped to `[vmin, vmax]`, normalized to
    0-255, colour-mapped and upsampled to `(height, width)` -- the clip-normalize-colormap step
    shared by every renderer in this module that turns a coarse percentage grid into a colour
    field (`render_pct_heatmap`, `render_table_view`), so the OOM-safety/colour-convention
    reasoning below lives once, not copy-pasted at each call site.
    """
    clipped = np.clip(grid, vmin, vmax)
    normalized = ((clipped - vmin) / (vmax - vmin) * 255.0).astype(np.uint8)
    upsampled = cv2.resize(normalized, (width, height), interpolation=cv2.INTER_LINEAR)

    # cv2.applyColorMap returns BGR, per OpenCV's own convention -- this project treats arrays as
    # RGB throughout (see camera.py's array_to_jpeg docstring), so the swap back is load-bearing,
    # not cosmetic.
    color_bgr = cv2.applyColorMap(upsampled, cv2.COLORMAP_TURBO)
    return cv2.cvtColor(color_bgr, cv2.COLOR_BGR2RGB)


def render_pct_heatmap(
    sample_at: Callable[[float, float], float],
    frame: np.ndarray,
    *,
    alpha: float = 0.45,
    vmin: float = HEATMAP_MIN_PCT,
    vmax: float = HEATMAP_MAX_PCT,
    max_width: int = HEATMAP_MAX_WIDTH,
) -> np.ndarray:
    """`frame` (RGB, see camera.py's array_to_jpeg) with a colour heatmap of `sample_at(x, y)`
    blended over it -- cool/blue at `vmin`, hot/red at `vmax`. Downscaled to `max_width` first;
    see `HEATMAP_MAX_WIDTH`. Shared rendering path for every per-position percentage field this
    module draws (`render_uncertainty_heatmap`, `render_area_shape_heatmap`) -- the OOM-safety
    comments below apply to all of them, not just the first one written.

    Sampled on a coarse grid and upsampled, not once per pixel: `sample_at` is typically a
    k-nearest-neighbour lookup over every detected tag, and the field varies smoothly, so a
    coarse grid costs far less compute for a visually identical result.
    """
    full_height, full_width = frame.shape[0], frame.shape[1]
    if full_width > max_width:
        scale = max_width / full_width
        frame = cv2.resize(
            np.ascontiguousarray(frame[..., :3]),
            (max_width, int(round(full_height * scale))),
            interpolation=cv2.INTER_AREA,
        )

    height, width = frame.shape[0], frame.shape[1]
    cols, rows = HEATMAP_GRID
    # Sampled in the *original* frame's coordinates -- `sample_at` was built from full-resolution
    # detections, so a downscaled grid position has to be scaled back up before querying it.
    xs = np.linspace(0, full_width - 1, cols)
    ys = np.linspace(0, full_height - 1, rows)
    grid = np.array(
        [[sample_at(float(x), float(y)) for x in xs] for y in ys],
        dtype=np.float32,
    )
    color_rgb = _grid_to_colormap(grid, vmin, vmax, width, height)

    # cv2.addWeighted blends in place in uint8, not three full-frame float32 copies (base,
    # colour, blended) -- at a real 64MP capture that float32 path allocated ~2.3GB of
    # short-lived temporaries and actually triggered the OOM killer on a second run (confirmed
    # in dmesg, not guessed), taking the whole camera worker down with it.
    base = np.ascontiguousarray(frame[..., :3])
    return cv2.addWeighted(base, 1 - alpha, color_rgb, alpha, 0)


def render_uncertainty_heatmap(
    field: UncertaintyField,
    frame: np.ndarray,
    *,
    k: int = 5,
    alpha: float = 0.45,
    vmin: float = HEATMAP_MIN_PCT,
    vmax: float = HEATMAP_MAX_PCT,
    max_width: int = HEATMAP_MAX_WIDTH,
) -> np.ndarray:
    """`frame` with a colour heatmap of `field.local_uncertainty_pct` blended over it -- cool/blue
    where confidence is high, hot/red where it's low. See `render_pct_heatmap`.

    `k` (default 5, matching `local_uncertainty_pct`'s own default) is the neighbourhood size.
    Small `k` is sensitive to exactly where sheet coverage is thin -- the "where do I need
    another tag" reading. Large `k` averages over many more tags, trading that local detail for
    the overall accuracy shape across the frame: round if the falloff toward the edges is even,
    elongated toward whichever side is worse if it isn't. Same real per-tag residuals either way
    -- no shape is assumed or fit, just a wider honest average (Aaron/supervisor, 2026-09-25; a
    range of k was compared against real saved calibration frames before picking 40 for the
    accuracy-shape view, see TODO.md).
    """
    return render_pct_heatmap(
        lambda x, y: field.local_uncertainty_pct(x, y, k=k),
        frame, alpha=alpha, vmin=vmin, vmax=vmax, max_width=max_width,
    )


def render_area_shape_heatmap(
    field: AreaScaleField,
    frame: np.ndarray,
    *,
    alpha: float = 0.45,
    vmin: float = AREA_SHAPE_HEATMAP_MIN_PCT,
    vmax: float = AREA_SHAPE_HEATMAP_MAX_PCT,
    max_width: int = HEATMAP_MAX_WIDTH,
) -> np.ndarray:
    """`frame` with a colour heatmap of `field.local_shape_factor_pct` blended over it -- TODO.md's
    area-scale shape check. Deliberately `shape_factor_pct`, not `area_error_pct`: see
    `calibration.AreaScaleSample`'s docstring for why heatmapping `area_error_pct` would mostly
    recolour the already-shipped `render_uncertainty_heatmap` at double magnitude, not show new
    structure. `vmin`/`vmax` default to `AREA_SHAPE_HEATMAP_MIN_PCT`/`_MAX_PCT` -- a much narrower
    range than the uncertainty heatmap's, because it's a different quantity on a different scale
    (see that constant's own comment for the measurement behind it), not a copy-paste. See
    `render_pct_heatmap`.
    """
    return render_pct_heatmap(
        field.local_shape_factor_pct, frame, alpha=alpha, vmin=vmin, vmax=vmax, max_width=max_width
    )


HONESTY_PLOT_SIZE = 640
HONESTY_PLOT_MARGIN = 70


def render_honesty_plot(
    points: list[tuple[float, float]],
    *,
    size: int = HONESTY_PLOT_SIZE,
    margin: int = HONESTY_PLOT_MARGIN,
    axis_max_pct: float | None = None,
) -> np.ndarray:
    """PLAN.md's M2 honesty plot: claimed uncertainty (x) vs actual measured error (y), one point
    per `(claimed_pct, actual_pct)` -- one per physical target position.

    Draws the y = x "honest" reference line: a point sitting on it means the claim matched
    reality; above it means the app under-claimed (actual error worse than claimed -- the
    dangerous direction); below it means it over-claimed (conservative, not dangerous). Whether
    the points scatter *randomly* around that line or drift with position is what CLAUDE.md's
    intrinsics evidence gate reads -- that judgement is Aaron's to make from where they land,
    this only draws them accurately. No threshold is baked in here.
    """
    if not points:
        raise ValueError("need at least one (claimed_pct, actual_pct) point to plot")

    claimed = [p[0] for p in points]
    actual = [p[1] for p in points]
    axis_max = axis_max_pct if axis_max_pct is not None else max(claimed + actual) * 1.15
    axis_max = max(axis_max, 1.0)  # never a zero-width axis

    plot_size = size - 2 * margin

    def to_px(value: float) -> int:
        return margin + int(round(value / axis_max * plot_size))

    def to_py(value: float) -> int:
        return size - margin - int(round(value / axis_max * plot_size))  # image y grows downward

    img = np.full((size, size, 3), 255, dtype=np.uint8)
    axis_color = (60, 60, 60)
    cv2.line(img, (margin, size - margin), (size - margin, size - margin), axis_color, 2)
    cv2.line(img, (margin, size - margin), (margin, margin), axis_color, 2)

    # y = x reference line -- "the claim exactly matched reality".
    cv2.line(
        img, (to_px(0), to_py(0)), (to_px(axis_max), to_py(axis_max)), (160, 160, 160), 1, cv2.LINE_AA
    )

    # All cv2 drawing happens before the text layer opens below -- `text_layer` snapshots `img`
    # once at entry and writes that snapshot back on exit, so any cv2 draw call made *inside*
    # the `with` block would be silently overwritten (lost) rather than composited.
    point_color = (30, 90, 200)  # RGB blue, reads clearly against the grey reference line
    centres = []
    for c, a in points:
        cx, cy = to_px(c), to_py(a)
        cv2.circle(img, (cx, cy), 6, point_color, -1, cv2.LINE_AA)
        centres.append((cx, cy))

    with text_layer(img) as t:
        for i, (cx, cy) in enumerate(centres, start=1):
            t.text(str(i), (cx + 8, cy - 8), 0.5, (0, 0, 0))
        t.text("claimed uncertainty (%)", (margin, size - margin + 40), 0.5, (0, 0, 0))
        t.text("actual error (%)", (10, margin - 15), 0.5, (0, 0, 0))

    return img


RANK_PLOT_SIZE = 900
RANK_PLOT_MARGIN = 90
RANK_PLOT_TOP_MARGIN = 130  # extra headroom above the plot for the title + key

BEST_COLOUR = (0, 150, 0)  # RGB green, used consistently across the rank plot and the photo
WORST_COLOUR = (210, 30, 30)  # RGB red


def render_rank_plot(
    points: list[tuple[float, int, float, float]],
    *,
    label: str,
    size: int = RANK_PLOT_SIZE,
    margin: int = RANK_PLOT_MARGIN,
    top_margin: int = RANK_PLOT_TOP_MARGIN,
) -> np.ndarray:
    """TODO.md's best-vs-worst-tag rank plot: `points` as `(magnitude_pct, tag_id, x, y)` tuples,
    one per calibration tag, sorted ascending and drawn as a single connected line (rank on x,
    magnitude on y) -- not one bar or marker per tag. With hundreds of calibration tags per run,
    individual bars would be unreadable; a monotonic line shows the whole distribution's shape
    for free (how many tags cluster near "good" vs. how sharply it kicks up at the tail) and
    stays legible at any tag count.

    Only the two ends are labelled: the best (lowest-magnitude) tag's value, and the worst
    (highest-magnitude) tag's value plus its `tag_id` and frame position, so that specific tag
    can be found and inspected physically. The y-axis auto-scales to this run's own worst value
    (with headroom), not a fixed cross-run scale like the heatmaps use -- this plot's job is
    showing the spread *within* one run, and the axis label says so explicitly to avoid it being
    mistaken for a heatmap's fixed comparison scale. A title and a green/red key are baked into
    the image itself (not left to the page around it), so a saved or screenshotted copy is still
    self-explanatory out of context.

    Raises ValueError with fewer than 2 points -- "best vs. worst" needs two distinct tags.
    """
    if len(points) < 2:
        raise ValueError(f"need at least 2 points for a rank plot, got {len(points)}")

    ordered = sorted(points, key=lambda p: p[0])
    values = [p[0] for p in ordered]
    n = len(ordered)
    axis_max = max(values[-1] * 1.15, 1e-9)

    img = np.full((size, size, 3), 255, dtype=np.uint8)
    plot_size = size - margin - top_margin
    axis_color = (60, 60, 60)
    cv2.line(img, (margin, size - margin), (size - margin, size - margin), axis_color, 2)
    cv2.line(img, (margin, size - margin), (margin, top_margin), axis_color, 2)

    def to_px(rank: int) -> int:
        return margin + int(round(rank / (n - 1) * (size - 2 * margin)))

    def to_py(value: float) -> int:
        return size - margin - int(round(value / axis_max * plot_size))

    line_color = (30, 90, 200)  # RGB blue, matches the honesty plot's point colour
    poly_points = np.array(
        [[to_px(i), to_py(v)] for i, v in enumerate(values)], dtype=np.int32
    ).reshape(-1, 1, 2)
    cv2.polylines(img, [poly_points], isClosed=False, color=line_color, thickness=3, lineType=cv2.LINE_AA)

    best_value, best_tag_id, best_x, best_y = ordered[0]
    worst_value, worst_tag_id, worst_x, worst_y = ordered[-1]

    # All cv2 drawing before the text layer opens -- see render_honesty_plot's comment on why.
    cv2.circle(img, (to_px(0), to_py(best_value)), 8, BEST_COLOUR, -1, cv2.LINE_AA)
    cv2.circle(img, (to_px(n - 1), to_py(worst_value)), 8, WORST_COLOUR, -1, cv2.LINE_AA)
    key_y = 75
    cv2.circle(img, (margin + 8, key_y), 8, BEST_COLOUR, -1, cv2.LINE_AA)
    cv2.circle(img, (margin + 100, key_y), 8, WORST_COLOUR, -1, cv2.LINE_AA)

    best_label = f"best: tag {best_tag_id}, {best_value:.2f}% ({best_x:.0f}, {best_y:.0f})"
    worst_label = f"worst: tag {worst_tag_id}, {worst_value:.2f}% ({worst_x:.0f}, {worst_y:.0f})"
    worst_text_width = text_width(worst_label, 0.6)

    with text_layer(img) as t:
        t.text(best_label, (margin, to_py(best_value) - 14), 0.6, BEST_COLOUR)
        t.text(
            worst_label, (size - margin - worst_text_width, to_py(worst_value) - 14),
            0.6, WORST_COLOUR,
        )
        t.text(f"{label}: best vs. worst tag", (margin, 40), 0.9, (0, 0, 0))
        t.text("best", (margin + 24, key_y + 6), 0.55, (0, 0, 0))
        t.text("worst", (margin + 116, key_y + 6), 0.55, (0, 0, 0))
        t.text(
            f"{label} (%), sorted best -> worst across {n} tags",
            (margin, size - margin + 40), 0.5, (0, 0, 0),
        )
        t.text(
            "this run's own spread -- not the heatmaps' fixed scale",
            (margin, size - margin + 60), 0.5, (0, 0, 0),
        )
        t.text(f"0-{axis_max:.2f}%", (10, top_margin - 15), 0.5, (0, 0, 0))

    return img


def render_best_worst_overlay(
    frame: np.ndarray,
    best: tuple[int, float, float, float],
    worst: tuple[int, float, float, float],
    *,
    label: str,
    max_width: int = HEATMAP_MAX_WIDTH,
) -> np.ndarray:
    """`frame` (RGB) with the best and worst calibration tags for `label` circled directly on
    the actual photo -- green for best, red for worst -- each labelled with its tag id and
    magnitude, so the worst tag can be found and inspected physically, not just read off the
    abstract rank plot's rank axis. `best`/`worst` are `(tag_id, x, y, magnitude_pct)`, in the
    frame's own full-resolution coordinates.

    Downscaled first, the same way the heatmaps are (see `HEATMAP_MAX_WIDTH`'s own comment): a
    full 64MP frame must never be carried through per-pixel drawing at full resolution.
    """
    full_height, full_width = frame.shape[0], frame.shape[1]
    scale = min(1.0, max_width / full_width)
    if scale < 1.0:
        img = cv2.resize(
            np.ascontiguousarray(frame[..., :3]),
            (int(round(full_width * scale)), int(round(full_height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    else:
        img = np.ascontiguousarray(frame[..., :3]).copy()

    radius = max(12, int(round(0.012 * img.shape[1])))
    key_y = img.shape[0] - 25
    labels = []
    for (tag_id, x, y, magnitude_pct), colour, tag_name in (
        (best, BEST_COLOUR, "best"),
        (worst, WORST_COLOUR, "worst"),
    ):
        cx, cy = int(round(x * scale)), int(round(y * scale))
        cv2.circle(img, (cx, cy), radius, colour, 4, cv2.LINE_AA)
        labels.append((f"{tag_name}: tag {tag_id}, {magnitude_pct:.2f}%", (cx + radius + 8, cy + 6), colour))
    cv2.circle(img, (30, key_y), 10, BEST_COLOUR, -1, cv2.LINE_AA)
    cv2.circle(img, (140, key_y), 10, WORST_COLOUR, -1, cv2.LINE_AA)

    with text_layer(img) as t:
        for text, org, colour in labels:
            t.text(text, org, 0.8, colour, stroke_width=2)
        t.text(f"{label}: best vs. worst tag", (20, 45), 1.1, (0, 0, 0), stroke_width=2)
        t.text("best", (48, key_y + 6), 0.7, (0, 0, 0), stroke_width=2)
        t.text("worst", (158, key_y + 6), 0.7, (0, 0, 0), stroke_width=2)

    return img


# RGB, same convention as BEST_COLOUR/WORST_COLOUR above. Amber (not a pure yellow) reads clearly
# against both a light table and a dark tray in the "drift" band.
LEVEL_OK_COLOUR = (0, 150, 0)
LEVEL_DRIFT_COLOUR = (210, 150, 0)
LEVEL_FAIL_COLOUR = (210, 30, 30)
_LEVEL_STATUS_COLOUR = {"ok": LEVEL_OK_COLOUR, "drift": LEVEL_DRIFT_COLOUR, "fail": LEVEL_FAIL_COLOUR}


def render_level_overlay(
    frame: np.ndarray,
    readings: list[CornerLevelReading],
    *,
    max_width: int = HEATMAP_MAX_WIDTH,
) -> np.ndarray:
    """`frame` (RGB) with each corner tag ringed green/amber/red by `CornerLevelReading.status`
    (see `tripwire.corner_level_readings`) -- for an installer levelling the rig by hand, reading
    the real photo rather than a rotation-in-degrees number. Same downscale-then-draw pattern as
    `render_best_worst_overlay`.

    `readings` may be empty (fewer than 2 corner tags currently detected) -- drawn as a plain
    frame with a caption saying so, not an error, since "can't judge yet" is itself useful
    feedback while an installer is still getting tags into frame.
    """
    full_height, full_width = frame.shape[0], frame.shape[1]
    scale = min(1.0, max_width / full_width)
    if scale < 1.0:
        img = cv2.resize(
            np.ascontiguousarray(frame[..., :3]),
            (int(round(full_width * scale)), int(round(full_height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    else:
        img = np.ascontiguousarray(frame[..., :3]).copy()

    radius = max(16, int(round(0.02 * img.shape[1])))
    if not readings:
        draw_text(
            img, "need at least 2 corner tags in frame to judge levelling",
            (20, 45), 1.0, (0, 0, 0), stroke_width=2,
        )
        return img

    labels = []
    for reading in readings:
        colour = _LEVEL_STATUS_COLOUR[reading.status]
        cx, cy = int(round(reading.centre[0] * scale)), int(round(reading.centre[1] * scale))
        cv2.circle(img, (cx, cy), radius, colour, 5, cv2.LINE_AA)
        labels.append((f"{reading.deviation_pct:+.1f}%", (cx + radius + 8, cy + 6), colour))

    worst = max(readings, key=lambda r: abs(r.deviation_pct))
    if worst.status == "ok":
        caption = "co-planar within tolerance"
    else:
        direction = "closer" if worst.deviation_pct > 0 else "farther"
        caption = f"tag {worst.tag_id} reads {abs(worst.deviation_pct):.0f}% {direction} than the others"

    with text_layer(img) as t:
        for text, org, colour in labels:
            t.text(text, org, 0.8, colour, stroke_width=2)
        t.text(caption, (20, 45), 1.0, (0, 0, 0), stroke_width=2)

    return img


RADIAL_PLOT_SIZE = 900
RADIAL_PLOT_MARGIN = 90
RADIAL_PLOT_TOP_MARGIN = 110


def render_radial_residual_plot(
    points: list[tuple[float, float, int]],
    *,
    label: str,
    size: int = RADIAL_PLOT_SIZE,
    margin: int = RADIAL_PLOT_MARGIN,
    top_margin: int = RADIAL_PLOT_TOP_MARGIN,
) -> np.ndarray:
    """PLAN.md's own evidence-gate measurement, drawn: signed `label` residual against distance
    from the image centre, one point per tag, `points` as `(radius_px, signed_value_pct, tag_id)`.
    A lens/parallax distortion signature is *structured* -- residuals trending with radius, with
    a consistent sign -- not random scatter; that's the specific test PLAN.md says decides
    whether intrinsic camera calibration is unbanned (deferred until this measurement, not
    banned outright). Signed, not `abs()`, on purpose: folding to magnitude would fold a genuine
    monotonic distortion trend in half and hide the exact shape being tested for.

    Raw scatter plus an unweighted least-squares linear fit and its R**2 -- no smoothing, no
    interpolation, no pre-judgement in code of whether the fit is "real": R**2 close to 0 means
    the scatter dominates (flat/random), close to 1 means radius genuinely predicts the residual
    (structured). That reading is left to whoever looks at the plot. "Distance from the image
    centre" is deliberately not called "the optical axis" -- the two aren't guaranteed to
    coincide, and this plot doesn't claim they do.

    Raises ValueError with fewer than 2 points -- a trend line needs at least two.
    """
    if len(points) < 2:
        raise ValueError(f"need at least 2 points for a radial residual plot, got {len(points)}")

    radii = np.array([p[0] for p in points])
    values = np.array([p[1] for p in points])
    n = len(points)

    slope, intercept = np.polyfit(radii, values, 1)
    fitted = slope * radii + intercept
    ss_res = float(np.sum((values - fitted) ** 2))
    ss_tot = float(np.sum((values - values.mean()) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    radius_max = max(float(radii.max()) * 1.05, 1e-9)
    value_span = max(float(np.abs(values).max()) * 1.15, 1e-9)

    img = np.full((size, size, 3), 255, dtype=np.uint8)
    plot_size = size - margin - top_margin
    axis_color = (60, 60, 60)
    cv2.line(img, (margin, size - margin), (size - margin, size - margin), axis_color, 2)
    cv2.line(img, (margin, size - margin), (margin, top_margin), axis_color, 2)

    def to_px(radius: float) -> int:
        return margin + int(round(radius / radius_max * (size - 2 * margin)))

    def to_py(value: float) -> int:
        # value_span covers +/- the same range either side of zero, zero at the plot's midline.
        mid = top_margin + plot_size / 2
        return int(round(mid - value / value_span * (plot_size / 2)))

    tick_colour = (60, 60, 60)

    # All cv2 drawing (tick marks, scatter, fit/zero lines) before the text layer opens below --
    # see render_honesty_plot's comment on why.
    x_ticks = []
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        radius_tick = frac * radius_max
        px = to_px(radius_tick)
        cv2.line(img, (px, size - margin), (px, size - margin + 6), tick_colour, 1, cv2.LINE_AA)
        x_ticks.append((px, f"{radius_tick:.0f}"))

    # Y-axis ticks: 5 evenly spaced values from -value_span to +value_span. The zero tick is
    # labelled explicitly ("0%") rather than left as an unlabelled reference line -- a line with
    # no number next to it answers "is this a trend" but not "a trend around what value".
    zero_colour = (170, 170, 170)
    y_ticks = []
    for frac in (-1.0, -0.5, 0.0, 0.5, 1.0):
        value_tick = frac * value_span
        py = to_py(value_tick)
        cv2.line(img, (margin - 6, py), (margin, py), tick_colour, 1, cv2.LINE_AA)
        y_ticks.append((py, f"{value_tick:+.2f}%" if value_tick != 0 else "0%"))
        if value_tick == 0:
            cv2.line(img, (margin, py), (size - margin, py), zero_colour, 1, cv2.LINE_AA)

    point_colour = (30, 90, 200)  # RGB blue, matches the honesty plot's own scatter colour
    for radius, value in zip(radii, values):
        cv2.circle(img, (to_px(radius), to_py(value)), 4, point_colour, -1, cv2.LINE_AA)

    fit_colour = (220, 120, 0)  # RGB orange, distinct from the scatter and the zero line
    fit_start = (to_px(0.0), to_py(intercept))
    fit_end = (to_px(radius_max), to_py(slope * radius_max + intercept))
    cv2.line(img, fit_start, fit_end, fit_colour, 3, cv2.LINE_AA)

    title = f"{label}: signed residual vs. distance from image centre"
    title_scale = 0.8
    available_width = size - 2 * margin
    title_width = text_width(title, title_scale)
    if title_width > available_width:
        title_scale *= available_width / title_width

    with text_layer(img) as t:
        for px, text in x_ticks:
            tick_text_width = text_width(text, 0.45)
            t.text(text, (px - tick_text_width // 2, size - margin + 22), 0.45, (0, 0, 0))
        for py, text in y_ticks:
            tick_text_width = text_width(text, 0.45)
            t.text(text, (margin - 12 - tick_text_width, py + 5), 0.45, (0, 0, 0))
        t.text(title, (margin, 40), title_scale, (0, 0, 0))
        t.text(
            f"linear fit: slope {slope:+.4f} %/px, R^2 = {r_squared:.3f}, n = {n} tags",
            (margin, 70), 0.55, fit_colour,
        )
        t.text("distance from image centre (px)", (margin, size - margin + 40), 0.5, (0, 0, 0))
        t.text(f"{label} (%), signed", (10, top_margin - 15), 0.5, (0, 0, 0))

    return img


def render_certainty_dome_plot(
    points: list[tuple[float, float, int]],
    *,
    size: int = RADIAL_PLOT_SIZE,
    margin: int = RADIAL_PLOT_MARGIN,
    top_margin: int = RADIAL_PLOT_TOP_MARGIN,
) -> np.ndarray:
    """An honest display of modeled area-measurement certainty as a function of distance from the
    image centre, where certainty *should* be highest (Aaron, 2026-09-25) -- claimed uncertainty
    (`UncertaintyField.local_uncertainty_pct`, already computed and persisted on every run, no new
    measurement) against distance from the image centre. `points` as `(radius_px,
    uncertainty_pct, tag_id)`, one per calibration tag. Unsigned, unlike
    `render_radial_residual_plot`'s signed residual -- a claimed uncertainty has no sign to fold.

    Same "no smoothing, no pre-judgement" approach as the radial residual plot: raw scatter plus
    an unweighted least-squares linear fit and its R**2. A "dome" need not be linear, but whether
    claimed uncertainty trends upward with radius at all -- confidence genuinely falling toward
    the edges, versus flat/noisy -- is the question this answers.

    Raises ValueError with fewer than 2 points -- a trend line needs at least two.
    """
    if len(points) < 2:
        raise ValueError(f"need at least 2 points for a certainty dome plot, got {len(points)}")

    radii = np.array([p[0] for p in points])
    values = np.array([p[1] for p in points])
    n = len(points)

    slope, intercept = np.polyfit(radii, values, 1)
    fitted = slope * radii + intercept
    ss_res = float(np.sum((values - fitted) ** 2))
    ss_tot = float(np.sum((values - values.mean()) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    radius_max = max(float(radii.max()) * 1.05, 1e-9)
    value_max = max(float(values.max()) * 1.15, 1e-9)

    img = np.full((size, size, 3), 255, dtype=np.uint8)
    plot_size = size - margin - top_margin
    axis_color = (60, 60, 60)
    cv2.line(img, (margin, size - margin), (size - margin, size - margin), axis_color, 2)
    cv2.line(img, (margin, size - margin), (margin, top_margin), axis_color, 2)

    def to_px(radius: float) -> int:
        return margin + int(round(radius / radius_max * (size - 2 * margin)))

    def to_py(value: float) -> int:
        return size - margin - int(round(max(value, 0.0) / value_max * plot_size))

    tick_colour = (60, 60, 60)

    # All cv2 drawing (tick marks, scatter, fit line) before the text layer opens below -- see
    # render_honesty_plot's comment on why.
    x_ticks = []
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        radius_tick = frac * radius_max
        px = to_px(radius_tick)
        cv2.line(img, (px, size - margin), (px, size - margin + 6), tick_colour, 1, cv2.LINE_AA)
        x_ticks.append((px, f"{radius_tick:.0f}"))

    # Y-axis ticks: 5 evenly spaced values from 0 to value_max -- unsigned, so no zero-midline
    # treatment like the radial residual plot's ± axis.
    y_ticks = []
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        value_tick = frac * value_max
        py = to_py(value_tick)
        cv2.line(img, (margin - 6, py), (margin, py), tick_colour, 1, cv2.LINE_AA)
        y_ticks.append((py, f"{value_tick:.2f}%"))

    point_colour = (30, 90, 200)  # RGB blue, matches every other scatter in this module
    for radius, value in zip(radii, values):
        cv2.circle(img, (to_px(radius), to_py(value)), 4, point_colour, -1, cv2.LINE_AA)

    fit_colour = (220, 120, 0)  # RGB orange, distinct from the scatter
    fit_start = (to_px(0.0), to_py(intercept))
    fit_end = (to_px(radius_max), to_py(slope * radius_max + intercept))
    cv2.line(img, fit_start, fit_end, fit_colour, 3, cv2.LINE_AA)

    title = "claimed uncertainty vs. distance from image centre"
    title_scale = 0.8
    available_width = size - 2 * margin
    title_width = text_width(title, title_scale)
    if title_width > available_width:
        title_scale *= available_width / title_width

    with text_layer(img) as t:
        for px, text in x_ticks:
            tick_text_width = text_width(text, 0.45)
            t.text(text, (px - tick_text_width // 2, size - margin + 22), 0.45, (0, 0, 0))
        for py, text in y_ticks:
            tick_text_width = text_width(text, 0.45)
            t.text(text, (margin - 12 - tick_text_width, py + 5), 0.45, (0, 0, 0))
        t.text(title, (margin, 40), title_scale, (0, 0, 0))
        t.text(
            f"linear fit: slope {slope:+.5f} %/px, R^2 = {r_squared:.3f}, n = {n} tags",
            (margin, 70), 0.55, fit_colour,
        )
        t.text("distance from image centre (px)", (margin, size - margin + 40), 0.5, (0, 0, 0))
        t.text("claimed uncertainty (%)", (10, top_margin - 15), 0.5, (0, 0, 0))

    return img


def _table_view_canvas_size(
    table_width_mm: float | None, table_length_mm: float | None
) -> tuple[int, int, bool]:
    """`(canvas_width_px, canvas_height_px, to_scale)`. Square (`to_scale=False`) unless *both*
    real dimensions were supplied, in which case the canvas's own aspect ratio matches them --
    never a plausible-looking but wrong rectangle from only one of the two.
    """
    if table_width_mm and table_length_mm:
        aspect = table_length_mm / table_width_mm  # height / width
        if aspect >= 1:
            height = TABLE_VIEW_CANVAS_DIM
            width = max(1, int(round(TABLE_VIEW_CANVAS_DIM / aspect)))
        else:
            width = TABLE_VIEW_CANVAS_DIM
            height = max(1, int(round(TABLE_VIEW_CANVAS_DIM * aspect)))
        return width, height, True
    return TABLE_VIEW_CANVAS_DIM, TABLE_VIEW_CANVAS_DIM, False


def _covered_hull_mask(
    table_frame: TableFrame,
    covered_positions: list[tuple[float, float]],
    canvas_width: int,
    canvas_height: int,
) -> np.ndarray:
    """Boolean mask, `True` inside the convex hull of `covered_positions` (original full-res pixel
    positions -- typically the calibration tags a field was actually built from) mapped into
    canvas space. A floor-plan view has no visible "table edge" cue the way a photo does, so
    anywhere never actually measured must read as unmeasured, not as a confident-looking colour
    borrowed from whichever tag happens to be nearest.
    """
    canvas_points = []
    for x, y in covered_positions:
        try:
            u, v = table_frame.to_fraction(x, y)
        except ValueError:
            continue
        canvas_points.append((u * canvas_width, v * canvas_height))

    mask = np.zeros((canvas_height, canvas_width), dtype=np.uint8)
    if len(canvas_points) < 3:
        return mask.astype(bool)  # can't form a hull from fewer than 3 points -- nothing covered
    hull = cv2.convexHull(np.array(canvas_points, dtype=np.float32))
    cv2.fillConvexPoly(mask, hull.astype(np.int32), 1)
    return mask.astype(bool)


def render_table_view(
    frame: np.ndarray,
    table_frame: TableFrame,
    sample_at: Callable[[float, float], float],
    covered_positions: list[tuple[float, float]],
    *,
    label: str,
    vmin: float,
    vmax: float,
    alpha: float = 0.55,
    table_width_mm: float | None = None,
    table_length_mm: float | None = None,
    max_width: int = HEATMAP_MAX_WIDTH,
) -> np.ndarray:
    """A straightened, top-down view of the table (via `table_frame`'s homography), with
    `sample_at`'s field painted on it the same way `render_pct_heatmap` paints one on the raw
    photo -- except this picture means the same real position every time, regardless of which
    calibration run produced it, because it's anchored to the four corner tags rather than to one
    specific photo's own tilt and framing.

    Two coordinate spaces are kept explicit throughout, not folded together by hand: `sample_at`
    is always queried in the *original, full-resolution* pixel coordinates it was built from
    (matching `render_pct_heatmap`'s own convention); only the photo warp itself composes
    pixel->fraction->canvas-pixel into one matrix, and only for `cv2.warpPerspective`'s sake.

    `frame` is downscaled to `max_width` first, same OOM guard as `render_pct_heatmap` (see
    `HEATMAP_MAX_WIDTH`'s own comment -- the dmesg-confirmed OOM this guards against is shared
    infrastructure, not re-derived here). The canvas is square with a baked-in "NOT TO SCALE"
    caveat unless both `table_width_mm`/`table_length_mm` are given (see
    `_table_view_canvas_size`) -- both must already be the real distance *centre-to-centre between
    the same four corner tags* `table_frame` was built from (see `TableFrame`'s own docstring), not
    the table's outer physical edge, or the aspect ratio silently won't match what's rendered.
    `table_width_mm` is specifically the TL-TR edge (`table_frame`'s own `u` axis, left-to-right
    in the camera image) and `table_length_mm` the TL-BL edge (`v`, top-to-bottom) -- swapping
    them renders a transposed rectangle, the exact "plausible-looking but wrong" failure this
    caveat exists to prevent.

    Callers do not measure centre-to-centre directly -- there's no mark on a tag's centre to put a
    tape measure to. `app.py`'s `run_calibration` is the one place that converts an operator's
    outer-edge-to-outer-edge tape measurement into the centre-to-centre distance this function
    expects (`_outer_edge_span_to_centre_distance_mm`), using the corner tags' own physical size.
    This function stays in terms of the clean, already-converted geometric quantity either way --
    it doesn't need to know how the caller obtained it.

    Anywhere outside the convex hull of `covered_positions` (see `_covered_hull_mask`) is rendered
    desaturated grey, not just lower alpha -- a floor-plan view has no visible "table edge" the
    way a photo does, so an unmasked extrapolated region would read as more confident than it is.
    A title and scale caveat are baked into the pixels, matching the precedent
    `render_rank_plot`/`render_radial_residual_plot` already set, so a saved/screenshotted copy
    stays self-explanatory out of context.
    """
    full_height, full_width = frame.shape[0], frame.shape[1]
    downscale = min(1.0, max_width / full_width)
    if downscale < 1.0:
        downscaled_frame = cv2.resize(
            np.ascontiguousarray(frame[..., :3]),
            (int(round(full_width * downscale)), int(round(full_height * downscale))),
            interpolation=cv2.INTER_AREA,
        )
    else:
        downscaled_frame = np.ascontiguousarray(frame[..., :3])

    canvas_width, canvas_height, to_scale = _table_view_canvas_size(table_width_mm, table_length_mm)

    # Three explicit matrices composed, not a hand-folded scale factor: `downscaled_to_full` maps
    # a *downscaled*-frame pixel back to the *full-res* pixel `table_frame`'s homography expects;
    # `homography` (pixel -> fraction) is `table_frame`'s own matrix; `fraction_to_canvas` maps
    # (u, v) in [0, 1]^2 onto the canvas's own pixel dimensions. `cv2.warpPerspective` wants the
    # forward map from its *source* image's pixels (the downscaled frame) to its *destination*
    # image's pixels (the canvas), which is exactly this product, applied right to left.
    downscaled_to_full = np.diag([1.0 / downscale, 1.0 / downscale, 1.0])
    homography = table_frame.as_matrix()
    fraction_to_canvas = np.diag([float(canvas_width), float(canvas_height), 1.0])
    warp_matrix = fraction_to_canvas @ homography @ downscaled_to_full

    warped_photo = cv2.warpPerspective(downscaled_frame, warp_matrix, (canvas_width, canvas_height))

    cols, rows = TABLE_VIEW_GRID
    grid = np.full((rows, cols), vmin, dtype=np.float32)
    valid = np.zeros((rows, cols), dtype=bool)
    xs = np.linspace(0, canvas_width - 1, cols)
    ys = np.linspace(0, canvas_height - 1, rows)
    for row, canvas_y in enumerate(ys):
        for col, canvas_x in enumerate(xs):
            u, v = canvas_x / canvas_width, canvas_y / canvas_height
            try:
                x, y = table_frame.to_pixel(u, v)
            except ValueError:
                continue  # outside the homography's physically valid domain -- left as invalid
            grid[row, col] = sample_at(x, y)
            valid[row, col] = True

    color_rgb = _grid_to_colormap(grid, vmin, vmax, canvas_width, canvas_height)
    blended = cv2.addWeighted(warped_photo, 1 - alpha, color_rgb, alpha, 0)

    valid_upsampled = (
        cv2.resize(valid.astype(np.uint8), (canvas_width, canvas_height), interpolation=cv2.INTER_NEAREST) > 0
    )
    hull_mask = _covered_hull_mask(table_frame, covered_positions, canvas_width, canvas_height)
    covered = valid_upsampled & hull_mask

    grey = cv2.cvtColor(cv2.cvtColor(warped_photo, cv2.COLOR_RGB2GRAY), cv2.COLOR_GRAY2RGB)
    result = np.where(covered[..., None], blended, grey)

    scale_note = (
        f"to scale: {table_width_mm:.0f}mm x {table_length_mm:.0f}mm, centre-to-centre "
        "between corner tags"
        if to_scale
        else "NOT TO SCALE -- width/length not entered; shows relative position only"
    )
    with text_layer(result) as t:
        t.text(f"{label}: table-position view", (20, 40), 1.0, (0, 0, 0), stroke_width=2)
        t.text(scale_note, (20, canvas_height - 20), 0.6, (0, 0, 0), stroke_width=2)
        t.text("grey = never measured near here", (20, canvas_height - 44), 0.6, (0, 0, 0), stroke_width=2)

    return result
