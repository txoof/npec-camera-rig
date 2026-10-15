from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

import leaves

pytestmark = pytest.mark.unit


def test_known_area_is_read_off_the_line_between_scans():
    t0 = datetime(2026, 10, 15, 11, 50, tzinfo=timezone.utc)
    scan = {"t0": t0, "a0": 1000.0, "t1": t0 + timedelta(minutes=10), "a1": 900.0}
    assert leaves.known_at(scan, t0) == pytest.approx(1000.0)
    assert leaves.known_at(scan, t0 + timedelta(minutes=4)) == pytest.approx(960.0)
    assert leaves.known_at(scan, t0 + timedelta(minutes=10)) == pytest.approx(900.0)


def test_row_mask_spans_full_width_and_leaves_out_the_aisle():
    slots = [
        {"name": "North 1", "box": [80, 80, 160, 160]},
        {"name": "North 2", "box": [240, 80, 320, 160]},
        {"name": "South 1", "box": [80, 240, 160, 320]},
    ]
    m = leaves.table_mask((50, 60), slots)  # 1/8 decode
    assert m[15, 0] and m[15, 59]  # North row, out past both end slots
    assert not m[25, 30]  # aisle between the rows (full-res y 200)
    assert m[35, 5]
    assert not np.any(m[45:, :])  # below the South row
