"""Light exclusions (#288): which photos' plant areas are left out because of the light, from each
photo's exposure and gain (metrology log 17.7 and 17.8).

The worked examples are hourly photos with exposure times gain (E) chosen by hand, so the norm,
the limit and each answer can be read off without the code. The real stretches are photos of
experiment 18 copied from `docs/figures/17.8/light-e18.csv`.
"""

import csv
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from npec_rig import captures, database, exclusions
from tests.helpers import record_light_photos

pytestmark = pytest.mark.unit

EXPERIMENT_18 = Path(__file__).parent.parent / "docs" / "figures" / "17.8" / "light-e18.csv"

START = datetime.fromisoformat("2026-10-22T08:00:00+00:00")


def _photos(*es: float, every: timedelta = timedelta(hours=1)) -> list[dict]:
    """Photos `every` apart from START, each with exposure E (us) at gain 1.0."""
    return [
        {"taken_at": (START + i * every).isoformat(), "exposure_us": e, "analogue_gain": 1.0}
        for i, e in enumerate(es)
    ]


def test_a_photo_at_the_cameras_ceiling_is_lights_off() -> None:
    """Real photos of experiment 18 (17.7): 64,022 us at gain 4.0 with the lights off, 5,404 us at
    gain 1.0 lit."""
    photos = [
        {"taken_at": "2026-10-22T23:28:53+00:00", "exposure_us": 64_022, "analogue_gain": 4.0},
        {"taken_at": "2026-10-23T08:41:20+00:00", "exposure_us": 5_404, "analogue_gain": 1.0},
    ]
    assert exclusions.light_exclusions(photos)["exclusions"] == ["lights off", None]


FIRST_DAY = [5000] * 24
FIRST_DAY[5] = 5300  # +6%: the first day's largest steady swing
FIRST_DAY[7] = 4850  # -3%


def test_the_norm_and_limit_come_from_the_first_full_day_and_wait_for_it() -> None:
    """Hourly photos, no lights off: the norm is the median, 5,000; the largest swing is 5,300,
    +6%, so the limit is 3 x 6% = 18% (Aaron, 2026-10-26). Before a photo 24 hours after the
    first, there is no norm yet."""
    pending = exclusions.light_exclusions(_photos(*FIRST_DAY))
    assert (pending["norm"], pending["limit"]) == (None, None)

    ready = exclusions.light_exclusions(_photos(*FIRST_DAY, 5000))
    assert ready["norm"] == 5000
    assert ready["limit"] == pytest.approx(0.18)


def test_a_short_dip_that_returns_to_the_norm_is_light_disturbed_and_one_within_the_limit_is_kept() -> None:
    """After the first day (norm 5,000, limit 18%): two photos at 4,000 (-20%), then back to
    5,000, are 3 photos or fewer that return, so "light disturbed" (Aaron, 2026-10-26); 4,500
    (-10%) is within the limit and kept."""
    result = exclusions.light_exclusions(_photos(*FIRST_DAY, 5000, 4000, 4000, 5000, 4500))
    assert result["exclusions"][24:] == [None, "light disturbed", "light disturbed", None, None]


def _experiment_18() -> dict[str, str | None]:
    """Each photo of experiment 18 up to 26 October 15:01 UTC, by time to the second, with its
    exclusion."""
    with open(EXPERIMENT_18) as f:
        photos = [{"taken_at": r["taken_at"], "exposure_us": float(r["exposure_us"]), "analogue_gain": float(r["analogue_gain"])}
                  for r in csv.DictReader(f)]
    result = exclusions.light_exclusions(photos)
    return {p["taken_at"][:19]: name for p, name in zip(photos, result["exclusions"])}


def test_a_fade_into_lights_off_is_light_changing() -> None:
    """The fade of 22 October in experiment 18 (17.8): at 23:27:53 E is 101,750, 19 times the
    norm, one photo before lights off, so "light changing", not off norm. At 23:03:53 E is 5,716,
    9% over the norm and inside its limit of about 21%, so kept; 22:30:53 is steady."""
    photo = _experiment_18()
    assert photo["2026-10-22T23:27:53"] == "light changing"
    assert photo["2026-10-22T23:03:53"] is None
    assert photo["2026-10-22T22:30:53"] is None


def test_a_long_steady_stretch_away_from_the_norm_is_light_off_norm() -> None:
    """Five hours at 4,000 (-20%, limit 18%), steady, then back: more than 3 photos, so "light off
    norm", which counts toward the warning (#288 part 2)."""
    result = exclusions.light_exclusions(_photos(*FIRST_DAY, 5000, 4000, 4000, 4000, 4000, 4000, 5000))
    assert result["exclusions"][25:31] == ["light off norm"] * 5 + [None]


def test_a_ramp_away_from_lights_off_is_light_changing() -> None:
    """A ramp down and up again: 4,000, 3,500, 3,000, 3,500, 4,000. Each step is 12% to 17%,
    more than the first day's largest step (5,000 to 5,300, 6%), so the light keeps moving:
    "light changing", no warning (Aaron, 2026-10-26: a normal ramp sets off no alarm)."""
    result = exclusions.light_exclusions(_photos(*FIRST_DAY, 5000, 4000, 3500, 3000, 3500, 4000, 5000))
    assert result["exclusions"][25:31] == ["light changing"] * 5 + [None]


def test_people_at_the_table_do_not_move_the_light_past_the_limit() -> None:
    """Shuffle 1, 23 October 08:43 to 08:56 UTC (17.8): E 8% to 11% low, inside the limit of
    about 21%. No light exclusion: visits are left to the visits rule (#288 part 3)."""
    photo = _experiment_18()
    shuffle = [name for t, name in photo.items() if "2026-10-23T08:43" <= t <= "2026-10-23T08:56"]
    assert len(shuffle) == 13
    assert shuffle == [None] * 13


def test_photos_taken_for_calibration_or_validation_are_left_out() -> None:
    """Review of #299: a validation photo at 9,000 (+80%, sheets on the table) in the first day
    leaves the norm at 5,000 and the limit at 18%, as without it, and gets no exclusion: only
    the experiment's own photos count, as in Reprocess and metrology log 17.8."""
    photos = _photos(*FIRST_DAY, 5000)
    validation = {"taken_at": (START + timedelta(hours=3, minutes=30)).isoformat(),
                  "exposure_us": 9000, "analogue_gain": 1.0, "purpose": "validation"}
    photos.insert(4, validation)
    result = exclusions.light_exclusions(photos)
    assert result["norm"] == 5000
    assert result["limit"] == pytest.approx(0.18)
    assert result["exclusions"][4] is None


def test_a_photo_with_no_exposure_is_left_out_and_the_others_are_still_labelled() -> None:
    """Review of #299: exposure 0 (a camera fault, or the synthetic camera) once stopped the
    whole experiment's exclusions. With one in the first day and one after it, the norm stays
    5,000 and the limit 18%, and a later dip of two photos at 4,000 is still light disturbed."""
    day = list(FIRST_DAY)
    day[10] = 0
    result = exclusions.light_exclusions(_photos(*day, 5000, 0, 4000, 4000, 5000))
    assert result["norm"] == 5000
    assert result["limit"] == pytest.approx(0.18)
    assert result["exclusions"][24:] == [None, None, "light disturbed", "light disturbed", None]


# --- The light warning (#288 part 2 PR 2) ----------------------------------------------------------
# More than 2 hours of "light off norm" within 24 hours raises it; the time of a stretch runs from
# its first photo to the photo after it (Aaron, 2026-10-27).


def _experiment(*series: tuple[timedelta, float]) -> int:
    """An experiment with photos at START plus each offset (`record_light_photos`); its id."""
    experiment_id = captures.create_experiment(name="Light")["id"]
    record_light_photos(experiment_id, START, series, f"light-{experiment_id}")
    return experiment_id


def _first_day() -> list[tuple[timedelta, float]]:
    """FIRST_DAY hourly, then one photo on the norm at 24 h: norm 5,000, limit 18%."""
    return [(timedelta(hours=h), e) for h, e in enumerate([*FIRST_DAY, 5000])]


def _off(start_h: float, photos: int, every_min: int) -> list[tuple[timedelta, float]]:
    """`photos` at 4,000 (-20%, off norm) `every_min` apart from `start_h`, then one back at
    5,000."""
    times = [timedelta(hours=start_h) + timedelta(minutes=every_min * i) for i in range(photos + 1)]
    return [(t, 4000) for t in times[:-1]] + [(times[-1], 5000)]


def test_more_than_2_hours_off_norm_raises_the_warning_and_2_hours_does_not() -> None:
    """4 photos at 4,000, 30 minutes apart, from 25 h: 25:00 to the photo back at 27:00 is 2.0
    hours, no warning. 5 photos: 25:00 to 27:30, 2.5 hours, a warning."""
    assert exclusions.light_warning(_experiment(*_first_day(), *_off(25, 4, 30))) is None

    warning = exclusions.light_warning(_experiment(*_first_day(), *_off(25, 5, 30)))
    assert warning == {
        "hours": 2.5,
        "first": (START + timedelta(hours=25)).isoformat(),
        "last": (START + timedelta(hours=27, minutes=30)).isoformat(),
    }


def test_two_short_stretches_count_together_only_within_24_hours() -> None:
    """Two stretches of 1.5 hours (6 photos 15 minutes apart, then back): from 25 h and 30 h they
    add to 3.0 hours within 24 hours, a warning from 25:00 to 31:30; from 25 h and 50 h they are
    25 hours apart, no warning."""
    near = _experiment(*_first_day(), *_off(25, 6, 15), *_off(30, 6, 15))
    assert exclusions.light_warning(near) == {
        "hours": 3.0,
        "first": (START + timedelta(hours=25)).isoformat(),
        "last": (START + timedelta(hours=31, minutes=30)).isoformat(),
    }
    assert exclusions.light_warning(_experiment(*_first_day(), *_off(25, 6, 15), *_off(50, 6, 15))) is None


def test_dismissing_hides_the_warning_until_a_new_stretch_raises_it() -> None:
    """2.5 hours from 25 h raise the warning; dismissed, it is gone. A new 2.5 hours from 40 h,
    photos taken after the dismissal, raise it again for those hours only."""
    series = [*_first_day(), *_off(25, 5, 30)]
    experiment_id = _experiment(*series)
    exclusions.dismiss_light_warning(
        experiment_id, now="2026-10-23T12:00:00+00:00", until=exclusions.light_warning(experiment_id)["last"]
    )
    assert exclusions.light_warning(experiment_id) is None

    record_light_photos(experiment_id, START, _off(40, 5, 30), f"later-{experiment_id}")
    assert exclusions.light_warning(experiment_id) == {
        "hours": 2.5,
        "first": (START + timedelta(hours=40)).isoformat(),
        "last": (START + timedelta(hours=42, minutes=30)).isoformat(),
    }


def test_dismissing_covers_only_the_warning_the_researcher_saw() -> None:
    """Review of #300: the warning shown ends at 27:30; a new 2.5 hours from 40 h arrive before
    Dismiss is tapped. Dismissing what was seen leaves the new stretch raising the warning."""
    experiment_id = _experiment(*_first_day(), *_off(25, 5, 30))
    seen = exclusions.light_warning(experiment_id)
    record_light_photos(experiment_id, START, _off(40, 5, 30), f"later-{experiment_id}")

    exclusions.dismiss_light_warning(experiment_id, now="2026-10-24T12:00:00+00:00", until=seen["last"])

    assert exclusions.light_warning(experiment_id) == {
        "hours": 2.5,
        "first": (START + timedelta(hours=40)).isoformat(),
        "last": (START + timedelta(hours=42, minutes=30)).isoformat(),
    }


def test_hours_after_a_dismissal_count_again_while_the_stretch_goes_on() -> None:
    """Review of #300: 6 photos at 4,000, 30 minutes apart from 25 h, the light not back yet:
    2.5 hours to the newest photo at 27:30, a warning. Dismissed, then the stretch goes on with
    5 more photos to 30:00: 27:30 to 30:00, 2.5 hours, raise it again."""
    off = [(timedelta(hours=25, minutes=30 * i), 4000) for i in range(6)]
    experiment_id = _experiment(*_first_day(), *off)
    seen = exclusions.light_warning(experiment_id)
    assert seen["last"] == (START + timedelta(hours=27, minutes=30)).isoformat()
    exclusions.dismiss_light_warning(experiment_id, now="2026-10-23T12:00:00+00:00", until=seen["last"])

    more = [(timedelta(hours=28, minutes=30 * i), 4000) for i in range(5)]
    record_light_photos(experiment_id, START, more, f"later-{experiment_id}")
    assert exclusions.light_warning(experiment_id) == {
        "hours": 2.5,
        "first": (START + timedelta(hours=27, minutes=30)).isoformat(),
        "last": (START + timedelta(hours=30)).isoformat(),
    }


def test_a_pause_after_photos_off_norm_counts_one_usual_gap_not_the_pause() -> None:
    """Review of #300: 4 photos at 4,000, 10 minutes apart from 25 h, then a pause to 40 h. The
    usual gap is 1 hour (the first day), so the last photo counts 1 hour, not 14.5: 10 + 10 + 10
    + 60 minutes, 1.5 hours, no warning. Before, 25:00 to 40:00 read as 15 hours."""
    off = [(timedelta(hours=25, minutes=10 * i), 4000) for i in range(4)]
    experiment_id = _experiment(*_first_day(), *off, (timedelta(hours=40), 5000))
    assert exclusions.light_warning(experiment_id) is None


# --- Visits (#288 part 2 PR 3, metrology log 17.9) -------------------------------------------------


def _areas(*rows: dict[int, float]) -> list[dict]:
    """Photos a minute apart from START, each with its trays' areas (mm2)."""
    return [{"taken_at": (START + timedelta(minutes=i)).isoformat(), "areas": areas} for i, areas in enumerate(rows)]


def test_a_jump_of_more_than_250_mm2_and_2_times_is_a_visit_up_or_down() -> None:
    """Tray 1 steady at 100 mm2 and tray 2 at 600 for 10 photos (the usual level), then:
    tray 1 at 400 (+300, 4 times): a visit; tray 1 at 340 (+240): not; tray 2 at 250 (-350,
    0.42 times): a visit; tray 2 at 1,000 (+400, 1.67 times): not (17.9). The two visits are 5
    photos apart, so the photos between them are not filled in."""
    steady = [{1: 100, 2: 600}] * 10
    result = exclusions.visits(_areas(*steady, {1: 400, 2: 600}, {1: 100, 2: 600}, {1: 340, 2: 600},
                                      {1: 100, 2: 600}, {1: 100, 2: 600}, {1: 100, 2: 250},
                                      {1: 100, 2: 600}, {1: 100, 2: 1000}))
    assert result == [False] * 10 + [True, False, False, False, False, True, False, False]


def test_photos_between_two_visits_at_most_4_photos_apart_are_visits_too() -> None:
    """Tray 1 steady at 100 mm2, then 400 (a visit), 3 photos back at 100, 400 again: 4 photos
    apart, so the 3 between are visits too, as in the tray move of 26 October (17.9). Then 4
    photos at 100 and 400 once more: 5 apart, not filled."""
    steady = [{1: 100}] * 10
    spike, back = {1: 400}, {1: 100}
    result = exclusions.visits(_areas(*steady, spike, back, back, back, spike, back, back, back, back, spike))
    assert result == [False] * 10 + [True] * 5 + [False] * 4 + [True]


def test_a_visit_is_stored_and_a_light_exclusion_wins() -> None:
    """An experiment of 12 photos a minute apart, tray 1 read at 100 mm2 in the first 10, then
    400 (+300, 4 times) lit: stored as "visit"; then 400 again with the lights off (E 256,000):
    stored as "lights off", which wins (17.9)."""
    experiment_id = captures.create_experiment(name="Visit")["id"]
    series = [(timedelta(minutes=i), 5000) for i in range(11)] + [(timedelta(minutes=11), 256_000)]
    record_light_photos(experiment_id, START, series, f"visit-{experiment_id}")
    photos = database.captures_for_experiment(experiment_id)
    for photo, area in zip(photos, [100] * 10 + [400, 400]):
        database.record_tray_readings(photo["id"], read_at=START.isoformat(), status="read", trays=[{
            "tray_id": 1, "slot": "North 1", "a1_corner": "SW", "placement": "placed", "centre_px": [0, 0],
            "tilt_deg": 0, "margin_mm": 50, "area_mm2": area,
        }])

    exclusions.update(photos[-1])

    assert [database.exclusion(p["id"])["name"] for p in photos[9:]] == [None, "visit", "lights off"]


def test_photos_with_a_light_exclusion_do_not_set_the_usual_level() -> None:
    """10 lit photos with tray 1 at 100 mm2, then 10 with the lights off reading 2,000 (light on
    the tray changes the green area), then lit at 100 again. The usual level comes from lit photos
    only, as in the review (17.9), so the last photo is no visit."""
    experiment_id = captures.create_experiment(name="Fade")["id"]
    series = [(timedelta(minutes=i), 5000 if i < 10 or i == 20 else 256_000) for i in range(21)]
    record_light_photos(experiment_id, START, series, f"fade-{experiment_id}")
    photos = database.captures_for_experiment(experiment_id)
    for photo, area in zip(photos, [100] * 10 + [2000] * 10 + [100]):
        database.record_tray_readings(photo["id"], read_at=START.isoformat(), status="read", trays=[{
            "tray_id": 1, "slot": "North 1", "a1_corner": "SW", "placement": "placed", "centre_px": [0, 0],
            "tilt_deg": 0, "margin_mm": 50, "area_mm2": area,
        }])

    exclusions.update(photos[-1])

    assert database.exclusion(photos[-1]["id"])["name"] is None
