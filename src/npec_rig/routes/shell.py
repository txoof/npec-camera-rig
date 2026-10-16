"""Routes for the menu pages that belong to no one feature: the landing redirect, the Setup menu
and the /ui component reference."""

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

from npec_rig.routes.shared import templates

router = APIRouter()


@router.get("/")
def index() -> RedirectResponse:
    """Root redirects to the everyday page -- Setup is occasional, not the default landing spot
    (2026-09-25 Setup-pages redesign)."""
    return RedirectResponse(url="/gallery")


@router.get("/setup")
def setup_page(request: Request) -> Response:
    """Setup menu: links to Focus & Square, Calibration, and Health check. One-and-done (or
    occasional) rig setup, kept separate from everyday capture/browsing."""
    return templates.TemplateResponse(request, "setup_index.html")


@router.get("/ui")
def ui_reference_page(request: Request) -> Response:
    """Every shared interface component with example values, to try in a browser (#128). Not in
    the rail. Later page issues point to it."""
    return templates.TemplateResponse(request, "ui_reference.html")
