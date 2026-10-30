"""Where on the chamber table each tray spends its time, and a warning when it stays too long in
one area (#332).

Light, temperature and airflow differ across the table, so a tray that stays in one area for a
long part of an experiment gets different conditions from the others. Researchers move trays to
even this out; this module tells them when a tray has stayed too long.

The table is divided into 6 areas, 3 columns by 2 rows: NW NM NE in the north row, SW SM SE in the
south row (north is up the photo, west is left). A tray's centre decides its area. These are
decisions, not measurements (Aaron, 2026-10-30, issue #332).
"""

from __future__ import annotations

from npec_rig.calibration import TableFrame

AREAS = ("NW", "NM", "NE", "SW", "SM", "SE")


def area_of(centre_px: tuple[float, float], photo_size: tuple[int, int], frame: TableFrame | None) -> str:
    """The area of the table a tray centred at `centre_px` (full-size photo pixels) lies in, in a
    photo of `photo_size` (width, height).

    With the calibration's table frame (the homography of the four corner tags), positions are
    worked out on the table, not in the photo: the rows meet halfway between the northern and the
    southern row of table tags, and the columns are thirds of the photo's width along the tray's
    own row of the table. Without a frame, in the photo: halves of its height, thirds of its width.
    """
    x, y = centre_px
    width, height = photo_size
    if frame is None:
        return ("N" if y < height / 2 else "S") + "WME"[min(max(int(3 * x / width), 0), 2)]
    u, v = frame.to_fraction(x, y)
    west, east = (_edge_u(frame, edge_x, height, v) for edge_x in (0, width))
    column = int(3 * (u - west) / (east - west))
    return ("N" if v < 0.5 else "S") + "WME"[min(max(column, 0), 2)]


def _edge_u(frame: TableFrame, edge_x: float, height: int, v: float) -> float:
    """Where the photo's vertical edge at pixel column `edge_x` meets the table's row `v`, as the
    table's `u`. The edge is a straight line on the table too: a homography keeps lines straight."""
    (u0, v0), (u1, v1) = frame.to_fraction(edge_x, 0), frame.to_fraction(edge_x, height)
    return u0 + (u1 - u0) * (v - v0) / (v1 - v0)
