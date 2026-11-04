"""Restricted randomization of the tray layout (#343).

The rig suggests where each tray goes and which way round it lies, and checks a photo against the
suggestion.

Trays stand wherever the researcher puts them (Aaron, 2026-11-04): there are no fixed slots. The
places are where the trays stand in the latest photo, and a suggestion shuffles the trays over
those places. A side of a place is on the outside edge of the table when no other tray stands
between it and the border (`outer_sides`).

The layout is drawn by restricted randomization: random layouts are drawn and any that breaks
the rule is rejected, so the one kept is drawn at random from those that pass. The rule: no row
or column of plants is on an outside edge of the table two rounds in a row.

Trays lie in portrait (reference/trays.md). The tag ID sets the tray type (PLAN.md, Tag ID
allocation), and the type how its heading is read:

- 4 x 5 (IDs 1 to 75): the tag lies in cell A1, so the heading is A1's corner, "SW" or "NE": SW
  when the tag lies south of the tray's centre (its blue outline, tray_placement.find_outlines).
  Columns A to D across the short side, rows 1 to 5 along the long side; with A1 at SW, row 1 is
  the south end and column A the west side.
- 2 x 2 (IDs 76 to 150): the tag is fixed in the middle of the tray (Aaron, 2026-11-04), so the
  heading is the tag's angle against the tray's first photo: "as first" or "turned" (180
  degrees). Rows 1 and 2, columns A and B: row 1 is the end that faced south in the first photo,
  column A the side that faced west.
- Every other tray (1 x 1, black, other): place only. A 1 x 1 tray has one well, and a black
  tray's disc tag can turn in its pot, so no heading is read and the edge rule is not applied.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from typing import NamedTuple

import numpy as np
from PIL import Image

from npec_rig import database, photo_tags
from npec_rig.calibration_store import (
    CalibrationNotFoundError,
    CalibrationUnreadableError,
    calibration_for_photos,
    load_saved_calibration,
)
from npec_rig.captures import photo_file
from npec_rig.tags import TRAY_ID_RANGE, TagDetection
from npec_rig.tray_placement import TRAY_SIZE_MM, find_outlines, name_trays

# A tray is in its place when its centre is within this of the place's centre: about half a
# tray's short side (305 mm). A decision, not a measurement (2026-11-04).
IN_PLACE_MM = 150.0

# Another tray is between a tray and a border only if it overlaps the tray across by more than this
# share of the tray's width: a tray set off to one side does not shade it. A decision, not a
# measurement (2026-11-04).
SHIELD_OVERLAP = 0.25

SIDES = ("north", "south", "west", "east")

# The photo is searched for trays at this fraction of its size, as tray_readings does: the blue
# finder's parameters were tuned on quarter-size stills (metrology log 20).
FINDER_FACTOR = 4


@dataclass(frozen=True)
class TrayType:
    name: str
    ids: range
    # The two headings, the first the one whose south end is row 1 and west side column A;
    # empty for a tray whose heading is not read.
    headings: tuple[str, ...]
    rows: int
    columns: int


TRAY_TYPES = (
    TrayType("4x5", range(1, 76), ("SW", "NE"), 5, 4),
    TrayType("2x2", range(76, 151), ("as first", "turned"), 2, 2),
    TrayType("1x1", range(151, 226), (), 1, 1),
    TrayType("black", range(226, 251), (), 1, 1),
)
OTHER = TrayType("other", range(0), (), 1, 1)


def tray_type(tray_id: int) -> TrayType:
    """The tray type its tag ID sets (PLAN.md, Tag ID allocation): "other" for 0 and 251 to 299."""
    return next((t for t in TRAY_TYPES if tray_id in t.ids), OTHER)


class Position(NamedTuple):
    """Where a tray goes: the name of a place and its heading: "SW" or "NE" (A1's corner,
    4 x 5), "as first" or "turned" (2 x 2), None when it is not read."""

    place: str
    heading: str | None


class Lying(NamedTuple):
    """How a tray lies: the outer sides where it stands and its heading (None when not read)."""

    sides: frozenset[str]
    heading: str | None


@dataclass(frozen=True)
class Place:
    """Where a tray stood in a photo: its name, its centre (full-size photo pixels), its outer
    sides and the calibration's scale there."""

    name: str
    centre: tuple[float, float]
    sides: frozenset[str]
    px_per_mm: float


@dataclass(frozen=True)
class TraySeen:
    """A tray found in a photo: its centre (full-size photo pixels), its heading (None when not
    read), its outer sides there and its tag's angle in degrees."""

    tray_id: int
    centre: tuple[float, float]
    heading: str | None
    sides: frozenset[str]
    tag_angle: float


def outer_sides(boxes: dict) -> dict:
    """For each tray's box (x0, y0, x1, y1, photo pixels, north at the top), the sides with no
    other tray between it and the border of the table: "north", "south", "west", "east".

    Another tray is beyond a side when its centre lies past that side's edge, and between it and
    the border when it also overlaps the tray across by more than SHIELD_OVERLAP of its width."""

    def overlap(a0: float, a1: float, b0: float, b1: float) -> float:
        return max(0.0, min(a1, b1) - max(a0, b0))

    out = {}
    for key, (x0, y0, x1, y1) in boxes.items():
        shut = set()
        for other, (u0, v0, u1, v1) in boxes.items():
            if other == key:
                continue
            cx, cy = (u0 + u1) / 2, (v0 + v1) / 2
            across_ns = overlap(x0, x1, u0, u1) > SHIELD_OVERLAP * (x1 - x0)
            across_we = overlap(y0, y1, v0, v1) > SHIELD_OVERLAP * (y1 - y0)
            if across_ns and cy < y0:
                shut.add("north")
            if across_ns and cy > y1:
                shut.add("south")
            if across_we and cx < x0:
                shut.add("west")
            if across_we and cx > x1:
                shut.add("east")
        out[key] = frozenset(s for s in SIDES if s not in shut)
    return out


def edge_exposure(sides, heading: str, tray_type: str = "4x5") -> frozenset[str]:
    """The rows and columns of plants on an outside edge of the table for a tray of `tray_type`
    whose outer sides are `sides`, lying at `heading`."""
    kind = next(t for t in (*TRAY_TYPES, OTHER) if t.name == tray_type)
    first_row, last_row = "row 1", f"row {kind.rows}"
    first_column, last_column = "column A", f"column {chr(ord('A') + kind.columns - 1)}"
    turned = heading == kind.headings[1]
    on_side = {
        "south": last_row if turned else first_row,
        "north": first_row if turned else last_row,
        "west": last_column if turned else first_column,
        "east": first_column if turned else last_column,
    }
    return frozenset(on_side[side] for side in sides)


def exposure(tray_id: int, lying: Lying | None) -> frozenset[str] | None:
    """`edge_exposure` for tray `tray_id` lying so; None when its heading is not known."""
    if lying is None or lying.heading is None:
        return None
    return edge_exposure(lying.sides, lying.heading, tray_type(tray_id).name)


def breaks_rule(last: Lying | None, new: Lying, tray_id: int = 1) -> bool:
    """Whether `new` puts a row or column of plants on an outside edge that was on one at `last`.
    A tray with no last position, or whose heading is not known, breaks nothing."""
    before, now = exposure(tray_id, last), exposure(tray_id, new)
    return before is not None and now is not None and bool(before & now)


# Place draws before giving up. A draw of 12 trays over two rows of six passes about once in 10, so
# this is far more than any solvable case needs.
MAX_DRAWS = 10_000


class NoLayoutError(RuntimeError):
    """No layout passing the rule was found in MAX_DRAWS draws."""


def suggest_layout(
    trays: list[int], last: dict[int, Lying], places: dict[str, frozenset[str]], rng
) -> dict[int, Position]:
    """A random layout of `trays` over `places` (name: outer sides), every layout that passes the
    rule against each tray's `last` lie equally likely.

    The same result as drawing place and heading at random and rejecting any layout that breaks
    the rule, in fewer draws: places are drawn, and the draw is kept with a chance in proportion
    to how many headings pass for its trays, then each heading is drawn from those that pass. A
    tray whose heading is not read (tray_type) gets a place only, heading None.
    """
    if len(trays) > len(places):
        raise ValueError(f"{len(trays)} trays do not fit in {len(places)} places")
    names = sorted(places)

    def allowed(tray: int, name: str) -> list[str | None]:
        headings = tray_type(tray).headings or (None,)
        return [h for h in headings if not breaks_rule(last.get(tray), Lying(places[name], h), tray)]

    # The most headings that can pass for each tray in any place: keeping a draw with chance
    # (product of its counts) / (product of these) keeps the result exact and the chance high.
    most = {tray: max(len(allowed(tray, name)) for name in names) or 1 for tray in trays}
    for _ in range(MAX_DRAWS):
        drawn = rng.sample(names, len(trays))
        choices = {tray: allowed(tray, name) for tray, name in zip(trays, drawn)}
        if any(not c for c in choices.values()):
            continue
        keep = math.prod(len(c) / most[tray] for tray, c in choices.items())
        if keep < 1.0 and rng.random() >= keep:
            continue
        return {tray: Position(name, rng.choice(choices[tray])) for tray, name in zip(trays, drawn)}
    raise NoLayoutError(f"no layout of {len(trays)} trays passes the rule in {MAX_DRAWS} draws")


def least_breaking_layout(
    trays: list[int], last: dict[int, Lying], places: dict[str, frozenset[str]], rng, draws: int = 2000
) -> dict[int, Position]:
    """When no layout keeps the rule (`suggest_layout` raises NoLayoutError: a tray with both the
    north and south borders, say), the layout in `draws` random ones with the fewest trays putting
    an edge row or column on the edge again. A gate needs a way past (Aaron): the page marks those
    trays instead of giving no layout."""
    names = sorted(places)
    best, fewest = None, None
    for _ in range(draws):
        layout = {
            tray: Position(name, rng.choice(tray_type(tray).headings or (None,)))
            for tray, name in zip(trays, rng.sample(names, len(trays)))
        }
        breaks = sum(breaks_rule(last.get(t), Lying(places[p.place], p.heading), t) for t, p in layout.items())
        if fewest is None or breaks < fewest:
            best, fewest = layout, breaks
    return best


@dataclass(frozen=True)
class TrayCheck:
    """One tray compared with the suggested layout.

    `status` is one of: "in place"; "wrong place"; "turned" (right place, other way round);
    "wrong place, turned"; "heading not read" (right place, the photo does not show which way
    round); "missing" (in the layout, not found in the photo); "not in layout" (found, not in the
    suggestion). A tray suggested with no heading (tray_type) is judged by its place only.
    `found_at` is the place it stands in (None when it stands in none), `breaks_rule` whether
    where it stands puts a row or column on an outside edge that was on one at its `last` lie.
    """

    tray_id: int
    status: str
    wanted: Position | None
    found_at: str | None
    heading: str | None
    centre: tuple[float, float] | None
    sides: frozenset[str] | None
    breaks_rule: bool


def place_at(point: tuple[float, float], places: dict[str, Place]) -> str | None:
    """The place whose centre is within IN_PLACE_MM of `point`, the nearest if more than one."""
    near = [p for p in places.values() if math.dist(point, p.centre) <= IN_PLACE_MM * p.px_per_mm]
    return min(near, key=lambda p: math.dist(point, p.centre)).name if near else None


def _status(wanted: Position | None, seen: TraySeen | None, places: dict[str, Place]) -> str:
    if seen is None:
        return "missing"
    if wanted is None:
        return "not in layout"
    target = places[wanted.place]
    place_ok = math.dist(seen.centre, target.centre) <= IN_PLACE_MM * target.px_per_mm
    if wanted.heading is None:
        return "in place" if place_ok else "wrong place"
    if seen.heading is None:
        return "heading not read" if place_ok else "wrong place"
    turned = seen.heading != wanted.heading
    if place_ok:
        return "turned" if turned else "in place"
    return "wrong place, turned" if turned else "wrong place"


def check_layout(
    suggested: dict[int, Position],
    seen: list[TraySeen],
    last: dict[int, Lying],
    places: dict[str, Place],
) -> list[TrayCheck]:
    """Each tray in the suggestion or `seen` in the photo, compared with where the suggestion put
    it among `places`, ordered by tray ID."""
    found = {t.tray_id: t for t in seen}
    checks = []
    for tray in sorted(set(suggested) | set(found)):
        tray_seen = found.get(tray)
        broken = tray_seen is not None and breaks_rule(last.get(tray), Lying(tray_seen.sides, tray_seen.heading), tray)
        checks.append(
            TrayCheck(
                tray_id=tray,
                status=_status(suggested.get(tray), tray_seen, places),
                wanted=suggested.get(tray),
                found_at=None if tray_seen is None else place_at(tray_seen.centre, places),
                heading=None if tray_seen is None else tray_seen.heading,
                centre=None if tray_seen is None else tuple(tray_seen.centre),
                sides=None if tray_seen is None else tray_seen.sides,
                breaks_rule=broken,
            )
        )
    return checks


def tag_angle(tag: TagDetection) -> float:
    """The tag's angle in the photo, degrees: the direction from its first corner to its second.
    Any fixed edge would do: only the change between photos is used."""
    (x0, y0), (x1, y1) = tag.corners[0], tag.corners[1]
    return math.degrees(math.atan2(y1 - y0, x1 - x0))


def turned_from(angle: float, reference: float) -> bool:
    """Whether a tag at `angle` is turned round (more than 90 degrees) from `reference`."""
    return abs((angle - reference + 180.0) % 360.0 - 180.0) > 90.0


class LayoutUnreadableError(RuntimeError):
    """A photo whose trays cannot be read: no calibration, or the photo is gone."""


def _box(centre: tuple[float, float], outline, px_per_mm: float) -> tuple[float, float, float, float]:
    """The tray's box: around its outline, or a portrait tray of TRAY_SIZE_MM around its centre."""
    if outline is not None:
        xs, ys = [c[0] for c in outline], [c[1] for c in outline]
        return min(xs), min(ys), max(xs), max(ys)
    half_w, half_h = TRAY_SIZE_MM[0] * px_per_mm / 2, TRAY_SIZE_MM[1] * px_per_mm / 2
    return centre[0] - half_w, centre[1] - half_h, centre[0] + half_w, centre[1] + half_h


def photo_layout(path: str, references: dict[int, float] | None = None) -> tuple[list[TraySeen], object]:
    """The trays of photo `path` (a gallery path) and its calibration's scale field.

    Each tray tag's tray is found from its blue outline (tray_placement.find_outlines and
    name_trays, as the tray readings do), wherever it stands. A 4 x 5 tray's A1 corner is SW when
    its tag lies south of the outline's centre, NE when north; not read when no outline was found.
    A 2 x 2 tray's heading is its tag's angle against `references`, its tag's angle in its first
    photo (its own angle when it has none yet)."""
    try:
        record = database.captures_by_path([path]).get(path)
    except (sqlite3.Error, RuntimeError) as exc:
        raise LayoutUnreadableError(f"could not read the record of photo {path}") from exc
    if record is None or not record.get("calibration"):
        raise LayoutUnreadableError("the photo has no calibration: calibrate the rig first")
    try:
        artifact = load_saved_calibration(calibration_for_photos(record["calibration"]))
    except (CalibrationNotFoundError, CalibrationUnreadableError) as exc:
        raise LayoutUnreadableError("the photo's calibration cannot be read") from exc
    file = photo_file(path)
    if file is None:
        raise LayoutUnreadableError(f"photo {path} is gone")
    with Image.open(file) as image:
        width = image.size[0]
        image.draft("RGB", (image.size[0] // FINDER_FACTOR, image.size[1] // FINDER_FACTOR))
        small = np.asarray(image.convert("RGB"))
    scale = artifact.scale_field
    tags = {d.tag_id: d for d in photo_tags.photo_tags_for(path) if d.tag_id in TRAY_ID_RANGE}
    trays = [t for t in name_trays(find_outlines(small, scale, width / small.shape[1]), list(tags.values()))
             if t.tray_id is not None]
    boxes = {t.tray_id: _box(t.centre, t.outline, scale.px_per_mm(*t.centre)) for t in trays}
    sides = outer_sides(boxes)
    references = references or {}
    seen = []
    for t in trays:
        tag = tags[t.tray_id]
        kind = tray_type(t.tray_id).name
        heading = None
        if kind == "4x5" and t.outline is not None:
            heading = "SW" if tag.centre[1] > t.centre[1] else "NE"
        elif kind == "2x2":
            # The tag is fixed in the middle of the tray (Aaron, 2026-11-04).
            angle = tag_angle(tag)
            heading = "turned" if turned_from(angle, references.get(t.tray_id, angle)) else "as first"
        seen.append(TraySeen(t.tray_id, tuple(t.centre), heading, sides[t.tray_id], tag_angle(tag)))
    return sorted(seen, key=lambda s: s.tray_id), scale
