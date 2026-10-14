import pytest

from npec_rig.calibration import CalibrationArtifact, ScaleField
from npec_rig.captures import photos_root
from npec_rig.calibration_store import (
    calibration_root,
    list_calibrations,
    load_calibration,
    load_current_calibration,
    save_calibration,
    calibration_frame_path,
    calibration_frame_url,
    stem_for_photo,
    LEGACY_HEATMAP_SUFFIXES,
    delete_legacy_heatmaps,
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


def test_a_calibration_stem_finds_its_photo() -> None:
    photo = {"date": "2026-10-08", "filename": "203512_123456.jpg"}
    stem = stem_for_photo(photo)

    assert stem == "20261008T203512123456"
    assert calibration_frame_path(stem) == photos_root() / "2026-10-08" / "203512_123456.jpg"


def test_a_stem_from_elsewhere_has_no_photo() -> None:
    assert calibration_frame_path("shared-stem") is None
    assert calibration_frame_url("shared-stem") is None
    assert calibration_frame_url(None) is None


def test_a_missing_photo_has_no_url() -> None:
    assert calibration_frame_url("20261008T203512123456") is None


def test_delete_legacy_heatmaps_removes_only_that_calibrations_old_images() -> None:
    root = calibration_root() / "heatmaps"
    root.mkdir(parents=True)
    for suffix in LEGACY_HEATMAP_SUFFIXES:
        (root / f"stem-a{suffix}.jpg").write_bytes(b"x")
    (root / "stem-b_area-shape.jpg").write_bytes(b"x")

    delete_legacy_heatmaps("stem-a")
    delete_legacy_heatmaps("never-had-any")  # nothing on disk: not an error

    assert [p.name for p in root.iterdir()] == ["stem-b_area-shape.jpg"]


def test_storage_is_separate_from_captures_dir(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("NPEC_RIG_PHOTOS_DIR", str(tmp_path / "captures"))
    save_calibration(_artifact())

    from npec_rig.captures import photos_root

    assert calibration_root() != photos_root()
    assert not (photos_root()).exists() or list(photos_root().iterdir()) == []
