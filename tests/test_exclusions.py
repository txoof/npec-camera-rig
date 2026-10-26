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

from npec_rig import exclusions

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
