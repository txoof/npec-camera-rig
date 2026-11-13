"""Disk headroom (#307): days of free space left at the rate the rig has been writing files.

Expected values are worked by hand: free bytes divided by bytes written in the last 24 hours.
Sizes are scaled down (bytes, not GB); the arithmetic is the same.
"""

from __future__ import annotations

import os

import pytest

from npec_rig import health

pytestmark = pytest.mark.unit

NOW = 1_800_000_000.0  # a fixed clock, seconds since the epoch
HOUR = 3600.0


def _write(path, size: int, hours_ago: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    t = NOW - hours_ago * HOUR
    os.utime(path, (t, t))


def test_five_days_left_is_yellow(tmp_path):
    # 7 photos of 100 bytes in the last day: 700 bytes a day; 3500 free is 5 days.
    for i in range(7):
        _write(tmp_path / "rig" / f"p{i}.jpg", 100, hours_ago=1 + i)
    h = health.disk_headroom(tmp_path, free_bytes=3500, now=NOW)
    assert h["bytes_per_day"] == 700
    assert h["days_left"] == pytest.approx(5.0)
    assert h["level"] == "yellow"


def test_nothing_written_in_the_last_day_gives_no_days_and_no_warning(tmp_path):
    # A file from two days ago is outside the last day; no rate, so no days figure.
    _write(tmp_path / "rig" / "old.jpg", 100, hours_ago=48)
    h = health.disk_headroom(tmp_path, free_bytes=3500, now=NOW)
    assert h["bytes_per_day"] == 0
    assert h["days_left"] is None
    assert h["level"] == "ok"


def test_three_days_left_is_red_and_six_is_ok(tmp_path):
    # 700 bytes a day: 2100 free is 3 days (red), 4200 free is 6 days (no warning).
    for i in range(7):
        _write(tmp_path / "masks" / f"m{i}.png", 100, hours_ago=2 * i)
    assert health.disk_headroom(tmp_path, free_bytes=2100, now=NOW)["level"] == "red"
    assert health.disk_headroom(tmp_path, free_bytes=4200, now=NOW)["level"] == "ok"
