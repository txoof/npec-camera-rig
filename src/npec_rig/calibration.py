"""Scale field across the measurement plane, built from tags of known physical size.

PLAN.md's M2 section A: the scale field is the local scale (px/mm) as a function of position in
the frame. This fits it from `TagDetection`s plus a tag_id -> real-world size (mm) lookup --
not yet from real-world tag *position* (a per-sheet position manifest is separate, in-progress
work); size alone is what the rig has today, and it's the same approach validated by hand
against a real capture (see project memory, not committed here).

The fit is a single tilted plane (relative depth linear in image x, y) -- validated on a real
capture where a plane explained the observed scale ramp to ~1.8% residual against a ~12% signal.
`residual_std_pct` is a *global* figure: how much scatter is left after removing that plane, as a
percentage of the mean scale. PLAN.md's "uncertainty field" calls for *local* scatter among
neighbouring tags, which this doesn't build yet -- this is the plane-fit diagnostic only.

`holdout_coverage_test` is PLAN.md's coverage check: fit on half the tags, predict the other
half, measure the error -- turns "is there enough coverage" into a number instead of a guess.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from npec_rig.tags import TagDetection, tag_side_px


@dataclass(frozen=True)
class ScaleField:
    """A fitted px/mm field over the frame, plus how well a single tilted plane explains it."""

    _coeffs: tuple[float, float, float]  # relative depth ~= a + b*x + c*y
    _mean_px_per_mm: float
    residual_std_pct: float

    def px_per_mm(self, x: float, y: float) -> float:
        """Local scale at image position (x, y), from the fitted field.

        Raises ValueError if the fitted plane predicts a non-physical (zero or negative) relative
        depth at this position -- extrapolating a tilted-plane fit far enough from where it was
        measured can reach that, and a silently-returned nonsense scale is worse than an error.
        """
        a, b, c = self._coeffs
        relative_depth = a + b * x + c * y
        if relative_depth <= 0:
            raise ValueError(
                f"scale field is not physically valid at ({x}, {y}): relative_depth="
                f"{relative_depth:.3g} <= 0 -- this position is too far outside where the field "
                "was measured to trust"
            )
        return self._mean_px_per_mm / relative_depth

    def mm_per_px(self, x: float, y: float) -> float:
        return 1.0 / self.px_per_mm(x, y)


@dataclass(frozen=True)
class CoverageResult:
    """How well a field fit on half the tags predicts the other half, at their positions."""

    fit_count: int
    held_out_count: int
    mean_abs_pct_error: float
    max_abs_pct_error: float


def _scale_samples(
    detections: list[TagDetection], tag_sizes_mm: dict[int, float]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(x, y, px_per_mm) for every detection whose tag id has a known real-world size."""
    xs: list[float] = []
    ys: list[float] = []
    px_per_mm: list[float] = []
    for detection in detections:
        size_mm = tag_sizes_mm.get(detection.tag_id)
        if size_mm is None:
            continue
        xs.append(detection.centre[0])
        ys.append(detection.centre[1])
        px_per_mm.append(tag_side_px(detection) / size_mm)
    return np.array(xs), np.array(ys), np.array(px_per_mm)


def _fit_plane(x: np.ndarray, y: np.ndarray, ppm: np.ndarray) -> ScaleField:
    mean_ppm = float(ppm.mean())
    relative_depth = mean_ppm / ppm  # ~1.0; >1 means farther away than the frame average

    design = np.column_stack([np.ones_like(x), x, y])
    coeffs, *_ = np.linalg.lstsq(design, relative_depth, rcond=None)
    residual = relative_depth - design @ coeffs
    residual_std_pct = float(100.0 * residual.std() / relative_depth.mean())

    return ScaleField(
        _coeffs=(float(coeffs[0]), float(coeffs[1]), float(coeffs[2])),
        _mean_px_per_mm=mean_ppm,
        residual_std_pct=residual_std_pct,
    )


def build_scale_field(
    detections: list[TagDetection], tag_sizes_mm: dict[int, float]
) -> ScaleField:
    """Fit a scale field from detections whose tag id has a known real-world size.

    Detections whose id isn't in `tag_sizes_mm` (e.g. corner tags, not sized for this purpose)
    are ignored. Raises ValueError with fewer than 3 usable detections -- a plane has 3 degrees
    of freedom.
    """
    x, y, ppm = _scale_samples(detections, tag_sizes_mm)
    if len(x) < 3:
        raise ValueError(
            f"need at least 3 tags with a known size to fit a scale field, got {len(x)}"
        )
    return _fit_plane(x, y, ppm)


def describe_scale_variation(field: ScaleField, positions: list[tuple[float, float]]) -> str:
    """One line: how much scale varies across the tag cloud used to build `field`, and where.

    Evaluated over the bounding box of the *observed* tag positions, never the full frame --
    extrapolating the fitted plane beyond where tags were actually seen would be exactly the
    silent-lie failure mode this report exists to catch (see `ScaleField.px_per_mm`'s guard).
    `positions` is normally the (x, y) of every detection `field` was fit from.
    """
    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    corners = {
        "top-left": (min(xs), min(ys)),
        "top-right": (max(xs), min(ys)),
        "bottom-left": (min(xs), max(ys)),
        "bottom-right": (max(xs), max(ys)),
    }
    values = {label: field.px_per_mm(x, y) for label, (x, y) in corners.items()}
    mean_value = sum(values.values()) / len(values)
    worst_label = max(values, key=lambda label: abs(values[label] - mean_value))
    variation_pct = 100.0 * (max(values.values()) - min(values.values())) / mean_value
    return f"Scale varies {variation_pct:.0f}% across the calibrated area, worst {worst_label}."


def describe_coverage(coverage: CoverageResult, *, threshold_pct: float = 2.0) -> str:
    """One line: whether holdout error is within the tape-measure acceptance target.

    `threshold_pct` defaults to 2.0 -- PLAN.md's M2 acceptance bar ("tape-measure two tags -> app
    agrees within 2%"). Provisional in the sense that the chamber acceptance tests are the actual
    measurement; this default just gives the report something to say before that happens.
    """
    if coverage.mean_abs_pct_error <= threshold_pct:
        return (
            f"Coverage sufficient: holdout error {coverage.mean_abs_pct_error:.1f}% "
            f"(target {threshold_pct:.0f}%)."
        )
    return (
        f"Coverage insufficient: holdout error {coverage.mean_abs_pct_error:.1f}% exceeds the "
        f"{threshold_pct:.0f}% target -- add more calibration coverage."
    )


def build_install_report(
    field: ScaleField,
    positions: list[tuple[float, float]],
    coverage: CoverageResult | None = None,
    *,
    coverage_threshold_pct: float = 2.0,
) -> list[str]:
    """Plain-language install report lines, from what's actually been measured so far.

    Deliberately narrow: only scale variation and (when given) coverage sufficiency. Roll, tilt
    and framing are PLAN.md's other install-report lines, but a roll/tilt angle isn't recoverable
    from a single photo without a physical standoff-distance measurement Aaron has ruled out (the
    rig is fragile), and framing needs a real capture's corner-tag/frame-edge check -- neither
    belongs here yet. No invented figures.
    """
    lines = [describe_scale_variation(field, positions)]
    if coverage is not None:
        lines.append(describe_coverage(coverage, threshold_pct=coverage_threshold_pct))
    return lines


def holdout_coverage_test(
    detections: list[TagDetection], tag_sizes_mm: dict[int, float], *, seed: int = 0
) -> CoverageResult:
    """Fit a scale field on half the usable tags, predict the other half, measure the error.

    A random half-split (`seed` makes it reproducible) rather than the first/second half of
    detection order, which is usually spatial (row by row) and would make the split coverage-
    dependent in a way that has nothing to do with the rig. Raises ValueError with fewer than 6
    usable tags -- half of that is the 3 a plane fit needs at minimum.
    """
    x, y, ppm = _scale_samples(detections, tag_sizes_mm)
    n = len(x)
    if n < 6:
        raise ValueError(
            f"need at least 6 tags with a known size to hold out half and still fit a plane "
            f"on the rest, got {n}"
        )

    rng = np.random.default_rng(seed)
    shuffled = rng.permutation(n)
    half = n // 2
    fit_idx, holdout_idx = shuffled[:half], shuffled[half:]

    field = _fit_plane(x[fit_idx], y[fit_idx], ppm[fit_idx])
    predicted = np.array([field.px_per_mm(xi, yi) for xi, yi in zip(x[holdout_idx], y[holdout_idx])])
    actual = ppm[holdout_idx]
    pct_error = 100.0 * np.abs(predicted - actual) / actual

    return CoverageResult(
        fit_count=len(fit_idx),
        held_out_count=len(holdout_idx),
        mean_abs_pct_error=float(pct_error.mean()),
        max_abs_pct_error=float(pct_error.max()),
    )
