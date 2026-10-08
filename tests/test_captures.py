import numpy as np
import pytest

from npec_rig import captures
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


class _FakeClock:
    """Stands in for /proc so the tests do not depend on how long this Pi has been up."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, boot_id: str, uptime_s: float) -> None:
        self.boot_id = boot_id
        self.uptime_s = uptime_s
        monkeypatch.setattr(captures, "read_boot_id", lambda: self.boot_id)
        monkeypatch.setattr(captures, "read_uptime_s", lambda: self.uptime_s)
        monkeypatch.setattr(captures, "_app_start", None)


def test_first_app_start_has_no_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeClock(monkeypatch, "boot-a", 5000.0)
    start = captures.record_app_start()
    assert start["gap_s"] is None
    assert start["gap_source"] is None


def test_app_restart_in_the_same_boot_measures_the_gap_from_uptime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _FakeClock(monkeypatch, "boot-a", 5000.0)
    captures.record_app_start()
    clock.uptime_s = 5030.0
    start = captures.record_app_start()
    assert start["same_boot"] is True
    assert start["gap_s"] == 30.0
    assert start["gap_source"] == "uptime"


def test_new_boot_falls_back_to_the_wall_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeClock(monkeypatch, "boot-a", 5000.0)
    captures.record_app_start()
    clock.boot_id, clock.uptime_s = "boot-b", 20.0
    start = captures.record_app_start()
    assert start["same_boot"] is False
    assert start["gap_source"] == "wall clock"


def test_photo_inside_the_cold_start_window_is_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeClock(monkeypatch, "boot-a", 600.0)
    captures.record_app_start()
    clock.uptime_s = 1200.0
    record = captures.uptime_record()
    assert record["flagged"] is True
    assert record["reason"] == (
        "taken 20 min after the Pi started, inside the 60 min cold-start window"
    )
    assert record["app_up_s"] == 600.0


def test_photo_after_the_cold_start_window_is_not_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeClock(monkeypatch, "boot-a", captures.COLD_START_WINDOW_S + 1)
    record = captures.uptime_record()
    assert record["flagged"] is False
    assert record["reason"] is None


def test_unreadable_uptime_is_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeClock(monkeypatch, "boot-a", 5000.0)
    captures.record_app_start()
    clock.uptime_s = None
    record = captures.uptime_record()
    assert record["flagged"] is True
    assert record["reason"] == "the Pi uptime could not be read"
