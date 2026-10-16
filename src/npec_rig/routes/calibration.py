"""Routes for calibration: the wizard and history pages, a calibration run, saved calibrations
and their plots, the certainty map, the level overlay and the tripwire check. Also the tag
lookup for photos, which validation uses too."""

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from PIL import Image

from npec_rig import images, validation_store
from npec_rig.calibration import (
    CalibrationArtifact,
    ScaleResidualSample,
    build_calibration_report,
    build_scale_field,
    build_table_frame,
    scale_field_from_dict,
    scale_field_to_dict,
    scale_residual_samples,
)
from npec_rig.calibration_store import (
    CURRENT_FILENAME,
    calibration_frame_path,
    calibration_frame_url,
    calibration_root,
    delete_legacy_heatmaps,
    list_calibrations,
    load_calibration,
    load_current_calibration,
    save_calibration,
    stem_for_photo,
)
from npec_rig.calibration_viz import (
    HEATMAP_MAX_WIDTH,
    TAG_MAP_FAR_PCT,
    radial_fit,
    render_level_overlay,
    render_radial_residual_plot,
    render_tag_map,
)
from npec_rig.camera import CameraManager, array_to_jpeg
from npec_rig.captures import photos_root, take_photo
from npec_rig.certainty_map import SlotLayoutError, certainty_by_slot, render_certainty_map
from npec_rig.routes.shared import _derived_response, templates
from npec_rig.tags import (
    ASSUMED_CALIBRATION_TAG_SIZE_MM,
    CALIBRATION_ID_RANGE,
    CORNER_ID_RANGE,
    detect_tags,
)
from npec_rig.tripwire import (
    CornerBaseline,
    build_corner_baseline,
    check_tripwire,
    corner_level_readings,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/setup/calibration")
def setup_calibration_page(request: Request) -> Response:
    """The calibration wizard (7 steps) and its diagnostics."""
    return templates.TemplateResponse(request, "setup_calibration.html")


@router.get("/setup/calibration-history")
def setup_calibration_history_page(request: Request) -> Response:
    """Browse every saved calibration, promote one to active, or delete old ones -- split out of
    the wizard (2026-09-26): reachable on its own, not nested three `<details>` deep inside Step
    5, and usable without walking the linear wizard."""
    return templates.TemplateResponse(request, "setup_calibration_history.html")


@router.get("/setup/calibration-history/{stem}")
def setup_calibration_history_diagnostics_page(stem: str, request: Request) -> Response:
    """Calibration diagnostics for one saved run, opened from the calibration history: its tag
    map and lens check with their numbers. The page looks the run up in `/calibration/list`."""
    return _calibration_diagnostics_page(
        request, stem, f"/calibration/{stem}", "Calibration history", "/setup/calibration-history"
    )


@router.get("/setup/calibration/diagnostics")
def setup_current_calibration_diagnostics_page(request: Request) -> Response:
    """Calibration diagnostics for the active calibration, from current.json itself (not the
    history file of the same name), opened from the wizard's Step 5."""
    return _calibration_diagnostics_page(
        request, None, "/calibration/current", "Calibration", "/setup/calibration#step-5"
    )


def _calibration_diagnostics_page(
    request: Request, stem: str | None, plot_base: str, back_label: str, back_href: str
) -> Response:
    return templates.TemplateResponse(
        request,
        "setup_calibration_diagnostics.html",
        {"stem": stem, "plot_base": plot_base, "back_label": back_label, "back_href": back_href},
    )


@router.get("/setup/health-check")
def setup_health_check_page(request: Request) -> Response:
    """On-demand checks outside the linear calibration wizard -- currently just the tripwire
    check, moved here from the wizard (Aaron, 2026-09-25: "should not be part of the wizard,
    should be moved to a 'health check' screen")."""
    return templates.TemplateResponse(request, "setup_health_check.html")


# Calibration's own readiness gate (TODO.md, "Give Lock focus a real function"): all 4 mounted
# corner tags, not check_tripwire's 2-tag minimum -- that check answers "has something changed
# since a good baseline", this one answers "is the camera positioned well enough to calibrate at
# all", which is a stricter bar by design (Aaron, 2026-09-28).
CORNER_TAGS_REQUIRED_FOR_CALIBRATION = 4


def _calibration_readiness() -> dict:
    """Live check for calibration's own gate: is focus currently locked, and are all 4 corner
    tags currently detectable. Cheap -- a main-stream frame, not a full-res capture -- so it can
    be polled from the wizard, and re-checked by `/calibration/run` itself right before the
    expensive capture (the backend never trusts a frontend-only check).
    """
    manager = CameraManager.instance()
    focus_locked = manager.focus_status()["locked"]
    frame = manager.capture_array()
    corner_tags_detected = len([d for d in detect_tags(frame) if d.tag_id in CORNER_ID_RANGE])
    return {
        "focus_locked": focus_locked,
        "corner_tags_detected": corner_tags_detected,
        "corner_tags_required": CORNER_TAGS_REQUIRED_FOR_CALIBRATION,
        "ready": focus_locked and corner_tags_detected >= CORNER_TAGS_REQUIRED_FOR_CALIBRATION,
    }


@router.get("/calibration/readiness")
def calibration_readiness() -> dict:
    """`_calibration_readiness` as its own endpoint, for the wizard to poll live on Step 5."""
    return _calibration_readiness()


def _build_calibration_delta(
    previous: CalibrationArtifact | None,
    *,
    residual_std_pct: float,
    corner_tag_count: int,
    calibration_tag_size_mm: float,
    lens_position: float | None,
    px_per_mm_at_centre: float | None,
    frame_width: int,
    frame_height: int,
) -> dict | None:
    """Compare this run's headline numbers against whatever was the active calibration right
    before this run replaced it (Aaron, 2026-09-28). Cheap, no re-detection: every value here
    already lives on the saved artifact or was just computed for this run's own result -- the
    same caution TODO.md already applies to the history browser (re-detecting tags from every
    saved frame just to show a number is real cost, not a one-line change).
    """
    if previous is None:
        return None

    previous_corner_count = (
        len(previous.corner_baseline.corners_by_id) if previous.corner_baseline else 0
    )
    try:
        previous_px_per_mm = previous.scale_field.px_per_mm(frame_width / 2, frame_height / 2)
    except ValueError:
        previous_px_per_mm = None

    def metric(previous_value: float | None, current_value: float | None) -> dict:
        delta = (
            current_value - previous_value
            if previous_value is not None and current_value is not None
            else None
        )
        return {"previous": previous_value, "current": current_value, "delta": delta}

    return {
        "previous_created_at": previous.created_at,
        "residual_std_pct": metric(previous.scale_field.residual_std_pct, residual_std_pct),
        "corner_tags_detected": metric(previous_corner_count, corner_tag_count),
        "calibration_tag_size_mm": metric(
            previous.calibration_tag_size_mm, calibration_tag_size_mm
        ),
        "lens_position": metric(previous.lens_position, lens_position),
        "px_per_mm_at_centre": metric(previous_px_per_mm, px_per_mm_at_centre),
    }


@router.post("/calibration/run")
def run_calibration(
    promote: bool = True,
    calibration_tag_size_mm: float | None = None,
    override_focus_gate: bool = False,
) -> dict:
    """Setup calibration (PLAN.md M2 section A): capture a full-res still, detect tags, build the
    scale field and install report, and save the frame plus the resulting artifact.

    `override_focus_gate=True` skips the readiness gate below (focus locked, all 4 corner tags
    detected) -- a data-quality check, not a safety one, so it warns rather than refuses outright:
    the operator always has an explicit way through (Aaron, 2026-09-28, see TODO.md's Lock-focus
    entry). Without it, a failed gate returns early with `gate_failed: true` and no capture, so a
    predictably-bad run doesn't cost the ~8.5s full-res round trip.

    Saving the frame, not just the numbers derived from it, matters here: every M2 acceptance
    test (PLAN.md "You verify") is a diff between two calibrations, so a disputed field must be
    re-processable from its original capture without redoing the physical paper-sheet setup.

    `promote=False` (the "set as current baseline" checkbox, unticked) saves this run without
    replacing the active `current.json` -- for a comparison run (the two-baseline/two-height
    tests) taken while a real baseline is still live for `/calibration/tripwire/check` to read.

    `calibration_tag_size_mm`, if given, is the operator's own calliper measurement of *this*
    print run's calibration tags, overriding `ASSUMED_CALIBRATION_TAG_SIZE_MM` -- that constant
    is a placeholder for whoever hasn't measured yet, not a substitute for measuring. A reprint at
    a different size needs a new measurement typed in here, not a source change.

    """
    # Checked before anything below: a refused run (no capture, gate_failed) must have no
    # lasting side effects.
    if not override_focus_gate:
        readiness = _calibration_readiness()
        if not readiness["ready"]:
            if not readiness["focus_locked"]:
                message = "Focus is not confirmed -- confirm focus before running calibration."
            else:
                required = readiness["corner_tags_required"]
                message = (
                    f"{readiness['corner_tags_detected']} of {required} corner tags detected. "
                    f"A minimum of {required} is required for a successful calibration."
                )
            return {"error": message, "gate_failed": True, **readiness}

    tag_size_mm = calibration_tag_size_mm if calibration_tag_size_mm is not None else (
        ASSUMED_CALIBRATION_TAG_SIZE_MM
    )

    manager = CameraManager.instance()

    # Captured before this run's own save/promote below can overwrite current.json -- the
    # "previous" half of the post-run delta.
    previous_artifact = load_current_calibration()

    array, photo = take_photo("calibration")
    frame_height, frame_width = array.shape[0], array.shape[1]

    detections = detect_tags(array)
    calibration_detections = [d for d in detections if d.tag_id in CALIBRATION_ID_RANGE]
    corner_detections = [d for d in detections if d.tag_id in CORNER_ID_RANGE]
    tag_sizes_mm = {d.tag_id: tag_size_mm for d in calibration_detections}

    stem = stem_for_photo(photo)

    result: dict = {
        "calibration_tags_detected": len(calibration_detections),
        "corner_tags_detected": len(corner_detections),
        "calibration_tag_size_mm": tag_size_mm,
        "calibration_tag_size_mm_is_default": calibration_tag_size_mm is None,
        "frame_path": str(calibration_frame_path(stem)),
        # Recorded, not a gate (Aaron, 2026-10-08): the run is promoted as before.
        "photo_flags": photo["flags"],
    }

    try:
        field = build_scale_field(detections, tag_sizes_mm)
    except ValueError as exc:
        result["error"] = str(exc)
        return result
    # The tags this run fitted its scale to, kept as the photo's tags: the diagnostic plots then
    # need no second full-size search of the saved photo, and plot the same tags as the fit.
    images.store_tag_detections(f"{photo['date']}/{Path(photo['filename']).stem}", detections)

    try:
        result["report"] = build_calibration_report(detections, tag_sizes_mm, frame_width, frame_height)
    except ValueError as exc:
        result["report"] = [f"Install report unavailable: {exc}"]
    result["residual_std_pct"] = field.residual_std_pct
    try:
        result["px_per_mm_at_centre"] = field.px_per_mm(frame_width / 2, frame_height / 2)
    except ValueError:
        result["px_per_mm_at_centre"] = None

    try:
        corner_baseline = build_corner_baseline(detections)
    except ValueError:
        corner_baseline = None
    result["corner_baseline_tags"] = sorted(corner_baseline.corners_by_id) if corner_baseline else []

    result["frame_url"] = calibration_frame_url(stem)

    lens_position = manager.get_lens_position()
    result["previous_calibration_comparison"] = _build_calibration_delta(
        previous_artifact,
        residual_std_pct=field.residual_std_pct,
        corner_tag_count=len(corner_baseline.corners_by_id) if corner_baseline else 0,
        calibration_tag_size_mm=tag_size_mm,
        lens_position=lens_position,
        px_per_mm_at_centre=result["px_per_mm_at_centre"],
        frame_width=frame_width,
        frame_height=frame_height,
    )
    artifact = CalibrationArtifact(
        created_at=datetime.now(timezone.utc).isoformat(),
        scale_field=field,
        corner_baseline=corner_baseline,
        lens_position=lens_position,
        calibration_tag_size_mm=tag_size_mm,
        frame_stem=stem,
    )
    result["artifact_path"] = str(save_calibration(artifact, stem=stem, promote=promote))
    result["promoted_to_current"] = promote
    result["lens_position"] = lens_position
    return result


@router.get("/calibration/list")
def list_calibration_artifacts() -> list[dict]:
    """Every saved calibration artifact, newest first, with URLs to download it and (if saved)
    the frame it came from -- the "exportable" half of PLAN.md's "frozen, versioned, exportable."

    Also carries the calibration-history browser's per-entry summary stats -- only ones already
    on the artifact (`residual_std_pct`, `calibration_tag_size_mm`, corner-tag count), no
    re-detection from the saved frame. Coplanarity/holdout/area-scale error need re-detecting
    tags from each saved frame and are deliberately left out of this list (reference/plans/
    calibration-history-browser.md's "real gaps" section) -- a per-entry drill-down view is where
    those belong, not a list that must stay fast with many saved runs.
    """
    current = load_current_calibration()
    entries = []
    for path in reversed(list_calibrations()):
        stem = path.stem
        try:
            artifact = load_calibration(path)
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning(
                "saved calibration %s is unreadable, listing without stats: %s", path, exc
            )
            artifact = None
        stats = (
            {
                "created_at": artifact.created_at,
                "residual_std_pct": artifact.scale_field.residual_std_pct,
                "calibration_tag_size_mm": artifact.calibration_tag_size_mm,
                "corner_tag_count": (
                    len(artifact.corner_baseline.corners_by_id) if artifact.corner_baseline else 0
                ),
                "is_current": current is not None and artifact.created_at == current.created_at,
            }
            if artifact is not None
            else {
                "created_at": None,
                "residual_std_pct": None,
                "calibration_tag_size_mm": None,
                "corner_tag_count": None,
                "is_current": False,
            }
        )
        frame_url = calibration_frame_url(path.stem)
        entries.append(
            {
                "stem": stem,
                "filename": path.name,
                "url": f"/calibration/files/{path.name}",
                "frame_url": frame_url,
                **stats,
            }
        )
    return entries


def _saved_calibration_path(stem: str) -> Path:
    """Resolve a calibration-history `stem` (a URL path segment) to its artifact JSON file,
    refusing anything that isn't a plain filename component -- `stem` comes straight from the
    request path, and building a file path by string interpolation is exactly the shape that
    needs this before it ever gets used, not after.
    """
    root = calibration_root()
    path = (root / f"{stem}.json").resolve()
    if path.parent != root.resolve() or path.name in (".json", CURRENT_FILENAME):
        raise HTTPException(404, f"no saved calibration {stem!r}")
    if not path.exists():
        raise HTTPException(404, f"no saved calibration {stem!r}")
    return path


def _load_saved_artifact(stem: str) -> CalibrationArtifact:
    """Load a saved calibration by history `stem`, for routes that need the full artifact rather
    than just its list-view stats -- the diagnostics drill-down and promote both want this."""
    path = _saved_calibration_path(stem)
    try:
        return load_calibration(path)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, f"saved calibration {stem!r} could not be read: {exc}") from exc


@router.post("/calibration/{stem}/promote")
def promote_calibration(stem: str) -> dict:
    """Make a previously saved calibration the active one, no fresh capture -- the
    calibration-history browser's "reactivate an old, still-valid measurement" action
    (reference/plans/calibration-history-browser.md). Reuses `save_calibration`'s own
    promote-to-`current.json` mechanism, the same one a live run's "set as current baseline"
    checkbox already uses.
    """
    artifact = _load_saved_artifact(stem)
    save_calibration(artifact, stem=stem, promote=True)
    return {"promoted": stem, "created_at": artifact.created_at}


@router.delete("/calibration/{stem}")
def delete_calibration(stem: str) -> dict:
    """Delete a saved calibration's artifact JSON, frame, and heatmap files -- disk hygiene for
    old runs (reference/plans/calibration-history-browser.md). Refuses to delete whichever one
    `current.json` currently points at, which would otherwise leave the rig's active calibration
    with a snapshot/report that no longer exists.

    `current.json` has no record of which stem it was promoted from (compared by `created_at`
    instead, see `list_calibration_artifacts`), so confirming "not the active one" requires
    reading both files. If either can't be read, this refuses rather than guessing -- a corrupt
    `current.json` means we don't know what's active at all, and a corrupt target stem can't be
    ruled out as the active one either (it could have been promoted before whatever damaged it).
    """
    path = _saved_calibration_path(stem)

    current_path = calibration_root() / CURRENT_FILENAME
    current = load_current_calibration() if current_path.exists() else None
    if current_path.exists() and current is None:
        raise HTTPException(
            409,
            "the active calibration (current.json) could not be read -- refusing to delete "
            "anything until that is resolved, since which calibration is active cannot be "
            "confirmed",
        )

    try:
        artifact = load_calibration(path)
    except (ValueError, KeyError, TypeError) as exc:
        if current is not None:
            raise HTTPException(
                409,
                f"saved calibration {stem!r} could not be read ({exc}) -- refusing to delete it "
                "since whether it is the active calibration cannot be confirmed from its content",
            ) from exc
    else:
        if current is not None and artifact.created_at == current.created_at:
            raise HTTPException(409, "refusing to delete the active calibration")

    path.unlink()
    # The photo stays with the other rig photos: originals are never changed (PLAN.md).
    # A validation session only means anything against its own calibration.
    validation_store.delete_sessions_for_calibration(stem)
    validation_store.delete_slot_layout(stem)
    delete_legacy_heatmaps(stem)
    images.forget_source(_calibration_source(stem))
    return {"deleted": stem}


@router.get("/calibration/current")
def current_calibration() -> dict:
    """Summary of the active saved calibration, so the operator knows which one is live."""
    artifact = load_current_calibration()
    if artifact is None:
        return {"exists": False}
    frame_url = calibration_frame_url(artifact.frame_stem)
    return {
        "exists": True,
        "frame_stem": artifact.frame_stem,
        "created_at": artifact.created_at,
        "residual_std_pct": artifact.scale_field.residual_std_pct,
        "lens_position": artifact.lens_position,
        "calibration_tag_size_mm": artifact.calibration_tag_size_mm,
        "corner_baseline_tags": (
            sorted(artifact.corner_baseline.corners_by_id) if artifact.corner_baseline else []
        ),
        "frame_url": frame_url,
    }


def _calibration_source(stem: str) -> str:
    """The images.py source for calibration `stem`'s plots, so deleting the calibration forgets
    them."""
    return f"calibration:{stem}"


def _calibration_ref(frame_stem: str) -> str:
    """The capture ref of a calibration's photo (its `frame_stem`), the images.py source of its
    tags. 409 for a stem that names no rig photo."""
    path = calibration_frame_path(frame_stem)
    if path is None:
        raise HTTPException(409, "the saved frame for this calibration is missing on disk")
    return f"{path.parent.name}/{path.stem}"


def _calibration_tags(frame_stem: str) -> list:
    """The tag detections of a calibration's photo, from the analysis store (images.py), the
    same as a validation capture's (`_capture_tags`). A run stores the tags it fitted its scale
    to; an older calibration's are worked out once from its photo."""
    try:
        return _capture_tags(_calibration_ref(frame_stem))
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(409, "the saved frame for this calibration is missing on disk") from exc
        raise


def _plot_samples(inputs: dict) -> list[ScaleResidualSample]:
    """The scale residual of every calibration tag in the photo `inputs` names, against the
    scale field and tag size in `inputs`, never the artifact on disk: a plot is drawn only from
    what its cache key holds."""
    detections = [d for d in _calibration_tags(inputs["frame_stem"]) if d.tag_id in CALIBRATION_ID_RANGE]
    tag_sizes_mm = {d.tag_id: inputs["calibration_tag_size_mm"] for d in detections}
    samples = scale_residual_samples(scale_field_from_dict(inputs["scale_field"]), detections, tag_sizes_mm)
    if len(samples) < 2:
        raise HTTPException(409, "not enough calibration tags detected in the saved frame to plot")
    return samples


def _render_radial_plot(inputs: dict) -> bytes:
    """The evidence gate for lens distortion modelling (CLAUDE.md, see
    `calibration_viz.render_radial_residual_plot`): each tag's signed scale residual against its
    distance from the image centre."""
    points = _radial_points(inputs, _plot_samples(inputs))
    return array_to_jpeg(render_radial_residual_plot(points, label="scale residual"))


def _radial_points(inputs: dict, samples: list[ScaleResidualSample]) -> list[tuple[float, float, int]]:
    """Each sample as `(distance from the image centre in px, residual %, tag id)`."""
    width, height = inputs["photo_size"]
    cx, cy = width / 2, height / 2
    return [(float(np.hypot(s.x - cx, s.y - cy)), s.residual_pct, s.tag_id) for s in samples]


def _render_tag_map(inputs: dict) -> bytes:
    """Where calibration tags read far from the run's median, on the table straightened by its
    corner tags, with a histogram (`calibration_viz.render_tag_map`). A setup aid for finding a
    badly printed sheet, not a claim about accuracy."""
    if inputs["corner_baseline"] is None:
        raise HTTPException(409, "this calibration has no corner tags to straighten the table on")
    baseline = CornerBaseline(
        corners_by_id={
            int(tag_id): tuple(tuple(pt) for pt in corners)
            for tag_id, corners in inputs["corner_baseline"].items()
        }
    )
    try:
        table_frame = build_table_frame(baseline)
    except ValueError as exc:
        raise HTTPException(409, f"cannot straighten the table: {exc}") from exc
    samples = _plot_samples(inputs)
    median = float(np.median([s.residual_pct for s in samples]))
    tags = [(np.asarray(s.corners, dtype=float), s.residual_pct - median) for s in samples]
    path = calibration_frame_path(inputs["frame_stem"])
    frame, scale = images.reduced_frame(path, HEATMAP_MAX_WIDTH)
    return array_to_jpeg(render_tag_map(frame, scale, table_frame, tags))


def _calibration_plot(artifact: CalibrationArtifact, source_stem: str, recipe: str) -> Response:
    """`artifact`'s `recipe` plot, from the images.py store once drawn. The inputs are everything
    the plot is drawn from, so a rewritten artifact or a new tag detector draws it anew. The
    photo is the artifact's own (`frame_stem`), whatever file name the artifact is saved under."""
    return _derived_response(recipe, _calibration_source(source_stem), _calibration_inputs(artifact))


def _calibration_inputs(artifact: CalibrationArtifact) -> dict:
    """Everything `artifact`'s plots and their readout are worked out from, and nothing else."""
    if artifact.frame_stem is None:
        raise HTTPException(409, "this calibration has no saved photo to plot")
    path = calibration_frame_path(artifact.frame_stem)
    if path is None or not path.exists():
        raise HTTPException(409, "the saved frame for this calibration is missing on disk")
    with Image.open(path) as photo:  # the header only, no decode
        photo_size = list(photo.size)
    inputs: dict = {
        "frame_stem": artifact.frame_stem,
        "photo_size": photo_size,
        "scale_field": scale_field_to_dict(artifact.scale_field),
        "calibration_tag_size_mm": artifact.calibration_tag_size_mm,
        "tag_detector_version": images.TAG_DETECTOR_VERSION,
        "corner_baseline": (
            {str(k): [list(pt) for pt in v] for k, v in artifact.corner_baseline.corners_by_id.items()}
            if artifact.corner_baseline is not None
            else None
        ),
    }
    return inputs


def _calibration_diagnostics(artifact: CalibrationArtifact) -> dict:
    """The numbers beside the diagnostics page's plots, from the same tags and fit the plots are
    drawn from. Tag map: how far each tag reads from the run's median, and how many are past the
    outline line (`TAG_MAP_FAR_PCT`). Lens check: the radial plot's fit, its slope in % per
    1000 px. `tag_map` is false when the run has no corner tags, so its map cannot be drawn."""
    inputs = _calibration_inputs(artifact)
    samples = _plot_samples(inputs)
    median = float(np.median([s.residual_pct for s in samples]))
    worst = max(samples, key=lambda s: abs(s.residual_pct - median))
    slope, _intercept, r_squared = radial_fit(_radial_points(inputs, samples))
    return {
        "tags": len(samples),
        "median_pct": median,
        "far_pct": TAG_MAP_FAR_PCT,
        "tags_far": sum(abs(s.residual_pct - median) > TAG_MAP_FAR_PCT for s in samples),
        "worst_tag": {"id": worst.tag_id, "from_median_pct": worst.residual_pct - median},
        "slope_pct_per_1000px": slope * 1000,
        "r_squared": r_squared,
        "tag_map": inputs["corner_baseline"] is not None,
    }


def _current_artifact() -> CalibrationArtifact:
    """The live calibration, from current.json itself, not from the history file of the same
    name."""
    artifact = load_current_calibration()
    if artifact is None or artifact.frame_stem is None:
        raise HTTPException(409, "no calibration with a saved frame yet")
    return artifact


def _no_other_metric(metric: str | None) -> None:
    """The plot review (issue #53) kept only the scale residual: say so rather than silently
    drawing it for an old ?metric= link."""
    if metric not in (None, "scale_residual"):
        raise HTTPException(422, f"unknown metric {metric!r}: only scale_residual is plotted")


@router.get("/calibration/current/diagnostics")
def current_diagnostics() -> dict:
    """The diagnostics readout for the live calibration."""
    return _calibration_diagnostics(_current_artifact())


@router.get("/calibration/{stem}/diagnostics")
def stem_diagnostics(stem: str) -> dict:
    """The diagnostics readout for saved calibration `stem`."""
    return _calibration_diagnostics(_load_saved_artifact(stem))


@router.get("/calibration/current/radial-plot")
def current_radial_plot(metric: str | None = None) -> Response:
    """The radial plot for the live calibration."""
    _no_other_metric(metric)
    artifact = _current_artifact()
    return _calibration_plot(artifact, artifact.frame_stem, "calibration_radial_plot")


@router.get("/calibration/{stem}/radial-plot")
def stem_radial_plot(stem: str, metric: str | None = None) -> Response:
    """The radial plot for saved calibration `stem` (the calibration history drill-down)."""
    _no_other_metric(metric)
    return _calibration_plot(_load_saved_artifact(stem), stem, "calibration_radial_plot")


@router.get("/calibration/current/tag-map")
def current_tag_map() -> Response:
    """The tag map for the live calibration."""
    artifact = _current_artifact()
    return _calibration_plot(artifact, artifact.frame_stem, "calibration_tag_map")


@router.get("/calibration/{stem}/tag-map")
def stem_tag_map(stem: str) -> Response:
    """The tag map for saved calibration `stem` (the calibration history drill-down)."""
    return _calibration_plot(_load_saved_artifact(stem), stem, "calibration_tag_map")


# Validation captures for the certainty map. A full 64MP frame is ~180MB, so captures never stay
# in memory at full size: their tags come from the analysis store (images.py) and the copy to
# draw on is decoded straight to _CAPTURE_PREVIEW_WIDTH. At most one full-size frame is live at
# once: the photo being analysed for the first time, under images._full_decode.
_CAPTURE_REF = re.compile(r"^\d{4}-\d{2}-\d{2}/\d{6}_\d{6}$")
_CAPTURE_PREVIEW_WIDTH = 2000
_MAX_CAPTURES_PER_MAP = 12


def _capture_path(ref: str) -> Path:
    if not _CAPTURE_REF.match(ref):
        raise HTTPException(422, f"not a capture reference: {ref!r} (expected YYYY-MM-DD/HHMMSS_ffffff)")
    path = photos_root() / f"{ref}.jpg"
    if not path.exists():
        raise HTTPException(404, f"capture {ref} not found")
    return path


def _capture_tags(ref: str) -> list:
    """Capture `ref`'s tag detections, worked out once per photograph and then read from the
    analysis store (images.py), so even after a restart nothing decodes it at full size again.
    Stored tags are used even if the photograph itself has since been deleted."""
    if not _CAPTURE_REF.match(ref):
        raise HTTPException(422, f"not a capture reference: {ref!r} (expected YYYY-MM-DD/HHMMSS_ffffff)")
    stored = images.stored_tag_detections(ref)
    if stored is not None:
        return stored
    return images.tag_detections(ref, _capture_path(ref), detect=lambda frame: detect_tags(frame))


def _capture_preview(ref: str) -> tuple[np.ndarray, float]:
    """`(preview, preview_scale)`: capture `ref` decoded straight to about _CAPTURE_PREVIEW_WIDTH,
    with its scale relative to full-resolution pixel coordinates."""
    return images.reduced_frame(_capture_path(ref), _CAPTURE_PREVIEW_WIDTH)


def _certainty_map_response(artifact: CalibrationArtifact, captures: list[str]) -> Response:
    """Per-tray-slot area certainty (certainty_map.py) for `artifact`, pooled over validation
    `captures` taken after the sheets and trays were moved. Slots come from the calibration's own
    saved frame; the map is drawn on the last capture."""
    if not captures:
        raise HTTPException(
            422, "pass at least one validation capture: captures=YYYY-MM-DD/HHMMSS_ffffff"
        )
    if len(captures) > _MAX_CAPTURES_PER_MAP:
        raise HTTPException(422, f"at most {_MAX_CAPTURES_PER_MAP} validation captures per map")
    if artifact.frame_stem is None:
        raise HTTPException(409, "this calibration has no saved frame to take tray slots from")
    calibration_detections = _calibration_tags(artifact.frame_stem)
    per_capture = [_capture_tags(ref) for ref in captures]  # only the last is drawn on
    try:
        layout, results = certainty_by_slot(
            calibration_detections,
            per_capture,
            artifact.scale_field,
            artifact.calibration_tag_size_mm,
        )
    except SlotLayoutError as exc:
        raise HTTPException(409, str(exc)) from exc
    preview, scale = _capture_preview(captures[-1])
    caption = (
        f"Calibration {artifact.frame_stem}, {len(captures)} validation capture(s) pooled. "
        "95% of tags within the stated band, at tray-top height."
    )
    image = render_certainty_map(preview, layout, results, caption, frame_scale=scale)
    return Response(content=array_to_jpeg(image), media_type="image/jpeg")


@router.get("/calibration/current/certainty-map")
def current_certainty_map(captures: list[str] = Query(default=[])) -> Response:
    """`_certainty_map_response` for the live calibration."""
    artifact = load_current_calibration()
    if artifact is None:
        raise HTTPException(409, "no calibration with a saved frame yet")
    return _certainty_map_response(artifact, captures)


@router.get("/calibration/{stem}/certainty-map")
def stem_certainty_map(stem: str, captures: list[str] = Query(default=[])) -> Response:
    """`_certainty_map_response` for an arbitrary saved calibration `stem`."""
    return _certainty_map_response(_load_saved_artifact(stem), captures)


@router.get("/calibration/orientation/level.jpg")
def live_level_overlay() -> Response:
    """Live co-planarity check for an installer levelling the rig by hand -- colored markers on
    the real camera image, not a rotation-in-degrees number (TODO.md: `roll_deg` "isn't super
    useful for an installer standing on a ladder"). No zero/baseline step needed:
    `corner_level_readings` (tripwire.py) compares the currently-detected corner tags to each
    other, which is valid regardless of how each one happens to be mounted -- see that function's
    docstring for the physical argument. Polled every 500ms while Step 2 of the wizard is showing.
    """
    manager = CameraManager.instance()
    frame = manager.capture_array()
    readings = corner_level_readings(detect_tags(frame))
    image = render_level_overlay(frame, readings)
    return Response(content=array_to_jpeg(image), media_type="image/jpeg")


@router.post("/calibration/tripwire/check")
def tripwire_check() -> dict:
    """Manual per-capture health check against the saved baseline (PLAN.md M2 section B).

    A "check now" button, not an automatic hook on every capture -- that needs a recurring
    capture loop, which doesn't exist until M3's scheduler. Built now anyway: without it, the M2
    roll/knock acceptance test has no way to trigger a tripwire check at all.
    """
    artifact = load_current_calibration()
    if artifact is None or artifact.corner_baseline is None:
        raise HTTPException(409, "no calibration baseline saved yet -- run a calibration first")

    array, photo = take_photo("tripwire")
    detections = detect_tags(array)
    del array
    result = check_tripwire(artifact.corner_baseline, detections)
    return {
        "photo_url": photo["url"],
        "photo_flags": photo["flags"],
        "verdict": result.verdict,
        "messages": list(result.messages),
        "roll_deg": result.roll_deg,
        "scale_delta_pct": result.scale_delta_pct,
    }


# Bump a recipe's version whenever its renderer would draw the same inputs differently.
# Version 2: the caption gives the slope in % per 1000 px, as the diagnostics readout does.
images.register(images.Recipe("calibration_radial_plot", 2, _render_radial_plot))
images.register(images.Recipe("calibration_tag_map", 1, _render_tag_map))
