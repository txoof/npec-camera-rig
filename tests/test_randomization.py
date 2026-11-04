"""Restricted randomization of the tray layout (#343).

Expected values come from the issue's worked example and reference/trays.md: 12 trays in
portrait, North 1 to 6 along the north border, South 1 to 6 along the south border, slot 1 at
the west border and slot 6 at the east. A1 at SW: row 1 is the south end, column A the west side.
"""

import json
import random
from pathlib import Path

import pytest

from npec_rig.calibration import scale_field_from_dict
from npec_rig.randomization import (
    NoLayoutError,
    Position,
    TraySeen,
    breaks_rule,
    check_layout,
    edge_exposure,
    suggest_layout,
)
from npec_rig.tags import TagDetection
from npec_rig.tray_placement import place_trays

pytestmark = pytest.mark.unit

SLOTS = [f"{side} {n}" for side in ("North", "South") for n in range(1, 7)]

# Layout 2 of 20 October, as read by hand from the photo (tests/test_tray_placement.py).
MEASURED = {
    3: ("North 1", "SW"), 10: ("North 2", "SW"), 6: ("North 3", "SW"), 1: ("North 4", "NE"),
    4: ("North 5", "SW"), 12: ("North 6", "NE"), 9: ("South 1", "NE"), 11: ("South 2", "SW"),
    7: ("South 3", "NE"), 8: ("South 4", "SW"), 5: ("South 5", "SW"), 2: ("South 6", "SW"),
}
LAST = {tray: Position(*where) for tray, where in MEASURED.items()}


def test_issue_example_south_1_with_a1_at_sw_puts_row_1_and_column_a_on_the_edge() -> None:
    # "Tray 2 sits in South 1 with its A1 end along the southern border": South 1 is also at
    # the west border, where column A lies when A1 is at SW.
    assert edge_exposure("South 1", "SW") == {"row 1", "column A"}


def test_issue_example_north_6_with_the_a1_end_north_again_breaks_the_rule() -> None:
    # Last round South 1, A1 end along the south border. North 6 with the A1 end along the north
    # border puts row 1 on the edge again: rejected. Turned 180 degrees (A1 at SW), it passes.
    last = Position("South 1", "SW")
    assert breaks_rule(last, Position("North 6", "NE"))
    assert not breaks_rule(last, Position("North 6", "SW"))


@pytest.mark.parametrize("seed", range(10))
def test_suggestion_gives_every_tray_its_own_slot_and_breaks_no_rule(seed: int) -> None:
    layout = suggest_layout(sorted(LAST), LAST, SLOTS, random.Random(seed))
    assert sorted(layout) == sorted(LAST)
    assert sorted(p.slot for p in layout.values()) == sorted(SLOTS)
    assert {p.heading for p in layout.values()} <= {"SW", "NE"}
    assert not [tray for tray, p in layout.items() if breaks_rule(LAST[tray], p)]


def test_the_same_seed_gives_the_same_layout() -> None:
    first = suggest_layout(sorted(LAST), LAST, SLOTS, random.Random(42))
    assert suggest_layout(sorted(LAST), LAST, SLOTS, random.Random(42)) == first


def test_a_table_with_no_passing_layout_raises() -> None:
    # One slot that is at both the west and east border: either heading puts columns A and D on
    # the edge again.
    with pytest.raises(NoLayoutError):
        suggest_layout([1], {1: Position("North 1", "SW")}, ["North 1"], random.Random(0))


FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "trays" / "shuffles-2026-10-20.json").read_text())


def _placements(still: str):
    detections = []
    for tag in FIXTURE["stills"][still]:
        corners = tuple(tuple(c) for c in tag["corners"])
        centre = (sum(c[0] for c in corners) / 4, sum(c[1] for c in corners) / 4)
        detections.append(TagDetection(tag_id=tag["id"], corners=corners, centre=centre))
    placements = place_trays(detections, scale_field_from_dict(FIXTURE["scale_field"]), FIXTURE["slots"])
    return [TraySeen(p.tray_id, p.slot, p.a1_corner, tuple(p.centre), 0.0) for p in placements]


def test_check_finds_the_trays_laid_the_wrong_way_round() -> None:
    # Layout 12 of 20 October (Aaron's note): "Trays in correct order; T1, T4, T6, T8, T10
    # oriented NE instead of SW; T9, T11 oriented SW instead of NE".
    meant = {
        1: ("North 1", "SW"), 7: ("North 2", "NE"), 6: ("North 3", "SW"), 11: ("North 4", "NE"),
        8: ("North 5", "SW"), 12: ("North 6", "NE"), 4: ("South 1", "SW"), 5: ("South 2", "NE"),
        9: ("South 3", "NE"), 3: ("South 4", "NE"), 10: ("South 5", "SW"), 2: ("South 6", "NE"),
    }
    checks = check_layout({t: Position(*w) for t, w in meant.items()}, _placements("103957_586168"), {})
    status = {c.tray_id: c.status for c in checks}
    assert status == {t: "turned" if t in (1, 4, 6, 8, 10, 9, 11) else "in place" for t in meant}


def test_check_finds_two_swapped_trays() -> None:
    # Layout 11 of 20 October (Aaron's note): "Trays 4 and 10 were swapped. T4: South 6; T10:
    # South 5". So the layout meant T4 in South 5 and T10 in South 6. The note gives no heading
    # for trays 1, 4 and 10, so only their slot is judged.
    meant = {
        11: ("North 1", "SW"), 5: ("North 2", "NE"), 1: ("North 3", None), 9: ("North 4", "SW"),
        7: ("North 5", "NE"), 8: ("North 6", "NE"), 3: ("South 1", "NE"), 6: ("South 2", "NE"),
        12: ("South 3", "NE"), 2: ("South 4", "NE"), 4: ("South 5", None), 10: ("South 6", None),
    }
    checks = {c.tray_id: c for c in check_layout(
        {t: Position(*w) for t, w in meant.items()}, _placements("100857_566810"), {}
    )}
    assert {t for t, c in checks.items() if c.status.startswith("wrong slot")} == {4, 10}
    assert checks[4].found.slot == "South 6" and checks[10].found.slot == "South 5"
    assert all(checks[t].status == "in place" for t in meant if meant[t][1] is not None)


def test_check_reports_a_missing_tray_and_a_tray_breaking_the_rule() -> None:
    # Layout 12 has tray 12 in North 6 with A1 at NE, as in layout 2: its row 1 and column A are
    # on the edge two rounds in a row. Tray 99 is in the suggestion and not on the table.
    suggested = {12: Position("North 1", "SW"), 99: Position("South 1", "SW")}
    checks = {c.tray_id: c for c in check_layout(suggested, _placements("103957_586168"), LAST)}
    assert checks[99].status == "missing"
    assert checks[12].breaks_rule
    assert not checks[7].breaks_rule  # North 2 NE after South 3 NE: north end row 1, was row 5
    assert checks[7].status == "not in layout"


def test_a_2x2_tray_turned_round_from_its_first_photo_has_its_first_south_end_north() -> None:
    # A 2 x 2 tray has rows 1 and 2 and columns A and B. Its tag is fixed to the tray, so its
    # heading is read against its first photo: row 1 is the end that faced south then, column A
    # the side that faced west. Turned round in North 1, row 1 is on the north edge and column B
    # on the west edge.
    assert edge_exposure("North 1", "turned", tray_type="2x2") == {"row 1", "column B"}
    assert edge_exposure("South 3", "as first", tray_type="2x2") == {"row 1"}
