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


def test_after_a_test_ends_its_database_derived_folder_and_camera_are_still_not_the_live_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A thread that outlives its test (#222) uses whatever path is left once the test's own
    settings are undone; that must never be the live rig.db, derived folder or camera (2026-10-21:
    a leaked reader thread migrated the live rig.db)."""
    import os
    from pathlib import Path

    from npec_rig.images import derived_root
    from npec_rig.settings import db_path

    monkeypatch.undo()  # what pytest does at the end of every test
    live = Path("/var/lib/npec-rig")
    assert live not in db_path().parents
    assert live not in derived_root().parents
    assert os.environ.get("NPEC_RIG_SYNTHETIC_CAMERA") == "1"
