"""Visual renderings of calibration confidence: a heatmap of `UncertaintyField` over a
calibration frame, the claimed-vs-actual scatter for PLAN.md's M2 "honesty plot" acceptance
test, and a sorted best-vs-worst-tag rank plot. Pure rendering -- every number drawn here already
exists in `calibration.py`; nothing here measures or derives anything new.
"""

from __future__ import annotations

from collections.abc import Callable

import cv2
import numpy as np

from npec_rig.calibration import AreaScaleField, UncertaintyField

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

    clipped = np.clip(grid, vmin, vmax)
    normalized = ((clipped - vmin) / (vmax - vmin) * 255.0).astype(np.uint8)
    upsampled = cv2.resize(normalized, (width, height), interpolation=cv2.INTER_LINEAR)

    # cv2.applyColorMap returns BGR, per OpenCV's own convention -- this project treats arrays as
    # RGB throughout (see camera.py's array_to_jpeg docstring), so the swap back is load-bearing,
    # not cosmetic.
    color_bgr = cv2.applyColorMap(upsampled, cv2.COLORMAP_TURBO)
    color_rgb = cv2.cvtColor(color_bgr, cv2.COLOR_BGR2RGB)

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
    alpha: float = 0.45,
    vmin: float = HEATMAP_MIN_PCT,
    vmax: float = HEATMAP_MAX_PCT,
    max_width: int = HEATMAP_MAX_WIDTH,
) -> np.ndarray:
    """`frame` with a colour heatmap of `field.local_uncertainty_pct` blended over it -- cool/blue
    where confidence is high, hot/red where it's low. See `render_pct_heatmap`.
    """
    return render_pct_heatmap(
        field.local_uncertainty_pct, frame, alpha=alpha, vmin=vmin, vmax=vmax, max_width=max_width
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

    point_color = (30, 90, 200)  # RGB blue, reads clearly against the grey reference line
    for i, (c, a) in enumerate(points, start=1):
        cx, cy = to_px(c), to_py(a)
        cv2.circle(img, (cx, cy), 6, point_color, -1, cv2.LINE_AA)
        cv2.putText(
            img, str(i), (cx + 8, cy - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA
        )

    cv2.putText(
        img, "claimed uncertainty (%)", (margin, size - margin + 40),
        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA,
    )
    cv2.putText(
        img, "actual error (%)", (10, margin - 15),
        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA,
    )

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

    cv2.circle(img, (to_px(0), to_py(best_value)), 8, BEST_COLOUR, -1, cv2.LINE_AA)
    cv2.circle(img, (to_px(n - 1), to_py(worst_value)), 8, WORST_COLOUR, -1, cv2.LINE_AA)

    font = cv2.FONT_HERSHEY_SIMPLEX
    best_label = f"best: tag {best_tag_id}, {best_value:.2f}% ({best_x:.0f}, {best_y:.0f})"
    cv2.putText(img, best_label, (margin, to_py(best_value) - 14), font, 0.6, BEST_COLOUR, 2, cv2.LINE_AA)
    worst_label = f"worst: tag {worst_tag_id}, {worst_value:.2f}% ({worst_x:.0f}, {worst_y:.0f})"
    worst_text_width = cv2.getTextSize(worst_label, font, 0.6, 2)[0][0]
    cv2.putText(
        img, worst_label, (size - margin - worst_text_width, to_py(worst_value) - 14),
        font, 0.6, WORST_COLOUR, 2, cv2.LINE_AA,
    )

    cv2.putText(img, f"{label}: best vs. worst tag", (margin, 40), font, 0.9, (0, 0, 0), 2, cv2.LINE_AA)

    key_y = 75
    cv2.circle(img, (margin + 8, key_y), 8, BEST_COLOUR, -1, cv2.LINE_AA)
    cv2.putText(img, "best", (margin + 24, key_y + 6), font, 0.55, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.circle(img, (margin + 100, key_y), 8, WORST_COLOUR, -1, cv2.LINE_AA)
    cv2.putText(img, "worst", (margin + 116, key_y + 6), font, 0.55, (0, 0, 0), 1, cv2.LINE_AA)

    cv2.putText(
        img, f"{label} (%), sorted best -> worst across {n} tags",
        (margin, size - margin + 40), font, 0.5, (0, 0, 0), 1, cv2.LINE_AA,
    )
    cv2.putText(
        img, "this run's own spread -- not the heatmaps' fixed scale",
        (margin, size - margin + 60), font, 0.5, (0, 0, 0), 1, cv2.LINE_AA,
    )
    cv2.putText(img, f"0-{axis_max:.2f}%", (10, top_margin - 15), font, 0.5, (0, 0, 0), 1, cv2.LINE_AA)

    return img


def _put_text_with_halo(
    img: np.ndarray, text: str, org: tuple[int, int], font_scale: float, colour: tuple[int, int, int],
    thickness: int,
) -> None:
    """`text` drawn twice -- a thick white outline, then the real colour on top -- so it stays
    legible over a real photo's own unpredictable background, unlike the rank plot's plain white
    canvas where a single colour is enough.
    """
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(img, text, org, font, font_scale, (255, 255, 255), thickness + 3, cv2.LINE_AA)
    cv2.putText(img, text, org, font, font_scale, colour, thickness, cv2.LINE_AA)


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
    for (tag_id, x, y, magnitude_pct), colour, tag_name in (
        (best, BEST_COLOUR, "best"),
        (worst, WORST_COLOUR, "worst"),
    ):
        cx, cy = int(round(x * scale)), int(round(y * scale))
        cv2.circle(img, (cx, cy), radius, colour, 4, cv2.LINE_AA)
        _put_text_with_halo(
            img, f"{tag_name}: tag {tag_id}, {magnitude_pct:.2f}%",
            (cx + radius + 8, cy + 6), 0.8, colour, 2,
        )

    _put_text_with_halo(img, f"{label}: best vs. worst tag", (20, 45), 1.1, (0, 0, 0), 2)

    key_y = img.shape[0] - 25
    cv2.circle(img, (30, key_y), 10, BEST_COLOUR, -1, cv2.LINE_AA)
    _put_text_with_halo(img, "best", (48, key_y + 6), 0.7, (0, 0, 0), 2)
    cv2.circle(img, (140, key_y), 10, WORST_COLOUR, -1, cv2.LINE_AA)
    _put_text_with_halo(img, "worst", (158, key_y + 6), 0.7, (0, 0, 0), 2)

    return img
