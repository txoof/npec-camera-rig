"""The JPEG setting full-size photos are saved at, read and changed through the API (#359)."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from npec_rig import database, settings

router = APIRouter()


@router.get("/api/photo-quality")
def get_photo_quality() -> dict:
    """The setting photos are saved at now, and every change of it, newest first."""
    return {**settings.photo_quality(), "changes": database.photo_quality_changes()}


class PhotoQuality(BaseModel):
    # Pillow advises against quality above 95: the file grows with almost nothing gained.
    quality: int = Field(ge=1, le=95)
    # Colour resolution: "4:2:0" half both ways (Pillow's default), "4:4:4" full.
    chroma: Literal["4:2:0", "4:4:4"]


@router.post("/api/photo-quality")
def post_photo_quality(body: PhotoQuality) -> dict:
    return settings.set_photo_quality(body.quality, body.chroma)
