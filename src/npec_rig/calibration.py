"""Scale field across the measurement plane, built from tags of known physical size.

PLAN.md's M2 section A: the scale field is the local scale (px/mm) as a function of position in
the frame. This fits it from `TagDetection`s plus a tag_id -> real-world size (mm) lookup --
not yet from real-world tag *position* (a per-sheet position manifest is separate, in-progress
work); size alone is what the rig has today, and it's the same approach validated by hand
against a real capture (see project memory, not committed here).

The fit is a single tilted plane (relative depth linear in image x, y) -- validated on a real
capture where a plane explained the observed scale ramp to ~1.8% residual against a ~12% signal.
`residual_std_pct` is a *global* figure: how much scatter is left after removing that plane, as a
percentage of the mean scale. `UncertaintyField` is PLAN.md's *local* uncertainty: at a query
position, the RMS residual of the k nearest tags to it, so two calibrations with the same global
residual can still report different confidence in different parts of the frame.

`holdout_coverage_test` is PLAN.md's coverage check: fit on half the tags, predict the other
half, measure the error -- turns "is there enough coverage" into a number instead of a guess.
`regional_coverage_test` answers *where*: fit on three quadrants, predict the fourth, so a report
can say "add coverage in the top-left" instead of just a single global percentage.
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


QUADRANTS = ("top-left", "top-right", "bottom-left", "bottom-right")


@dataclass(frozen=True)
class QuadrantCoverage:
    """Coverage in one quadrant of the frame, from a fit on every *other* quadrant's tags.

    `mean_abs_pct_error`/`max_abs_pct_error` are None when there's nothing to report: either no
    tags were observed in this quadrant at all (the strongest possible coverage gap -- "add a
    sheet here"), or too few tags in the *other three* quadrants to fit a plane to predict with.
    """

    quadrant: str
    observed_count: int
    mean_abs_pct_error: float | None
    max_abs_pct_error: float | None


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
        px_per_mm.append(tag_side_px(detection.corners) / size_mm)
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


@dataclass(frozen=True)
class UncertaintyField:
    """Local scatter among neighbouring tags -- PLAN.md's "uncertainty field", distinct from
    `ScaleField.residual_std_pct` (a single global plane-fit number). Built from the same
    detections as a `ScaleField`: at each tag, how far the plane's prediction was off, as a
    percentage of that tag's actual scale.

    `local_uncertainty_pct` reports RMS-about-zero of the k nearest tags to a query position, not
    their standard deviation about each other's mean. A region where every tag agrees with its
    neighbours but all of them sit 5% off the fitted plane has zero *scatter* but a real 5% error
    -- std would report that as maximum confidence, which is exactly the honesty-plot failure
    mode M2's acceptance tests exist to catch. RMS-about-zero reports it as 5% uncertainty
    instead.

    Uses k-nearest-neighbour by image-plane distance, not a fixed grid -- tags are scattered
    irregularly across a real calibration sheet, not laid out on a regular lattice.
    """

    _positions: tuple[tuple[float, float], ...]
    _residual_pct: tuple[float, ...]

    def local_uncertainty_pct(self, x: float, y: float, k: int = 5) -> float:
        """RMS-about-zero residual of the k tags nearest to (x, y), as a percentage."""
        positions = np.array(self._positions)
        distances = np.linalg.norm(positions - np.array([x, y]), axis=1)
        nearest = np.argsort(distances)[: min(k, len(distances))]
        residuals = np.array(self._residual_pct)[nearest]
        return float(np.sqrt(np.mean(residuals**2)))


def build_uncertainty_field(
    field: ScaleField, detections: list[TagDetection], tag_sizes_mm: dict[int, float]
) -> UncertaintyField:
    """Build an `UncertaintyField` from `field`'s own per-tag residuals.

    Raises ValueError with fewer than 2 usable tags -- with 1, "neighbour scatter" is undefined.
    """
    x, y, ppm = _scale_samples(detections, tag_sizes_mm)
    if len(x) < 2:
        raise ValueError(
            f"need at least 2 tags with a known size to build an uncertainty field, got {len(x)}"
        )
    predicted = np.array([field.px_per_mm(xi, yi) for xi, yi in zip(x, y)])
    residual_pct = 100.0 * (ppm - predicted) / predicted
    return UncertaintyField(
        _positions=tuple(zip(x.tolist(), y.tolist())),
        _residual_pct=tuple(residual_pct.tolist()),
    )


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
    regional_coverage: tuple[QuadrantCoverage, ...] | None = None,
    *,
    coverage_threshold_pct: float = 2.0,
) -> list[str]:
    """Plain-language install report lines, from what's actually been measured so far.

    Deliberately narrow: scale variation, overall coverage sufficiency, and (when given) which
    quadrant a coverage gap is in. Roll, tilt and framing are PLAN.md's other install-report
    lines, but a roll/tilt angle isn't recoverable from a single photo without a physical
    standoff-distance measurement Aaron has ruled out (the rig is fragile), and framing needs a
    real capture's corner-tag/frame-edge check -- neither belongs here yet. No invented figures.
    """
    lines = [describe_scale_variation(field, positions)]
    if coverage is not None:
        lines.append(describe_coverage(coverage, threshold_pct=coverage_threshold_pct))
    if regional_coverage is not None:
        lines.extend(describe_regional_coverage(regional_coverage, threshold_pct=coverage_threshold_pct))
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


def _quadrant_of(x: float, y: float, mid_x: float, mid_y: float) -> str:
    vertical = "top" if y < mid_y else "bottom"
    horizontal = "left" if x < mid_x else "right"
    return f"{vertical}-{horizontal}"


def regional_coverage_test(
    detections: list[TagDetection],
    tag_sizes_mm: dict[int, float],
    frame_width: float,
    frame_height: float,
) -> tuple[QuadrantCoverage, ...]:
    """Where coverage is weak, not just how weak overall: fit on every tag *outside* quadrant Q,
    predict the tags *inside* Q, for each of the frame's four quadrants.

    Quadrants split at the *frame's* midpoint, not the tag cloud's own median -- splitting on the
    data's own median puts roughly a quarter of the tags in every quadrant by construction, so an
    empty quadrant (the strongest possible "add coverage here" signal) could never show up. Frame
    midpoint is a fixed reference the data can actually fail to cover.

    A prediction that lands on a non-physical relative depth (see `ScaleField.px_per_mm`) is
    itself a coverage failure for that quadrant -- reported as unusable (None), not raised, so one
    bad quadrant doesn't take down the whole report.
    """
    x, y, ppm = _scale_samples(detections, tag_sizes_mm)
    mid_x, mid_y = frame_width / 2, frame_height / 2
    quadrant_labels = [_quadrant_of(xi, yi, mid_x, mid_y) for xi, yi in zip(x, y)]

    results = []
    for label in QUADRANTS:
        inside = [i for i, q in enumerate(quadrant_labels) if q == label]
        outside = [i for i, q in enumerate(quadrant_labels) if q != label]
        if not inside:
            results.append(QuadrantCoverage(label, 0, None, None))
            continue
        if len(outside) < 3:
            results.append(QuadrantCoverage(label, len(inside), None, None))
            continue
        field = _fit_plane(x[outside], y[outside], ppm[outside])
        try:
            predicted = np.array([field.px_per_mm(xi, yi) for xi, yi in zip(x[inside], y[inside])])
        except ValueError:
            results.append(QuadrantCoverage(label, len(inside), None, None))
            continue
        actual = ppm[inside]
        pct_error = 100.0 * np.abs(predicted - actual) / actual
        results.append(
            QuadrantCoverage(label, len(inside), float(pct_error.mean()), float(pct_error.max()))
        )
    return tuple(results)


def describe_regional_coverage(
    results: tuple[QuadrantCoverage, ...], *, threshold_pct: float = 2.0
) -> list[str]:
    """One line per quadrant that isn't fine -- silent when coverage is even and within target."""
    lines = []
    for result in results:
        if result.observed_count == 0:
            lines.append(f"No calibration tags in the {result.quadrant} -- add a sheet there.")
        elif result.mean_abs_pct_error is None:
            lines.append(
                f"Can't check coverage in the {result.quadrant} yet -- too little coverage "
                "elsewhere to predict against."
            )
        elif result.mean_abs_pct_error > threshold_pct:
            lines.append(
                f"Coverage weak in the {result.quadrant}: holdout error "
                f"{result.mean_abs_pct_error:.1f}% exceeds the {threshold_pct:.0f}% target -- "
                "add more coverage there."
            )
    return lines
