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
    # Hours a tray may stay in one table location before the page warns (#332). The page
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
        # Trays too long in one table location (#332): only a running experiment's trays can
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


class ExportChoice(BaseModel):
    """What goes in an export, ticked in the page's dialog (#65, #368)."""

    data: bool = True
    photos: bool = True


@router.post("/api/experiments/{experiment_id}/export")
def api_export_experiment(experiment_id: int, choice: ExportChoice | None = None) -> dict:
    """Start building an export, of photos up to now if the experiment is running; it is
    prepared in the background. With no choice sent, it holds everything."""
    choice = choice or ExportChoice()
    if not (choice.data or choice.photos):
        raise HTTPException(422, "tick the data, the photos or both")
    return _experiment_action(exports.start_export, experiment_id, data=choice.data, photos=choice.photos)


@router.get("/api/experiments/{experiment_id}/export-size")
def api_export_size(experiment_id: int) -> dict:
    """The expected size of an export of the data and of the photos, for the Export dialog."""
    return _experiment_action(exports.export_sizes, experiment_id)


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
# Table locations, the 1 hour rule and the limit: dwell.py. The diagrams Aaron chose: a map per tray
# with its hours in each location, where it is now and the path of its moves (2026-10-30), and one
# timeline of all trays (2026-11-02). Every piece carries its location's name, never colour alone.

# A tray's map: a 3 x 2 grid of square cells, north at the top. Each location keeps one tint.
_CELL = 110
_LOCATION_CELLS = {location: (i % 3, i // 3) for i, location in enumerate(dwell.LOCATIONS)}
_LOCATION_TINTS = {"NW": "#2f5f91", "NM": "#2e7556", "NE": "#6e5596", "SW": "#8c5f2b", "SM": "#56742f", "SE": "#8a3c5b"}
# The all trays timeline (Aaron, 2026-11-02): a row per tray on one time axis, in drawing units,
# scaled to the space on the page: about 1 px per unit at 1024 px wide (the page less the rail
# and the scroll lane), so no text is under 13 units, at least 12 px there. Names fit inside
# pieces this wide; a narrower piece is named right of the strips (the last stay) or in the list
# of short stays.
_TIMELINE_LABEL_W = 80
_TIMELINE_W = 680
_TIMELINE_MARGIN = 40  # right of the strips: the name of a short last stay
_ROW_H, _ROW_GAP = 28, 8
_NAME_W = 30


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _when(moment: datetime) -> str:
    return f"{moment:%d %b %H:%M}"


def _days(hours: float) -> str:
    return f"{hours / 24:.1f} days"


def _limit(hours: float) -> str:
    """The limit as the page sets it, in whole days: "4 days"."""
    days = hours / 24
    return f"{days:g} day" if days == 1 else f"{days:g} days"


def _cell_point(location: str, down: float) -> tuple[float, float]:
    col, row = _LOCATION_CELLS[location]
    return (col + 0.5) * _CELL, (row + down) * _CELL


def _map_arrows(moves: list[tuple[str, str]]) -> list[dict]:
    """A numbered arrow for each move, from one location to the other through the lower half of the
    cells, clear of the hours. Each arrow lies on one of 4 lanes beside the line between the two
    locations' centres, in turn, so moves along one line (there and back, or through a middle location)
    lie side by side."""
    out = []
    for n, (a, b) in enumerate(moves, start=1):
        (ax, ay), (bx, by) = _cell_point(a, 0.7), _cell_point(b, 0.7)
        length = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
        ux, uy = (bx - ax) / length, (by - ay) / length
        # The lane is measured from the pair in one order, so a move back lies beside, not on,
        # the move there.
        side = ((n - 1) % 4 - 1.5) * 12 * (1 if a < b else -1)  # -18, -6, 6, 18
        ox, oy = -uy * side, ux * side
        start = (ax + ux * 22 + ox, ay + uy * 22 + oy)
        end = (bx - ux * 22 + ox, by - uy * 22 + oy)
        along = (0.5, 0.3, 0.7)[(n - 1) % 3]  # numbers on near lanes apart along them too
        out.append({
            "n": n, "x1": round(start[0], 1), "y1": round(start[1], 1), "x2": round(end[0], 1), "y2": round(end[1], 1),
            "nx": round(start[0] + (end[0] - start[0]) * along, 1), "ny": round(start[1] + (end[1] - start[1]) * along, 1),
        })
    return out


def _timeline(rows: list[tuple[int, list[dwell.Stay]]], begin: datetime, end: datetime) -> dict:
    """The all trays timeline: for each tray, one piece per stay across the experiment from `begin`
    to `end`, and a tick at each UTC midnight. Every piece is named: inside it when it is wide
    enough, right of the strips when it is the last stay, else in the list of short stays."""
    span = max((end - begin).total_seconds(), 1.0)
    x = lambda moment: round(_TIMELINE_LABEL_W + 4 + max(0.0, min(1.0, (moment - begin).total_seconds() / span)) * _TIMELINE_W, 1)  # noqa: E731
    out, short = [], []
    for i, (tray_id, stays) in enumerate(rows):
        y = i * (_ROW_H + _ROW_GAP)
        pieces = []
        for n, stay in enumerate(stays):
            x1 = x(stay.start)
            width = max(x(stay.end) - x1, 2.0)
            name = "inside" if width >= _NAME_W else "after" if n == len(stays) - 1 else "listed"
            if name == "listed":
                short.append(f"tray {tray_id} {stay.location} {_when(stay.start)}")
            pieces.append({"location": stay.location, "x": x1, "w": width, "mid": round(x1 + width / 2, 1),
                           "end": round(x1 + width + 4, 1), "tint": _LOCATION_TINTS[stay.location], "name": name})
        out.append({"tray_id": tray_id, "y": y, "pieces": pieces,
                    "label": f"Tray {tray_id} over time: " + ", ".join(stay.location for stay in stays)})
    height = len(rows) * (_ROW_H + _ROW_GAP)
    days = (end - begin).days + 1
    every = 1 if days <= 9 else 2 if days <= 18 else 7
    ticks, day, i = [], datetime(begin.year, begin.month, begin.day, tzinfo=UTC) + timedelta(days=1), 0
    while day < end:
        # The label sits at the middle of its day, as far as the experiment covers it.
        middle = x(min(day + timedelta(hours=12), end))
        ticks.append({"x": x(day), "label": f"{day:%a %d %b}" if i % every == 0 else "", "mid": middle})
        day += timedelta(days=1)
        i += 1
    return {"rows": out, "ticks": ticks, "height": height, "w": _TIMELINE_LABEL_W + 4 + _TIMELINE_W + _TIMELINE_MARGIN,
            "x0": _TIMELINE_LABEL_W + 4, "x1": _TIMELINE_LABEL_W + 4 + _TIMELINE_W, "short": short}


def _table_locations(experiment: dict) -> dict:
    """What the table locations panel shows for `experiment`: its limit, the trays too long in one
    location now (a running experiment only), the all trays timeline, and per tray its map."""
    running = experiment["state"] == "running"
    periods = experiment["periods"]
    setting = {"limit": _limit(experiment["dwell_limit_h"])}
    if not periods:
        return {**setting, "warnings": [], "trays": [], "running": running}
    begin = datetime.fromisoformat(periods[0]["started_at"])
    end = datetime.now(UTC) if running else datetime.fromisoformat(periods[-1]["ended_at"] or _now())
    hidden = database.hidden_trays(experiment["id"])
    # One snapshot of the stays for the whole panel: the warnings, the hours and the diagrams all
    # come from it, so a photo read in the meantime cannot give a tray in one and not another.
    snapshot = dwell.tray_stays(experiment["id"], until=end.isoformat() if running else None)
    warned = ({w["tray_id"]: w for w in dwell.over_limit_in(snapshot, end, experiment["dwell_limit_h"], hidden)}
              if running else {})
    hours = dwell.hours_in(snapshot)
    trays, shown = [], []
    for tray_id, stays in snapshot.items():
        if tray_id in hidden:
            # One line until Show is tapped, such as a misread tag (Aaron, 2026-11-02).
            trays.append({"tray_id": tray_id, "hidden": True, "warning": None})
            continue
        shown.append((tray_id, stays))
        last = stays[-1]
        # Where the tray is now: its last stay, unless it has not been found for over 48 hours,
        # as for trays not found in the Gallery (database.NOT_SEEN_FOR).
        now_location = last.location if end - last.end <= database.NOT_SEEN_FOR else None
        warning = warned.get(tray_id)
        here_h = warning["hours"] if warning else (end - last.start) / timedelta(hours=1)
        # A new stay in the same location (the tray taken away over 48 hours and back) is no move.
        pairs = [(a, b) for a, b in zip(stays, stays[1:]) if a.location != b.location]
        moves = [(a.location, b.location) for a, b in pairs]
        trays.append({
            "tray_id": tray_id,
            "hidden": False,
            "warning": None if warning is None else f"Too long in {warning['location']}, {_days(warning['hours'])}",
            "cells": [
                {"location": location, "x": col * _CELL, "y": row * _CELL, "tint": _LOCATION_TINTS[location],
                 "hours": f"{hours[tray_id][location]:.0f} h", "now": location == now_location}
                for location, (col, row) in _LOCATION_CELLS.items()
            ],
            "now": None if now_location is None else f"Now in {now_location}, {_days(here_h)}",
            "arrows": _map_arrows(moves),
            "moves": [f"{n}. {a.location} to {b.location}, {_when(b.start)}" for n, (a, b) in enumerate(pairs, start=1)],
        })
    return {
        **setting,
        "warnings": [f"Tray {t['tray_id']}: {t['warning'][0].lower()}{t['warning'][1:]}." for t in trays if t["warning"]],
        "trays": trays,
        "timeline": _timeline(shown, begin, end),
        # Hidden trays are left out of the timeline, and named once under it.
        "hidden": ", ".join(str(t["tray_id"]) for t in trays if t["hidden"]),
        "running": running,
        "begin": _when(begin),
        "end": "now" if running else _when(end),
    }


@router.get("/experiments/{experiment_id}/table-locations")
def table_locations_panel(request: Request, experiment_id: int) -> Response:
    """The Experiments page's table locations panel for one experiment, as HTML: the trays too long in
    one table location, and where each tray has been (#332)."""
    experiment = _experiment_action(database.get_experiment, experiment_id)
    return templates.TemplateResponse(request, "_table_locations.html", {"view": _table_locations(experiment)})


@router.post("/api/experiments/{experiment_id}/trays/{tray_id}/hide")
def api_hide_tray(experiment_id: int, tray_id: int) -> dict:
    """Hide a tray on the experiment's table locations panel, kept in rig.db: it gives no warning
    until shown again (#332). Its readings and the export are unchanged."""
    _experiment_action(database.hide_tray, experiment_id, tray_id, now=_now())
    return {"hidden": sorted(database.hidden_trays(experiment_id))}


@router.post("/api/experiments/{experiment_id}/trays/{tray_id}/show")
def api_show_tray(experiment_id: int, tray_id: int) -> dict:
    """Show a hidden tray again (#332)."""
    _experiment_action(database.show_tray, experiment_id, tray_id)
    return {"hidden": sorted(database.hidden_trays(experiment_id))}
