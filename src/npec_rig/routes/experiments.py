"""Routes for the Experiments page: set up, start, stop, purge, export and reprocess an experiment."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from npec_rig import captures, database, exports, scheduler, tray_readings
from npec_rig.routes.shared import templates

router = APIRouter()


# --- Experiments ---
# Rules in database.py, folders in captures.py. Every field is optional (Aaron, 2026-10-09): an
# unnamed experiment is shown by the time it started.


@router.get("/experiments")
def experiments_page(request: Request) -> Response:
    return templates.TemplateResponse(
        request, "experiments.html", {"known_trays": captures.KNOWN_TRAY_HEIGHTS_MM}
    )


class ExperimentFields(BaseModel):
    name: str | None = None
    researcher: str | None = None
    tray_height_mm: float | None = Field(default=None, ge=0)
    notes: str | None = None
    # Seconds between scheduled photos; empty for none. The page offers 1 to 6 minutes.
    interval_s: float | None = Field(default=None, gt=0)


def _cleaned(fields: ExperimentFields) -> dict:
    """Only the fields sent, with blank text stored as empty (NULL)."""
    sent = fields.model_dump(exclude_unset=True)
    interval_s = sent.get("interval_s")
    if interval_s is not None and interval_s < scheduler.MIN_INTERVAL_S:
        raise HTTPException(422, f"the interval must be at least {scheduler.MIN_INTERVAL_S:g} s")
    return {k: (v.strip() or None) if isinstance(v, str) else v for k, v in sent.items()}


def _with_schedule(experiment: dict) -> dict:
    experiment["schedule"] = scheduler.schedule(experiment)
    return experiment


def _experiment_action(action, *args, **kwargs) -> dict:
    try:
        return action(*args, **kwargs)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except database.ExperimentError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/api/experiments")
def api_experiments() -> list[dict]:
    """Every experiment, newest first, with its state, periods, newest export and Reprocess progress."""
    experiments = database.list_experiments()
    for experiment in experiments:
        experiment["reprocess"] = tray_readings.reprocess_progress(experiment["id"])
        newest = database.exports_for(experiment["id"])[:1]
        experiment["export"] = newest[0] if newest else None
        experiment["complete_export"] = database.complete_export(experiment["id"])
        experiment["purge_confirmation"] = captures.purge_confirmation(experiment)
        _with_schedule(experiment)
    return experiments


@router.post("/api/experiments")
def api_create_experiment(fields: ExperimentFields) -> dict:
    return _with_schedule(captures.create_experiment(**_cleaned(fields)))


@router.patch("/api/experiments/{experiment_id}")
def api_update_experiment(experiment_id: int, fields: ExperimentFields) -> dict:
    return _with_schedule(
        _experiment_action(captures.update_experiment, experiment_id, **_cleaned(fields))
    )


@router.post("/api/experiments/{experiment_id}/start")
def api_start_experiment(experiment_id: int, stop_running: bool = False) -> dict:
    """Start, or resume a stopped experiment. `stop_running` stops the running one first, in the
    same transaction. Scheduled photos follow the experiment's interval."""
    return _with_schedule(
        _experiment_action(captures.start_experiment, experiment_id, stop_running=stop_running)
    )


@router.post("/api/experiments/{experiment_id}/stop")
def api_stop_experiment(experiment_id: int) -> dict:
    return _with_schedule(_experiment_action(captures.stop_experiment, experiment_id))


@router.delete("/api/experiments/{experiment_id}")
def api_discard_experiment(experiment_id: int) -> dict:
    _experiment_action(database.discard_experiment, experiment_id)
    return {"discarded": experiment_id}


class PurgeRequest(BaseModel):
    confirm: str
    override_no_export: bool = False


@router.post("/api/experiments/{experiment_id}/purge")
def api_purge_experiment(experiment_id: int, request: PurgeRequest) -> dict:
    """Delete a stopped experiment's photos, rows and export zips; its record stays."""
    return _experiment_action(
        captures.purge_experiment,
        experiment_id,
        confirm=request.confirm,
        override_no_export=request.override_no_export,
    )


@router.post("/api/experiments/{experiment_id}/reprocess")
def api_reprocess_experiment(experiment_id: int) -> dict:
    """Read every photo of the experiment again in the background and work out its plant areas
    afresh (#75). 409 while a Reprocess is running."""
    _experiment_action(database.get_experiment, experiment_id)  # 404 for no such experiment
    try:
        return tray_readings.start_reprocess(experiment_id)
    except tray_readings.ReprocessRunning as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/api/experiments/{experiment_id}/reprocess")
def api_reprocess_progress(experiment_id: int) -> dict:
    return tray_readings.reprocess_progress(experiment_id)


@router.post("/api/experiments/{experiment_id}/export")
def api_export_experiment(experiment_id: int) -> dict:
    """Start building an export, of photos up to now if the experiment is running; it is
    prepared in the background."""
    return _experiment_action(exports.start_export, experiment_id)


@router.get("/api/exports/{export_id}/download")
def api_download_export(export_id: int) -> Response:
    try:
        export = database.get_export(export_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    if export["error"] or not export["file"]:
        raise HTTPException(409, "this export did not finish")
    if export["removed_at"]:
        raise HTTPException(410, "this export was deleted when its experiment was purged")
    path = exports.zip_path(export)
    if not path.exists():
        raise HTTPException(404, "the export file is no longer on the rig")
    return FileResponse(path, media_type="application/zip", filename=path.name)
