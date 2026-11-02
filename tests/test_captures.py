import json

import numpy as np
import pytest

from npec_rig import captures
from npec_rig.captures import list_recent_captures, photos_root, take_photo

save_capture = captures._save_photo

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def isolated_photos_root(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("NPEC_RIG_PHOTOS_DIR", str(tmp_path / "rig"))


def _frame() -> np.ndarray:
    return np.zeros((4, 4, 3), dtype=np.uint8)


def test_save_capture_writes_jpeg_and_json_sidecar() -> None:
    record = save_capture(_frame(), {"lens_position": 6.3})

    day_dir = photos_root() / record["date"]
    jpeg_path = day_dir / record["filename"]
    json_path = jpeg_path.with_suffix(".json")
    assert jpeg_path.exists()
    assert json_path.exists()


def test_save_capture_merges_metadata_and_timestamp_into_the_record() -> None:
    record = save_capture(_frame(), {"lens_position": 6.3})
    assert record["lens_position"] == 6.3
    assert "timestamp" in record
    assert record["url"] == f"/photos/{record['date']}/{record['filename']}"


def test_list_recent_captures_returns_empty_when_root_does_not_exist() -> None:
    # Nothing has been captured yet — photos_root() itself doesn't exist.
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
    day_dir = photos_root() / record["date"]
    (day_dir / record["filename"]).with_suffix(".json").unlink()

    entries = list_recent_captures()
    assert entries[0]["filename"] == record["filename"]
    assert "lens_position" not in entries[0]


def test_list_recent_captures_tolerates_a_corrupted_sidecar_json() -> None:
    # A partial write (e.g. power loss mid-write) leaves invalid JSON on disk — one bad sidecar
    # must not take down the whole gallery listing.
    record = save_capture(_frame(), {"lens_position": 6.3})
    day_dir = photos_root() / record["date"]
    (day_dir / record["filename"]).with_suffix(".json").write_text("{not valid json")

    entries = list_recent_captures()
    assert entries[0]["filename"] == record["filename"]
    assert "lens_position" not in entries[0]


def test_take_photo_writes_the_same_sidecar_for_every_purpose() -> None:
    _array, capture = take_photo("capture")
    _array, validation = take_photo("validation", {"validation_session": "s1"})
    del _array

    assert capture["purpose"] == "capture"
    assert validation["purpose"] == "validation"
    assert set(validation) - set(capture) == {"validation_session"}
    for key in ("lens_check", "uptime", "flags", "focus", "sensor_metadata"):
        assert key in capture
    day_dir = photos_root() / capture["date"]
    on_disk = json.loads((day_dir / capture["filename"]).with_suffix(".json").read_text())
    assert on_disk["purpose"] == "capture"
    assert not list(day_dir.glob(".*.tmp"))


def test_take_photo_rejects_an_unknown_purpose() -> None:
    with pytest.raises(ValueError, match="unknown photo purpose"):
        take_photo("snapshot")


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


def test_clean_stop_writes_a_tick_so_the_next_start_measures_downtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _FakeClock(monkeypatch, "boot-a", 5000.0)
    captures.record_app_start()
    clock.uptime_s = 9000.0
    captures.record_app_stop()
    clock.uptime_s = 9012.0
    assert captures.record_app_start()["gap_s"] == 12.0


def test_a_wall_clock_gap_that_goes_backwards_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeClock(monkeypatch, "boot-b", 20.0)
    future = {"boot_id": "boot-a", "uptime_s": 9.0, "wall": "2099-01-01T00:00:00+00:00"}
    captures.save_setting("LastTick", future)
    start = captures.record_app_start()
    assert start["gap_s"] is None
    assert start["same_boot"] is False
    assert clock.boot_id == "boot-b"


def test_tick_storage_failure_does_not_stop_a_photo(monkeypatch: pytest.MonkeyPatch) -> None:
    import sqlite3

    _FakeClock(monkeypatch, "boot-a", 5000.0)

    def fail(*_args: object) -> None:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(captures, "save_setting", fail)
    monkeypatch.setattr(captures, "load_settings", fail)
    record = captures.uptime_record()
    assert record["pi_up_s"] == 5000.0


# --- Gallery paging (#165) and photo paths (#56) ---


def _put_photo(day_dir, stem: str) -> None:
    from npec_rig.camera import array_to_jpeg

    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / f"{stem}.jpg").write_bytes(array_to_jpeg(np.zeros((8, 8, 3), dtype=np.uint8)))


@pytest.fixture
def two_roots(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Five rig photos over two days and two in one experiment's stills."""
    monkeypatch.setenv("NPEC_RIG_EXPERIMENTS_DIR", str(tmp_path / "experiments"))
    for day, stem in [("2026-10-13", "230000_000000"), ("2026-10-14", "080000_000000"),
                      ("2026-10-14", "090000_000000"), ("2026-10-14", "091500_000000"),
                      ("2026-10-15", "010000_000000")]:
        _put_photo(photos_root() / day, stem)
    stills = tmp_path / "experiments" / "2026-10-14_abcd1234" / "stills"
    _put_photo(stills / "2026-10-14", "085000_000000")
    _put_photo(stills / "2026-10-14", "120000_000000")


def test_pages_back_in_time_across_rig_and_experiment_photos(two_roots) -> None:
    keys, before = [], None
    while True:
        page = list_recent_captures(limit=3, before=before)
        keys += [p["key"] for p in page]
        if len(page) < 3:
            break
        before = page[-1]["key"]
    assert keys == [
        "2026-10-15T010000_000000", "2026-10-14T120000_000000", "2026-10-14T091500_000000",
        "2026-10-14T090000_000000", "2026-10-14T085000_000000", "2026-10-14T080000_000000",
        "2026-10-13T230000_000000",
    ]


def test_before_is_exclusive_and_works_from_any_instant(two_roots) -> None:
    page = list_recent_captures(limit=10, before="2026-10-14T090000_000000")
    assert [p["key"] for p in page] == [
        "2026-10-14T085000_000000", "2026-10-14T080000_000000", "2026-10-13T230000_000000",
    ]
    # A jump to the start of a day the folders do not have.
    assert [p["key"] for p in list_recent_captures(limit=10, before="2026-10-14T000000_000000")] == [
        "2026-10-13T230000_000000",
    ]


def test_capture_hours_counts_every_root_by_utc_hour(two_roots) -> None:
    assert [{"hour": h["hour"], "count": h["count"]} for h in captures.capture_hours()] == [
        {"hour": "2026-10-15T01", "count": 1}, {"hour": "2026-10-14T12", "count": 1},
        {"hour": "2026-10-14T09", "count": 2}, {"hour": "2026-10-14T08", "count": 2},
        {"hour": "2026-10-13T23", "count": 1},
    ]


def test_photo_file_finds_rig_and_experiment_photos(two_roots, tmp_path) -> None:
    assert captures.photo_file("rig/2026-10-14/090000_000000") == photos_root() / "2026-10-14" / "090000_000000.jpg"
    assert captures.photo_file("experiments/2026-10-14_abcd1234/stills/2026-10-14/120000_000000") == (
        tmp_path / "experiments" / "2026-10-14_abcd1234" / "stills" / "2026-10-14" / "120000_000000.jpg"
    )
    assert captures.photo_file("rig/2026-10-14/100000_000000") is None
    assert captures.photo_file("experiments/2026-10-01_nope/stills/2026-10-14/120000_000000") is None


@pytest.mark.parametrize("path", [
    "rig/../2026-10-14/090000_000000",
    "experiments/../../etc/stills/2026-10-14/090000_000000",
    "rig/2026-10-14/090000_000000.jpg",
    "/var/lib/npec-rig/rig/2026-10-14/090000_000000",
    "calibration/2026-10-14/090000_000000",
])
def test_photo_file_rejects_anything_not_shaped_like_a_gallery_path(path) -> None:
    with pytest.raises(ValueError):
        captures.photo_file(path)


def test_a_replay_camera_takes_the_folders_photos_in_name_order(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    # Two saved photos of different sizes and colours; a third still starts over at the first.
    from PIL import Image

    folder = tmp_path / "replay"
    folder.mkdir()
    Image.new("RGB", (40, 30), (200, 30, 30)).save(folder / "a.jpg")
    Image.new("RGB", (50, 20), (30, 30, 200)).save(folder / "b.jpg")
    monkeypatch.delenv("NPEC_RIG_SYNTHETIC_CAMERA")
    monkeypatch.setenv("NPEC_RIG_REPLAY_PHOTOS", str(folder))

    stills = [take_photo("capture") for _ in range(3)]

    assert [array.shape for array, _record in stills] == [(30, 40, 3), (20, 50, 3), (30, 40, 3)]
    # JPEG is lossy: the colour, not the exact pixel values.
    reds = [array.reshape(-1, 3).mean(axis=0) for array, _record in stills]
    assert [int(np.argmax(c)) for c in reds] == [0, 2, 0]
    assert [record["sensor_metadata"]["ReplayedFrom"] for _array, record in stills] == [
        str(folder / "a.jpg"),
        str(folder / "b.jpg"),
        str(folder / "a.jpg"),
    ]


def test_a_replay_cameras_live_view_shows_the_photo_the_next_still_will_be(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    import io

    from PIL import Image

    from npec_rig.camera import CameraManager

    folder = tmp_path / "replay"
    folder.mkdir()
    Image.new("RGB", (40, 30), (200, 30, 30)).save(folder / "a.jpg")
    Image.new("RGB", (50, 20), (30, 30, 200)).save(folder / "b.jpg")
    monkeypatch.delenv("NPEC_RIG_SYNTHETIC_CAMERA")
    monkeypatch.setenv("NPEC_RIG_REPLAY_PHOTOS", str(folder))
    manager = CameraManager.instance()

    def views() -> list[tuple[tuple[int, int], int]]:
        # (size, strongest colour channel) of the live preview and the main-stream snapshot.
        out = []
        for jpeg in (manager.preview_jpeg(), manager.snapshot_jpeg()):
            image = Image.open(io.BytesIO(jpeg)).convert("RGB")
            out.append((image.size, int(np.argmax(np.asarray(image).reshape(-1, 3).mean(axis=0)))))
        return out

    # The camera's stream sizes: lores 320 x 240 for the preview, main 1536 x 1152.
    assert views() == [((320, 240), 0), ((1536, 1152), 0)]
    take_photo("capture")
    assert views() == [((320, 240), 2), ((1536, 1152), 2)]


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("missing", "no photos to replay in"),
        ("empty", "no photos to replay in"),
        ("both", "both NPEC_RIG_REPLAY_PHOTOS and NPEC_RIG_SYNTHETIC_CAMERA are set"),
    ],
)
def test_a_replay_camera_that_cannot_replay_is_unavailable_not_another_camera(
    monkeypatch: pytest.MonkeyPatch, tmp_path, case: str, reason: str
) -> None:
    from PIL import Image

    from npec_rig.camera import CameraUnavailableError

    folder = tmp_path / "replay"
    if case != "missing":
        folder.mkdir()
    if case == "both":
        Image.new("RGB", (40, 30), (200, 30, 30)).save(folder / "a.jpg")
    else:
        monkeypatch.delenv("NPEC_RIG_SYNTHETIC_CAMERA")
    monkeypatch.setenv("NPEC_RIG_REPLAY_PHOTOS", str(folder))

    with pytest.raises(CameraUnavailableError, match=reason):
        take_photo("capture")


def test_a_replay_camera_skips_hidden_files_and_reads_any_jpeg_name(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    # A Mac copy leaves "._" files beside each photo: not JPEGs, and they sort first.
    from PIL import Image

    folder = tmp_path / "replay"
    folder.mkdir()
    (folder / "._a.jpg").write_bytes(b"\x00\x05\x16\x07 not a jpeg")
    Image.new("RGB", (40, 30), (200, 30, 30)).save(folder / "a.JPG", format="JPEG")
    Image.new("RGB", (50, 20), (30, 30, 200)).save(folder / "b.jpeg")
    monkeypatch.delenv("NPEC_RIG_SYNTHETIC_CAMERA")
    monkeypatch.setenv("NPEC_RIG_REPLAY_PHOTOS", str(folder))

    replayed = [take_photo("capture")[1]["sensor_metadata"]["ReplayedFrom"] for _ in range(2)]

    assert replayed == [str(folder / "a.JPG"), str(folder / "b.jpeg")]


def test_a_replayed_still_says_so_in_its_flags_sidecar_and_jpeg(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from PIL import Image

    folder = tmp_path / "replay"
    folder.mkdir()
    Image.new("RGB", (40, 30), (200, 30, 30)).save(folder / "a.jpg")
    monkeypatch.delenv("NPEC_RIG_SYNTHETIC_CAMERA")
    monkeypatch.setenv("NPEC_RIG_REPLAY_PHOTOS", str(folder))

    _array, record = take_photo("capture")

    assert "replayed from a.jpg" in record["flags"]
    assert record["replayed_from"] == str(folder / "a.jpg")
    with Image.open(photos_root() / record["date"] / record["filename"]) as saved:
        assert saved.getexif()[0x010E].startswith("Replayed from a.jpg")  # EXIF ImageDescription


def test_a_photo_taken_before_the_clock_has_the_network_time_says_so(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    # Test C of #62 (2026-11-02): after a power cut with no network the rig booted 11 min 35 s
    # slow, and its photos carried those times with no mark.
    from npec_rig import database

    monkeypatch.setattr(captures, "CLOCK_SYNC_MARKER", tmp_path / "synchronized")  # not there

    _array, record = take_photo("capture")

    assert record["clock"]["synchronized"] is False
    row = database.captures_by_path([record["path"]])[record["path"]]
    assert row["clock_synced"] == 0


def test_a_photo_taken_once_the_clock_has_the_network_time_is_not_marked(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from npec_rig import database

    marker = tmp_path / "synchronized"
    marker.touch()
    monkeypatch.setattr(captures, "CLOCK_SYNC_MARKER", marker)

    _array, record = take_photo("capture")

    assert record["clock"]["synchronized"] is True
    assert "time may be wrong: clock not set" not in record["flags"]
    assert database.captures_by_path([record["path"]])[record["path"]]["clock_synced"] == 1
