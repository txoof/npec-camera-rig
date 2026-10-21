"""The tags found in a rig photo, and a reduced copy of it to draw on.

Used by the calibration and gallery routes and by the validation module (#182). A full 64MP frame is about
180 MB, so photos never stay in memory at full size: their tags come from the analysis store
(images.py) and the copy to draw on is decoded straight to PREVIEW_WIDTH. At most one full-size
frame is live at once: the photo being analysed for the first time, under images._full_decode.

Every tag search that web code starts goes through `detect_tags` here, so a test replaces the
detector in this one module.

The errors are answered by app.py: CaptureRefError 422, CaptureNotFoundError 404,
FrameMissingError 409.
"""

import re
from pathlib import Path

import numpy as np

from npec_rig import images
from npec_rig.calibration_store import calibration_frame_path
from npec_rig.captures import photo_file, photos_root
from npec_rig.tags import TagDetection, detect_tags

CAPTURE_REF = re.compile(r"^\d{4}-\d{2}-\d{2}/\d{6}_\d{6}$")
PREVIEW_WIDTH = 2000


class CaptureRefError(ValueError):
    """Not a capture reference (YYYY-MM-DD/HHMMSS_ffffff)."""


class CaptureNotFoundError(LookupError):
    """No photo on disk for a capture reference."""


class FrameMissingError(Exception):
    """A calibration whose photo is no longer on disk."""


def _check_ref(ref: str) -> None:
    if not CAPTURE_REF.match(ref):
        raise CaptureRefError(f"not a capture reference: {ref!r} (expected YYYY-MM-DD/HHMMSS_ffffff)")


def capture_path(ref: str) -> Path:
    _check_ref(ref)
    path = photos_root() / f"{ref}.jpg"
    if not path.exists():
        raise CaptureNotFoundError(f"capture {ref} not found")
    return path


def capture_tags(ref: str) -> list[TagDetection]:
    """Capture `ref`'s tag detections, worked out once per photograph and then read from the
    analysis store (images.py), so even after a restart nothing decodes it at full size again.
    Stored tags are used even if the photograph itself has since been deleted."""
    _check_ref(ref)
    stored = images.stored_tag_detections(ref)
    if stored is not None:
        return stored
    return images.tag_detections(ref, capture_path(ref), detect=lambda frame: detect_tags(frame))


def photo_tags_for(path: str) -> list[TagDetection]:
    """Every tag in gallery photo `path` (a rig photo or an experiment still), searched once and
    then read from the analysis store (images.py). A rig photo is stored under its capture
    reference, so it shares its search with the calibration and validation pages; an experiment
    still under its whole gallery path."""
    try:
        found = photo_file(path)
    except ValueError as exc:
        raise CaptureRefError(str(exc)) from exc
    if found is None:
        raise CaptureNotFoundError(f"photo {path} not found")
    if path.startswith("rig/"):
        return capture_tags(path.removeprefix("rig/"))
    return images.tag_detections(path, found, detect=lambda frame: detect_tags(frame))


def capture_preview(ref: str) -> tuple[np.ndarray, float]:
    """`(preview, preview_scale)`: capture `ref` decoded straight to about PREVIEW_WIDTH, with its
    scale relative to full-resolution pixel coordinates."""
    return images.reduced_frame(capture_path(ref), PREVIEW_WIDTH)


def calibration_ref(frame_stem: str) -> str:
    """The capture ref of a calibration's photo (its `frame_stem`), the images.py source of its
    tags."""
    path = calibration_frame_path(frame_stem)
    if path is None:
        raise FrameMissingError("the saved frame for this calibration is missing on disk")
    return f"{path.parent.name}/{path.stem}"


def calibration_tags(frame_stem: str) -> list[TagDetection]:
    """The tag detections of a calibration's photo, from the analysis store (images.py), the
    same as a validation capture's (`capture_tags`). A run stores the tags it fitted its scale
    to; an older calibration's are worked out once from its photo."""
    try:
        return capture_tags(calibration_ref(frame_stem))
    except CaptureNotFoundError as exc:
        raise FrameMissingError("the saved frame for this calibration is missing on disk") from exc
