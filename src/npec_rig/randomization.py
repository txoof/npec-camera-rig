"""Restricted randomization of the tray layout (#343).

The rig suggests where each tray goes (its slot) and which way round it lies (A1 at the
south-west or the north-east corner), and checks a photo against the suggestion.

The layout is drawn by restricted randomization: random layouts are drawn and any that breaks
the rule is rejected, so the one kept is drawn at random from those that pass. The rule: no row
or column of plants is on an outside edge of the table two rounds in a row.

Geometry (reference/trays.md): 12 trays in portrait, North 1 to 6 along the north border and
South 1 to 6 along the south border, numbered from the west. A 4 x 5 tray has columns A to D
across its short (east-west) side and rows 1 to 5 along its long side. With A1 at SW, row 1 is
the south end and column A the west side; turned 180 degrees (A1 at NE) they swap.
"""

from __future__ import annotations

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
from npec_rig.tray_placement import TrayPlacement, place_trays

FIRST_ROW, LAST_ROW = "row 1", "row 5"
FIRST_COLUMN, LAST_COLUMN = "column A", "column D"


class Position(NamedTuple):
    """Where a tray lies: its slot ("North 1" to "South 6") and its A1 corner ("SW" or "NE",
    None when the photo did not show which way round it lies)."""

    slot: str
    a1_corner: str | None


def edge_exposure(slot: str, a1_corner: str, columns: int = 6) -> frozenset[str]:
    """The rows and columns of plants on an outside edge of the table for a tray in `slot`
    lying with A1 at `a1_corner` ("SW" or "NE"). `columns` is the number of slots per row."""
    side, number = slot.split()
    turned = a1_corner == "NE"
    south_end, north_end = (LAST_ROW, FIRST_ROW) if turned else (FIRST_ROW, LAST_ROW)
    west_side, east_side = (LAST_COLUMN, FIRST_COLUMN) if turned else (FIRST_COLUMN, LAST_COLUMN)
    edges = {north_end if side == "North" else south_end}
    if int(number) == 1:
        edges.add(west_side)
    if int(number) == columns:
        edges.add(east_side)
    return frozenset(edges)


def breaks_rule(last: Position | None, new: Position, columns: int = 6) -> bool:
    """Whether `new` puts a row or column of plants on an outside edge that was on one at `last`.
    A tray with no last position, or whose last heading is not known, breaks nothing."""
    if last is None or last.a1_corner is None or new.a1_corner is None:
        return False
    return bool(
        edge_exposure(last.slot, last.a1_corner, columns) & edge_exposure(new.slot, new.a1_corner, columns)
    )


# Slot draws before giving up. A 12-tray draw passes about once in 10 (only the 4 end slots can
# clash), so this is far more than any solvable case needs.
MAX_DRAWS = 10_000
HEADINGS = ("SW", "NE")


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
    heading, then each heading is drawn from those that pass.
    """
    if len(trays) > len(slots):
        raise ValueError(f"{len(trays)} trays do not fit in {len(slots)} slots")
    columns = max(int(slot.split()[1]) for slot in slots)
    for _ in range(MAX_DRAWS):
        layout = {}
        for tray, slot in zip(trays, rng.sample(slots, len(trays))):
            allowed = [h for h in HEADINGS if not breaks_rule(last.get(tray), Position(slot, h), columns)]
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
    slot, turned"; "heading not read" (right slot, the photo does not show which way round);
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
    if found.a1_corner is None:
        return "heading not read" if slot_ok else "wrong slot"
    turned = found.a1_corner != wanted.a1_corner
    if slot_ok:
        return "turned" if turned else "in place"
    return "wrong slot, turned" if turned else "wrong slot"


def check_layout(
    suggested: dict[int, Position],
    placements: list,
    last: dict[int, Position],
    columns: int = 6,
) -> list[TrayCheck]:
    """Each tray in the suggestion or the photo's `placements` (tray_placement.TrayPlacement),
    compared with where the suggestion put it, ordered by tray ID."""
    found = {p.tray_id: p for p in placements}
    checks = []
    for tray in sorted(set(suggested) | set(found)):
        placement = found.get(tray)
        where = None if placement is None else Position(placement.slot, placement.a1_corner)
        broken = (
            where is not None
            and where.slot is not None
            and breaks_rule(last.get(tray), where, columns)
        )
        checks.append(
            TrayCheck(
                tray_id=tray,
                status=_status(suggested.get(tray), where),
                wanted=suggested.get(tray),
                found=where,
                centre=None if placement is None else tuple(placement.centre),
                breaks_rule=broken,
            )
        )
    return checks


class LayoutUnreadableError(RuntimeError):
    """A photo whose trays cannot be placed in slots: no calibration, or no slot layout."""


def photo_layout(path: str) -> tuple[list[TrayPlacement], list[dict]]:
    """The trays of photo `path` (a gallery path), each placed in a slot with its A1 corner from
    its tag (tray_placement.place_trays), and the slots of the photo's calibration.

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
    return place_trays(photo_tags.photo_tags_for(path), artifact.scale_field, slots), slots
