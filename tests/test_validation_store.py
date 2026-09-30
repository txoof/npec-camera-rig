import pytest

from npec_rig import validation_store as store

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


def test_a_session_saved_before_end_validation_existed_reads_as_ended() -> None:
    session = store.new_session("a", SLOTS, [])
    assert not store.is_ended(session)
    legacy = {k: v for k, v in session.items() if k != "ended_at"}
    assert store.is_ended(legacy)
