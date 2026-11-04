"""Restricted randomization of the tray layout (#343).

Expected values come from the issue's worked example, reference/trays.md and Aaron's records of
the 20 October shuffles. Trays stand wherever the researcher puts them (Aaron, 2026-11-04): a
place is where a tray stood, and its outer sides are those with no tray between it and the
border. A1 at SW: row 1 is the south end, column A the west side.
"""

import json
import random
from pathlib import Path

import pytest

from npec_rig.calibration import scale_field_from_dict
from npec_rig.randomization import (
    Lying,
    NoLayoutError,
    Place,
    Position,
    TraySeen,
    breaks_rule,
    check_layout,
    edge_exposure,
    least_breaking_layout,
    table_places,
    suggest_layout,
)
from npec_rig.tags import TagDetection
from npec_rig.tray_placement import place_trays

pytestmark = pytest.mark.unit

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "trays" / "shuffles-2026-10-20.json").read_text())
SLOT_NAMES = [f"{side} {n}" for side in ("North", "South") for n in range(1, 7)]
# Two rows of six, as on 20 October: the outer sides of each slot, worked out by hand.
SLOT_SIDES = {
    name: frozenset({"north" if name.startswith("North") else "south"}
                    | ({"west"} if name.endswith(" 1") else set()) | ({"east"} if name.endswith(" 6") else set()))
    for name in SLOT_NAMES
}

# Layout 2 of 20 October, as read by hand from the photo (tests/test_tray_placement.py).
MEASURED = {
    3: ("North 1", "SW"), 10: ("North 2", "SW"), 6: ("North 3", "SW"), 1: ("North 4", "NE"),
    4: ("North 5", "SW"), 12: ("North 6", "NE"), 9: ("South 1", "NE"), 11: ("South 2", "SW"),
    7: ("South 3", "NE"), 8: ("South 4", "SW"), 5: ("South 5", "SW"), 2: ("South 6", "SW"),
}
LAST = {tray: Lying(SLOT_SIDES[slot], heading) for tray, (slot, heading) in MEASURED.items()}


def test_issue_example_south_1_with_a1_at_sw_puts_row_1_and_column_a_on_the_edge() -> None:
    # "Tray 2 sits in South 1 with its A1 end along the southern border": South 1 is also at
    # the west border, where column A lies when A1 is at SW.
    assert edge_exposure({"south", "west"}, "SW") == {"row 1", "column A"}


def test_issue_example_north_6_with_the_a1_end_north_again_breaks_the_rule() -> None:
    # Last round South 1, A1 end along the south border. North 6 with the A1 end along the north
    # border puts row 1 on the edge again: rejected. Turned 180 degrees (A1 at SW), it passes.
    last = Lying(frozenset({"south", "west"}), "SW")
    assert breaks_rule(last, Lying(frozenset({"north", "east"}), "NE"))
    assert not breaks_rule(last, Lying(frozenset({"north", "east"}), "SW"))


def test_a_2x2_tray_turned_round_from_its_first_photo_has_its_first_south_end_north() -> None:
    # A 2 x 2 tray has rows 1 and 2 and columns A and B. Its tag is fixed to the tray, so its
    # heading is read against its first photo: row 1 is the end that faced south then, column A
    # the side that faced west. Turned round at the north-west, row 1 is on the north edge and
    # column B on the west edge.
    assert edge_exposure({"north", "west"}, "turned", tray_type="2x2") == {"row 1", "column B"}
    assert edge_exposure({"south"}, "as first", tray_type="2x2") == {"row 1"}


# --- Places: trays stand wherever the researcher puts them (Aaron, 2026-11-04) ---------------
# Tray centres in photo pixels, north at the top (small y), at 5 px/mm. Only the table's own
# north, south, west and east edges are edges, and an empty spot is a place too (Aaron).


def test_the_development_table_is_two_rows_of_five_with_one_empty_place() -> None:
    # The development table of 4 November: five trays along the north, four along the south, the
    # gap under the second north tray. Centres as the photo gave them (not in a straight line).
    centres = {79: (989, 2273), 85: (2774, 2154), 77: (4523, 2220), 80: (6326, 2292), 78: (8115, 2301),
               87: (998, 4288), 76: (4332, 4346), 86: (6184, 4436), 81: (8050, 4431)}
    places = table_places(centres, px_per_mm=5.0)
    assert len(places) == 10
    by_tray = {p.occupant: p for p in places}
    assert by_tray[85].label == "North row, 2nd from west" and by_tray[85].sides == {"north"}
    assert by_tray[79].sides == {"north", "west"}
    assert by_tray[81].sides == {"south", "east"}
    empty = [p for p in places if p.occupant is None]
    assert [(p.label, p.sides) for p in empty] == [("South row, 2nd from west", {"south"})]
    # The empty place lies under tray 85, level with the south row.
    assert abs(empty[0].centre[0] - 2774) < 1 and abs(empty[0].centre[1] - 4375) < 60


def test_a_middle_row_is_on_no_north_or_south_edge() -> None:
    # Three rows of two: the middle row touches only the west and east edges.
    centres = {1: (500, 500), 2: (2200, 520), 3: (510, 2400), 4: (2190, 2380), 5: (500, 4300), 6: (2210, 4290)}
    places = {p.occupant: p for p in table_places(centres, px_per_mm=5.0)}
    assert places[3].sides == {"west"} and places[4].sides == {"east"}
    assert places[3].label == "Row 2 from north, 1st from west"
    assert places[1].sides == {"north", "west"}


@pytest.mark.parametrize("seed", range(10))
def test_suggestion_gives_every_tray_its_own_place_and_breaks_no_rule(seed: int) -> None:
    layout = suggest_layout(sorted(LAST), LAST, SLOT_SIDES, random.Random(seed))
    assert sorted(layout) == sorted(LAST)
    assert sorted(p.place for p in layout.values()) == sorted(SLOT_NAMES)
    assert {p.heading for p in layout.values()} <= {"SW", "NE"}
    assert not [t for t, p in layout.items() if breaks_rule(LAST[t], Lying(SLOT_SIDES[p.place], p.heading))]


def test_a_tray_shut_in_on_every_side_may_lie_either_way() -> None:
    # The middle of a plus shape has no outer side: no heading breaks the rule there, so over 40
    # draws both headings come up.
    places = {"mid": frozenset(), "n": frozenset({"north", "west", "east"})}
    last = {1: Lying(frozenset({"north", "west", "east"}), "SW"), 2: Lying(frozenset(), "SW")}
    headings = set()
    for seed in range(40):
        layout = suggest_layout([1, 2], last, places, random.Random(seed))
        headings.add(next(p.heading for t, p in layout.items() if p.place == "mid"))
    assert headings == {"SW", "NE"}


def test_the_same_seed_gives_the_same_layout() -> None:
    first = suggest_layout(sorted(LAST), LAST, SLOT_SIDES, random.Random(42))
    assert suggest_layout(sorted(LAST), LAST, SLOT_SIDES, random.Random(42)) == first


def test_a_table_with_no_passing_layout_raises() -> None:
    # One tray standing alone: all four sides are outer, so either heading puts rows 1 and 5 and
    # columns A and D on the edge again.
    all_four = frozenset({"north", "south", "west", "east"})
    with pytest.raises(NoLayoutError):
        suggest_layout([1], {1: Lying(all_four, "SW")}, {"only": all_four}, random.Random(0))


SCALE = scale_field_from_dict(FIXTURE["scale_field"])
PLACES = {
    s["name"]: Place(s["name"], tuple(s["centre"]), SLOT_SIDES[s["name"]], SCALE.px_per_mm(*s["centre"]))
    for s in FIXTURE["slots"]
}


def _seen(still: str) -> list[TraySeen]:
    """The trays of a 20 October still, each where its tag in A1 puts it, with the outer sides of
    its slot."""
    detections = []
    for tag in FIXTURE["stills"][still]:
        corners = tuple(tuple(c) for c in tag["corners"])
        centre = (sum(c[0] for c in corners) / 4, sum(c[1] for c in corners) / 4)
        detections.append(TagDetection(tag_id=tag["id"], corners=corners, centre=centre))
    return [
        TraySeen(p.tray_id, tuple(p.centre), p.a1_corner, SLOT_SIDES[p.slot], 0.0)
        for p in place_trays(detections, SCALE, FIXTURE["slots"])
    ]


def test_check_finds_the_trays_laid_the_wrong_way_round() -> None:
    # Layout 12 of 20 October (Aaron's note): "Trays in correct order; T1, T4, T6, T8, T10
    # oriented NE instead of SW; T9, T11 oriented SW instead of NE".
    meant = {
        1: ("North 1", "SW"), 7: ("North 2", "NE"), 6: ("North 3", "SW"), 11: ("North 4", "NE"),
        8: ("North 5", "SW"), 12: ("North 6", "NE"), 4: ("South 1", "SW"), 5: ("South 2", "NE"),
        9: ("South 3", "NE"), 3: ("South 4", "NE"), 10: ("South 5", "SW"), 2: ("South 6", "NE"),
    }
    checks = check_layout({t: Position(*w) for t, w in meant.items()}, _seen("103957_586168"), {}, PLACES)
    status = {c.tray_id: c.status for c in checks}
    assert status == {t: "turned" if t in (1, 4, 6, 8, 10, 9, 11) else "in place" for t in meant}


def test_check_finds_two_swapped_trays() -> None:
    # Layout 11 of 20 October (Aaron's note): "Trays 4 and 10 were swapped. T4: South 6; T10:
    # South 5". So the layout meant T4 in South 5 and T10 in South 6. The note gives no heading
    # for trays 1, 4 and 10, so only their place is judged.
    meant = {
        11: ("North 1", "SW"), 5: ("North 2", "NE"), 1: ("North 3", None), 9: ("North 4", "SW"),
        7: ("North 5", "NE"), 8: ("North 6", "NE"), 3: ("South 1", "NE"), 6: ("South 2", "NE"),
        12: ("South 3", "NE"), 2: ("South 4", "NE"), 4: ("South 5", None), 10: ("South 6", None),
    }
    checks = {c.tray_id: c for c in check_layout(
        {t: Position(*w) for t, w in meant.items()}, _seen("100857_566810"), {}, PLACES
    )}
    assert {t for t, c in checks.items() if c.status.startswith("wrong place")} == {4, 10}
    assert checks[4].found_at == "South 6" and checks[10].found_at == "South 5"
    assert all(checks[t].status == "in place" for t in meant if meant[t][1] is not None)


def test_check_reports_a_missing_tray_and_a_tray_breaking_the_rule() -> None:
    # Layout 12 has tray 12 in North 6 with A1 at NE, as in layout 2: its row 1 and column A are
    # on the edge two rounds in a row. Tray 99 is in the suggestion and not on the table.
    suggested = {12: Position("North 1", "SW"), 99: Position("South 1", "SW")}
    checks = {c.tray_id: c for c in check_layout(suggested, _seen("103957_586168"), LAST, PLACES)}
    assert checks[99].status == "missing"
    assert checks[12].breaks_rule
    assert not checks[7].breaks_rule  # North 2 NE after South 3 NE: north end row 1, was row 5
    assert checks[7].status == "not in layout"


def test_when_the_rule_cannot_be_kept_the_fewest_trays_break_it() -> None:
    # The development table of 4 November: nine 2 x 2 trays; tray 85 has no tray north or south
    # of it, so it has both borders. Wherever it goes it repeats an end row, and any tray put in
    # its place does too: the least is one tray, tray 85 staying in its place.
    F = frozenset
    sides = {76: F({"south"}), 77: F({"north"}), 78: F({"north", "east"}), 79: F({"north", "west"}),
             80: F({"north"}), 81: F({"south", "east"}), 85: F({"north", "south"}), 86: F({"south"}),
             87: F({"south", "west"})}
    last = {t: Lying(s, "as first") for t, s in sides.items()}
    places = {str(t): s for t, s in sides.items()}
    for seed in range(5):
        layout = least_breaking_layout(sorted(last), last, places, random.Random(seed))
        breaking = [t for t, p in layout.items() if breaks_rule(last[t], Lying(places[p.place], p.heading), t)]
        assert breaking == [85]
