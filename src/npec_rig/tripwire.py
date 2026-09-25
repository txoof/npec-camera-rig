"""Per-capture health tripwire: compare the four corner tags against a frozen baseline, verdict
OK / DRIFT / FAIL. PLAN.md's M2 section B.

There is no real baseline yet -- that needs bench access Aaron doesn't currently have -- so
`CornerBaseline` is a plain input, built once from whatever corner tags a real calibration
detects and passed in from wherever the caller keeps it (storage is a separate concern).

**Roll here is not the tilt angle CLAUDE.md/PLAN.md rule out measuring from a single photo.**
That earlier conclusion was about the camera's absolute tilt relative to the table, which needs a
physical standoff-distance measurement. This is different: comparing the *same* four corner tags'
image-plane positions between two photos of the same rig. A pure in-image rotation between two
frames needs no depth information at all -- it's recovered directly from how the points moved
against each other, the same way you'd measure it by overlaying two photos and rotating one until
it lines up. Don't re-litigate this.

All 4 mounted corner tags are detected in every recent real run (verified directly against saved
calibration artifacts, not assumed) -- an earlier note here about one being partially obscured,
giving a 3-entry baseline, was stale and has been corrected. `build_corner_baseline` still accepts
any size >= 1, and `check_tripwire` still only FAILs on a missing-tag basis for a tag *present in
the baseline* going missing -- never for a tag the baseline never had: a real guard, not dead code
for a condition that no longer occurs, since a corner tag could still be knocked loose or
obstructed later. `check_tripwire` itself refuses to compute a roll figure from fewer than 2
*matched* tags (FAILs instead): one tag's own 4 corners measure that tag's own orientation, not
the cross-tag geometry a roll/drift check needs, per PLAN.md's "default to refusing, not
guessing."
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from npec_rig.tags import CORNER_ID_RANGE, TagDetection, tag_side_px

Corners = tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]

# Provisional -- PLAN.md's M2 acceptance tests ("roll the camera ~5 deg -> reported as ~5 deg;
# knock it hard -> verdict flips to FAIL") are the actual measurement that tunes these, not this
# guess. Set so that a deliberate ~5 deg test roll lands as DRIFT, matching PLAN.md's wording
# treating "roll ~5 deg" and "knock it hard" as two different, escalating actions -- only the
# latter should FAIL.
DEFAULT_ROLL_DRIFT_DEG = 1.0
DEFAULT_ROLL_FAIL_DEG = 10.0
DEFAULT_SCALE_DRIFT_PCT = 3.0
DEFAULT_SCALE_FAIL_PCT = 8.0


@dataclass(frozen=True)
class CornerBaseline:
    """Corner tag corners recorded at calibration time, keyed by tag id.

    Whatever subset of the (up to 4) mounted corner tags was actually detected when the baseline
    was built -- not assumed to be exactly 4.
    """

    corners_by_id: dict[int, Corners]


def build_corner_baseline(detections: list[TagDetection]) -> CornerBaseline:
    """Baseline from whichever corner tags (`CORNER_ID_RANGE`) are present in `detections`.

    Raises ValueError if none are -- a baseline with zero tags can't detect anything.
    """
    corner_detections = {d.tag_id: d.corners for d in detections if d.tag_id in CORNER_ID_RANGE}
    if not corner_detections:
        raise ValueError("no corner tags detected -- can't build a baseline")
    return CornerBaseline(corners_by_id=corner_detections)


@dataclass(frozen=True)
class TripwireResult:
    """OK / DRIFT / FAIL for one capture, against a `CornerBaseline`."""

    verdict: str  # "OK" | "DRIFT" | "FAIL"
    messages: tuple[str, ...]
    roll_deg: float | None
    scale_delta_pct: dict[int, float] | None  # per corner tag id; +ve = larger now (closer)


def _procrustes_rotation_deg(baseline_pts: np.ndarray, current_pts: np.ndarray) -> float:
    """Best-fit rotation (degrees) taking `baseline_pts` onto `current_pts`, ignoring translation
    and scale (2D Kabsch/Procrustes). Positive = clockwise in image coordinates (x right, y down)
    -- verified against a known synthetic rotation in tests/test_tripwire.py, not assumed.
    """
    baseline_centered = baseline_pts - baseline_pts.mean(axis=0)
    current_centered = current_pts - current_pts.mean(axis=0)
    h = baseline_centered.T @ current_centered
    u, _s, vt = np.linalg.svd(h)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt = vt.copy()
        vt[-1, :] *= -1
        rotation = vt.T @ u.T
    return float(np.degrees(np.arctan2(rotation[1, 0], rotation[0, 0])))


def check_tripwire(
    baseline: CornerBaseline,
    current: list[TagDetection],
    *,
    roll_drift_deg: float = DEFAULT_ROLL_DRIFT_DEG,
    roll_fail_deg: float = DEFAULT_ROLL_FAIL_DEG,
    scale_drift_pct: float = DEFAULT_SCALE_DRIFT_PCT,
    scale_fail_pct: float = DEFAULT_SCALE_FAIL_PCT,
) -> TripwireResult:
    """Compare `current`'s corner tags against `baseline`. Conservative: any ambiguity fails
    rather than guesses.
    """
    current_by_id = {d.tag_id: d.corners for d in current}
    missing = sorted(tag_id for tag_id in baseline.corners_by_id if tag_id not in current_by_id)
    if missing:
        return TripwireResult(
            verdict="FAIL",
            messages=(f"corner tag(s) {missing} present at calibration are missing now",),
            roll_deg=None,
            scale_delta_pct=None,
        )

    matched_ids = sorted(baseline.corners_by_id)
    if len(matched_ids) < 2:
        # Rotation from a single tag's own 4 corners measures that tag's own orientation (e.g.
        # its mount coming loose), not the cross-tag geometry a roll/drift check needs -- refusing
        # rather than presenting that as a confident rig-wide roll figure.
        return TripwireResult(
            verdict="FAIL",
            messages=(
                f"only {len(matched_ids)} corner tag(s) matched -- not enough to check "
                "roll/drift confidently",
            ),
            roll_deg=None,
            scale_delta_pct=None,
        )

    baseline_pts = np.array([pt for tag_id in matched_ids for pt in baseline.corners_by_id[tag_id]])
    current_pts = np.array([pt for tag_id in matched_ids for pt in current_by_id[tag_id]])
    roll_deg = _procrustes_rotation_deg(baseline_pts, current_pts)

    scale_delta_pct = {
        tag_id: 100.0
        * (tag_side_px(current_by_id[tag_id]) / tag_side_px(baseline.corners_by_id[tag_id]) - 1.0)
        for tag_id in matched_ids
    }
    worst_tag_id = max(scale_delta_pct, key=lambda tag_id: abs(scale_delta_pct[tag_id]))
    worst_delta = scale_delta_pct[worst_tag_id]

    def _level(magnitude: float, drift_at: float, fail_at: float) -> str:
        if magnitude >= fail_at:
            return "FAIL"
        if magnitude >= drift_at:
            return "DRIFT"
        return "OK"

    roll_level = _level(abs(roll_deg), roll_drift_deg, roll_fail_deg)
    scale_level = _level(abs(worst_delta), scale_drift_pct, scale_fail_pct)
    verdict = "FAIL" if "FAIL" in (roll_level, scale_level) else (
        "DRIFT" if "DRIFT" in (roll_level, scale_level) else "OK"
    )

    messages: list[str] = []
    if roll_level != "OK":
        direction = "clockwise" if roll_deg > 0 else "counterclockwise"
        messages.append(f"rolled {abs(roll_deg):.1f} deg {direction}")
    if scale_level != "OK":
        direction = "closer" if worst_delta > 0 else "farther"
        messages.append(f"near corner tag {worst_tag_id} is {abs(worst_delta):.0f}% {direction}")
    if not messages:
        messages.append("no significant drift detected")

    return TripwireResult(
        verdict=verdict,
        messages=tuple(messages),
        roll_deg=roll_deg,
        scale_delta_pct=scale_delta_pct,
    )


@dataclass(frozen=True)
class CornerLevelReading:
    """One corner tag's apparent size compared to the *other currently-detected* corner tags --
    self-referential, no baseline needed. See `corner_level_readings` for the physics."""

    tag_id: int
    centre: tuple[float, float]
    deviation_pct: float  # +ve = larger than the mean of the others (closer to the camera)
    status: str  # "ok" | "drift" | "fail"


def corner_level_readings(
    detections: list[TagDetection],
    *,
    drift_pct: float = DEFAULT_SCALE_DRIFT_PCT,
    fail_pct: float = DEFAULT_SCALE_FAIL_PCT,
) -> list[CornerLevelReading]:
    """How co-planar the table is with the camera, read live with no zero/baseline step: under a
    pinhole projection, a tag's apparent size depends only on its distance from the camera, not on
    where it sits within a fronto-parallel plane. So if the table is co-planar, every corner tag
    reads the same size *right now*, regardless of how each one happens to be mounted -- this
    doesn't assume symmetric placement the way a fixed-ROI approach would.

    Reuses `DEFAULT_SCALE_DRIFT_PCT`/`DEFAULT_SCALE_FAIL_PCT`, the same bands `check_tripwire`
    already uses for its (baseline-relative) `scale_delta_pct` -- one definition of "how much
    size difference matters," not two.

    Returns one reading per currently-detected corner tag (`CORNER_ID_RANGE`), or an empty list if
    fewer than 2 are detected -- "different from the mean of the others" needs at least 2 to
    compare. Unlike `check_tripwire`, there is no baseline here, so a corner tag that isn't
    currently detected has no "missing" status to report -- there's nothing to know it's missing
    *from* before any calibration exists.
    """
    corner_detections = [d for d in detections if d.tag_id in CORNER_ID_RANGE]
    if len(corner_detections) < 2:
        return []

    sides = {d.tag_id: tag_side_px(d.corners) for d in corner_detections}
    mean_side = sum(sides.values()) / len(sides)
    centres = {d.tag_id: d.centre for d in corner_detections}

    readings = []
    for tag_id, side in sides.items():
        deviation_pct = 100.0 * (side / mean_side - 1.0)
        magnitude = abs(deviation_pct)
        if magnitude >= fail_pct:
            status = "fail"
        elif magnitude >= drift_pct:
            status = "drift"
        else:
            status = "ok"
        readings.append(
            CornerLevelReading(
                tag_id=tag_id, centre=centres[tag_id], deviation_pct=deviation_pct, status=status
            )
        )
    return readings
