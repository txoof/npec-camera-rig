"""Visual renderings of calibration data: the radial residual plot (the evidence gate for lens
distortion modelling, CLAUDE.md), the tag map with its histogram (where tags read far from the
run's norm, a setup aid), and the corner level overlay. Pure
rendering: every number drawn here already exists in `calibration.py`; nothing here measures or
derives anything new.
"""

from __future__ import annotations

import cv2
import numpy as np

from npec_rig.calibration import TableFrame
from npec_rig.text_render import draw_text, text_layer, text_width
from npec_rig.tripwire import CornerLevelReading

# A diagnostic image is for a human to glance at in a browser, not a measurement -- there is
# no reason to carry a real 64MP frame (and its ~190MB-plus of uint8 copies) through a resize,
# colour-map and blend just to shrink it back down for display. Capped well below the display's
# own resolution.
HEATMAP_MAX_WIDTH = 1600


# RGB. Amber (not a pure yellow) reads clearly against both a light table and a dark tray in
# the "drift" band.
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
    the real photo rather than a rotation-in-degrees number. Downscaled first, then drawn on.

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

    # Sized to the image, so the marks stay readable where the page shows it about a third of
    # its width (Aaron, 2026-10-13: "nearly invisible at 1024 scale").
    width = img.shape[1]
    radius = max(16, int(round(0.04 * width)))
    thickness = max(4, int(round(0.008 * width)))
    font = max(0.8, 0.0014 * width)
    if not readings:
        draw_text(
            img, "need at least 2 corner tags in frame to judge levelling",
            (20, int(45 * font)), font, (0, 0, 0), stroke_width=2,
        )
        return img

    labels = []
    for reading in readings:
        colour = _LEVEL_STATUS_COLOUR[reading.status]
        cx, cy = int(round(reading.centre[0] * scale)), int(round(reading.centre[1] * scale))
        _draw_level_mark(img, (cx, cy), radius, colour, thickness, reading.status)
        # The label goes on the side of the mark facing the image's middle, so it stays on it.
        text = f"{reading.deviation_pct:+.1f}%"
        gap = radius + thickness + 8
        x = cx + gap if cx < width / 2 else cx - gap - text_width(text, font)
        labels.append((text, (x, cy + int(12 * font)), colour))

    worst = max(readings, key=lambda r: abs(r.deviation_pct))
    if worst.status == "ok":
        caption = "co-planar within tolerance"
    else:
        direction = "closer" if worst.deviation_pct > 0 else "farther"
        caption = f"tag {worst.tag_id} reads {abs(worst.deviation_pct):.0f}% {direction} than the others"

    with text_layer(img) as t:
        for text, org, colour in labels:
            t.text(text, org, font, colour, stroke_width=3)
        # The caption in the middle at the top, between the two upper marks, and smaller than them.
        caption_font = 0.75 * font
        t.text(caption, ((width - text_width(caption, caption_font)) // 2, int(45 * caption_font)),
               caption_font, (0, 0, 0), stroke_width=2)

    return img


def _draw_level_mark(img, centre, radius, colour, thickness, status) -> None:
    """A shape as well as a color for each status, as the page's legend shows them (never color
    alone): a circle for ok, a triangle for drift, a circle with a cross for fail."""
    cx, cy = centre
    if status == "drift":
        points = np.array([
            (cx, cy - radius), (cx + int(radius * 0.87), cy + radius // 2), (cx - int(radius * 0.87), cy + radius // 2),
        ], dtype=np.int32)
        cv2.polylines(img, [points], True, colour, thickness, cv2.LINE_AA)
        return
    cv2.circle(img, (cx, cy), radius, colour, thickness, cv2.LINE_AA)
    if status == "fail":
        d = int(radius * 0.7)
        cv2.line(img, (cx - d, cy - d), (cx + d, cy + d), colour, thickness, cv2.LINE_AA)
        cv2.line(img, (cx - d, cy + d), (cx + d, cy - d), colour, thickness, cv2.LINE_AA)


RADIAL_PLOT_SIZE = 900
RADIAL_PLOT_MARGIN = 90
RADIAL_PLOT_TOP_MARGIN = 110


def radial_fit(points: list[tuple[float, float, int]]) -> tuple[float, float, float]:
    """The radial plot's straight line: `(slope, intercept, r_squared)` of an unweighted
    least-squares fit of each point's signed value (%) to its radius (px), `points` as for
    `render_radial_residual_plot`. The plot and the diagnostics readout both use it, so the two
    always show the same numbers. R**2 is 0 when every value is the same."""
    if len(points) < 2:
        raise ValueError(f"need at least 2 points for a radial fit, got {len(points)}")
    radii = np.array([p[0] for p in points])
    values = np.array([p[1] for p in points])
    slope, intercept = np.polyfit(radii, values, 1)
    ss_res = float(np.sum((values - (slope * radii + intercept)) ** 2))
    ss_tot = float(np.sum((values - values.mean()) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return float(slope), float(intercept), r_squared


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
    slope, intercept, r_squared = radial_fit(points)

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

    # All cv2 drawing (tick marks, scatter, fit/zero lines) before the text layer opens below:
    # `text_layer` snapshots `img` once at entry and writes that snapshot back on exit, so a cv2
    # draw call made inside the `with` block would be silently overwritten.
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

    point_colour = (30, 90, 200)  # RGB blue
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
            f"linear fit: slope {slope * 1000:+.2f}% per 1000 px, R^2 = {r_squared:.3f}, n = {n} tags",
            (margin, 70), 0.55, fit_colour,
        )
        t.text("distance from image centre (px)", (margin, size - margin + 40), 0.5, (0, 0, 0))
        t.text(f"{label} (%), signed", (10, top_margin - 15), 0.5, (0, 0, 0))

    return img


# The tag map's colour range and its "far out" line, in percent of length, measured from the
# run's own median. Decisions, not measurements (Aaron's plot review, issue #53): fixed, not
# stretched to each run's spread, so a good run stays pale instead of always showing a worst
# tag in full colour. Calibration residuals on this rig are about 0.5% (standard deviation,
# docs/metrology-log.md), so 1.5% is about 3 of them; a sheet printed at 96% reads about 4%
# small and saturates the scale. Revisit if real runs show these do not separate good from bad.
TAG_MAP_RANGE_PCT = 2.0
TAG_MAP_FAR_PCT = 1.5
TAG_MAP_CANVAS_DIM = 900
TAG_MAP_HEADER_PX = 110
TAG_MAP_HISTOGRAM_PX = 300
TAG_MAP_BIN_PCT = 0.25
TAG_MAP_SMALL_COLOUR = (30, 90, 210)  # RGB blue: tag reads small
TAG_MAP_LARGE_COLOUR = (210, 60, 20)  # RGB orange-red: tag reads large
TAG_MAP_NEUTRAL_COLOUR = (240, 240, 240)
_KEY_STEP = 150  # px from one legend entry to the next
_TAG_MAP_KEY = ((-TAG_MAP_RANGE_PCT, "reads small"), (0.0, "normal"), (TAG_MAP_RANGE_PCT, "reads large"))


def tag_map_colour(deviation_pct: float) -> tuple[int, int, int]:
    """Neutral at 0, blending to blue (reads small) or orange-red (reads large) at
    +/- `TAG_MAP_RANGE_PCT`, clipped beyond."""
    t = float(np.clip(deviation_pct / TAG_MAP_RANGE_PCT, -1.0, 1.0))
    end = TAG_MAP_SMALL_COLOUR if t < 0 else TAG_MAP_LARGE_COLOUR
    return tuple(int(round(n + (e - n) * abs(t))) for n, e in zip(TAG_MAP_NEUTRAL_COLOUR, end))


def _tag_map_extent(full_to_fraction: np.ndarray, tags: list[tuple[np.ndarray, float]]) -> tuple[float, float, float, float]:
    """`(u_low, u_high, v_low, v_high)`: the corner-tag square `[0, 1]^2` widened to take in every
    tag, plus a small margin. Sheets at the table's edge sit outside the corner tags' centres, and
    a map that cut them off would hide exactly the tags most likely to read far out."""
    u_low, u_high, v_low, v_high = 0.0, 1.0, 0.0, 1.0
    if tags:
        corners = np.concatenate([np.asarray(c, dtype=np.float64).reshape(-1, 2) for c, _ in tags])
        fractions = cv2.perspectiveTransform(corners.reshape(-1, 1, 2), full_to_fraction).reshape(-1, 2)
        u_low, v_low = min(u_low, float(fractions[:, 0].min())), min(v_low, float(fractions[:, 1].min()))
        u_high, v_high = max(u_high, float(fractions[:, 0].max())), max(v_high, float(fractions[:, 1].max()))
    margin = 0.02
    return u_low - margin, u_high + margin, v_low - margin, v_high + margin


def _tag_map_canvas_size(table_frame: TableFrame, u_span: float, v_span: float) -> tuple[int, int]:
    """`(width_px, height_px)` for a map covering `u_span` x `v_span` of the corner-tag square,
    in the proportions the corner tags have in the photo: the mean length of its top and bottom
    edges against its left and right. The camera looks straight down, so that is close to the
    real table's shape, but it is not measured, and the map says so."""
    tl, tr, br, bl = (np.array(p) for p in table_frame.corners_px)
    width_px = (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2
    height_px = (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2
    aspect = (v_span * height_px) / (u_span * width_px)  # height / width
    if aspect >= 1:
        return max(1, int(round(TAG_MAP_CANVAS_DIM / aspect))), TAG_MAP_CANVAS_DIM
    return TAG_MAP_CANVAS_DIM, max(1, int(round(TAG_MAP_CANVAS_DIM * aspect)))


def _tag_map_histogram(deviations: list[float], width: int) -> np.ndarray:
    """Count of tags per `TAG_MAP_BIN_PCT` band of deviation, each bar in its band's map colour,
    plus one bar at each end for everything beyond the colour range. Tells one far tag from a
    group of them, which the map alone does not."""
    edges = np.arange(-TAG_MAP_RANGE_PCT, TAG_MAP_RANGE_PCT + TAG_MAP_BIN_PCT / 2, TAG_MAP_BIN_PCT)
    values = np.array(deviations, dtype=float)
    inner, _ = np.histogram(np.clip(values, edges[0], edges[-1]), bins=edges)
    below = int(np.sum(values < edges[0]))
    above = int(np.sum(values > edges[-1]))
    inner[0] -= below  # clipped values landed in the end bins; count them in their own bars
    inner[-1] -= above
    counts = [below, *inner.tolist(), above]
    centres = [edges[0] - TAG_MAP_BIN_PCT / 2]
    centres += [(a + b) / 2 for a, b in zip(edges[:-1], edges[1:])]
    centres += [edges[-1] + TAG_MAP_BIN_PCT / 2]

    height = TAG_MAP_HISTOGRAM_PX
    img = np.full((height, width, 3), 255, dtype=np.uint8)
    left, right, top, bottom = 50, width - 20, 60, height - 60
    bar_width = (right - left) / len(counts)
    tallest = max(max(counts), 1)

    def bar_x(index: int) -> int:
        return int(round(left + index * bar_width))

    def value_x(pct: float) -> int:
        # The inner bins start one bar in, after the "beyond" bar.
        return int(round(left + bar_width + (pct - edges[0]) / TAG_MAP_BIN_PCT * bar_width))

    axis_colour = (60, 60, 60)
    for index, (count, centre) in enumerate(zip(counts, centres)):
        bar_height = int(round(count / tallest * (bottom - top)))
        if count:
            colour = tag_map_colour(centre)
            cv2.rectangle(img, (bar_x(index) + 2, bottom - bar_height), (bar_x(index + 1) - 2, bottom), colour, -1)
            cv2.rectangle(img, (bar_x(index) + 2, bottom - bar_height), (bar_x(index + 1) - 2, bottom), axis_colour, 1)
    cv2.line(img, (left, bottom), (right, bottom), axis_colour, 2)
    for pct in (-TAG_MAP_FAR_PCT, TAG_MAP_FAR_PCT):
        x = value_x(pct)
        for y in range(top, bottom, 12):
            cv2.line(img, (x, y), (x, min(y + 6, bottom)), (0, 0, 0), 2)

    with text_layer(img) as t:
        t.text("How many tags at each distance from the median", (left, 30), 0.6, (0, 0, 0))
        for index, count in enumerate(counts):
            if count:
                label = str(count)
                centre_x = (bar_x(index) + bar_x(index + 1)) // 2
                bar_height = int(round(count / tallest * (bottom - top)))
                t.text(label, (centre_x - text_width(label, 0.45) // 2, bottom - bar_height - 6), 0.45, (0, 0, 0))
        for pct in (-TAG_MAP_RANGE_PCT, -1.0, 0.0, 1.0, TAG_MAP_RANGE_PCT):
            label = "0%" if pct == 0 else f"{pct:+.1f}%"
            t.text(label, (value_x(pct) - text_width(label, 0.45) // 2, bottom + 20), 0.45, (0, 0, 0))
        beyond = f"beyond {TAG_MAP_RANGE_PCT:.0f}%"
        t.text(beyond, (bar_x(0), bottom + 40), 0.4, (0, 0, 0))
        t.text(beyond, (bar_x(len(counts)) - text_width(beyond, 0.4), bottom + 40), 0.4, (0, 0, 0))
        far = f"dashed lines: {TAG_MAP_FAR_PCT:.1f}% from the median"
        t.text(far, ((left + right) // 2 - text_width(far, 0.45) // 2, height - 8), 0.45, (0, 0, 0))
    return img


def render_tag_map(
    frame: np.ndarray,
    frame_scale: float,
    table_frame: TableFrame,
    tags: list[tuple[np.ndarray, float]],
) -> np.ndarray:
    """Where calibration tags read far from the run's norm (Aaron's plot review, issue #53): a
    setup aid for finding a sheet printed at the wrong size or a camera behaving poorly, not a
    claim about accuracy -- validation decides that.

    `frame` is the calibration photo already reduced, `frame_scale` its size relative to full
    resolution (`images.reduced_frame`). `tags` is `(corners, deviation_pct)` per calibration tag:
    its four corners in full-resolution pixels, and its scale residual minus the run's median
    residual, in percent of length.

    The photo is straightened on the four corner tags (`table_frame`) and greyed. Each tag's own
    square is filled with its colour; nothing is painted between tags, so no value is guessed
    where no tag was. Tags past `TAG_MAP_FAR_PCT` are also outlined in black, so the far ones do
    not depend on colour alone. A histogram of the same deviations, in the same colours, sits
    under the map.

    The scale is fitted to these same tags, so a whole bad sheet pulls the fit toward itself and
    reads somewhat less far out than it really is.
    """
    full_to_fraction = table_frame.as_matrix()
    u_low, u_high, v_low, v_high = _tag_map_extent(full_to_fraction, tags)
    canvas_width, canvas_height = _tag_map_canvas_size(table_frame, u_high - u_low, v_high - v_low)
    reduced_to_full = np.diag([1.0 / frame_scale, 1.0 / frame_scale, 1.0])
    sx, sy = canvas_width / (u_high - u_low), canvas_height / (v_high - v_low)
    fraction_to_canvas = np.array([[sx, 0.0, -u_low * sx], [0.0, sy, -v_low * sy], [0.0, 0.0, 1.0]])
    full_to_canvas = fraction_to_canvas @ full_to_fraction
    warped = cv2.warpPerspective(
        np.ascontiguousarray(frame[..., :3]), full_to_canvas @ reduced_to_full, (canvas_width, canvas_height)
    )
    grey = cv2.cvtColor(warped, cv2.COLOR_RGB2GRAY)
    canvas = cv2.cvtColor((grey * 0.5).astype(np.uint8), cv2.COLOR_GRAY2RGB)

    far_marks = []  # (centre, sign): far tags also carry a sign, so small and large differ by more than colour
    for corners, deviation in tags:
        points = cv2.perspectiveTransform(np.asarray(corners, dtype=np.float64).reshape(-1, 1, 2), full_to_canvas)
        polygon = np.round(points.reshape(-1, 2)).astype(np.int32)
        cv2.fillConvexPoly(canvas, polygon, tag_map_colour(deviation), cv2.LINE_AA)
        if abs(deviation) > TAG_MAP_FAR_PCT:
            cv2.polylines(canvas, [polygon], True, (0, 0, 0), 3, cv2.LINE_AA)
            centre = points.reshape(-1, 2).mean(axis=0)
            far_marks.append(((int(round(centre[0])), int(round(centre[1]))), "-" if deviation < 0 else "+"))
    if far_marks:
        with text_layer(canvas) as t:
            for centre, sign in far_marks:
                t.text(sign, centre, 0.6, (255, 255, 255), anchor="mm", stroke_width=1, stroke_fill=(0, 0, 0))

    # Wide enough for the legend's last entry, so its text is never cut off on a narrow map.
    legend_end = 20 + 3 * _KEY_STEP + 30 + text_width(f"outlined: over {TAG_MAP_FAR_PCT:.1f}%, marked - or +", 0.5) + 20
    width = max(canvas_width, legend_end)
    header = np.full((TAG_MAP_HEADER_PX, width, 3), 255, dtype=np.uint8)
    key_y = 62
    for index, (pct, _word) in enumerate(_TAG_MAP_KEY):
        x = 20 + index * _KEY_STEP
        cv2.rectangle(header, (x, key_y - 16), (x + 22, key_y + 6), tag_map_colour(pct), -1)
        cv2.rectangle(header, (x, key_y - 16), (x + 22, key_y + 6), (60, 60, 60), 1)
    far_x = 20 + 3 * _KEY_STEP
    cv2.rectangle(header, (far_x, key_y - 16), (far_x + 22, key_y + 6), (0, 0, 0), 3)
    with text_layer(header) as t:
        t.text("Tag size against the fitted scale, from this run's median", (20, 30), 0.7, (0, 0, 0))
        for index, (_pct, word) in enumerate(_TAG_MAP_KEY):
            t.text(word, (20 + index * _KEY_STEP + 30, key_y + 4), 0.5, (0, 0, 0))
        t.text(f"outlined: over {TAG_MAP_FAR_PCT:.1f}%, marked - or +", (far_x + 30, key_y + 4), 0.5, (0, 0, 0))
        t.text("Proportions as photographed, not measured. Grey: no tag.", (20, 96), 0.45, (0, 0, 0))

    body = np.full((canvas_height, width, 3), 255, dtype=np.uint8)
    body[:, :canvas_width] = canvas
    histogram = _tag_map_histogram([deviation for _corners, deviation in tags], width)
    return np.vstack([header, body, histogram])
