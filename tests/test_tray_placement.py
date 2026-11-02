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


def _square_tag(tag_id: int, centre: tuple[float, float], side_px: float, turned_deg: float) -> TagDetection:
    """A tag with its top facing up, turned clockwise on the photo by `turned_deg`."""
    import math

    t = math.radians(turned_deg)
    h = side_px / 2
    corners = tuple(
        (centre[0] + x * math.cos(t) - y * math.sin(t), centre[1] + x * math.sin(t) + y * math.cos(t))
        for x, y in ((-h, -h), (h, -h), (h, h), (-h, h))  # top-left, top-right, bottom-right, bottom-left
    )
    return TagDetection(tag_id=tag_id, corners=corners, centre=centre)


@pytest.mark.parametrize("turned_deg, tilt_deg", [(5, 5), (-3, -3), (93, 3), (178, -2)])
def test_tilt_is_the_tags_turn_off_the_nearest_right_angle(turned_deg: float, tilt_deg: float) -> None:
    slot = next(s for s in FIXTURE["slots"] if s["name"] == "North 3")
    tag = _square_tag(6, (slot["centre"][0] + 600, slot["centre"][1] - 700), 194, turned_deg)
    [placed] = place_trays([tag], scale_field_from_dict(FIXTURE["scale_field"]), FIXTURE["slots"])
    assert placed.tilt_deg == pytest.approx(tilt_deg, abs=0.01)


def test_the_outline_is_the_trays_measured_size_at_the_tags_scale() -> None:
    import math

    scale = scale_field_from_dict(FIXTURE["scale_field"])
    tags = {d.tag_id: d for d in _detections("080357_563754")}
    for p in _place("080357_563754"):
        ppm = scale.px_per_mm(*tags[p.tray_id].centre)
        sides = [math.dist(p.outline[i], p.outline[(i + 1) % 4]) / ppm for i in range(4)]
        # Tape measure, reference/trays.md: 305.0 mm east-west, 366.0 mm north-south.
        assert sides == pytest.approx([305.0, 366.0, 305.0, 366.0], abs=0.01), f"tray {p.tray_id}"


# --- Naming outlines found in the photo from the tags inside them (#331) -------------------------
# Worked examples at an even 10 px/mm: a tray 305 x 366 mm is 3050 x 3660 px.

EVEN_10 = {"coeffs": [1.0, 0.0, 0.0], "mean_px_per_mm": 10.0, "residual_std_pct": 0.0}


def _box_outline(x0: float, y0: float, edge: bool = False):
    from npec_rig.tray_placement import TrayOutline

    corners = ((x0, y0), (x0 + 3050, y0), (x0 + 3050, y0 + 3660), (x0, y0 + 3660))
    return TrayOutline(corners=corners, centre=(x0 + 1525, y0 + 1830), tilt_deg=0.0, edge=edge)


def _tag_at(tag_id: int, x: float, y: float) -> TagDetection:
    return TagDetection(tag_id, ((x - 200, y - 200), (x + 200, y - 200), (x + 200, y + 200), (x - 200, y + 200)), (x, y))


def test_a_tag_names_the_outline_its_centre_lies_inside_wherever_it_lies_in_the_tray() -> None:
    from npec_rig.tray_placement import name_trays

    # Tag 4 near the outline's north-east corner, not in cell A1: it still names the outline.
    outline = _box_outline(1000, 500)
    [tray] = name_trays([outline], [_tag_at(4, 3700, 900)])
    assert (tray.tray_id, tray.found, tray.warnings) == (4, "photo + tag", ())
    assert tray.outline == outline.corners
    assert (tray.centre, tray.slot) == ((2525, 2330), None)


def test_an_outline_with_no_tag_inside_keeps_its_outline_with_no_tray_id_and_says_no_tag() -> None:
    from npec_rig.tray_placement import name_trays

    outline = _box_outline(1000, 500)
    [tray] = name_trays([outline], [])
    assert (tray.tray_id, tray.found, tray.warnings, tray.slot) == (None, "photo, no tag", ("no tag",), None)
    assert tray.outline == outline.corners


def test_two_tags_in_one_outline_both_get_it_and_both_say_so() -> None:
    from npec_rig.tray_placement import name_trays

    outline = _box_outline(1000, 500)
    trays = name_trays([outline], [_tag_at(4, 1500, 3800), _tag_at(9, 3700, 900)])
    assert sorted((t.tray_id, t.found, t.warnings) for t in trays) == [
        (4, "photo + tag", ("two tags in one tray outline",)),
        (9, "photo + tag", ("two tags in one tray outline",)),
    ]
    assert all(t.outline == outline.corners for t in trays)


def test_a_tag_in_the_strip_two_outlines_share_names_only_the_one_whose_centre_is_nearer() -> None:
    """Review of #334: accepted outlines may overlap by up to a quarter (`MAX_OVERLAP`). Outlines
    at x 1000 to 4050 and 3550 to 6600 share x 3550 to 4050; tag 4 at x 3700 lies 1175 px from the
    first's centre (2525) and 1375 px from the second's (5075). It names the first only; the
    second is a tray with no tag, never a second tray 4."""
    from npec_rig.tray_placement import name_trays

    first, second = _box_outline(1000, 500), _box_outline(3550, 500)
    trays = name_trays([first, second], [_tag_at(4, 3700, 2000)])
    assert sorted(((t.tray_id or 0), t.outline == first.corners, t.found) for t in trays) == [
        (0, False, "photo, no tag"),
        (4, True, "photo + tag"),
    ]


def test_a_tag_inside_no_outline_is_a_tag_seen_with_no_tray_outline_where_the_tag_lies() -> None:
    """No tray found in the photo around tag 4 (a black tray, one under a sheet, an edge tag on the
    rail): the tag is reported at its own centre, with no outline and no slot. Placing a tray from
    the tag assumed it lay in cell A1 and put outlines about 176 mm off (#331 edge-tag trial)."""
    from npec_rig.tray_placement import name_trays

    [tray] = name_trays([], [_tag_at(4, 4500, 900)])
    assert (tray.tray_id, tray.found, tray.warnings) == (4, "tag only", ("tag seen, tray not found in the photo",))
    assert (tray.centre, tray.outline, tray.slot) == ((4500, 900), None, None)


def test_an_outline_cut_from_blue_touching_the_photo_edge_says_partly_outside_the_photo() -> None:
    from npec_rig.tray_placement import name_trays

    tagged, untagged = _box_outline(0, 500, edge=True), _box_outline(3050, 500, edge=True)
    trays = name_trays([tagged, untagged], [_tag_at(4, 1500, 3800)])
    assert sorted((t.tray_id or 0, t.warnings) for t in trays) == [
        (0, ("no tag", "partly outside the photo")),
        (4, ("partly outside the photo",)),
    ]


# --- Trays found in the photo from their blue plastic (#331) -------------------------------------
# Drawn scenes, a quarter of full size: tray blue (RGB 40, 90, 200: OpenCV hue 110, saturation
# 204, value 200, inside the sampled tray plastic) on grey table. At an even 10 px/mm a tray is
# 3050 x 3660 full-size px, 762.5 x 915 at a quarter.

TRAY_BLUE = (40, 90, 200)


def _scene(size=(1100, 1300), boxes=()):
    """A grey quarter-size photo (width, height) with blue boxes given in FULL-size px
    (x0, y0, x1, y1)."""
    import numpy as np

    image = np.full((size[1], size[0], 3), 128, np.uint8)
    for x0, y0, x1, y1 in boxes:
        image[round(y0 / 4):round(y1 / 4), round(x0 / 4):round(x1 / 4)] = TRAY_BLUE
    return image


def _flat(corners) -> list[float]:
    return [v for corner in sorted(corners) for v in corner]


def test_one_blue_tray_is_found_where_it_was_drawn() -> None:
    from npec_rig.tray_placement import find_outlines

    [tray] = find_outlines(_scene(boxes=[(400, 400, 3450, 4060)]), scale_field_from_dict(EVEN_10), 4)
    assert tray.centre == pytest.approx((1925, 2230), abs=10)  # 1 mm
    assert _flat(tray.corners) == pytest.approx(_flat([(400, 400), (3450, 400), (3450, 4060), (400, 4060)]), abs=10)
    assert tray.edge is False


def test_two_touching_trays_in_one_blue_piece_are_cut_into_two_at_the_tray_size() -> None:
    """Two trays side by side with no gap, 6100 x 3660 px: the cut lies at x 400 + 3050 = 3450."""
    from npec_rig.tray_placement import find_outlines

    trays = find_outlines(_scene((1800, 1300), [(400, 400, 6500, 4060)]), scale_field_from_dict(EVEN_10), 4)
    assert sorted(t.centre for t in trays) == [pytest.approx((1925, 2230), abs=10), pytest.approx((4975, 2230), abs=10)]


def test_a_photo_with_no_blue_finds_no_trays() -> None:
    from npec_rig.tray_placement import find_outlines

    assert find_outlines(_scene(), scale_field_from_dict(EVEN_10), 4) == []


def test_a_tray_cut_off_by_the_photo_edge_is_cut_from_the_side_inside_the_photo() -> None:
    """A tray reaching 600 px past the west edge: 2450 px of it shows. Its outline is the tray's
    full 3050 px, measured from its east side (x 2450), so the centre is at x 2450 - 1525 = 925."""
    from npec_rig.tray_placement import find_outlines

    [tray] = find_outlines(_scene(boxes=[(0, 400, 2450, 4060)]), scale_field_from_dict(EVEN_10), 4)
    assert tray.centre == pytest.approx((925, 2230), abs=10)
    assert tray.edge is True


def test_a_tray_is_found_at_the_calibrations_scale_where_it_lies() -> None:
    """At 5 px/mm a tray is 1525 x 1830 px. Drawn that size it is one tray; at 10 px/mm it would
    be under half a tray and not a tray at all."""
    from npec_rig.tray_placement import find_outlines

    small = _scene(boxes=[(400, 400, 1925, 2230)])
    assert len(find_outlines(small, scale_field_from_dict({**EVEN_10, "mean_px_per_mm": 5.0}), 4)) == 1
    assert find_outlines(small, scale_field_from_dict(EVEN_10), 4) == []


# Real stills at a quarter of full size, with answers from outside the finder: Aaron's held-out
# inspection, the rig's tag placement where he accepted it, corners marked by eye
# (tests/fixtures/trays/blue-finder/README.md).
BLUE_FIXTURES = Path(__file__).parent / "fixtures" / "trays" / "blue-finder"
BLUE_EXPECTED = json.loads((BLUE_FIXTURES / "expected.json").read_text())["fixtures"]


def _fixture_outlines(name: str):
    import numpy as np
    from PIL import Image

    from npec_rig.tray_placement import find_outlines

    fixture = BLUE_EXPECTED[name]
    with Image.open(BLUE_FIXTURES / f"{name}.jpg") as image:
        rgb = np.asarray(image.convert("RGB"))
    return find_outlines(rgb, scale_field_from_dict(fixture["scale_field"]), fixture["factor"])


@pytest.mark.parametrize("name", sorted(BLUE_EXPECTED))
def test_every_tray_in_a_real_still_is_found_once(name: str) -> None:
    assert len(_fixture_outlines(name)) == BLUE_EXPECTED[name]["count"]


@pytest.mark.parametrize("name", sorted(n for n, f in BLUE_EXPECTED.items() if f["trays"]))
def test_each_tray_found_in_a_real_still_lies_within_30_mm_of_its_known_centre(name: str) -> None:
    """30 mm, as in #328. A tray only partly in the photo is left out: its outline is the tray's
    full size from its side inside the photo, not the visible part that was marked."""
    import math

    fixture = BLUE_EXPECTED[name]
    scale = scale_field_from_dict(fixture["scale_field"])
    found = [o.centre for o in _fixture_outlines(name)]
    for tray in fixture["trays"]:
        if tray.get("partial"):
            continue
        x, y = tray["centre_px"]
        nearest = min(math.dist((x, y), c) for c in found) / scale.px_per_mm(x, y)
        assert nearest <= fixture["centre_tolerance_mm"], f"{tray.get('tray_id', tray.get('name'))}: {nearest:.1f} mm"


@pytest.mark.parametrize("name", sorted(n for n, f in BLUE_EXPECTED.items() if f["trays"] and "tray_id" in f["trays"][0]))
def test_each_tray_tag_in_a_real_still_names_the_tray_it_lies_on(name: str) -> None:
    import math

    from npec_rig.tray_placement import name_trays

    fixture = BLUE_EXPECTED[name]
    scale = scale_field_from_dict(fixture["scale_field"])
    tags = [TagDetection(t["tag_id"], tuple(tuple(c) for c in t["corners"]), tuple(t["centre"])) for t in fixture["tags"]]
    trays = name_trays(_fixture_outlines(name), tags)
    assert {t.found for t in trays} == {"photo + tag"}
    named = {t.tray_id: t for t in trays}
    assert sorted(named) == sorted(t["tray_id"] for t in fixture["trays"])
    for tray in fixture["trays"]:
        x, y = tray["centre_px"]
        assert math.dist((x, y), named[tray["tray_id"]].centre) / scale.px_per_mm(x, y) <= 30, f"tray {tray['tray_id']}"
