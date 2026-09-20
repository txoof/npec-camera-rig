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

TODO.md notes one of the four mounted corner tags is currently partially obscured, so a baseline
built today would have 3 entries, not 4. The tripwire treats a baseline of any size >= 1 as valid,
and only FAILs when a tag *present in the baseline* goes missing from the current frame -- never
for a tag the baseline never had.
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
    baseline_pts = np.array([pt for tag_id in matched_ids for pt in baseline.corners_by_id[tag_id]])
    current_pts = np.array([pt for tag_id in matched_ids for pt in current_by_id[tag_id]])
    roll_deg = _procrustes_rotation_deg(baseline_pts, current_pts)

    scale_delta_pct = {
        tag_id: 100.0
        * (tag_side_px(current_by_id[tag_id]) / tag_side_px(baseline.corners_by_id[tag_id]) - 1.0)
        for tag_id in matched_ids
    }

    messages: list[str] = []
    verdict = "OK"

    if abs(roll_deg) >= roll_fail_deg:
        verdict = "FAIL"
    elif abs(roll_deg) >= roll_drift_deg:
        verdict = "DRIFT" if verdict == "OK" else verdict
    if abs(roll_deg) >= roll_drift_deg:
        direction = "clockwise" if roll_deg > 0 else "counterclockwise"
        messages.append(f"rolled {abs(roll_deg):.1f} deg {direction}")

    worst_tag_id = max(scale_delta_pct, key=lambda tag_id: abs(scale_delta_pct[tag_id]))
    worst_delta = scale_delta_pct[worst_tag_id]
    if abs(worst_delta) >= scale_fail_pct:
        verdict = "FAIL"
    elif abs(worst_delta) >= scale_drift_pct:
        verdict = "DRIFT" if verdict == "OK" else verdict
    if abs(worst_delta) >= scale_drift_pct:
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
