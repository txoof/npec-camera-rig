"""Time lapse videos (#64): which photos become frames, what each frame says, the video job."""
from datetime import datetime, timedelta, timezone

import pytest

from npec_rig import database, timelapse
from tests.helpers import banded_validation, turned_tray_photo

pytestmark = pytest.mark.unit

START = datetime(2027, 3, 1, 10, 0, tzinfo=timezone.utc)
# A tray outline and its 2 x 2 cells in full-size photo pixels, A1 at the bottom left: enough for a frame to be drawn.
OUTLINE = [[100, 100], [400, 100], [400, 460], [100, 460]]


def _cell(name: str, holds: str, x: float, y: float, area: float | None) -> dict:
    return {"cell": name, "holds": holds, "centre_px": [x, y],
            "corners_px": [[x - 30, y - 30], [x + 30, y - 30], [x + 30, y + 30], [x - 30, y + 30]],
            "plant_px": None if area is None else 100, "area_mm2": area, "over_other_cells": False}


def _photo(experiment_id: int, taken: datetime, *, exclusion: str | None = None, tray_id: int = 4,
           warnings: list[str] | None = None, placement: str = "placed", area: float = 1000.0,
           grown_area: float | None = None, validation: str | None = None, calibration: str | None = None,
           centre: tuple[float, float] = (250, 280), slot: str | None = None,
           others: tuple[tuple[int, tuple[float, float], str | None], ...] = (), tilt_deg: float = 0.0) -> int:
    """A photo of the experiment at `taken` with tray `tray_id` read in it, in stored slot `slot`,
    with `others` (tray ID, centre, slot) beside it, and the photo's saved exclusion."""
    capture_id = database.record_capture(
        taken_at=taken.isoformat(), path=f"rig/{taken:%Y-%m-%d}/{taken:%H%M%S}_{taken:%f}", purpose="capture",
        experiment_id=experiment_id, calibration=calibration, validation=validation, lens_position=None,
        focus_locked_at=None, exposure_us=None, analogue_gain=None, flags=[],
    )
    def tray(tid: int, at: tuple[float, float], in_slot: str | None, main: bool) -> dict:
        # The outline and cells lie around `at`: shifted from the tray at (250, 280).
        dx, dy = at[0] - 250, at[1] - 280
        shift = lambda points: [[x + dx, y + dy] for x, y in points]
        cells = [{**c, "centre_px": shift([c["centre_px"]])[0], "corners_px": shift(c["corners_px"])} for c in [
            _cell("A1", "tag", 130, 430, None), _cell("B1", "plant", 370, 430, 250.0),
            _cell("A2", "plant", 130, 130, 250.0), _cell("B2", "plant", 370, 130, 250.0)]]
        return {
            "tray_id": tid, "slot": in_slot, "a1_corner": "SW", "placement": placement if main else "placed",
            "centre_px": list(at), "tilt_deg": tilt_deg if main else 0.0, "margin_mm": None, "found": "photo + tag",
            "warnings": (warnings or []) if main else [], "outline_px": shift(OUTLINE), "area_mm2": area,
            "segmenter": "green threshold, 0.1",
            **({} if grown_area is None or not main else {"grown_method": "grow from leaf cores", "grown_area_mm2": grown_area}),
            "cells": cells,
        }

    database.record_tray_readings(capture_id, read_at=taken.isoformat(), status="read", trays=[
        tray(tray_id, centre, slot, True), *(tray(t, c, s, False) for t, c, s in others)])
    database.record_exclusions([{"capture_id": capture_id, "name": exclusion, "norm_e": None, "limit_fraction": None}],
                               worked_out_at=taken.isoformat())
    return capture_id


@pytest.fixture
def experiment() -> int:
    e = database.create_experiment(uuid="u-64", created_at=START.isoformat())
    database.start_experiment(e["id"], now=START.isoformat(), folder="experiments/x")
    return e["id"]


def test_each_hour_gives_its_first_usable_photo_and_counts_the_hours_without_one(experiment):
    m = timedelta(minutes=1)
    h = timedelta(hours=1)
    _photo(experiment, START, exclusion="light changing")
    first_good = _photo(experiment, START + m)
    _photo(experiment, START + 2 * m)
    # Hour 2: the tray's tag was seen but the tray was not: no frame, counted as skipped.
    _photo(experiment, START + h, warnings=["tag seen, tray not found in the photo"])
    # Hour 3: the lights were off. Night is not a skipped step.
    _photo(experiment, START + 2 * h, exclusion="lights off")
    _photo(experiment, START + 2 * h + m, exclusion="lights off")
    last_good = _photo(experiment, START + 3 * h + 30 * m)

    chosen = timelapse.choose_frames(experiment, tray_id=4, start=START, end=START + 4 * h, per_hour=1)

    assert [f["capture"]["id"] for f in chosen["frames"]] == [first_good, last_good]
    assert chosen["skipped"] == 1


def test_two_frames_an_hour_take_one_photo_from_each_half_hour_inside_the_range_only(experiment):
    m = timedelta(minutes=1)
    _photo(experiment, START - m)  # before the range
    early = _photo(experiment, START + 5 * m)
    _photo(experiment, START + 20 * m)
    late = _photo(experiment, START + 31 * m)
    _photo(experiment, START + 60 * m)  # the end of the range is not in it

    chosen = timelapse.choose_frames(experiment, tray_id=4, start=START, end=START + 60 * m, per_hour=2)

    assert [f["capture"]["id"] for f in chosen["frames"]] == [early, late]
    assert chosen["skipped"] == 0


def _only_frame(experiment_id: int) -> dict:
    return timelapse.choose_frames(experiment_id, tray_id=4, start=START, end=START + timedelta(days=60), per_hour=1)["frames"][0]


def test_a_frame_says_utc_and_chamber_time_the_day_and_the_area_with_its_band(experiment):
    banded_validation("20270301T000000000000", {"North 1": ((250, 280), 2.0)})
    # 29 March 2027 is in summer time: the chamber is at UTC+2. Day 1 is the first 24 h.
    _photo(experiment, datetime(2027, 3, 29, 10, 0, tzinfo=timezone.utc), grown_area=1234.6,
           validation="20270301T000000000000")

    values = timelapse.frame_values(database.get_experiment(experiment), _only_frame(experiment), method="grown")

    assert values["utc"] == "2027-03-29 10:00 UTC"
    assert values["chamber"] == "12:00 chamber time"
    assert values["day"] == 29
    assert values["method"] == "Grow from leaf cores"
    assert values["area"] == "1,235 mm²"
    assert values["band"] == "±2.0%, North 1"


def test_a_frame_with_no_band_or_no_area_says_why_in_words(experiment):
    # 1 March 2027 is in winter time: UTC+1.
    _photo(experiment, START + timedelta(minutes=1), area=80.0)
    frame = _only_frame(experiment)

    fixed = timelapse.frame_values(database.get_experiment(experiment), frame, method="fixed")
    grown = timelapse.frame_values(database.get_experiment(experiment), frame, method="grown")

    assert fixed["chamber"] == "11:01 chamber time"
    assert fixed["day"] == 1
    assert fixed["area"] == "under 100 mm²"  # the fixed cutoff's floor (#288)
    assert fixed["band"] == "not validated"
    assert grown["area"] == "not worked out"


def test_a_drawn_frame_shows_the_tray_upright_with_cell_a1_at_the_bottom_left(experiment):
    turned_tray_photo(experiment, START)
    frame = _only_frame(experiment)
    values = timelapse.frame_values(database.get_experiment(experiment), frame, method="fixed")

    image = timelapse.draw_frame(frame, values)

    # The tray at 2 px/mm (610 x 732 px), the label under it.
    assert image.width == 610 and image.height > 732
    r, g, b = image.getpixel((76, 659))  # the centre of cell A1, bottom left
    assert r > 200 and g < 60 and b < 60
    r, g, b = image.getpixel((534, 73))  # the centre of cell D5, top right
    assert b > 200 and r < 60 and g < 60


def test_with_a_mask_overlay_a_photo_without_that_mask_is_skipped_and_counted(experiment):
    import numpy as np

    from npec_rig import segmentation

    h = timedelta(hours=1)
    with_mask = _photo(experiment, START)
    _photo(experiment, START + h)  # no mask saved for this one
    mask = np.zeros((500, 500), dtype=bool)
    path = database.captures_for_experiment(experiment)[0]["path"]
    segmentation.save_mask(path, mask, segmentation.GROWN_MASK)

    grown = timelapse.choose_frames(experiment, tray_id=4, start=START, end=START + 2 * h, per_hour=1, mask="grown")
    fixed = timelapse.choose_frames(experiment, tray_id=4, start=START, end=START + 2 * h, per_hour=1, mask="fixed")

    assert [f["capture"]["id"] for f in grown["frames"]] == [with_mask]
    assert grown["skipped"] == 1
    assert fixed["frames"] == [] and fixed["skipped"] == 2  # no fixed cutoff mask on either photo


def test_a_frame_with_a_mask_shows_its_edge_in_magenta_and_tints_only_inside_it(experiment):
    import numpy as np

    from npec_rig import segmentation

    turned_tray_photo(experiment, START)
    path = database.captures_for_experiment(experiment)[0]["path"]
    mask = np.zeros((1000, 1000), dtype=bool)
    mask[300:500, 300:500] = True  # photo pixels; the tray lies turned, so upright x 210 to 410, y 332 to 532
    segmentation.save_mask(path, mask)
    frame = timelapse.choose_frames(experiment, tray_id=4, start=START, end=START + timedelta(hours=1),
                                    per_hour=1, mask="fixed")["frames"][0]
    values = timelapse.frame_values(database.get_experiment(experiment), frame, method="fixed")

    image = timelapse.draw_frame(frame, values, mask="fixed")

    edge = [image.getpixel((x, 432)) for x in range(206, 215)]
    assert any(r > 220 and g < 40 and b > 220 for r, g, b in edge)  # magenta edge
    r, g, b = image.getpixel((310, 432))  # inside: grey 128 tinted toward magenta
    assert r > 140 and b > 140 and g < 115
    r, g, b = image.getpixel((150, 200))  # outside the mask: the grey photo
    assert abs(r - 128) < 12 and abs(g - 128) < 12 and abs(b - 128) < 12


def test_a_cell_frame_gives_its_area_or_its_status_word_and_the_slot_band(experiment):
    banded_validation("20270301T000000000000", {"North 1": ((250, 280), 2.0)})
    _photo(experiment, START, validation="20270301T000000000000")
    frame = _only_frame(experiment)
    experiment_row = database.get_experiment(experiment)

    plant = timelapse.frame_values(experiment_row, frame, method="fixed", cell="B1")
    tag = timelapse.frame_values(experiment_row, frame, method="fixed", cell="A1")
    grown = timelapse.frame_values(experiment_row, frame, method="grown", cell="B1")

    assert plant["cell"] == "B1"
    assert plant["area"] == "250 mm²"
    assert plant["band"] == "±2.0%, North 1"
    assert plant["band_label"] == "Slot band, flat objects at tray-top height"
    assert tag["area"] == "Tag"
    assert grown["area"] == "not worked out"  # grow from leaf cores was not run on this photo


def test_a_cell_frame_shows_that_cell_upright_in_the_middle_with_half_a_cell_around_it(experiment):
    turned_tray_photo(experiment, START)
    frame = _only_frame(experiment)
    experiment_row = database.get_experiment(experiment)

    a1 = timelapse.draw_frame(frame, timelapse.frame_values(experiment_row, frame, method="fixed", cell="A1"), cell="A1")
    d5 = timelapse.draw_frame(frame, timelapse.frame_values(experiment_row, frame, method="fixed", cell="D5"), cell="D5")

    # The cell's opening 300 px across, 150 px around it: 600 px wide, the cell's centre at 300, 300.
    assert a1.width == 600 and a1.height > 600
    r, g, b = a1.getpixel((300, 300))
    assert r > 200 and g < 60 and b < 60  # A1's red patch
    r, g, b = d5.getpixel((300, 300))
    assert b > 200 and r < 60 and g < 60  # D5's blue patch


def test_a_video_that_would_leave_five_days_of_disk_or_fewer_is_refused_with_the_days_left(tmp_path):
    import time

    from npec_rig import health

    # 10 MB written in the data folder in the last day: about 10 MB a day.
    (health.db_path().parent / "photos-today.bin").write_bytes(b"\0" * 10_000_000)
    mb = 1_000_000

    refused = timelapse.disk_refusal(60 * mb, 100 * mb, time.time())  # leaves 40 MB, about 4 days
    allowed = timelapse.disk_refusal(10 * mb, 100 * mb, time.time())  # leaves 90 MB, about 9 days

    assert refused is not None and "4 days" in refused
    assert allowed is None



def _two_slot_table() -> None:
    """Calibration TABLE_STEM with two slots: South 2 centred at (150, 450), North 4 at (750, 150)."""
    from npec_rig import validation_store
    from tests.helpers import TABLE_STEM, table_calibration

    table_calibration()
    validation_store.save_slot_layout(TABLE_STEM, [
        {"name": "South 2", "centre": [150, 450], "box": [50, 350, 250, 550]},
        {"name": "North 4", "centre": [750, 150], "box": [650, 50, 850, 250]},
    ], [])


def test_a_frame_names_its_slot_and_the_last_different_slot_from_the_whole_experiment(experiment):
    from tests.helpers import TABLE_STEM

    _two_slot_table()
    h = timedelta(hours=1)
    _photo(experiment, START, calibration=TABLE_STEM, centre=(160, 440))  # South 2
    _photo(experiment, START + h, calibration=TABLE_STEM, centre=(740, 160))  # North 4
    _photo(experiment, START + 2 * h, calibration=TABLE_STEM, centre=(745, 155))  # North 4 still
    experiment_row = database.get_experiment(experiment)

    # The video starts after the move: the earlier slot still comes from the whole experiment.
    frames = timelapse.choose_frames(experiment, tray_id=4, start=START + h, end=START + 3 * h, per_hour=1)["frames"]
    first_of_all = timelapse.choose_frames(experiment, tray_id=4, start=START, end=START + h, per_hour=1)["frames"][0]

    assert [timelapse.frame_values(experiment_row, f, method="fixed")["slot"] for f in frames] == [
        "North 4 (was South 2)", "North 4 (was South 2)"]
    assert timelapse.frame_values(experiment_row, first_of_all, method="fixed")["slot"] == "South 2"



def test_a_frame_gives_its_warnings_in_words_and_soil_hidden_only_for_grow_from_leaf_cores(experiment):
    from npec_rig import segmentation, tray_readings

    # The tag lay turned on the tray in this photo, and grow from leaf cores found the soil hidden.
    _photo(experiment, START, warnings=[tray_readings.TAG_TURNED, segmentation.SOIL_HIDDEN], grown_area=900.0)
    frame = _only_frame(experiment)
    experiment_row = database.get_experiment(experiment)

    fixed = timelapse.frame_values(experiment_row, frame, method="fixed")["warnings"]
    grown = timelapse.frame_values(experiment_row, frame, method="grown")["warnings"]

    assert fixed == ["names may be swapped since 2027-03-01 10:00 UTC"]
    assert grown == ["names may be swapped since 2027-03-01 10:00 UTC", "soil hidden: usual leaf cutoff used"]



def test_a_frame_after_photos_that_could_not_be_used_says_how_long_the_lit_gap_was(experiment):
    h, m = timedelta(hours=1), timedelta(minutes=1)
    bad = ["tag seen, tray not found in the photo"]
    _photo(experiment, START)
    _photo(experiment, START + h, warnings=bad)
    _photo(experiment, START + 2 * h, exclusion="lights off")  # night: not a gap
    _photo(experiment, START + 3 * h, warnings=bad)
    _photo(experiment, START + 4 * h)
    _photo(experiment, START + 4 * h + 12 * m, warnings=bad)
    _photo(experiment, START + 4 * h + 24 * m)
    experiment_row = database.get_experiment(experiment)

    hourly = timelapse.choose_frames(experiment, tray_id=4, start=START, end=START + 5 * h, per_hour=1)["frames"]
    fifths = timelapse.choose_frames(experiment, tray_id=4, start=START + 4 * h, end=START + 5 * h, per_hour=5)["frames"]
    words = lambda f: timelapse.frame_values(experiment_row, f, method="fixed")["warnings"]

    assert [f["gap_minutes"] for f in hourly] == [0, 120]
    assert words(hourly[0]) == []
    assert words(hourly[1]) == ["gap: 2 h without a usable photo"]
    assert words(fifths[1]) == ["gap: 12 min without a usable photo"]



def _map_at(image, x: float, y: float) -> tuple[int, int, int]:
    """The map pixel of photo point (x, y) on TABLE_STEM's table: corner tags at x 100 to 800 and
    y 100 to 500 (700 x 400 px), drawn 200 px wide, so 200 / 700 map px per photo px."""
    k = 200 / 700
    return image.getpixel((int((x - 100) * k), int((y - 100) * k)))


BLUE = lambda c: c[2] > 200 and c[0] < 90  # the video's tray
PALE = lambda c: c[2] > c[0] + 15 and c[0] > 110  # its last different slot
GREY = lambda c: abs(c[0] - c[1]) < 12 and abs(c[1] - c[2]) < 12 and 130 < c[0] < 215  # another tray
EMPTY = lambda c: min(c) > 225  # the table, nothing on it


def test_the_map_draws_each_tray_at_the_median_of_its_stay_all_trays_one_size(experiment):
    from tests.helpers import TABLE_STEM, table_calibration

    # 0.4 px/mm: a tray (305 x 366 mm) is 122 x 146 px, on the map about 35 x 42 px.
    table_calibration(px_per_mm=0.4)
    h = timedelta(hours=1)
    for i, x in enumerate((500, 460, 540)):  # one stay of tray 4 in North 1; its median x is 500
        _photo(experiment, START + i * h, calibration=TABLE_STEM, centre=(x, 300), slot="North 1",
               others=((7, (250, 300), "North 0"),))
    frames = timelapse.choose_frames(experiment, tray_id=4, start=START, end=START + 3 * h, per_hour=1)["frames"]

    image = timelapse.draw_map(frames[1])  # the photo with tray 4 at x 460

    # Drawn at the median, x 439 to 561, not at 460 (x 399 to 521).
    assert EMPTY(_map_at(image, 418, 300))
    assert BLUE(_map_at(image, 450, 300))
    assert GREY(_map_at(image, 250, 300))  # tray 7, also seen in this photo
    row = [image.getpixel((x, int(200 * 200 / 700))) for x in range(image.width)]
    blue, grey = sum(map(BLUE, row)), sum(map(GREY, row))
    assert abs(blue - grey) <= 2 and 30 <= blue <= 40  # one size: 305 mm is about 35 map px
    # The tag's corner: the cell holding the tag lies to the lower left, so the square is there.
    assert max(_map_at(image, 439 + 8, 373 - 8)) < 90


def test_the_map_jumps_only_when_the_slot_changes_and_shows_the_last_slot_and_only_trays_seen(experiment):
    from tests.helpers import TABLE_STEM, table_calibration

    table_calibration(px_per_mm=0.4)
    h = timedelta(hours=1)
    _photo(experiment, START, calibration=TABLE_STEM, centre=(250, 250), slot="North 1",
           others=((9, (400, 420), "South 2"),))  # tray 9 is seen in this photo only
    _photo(experiment, START + h, calibration=TABLE_STEM, centre=(270, 250), slot="North 1")
    _photo(experiment, START + 2 * h, calibration=TABLE_STEM, centre=(550, 250), slot="North 2")
    _photo(experiment, START + 3 * h, calibration=TABLE_STEM, centre=(570, 250), slot="North 2")
    frames = timelapse.choose_frames(experiment, tray_id=4, start=START, end=START + 4 * h, per_hour=1)["frames"]

    before, after = timelapse.draw_map(frames[1]), timelapse.draw_map(frames[3])

    # In North 1 the tray is at the median of 250 and 270; after the move, of 550 and 570.
    assert BLUE(_map_at(before, 260, 250)) and not BLUE(_map_at(before, 560, 250))
    assert BLUE(_map_at(after, 560, 250))
    assert PALE(_map_at(after, 260, 250))  # where it was before the move
    assert GREY(_map_at(timelapse.draw_map(frames[0]), 400, 420))  # tray 9, seen in the first photo
    assert EMPTY(_map_at(after, 400, 420))  # and not drawn where it was not seen


def test_the_size_estimate_of_all_trays_covers_every_tray_in_the_zip(experiment):
    _photo(experiment, START, tray_id=4)
    _photo(experiment, START + timedelta(minutes=1), tray_id=7)
    request = {"experiment_id": experiment, "tray_id": "all", "start": START.isoformat(),
               "end": (START + timedelta(hours=3)).isoformat(), "per_hour": 1, "method": "fixed"}

    # 2 trays, 3 frames each, at the trial's 42,984 bytes a frame.
    assert timelapse.estimate_bytes(request) == 2 * 3 * 42_984



def test_the_map_draws_trays_square_to_the_table_with_the_tag_at_the_nearest_corner(experiment):
    from tests.helpers import TABLE_STEM, table_calibration

    table_calibration(px_per_mm=0.4)
    # Stored 30 degrees turned: drawn square to the table, 122 x 146 px about (500, 300).
    _photo(experiment, START, calibration=TABLE_STEM, centre=(500, 300), slot="North 1", tilt_deg=30.0)
    frame = timelapse.choose_frames(experiment, tray_id=4, start=START, end=START + timedelta(hours=1), per_hour=1)["frames"][0]

    image = timelapse.draw_map(frame)

    # Both upper corners of the square rectangle are filled; a 30 degree turn would leave one empty.
    assert BLUE(_map_at(image, 439 + 4, 227 + 4)) and BLUE(_map_at(image, 561 - 4, 227 + 4))
    assert EMPTY(_map_at(image, 439 - 6, 300))  # nothing past its left side
    # The tag cell lies to the lower left: the square snaps to the lower left corner.
    assert max(_map_at(image, 439 + 8, 373 - 8)) < 90


def test_the_old_slot_fades_over_24_frames_after_a_move_and_is_then_not_drawn(experiment):
    from tests.helpers import TABLE_STEM, table_calibration

    table_calibration(px_per_mm=0.4)
    step = timedelta(minutes=12)  # 5 frames an hour
    for i in range(2):
        _photo(experiment, START + i * step, calibration=TABLE_STEM, centre=(250, 250), slot="North 1")
    for i in range(2, 2 + 25):
        _photo(experiment, START + i * step, calibration=TABLE_STEM, centre=(560, 250), slot="North 2")
    frames = timelapse.choose_frames(experiment, tray_id=4, start=START, end=START + 27 * step, per_hour=5)["frames"]
    old = lambda n: _map_at(timelapse.draw_map(frames[2 + n]), 250, 250)  # n frames after the move

    # Pale blue (150, 175, 215) fading into the table (245, 245, 245): full, halfway, gone.
    assert all(abs(a - b) <= 2 for a, b in zip(old(0), (150, 175, 215)))
    assert all(abs(a - b) <= 2 for a, b in zip(old(12), (197.5, 210, 230)))
    assert old(24) == (245, 245, 245)


def test_a_tray_cut_off_by_the_photo_edge_keeps_its_frame_and_says_partly_outside_the_photo(experiment):
    # The Gallery's words for a tray whose outline reaches the photo edge (its PARTLY OUTSIDE label).
    _photo(experiment, START, warnings=["partly outside the photo"])

    frame = _only_frame(experiment)  # a frame was made: the tray is not skipped
    words = timelapse.frame_values(database.get_experiment(experiment), frame, method="fixed")["warnings"]

    assert words == ["partly outside the photo"]


def test_a_frame_says_grown_area_not_worked_out_for_grow_from_leaf_cores_only(experiment):
    # Photos read before grow from leaf cores was run carry this word (#483).
    _photo(experiment, START, warnings=["grown area not worked out"])
    frame = _only_frame(experiment)
    experiment_row = database.get_experiment(experiment)

    fixed = timelapse.frame_values(experiment_row, frame, method="fixed")["warnings"]
    grown = timelapse.frame_values(experiment_row, frame, method="grown")["warnings"]

    assert fixed == []
    assert grown == ["grown area not worked out"]


def test_a_frame_names_the_validation_slot_that_sets_its_band_not_another_slot(experiment):
    from tests.helpers import TABLE_STEM

    _two_slot_table()  # the calibration's layout: this tray at (160, 440) is nearest South 2
    # The validation's own slots, centred by hand: here the nearest to the tray is "North 1".
    banded_validation("20270301T000000000000", {"North 1": ((170, 430), 2.0), "North 2": ((700, 100), 3.0)})
    _photo(experiment, START, calibration=TABLE_STEM, validation="20270301T000000000000", centre=(160, 440))

    values = timelapse.frame_values(database.get_experiment(experiment), _only_frame(experiment), method="fixed")

    assert values["band"] == "±2.0%, North 1"
    assert values["slot"] == "North 1"
