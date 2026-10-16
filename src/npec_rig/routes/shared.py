"""What several route files use: the page templates and the derived-image response."""

from pathlib import Path

from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

from npec_rig import images
from npec_rig.camera import AUTOFOCUS_TIMEOUT_S

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
# The focus controls tell the operator how long an autofocus may take (camera.py).
templates.env.globals["AUTOFOCUS_TIMEOUT_S"] = int(AUTOFOCUS_TIMEOUT_S)


def derived_response(recipe: str, source: str, inputs: dict) -> Response:
    """A derived image from the store. `no-cache`: the browser asks again every time (the URL
    stays the same while the session changes), and the store answers from disk."""
    content, media_type = images.get(recipe, source, inputs)
    return Response(content=content, media_type=media_type, headers={"Cache-Control": "no-cache"})
