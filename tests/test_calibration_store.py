import numpy as np
import pytest

from npec_rig.calibration import CalibrationArtifact, ScaleField
from npec_rig.calibration_store import (
    calibration_root,
    list_calibrations,
    load_calibration,
    load_current_calibration,
    save_calibration,
    save_calibration_frame,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def isolated_calibration_root(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("NPEC_RIG_CALIBRATION_DIR", str(tmp_path / "calibration"))


def _artifact(created_at: str = "2026-09-20T12:00:00+00:00") -> CalibrationArtifact:
    field = ScaleField(_coeffs=(1.0, 0.0, 0.0), _mean_px_per_mm=4.0, residual_std_pct=1.2)
    return CalibrationArtifact(created_at=created_at, scale_field=field, lens_position=6.3)


def test_load_current_calibration_is_none_before_anything_is_saved() -> None:
    assert load_current_calibration() is None


def test_save_and_load_current_calibration_round_trips() -> None:
    artifact = _artifact()
    save_calibration(artifact)

    loaded = load_current_calibration()
    assert loaded == artifact


def test_save_writes_a_timestamped_file_and_the_current_pointer() -> None:
    artifact = _artifact()
    path = save_calibration(artifact)

    assert path.exists()
    assert path.parent == calibration_root()
    assert (calibration_root() / "current.json").exists()
    assert load_calibration(path) == artifact


def test_current_pointer_tracks_the_most_recent_save() -> None:
    first = _artifact(created_at="2026-09-20T12:00:00+00:00")
    second = _artifact(created_at="2026-09-20T13:00:00+00:00")

    save_calibration(first)
    save_calibration(second)

    assert load_current_calibration() == second


def test_list_calibrations_excludes_the_current_pointer() -> None:
    save_calibration(_artifact())
    save_calibration(_artifact(created_at="2026-09-20T13:00:00+00:00"))

    paths = list_calibrations()
    assert len(paths) == 2
    assert all(p.name != "current.json" for p in paths)


def test_list_calibrations_empty_before_anything_is_saved() -> None:
    assert list_calibrations() == []


def test_save_calibration_frame_writes_a_jpeg_under_the_frames_dir() -> None:
    image = np.zeros((8, 8, 3), dtype=np.uint8)
    path = save_calibration_frame(image)

    assert path.exists()
    assert path.parent == calibration_root() / "frames"
    assert path.read_bytes()[:2] == b"\xff\xd8"


def test_save_calibration_and_frame_share_a_stem_when_given_one() -> None:
    save_calibration_frame(np.zeros((8, 8, 3), dtype=np.uint8), stem="shared-stem")
    save_calibration(_artifact(), stem="shared-stem")

    assert (calibration_root() / "frames" / "shared-stem.jpg").exists()
    assert (calibration_root() / "shared-stem.json").exists()


def test_storage_is_separate_from_captures_dir(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("NPEC_RIG_CAPTURES_DIR", str(tmp_path / "captures"))
    save_calibration(_artifact())

    from npec_rig.captures import captures_root

    assert calibration_root() != captures_root()
    assert not (captures_root()).exists() or list(captures_root().iterdir()) == []
