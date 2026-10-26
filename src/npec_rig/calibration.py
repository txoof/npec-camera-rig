"""Scale field across the measurement plane, built from tag spacing on the tag sheets.

PLAN.md's M2 section A: the scale field is the local scale (px/mm) as a function of position in
the frame. It is fitted to tag spacing: the distance between the centres of two tags of one tag
sheet over their distance as printed (the print layout files in `reference/calibration-sheets/`),
scaled by the calliper-measured tag size. Not to tag edges: in the rig's photos they read 1 to
2.5% short of tag spacing, by an amount that changes between photos, so areas read 1 to 5% high
(metrology log 18, #286).

The fit is a single tilted plane (relative depth linear in image x, y) -- validated on a real
capture where a plane explained the observed scale ramp to ~1.8% residual against a ~12% signal.
`residual_std_pct` is a *global* figure: how much scatter is left after removing that plane, as a
percentage of the mean scale. How far a measurement can be trusted at a position is not claimed
here: validation measures it per slot (issue #52).

`holdout_coverage_test` is PLAN.md's coverage check: fit on half the tags, predict the other
half, measure the error -- turns "is there enough coverage" into a number instead of a guess.
`regional_coverage_test` answers *where*: fit on three quadrants, predict the fourth, so a report
can say "add coverage in the top-left" instead of just a single global percentage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from itertools import combinations
from pathlib import Path

import numpy as np

from npec_rig.tags import ASSUMED_CALIBRATION_TAG_SIZE_MM, TagDetection, tag_area_px, tag_side_px
from npec_rig.tripwire import CornerBaseline

# PLAN.md 339-340's promised-but-unbuilt corner-tag homography (TODO.md's "Health baseline" item
# flagged this as the gap). Position only, never mm -- see `TableFrame`'s own docstring for why
# `build_table_frame` takes only a `CornerBaseline` and no `ScaleField`.
#
# Verified this session, against real saved calibration frames, not just argued from docs:
# a single tag's own 4-corner homography does NOT generalize across the frame (size error grew to
# ~10% by the far side, r=0.72 with distance from the source tag -- no single tag has a wide
# enough baseline). The four corner tags' homography (wide baseline, spanning near the full frame)
# DID hold up: shape consistency stayed within ~1-6% end to end, ~uncorrelated with distance from
# centre (r=-0.05). Wide baseline, not which physical plane the anchor points sit on, is what
# makes a homography hold up across a whole frame -- that's the basis for using the corner tags,
# and only the corner tags, here.
_TABLE_FRAME_DEGENERACY_EPS = 1e-6  # see build_table_frame's docstring for what this guards


def _tag_centre(corners: tuple[tuple[float, float], ...]) -> tuple[float, float]:
    """Mean of a tag's 4 corners -- averages corner-detection noise 4x, and is an unambiguous,
    rotation-invariant point to anchor a homography on (as opposed to picking one of the tag's
    own 4 corners, which would be an arbitrary choice of *which* corner of *which* tag).
    """
    array = np.array(corners)
    centre = array.mean(axis=0)
    return (float(centre[0]), float(centre[1]))


def _normalize_points(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Hartley-normalize `points` (centroid at origin, mean distance sqrt(2)) plus the 3x3
    transform `T` that performs it -- `points @ T.T` in homogeneous form. Real pixel coordinates
    on this rig run into the thousands (9152x6944), and unnormalized DLT is numerically unstable
    at that scale (entries of the linear system span many orders of magnitude); the unit-square
    destination points don't need this, only the pixel-side source points do.
    """
    centroid = points.mean(axis=0)
    shifted = points - centroid
    mean_dist = float(np.mean(np.linalg.norm(shifted, axis=1)))
    if mean_dist == 0:
        raise ValueError("degenerate point set: all points coincide, can't normalize")
    scale = np.sqrt(2) / mean_dist
    transform = np.array(
        [[scale, 0, -scale * centroid[0]], [0, scale, -scale * centroid[1]], [0, 0, 1]]
    )
    normalized = shifted * scale
    return normalized, transform


def _dlt_homography(
    src_pts: list[tuple[float, float]], dst_pts: list[tuple[float, float]]
) -> np.ndarray:
    """3x3 homography mapping each `src_pts[i]` to `dst_pts[i]` (direct linear transform via the
    null space of the standard DLT constraint matrix, found with SVD) -- exactly 4 correspondences
    here (a homography has 8 degrees of freedom, each point gives 2 equations), not a least-
    squares fit over many points. Both point sets are Hartley-normalized first (`_normalize_points`)
    and the result denormalized back, for numerical stability at real pixel scales.
    """
    src = np.array(src_pts, dtype=float)
    dst = np.array(dst_pts, dtype=float)
    src_norm, t_src = _normalize_points(src)
    dst_norm, t_dst = _normalize_points(dst)

    rows = []
    for (x, y), (u, v) in zip(src_norm, dst_norm):
        rows.append([-x, -y, -1, 0, 0, 0, x * u, y * u, u])
        rows.append([0, 0, 0, -x, -y, -1, x * v, y * v, v])
    _u, _s, vt = np.linalg.svd(np.array(rows))
    h_norm = vt[-1].reshape(3, 3)

    return np.linalg.inv(t_dst) @ h_norm @ t_src


def _shoelace_triangle_area(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    return float(abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2)


def _assert_not_degenerate(points: np.ndarray, ordered: np.ndarray) -> None:
    """Raises ValueError if `points` (the 4 corner-tag centres) has any near-collinear triple, or
    if `ordered` (the same 4 points, arranged TL/TR/BR/BL) winds as a self-intersecting bowtie
    rather than a simple quad.

    The collinearity epsilon is scale-*relative* (triangle area over the largest pairwise
    distance, squared) rather than an absolute pixel-area threshold -- an absolute threshold tuned
    on a small synthetic fixture would mean something completely different at this rig's real
    9152x6944 frame scale.
    """
    pairwise_max = max(
        float(np.linalg.norm(points[i] - points[j])) for i, j in combinations(range(4), 2)
    )
    if pairwise_max == 0:
        raise ValueError("corner tags are degenerate: all 4 centres coincide")
    for i, j, k in combinations(range(4), 3):
        area = _shoelace_triangle_area(points[i], points[j], points[k])
        if area / (pairwise_max**2) < _TABLE_FRAME_DEGENERACY_EPS:
            raise ValueError(
                f"corner tags are degenerate: centres {i}, {j}, {k} are near-collinear "
                f"(normalized triangle area {area / pairwise_max ** 2:.2e})"
            )

    edges = [ordered[(i + 1) % 4] - ordered[i] for i in range(4)]
    cross_signs = [
        edges[i][0] * edges[(i + 1) % 4][1] - edges[i][1] * edges[(i + 1) % 4][0] for i in range(4)
    ]
    if not (all(c > 0 for c in cross_signs) or all(c < 0 for c in cross_signs)):
        raise ValueError("corner tags wind as a self-intersecting (bowtie) quad, not a simple one")


@dataclass(frozen=True)
class TableFrame:
    """Pixel <-> table-fraction transform, built from the four corner tags' own centres --
    position only, see `build_table_frame`.

    `(u, v) in [0, 1]^2` span the quadrilateral of the four corner tags' own centres, not the
    table's physical edge some distance further out. `u` runs TL -> TR (left-to-right in the
    camera image), `v` runs TL -> BL (top-to-bottom). Fractions carry no millimetres: a map drawn
    in these coordinates has the corner tags' proportions, not a measured table size.

    `corners_px` is the same four points, in TL/TR/BR/BL order -- not consulted by
    `to_fraction`/`to_pixel`, which go through `_matrix` alone; the tag map reads its proportions
    from them.
    """

    _matrix: tuple[
        tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]
    ]
    corners_px: tuple[
        tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]
    ]

    def to_fraction(self, x: float, y: float) -> tuple[float, float]:
        """Pixel `(x, y)` -> table-fraction `(u, v)`. Raises ValueError if the homography's
        perspective divide is non-physical (w <= 0) at this position -- the same
        extrapolation-honesty guard `ScaleField.px_per_mm` uses, for the same reason: a silently
        returned nonsense position is worse than an error.
        """
        matrix = np.array(self._matrix)
        u, v, w = matrix @ np.array([x, y, 1.0])
        if w <= 0:
            raise ValueError(
                f"table frame is not physically valid at pixel ({x}, {y}): w={w:.3g} <= 0"
            )
        return (float(u / w), float(v / w))

    def to_pixel(self, u: float, v: float) -> tuple[float, float]:
        """Table-fraction `(u, v)` -> pixel `(x, y)` -- the inverse of `to_fraction`. Computed via
        `np.linalg.inv` on each call rather than cached: a 3x3 inverse is cheap, and this isn't
        called often enough to be worth the complexity of caching it.
        """
        matrix = np.linalg.inv(np.array(self._matrix))
        x, y, w = matrix @ np.array([u, v, 1.0])
        if w <= 0:
            raise ValueError(
                f"table frame is not physically valid at fraction ({u}, {v}): w={w:.3g} <= 0"
            )
        return (float(x / w), float(y / w))

    def as_matrix(self) -> np.ndarray:
        """The pixel -> fraction homography as a plain 3x3 `np.ndarray` -- for a caller (e.g.
        `calibration_viz.render_tag_map`) that needs to compose it with other matrices (a
        downscale, a canvas scale) rather than call `to_fraction`/`to_pixel` point by point.
        """
        return np.array(self._matrix)


def build_table_frame(baseline: CornerBaseline) -> TableFrame:
    """Build a `TableFrame` from the four corner tags' own centres.

    Takes **only `CornerBaseline`** -- no `ScaleField` parameter exists, by construction, so mm
    can't leak into this transform even by accident. Position (this) and scale/area (`ScaleField`,
    fit from the measurement-plane calibration tags) are two coordinate systems that must never
    mix: the corner tags sit on a different physical plane (the table edge) than the measurement
    slab (tray height) `ScaleField` is fit to, and using a cross-plane figure to correct anything
    here would be exactly the invented parallax correction CLAUDE.md's evidence gate blocks.

    Raises ValueError if `len(baseline.corners_by_id) != 4` -- a homography needs exactly 4
    non-degenerate correspondences, and a reduced-DOF fallback (e.g. an affine fit from 3 points)
    would be exactly the derived-not-measured shortcut this project exists to avoid. Not currently
    a practical limitation: all 4 corner tags are detected in every recent real run (verified
    directly against saved calibration artifacts) -- unlike `CornerBaseline`/`check_tripwire`
    elsewhere in this codebase, which deliberately tolerate fewer than 4 for the tripwire's own,
    looser purpose (comparing whichever tags are present against themselves later); a homography
    has no equivalent looser mode, so this is strict where those are lenient.

    Corner roles (TL/TR/BR/BL) are assigned geometrically from the 4 centres' own layout (the
    standard sum/difference trick: smallest x+y is TL, largest is BR; of the remaining two,
    largest x-y is TR, smallest is BL) -- not from a fixed tag-ID-to-corner mapping, since no such
    mapping exists anywhere in this codebase. This assumption stays correct unless the rig gets
    rotated by roughly 180 degrees, which would already trip `tripwire.check_tripwire`'s own roll
    check as a backstop.

    Also raises ValueError on a near-collinear triple of centres, or a self-intersecting (bowtie)
    winding order -- see `_assert_not_degenerate`.
    """
    if len(baseline.corners_by_id) != 4:
        raise ValueError(
            f"need exactly 4 corner tags to build a table frame, got "
            f"{len(baseline.corners_by_id)}"
        )

    centres = {tag_id: _tag_centre(corners) for tag_id, corners in baseline.corners_by_id.items()}
    tag_ids = sorted(centres)
    points = np.array([centres[tag_id] for tag_id in tag_ids])

    sums = points[:, 0] + points[:, 1]
    diffs = points[:, 0] - points[:, 1]
    idx_tl = int(np.argmin(sums))
    idx_br = int(np.argmax(sums))
    remaining = [i for i in range(4) if i not in (idx_tl, idx_br)]
    idx_tr, idx_bl = (
        (remaining[0], remaining[1])
        if diffs[remaining[0]] > diffs[remaining[1]]
        else (remaining[1], remaining[0])
    )

    ordered = np.array([points[idx_tl], points[idx_tr], points[idx_br], points[idx_bl]])
    _assert_not_degenerate(points, ordered)

    unit_square = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]  # TL, TR, BR, BL
    matrix = _dlt_homography([tuple(p) for p in ordered], unit_square)

    # The DLT solves for a null-space vector, which SVD returns up to an arbitrary +/-1 sign --
    # both signs solve the same linear system equally validly, and `to_fraction`/`to_pixel`'s own
    # `u/w`, `v/w` divisions are sign-invariant, so this has no effect on any *position* either of
    # them reports. But their `w <= 0` extrapolation guards are NOT sign-invariant: whichever sign
    # SVD happens to return could make `w` negative everywhere inside the table, which would make
    # every real query raise and everywhere read as "never measured" -- a straightened photo that
    # renders correctly (cv2.warpPerspective's own divide doesn't care about this sign) sitting
    # under an entirely grey field, with no exception and no None result to notice by. Pinned by
    # construction: the quad's own centroid must map to a physically valid (w > 0) position, since
    # it sits inside the quad by definition.
    centroid = ordered.mean(axis=0)
    w_at_centroid = matrix[2, 0] * centroid[0] + matrix[2, 1] * centroid[1] + matrix[2, 2]
    if w_at_centroid < 0:
        matrix = -matrix

    return TableFrame(
        _matrix=tuple(tuple(float(v) for v in row) for row in matrix),
        corners_px=tuple((float(p[0]), float(p[1])) for p in ordered),
    )


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


# The print layout files of the tag sheets: where each tag's centre sits on its printed page.
SHEET_LAYOUTS_DIR = Path(__file__).parent.parent.parent / "reference" / "calibration-sheets"
# Tag spacing is used only between tags of one tag sheet 30 to 90 mm apart as printed: neighbours
# and their neighbours, over which the paper lies flat (metrology log 18).
PAIR_MM = (30.0, 90.0)
# A partner is taken only where the print layout puts it: its offset from the tag, predicted from
# the tag's own direction and rough scale (its corners and edges), within this fraction of the
# predicted distance. Edges read at most ~2.5% short (metrology log 18); a tag on another copy of
# the same page lies far from the predicted spot (on the 2026-10-22 calibration photo, 12 sheets
# from 6 pages: every one of 3,582 pairs within 3.4% at the 95th percentile, the next candidate
# always over 300% off).
_PARTNER_TOLERANCE = 0.10


@cache
def sheet_layout() -> dict[int, tuple[str, float, float, float]]:
    """tag_id -> (page, x mm, y mm, printed size mm) from every print layout file. Raises
    FileNotFoundError when there is none: without them no scale can be fitted."""
    paths = sorted(SHEET_LAYOUTS_DIR.glob("*.manifest.json"))
    if not paths:
        raise FileNotFoundError(f"no print layout files (*.manifest.json) in {SHEET_LAYOUTS_DIR}")
    layout = {}
    for path in paths:
        for tag in json.loads(path.read_text())["tags"]:
            layout[tag["id"]] = (f"{path.name} page {tag['page']}", tag["center_x_mm"], tag["center_y_mm"], tag["size_mm"])
    return layout


@dataclass(frozen=True)
class SpacingPair:
    """Two tags of one tag sheet: their midpoint and the scale their centre distance gives."""

    a: TagDetection
    b: TagDetection
    x: float
    y: float
    px_per_mm: float


def spacing_pairs(detections: list[TagDetection], tag_sizes_mm: dict[int, float]) -> list[SpacingPair]:
    """Every pair of tags of one tag sheet 30 to 90 mm apart as printed, with the scale (px/mm)
    from their centre distance over their printed distance.

    Tag edges read 1 to 2.5% short of tag spacing in the rig's photos, by an amount that changes
    between photos (metrology log 18); the centres do not move with the edges. A printed distance
    is scaled by the tag's calliper size over its printed size, so a sheet printed at 96% still
    gives the right scale. IDs repeat between copies of one page, so a partner is taken only where
    the print layout puts it, seen from the tag: the detector's first two corners give the page's
    x direction (from corner 1 to corner 0, checked on the 2026-10-22 calibration photo) and the
    tag's edges a rough scale. A pair counts only when each of its two tags finds the other.
    """
    layout = sheet_layout()
    partners = _printed_partners()
    usable = [d for d in detections if d.tag_id in tag_sizes_mm and d.tag_id in layout]
    by_id: dict[int, list[int]] = {}
    for i, d in enumerate(usable):
        by_id.setdefault(d.tag_id, []).append(i)
    centres = {tag_id: np.array([usable[k].centre for k in members]) for tag_id, members in by_id.items()}

    seen: dict[tuple[int, int], list[float]] = {}
    for i, d in enumerate(usable):
        _, _, _, printed_mm = layout[d.tag_id]
        factor = tag_sizes_mm[d.tag_id] / printed_mm
        rough = tag_side_px(d.corners) / tag_sizes_mm[d.tag_id]
        ux, uy = np.subtract(d.corners[0], d.corners[1])
        norm = float(np.hypot(ux, uy))
        if norm == 0:
            continue
        ux, uy = ux / norm, uy / norm
        for partner_id, dx_printed, dy_printed in partners[d.tag_id]:
            candidates = by_id.get(partner_id)
            if not candidates:
                continue
            dx_mm, dy_mm = dx_printed * factor, dy_printed * factor
            true_mm = float(np.hypot(dx_mm, dy_mm))
            # Page y is up; in the image it is the page's x direction turned a quarter back.
            predicted = rough * np.array([dx_mm * ux + dy_mm * uy, dx_mm * uy - dy_mm * ux])
            offsets = centres[partner_id] - d.centre
            misses = np.hypot(*(offsets - predicted).T)
            best = int(np.argmin(misses))
            if misses[best] > _PARTNER_TOLERANCE * rough * true_mm:
                continue
            j, offset = candidates[best], offsets[best]
            seen.setdefault((min(i, j), max(i, j)), []).append(float(np.hypot(*offset)) / true_mm)
    # Both tags must find each other: seen from either, the other sits where the print puts it.
    return [
        SpacingPair(
            usable[i], usable[j],
            (usable[i].centre[0] + usable[j].centre[0]) / 2, (usable[i].centre[1] + usable[j].centre[1]) / 2,
            ratios[0],
        )
        for (i, j), ratios in seen.items()
        if len(ratios) == 2
    ]


@cache
def _printed_partners() -> dict[int, tuple[tuple[int, float, float], ...]]:
    """tag_id -> (partner_id, dx mm, dy mm) for every tag of its page 30 to 90 mm from it as printed."""
    layout = sheet_layout()
    partners: dict[int, list[tuple[int, float, float]]] = {tag_id: [] for tag_id in layout}
    for tag_id, (page, x_mm, y_mm, _) in layout.items():
        for other_id, (other_page, ox_mm, oy_mm, _) in layout.items():
            if other_page == page and PAIR_MM[0] <= np.hypot(ox_mm - x_mm, oy_mm - y_mm) <= PAIR_MM[1]:
                partners[tag_id].append((other_id, ox_mm - x_mm, oy_mm - y_mm))
    return {tag_id: tuple(found) for tag_id, found in partners.items()}


def tag_spacing_scales(
    detections: list[TagDetection], tag_sizes_mm: dict[int, float]
) -> list[tuple[TagDetection, float]]:
    """Each tag's own scale (px/mm) from tag spacing: the median over the pairs it is in
    (`spacing_pairs`). Tags in no pair are left out."""
    ratios: dict[int, tuple[TagDetection, list[float]]] = {}
    for pair in spacing_pairs(detections, tag_sizes_mm):
        for tag in (pair.a, pair.b):
            ratios.setdefault(id(tag), (tag, []))[1].append(pair.px_per_mm)
    return [(tag, float(np.median(values))) for tag, values in ratios.values()]


def _scale_samples(
    detections: list[TagDetection], tag_sizes_mm: dict[int, float]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(x, y, px_per_mm) at the midpoint of every pair from tag spacing (`spacing_pairs`)."""
    pairs = spacing_pairs(detections, tag_sizes_mm)
    return np.array([p.x for p in pairs]), np.array([p.y for p in pairs]), np.array([p.px_per_mm for p in pairs])


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
            f"need at least 3 pairs of tags of one tag sheet to fit a scale field from tag "
            f"spacing, got {len(x)}: are the tag sheets printed from the layout files in "
            f"{SHEET_LAYOUTS_DIR}, at 100%?"
        )
    return _fit_plane(x, y, ppm)


@dataclass(frozen=True)
class ScaleResidualSample:
    """One calibration tag's own length-scale residual against the fitted plane, with its
    `tag_id` and position: the number the radial plot and the tag map draw, per tag.
    """

    x: float
    y: float
    tag_id: int
    residual_pct: float
    corners: tuple = ()  # the tag's four corners, full-resolution pixels: the tag map fills them


def scale_residual_samples(
    field: ScaleField, detections: list[TagDetection], tag_sizes_mm: dict[int, float]
) -> list[ScaleResidualSample]:
    """One `ScaleResidualSample` per tag with a scale from tag spacing (`tag_spacing_scales`).
    Skips a tag if `field.px_per_mm` isn't physically valid there (same extrapolation guard as
    `area_scale_samples`) rather than raising, so one bad position doesn't take down the plot.
    """
    samples = []
    for detection, observed in tag_spacing_scales(detections, tag_sizes_mm):
        x, y = detection.centre
        try:
            predicted = field.px_per_mm(x, y)
        except ValueError:
            continue
        samples.append(
            ScaleResidualSample(
                x=x,
                y=y,
                tag_id=detection.tag_id,
                residual_pct=100.0 * (observed - predicted) / predicted,
                corners=tuple(tuple(c) for c in detection.corners),
            )
        )
    return samples


@dataclass(frozen=True)
class AreaScaleSample:
    """TODO.md's area-scale shape check, at one calibration tag: is naively squaring the fitted
    *length* scale (`ScaleField.px_per_mm(x, y) ** 2`) good enough for *area*, or does the tag's
    actual pixel shape (shoelace area on its four corners, exact, no lens model) disagree?

    `area_error_pct` is "how wrong M5's canopy area will be here" -- the number the TODO asks
    for, `100 * (measured_area_scale / naive_area_scale - 1)`. But it is not a clean new
    measurement: writing `s = tag_side_px(corners)` (what the length field was fit from) and
    `P = field.px_per_mm(x, y)`, the tag's own length residual is `r = s / (size_mm * P) - 1`
    (the `ScaleResidualSample` at this tag), and

        area_error_pct ~= 100 * (kappa - 1) + 2 * (100 * r)

    where `kappa = tag_area_px(corners) / s ** 2` is the part that's actually new: a pure shape
    factor, 1.0 for a true square, that captures a tag whose corners aren't well described by
    "mean side length squared" regardless of overall scale. `shape_factor_pct = 100 * (kappa - 1)`
    is kept alongside `area_error_pct` for exactly this reason -- most of `area_error_pct` at any
    real position is the *already-plotted* length residual, doubled. Reading `area_error_pct`
    alone and seeing it grow toward the corners would re-discover the coverage gaps
    `regional_coverage_test` already reports, not new evidence that area needs its own fit.
    `shape_factor_pct` is the number that actually answers that question.

    `shape_factor_pct` is <= 0 always, not a bidirectional error: a square is the maximum-area
    quadrilateral for a given mean side length (`kappa <= 1`, equality only for a true square), so
    0% means a perfect square and more negative means more distorted -- there is no "positive"
    direction to lose by taking an absolute value here, but one is deliberately not taken, so a
    small or blurry tag's corner-refinement noise (which can only ever push `kappa` further below
    1, never above) still reads as a magnitude, not cancelled out by averaging with tags that
    happen to jitter the other way (they can't). `area_error_pct` does keep its sign either way --
    it also carries the length residual's own, genuinely bidirectional, sign.
    """

    x: float
    y: float
    tag_id: int
    area_error_pct: float
    shape_factor_pct: float


def area_scale_samples(
    field: ScaleField, detections: list[TagDetection], tag_sizes_mm: dict[int, float]
) -> list[AreaScaleSample]:
    """One `AreaScaleSample` per tag with a scale from tag spacing (`tag_spacing_scales`), at the
    position `field` was evaluated at. The measured area scale is the tag's spacing scale squared
    times its shape factor: tag edges read short (metrology log 18), and the shape factor, a
    ratio of the tag's own pixel area to its own side squared, does not carry that. Skips a tag
    if `field.px_per_mm` isn't physically valid there (the same extrapolation guard
    `regional_coverage_test` treats as a coverage failure, not an error).
    """
    samples = []
    for detection, spacing_px_per_mm in tag_spacing_scales(detections, tag_sizes_mm):
        x, y = detection.centre
        try:
            naive_area_scale = field.px_per_mm(x, y) ** 2
        except ValueError:
            continue
        side_px = tag_side_px(detection.corners)
        area_px = tag_area_px(detection.corners)
        kappa = area_px / (side_px**2)
        measured_area_scale = spacing_px_per_mm**2 * kappa
        samples.append(
            AreaScaleSample(
                x=x,
                y=y,
                tag_id=detection.tag_id,
                area_error_pct=100.0 * (measured_area_scale / naive_area_scale - 1.0),
                shape_factor_pct=100.0 * (kappa - 1.0),
            )
        )
    return samples


def describe_area_scale_shape(samples: list[AreaScaleSample]) -> str:
    """One line: mean area-scale error (what M5 will actually see), and, as a separate figure,
    the shape-distortion part that's actually new (see `AreaScaleSample`) -- reported side by
    side, not as a share of the first, because `area_error_pct` and `shape_factor_pct` can carry
    different signs and a mean-of-absolutes doesn't decompose that way. Plus which tag has the
    worst shape distortion (most negative `shape_factor_pct`, since it's never positive).
    Raises ValueError with zero samples.
    """
    if not samples:
        raise ValueError("need at least one area-scale sample to describe")
    n = len(samples)
    mean_abs_area = sum(abs(s.area_error_pct) for s in samples) / n
    mean_abs_shape = sum(abs(s.shape_factor_pct) for s in samples) / n
    worst = min(samples, key=lambda s: s.shape_factor_pct)
    return (
        f"Area-scale error {mean_abs_area:.1f}% mean over {n} tags; shape distortion "
        f"{mean_abs_shape:.2f}% mean (a separate figure, not a share of the above) -- worst "
        f"shape tag {worst.tag_id} at {worst.shape_factor_pct:.2f}% ({worst.x:.0f}, {worst.y:.0f})."
    )


def _bbox_corner_scale(
    field: ScaleField, positions: list[tuple[float, float]]
) -> dict[str, float]:
    """px/mm at each corner of the *observed* tag cloud's bounding box, keyed by corner label.

    Shared by `describe_scale_variation` and `describe_coplanarity` so both read the same four
    corners -- never the full frame, for the reason `describe_scale_variation` documents.
    """
    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    corners = {
        "top-left": (min(xs), min(ys)),
        "top-right": (max(xs), min(ys)),
        "bottom-left": (min(xs), max(ys)),
        "bottom-right": (max(xs), max(ys)),
    }
    return {label: field.px_per_mm(x, y) for label, (x, y) in corners.items()}


def describe_scale_variation(field: ScaleField, positions: list[tuple[float, float]]) -> str:
    """One line: how much scale varies across the tag cloud used to build `field`, and where.

    Evaluated over the bounding box of the *observed* tag positions, never the full frame --
    extrapolating the fitted plane beyond where tags were actually seen would be exactly the
    silent-lie failure mode this report exists to catch (see `ScaleField.px_per_mm`'s guard).
    `positions` is normally the (x, y) of every detection `field` was fit from.
    """
    values = _bbox_corner_scale(field, positions)
    mean_value = sum(values.values()) / len(values)
    worst_label = max(values, key=lambda label: abs(values[label] - mean_value))
    variation_pct = 100.0 * (max(values.values()) - min(values.values())) / mean_value
    return f"Scale varies {variation_pct:.0f}% across the calibrated area, worst {worst_label}."


def describe_coplanarity(field: ScaleField, positions: list[tuple[float, float]]) -> str:
    """One line: which side of the observed tag cloud reads nearer the camera, and by how much.

    A co-planar sensor and table give constant px/mm everywhere; the same fitted plane
    `describe_scale_variation` reads is the direct evidence of a gradient instead -- higher
    px/mm means nearer the lens (see `ScaleField`/`_fit_plane`'s relative-depth convention).
    Reuses `_bbox_corner_scale` so this and the scale-variation line can't disagree about which
    corners they're describing.

    Deliberately stops at direction and magnitude, not a tilt angle: converting a scale gradient
    to degrees needs the camera-to-table standoff distance, which Aaron has ruled out measuring
    on this rig (fragile) -- see CLAUDE.md's evidence-gate table and the module docstring this
    line's callers already carry. No angle is offered; inventing one from this data would be
    exactly the derived-not-measured number CLAUDE.md exists to rule out.
    """
    values = _bbox_corner_scale(field, positions)
    mean_value = sum(values.values()) / len(values)
    near_label = max(values, key=values.get)
    far_label = min(values, key=values.get)
    span_pct = 100.0 * (values[near_label] - values[far_label]) / mean_value
    return (
        f"Scale reads {span_pct:.1f}% higher at {near_label} than {far_label} -- that side of "
        "the sensor sits nearer the table. No tilt angle is offered: that needs a standoff-"
        "distance measurement this rig doesn't take (CLAUDE.md's evidence gate)."
    )


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
    area_samples: list[AreaScaleSample] | None = None,
    *,
    coverage_threshold_pct: float = 2.0,
) -> list[str]:
    """Plain-language install report lines, from what's actually been measured so far.

    Deliberately narrow: scale variation, co-planarity direction (from the same fitted field,
    see `describe_coplanarity`), overall coverage sufficiency, which quadrant a coverage gap is
    in, and (when given) the area-scale shape check. Framing is PLAN.md's other install-report
    line, but it needs a real capture's corner-tag/frame-edge check and doesn't belong here yet.
    A roll/tilt *angle* also isn't recoverable from a single photo without a physical standoff-
    distance measurement Aaron has ruled out (the rig is fragile) -- `describe_coplanarity`
    reports direction and magnitude instead of guessing one. No invented figures.
    """
    lines = [describe_scale_variation(field, positions), describe_coplanarity(field, positions)]
    if coverage is not None:
        lines.append(describe_coverage(coverage, threshold_pct=coverage_threshold_pct))
    if regional_coverage is not None:
        lines.extend(describe_regional_coverage(regional_coverage, threshold_pct=coverage_threshold_pct))
    if area_samples:
        lines.append(describe_area_scale_shape(area_samples))
    return lines


def build_calibration_report(
    detections: list[TagDetection],
    tag_sizes_mm: dict[int, float],
    frame_width: float,
    frame_height: float,
    *,
    coverage_threshold_pct: float = 2.0,
) -> list[str]:
    """The install report a real caller should use: builds the field, positions, and global and
    regional coverage from one consistent set of detections, then calls `build_install_report`.

    `build_install_report` itself takes those pieces separately and doesn't check they came from
    the same detections -- useful for testing each line in isolation, but a real caller passing
    mismatched pieces (a field from one capture, coverage from another) would get a coherent-
    looking but wrong report. This is the one function that can't produce that mismatch.

    Skips the coverage line (not the whole report) if there aren't enough tags for a holdout
    split.
    """
    field = build_scale_field(detections, tag_sizes_mm)
    x, y, _ppm = _scale_samples(detections, tag_sizes_mm)
    positions = list(zip(x.tolist(), y.tolist()))

    coverage = None
    try:
        coverage = holdout_coverage_test(detections, tag_sizes_mm)
    except ValueError:
        pass

    regional = regional_coverage_test(detections, tag_sizes_mm, frame_width, frame_height)
    area_samples = area_scale_samples(field, detections, tag_sizes_mm)

    return build_install_report(
        field, positions, coverage, regional, area_samples, coverage_threshold_pct=coverage_threshold_pct
    )


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
            f"need at least 6 pairs of tags to hold out half and still fit a plane "
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


# Calibration artifact: PLAN.md's "calibration is frozen, versioned, exportable." A plain
# versioned dict is enough -- no need for anything fancier until a concrete need for it shows up.
#
# Version 2 added `calibration_tag_size_mm` -- the actual physical size (calliper-measured, not
# assumed) used to build this artifact's scale field. A single hardcoded constant was wrong: the
# calibration sheets are a print run, and a reprint isn't guaranteed to come out at the same size
# (Aaron's callipers found the 2026-09-20 sheets read ~30.02mm, not the 29.3106mm the old rig's
# corner tag measured -- see CLAUDE.md). Recording it per-artifact means a re-print doesn't
# require a source change, and an old artifact stays honest about what it actually assumed.
#
# Version 3 adds `uncertainty_field` (no longer written or read, issue #52) and `frame_stem`.
# `frame_stem` records which saved frame this artifact's field was built from --
# `current.json` otherwise carries no way back to `frames/{stem}.jpg`, since it's a copy of the
# same dict written under a different filename.
CALIBRATION_ARTIFACT_VERSION = 3


def scale_field_to_dict(field: ScaleField) -> dict:
    return {
        "coeffs": list(field._coeffs),
        "mean_px_per_mm": field._mean_px_per_mm,
        "residual_std_pct": field.residual_std_pct,
    }


def scale_field_from_dict(data: dict) -> ScaleField:
    return ScaleField(
        _coeffs=tuple(data["coeffs"]),
        _mean_px_per_mm=data["mean_px_per_mm"],
        residual_std_pct=data["residual_std_pct"],
    )


@dataclass(frozen=True)
class CalibrationArtifact:
    """Everything one setup calibration produces, in one versioned, exportable bundle.

    `corner_baseline` and `lens_position` are optional because a `ScaleField` alone is still a
    valid, usable artifact (e.g. in tests) -- they're populated by the real calibration workflow
    once bench access exists to build them.
    """

    created_at: str  # ISO 8601 timestamp
    scale_field: ScaleField
    corner_baseline: CornerBaseline | None = None
    lens_position: float | None = None
    # Default only serves callers (mostly tests) that don't care what size was assumed -- a real
    # calibration run always passes the value it actually used, calliper-measured or otherwise.
    calibration_tag_size_mm: float = ASSUMED_CALIBRATION_TAG_SIZE_MM
    frame_stem: str | None = None
    version: int = CALIBRATION_ARTIFACT_VERSION
    # The calibration this one was rebuilt from, from that calibration's own stored photo (#286):
    # its scale refitted to tag spacing. None for a calibration made by a run.
    rebuilt_from: str | None = None


def calibration_artifact_to_dict(artifact: CalibrationArtifact) -> dict:
    data: dict = {
        "version": artifact.version,
        "created_at": artifact.created_at,
        "scale_field": scale_field_to_dict(artifact.scale_field),
        "lens_position": artifact.lens_position,
        "calibration_tag_size_mm": artifact.calibration_tag_size_mm,
        "frame_stem": artifact.frame_stem,
    }
    if artifact.rebuilt_from is not None:
        data["rebuilt_from"] = artifact.rebuilt_from
    if artifact.corner_baseline is not None:
        data["corner_baseline"] = {
            str(tag_id): [list(pt) for pt in corners]
            for tag_id, corners in artifact.corner_baseline.corners_by_id.items()
        }
    return data


def calibration_artifact_from_dict(data: dict) -> CalibrationArtifact:
    version = data["version"]
    if version != CALIBRATION_ARTIFACT_VERSION:
        raise ValueError(
            f"unsupported calibration artifact version {version!r}, expected "
            f"{CALIBRATION_ARTIFACT_VERSION}"
        )

    corner_baseline = None
    if "corner_baseline" in data:
        corner_baseline = CornerBaseline(
            corners_by_id={
                int(tag_id): tuple(tuple(pt) for pt in corners)
                for tag_id, corners in data["corner_baseline"].items()
            }
        )

    # Artifacts saved before issue #52 may still hold an "uncertainty_field" key: ignored.
    return CalibrationArtifact(
        version=version,
        created_at=data["created_at"],
        scale_field=scale_field_from_dict(data["scale_field"]),
        corner_baseline=corner_baseline,
        lens_position=data.get("lens_position"),
        calibration_tag_size_mm=data["calibration_tag_size_mm"],
        frame_stem=data.get("frame_stem"),
        rebuilt_from=data.get("rebuilt_from"),
    )
