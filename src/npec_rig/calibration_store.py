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
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

from npec_rig.calibration import (
    CalibrationArtifact,
    calibration_artifact_from_dict,
    calibration_artifact_to_dict,
)
from npec_rig.camera import array_to_jpeg

CURRENT_FILENAME = "current.json"
FRAMES_DIRNAME = "frames"
HEATMAPS_DIRNAME = "heatmaps"

logger = logging.getLogger(__name__)


def calibration_root() -> Path:
    """Directory calibration artifacts are written under."""
    return Path(os.environ.get("NPEC_RIG_CALIBRATION_DIR", "/var/lib/npec-rig/calibration"))


def _write_json_atomically(path: Path, data: dict) -> None:
    """Write-then-rename, with a per-call-unique temp file.

    A fixed tmp name (e.g. `path` + `.tmp`) would be shared by every writer of the same `path` --
    for `current.json` specifically, two calibration runs overlapping in the request threadpool
    both write and rename the *same* tmp file, which can interleave their bytes into malformed
    JSON or have the second `replace` silently promote stale content. `tempfile.mkstemp` in the
    same directory gives each call its own file, and keeps the rename atomic on one filesystem.
    """
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.stem + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(data, indent=2))
        os.chmod(tmp_name, 0o644)  # mkstemp defaults to 0600; match write_text's umask-based mode
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


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


def load_calibration_frame(stem: str) -> np.ndarray:
    """Read back a frame written by `save_calibration_frame`, as an RGB array -- for
    reprocessing (re-detecting tags) against a saved calibration without a fresh capture, e.g.
    the best-vs-worst-tag rank plot, which needs per-tag data no artifact schema persists.
    """
    path = calibration_root() / FRAMES_DIRNAME / f"{stem}.jpg"
    return np.array(Image.open(path).convert("RGB"))


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


def save_calibration_accuracy_shape_heatmap(image: np.ndarray, *, stem: str) -> Path:
    """Write `image` (rendered by `calibration_viz.render_uncertainty_heatmap` with a large `k`)
    as a JPEG under the same heatmaps directory as `save_calibration_heatmap`, with an
    `_accuracy-shape` suffix -- the smoothed-neighbourhood accuracy-shape view (Aaron/supervisor,
    2026-09-25), distinct from the small-`k` coverage-gap heatmap the plain `.jpg` stem holds.
    """
    root = calibration_root() / HEATMAPS_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{stem}_accuracy-shape.jpg"
    path.write_bytes(array_to_jpeg(image))
    return path


def save_calibration_table_view(image: np.ndarray, *, stem: str) -> Path:
    """Write `image` (rendered by `calibration_viz.render_table_view` for the scale-residual
    field) as a JPEG under the same heatmaps directory as `save_calibration_heatmap`, with a
    `_table-view` suffix on the stem so the straightened view doesn't collide with the raw-photo
    heatmap from the same capture.
    """
    root = calibration_root() / HEATMAPS_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{stem}_table-view.jpg"
    path.write_bytes(array_to_jpeg(image))
    return path


def save_calibration_table_view_area_shape(image: np.ndarray, *, stem: str) -> Path:
    """Write `image` (rendered by `calibration_viz.render_table_view` for the area-shape field)
    as a JPEG under the same heatmaps directory, with a `_table-view-area-shape` suffix -- the
    table-view analogue of `save_calibration_area_shape_heatmap`.
    """
    root = calibration_root() / HEATMAPS_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{stem}_table-view-area-shape.jpg"
    path.write_bytes(array_to_jpeg(image))
    return path


def load_calibration(path: Path) -> CalibrationArtifact:
    """Load a specific calibration artifact file."""
    return calibration_artifact_from_dict(json.loads(Path(path).read_text()))


def load_current_calibration() -> CalibrationArtifact | None:
    """The active calibration, or None if none has ever been saved, or the saved one can't be
    read back (an older/newer schema version, or a truncated/corrupt file) -- every caller of
    this already treats None as "no calibration to show yet", so a stale or unreadable
    current.json degrades to that instead of a 500 on every calibration route."""
    path = calibration_root() / CURRENT_FILENAME
    if not path.exists():
        return None
    try:
        return load_calibration(path)
    except (ValueError, KeyError) as exc:
        logger.warning("current calibration at %s is unreadable, treating as none saved: %s", path, exc)
        return None


def list_calibrations() -> list[Path]:
    """Every saved calibration artifact file, oldest first. Excludes the `current.json` pointer."""
    root = calibration_root()
    if not root.exists():
        return []
    return sorted(p for p in root.glob("*.json") if p.name != CURRENT_FILENAME)
