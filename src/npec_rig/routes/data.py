"""The Data page (#64): time lapse videos of an experiment's trays. Exports move here later."""

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from npec_rig import database, timelapse, tray_readings
from npec_rig.routes.shared import templates

router = APIRouter()


class VideoRequest(BaseModel):
    experiment_id: int
    # A tray ID, or "all": one video per tray in one zip (#64).
    tray_id: int | Literal["all"]
    start: str
    end: str
    per_hour: int
    method: str
    cell: str | None = None
    # True: show the leaf area method's own mask over each frame.
    mask: bool = False


@router.get("/data", response_class=HTMLResponse)
def data_page(request: Request, experiment: int | None = None, tab: str = "timelapse") -> HTMLResponse:
    """The Data page: a time lapse video of one of an experiment's trays. The experiment named in
    the address, else the running one, else the latest started (the list is newest first)."""
    started = [e for e in database.list_experiments() if e["periods"] and e["state"] != "purged"]
    chosen = next((e for e in started if e["id"] == experiment), None) or next(
        (e for e in started if e["state"] == "running"), None) or (started[0] if started else None)
    # The tab to open, from the address, so a link can land on Export (#454).
    tab = tab if tab in ("timelapse", "export") else "timelapse"
    context = {"nav_active": "data", "tab": tab, "experiments": started, "experiment": chosen, "trays": [],
               # As ui.choices options: value, text, detail.
               "methods": [(m["key"], m["name"], "") for m in tray_readings.AREA_METHODS],
               "per_hour": [(str(n), f"{n} per hour", "") for n in timelapse.PER_HOUR],
               "unavailable": timelapse.unavailable(), "latest": timelapse.latest()}
    # As ui.field_button choice options: value, text, detail. Trays are 4 x 5, 2 x 2 or 1 x 1.
    context["cell_options"] = [("tray", "Whole tray", "")] + [
        (f"{col}{row}", f"Cell {col}{row}", "") for col in "ABCD" for row in range(1, 6)]
    if chosen is not None:
        context["trays"] = timelapse.experiment_trays(chosen["id"])
        context["tray_options"] = [(str(t), f"Tray {t}", "") for t in context["trays"]] + (
            [(timelapse.ALL_TRAYS, "All trays", "one video per tray, in one zip")] if len(context["trays"]) > 1 else [])
        context["first"] = chosen["periods"][0]["started_at"]
        context["last"] = chosen["periods"][-1]["ended_at"] or datetime.now(timezone.utc).isoformat()
    return templates.TemplateResponse(request, "data.html", context)


@router.post("/api/data/timelapse")
def start_video(request: VideoRequest) -> dict:
    """Start making a video in the background: its id. 409 with the reason when none can be made
    now (a video is being made, or ffmpeg is missing)."""
    try:
        return timelapse.start(request.model_dump())
    except (timelapse.VideoBusy, timelapse.VideoUnavailable) as exc:
        raise HTTPException(409, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/api/data/timelapse/{video_id}")
def video_progress(video_id: str) -> dict:
    return timelapse.progress(video_id)


@router.get("/api/data/timelapse/{video_id}/download")
def download_video(video_id: str) -> FileResponse:
    """The finished video. It stays on the rig until the next one is started (Aaron, 2026-11-20)."""
    file = timelapse.video_file(video_id)
    if file is None:
        raise HTTPException(404, "This video is gone: a newer one was started. Make it again.")
    if file.suffix == ".zip":
        return FileResponse(file, media_type="application/zip", filename=f"timelapse-all-trays-{video_id}.zip")
    return FileResponse(file, media_type="video/mp4", filename=f"timelapse-{video_id}.mp4")
