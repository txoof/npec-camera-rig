"""Restricted randomization of the tray layout (#343).

The rig suggests where each tray goes (its slot) and which way round it lies, and checks a photo
against the suggestion.

The layout is drawn by restricted randomization: random layouts are drawn and any that breaks
the rule is rejected, so the one kept is drawn at random from those that pass. The rule: no row
or column of plants is on an outside edge of the table two rounds in a row.

Geometry (reference/trays.md): trays in portrait, North 1 to 6 along the north border and South 1
to 6 along the south border, numbered from the west. The tag ID sets the tray type (PLAN.md, Tag
ID allocation), and the type how its heading is read:

- 4 x 5 (IDs 1 to 75): the tag lies in cell A1, so the heading is A1's corner, "SW" or "NE"
  (tray_placement.place_trays). Columns A to D across the short side, rows 1 to 5 along the long
  side; with A1 at SW, row 1 is the south end and column A the west side.
- 2 x 2 (IDs 76 to 150): the tag is fixed in the middle of the tray (Aaron, 2026-11-04), so the
  heading is the tag's angle against the tray's first photo: "as first" or "turned" (180
  degrees). Rows 1 and 2, columns A and B: row 1 is the end that faced south in the first photo,
  column A the side that faced west.
- Every other tray (1 x 1, black, other): slot only. A 1 x 1 tray has one well, and a black
  tray's disc tag can turn in its pot, so no heading is read and the edge rule is not applied.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from typing import NamedTuple

from npec_rig import database, photo_tags, validation_store
from npec_rig.calibration_store import (
    CalibrationNotFoundError,
    CalibrationUnreadableError,
    calibration_for_photos,
    load_saved_calibration,
)
from npec_rig.tags import TRAY_ID_RANGE, TagDetection
from npec_rig.tray_placement import place_trays


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
    """Where a tray lies: its slot ("North 1" to "South 6") and its heading: "SW" or "NE" (A1's
    corner, 4 x 5), "as first" or "turned" (2 x 2), None when it is not read."""

    slot: str
    heading: str | None


def edge_exposure(slot: str, heading: str, columns: int = 6, tray_type: str = "4x5") -> frozenset[str]:
    """The rows and columns of plants on an outside edge of the table for a tray of `tray_type`
    in `slot` lying at `heading`. `columns` is the number of slots per row."""
    kind = next(t for t in (*TRAY_TYPES, OTHER) if t.name == tray_type)
    first_row, last_row = "row 1", f"row {kind.rows}"
    first_column, last_column = "column A", f"column {chr(ord('A') + kind.columns - 1)}"
    side, number = slot.split()
    turned = heading == kind.headings[1]
    south_end, north_end = (last_row, first_row) if turned else (first_row, last_row)
    west_side, east_side = (last_column, first_column) if turned else (first_column, last_column)
    edges = {north_end if side == "North" else south_end}
    if int(number) == 1:
        edges.add(west_side)
    if int(number) == columns:
        edges.add(east_side)
    return frozenset(edges)


def exposure(tray_id: int, position: Position | None, columns: int = 6) -> frozenset[str] | None:
    """`edge_exposure` for tray `tray_id` at `position`; None when its heading is not known."""
    if position is None or position.slot is None or position.heading is None:
        return None
    return edge_exposure(position.slot, position.heading, columns, tray_type(tray_id).name)


def breaks_rule(last: Position | None, new: Position, columns: int = 6, tray_id: int = 1) -> bool:
    """Whether `new` puts a row or column of plants on an outside edge that was on one at `last`.
    A tray with no last position, or whose heading is not known, breaks nothing."""
    before, now = exposure(tray_id, last, columns), exposure(tray_id, new, columns)
    return before is not None and now is not None and bool(before & now)


# Slot draws before giving up. A 12-tray draw passes about once in 10 (only the 4 end slots can
# clash), so this is far more than any solvable case needs.
MAX_DRAWS = 10_000


class NoLayoutError(RuntimeError):
    """No layout passing the rule was found in MAX_DRAWS draws."""


def suggest_layout(
    trays: list[int], last: dict[int, Position], slots: list[str], rng
) -> dict[int, Position]:
    """A random layout for `trays` over `slots`, every layout that passes the rule against each
    tray's `last` position equally likely.

    The same result as drawing slot and heading at random and rejecting any layout that breaks
    the rule, in far fewer draws. Every slot touches the north or south border, so the rule
    leaves a tray whose last heading is known at most one heading, and any other tray both: a
    slot draw in which every tray has a heading would survive the heading draw with the same
    chance as any other such draw. So slots are drawn and rejected only when a tray has no
    heading, then each heading is drawn from those that pass. A tray whose heading is not read
    (tray_type) gets a slot only, heading None.
    """
    if len(trays) > len(slots):
        raise ValueError(f"{len(trays)} trays do not fit in {len(slots)} slots")
    columns = max(int(slot.split()[1]) for slot in slots)
    for _ in range(MAX_DRAWS):
        layout = {}
        for tray, slot in zip(trays, rng.sample(slots, len(trays))):
            headings = tray_type(tray).headings or (None,)
            allowed = [h for h in headings if not breaks_rule(last.get(tray), Position(slot, h), columns, tray)]
            if not allowed:
                break
            layout[tray] = Position(slot, rng.choice(allowed))
        else:
            return layout
    raise NoLayoutError(f"no layout of {len(trays)} trays passes the rule in {MAX_DRAWS} draws")


@dataclass(frozen=True)
class TrayCheck:
    """One tray compared with the suggested layout.

    `status` is one of: "in place"; "wrong slot"; "turned" (right slot, other way round); "wrong
    slot, turned"; "heading not read" (right slot, the photo does not show which way round). A
    tray suggested with no heading (tray_type) is judged by its slot only. Then:
    "missing" (in the layout, not found in the photo); "not placed" (found, no slot for it);
    "not in layout" (found, not in the suggestion). `breaks_rule` is whether where it lies puts a
    row or column on an outside edge that was on one at its `last` position.
    """

    tray_id: int
    status: str
    wanted: Position | None
    found: Position | None
    centre: tuple[float, float] | None
    breaks_rule: bool


def _status(wanted: Position | None, found: Position | None) -> str:
    if found is None:
        return "missing"
    if found.slot is None:
        return "not placed"
    if wanted is None:
        return "not in layout"
    slot_ok = found.slot == wanted.slot
    if wanted.heading is None:
        return "in place" if slot_ok else "wrong slot"
    if found.heading is None:
        return "heading not read" if slot_ok else "wrong slot"
    turned = found.heading != wanted.heading
    if slot_ok:
        return "turned" if turned else "in place"
    return "wrong slot, turned" if turned else "wrong slot"


@dataclass(frozen=True)
class TraySeen:
    """A tray found in a photo: its slot (None when it is in none), its heading (None when not
    read), its centre in full-size photo pixels and its tag's angle in degrees."""

    tray_id: int
    slot: str | None
    heading: str | None
    centre: tuple[float, float]
    tag_angle: float


def check_layout(
    suggested: dict[int, Position],
    seen: list[TraySeen],
    last: dict[int, Position],
    columns: int = 6,
) -> list[TrayCheck]:
    """Each tray in the suggestion or `seen` in the photo, compared with where the suggestion put
    it, ordered by tray ID."""
    found = {t.tray_id: t for t in seen}
    checks = []
    for tray in sorted(set(suggested) | set(found)):
        tray_seen = found.get(tray)
        where = None if tray_seen is None else Position(tray_seen.slot, tray_seen.heading)
        broken = where is not None and where.slot is not None and breaks_rule(last.get(tray), where, columns, tray)
        checks.append(
            TrayCheck(
                tray_id=tray,
                status=_status(suggested.get(tray), where),
                wanted=suggested.get(tray),
                found=where,
                centre=None if tray_seen is None else tuple(tray_seen.centre),
                breaks_rule=broken,
            )
        )
    return checks


class LayoutUnreadableError(RuntimeError):
    """A photo whose trays cannot be placed in slots: no calibration, or no slot layout."""


def tag_angle(tag: TagDetection) -> float:
    """The tag's angle in the photo, degrees: the direction from its first corner to its second.
    Any fixed edge would do: only the change between photos is used."""
    (x0, y0), (x1, y1) = tag.corners[0], tag.corners[1]
    return math.degrees(math.atan2(y1 - y0, x1 - x0))


def turned_from(angle: float, reference: float) -> bool:
    """Whether a tag at `angle` is turned round (more than 90 degrees) from `reference`."""
    return abs((angle - reference + 180.0) % 360.0 - 180.0) > 90.0


def _nearest_slot(point: tuple[float, float], slots: list[dict]) -> str | None:
    if not slots:
        return None
    return min(slots, key=lambda s: math.dist(point, s["centre"]))["name"]


def _trays_seen(detections: list[TagDetection], scale_field, slots: list[dict], references: dict[int, float]) -> list[TraySeen]:
    """Each tray tag of a photo as a tray: a 4 x 5 tray placed from its tag in cell A1, any other
    tray at its tag's slot. A 2 x 2 tray's heading is its tag's angle against `references`, the
    tag's angle in the tray's first photo (its own angle when it has none yet)."""
    tags = [d for d in detections if d.tag_id in TRAY_ID_RANGE]
    angles = {d.tag_id: tag_angle(d) for d in tags}
    four_by_five = [d for d in tags if tray_type(d.tag_id).name == "4x5"]
    seen = [
        TraySeen(p.tray_id, p.slot, p.a1_corner, tuple(p.centre), angles[p.tray_id])
        for p in place_trays(four_by_five, scale_field, slots)
    ]
    for tag in tags:
        kind = tray_type(tag.tag_id)
        if kind.name == "4x5":
            continue
        heading = None
        if kind.name == "2x2":
            # The tag is fixed in the middle of the tray (Aaron, 2026-11-04).
            reference = references.get(tag.tag_id, angles[tag.tag_id])
            heading = kind.headings[1] if turned_from(angles[tag.tag_id], reference) else kind.headings[0]
        seen.append(TraySeen(tag.tag_id, _nearest_slot(tag.centre, slots), heading, tuple(tag.centre), angles[tag.tag_id]))
    return sorted(seen, key=lambda t: t.tray_id)


def photo_layout(path: str, references: dict[int, float] | None = None) -> tuple[list[TraySeen], list[dict]]:
    """The trays of photo `path` (a gallery path), each in a slot with its heading where its type
    has one (_trays_seen), and the slots of the photo's calibration. `references`: each 2 x 2
    tray's tag angle in its first photo.

    Since #331 tray readings name trays without slots, so the photo's tags (searched once,
    photo_tags) are placed here. The calibration lookup is the one tray_readings makes."""
    try:
        record = database.captures_by_path([path]).get(path)
    except (sqlite3.Error, RuntimeError) as exc:
        raise LayoutUnreadableError(f"could not read the record of photo {path}") from exc
    if record is None or not record.get("calibration"):
        raise LayoutUnreadableError("the photo has no calibration: calibrate the rig first")
    try:
        stem = calibration_for_photos(record["calibration"])
        artifact = load_saved_calibration(stem)
    except (CalibrationNotFoundError, CalibrationUnreadableError) as exc:
        raise LayoutUnreadableError("the photo's calibration cannot be read") from exc
    try:
        # A twin has its original's slots, as in tray_readings.
        layout = validation_store.load_slot_layout(stem) or validation_store.load_slot_layout(record["calibration"])
    except validation_store.SessionNotFoundError:
        layout = None
    if layout is None:
        raise LayoutUnreadableError("the calibration has no slot layout: run a validation first")
    slots = layout["slots"]
    return _trays_seen(photo_tags.photo_tags_for(path), artifact.scale_field, slots, references or {}), slots
