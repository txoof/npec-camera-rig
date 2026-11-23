"""Photo size estimates for a JPEG setting (#473).

Expected values are worked by hand from the measured table in metrology log 26.1 (file MB on
9152 x 6944 px and mean tray area change), not recomputed the way the code does.
"""

import pytest

from npec_rig import photo_size

pytestmark = pytest.mark.unit

PIXELS_64MP = 9152 * 6944


def test_presets_are_recommended_smaller_and_detail_at_full_colour():
    got = [(p.key, p.label, p.quality, p.chroma) for p in photo_size.PRESETS]
    assert got == [
        ("recommended", "Recommended", 85, "4:4:4"),
        ("smaller", "Smaller files", 75, "4:4:4"),
        ("detail", "Most detail", 95, "4:4:4"),
    ]
    assert photo_size.DEFAULT.key == "recommended"
    assert photo_size.DEFAULT.quality == 85


def test_measured_setting_at_64mp_gives_measured_size_and_area_change():
    got = photo_size.estimate(85, "4:4:4", PIXELS_64MP, 1440)
    assert got.mb_per_photo == pytest.approx(10.7, rel=1e-3)
    assert got.gb_per_day == pytest.approx(15.408, rel=1e-3)
    assert got.area_change_pct == pytest.approx(-0.36, rel=1e-3)
    assert got.size_is_guess is False


def test_half_colour_75_gives_its_measured_size_and_area_change():
    got = photo_size.estimate(75, "4:2:0", PIXELS_64MP, 1440)
    assert got.mb_per_photo == pytest.approx(5.9, rel=1e-3)
    assert got.area_change_pct == pytest.approx(-1.37, rel=1e-3)


def test_size_scales_with_pixel_count_for_a_12mp_camera():
    got = photo_size.estimate(85, "4:4:4", 4056 * 3040, 1440)
    assert got.mb_per_photo == pytest.approx(2.0760, rel=1e-3)
    assert got.gb_per_day == pytest.approx(2.9894, rel=1e-3)


def test_between_measured_qualities_size_is_interpolated_and_area_is_unknown():
    got = photo_size.estimate(80, "4:4:4", PIXELS_64MP, 1440)
    assert got.mb_per_photo == pytest.approx(9.05, rel=1e-3)
    assert got.area_change_pct is None
    assert got.size_is_guess is False


def test_below_lowest_measured_quality_size_is_a_guess_scaled_from_75():
    got = photo_size.estimate(50, "4:4:4", PIXELS_64MP, 1440)
    assert got.mb_per_photo == pytest.approx(4.9333, rel=1e-3)
    assert got.area_change_pct is None
    assert got.size_is_guess is True


@pytest.mark.parametrize(
    "quality, chroma, pixels, photos_per_day",
    [
        (0, "4:4:4", PIXELS_64MP, 1440),
        (96, "4:4:4", PIXELS_64MP, 1440),
        (85, "4:2:2", PIXELS_64MP, 1440),
        (85, "4:4:4", 0, 1440),
        (85, "4:4:4", PIXELS_64MP, -1),
    ],
)
def test_out_of_range_inputs_are_refused(quality, chroma, pixels, photos_per_day):
    with pytest.raises(ValueError):
        photo_size.estimate(quality, chroma, pixels, photos_per_day)
