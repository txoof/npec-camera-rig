"""Shared text rendering for annotated images: one font (DejaVu Sans Bold, bundled on this OS,
no new dependency -- PIL is already used elsewhere in this codebase for JPEG encoding) and one
drawing path for every module that labels a numpy RGB frame, replacing `cv2.putText`'s Hershey
stroke fonts everywhere in this codebase (Aaron, 2026-09-25: "let's make this the default font
for the project"). Positions use the same `(x, y)` = baseline-left convention `cv2.putText` did,
via PIL's `anchor="ls"`, so existing call sites' layout math (margins, offsets) didn't need
re-deriving.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

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


class TextLayer:
    """One PIL round-trip shared across several `.text()` calls against the same image --
    `draw_text` below does a fresh `Image.fromarray`/`np.array` conversion per call, which is
    fine for a single label but was measured to roughly 4x the unit test suite's runtime once
    plots that draw many labels per image (the rank plot, radial/dome plots, table view) switched
    to it. Use `text_layer()` instead of `draw_text` whenever a render function draws more than
    one label onto the same image.
    """

    def __init__(self, img: np.ndarray) -> None:
        self._img = img
        self._pil = Image.fromarray(img)
        self._draw = ImageDraw.Draw(self._pil)

    def text(
        self,
        text: str,
        org: tuple[int, int],
        scale: float,
        colour: tuple[int, int, int],
        *,
        anchor: str = "ls",
        stroke_width: int = 0,
        stroke_fill: tuple[int, int, int] = (255, 255, 255),
    ) -> None:
        self._draw.text(
            org, text, font=_font(font_size_px(scale)), fill=tuple(int(c) for c in colour),
            anchor=anchor, stroke_width=stroke_width, stroke_fill=stroke_fill,
        )

    def commit(self) -> None:
        self._img[:] = np.array(self._pil)


@contextmanager
def text_layer(img: np.ndarray) -> Iterator[TextLayer]:
    """`with text_layer(img) as t: t.text(...); t.text(...)` -- draws in place on `img` exactly
    once it's converted back, no matter how many `.text()` calls happen inside the block.
    """
    layer = TextLayer(img)
    yield layer
    layer.commit()


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
    """Draws a single `text` onto `img` in place, in DejaVu Sans Bold. `stroke_width > 0` adds an
    outline (for text over a real photo's unpredictable background, e.g. `calibration_viz`'s halo
    text); 0 (the default) matches the plain, unoutlined text most plot labels in this codebase
    use. Prefer `text_layer()` over several `draw_text` calls against the same image -- see
    `TextLayer`'s docstring for why.
    """
    with text_layer(img) as layer:
        layer.text(text, org, scale, colour, anchor=anchor, stroke_width=stroke_width, stroke_fill=stroke_fill)
