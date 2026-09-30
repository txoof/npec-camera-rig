import pytest

from npec_rig import validation_store as store
from npec_rig.calibration import ScaleField
from npec_rig.certainty_map import build_slot_layout, group_sheets, round_errors_by_slot, slot_layout_to_dict
from tests.helpers import sheet_detections, tray_layout_detections

pytestmark = pytest.mark.unit

SLOTS = [{"name": "North 1", "centre": [0, 0], "box": [0, 0, 1, 1]}]


@pytest.fixture(autouse=True)
def isolated_calibration_dir(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("NPEC_RIG_CALIBRATION_DIR", str(tmp_path / "calibration"))


def _counted_round(errors: list[float]) -> dict:
    return {"counted": True, "slot_errors": {"North 1": errors}, "centres": []}


def test_a_new_session_round_trips_through_disk() -> None:
    session = store.new_session("20260929T143405685796", SLOTS, [(1.0, 2.0)])
    loaded = store.load_session(session["id"])
    assert loaded == session
    assert loaded["completed_at"] is None
    assert loaded["calibration_centres"] == [[1.0, 2.0]]


def test_session_ids_are_checked_before_any_path_is_built() -> None:
    for bad in ("../../etc/passwd", "20260929", "20260929T1434056857960"):
        with pytest.raises(store.SessionNotFoundError):
            store.load_session(bad)


def test_list_is_newest_first_and_delete_removes_one() -> None:
    first = store.new_session("a", SLOTS, [])
    second = store.new_session("a", SLOTS, [])
    assert [s["id"] for s in store.list_sessions()] == [second["id"], first["id"]]
    store.delete_session(first["id"])
    assert [s["id"] for s in store.list_sessions()] == [second["id"]]
    with pytest.raises(store.SessionNotFoundError):
        store.delete_session(first["id"])


def test_deleting_a_calibration_removes_only_its_sessions() -> None:
    store.new_session("old", SLOTS, [])
    store.new_session("old", SLOTS, [])
    keep = store.new_session("new", SLOTS, [])
    assert store.delete_sessions_for_calibration("old") == 2
    assert [s["id"] for s in store.list_sessions()] == [keep["id"]]


def test_results_pool_counted_rounds_only_and_complete_at_three() -> None:
    session = store.new_session("a", SLOTS, [])
    session["rounds"] = [_counted_round([1.0] * 10), _counted_round([-2.0] * 10)]
    session["rounds"].append({"counted": False, "slot_errors": {"North 1": [50.0] * 10}, "centres": []})
    store.refresh_results(session)
    assert session["results"][0]["n"] == 20
    assert session["results"][0]["p95_abs_pct"] == pytest.approx(2.0)
    assert session["completed_at"] is None

    session["rounds"].append(_counted_round([0.5] * 10))
    store.refresh_results(session)
    completed = session["completed_at"]
    assert completed is not None

    session["rounds"].append(_counted_round([0.5] * 10))
    store.refresh_results(session)
    assert session["completed_at"] == completed  # the date it was first completed, kept


def test_each_round_keeps_its_own_figures() -> None:
    round_ = _counted_round([1.0] * 5 + [-3.0] * 5)
    result = store.round_slot_results(round_)["North 1"]
    assert result["n"] == 10
    assert result["median_pct"] == pytest.approx(-1.0)
    assert store.round_slot_results({"counted": False, "slot_errors": None}) is None


def test_median_range_needs_two_counted_rounds() -> None:
    session = store.new_session("a", SLOTS, [])
    session["rounds"] = [_counted_round([0.5] * 10)]
    assert store.median_ranges(session) == {"North 1": None}
    session["rounds"] += [
        _counted_round([-1.5] * 10),
        {"counted": False, "slot_errors": {"North 1": [9.0] * 10}, "centres": []},
    ]
    assert store.median_ranges(session)["North 1"] == pytest.approx(2.0)


def test_validated_only_while_no_slot_median_moves_past_the_limit() -> None:
    two_slots = SLOTS + [{"name": "South 1", "centre": [5, 5], "box": [5, 5, 6, 6]}]
    session = store.new_session("a", two_slots, [])

    def round_(north: float, south: float) -> dict:
        errors = {"North 1": [north] * 10, "South 1": [south] * 10}
        return {"counted": True, "slot_errors": errors, "centres": []}

    session["rounds"] = [round_(0.0, 0.0), round_(0.5, -0.5), round_(-0.5, 0.5)]
    store.refresh_results(session)
    assert store.inconsistent_slots(session) == []
    assert store.is_validated(session)

    # A 4th round with a mis-scaled sheet on South 1 takes the status away; completed_at stays.
    session["rounds"].append(round_(0.0, -7.8))
    store.refresh_results(session)
    assert session["completed_at"] is not None
    assert store.inconsistent_slots(session) == ["South 1"]
    assert not store.is_validated(session)


def test_a_drift_shows_before_the_session_is_complete() -> None:
    session = store.new_session("a", SLOTS, [])
    session["rounds"] = [_counted_round([0.0] * 10), _counted_round([-7.8] * 10)]
    assert store.inconsistent_slots(session) == ["North 1"]
    assert not store.is_validated(session)


def test_a_session_saved_before_end_validation_existed_reads_as_ended() -> None:
    session = store.new_session("a", SLOTS, [])
    assert not store.is_ended(session)
    legacy = {k: v for k, v in session.items() if k != "ended_at"}
    assert store.is_ended(legacy)


# Slot order in tray_layout_detections: North 1..6 then South 1..6, 30 tags per sheet.
_SLOT_NAMES = [f"{row} {i}" for row in ("North", "South") for i in range(1, 7)]
_FIELD = ScaleField((1.0, 0.0, 0.0), 4.0, 0.0)  # uniform 4 px/mm: a 30 mm tag is 120 px
_TAG_MM = 30.0


def _tray_session(bad_slot_per_round: list[str | None], round_scale: list[float] | None = None) -> dict:
    """A session whose rounds come from synthetic tray detections: in round i the sheet on
    `bad_slot_per_round[i]` (if any) is a 96% print, and `round_scale[i]` scales every tag of the
    round, as the camera or table moving would."""
    layout = build_slot_layout(group_sheets(tray_layout_detections(), _FIELD, _TAG_MM))
    session = store.new_session("a", slot_layout_to_dict(layout), [])
    for i, bad in enumerate(bad_slot_per_round):
        scale = round_scale[i] if round_scale else 1.0
        capture = tray_layout_detections(side_px=120.0 * scale)
        if bad is not None:
            k = _SLOT_NAMES.index(bad)
            x0, y0 = 800.0 + (k % 6) * 1300.0, (1000.0, 3500.0)[k // 6]
            capture[k * 30 : (k + 1) * 30] = sheet_detections(300, x0, y0, side_px=120.0 * 0.96 * scale)
        errors = round_errors_by_slot(capture, layout, _FIELD, _TAG_MM)
        session["rounds"].append({"counted": True, "slot_errors": errors, "centres": []})
    store.refresh_results(session)
    return session


def test_a_mis_scaled_sheet_moving_between_slots_is_named_each_round() -> None:
    session = _tray_session(["North 2", "South 5", "North 5"])
    assert store.inconsistent_slots(session) == ["North 2", "North 5", "South 5"]
    problems = store.round_problems(session)
    # Only the round the bad sheet sat there: the good sheets on those slots are not named.
    assert [(p["round"], p["slot"]) for p in problems] == [(1, "North 2"), (2, "South 5"), (3, "North 5")]
    assert all(p["offset_pct"] == pytest.approx(-7.84) for p in problems)
    assert not store.is_validated(session)


def test_a_mis_scaled_sheet_that_never_moves_is_not_flagged() -> None:
    # The limit of this check: a bad sheet (or tray) that stays on one slot reads the same every
    # round, so it looks like a bad slot. Sheets must change trays every round.
    session = _tray_session(["North 2", "North 2", "North 2"])
    assert store.inconsistent_slots(session) == []
    assert store.round_problems(session) == []
    north_2 = next(r for r in session["results"] if r["name"] == "North 2")
    assert north_2["median_pct"] == pytest.approx(-7.84)  # steady, low, unflagged


def test_two_rounds_are_not_consistent_but_name_no_sheet() -> None:
    session = _tray_session(["North 2", None])
    assert store.inconsistent_slots(session) == ["North 2"]
    assert store.round_problems(session) == []


def test_a_whole_round_shift_is_one_problem_not_twelve() -> None:
    # Every tag of round 2 reads 3.96% small in area (0.98 linear): the camera or table moved.
    session = _tray_session([None, None, None], round_scale=[1.0, 0.98, 1.0])
    assert store.inconsistent_slots(session) == _SLOT_NAMES
    problems = store.round_problems(session)
    assert [(p["round"], p["slot"]) for p in problems] == [(2, None)]
    assert problems[0]["offset_pct"] == pytest.approx(-3.96)


def test_rounds_are_numbered_as_the_page_counts_them_and_only_counted_ones_judged() -> None:
    session = _tray_session([None, "South 1", None, None])
    session["rounds"].insert(0, {"counted": False, "slot_errors": None, "centres": []})
    problems = store.round_problems(session)
    assert [(p["round"], p["slot"]) for p in problems] == [(3, "South 1")]
