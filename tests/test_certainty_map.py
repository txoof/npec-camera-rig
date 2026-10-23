import numpy as np
import pytest

from tests.helpers import sheet_detections, square_detection, tray_layout_detections
from npec_rig.calibration import ScaleField
from npec_rig.certainty_map import (
    MAP_WIDTH_PX,
    SlotLayoutError,
    build_slot_layout,
    calibration_centres,
    certainty_by_slot,
    group_sheets,
    moved_fraction,
    render_certainty_map,
    round_errors_by_slot,
    slot_layout_from_dict,
    slot_layout_to_dict,
    tag_errors,
)

pytestmark = pytest.mark.unit

# Uniform 4 px/mm, so a 30 mm tag is exactly 120 px across and reads 0% error.
FIELD = ScaleField((1.0, 0.0, 0.0), 4.0, 0.0)
TAG_MM = 30.0


def test_a_true_size_tag_reads_zero_error() -> None:
    errors, _corners = tag_errors([square_detection(300, 500, 500, 120.0)], FIELD, TAG_MM)
    assert errors[0].error_pct == pytest.approx(0.0)


def test_a_sheet_printed_at_96_percent_reads_about_8_percent_small() -> None:
    # The 2026-09-29 mix-up: 0.96 linear is 0.9216 in area.
    errors, _corners = tag_errors([square_detection(300, 500, 500, 120.0 * 0.96)], FIELD, TAG_MM)
    assert errors[0].error_pct == pytest.approx(-7.84)


def test_corner_and_tray_tags_are_not_calibration_targets() -> None:
    detections = [square_detection(450, 500, 500, 200.0), square_detection(10, 900, 500, 120.0)]
    errors, _corners = tag_errors(detections, FIELD, TAG_MM)
    assert errors == []


def test_error_uses_the_calibrations_own_tag_size() -> None:
    errors, _corners = tag_errors([square_detection(300, 500, 500, 120.0)], FIELD, 29.0)
    assert errors[0].error_pct == pytest.approx(100 * ((30.0 / 29.0) ** 2 - 1))


def test_tray_layout_groups_into_12_whole_sheets() -> None:
    sheets = group_sheets(tray_layout_detections(), FIELD, TAG_MM)
    assert len(sheets) == 12
    assert all(len(s.tags) == 30 for s in sheets)


def test_slots_are_named_north_then_south_west_to_east() -> None:
    layout = build_slot_layout(group_sheets(tray_layout_detections(), FIELD, TAG_MM))
    assert [s.name for s in layout] == [f"North {i}" for i in range(1, 7)] + [
        f"South {i}" for i in range(1, 7)
    ]
    north_x = [s.centre[0] for s in layout[:6]]
    assert north_x == sorted(north_x)
    assert all(n.centre[1] < s.centre[1] for n, s in zip(layout[:6], layout[6:]))


def test_a_missing_sheet_is_refused_with_a_count() -> None:
    sheets = group_sheets(tray_layout_detections(), FIELD, TAG_MM)[:11]
    with pytest.raises(SlotLayoutError, match="found 11 calibration sheets, expected 12"):
        build_slot_layout(sheets)


def test_touching_sheets_are_refused_not_pooled() -> None:
    # Two copies of the same sheet 40 mm apart link into one group with every ID twice.
    detections = sheet_detections(300, 1000, 1000) + sheet_detections(300, 1000 + 5 * 160, 1000)
    with pytest.raises(SlotLayoutError, match="touching"):
        group_sheets(detections, FIELD, TAG_MM)


def test_moved_sheets_stay_in_their_slot_and_pool_across_captures() -> None:
    layout, results = certainty_by_slot(
        tray_layout_detections(),
        [tray_layout_detections(shift=(200, -150)), tray_layout_detections(shift=(-250, 100))],
        FIELD,
        TAG_MM,
    )
    assert [r.n for r in results] == [60] * 12
    assert all(r.p95_abs_pct == pytest.approx(0.0) for r in results)


def test_a_small_sheet_shows_in_its_own_slot_only() -> None:
    capture = tray_layout_detections()
    # Replace the North 3 sheet (third from the west, north row) with a 96% print.
    north_3 = sheet_detections(300, 800.0 + 2 * 1300.0, 1000.0, side_px=120.0 * 0.96)
    capture = capture[:60] + north_3 + capture[90:]
    _layout, results = certainty_by_slot(tray_layout_detections(), [capture], FIELD, TAG_MM)
    by_name = {r.name: r for r in results}
    assert by_name["North 3"].median_pct == pytest.approx(-7.84)
    assert by_name["North 3"].p95_abs_pct == pytest.approx(7.84)
    assert by_name["North 2"].p95_abs_pct == pytest.approx(0.0)


def test_a_slot_with_too_few_tags_is_not_measured() -> None:
    capture = tray_layout_detections()[30:]  # North 1's sheet absent from this capture
    _layout, results = certainty_by_slot(tray_layout_detections(), [capture], FIELD, TAG_MM)
    north_1 = results[0]
    assert north_1.name == "North 1"
    assert (north_1.n, north_1.p95_abs_pct, north_1.median_pct) == (0, None, None)


def test_render_is_one_fixed_width_rgb_image() -> None:
    layout, results = certainty_by_slot(
        tray_layout_detections(), [tray_layout_detections()], FIELD, TAG_MM
    )
    frame = np.zeros((694, 915, 3), dtype=np.uint8)  # a preview at 1/10 of 9152x6944
    image = render_certainty_map(frame, layout, results, "caption", frame_scale=0.1)
    assert image.shape[1] == MAP_WIDTH_PX
    assert image.shape[2] == 3
    assert image.shape[0] > 694 * MAP_WIDTH_PX / 915  # caption band below the frame


def test_a_sheet_off_every_tray_slot_is_refused() -> None:
    # Halfway between the rows, on the table between the trays.
    capture = tray_layout_detections() + sheet_detections(300, 800.0 + 650.0, 2250.0)
    with pytest.raises(SlotLayoutError, match="not on any tray slot"):
        certainty_by_slot(tray_layout_detections(), [capture], FIELD, TAG_MM)


def test_an_off_slot_sheet_is_named_by_its_nearest_slot_and_distance() -> None:
    # North 1's sheet moved 720 px (180 mm at 4 px/mm) south, past half the 1300 px slot
    # spacing. Slot centres: North 1 (1120, 1400), South 1 (1120, 3900).
    capture = [
        d for d in tray_layout_detections() if not (d.centre[0] < 1500 and d.centre[1] < 2500)
    ] + sheet_detections(300, 800.0, 1000.0 + 720.0)
    layout = build_slot_layout(group_sheets(tray_layout_detections(), FIELD, TAG_MM))
    with pytest.raises(SlotLayoutError) as exc:
        round_errors_by_slot(capture, layout, FIELD, TAG_MM)
    assert (
        "the sheet with tags 300 to 329 is about 180 mm south of North 1, "
        "between North 1 and South 1" in str(exc.value)
    )


def test_a_sheet_off_the_outer_edge_is_named_outside_the_slots() -> None:
    # North 1's sheet moved 720 px (180 mm) west, off the west edge: no slot lies that way.
    capture = [
        d for d in tray_layout_detections() if not (d.centre[0] < 1500 and d.centre[1] < 2500)
    ] + sheet_detections(300, 800.0 - 720.0, 1000.0)
    layout = build_slot_layout(group_sheets(tray_layout_detections(), FIELD, TAG_MM))
    with pytest.raises(SlotLayoutError) as exc:
        round_errors_by_slot(capture, layout, FIELD, TAG_MM)
    assert "the sheet with tags 300 to 329 is about 180 mm west of North 1, outside the slots" in str(
        exc.value
    )


def test_an_off_slot_sheet_names_the_nearest_tray() -> None:
    # North 1's sheet moved 880 px (220 mm) south, off the bottom edge of North 1's tray
    # (366 mm tall, so 732 px below its centre at y 1400) but still nearer North 1 than South 1.
    # Tray 7's tag lies in cell A1 at the south-west of the tray on North 1, tray 8's on South 1.
    capture = (
        [d for d in tray_layout_detections() if not (d.centre[0] < 1500 and d.centre[1] < 2500)]
        + sheet_detections(300, 800.0, 1000.0 + 880.0)
        + [square_detection(7, 704.0, 1966.0, 160.0), square_detection(8, 704.0, 4466.0, 160.0)]
    )
    layout = build_slot_layout(group_sheets(tray_layout_detections(), FIELD, TAG_MM))
    with pytest.raises(SlotLayoutError) as exc:
        round_errors_by_slot(capture, layout, FIELD, TAG_MM)
    assert (
        "the sheet with tags 300 to 329 is about 220 mm south of North 1, "
        "between North 1 and South 1, nearest tray 7" in str(exc.value)
    )


def test_two_sheets_on_one_slot_are_refused() -> None:
    # A second, separate sheet on North 1's tray, clear of the first (gap > the 65 mm link).
    extra = sheet_detections(300, 800.0 + 4 * 160.0 + 300.0, 1000.0, columns=1, rows=6)
    with pytest.raises(SlotLayoutError, match="two sheets are on slot North 1"):
        certainty_by_slot(tray_layout_detections(), [tray_layout_detections() + extra], FIELD, TAG_MM)


def test_two_sheets_on_one_slot_are_named_by_their_tags() -> None:
    # A one-column strip of tags 300 to 305 beside North 1's full sheet of tags 300 to 329.
    extra = sheet_detections(300, 800.0 + 4 * 160.0 + 300.0, 1000.0, columns=1, rows=6)
    with pytest.raises(SlotLayoutError) as exc:
        certainty_by_slot(tray_layout_detections(), [tray_layout_detections() + extra], FIELD, TAG_MM)
    assert (
        "two sheets are on slot North 1, the sheet with tags 300 to 329 and the sheet with "
        "tags 300 to 305" in str(exc.value)
    )


def test_an_untouched_layout_has_not_moved() -> None:
    centres = calibration_centres(tray_layout_detections())
    assert moved_fraction(centres, [centres], FIELD) == 0.0


def test_a_shuffled_layout_has_moved() -> None:
    before = calibration_centres(tray_layout_detections())
    after = calibration_centres(tray_layout_detections(shift=(200, -150)))
    assert moved_fraction(after, [before], FIELD) == 1.0


def test_movement_is_judged_against_every_earlier_layout() -> None:
    calibration = calibration_centres(tray_layout_detections())
    round_1 = calibration_centres(tray_layout_detections(shift=(200, -150)))
    # Moved from the calibration, but a repeat of round 1.
    assert moved_fraction(round_1, [calibration, round_1], FIELD) == 0.0


def test_a_round_needs_every_sheet() -> None:
    layout = build_slot_layout(group_sheets(tray_layout_detections(), FIELD, TAG_MM))
    with pytest.raises(SlotLayoutError, match="found 0 calibration sheets, expected 12"):
        round_errors_by_slot([], layout, FIELD, TAG_MM)
    errors = round_errors_by_slot(tray_layout_detections(shift=(100, 0)), layout, FIELD, TAG_MM)
    assert sorted(errors) == sorted(s.name for s in layout)
    assert all(len(v) == 30 for v in errors.values())


def test_slot_layout_round_trips_through_json() -> None:
    layout = build_slot_layout(group_sheets(tray_layout_detections(), FIELD, TAG_MM))
    assert slot_layout_from_dict(slot_layout_to_dict(layout)) == layout


def test_a_round_mixing_earlier_positions_has_not_moved() -> None:
    calibration = calibration_centres(tray_layout_detections())
    round_1 = calibration_centres(tray_layout_detections(shift=(200, -150)))
    # Half the tags back where the calibration had them, half back where round 1 had them.
    half = len(calibration) // 2
    mixed = calibration[:half] + round_1[half:]
    assert moved_fraction(mixed, [calibration, round_1], FIELD) == 0.0
