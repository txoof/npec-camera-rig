import numpy as np
import pytest

from npec_rig.captures import captures_root, list_recent_captures, save_capture

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def isolated_captures_root(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("NPEC_RIG_CAPTURES_DIR", str(tmp_path / "captures"))


def _frame() -> np.ndarray:
    return np.zeros((4, 4, 3), dtype=np.uint8)


def test_save_capture_writes_jpeg_and_json_sidecar() -> None:
    record = save_capture(_frame(), {"lens_position": 6.3})

    day_dir = captures_root() / record["date"]
    jpeg_path = day_dir / record["filename"]
    json_path = jpeg_path.with_suffix(".json")
    assert jpeg_path.exists()
    assert json_path.exists()


def test_save_capture_merges_metadata_and_timestamp_into_the_record() -> None:
    record = save_capture(_frame(), {"lens_position": 6.3})
    assert record["lens_position"] == 6.3
    assert "timestamp" in record
    assert record["url"] == f"/captures/{record['date']}/{record['filename']}"


def test_list_recent_captures_returns_empty_when_root_does_not_exist() -> None:
    # Nothing has been captured yet — captures_root() itself doesn't exist.
    assert list_recent_captures() == []


def test_list_recent_captures_returns_saved_captures_newest_first() -> None:
    first = save_capture(_frame(), {})
    second = save_capture(_frame(), {})

    entries = list_recent_captures()
    filenames = [entry["filename"] for entry in entries]
    assert filenames.index(second["filename"]) < filenames.index(first["filename"])


def test_list_recent_captures_respects_limit() -> None:
    for _ in range(5):
        save_capture(_frame(), {})

    assert len(list_recent_captures(limit=2)) == 2


def test_list_recent_captures_tolerates_a_missing_sidecar_json() -> None:
    record = save_capture(_frame(), {})
    day_dir = captures_root() / record["date"]
    (day_dir / record["filename"]).with_suffix(".json").unlink()

    entries = list_recent_captures()
    assert entries[0]["filename"] == record["filename"]
    assert "lens_position" not in entries[0]


def test_list_recent_captures_tolerates_a_corrupted_sidecar_json() -> None:
    # A partial write (e.g. power loss mid-write) leaves invalid JSON on disk — one bad sidecar
    # must not take down the whole gallery listing.
    record = save_capture(_frame(), {"lens_position": 6.3})
    day_dir = captures_root() / record["date"]
    (day_dir / record["filename"]).with_suffix(".json").write_text("{not valid json")

    entries = list_recent_captures()
    assert entries[0]["filename"] == record["filename"]
    assert "lens_position" not in entries[0]
