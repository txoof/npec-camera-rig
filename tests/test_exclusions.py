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


MINUTE = timedelta(minutes=1)


def test_a_ramp_of_any_length_is_light_changing_with_one_photo_either_side() -> None:
    """N-pad (#382, metrology log 29.2): a photo whose E lies strictly between the photo before
    and the photo after is in a ramp, and so are those two. Short ramp, photos a minute apart:
    5,000 5,000 6,000 7,000 7,000; only 6,000 is between its neighbours, so it and the two around
    it. Long ramp: 3 photos at 5,000, then 40 photos each 100 higher (5,100 to 9,000), then 2 more
    at 9,000. The first 39 rising photos lie between their neighbours; the 40th, 9,000, has 8,900
    before and 9,000 after, so it is not, but it is next to 8,900; the last 5,000 is next to the
    first rise. 41 photos in all."""
    short = exclusions.light_exclusions(_photos(5000, 5000, 6000, 7000, 7000, every=MINUTE))
    assert short["exclusions"] == [None, "light changing", "light changing", "light changing", None]

    rising = [5000 + 100 * i for i in range(1, 41)]
    long = exclusions.light_exclusions(_photos(5000, 5000, 5000, *rising, 9000, 9000, every=MINUTE))
    assert long["exclusions"] == [None, None] + ["light changing"] * 41 + [None, None]


def test_a_scene_step_or_a_daytime_wobble_is_not_light_changing_and_two_steps_are() -> None:
    """A scene change moves E once and it stays: 5,000 5,000 4,800 4,800 4,800, no photo strictly
    between its neighbours, nothing flagged. A wobble, 5,000 4,900 5,000, is not between either.
    Two steps in a row, 5,000 4,900 4,800 4,800: 4,900 is between, so it and its two neighbours
    (a few such photos a day are left out, Aaron, 2026-11-07)."""
    step = exclusions.light_exclusions(_photos(5000, 5000, 4800, 4800, 4800, every=MINUTE))
    assert step["exclusions"] == [None] * 5
    wobble = exclusions.light_exclusions(_photos(5000, 5000, 4900, 5000, 5000, every=MINUTE))
    assert wobble["exclusions"] == [None] * 5
    two = exclusions.light_exclusions(_photos(5000, 5000, 4900, 4800, 4800, every=MINUTE))
    assert two["exclusions"] == [None, "light changing", "light changing", "light changing", None]


def test_lights_off_is_the_cameras_own_searching_state_and_e_of_200000_only_when_none_was_saved() -> None:
    """Development experiment 3, 9 November 07:59 to 08:05 UTC, the start of the ramp up (metrology
    log 29.3): E 265,860 searching at 07:59 and 08:00, 182,763 searching at 08:01, then 66,620,
    41,994, 30,618 and 19,945 converged. The searching photos are lights off; the converged ones
    after them fall every minute, so light changing. A photo the camera reports settled is not
    lights off whatever its E; one saved before the state was recorded (#382) falls back to E of
    200,000 or more (17.7)."""
    def photo(minute: int, e: float, state: str | None) -> dict:
        return {"taken_at": (START + minute * MINUTE).isoformat(), "exposure_us": e, "analogue_gain": 1.0, "ae_state": state}

    ramp_up = [photo(0, 265_860, "searching"), photo(1, 265_860, "searching"), photo(2, 182_763, "searching"),
               photo(3, 66_620, "converged"), photo(4, 41_994, "converged"), photo(5, 30_618, "converged"),
               photo(6, 19_945, "converged")]
    assert exclusions.light_exclusions(ramp_up)["exclusions"] == ["lights off"] * 3 + ["light changing"] * 4

    settled = [photo(0, 250_000, "converged"), photo(1, 250_000, "converged"), photo(2, 250_000, "converged")]
    assert exclusions.light_exclusions(settled)["exclusions"] == [None] * 3
    old = [photo(0, 250_000, None), photo(1, 250_000, None), photo(2, 199_999, None), photo(3, 199_999, None)]
    assert exclusions.light_exclusions(old)["exclusions"] == ["lights off", "lights off", None, None]


def _experiment_18() -> dict[str, str | None]:
    """Each photo of experiment 18 up to 26 October 15:01 UTC, by time to the second, with its
    exclusion."""
    with open(EXPERIMENT_18) as f:
        photos = [{"taken_at": r["taken_at"], "exposure_us": float(r["exposure_us"]), "analogue_gain": float(r["analogue_gain"])}
                  for r in csv.DictReader(f)]
    result = exclusions.light_exclusions(photos)
    return {p["taken_at"][:19]: name for p, name in zip(photos, result["exclusions"])}


def test_the_fade_into_lights_off_of_experiment_18_is_light_changing_from_its_first_photo() -> None:
    """The fade of 22 October (`light-e18.csv`): E is 5,248 up to 23:00:53, then rises every
    minute, 5,404 at 23:01:53 to 101,750 at 23:27:53, and is 256,088 (lights off) at 23:28:53.
    So 23:00:53, the photo before the first rise, to 23:27:53 are light changing: 28 photos."""
    photo = _experiment_18()
    fade = [name for t, name in photo.items() if "2026-10-22T23:00:53" <= t <= "2026-10-22T23:27:53"]
    assert fade == ["light changing"] * 28
    assert photo["2026-10-22T22:59:53"] is None
    assert photo["2026-10-22T23:28:53"] == "lights off"


def test_photos_taken_for_calibration_or_validation_are_left_out() -> None:
    """Review of #299: a validation photo at 9,000 (sheets on the table) between two steady photos
    gets no exclusion and is not a neighbour: only the experiment's own photos count, as in
    Reprocess and metrology log 17.8."""
    photos = _photos(5000, 5000, 5000, every=MINUTE)
    validation = {"taken_at": (START + timedelta(seconds=90)).isoformat(),
                  "exposure_us": 9000, "analogue_gain": 1.0, "purpose": "validation"}
    photos.insert(2, validation)
    assert exclusions.light_exclusions(photos)["exclusions"] == [None] * 4


def test_a_photo_with_no_exposure_is_left_out_and_the_others_are_still_labelled() -> None:
    """Review of #299: exposure 0 (a camera fault, or the synthetic camera) gets no exclusion and
    is not judged as a neighbour; a ramp after it is still found."""
    result = exclusions.light_exclusions(_photos(5000, 0, 5000, 5000, 6000, 7000, 7000, every=MINUTE))
    assert result["exclusions"] == [None, None, None, "light changing", "light changing", "light changing", None]


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


def test_each_new_photo_works_out_the_whole_experiment_again_and_saves_no_norm() -> None:
    """Photos a minute apart at 5,000, 5,000, 6,000: the last has no photo after it yet, so
    nothing is in a ramp. When 7,000 comes, 6,000 lies between its neighbours, so it and the
    photos either side change to light changing in rig.db. The norm columns of 17.8 stay empty
    (#382; removed in #384)."""
    experiment_id = captures.create_experiment(name="Ramp")["id"]
    record_light_photos(experiment_id, START, [(i * MINUTE, e) for i, e in enumerate([5000, 5000, 6000])], f"ramp-{experiment_id}")
    assert [r["name"] for r in database.experiment_exclusions(experiment_id)] == [None, None, None]

    database.record_capture(
        taken_at=(START + 3 * MINUTE).isoformat(), path=f"ramp-{experiment_id}/3.jpg", purpose="capture",
        experiment_id=experiment_id, calibration=None, validation=None, lens_position=None,
        focus_locked_at=None, exposure_us=7000, analogue_gain=1.0, flags=[],
    )
    photos = database.captures_for_experiment(experiment_id)
    exclusions.update(photos[-1])

    assert [r["name"] for r in database.experiment_exclusions(experiment_id)] == [None, "light changing", "light changing", "light changing"]
    saved = [database.exclusion(p["id"]) for p in photos]
    assert [(r["norm_e"], r["limit_fraction"]) for r in saved] == [(None, None)] * 4


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


def test_photos_whose_trays_are_not_read_are_left_out_of_visits() -> None:
    """Review of #301: tray 1 read at 100 mm2 in 10 photos, then 400 (a visit), 2 photos not read
    yet, then 400 again. As in the review (17.9), only photos with trays read count: the two
    visits are next to each other, and the 2 photos not read are not visits."""
    experiment_id = captures.create_experiment(name="Unread")["id"]
    record_light_photos(experiment_id, START, [(timedelta(minutes=i), 5000) for i in range(14)], f"unread-{experiment_id}")
    photos = database.captures_for_experiment(experiment_id)
    for photo, area in zip(photos, [100] * 10 + [400, None, None, 400]):
        if area is not None:
            database.record_tray_readings(photo["id"], read_at=START.isoformat(), status="read", trays=[{
                "tray_id": 1, "slot": "North 1", "a1_corner": "SW", "placement": "placed", "centre_px": [0, 0],
                "tilt_deg": 0, "margin_mm": 50, "area_mm2": area,
            }])

    exclusions.update(photos[-1])

    assert [database.exclusion(p["id"])["name"] for p in photos[10:]] == ["visit", None, None, "visit"]
