"""Where calibration artifacts live on disk -- rig-level state, separate from experiment captures
(TODO.md, Aaron 2026-09-19). Same env-var-override-with-a-default convention as `settings.py`'s
`db_path()` and `captures.py`'s `captures_root()`.

Follows the schema-versioned-timestamped-JSON-plus-`current.json`-pointer pattern PLAN.md notes
approvingly from the old project's settings persistence (`docs/persistence.md`) -- appropriate
here because a calibration is explicitly "frozen, versioned, exportable" (PLAN.md M2 section A),
unlike camera settings, which went to SQLite instead.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from npec_rig.calibration import (
    CalibrationArtifact,
    calibration_artifact_from_dict,
    calibration_artifact_to_dict,
)
from npec_rig.camera import array_to_jpeg

CURRENT_FILENAME = "current.json"
FRAMES_DIRNAME = "frames"
HEATMAPS_DIRNAME = "heatmaps"


def calibration_root() -> Path:
    """Directory calibration artifacts are written under."""
    return Path(os.environ.get("NPEC_RIG_CALIBRATION_DIR", "/var/lib/npec-rig/calibration"))


def _write_json_atomically(path: Path, data: dict) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, indent=2))
    tmp_path.replace(path)


def save_calibration(
    artifact: CalibrationArtifact, *, stem: str | None = None, promote: bool = True
) -> Path:
    """Write `artifact` as a new timestamped file, and, if `promote`, update the `current.json`
    pointer.

    Returns the timestamped file's path. Both writes are atomic (write-then-rename) so a reader
    never sees a partially-written file. `stem` lets a caller line this artifact's filename up
    with a frame saved by `save_calibration_frame` from the same capture; omitted, one is
    generated the same way it always was.

    `promote=False` keeps this artifact off `current.json` -- for a calibration run taken to
    *compare* against the live one (PLAN.md's two-baseline/two-height tests), which must not
    silently replace the baseline `check_tripwire` is reading mid-acceptance-test. Always
    written to its own timestamped file regardless, so it's never lost.
    """
    root = calibration_root()
    root.mkdir(parents=True, exist_ok=True)

    data = calibration_artifact_to_dict(artifact)
    stem = stem or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    path = root / f"{stem}.json"
    _write_json_atomically(path, data)
    if promote:
        _write_json_atomically(root / CURRENT_FILENAME, data)
    return path


def save_calibration_frame(image: np.ndarray, *, stem: str | None = None) -> Path:
    """Write `image` as a full-res JPEG under the calibration frames directory, timestamped.

    Kept alongside the artifact it produced, not just the numbers derived from it: every M2
    acceptance test (PLAN.md, "You verify") is a diff between two calibrations, so a bad or
    disputed field must be re-processable from its original frame without redoing the physical
    setup.
    """
    root = calibration_root() / FRAMES_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    stem = stem or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    path = root / f"{stem}.jpg"
    path.write_bytes(array_to_jpeg(image))
    return path


def save_calibration_heatmap(image: np.ndarray, *, stem: str) -> Path:
    """Write `image` (already rendered by `calibration_viz.render_uncertainty_heatmap`) as a
    JPEG under its own directory, keyed by the same `stem` as the frame and artifact it came
    from -- a rendering, not a measurement, so it lives separately from both.
    """
    root = calibration_root() / HEATMAPS_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{stem}.jpg"
    path.write_bytes(array_to_jpeg(image))
    return path


def save_calibration_area_shape_heatmap(image: np.ndarray, *, stem: str) -> Path:
    """Write `image` (rendered by `calibration_viz.render_area_shape_heatmap`) as a JPEG under
    the same heatmaps directory as `save_calibration_heatmap`, with a `_area-shape` suffix on
    the stem so the two renderings from one capture don't collide.
    """
    root = calibration_root() / HEATMAPS_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{stem}_area-shape.jpg"
    path.write_bytes(array_to_jpeg(image))
    return path


def load_calibration(path: Path) -> CalibrationArtifact:
    """Load a specific calibration artifact file."""
    return calibration_artifact_from_dict(json.loads(Path(path).read_text()))


def load_current_calibration() -> CalibrationArtifact | None:
    """The active calibration, or None if none has ever been saved."""
    path = calibration_root() / CURRENT_FILENAME
    if not path.exists():
        return None
    return load_calibration(path)


def list_calibrations() -> list[Path]:
    """Every saved calibration artifact file, oldest first. Excludes the `current.json` pointer."""
    root = calibration_root()
    if not root.exists():
        return []
    return sorted(p for p in root.glob("*.json") if p.name != CURRENT_FILENAME)
