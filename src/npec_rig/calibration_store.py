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

from npec_rig.calibration import (
    CalibrationArtifact,
    calibration_artifact_from_dict,
    calibration_artifact_to_dict,
)

CURRENT_FILENAME = "current.json"


def calibration_root() -> Path:
    """Directory calibration artifacts are written under."""
    return Path(os.environ.get("NPEC_RIG_CALIBRATION_DIR", "/var/lib/npec-rig/calibration"))


def _write_json_atomically(path: Path, data: dict) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, indent=2))
    tmp_path.replace(path)


def save_calibration(artifact: CalibrationArtifact) -> Path:
    """Write `artifact` as a new timestamped file and update the `current.json` pointer.

    Returns the timestamped file's path. Both writes are atomic (write-then-rename) so a reader
    never sees a partially-written file.
    """
    root = calibration_root()
    root.mkdir(parents=True, exist_ok=True)

    data = calibration_artifact_to_dict(artifact)
    stem = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    path = root / f"{stem}.json"
    _write_json_atomically(path, data)
    _write_json_atomically(root / CURRENT_FILENAME, data)
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
