"""Where calibration artifacts live on disk -- rig-level state, separate from experiment captures
(TODO.md, Aaron 2026-09-19). Same env-var-override-with-a-default convention as `settings.py`'s
`db_path()` and `captures.py`'s `photos_root()`.

Follows the schema-versioned-timestamped-JSON-plus-`current.json`-pointer pattern PLAN.md notes
approvingly from the old project's settings persistence (`docs/persistence.md`) -- appropriate
here because a calibration is explicitly "frozen, versioned, exportable" (PLAN.md M2 section A),
unlike camera settings, which went to SQLite instead.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from npec_rig.calibration import (
    CalibrationArtifact,
    calibration_artifact_from_dict,
    calibration_artifact_to_dict,
)
from npec_rig.captures import photos_root

CURRENT_FILENAME = "current.json"
HEATMAPS_DIRNAME = "heatmaps"

logger = logging.getLogger(__name__)

# A calibration stem: the UTC instant of its photo, YYYYMMDDTHHMMSSffffff.
_STEM = re.compile(r"^\d{8}T\d{12}$")


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
    with its photo (`stem_for_photo`); omitted, one is generated the same way it always was.

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


def stem_for_photo(photo: dict) -> str:
    """The calibration stem for a photo saved by `captures.take_photo`: the same instant as the
    photo's own name, so a calibration and its photo can always be found from each other."""
    return photo["date"].replace("-", "") + "T" + Path(photo["filename"]).stem.replace("_", "")


def calibration_frame_path(stem: str) -> Path | None:
    """Where calibration `stem`'s photo is, among the rig photos (`captures.photos_root()`).

    Kept with every other photo, not just the numbers derived from it: every M2 acceptance test
    (PLAN.md, "You verify") is a diff between two calibrations, so a disputed field must be
    re-processable from its original photo without redoing the physical setup. None when the
    stem is not one `stem_for_photo` makes. Calibrations from before #103 kept their frame under
    calibration/frames/, which is no longer read, so their path does not exist.
    """
    if not _STEM.match(stem):
        return None
    ref = f"{stem[0:4]}-{stem[4:6]}-{stem[6:8]}/{stem[9:15]}_{stem[15:21]}"
    return photos_root() / f"{ref}.jpg"


def calibration_frame_url(stem: str | None) -> str | None:
    """The page URL of calibration `stem`'s photo, or None when it is not on disk."""
    path = calibration_frame_path(stem) if stem else None
    if path is None or not path.exists():
        return None
    return f"/photos/{path.parent.name}/{path.name}"


# Diagnostic images that calibration runs used to write under `heatmaps/`, before the plot review
# (issue #53) removed them. Nothing writes them now; deleting a calibration still removes any left
# on disk. Plots drawn now go through images.py.
LEGACY_HEATMAP_SUFFIXES = ("", "_area-shape", "_accuracy-shape", "_table-view", "_table-view-area-shape")


def delete_legacy_heatmaps(stem: str) -> None:
    """Remove calibration `stem`'s old diagnostic images, if any are left."""
    root = calibration_root() / HEATMAPS_DIRNAME
    for suffix in LEGACY_HEATMAP_SUFFIXES:
        (root / f"{stem}{suffix}.jpg").unlink(missing_ok=True)


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
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning("current calibration at %s is unreadable, treating as none saved: %s", path, exc)
        return None


def list_calibrations() -> list[Path]:
    """Every saved calibration artifact file, oldest first. Excludes the `current.json` pointer."""
    root = calibration_root()
    if not root.exists():
        return []
    return sorted(p for p in root.glob("*.json") if p.name != CURRENT_FILENAME)
