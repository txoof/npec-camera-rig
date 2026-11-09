"""Hand-worked examples for script_b.py. Expected values worked out on paper, not by the code."""
from datetime import datetime, timedelta, timezone

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import script_b as q1b  # noqa: E402

pytestmark = pytest.mark.unit

U = timezone.utc


def photo(t, **kw):
    p = dict(t=t, calibration="c", lens=6.05, flags=[], status="read", exclusion=None)
    p.update(kw)
    return p


def test_shuffle_windows_hand():
    rows = [dict(shuffle="0", date="2026-10-22", start="", finish="12:41"),
            dict(shuffle="1", date="2026-10-23", start="", finish="10:56"),
            dict(shuffle="3", date="2026-10-27", start="10:49", finish="11:02")]
    w = q1b.shuffle_windows(rows)
    # Shuffle 0: none. Shuffle 1: summer time, 08:56 UTC finish, start 07:56, widened.
    assert w[0] == (datetime(2026, 10, 23, 7, 41, tzinfo=U), datetime(2026, 10, 23, 9, 11, tzinfo=U))
    # Shuffle 3: winter time, 09:49 to 10:02 UTC, widened 09:34 to 10:17.
    assert w[1] == (datetime(2026, 10, 27, 9, 34, tzinfo=U), datetime(2026, 10, 27, 10, 17, tzinfo=U))
    assert len(w) == 2


def test_pair_rules_hand():
    w = [(datetime(2026, 10, 27, 9, 34, tzinfo=U), datetime(2026, 10, 27, 10, 17, tzinfo=U))]
    t = lambda h, m, s=0: datetime(2026, 10, 27, h, m, s, tzinfo=U)
    r = lambda a, b: q1b.photo_reasons(a, b, w, [], [t(12, 0, 30)], [])
    assert r(photo(t(9, 32)), photo(t(9, 33))) == []
    assert r(photo(t(9, 33, 30)), photo(t(9, 34, 30))) == ["shuffle"]
    assert r(photo(t(10, 17, 30)), photo(t(10, 18, 30))) == []
    assert r(photo(t(11, 0)), photo(t(11, 2, 31))) == ["more than 150 s apart"]
    assert r(photo(t(11, 0)), photo(t(11, 2, 30))) == []
    assert r(photo(t(12, 0)), photo(t(12, 1))) == ["app start"]
    assert r(photo(t(11, 0), exclusion="visit"), photo(t(11, 1))) == ["exclusion"]
    assert r(photo(t(11, 0), status="no trays found"), photo(t(11, 1))) == ["not read"]
    left = datetime(2026, 10, 28, 8, 50, 1, tzinfo=U)
    assert "left out (17.12)" in r(photo(left - timedelta(seconds=60)), photo(left))


def test_tray_rule_hand():
    ok = dict(slot="N2", placement="placed", warnings=[], area=10.0)
    assert q1b.tray_reasons([ok], [ok]) == ([], False)
    out = dict(ok, warnings=["partly outside the photo"])
    assert q1b.tray_reasons([ok], [out]) == ([], True)
    assert q1b.tray_reasons([ok], [dict(ok, slot="N3")])[0] == ["slot differs"]
    assert q1b.tray_reasons([ok], [dict(ok, warnings=["no tag"])])[0] == ["warning"]
    assert q1b.tray_reasons([ok], [])[0] == ["tray not read"]


def test_percent_stats_hand():
    # 100 -> 110: 10 / 105 = 9.5238 %. 110 -> 99: -11 / 104.5 = -10.5263 %.
    a = q1b.pct_change(100, 110)
    b = q1b.pct_change(110, 99)
    assert a == pytest.approx(9.5238, abs=1e-4)
    assert b == pytest.approx(-10.5263, abs=1e-4)
    s = q1b.stats([a, b])
    assert s["rms"] == pytest.approx(10.0376, abs=1e-3)  # sqrt((90.703 + 110.803) / 2)
    assert s["median"] == pytest.approx(-0.5013, abs=1e-3)
    assert s["largest"] == pytest.approx(-10.5263, abs=1e-4)
    # 1 to 20: 95th percentile, linear, at position 18.05 of 0..19: 19.05.
    assert q1b.stats(list(range(1, 21)))["p95_abs"] == pytest.approx(19.05)
    assert q1b.pct_change(0, 0) is None


def test_growth_hand():
    d1 = lambda m: datetime(2026, 11, 1, 10, m, tzinfo=U)
    d2 = lambda m: datetime(2026, 11, 2, 10, m, tzinfo=U)
    pts = {"2026-11-01": [(d1(0), 10), (d1(1), 12), (d1(2), 14)],
           "2026-11-02": [(d2(0), 20), (d2(1), 22), (d2(2), 30)],
           "2026-11-04": [(d2(0), 40)]}
    g = q1b.growth_per_minute(pts)
    # (22 - 12) mm2 over 1440 min = 0.0069444; as % of 12: 0.05787.
    assert g["2026-11-01"][0] == pytest.approx(0.0069444, abs=1e-6)
    assert g["2026-11-01"][1] == pytest.approx(0.05787, abs=1e-5)
    assert "2026-11-02" not in g  # 3 November has no data


def test_nearest_slot_hand():
    slots = [dict(name="North 1", centre=[0, 0]), dict(name="North 2", centre=[100, 0])]
    assert q1b.nearest_slot(49, 30, slots) == "North 1"
    assert q1b.nearest_slot(51, -30, slots) == "North 2"


def test_shuffle0_window_hand():
    rows = [dict(shuffle="0", date="2026-10-22", start="", finish="12:41")]
    # 12:41 summer time is 10:41 UTC; start 09:41; widened 09:26 to 10:56.
    assert q1b.shuffle_windows(rows, shuffle0=True) == [
        (datetime(2026, 10, 22, 9, 26, tzinfo=U), datetime(2026, 10, 22, 10, 56, tzinfo=U))]
