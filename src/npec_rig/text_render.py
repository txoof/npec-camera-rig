"""Shared text rendering for annotated images: one font (DejaVu Sans Bold, bundled on this OS,
no new dependency -- PIL is already used elsewhere in this codebase for JPEG encoding) and one
drawing path for every module that labels a numpy RGB frame, replacing `cv2.putText`'s Hershey
stroke fonts everywhere in this codebase (Aaron, 2026-09-25: "let's make this the default font
for the project"). Positions use the same `(x, y)` = baseline-left convention `cv2.putText` did,
via PIL's `anchor="ls"`, so existing call sites' layout math (margins, offsets) didn't need
re-deriving.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_FONT_CACHE: dict[int, ImageFont.FreeTypeFont] = {}


def _font(size: int) -> ImageFont.FreeTypeFont:
    font = _FONT_CACHE.get(size)
    if font is None:
        font = ImageFont.truetype(_FONT_PATH, size)
        _FONT_CACHE[size] = font
    return font


def font_size_px(scale: float) -> int:
    """Maps the old `cv2` `font_scale` convention (kept at every call site, so existing layout
    math didn't need re-deriving) to a DejaVu Sans Bold pixel size."""
    return max(11, int(round(scale * 34)))


def text_width(text: str, scale: float) -> int:
    """Advance width in px, for right-aligning or centring text -- replaces `cv2.getTextSize`."""
    return int(round(_font(font_size_px(scale)).getlength(text)))


def draw_text(
    img: np.ndarray,
    text: str,
    org: tuple[int, int],
    scale: float,
    colour: tuple[int, int, int],
    *,
    anchor: str = "ls",
    stroke_width: int = 0,
    stroke_fill: tuple[int, int, int] = (255, 255, 255),
) -> None:
    """Draws `text` onto `img` in place, in DejaVu Sans Bold. `stroke_width > 0` adds an outline
    (for text over a real photo's unpredictable background, e.g. `calibration_viz`'s halo text);
    0 (the default) matches the plain, unoutlined text most plot labels in this codebase use.
    """
    pil_img = Image.fromarray(img)
    draw = ImageDraw.Draw(pil_img)
    draw.text(
        org, text, font=_font(font_size_px(scale)), fill=tuple(int(c) for c in colour),
        anchor=anchor, stroke_width=stroke_width, stroke_fill=stroke_fill,
    )
    img[:] = np.array(pil_img)
