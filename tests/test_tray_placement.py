"""Tray placement from the cell A1 tag (#220), against stills of 20 October with a known layout.

The fixture holds the real tag detections of four stills of "tray tracking 26.10.20" (metrology
log 15.5l), their calibration's scale field and slot layout. The expected slots and corners are
the printed shuffle maps (`experiments/round1-trays/sessions/shuffle-maps-2026-10-20.json`) with
Aaron's corrections from the pictures (`shuffle-times-2026-10-20.csv`), not anything the code
works out.
"""

import json
from pathlib import Path

import pytest

from npec_rig.calibration import scale_field_from_dict
from npec_rig.tags import TagDetection
from npec_rig.tray_placement import place_trays

pytestmark = pytest.mark.unit

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "trays" / "shuffles-2026-10-20.json").read_text())

# Tray ID: (slot, A1 corner), or (slot, None) where Aaron's note gives the slot only.
LAYOUTS = {
    # Layout 2, touching, as the map.
    "080357_563754": {
        3: ("North 1", "SW"), 10: ("North 2", "SW"), 6: ("North 3", "SW"), 1: ("North 4", "NE"),
        4: ("North 5", "SW"), 12: ("North 6", "NE"), 9: ("South 1", "NE"), 11: ("South 2", "SW"),
        7: ("South 3", "NE"), 8: ("South 4", "SW"), 5: ("South 5", "SW"), 2: ("South 6", "SW"),
    },
    # Layout 3, gaps: "Tray 1 was in North 4, not North 5", so tray 10 in North 5.
    "081557_536877": {
        5: ("North 1", "SW"), 8: ("North 2", "SW"), 3: ("North 3", "NE"), 1: ("North 4", None),
        10: ("North 5", None), 9: ("North 6", "SW"), 12: ("South 1", "NE"), 7: ("South 2", "NE"),
        11: ("South 3", "NE"), 4: ("South 4", "NE"), 2: ("South 5", "NE"), 6: ("South 6", "NE"),
    },
    # Layout 11, gaps: "Trays 4 and 10 were swapped. T4: South 6; T10: South 5".
    "100857_566810": {
        11: ("North 1", "SW"), 5: ("North 2", "NE"), 1: ("North 3", "NE"), 9: ("North 4", "SW"),
        7: ("North 5", "NE"), 8: ("North 6", "NE"), 3: ("South 1", "NE"), 6: ("South 2", "NE"),
        12: ("South 3", "NE"), 2: ("South 4", "NE"), 10: ("South 5", None), 4: ("South 6", None),
    },
    # Layout 12, touching: "Trays in correct order; T1, T4, T6, T8, T10 oriented NE instead of SW;
    # T9, T11 oriented SW instead of NE".
    "103957_586168": {
        1: ("North 1", "NE"), 7: ("North 2", "NE"), 6: ("North 3", "NE"), 11: ("North 4", "SW"),
        8: ("North 5", "NE"), 12: ("North 6", "NE"), 4: ("South 1", "NE"), 5: ("South 2", "NE"),
        9: ("South 3", "SW"), 3: ("South 4", "NE"), 10: ("South 5", "NE"), 2: ("South 6", "NE"),
    },
}


def _detections(still: str) -> list[TagDetection]:
    out = []
    for tag in FIXTURE["stills"][still]:
        corners = tuple(tuple(c) for c in tag["corners"])
        centre = (sum(c[0] for c in corners) / 4, sum(c[1] for c in corners) / 4)
        out.append(TagDetection(tag_id=tag["id"], corners=corners, centre=centre))
    return out


def _place(still: str):
    return place_trays(_detections(still), scale_field_from_dict(FIXTURE["scale_field"]), FIXTURE["slots"])


@pytest.mark.parametrize("still", sorted(LAYOUTS))
def test_every_tray_is_placed_in_the_slot_and_corner_it_was_laid_out_in(still: str) -> None:
    placed = {p.tray_id: (p.slot, p.a1_corner) for p in _place(still)}
    expected = LAYOUTS[still]
    assert sorted(placed) == sorted(expected)  # tray tags only, the corner tags left out
    for tray, (slot, corner) in expected.items():
        assert placed[tray][0] == slot, f"tray {tray}"
        if corner is not None:
            assert placed[tray][1] == corner, f"tray {tray}"


def _moved_copy(tag: TagDetection, tag_id: int, dx: float, dy: float) -> TagDetection:
    return TagDetection(
        tag_id=tag_id,
        corners=tuple((x + dx, y + dy) for x, y in tag.corners),
        centre=(tag.centre[0] + dx, tag.centre[1] + dy),
    )


def test_two_trays_placed_in_one_slot_both_say_so_and_the_others_are_placed() -> None:
    detections = _detections("080357_563754")
    tray3 = next(d for d in detections if d.tag_id == 3)
    # A 13th tag 30 mm (about 146 px at this calibration's 4.86 px/mm) beside tray 3's: a second
    # tray in tray 3's slot.
    detections.append(_moved_copy(tray3, 13, 146, 0))
    placed = place_trays(detections, scale_field_from_dict(FIXTURE["scale_field"]), FIXTURE["slots"])
    status = {p.tray_id: p.status for p in placed}
    assert status[3] == status[13] == "two trays in one slot"
    assert all(s == "placed" for tray, s in status.items() if tray not in (3, 13))


def test_a_tag_on_a_slot_centre_is_a_close_call() -> None:
    # The two candidate tray centres lie either side of the tag, so with the tag on a slot centre
    # they are the same distance from it and neither corner can be told apart.
    detections = [d for d in _detections("080357_563754") if d.tag_id != 6]
    tray6 = next(d for d in _detections("080357_563754") if d.tag_id == 6)
    slot = next(s for s in FIXTURE["slots"] if s["name"] == "North 3")
    detections.append(_moved_copy(tray6, 6, slot["centre"][0] - tray6.centre[0], slot["centre"][1] - tray6.centre[1]))
    placed = {p.tray_id: p for p in place_trays(detections, scale_field_from_dict(FIXTURE["scale_field"]), FIXTURE["slots"])}
    assert placed[6].status == "close call"


@pytest.mark.parametrize("still", sorted(LAYOUTS))
def test_each_outline_holds_its_own_tag_and_no_other_trays_tag(still: str) -> None:
    import cv2
    import numpy as np

    tags = {d.tag_id: d.centre for d in _detections(still) if d.tag_id <= 12}
    for p in _place(still):
        outline = np.array(p.outline, dtype=np.float32).reshape(-1, 1, 2)
        inside = {tray for tray, c in tags.items() if cv2.pointPolygonTest(outline, c, False) > 0}
        assert inside == {p.tray_id}, f"tray {p.tray_id}"
