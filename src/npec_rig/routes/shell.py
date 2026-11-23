"""Routes for the menu pages that belong to no one feature: the landing redirect, the Setup menu
and the /ui component reference."""

from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response
from PIL import Image

from npec_rig import captures, database, health, photo_size, settings, validation
from npec_rig.calibration_store import load_current_calibration
from npec_rig.camera import CameraManager
from npec_rig.routes.shared import templates

router = APIRouter()

# With no experiment running, the estimate assumes one photo a minute.
DEFAULT_PHOTOS_PER_DAY = 1440


@router.get("/")
def index() -> RedirectResponse:
    """Root redirects to the everyday page -- Setup is occasional, not the default landing spot
    (2026-09-25 Setup-pages redesign)."""
    return RedirectResponse(url="/gallery")


def _steps(focus: dict, local_times: dict) -> list[dict]:
    """The Setup steps tab: one card per setup page, with a status chip where the rig already
    reports one (focus lock, active calibration, validation). A UTC time in a card's details is
    added to `local_times` (text: (words before it, ISO time)), for the page to show locally."""
    lens = focus["lens_position"]
    calibration = load_current_calibration()
    checked = validation.status(focus)
    saved = "No calibration yet"
    if calibration:
        saved = f"Saved {datetime.fromisoformat(calibration.created_at).astimezone(UTC):%d %b %Y %H:%M} UTC"
        local_times[saved] = ("Saved", calibration.created_at)
    return [
        {"title": "Focus & Square", "href": "/setup/focus",
         "status": ("ok", "Locked") if focus["locked"] else ("warn", "Not locked"),
         "meta": [f"Lens {lens:.2f}" if lens is not None else "Lens not set"]},
        {"title": "Calibration", "href": "/setup/calibration",
         "status": ("ok", "Active") if calibration else ("warn", "None"), "meta": [saved]},
        {"title": "Validation", "href": "/setup/validation",
         "status": {"validated": ("ok", "Validated"), "not_consistent": ("fail", "Not consistent")}.get(
             checked["state"], ("warn", "Not validated")),
         "meta": [checked["text"]]},
        {"title": "Calibration history", "href": "/setup/calibration-history", "status": None,
         "meta": ["Every saved calibration"]},
        {"title": "Health check", "href": "/setup/health-check", "status": None,
         "meta": ["Tripwire check, on demand"]},
    ]


def _newest_photo_pixels() -> tuple[int, int] | None:
    """Width and height of the newest photo the rig has saved, from its JPEG header only."""
    for entry in captures.list_recent_captures(limit=1):
        path = captures.photo_file(entry["path"])
        if path is not None:
            with Image.open(path) as image:
                return image.size
    return None


def _photos_per_day(running: dict | None) -> tuple[float, str]:
    """Photos a day at the running experiment's interval, else at one photo a minute, and how
    the page names that rate."""
    interval_s = running and running["interval_s"]
    if not interval_s:
        return DEFAULT_PHOTOS_PER_DAY, "1 photo a minute, no experiment running"
    every = ("a minute" if interval_s == 60 else f"every {interval_s / 60:g} minutes"
             if interval_s % 60 == 0 else f"every {interval_s:g} seconds")
    return 86400 / interval_s, f"1 photo {every}, the experiment interval"


@router.get("/setup")
def setup_page(request: Request) -> Response:
    """The Setup page (#473): the setup pages on one tab, the rig settings (photo quality, white
    balance) on the other, with each photo quality's estimate for the page to look up."""
    focus = CameraManager.instance().focus_status()
    local_times: dict = {}
    steps = _steps(focus, local_times)
    running = database.running_experiment()
    pixels = _newest_photo_pixels()
    per_day, per_day_text = _photos_per_day(running)
    estimates = {
        chroma: [asdict(photo_size.estimate(q, chroma, pixels[0] * pixels[1] if pixels else photo_size.MEASURED_PIXELS,
                                            per_day)) for q in settings.PHOTO_QUALITIES]
        for chroma in settings.PHOTO_CHROMAS
    }
    lens = focus["lens_position"]
    return templates.TemplateResponse(request, "setup_index.html", {
        "steps": steps,
        "local_times": local_times,
        "saved": settings.photo_quality(),
        "changes": database.photo_quality_changes(),
        "presets": photo_size.PRESETS,
        "preset_names": {f"{p.quality}|{p.chroma}": p.label for p in photo_size.PRESETS},
        "default": photo_size.DEFAULT,
        "pixels": pixels,
        "estimates": estimates,
        "per_day_text": per_day_text,
        "free_bytes": health.disk_status()["free_bytes"],
        "experiment": running["name"] if running else None,
        "lens": (f"{lens:.2f}, {'locked' if focus['locked'] else 'not locked'}" if lens is not None else "Not set"),
    })


@router.get("/ui")
def ui_reference_page(request: Request) -> Response:
    """Every shared interface component with example values, to try in a browser (#128). Not in
    the rail. Later page issues point to it."""
    return templates.TemplateResponse(request, "ui_reference.html")
