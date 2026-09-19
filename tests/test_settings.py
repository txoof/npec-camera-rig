import pytest

from npec_rig.settings import load_settings, save_setting

pytestmark = pytest.mark.unit


def test_save_and_load_round_trips_values_of_different_types() -> None:
    save_setting("ExposureTime", 20000)
    save_setting("AwbEnable", True)
    save_setting("AnalogueGain", 2.5)

    settings = load_settings()
    assert settings["ExposureTime"] == 20000
    assert settings["AwbEnable"] is True
    assert settings["AnalogueGain"] == 2.5


def test_save_setting_overwrites_previous_value() -> None:
    save_setting("AnalogueGain", 1.0)
    save_setting("AnalogueGain", 4.0)
    assert load_settings()["AnalogueGain"] == 4.0


def test_load_settings_empty_by_default() -> None:
    assert load_settings() == {}
