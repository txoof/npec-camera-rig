"""The About page (#390), reached from the (i) button at the foot of the rail."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from npec_rig import about
from npec_rig.routes.shared import templates

router = APIRouter()


@router.get("/about", response_class=HTMLResponse)
def about_page(request: Request) -> HTMLResponse:
    """What the rig runs and the state it is in, read when the page is opened."""
    return templates.TemplateResponse(
        request, "about.html", {"about_sections": about.sections(about.facts())}
    )


@router.get("/api/about")
def about_facts() -> dict:
    """The same facts as the page, for scripts and the health check."""
    return about.facts()
