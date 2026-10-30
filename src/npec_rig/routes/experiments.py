"""Routes for the Experiments page: set up, start, stop, purge, export and reprocess an experiment."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from npec_rig import captures, database, dwell, exports, scheduler, tray_readings
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
    # Hours a tray may stay in one area of the table before the page warns (#332). The page
    # offers whole days; left out, 4 days.
    dwell_limit_h: float | None = Field(default=None, gt=0)


def _cleaned(fields: ExperimentFields) -> dict:
    """Only the fields sent, with blank text stored as empty (NULL)."""
    sent = fields.model_dump(exclude_unset=True)
    if sent.get("dwell_limit_h", 0) is None:
        del sent["dwell_limit_h"]  # never empty: the column keeps its value
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
        # Trays too long in one area of the table (#332): only a running experiment's trays can
        # still be moved.
        experiment["dwell_warnings"] = (
            dwell.over_limit(experiment["id"], at=_now()) if experiment["state"] == "running" else []
        )
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


# --- Where each tray has been on the table (#332) ---
# Areas, the 1 hour rule and the limit: dwell.py. The diagrams Aaron chose (2026-10-30): a map per
# tray with its hours in each area and where it is now, the path of its moves on that map, and a
# timeline strip split at each move. Every piece carries its area's name, never colour alone.

# A tray's map: a 3 x 2 grid of square cells, north at the top. Each area keeps one tint.
_CELL = 110
_AREA_CELLS = {area: (i % 3, i // 3) for i, area in enumerate(dwell.AREAS)}
_AREA_TINTS = {"NW": "#2f5f91", "NM": "#2e7556", "NE": "#6e5596", "SW": "#8c5f2b", "SM": "#56742f", "SE": "#8a3c5b"}
_STRIP_W = 600  # the timeline strip's drawing width; it is scaled to the space on the page
_LABEL_MIN_W = 26  # a piece narrower than this has its name written under the strip


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _when(moment: datetime) -> str:
    return f"{moment:%d %b %H:%M}"


def _days(hours: float) -> str:
    return f"{hours / 24:.1f} days"


def _cell_point(area: str, down: float) -> tuple[float, float]:
    col, row = _AREA_CELLS[area]
    return (col + 0.5) * _CELL, (row + down) * _CELL


def _map_arrows(moves: list[tuple[str, str]]) -> list[dict]:
    """A numbered arrow for each move, from one area to the other through the lower half of the
    cells, clear of the hours. Moves between the same two areas lie side by side."""
    out, pairs = [], {}
    for n, (a, b) in enumerate(moves, start=1):
        (ax, ay), (bx, by) = _cell_point(a, 0.7), _cell_point(b, 0.7)
        length = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
        ux, uy = (bx - ax) / length, (by - ay) / length
        k = pairs.setdefault(frozenset((a, b)), 0)
        pairs[frozenset((a, b))] += 1
        side = (k + 1) // 2 * (1 if k % 2 else -1) * 12  # 0, +12, -12, +24, ...
        ox, oy = -uy * side, ux * side
        start = (ax + ux * 22 + ox, ay + uy * 22 + oy)
        end = (bx - ux * 22 + ox, by - uy * 22 + oy)
        out.append({
            "n": n, "x1": round(start[0], 1), "y1": round(start[1], 1), "x2": round(end[0], 1), "y2": round(end[1], 1),
            "nx": round((start[0] + end[0]) / 2, 1), "ny": round((start[1] + end[1]) / 2, 1),
        })
    return out


def _strip(stays: list[dwell.Stay], begin: datetime, end: datetime) -> dict:
    """The timeline strip: one piece per stay, placed across the experiment from `begin` to `end`,
    and a tick at each UTC midnight, labelled on every day or every few when they are many."""
    span = max((end - begin).total_seconds(), 1.0)
    x = lambda moment: round(max(0.0, min(1.0, (moment - begin).total_seconds() / span)) * _STRIP_W, 1)  # noqa: E731
    pieces, under = [], 0
    for stay in stays:
        x1, x2 = x(stay.start), x(stay.end)
        width = max(x2 - x1, 2.0)
        piece = {"area": stay.area, "x": x1, "w": width, "mid": round(x1 + width / 2, 1), "tint": _AREA_TINTS[stay.area],
                 "inside": width >= _LABEL_MIN_W, "row": 0}
        if not piece["inside"]:
            piece["row"] = under % 2  # names under the strip alternate between two rows
            under += 1
        pieces.append(piece)
    days = (end - begin).days + 1
    every = 1 if days <= 9 else 2 if days <= 18 else 7
    ticks, day = [], datetime(begin.year, begin.month, begin.day, tzinfo=UTC) + timedelta(days=1)
    i = 0
    while day < end:
        ticks.append({"x": x(day), "label": f"{day:%d %b}" if i % every == 0 else ""})
        day += timedelta(days=1)
        i += 1
    return {"pieces": pieces, "ticks": ticks, "w": _STRIP_W, "under": bool(under)}


def _tray_areas(experiment: dict) -> dict:
    """What the tray areas panel shows for `experiment`: its limit, the trays too long in one
    area now (a running experiment only) and, per tray, its map and strip."""
    running = experiment["state"] == "running"
    periods = experiment["periods"]
    if not periods:
        return {"limit": _days(experiment["dwell_limit_h"]), "warnings": [], "trays": [], "running": running}
    begin = datetime.fromisoformat(periods[0]["started_at"])
    end = datetime.now(UTC) if running else datetime.fromisoformat(periods[-1]["ended_at"] or _now())
    warned = {w["tray_id"]: w for w in dwell.over_limit(experiment["id"], at=end.isoformat())} if running else {}
    hours = dwell.hours_per_area(experiment["id"])
    trays = []
    for tray_id, stays in dwell.tray_stays(experiment["id"]).items():
        last = stays[-1]
        # Where the tray is now: its last stay, unless it has not been found for over 48 hours,
        # as for trays not found in the Gallery (database.NOT_SEEN_FOR).
        now_area = last.area if end - last.end <= database.NOT_SEEN_FOR else None
        warning = warned.get(tray_id)
        here_h = warning["hours"] if warning else (end - last.start) / timedelta(hours=1)
        moves = [(a.area, b.area) for a, b in zip(stays, stays[1:])]
        trays.append({
            "tray_id": tray_id,
            "warning": None if warning is None else f"Too long in {warning['area']}, {_days(warning['hours'])}",
            "cells": [
                {"area": area, "x": col * _CELL, "y": row * _CELL, "tint": _AREA_TINTS[area],
                 "hours": f"{hours[tray_id][area]:.0f} h", "now": area == now_area}
                for area, (col, row) in _AREA_CELLS.items()
            ],
            "now": None if now_area is None else f"Now in {now_area}, {_days(here_h)}",
            "arrows": _map_arrows(moves),
            "moves": [f"{n}. {a} to {b}, {_when(stay.start)}" for n, ((a, b), stay) in enumerate(zip(moves, stays[1:]), start=1)],
            "strip": _strip(stays, begin, end),
        })
    return {
        "limit": _days(experiment["dwell_limit_h"]),
        "warnings": [f"Tray {t['tray_id']}: {t['warning'][0].lower()}{t['warning'][1:]}." for t in trays if t["warning"]],
        "trays": trays,
        "running": running,
        "begin": _when(begin),
        "end": "now" if running else _when(end),
    }


@router.get("/experiments/{experiment_id}/tray-areas")
def tray_areas_panel(request: Request, experiment_id: int) -> Response:
    """The Experiments page's tray areas panel for one experiment, as HTML: the trays too long in
    one area of the table, and where each tray has been (#332)."""
    experiment = _experiment_action(database.get_experiment, experiment_id)
    return templates.TemplateResponse(request, "_tray_areas.html", {"view": _tray_areas(experiment)})
