"""Disk headroom (#307): days of free space left at the rate the rig has been writing files.

Expected values are worked by hand: free bytes divided by bytes written in the last 24 hours.
Sizes are GB, as on a rig, so the free space floor (#506) does not set the level by accident; the
files are sparse, so they take almost no real disk.
"""

from __future__ import annotations

import os

import pytest

from npec_rig import health

pytestmark = pytest.mark.unit

NOW = 1_800_000_000.0  # a fixed clock, seconds since the epoch
HOUR = 3600.0
GB = 1_000_000_000


def _write(path, size: int, hours_ago: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.truncate(size)  # sparse: `size` bytes long, almost none on disk
    t = NOW - hours_ago * HOUR
    os.utime(path, (t, t))


def test_five_days_left_is_yellow(tmp_path):
    # 7 photos of 2 GB in the last day: 14 GB a day; 70 GB free is 5 days.
    for i in range(7):
        _write(tmp_path / "rig" / f"p{i}.jpg", 2 * GB, hours_ago=1 + i)
    h = health.disk_headroom(tmp_path, free_bytes=70 * GB, now=NOW)
    assert h["bytes_per_day"] == 14 * GB
    assert h["days_left"] == pytest.approx(5.0)
    assert h["level"] == "yellow"


def test_nothing_written_in_the_last_day_gives_no_days_and_no_warning(tmp_path):
    # A file from two days ago is outside the last day; no rate, so no days figure.
    _write(tmp_path / "rig" / "old.jpg", 2 * GB, hours_ago=48)
    h = health.disk_headroom(tmp_path, free_bytes=70 * GB, now=NOW)
    assert h["bytes_per_day"] == 0
    assert h["days_left"] is None
    assert h["level"] == "ok"


def test_three_days_left_is_red_and_six_is_ok(tmp_path):
    # 14 GB a day: 42 GB free is 3 days (red), 84 GB free is 6 days (no warning).
    for i in range(7):
        _write(tmp_path / "masks" / f"m{i}.png", 2 * GB, hours_ago=2 * i)
    assert health.disk_headroom(tmp_path, free_bytes=42 * GB, now=NOW)["level"] == "red"
    assert health.disk_headroom(tmp_path, free_bytes=84 * GB, now=NOW)["level"] == "ok"


def _db_files(root, size: int, hours_ago: float) -> None:
    """rig.db and its two journal files, rewritten all day: not photos the rig keeps adding."""
    for name in ("rig.db", "rig.db-wal", "rig.db-shm"):
        _write(root / name, size, hours_ago)


def test_a_full_disk_with_nothing_written_today_is_red_on_free_space(tmp_path):
    # #506: no write rate, so no days figure, but 0 bytes free must still warn. The tests' rig.db
    # is in tmp_path (conftest).
    _db_files(tmp_path, 100, hours_ago=1)
    h = health.disk_headroom(tmp_path, free_bytes=0, now=NOW)
    assert h["level"] == "red"
    assert h["days_left"] is None
    assert h["level_reason"] == "bytes"


def test_just_under_3_gb_free_is_red(tmp_path):
    h = health.disk_headroom(tmp_path, free_bytes=3 * GB - 1, now=NOW)
    assert h["level"] == "red"


def test_just_under_5_gb_free_is_yellow(tmp_path):
    h = health.disk_headroom(tmp_path, free_bytes=5 * GB - 1, now=NOW)
    assert h["level"] == "yellow"
    assert h["level_reason"] == "bytes"


def test_plenty_free_with_nothing_written_today_is_ok_with_no_days(tmp_path):
    h = health.disk_headroom(tmp_path, free_bytes=50 * GB, now=NOW)
    assert h["level"] == "ok"
    assert h["days_left"] is None


def test_a_normal_day_of_photos_with_plenty_free_is_ok(tmp_path):
    # 1 GB written in the last day; 100 GB free is 100 days.
    _write(tmp_path / "rig" / "day.jpg", GB, hours_ago=3)
    h = health.disk_headroom(tmp_path, free_bytes=100 * GB, now=NOW)
    assert h["days_left"] == pytest.approx(100.0)
    assert h["level"] == "ok"


def test_many_days_left_but_under_3_gb_free_is_red_on_free_space(tmp_path):
    # 10 MB a day: 2.9 GB free is 290 days, an ok days figure, but under the 3 GB floor.
    _write(tmp_path / "rig" / "day.jpg", 10_000_000, hours_ago=3)
    h = health.disk_headroom(tmp_path, free_bytes=2_900_000_000, now=NOW)
    assert h["days_left"] == pytest.approx(290.0)
    assert h["level"] == "red"
    assert h["level_reason"] == "bytes"


def test_plenty_free_but_three_days_left_is_red_on_days(tmp_path):
    # 20 GB a day: 60 GB free is 3 days.
    _write(tmp_path / "rig" / "day.jpg", 20 * GB, hours_ago=3)
    h = health.disk_headroom(tmp_path, free_bytes=60 * GB, now=NOW)
    assert h["level"] == "red"
    assert h["level_reason"] == "days"


def test_the_database_and_its_journals_are_not_counted_as_written(tmp_path):
    # rig.db, -wal and -shm are rewritten all day; only the 1 GB photo is new data.
    _db_files(tmp_path, 5 * GB, hours_ago=1)
    _write(tmp_path / "rig" / "photo.jpg", GB, hours_ago=2)
    h = health.disk_headroom(tmp_path, free_bytes=100 * GB, now=NOW)
    assert h["bytes_per_day"] == GB


def test_a_file_named_rig_db_elsewhere_is_counted(tmp_path):
    # Only the rig's own database is left out, not any file of that name.
    _write(tmp_path / "rig" / "rig.db", GB, hours_ago=2)
    h = health.disk_headroom(tmp_path, free_bytes=100 * GB, now=NOW)
    assert h["bytes_per_day"] == GB
