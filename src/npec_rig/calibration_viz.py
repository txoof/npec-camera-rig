"""Visual renderings of calibration confidence: a heatmap of `UncertaintyField` over a
calibration frame, and the claimed-vs-actual scatter for PLAN.md's M2 "honesty plot" acceptance
test. Pure rendering -- every number drawn here already exists in `calibration.py`; nothing here
measures or derives anything new.
"""

from __future__ import annotations

import cv2
import numpy as np

from npec_rig.calibration import UncertaintyField

# Fixed color scale, not per-image min/max: a heatmap that always stretches to fill its own
# range would look equally "hot" whether the worst spot is 2% or 20% uncertain, hiding exactly
# the honesty this feature exists to show. 0-8% covers every regional-coverage reading seen on
# this rig so far (tripwire.py's own DEFAULT_SCALE_FAIL_PCT is 8%, chosen independently) --
# revisit if a real reading exceeds it.
HEATMAP_MIN_PCT = 0.0
HEATMAP_MAX_PCT = 8.0
HEATMAP_GRID = (40, 30)  # (columns, rows) -- coarse is fine, it's smoothly upsampled after
# A confidence heatmap is for a human to glance at in a browser, not a measurement -- there is
# no reason to carry a real 64MP frame (and its ~190MB-plus of uint8 copies) through a resize,
# colour-map and blend just to shrink it back down for display. Capped well below the display's
# own resolution.
HEATMAP_MAX_WIDTH = 1600


def render_uncertainty_heatmap(
    field: UncertaintyField,
    frame: np.ndarray,
    *,
    alpha: float = 0.45,
    vmin: float = HEATMAP_MIN_PCT,
    vmax: float = HEATMAP_MAX_PCT,
    max_width: int = HEATMAP_MAX_WIDTH,
) -> np.ndarray:
    """`frame` (RGB, see camera.py's array_to_jpeg) with a colour heatmap of
    `field.local_uncertainty_pct` blended over it -- cool/blue where confidence is high, hot/red
    where it's low. Downscaled to `max_width` first; see `HEATMAP_MAX_WIDTH`.

    Sampled on a coarse grid and upsampled, not once per pixel: `local_uncertainty_pct` is a
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
    # Sampled in the *original* frame's coordinates -- `field` was built from full-resolution
    # detections, so a downscaled grid position has to be scaled back up before querying it.
    xs = np.linspace(0, full_width - 1, cols)
    ys = np.linspace(0, full_height - 1, rows)
    grid = np.array(
        [[field.local_uncertainty_pct(float(x), float(y)) for x in xs] for y in ys],
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
