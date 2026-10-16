import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

import npec_rig.photo_tags as photo_tags
import npec_rig.routes.calibration as calibration_routes
from npec_rig import images
from npec_rig.app import app
from npec_rig.calibration import CalibrationArtifact, ScaleField
from npec_rig.calibration_store import (
    CalibrationNotFoundError,
    calibration_root,
    save_calibration,
    saved_calibration_path,
)
from npec_rig.camera import array_to_jpeg
from npec_rig.captures import photos_root
from npec_rig.tags import ASSUMED_CALIBRATION_TAG_SIZE_MM
from npec_rig.tripwire import CornerBaseline
from tests.helpers import rotate_detection, tray_layout_detections
from tests.web.tag_scenes import CALIBRATION_TAGS, CORNER_TAGS, FOUR_CORNER_TAGS

pytestmark = pytest.mark.unit


# Captured once, at collection time, before the autouse fixture below ever patches the module
# attribute -- the small number of dedicated gate tests restore this to exercise the real
# function instead of the "always ready" default.
_REAL_CALIBRATION_READINESS = calibration_routes._calibration_readiness


def test_run_calibration_reports_insufficient_tags(isolated_calibration_dir: None) -> None:
    client = TestClient(app)
    response = client.post("/calibration/run")
    assert response.status_code == 200
    body = response.json()
    assert body["calibration_tags_detected"] == 0
    assert body["corner_tags_detected"] == 0
    assert "error" in body


def test_run_calibration_builds_field_and_saves_artifact_and_frame(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(
        photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + CORNER_TAGS
    )

    client = TestClient(app)
    response = client.post("/calibration/run")
    assert response.status_code == 200
    body = response.json()

    assert "error" not in body
    assert body["calibration_tags_detected"] == len(CALIBRATION_TAGS)
    assert body["corner_tags_detected"] == len(CORNER_TAGS)
    assert body["corner_baseline_tags"] == [450, 451]
    assert body["report"]
    assert isinstance(body["residual_std_pct"], float)

    assert Path(body["frame_path"]).exists()
    assert Path(body["artifact_path"]).exists()
    assert "focus not locked" in body["photo_flags"]
    sidecar = json.loads(Path(body["frame_path"]).with_suffix(".json").read_text())
    assert sidecar["purpose"] == "calibration"
    assert body["frame_url"] is not None
    # No heatmaps are drawn or saved any more (plot review, issue #53); plots go through
    # images.py when asked for.
    removed_keys = {
        "heatmap_url", "accuracy_shape_heatmap_url", "table_view_url",
        "area_shape_heatmap_url", "table_view_shape_url",
    }
    assert not removed_keys & body.keys()
    assert not (calibration_root() / "heatmaps").exists()
    assert "uncertainty_field" not in json.loads(Path(body["artifact_path"]).read_text())

    current = client.get("/calibration/current").json()
    assert current["exists"] is True
    assert current["corner_baseline_tags"] == [450, 451]
    assert current["residual_std_pct"] == body["residual_std_pct"]
    assert current["frame_url"] == body["frame_url"]
    assert not (removed_keys | {"has_uncertainty_field"}) & current.keys()

    listing = client.get("/calibration/list").json()
    assert not removed_keys & listing[0].keys()


def test_tag_map_is_drawn_for_a_calibration_with_all_four_corner_tags(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(
        photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + FOUR_CORNER_TAGS
    )

    client = TestClient(app)
    response = client.post("/calibration/run")
    assert response.status_code == 200
    body = response.json()

    assert body["corner_baseline_tags"] == [450, 451, 452, 455]
    assert client.post("/calibration/table-dims").status_code in (404, 405)  # the inputs are gone

    for path in ("/calibration/current/tag-map", f"/calibration/{Path(body['artifact_path']).stem}/tag-map"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["content-type"] == "image/jpeg"
        assert response.content[:2] == b"\xff\xd8"


def test_tag_map_needs_four_corner_tags(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + CORNER_TAGS)
    client = TestClient(app)
    assert client.post("/calibration/run").status_code == 200

    response = client.get("/calibration/current/tag-map")
    assert response.status_code == 409
    assert "straighten" in response.json()["detail"]


# --- Calibration readiness gate: focus locked, all 4 corner tags detected ---
# These tests restore the real `_calibration_readiness` (the other tests in this file default it
# open, see `calibration_gate_open_by_default`) to exercise the actual gate logic against real
# lock state and real `detect_tags` results.


def test_calibration_readiness_reports_not_ready_with_no_lock_and_no_corner_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(calibration_routes, "_calibration_readiness", _REAL_CALIBRATION_READINESS)
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: [])

    client = TestClient(app)
    body = client.get("/calibration/readiness").json()
    assert body == {
        "focus_locked": False,
        "corner_tags_detected": 0,
        "corner_tags_required": 4,
        "ready": False,
    }


def test_calibration_readiness_reports_ready_once_locked_with_four_corner_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(calibration_routes, "_calibration_readiness", _REAL_CALIBRATION_READINESS)
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: FOUR_CORNER_TAGS)

    client = TestClient(app)
    client.post("/controls/lens-position", json={"value": 6.3})
    client.post("/focus/lock")

    body = client.get("/calibration/readiness").json()
    assert body == {
        "focus_locked": True,
        "corner_tags_detected": 4,
        "corner_tags_required": 4,
        "ready": True,
    }


def test_run_calibration_refuses_without_a_lock_and_can_be_overridden(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(calibration_routes, "_calibration_readiness", _REAL_CALIBRATION_READINESS)
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + FOUR_CORNER_TAGS)

    client = TestClient(app)
    refused = client.post("/calibration/run").json()
    assert refused["gate_failed"] is True
    assert refused["focus_locked"] is False
    assert "Focus is not confirmed" in refused["error"]
    assert "artifact_path" not in refused  # no capture happened

    overridden = client.post("/calibration/run", params={"override_focus_gate": "true"}).json()
    assert "gate_failed" not in overridden
    assert "error" not in overridden


def test_run_calibration_refuses_with_too_few_corner_tags_and_can_be_overridden(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(calibration_routes, "_calibration_readiness", _REAL_CALIBRATION_READINESS)
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + CORNER_TAGS)

    client = TestClient(app)
    client.post("/controls/lens-position", json={"value": 6.3})
    client.post("/focus/lock")

    refused = client.post("/calibration/run").json()
    assert refused["gate_failed"] is True
    assert refused["corner_tags_detected"] == len(CORNER_TAGS)
    assert "2 of 4 corner tags" in refused["error"]
    assert "artifact_path" not in refused

    overridden = client.post("/calibration/run", params={"override_focus_gate": "true"}).json()
    assert "gate_failed" not in overridden
    assert "error" not in overridden


def test_run_calibration_accepts_a_measured_tag_size_override(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    # The point of the override: a reprint of the calibration sheets can come out at a different
    # physical size, and that's the operator's callipers to measure, not a source-code constant.
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + CORNER_TAGS)

    client = TestClient(app)
    response = client.post("/calibration/run", params={"calibration_tag_size_mm": 30.02})
    assert response.status_code == 200
    body = response.json()
    assert body["calibration_tag_size_mm"] == 30.02
    assert body["calibration_tag_size_mm_is_default"] is False

    current = client.get("/calibration/current").json()
    assert current["calibration_tag_size_mm"] == 30.02


def test_run_calibration_without_override_uses_the_placeholder_default(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + CORNER_TAGS)

    client = TestClient(app)
    response = client.post("/calibration/run")
    assert response.status_code == 200
    body = response.json()
    assert body["calibration_tag_size_mm"] == ASSUMED_CALIBRATION_TAG_SIZE_MM
    assert body["calibration_tag_size_mm_is_default"] is True


def test_current_calibration_before_any_run(isolated_calibration_dir: None) -> None:
    client = TestClient(app)
    response = client.get("/calibration/current")
    assert response.status_code == 200
    assert response.json() == {"exists": False}


def test_tripwire_check_without_baseline_is_refused(isolated_calibration_dir: None) -> None:
    client = TestClient(app)
    response = client.post("/calibration/tripwire/check")
    assert response.status_code == 409


def test_tripwire_check_against_saved_baseline(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    baseline = CornerBaseline(corners_by_id={d.tag_id: d.corners for d in CORNER_TAGS})
    artifact = CalibrationArtifact(
        created_at="2026-09-20T12:00:00+00:00",
        scale_field=ScaleField(_coeffs=(1.0, 0.0, 0.0), _mean_px_per_mm=4.0, residual_std_pct=1.0),
        corner_baseline=baseline,
        lens_position=6.3,
    )
    save_calibration(artifact)

    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CORNER_TAGS)

    client = TestClient(app)
    response = client.post("/calibration/tripwire/check")
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "OK"
    assert body["roll_deg"] == pytest.approx(0.0)
    assert body["photo_url"].startswith("/photos/")
    sidecar_path = photos_root() / body["photo_url"].removeprefix("/photos/")
    assert json.loads(sidecar_path.with_suffix(".json").read_text())["purpose"] == "tripwire"


def test_a_calibration_whose_photo_is_gone_still_loads(isolated_calibration_dir: None) -> None:
    # Calibrations from before #103 kept their frame in calibration/frames/, which is no longer
    # read. The pages must still load, so a new calibration can be run to replace it.
    artifact = CalibrationArtifact(
        created_at="2026-09-20T12:00:00+00:00",
        scale_field=ScaleField(_coeffs=(1.0, 0.0, 0.0), _mean_px_per_mm=4.0, residual_std_pct=1.0),
        frame_stem="20260920T120000000000",
    )
    save_calibration(artifact, stem="20260920T120000000000")
    client = TestClient(app)

    current = client.get("/calibration/current")
    assert current.status_code == 200
    assert current.json()["frame_url"] is None
    listing = client.get("/calibration/list")
    assert listing.status_code == 200
    assert listing.json()[0]["frame_url"] is None
    for page in ("/setup/calibration", "/setup/calibration-history", "/setup/health-check"):
        assert client.get(page).status_code == 200


def test_tripwire_check_reports_a_real_roll_through_the_json_round_trip(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    # Unlike the zero-motion case above, this proves roll_deg/scale_delta_pct survive the
    # endpoint's dict-building and JSON encoding with real (non-zero, non-default) values, not
    # just that the wiring doesn't crash -- what Aaron will actually be reading off the screen
    # during the roll-camera acceptance test.
    baseline = CornerBaseline(corners_by_id={d.tag_id: d.corners for d in CORNER_TAGS})
    artifact = CalibrationArtifact(
        created_at="2026-09-20T12:00:00+00:00",
        scale_field=ScaleField(_coeffs=(1.0, 0.0, 0.0), _mean_px_per_mm=4.0, residual_std_pct=1.0),
        corner_baseline=baseline,
        lens_position=6.3,
    )
    save_calibration(artifact)

    pivot = (750, 500)
    rolled = [rotate_detection(d, pivot, 5.0) for d in CORNER_TAGS]
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: rolled)

    client = TestClient(app)
    response = client.post("/calibration/tripwire/check")
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "DRIFT"
    assert body["roll_deg"] == pytest.approx(5.0, abs=0.01)
    assert set(body["scale_delta_pct"].keys()) == {"450", "451"}


def test_run_calibration_with_promote_false_does_not_replace_current(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + CORNER_TAGS)
    client = TestClient(app)

    first = client.post("/calibration/run").json()
    assert first["promoted_to_current"] is True

    second = client.post("/calibration/run", params={"promote": "false"}).json()
    assert second["promoted_to_current"] is False
    assert second["artifact_path"] != first["artifact_path"]

    current = client.get("/calibration/current").json()
    assert current["created_at"] != second.get("created_at")  # unaffected by the second run
    # Both runs still landed on disk -- promote=False only skips the current.json pointer.
    assert Path(first["artifact_path"]).exists()
    assert Path(second["artifact_path"]).exists()


def test_run_calibration_has_no_delta_on_the_first_run(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + CORNER_TAGS)
    client = TestClient(app)

    result = client.post("/calibration/run").json()
    assert result["previous_calibration_comparison"] is None


def test_run_calibration_delta_compares_against_the_previous_active_calibration(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + CORNER_TAGS)
    client = TestClient(app)

    first = client.post("/calibration/run").json()
    assert first["previous_calibration_comparison"] is None

    second = client.post("/calibration/run", params={"calibration_tag_size_mm": 30.02}).json()
    cmp = second["previous_calibration_comparison"]
    assert cmp is not None
    assert cmp["previous_created_at"]  # a real ISO timestamp string, not asserting its exact value
    assert cmp["residual_std_pct"]["previous"] == first["residual_std_pct"]
    assert cmp["residual_std_pct"]["current"] == second["residual_std_pct"]
    assert cmp["residual_std_pct"]["delta"] == pytest.approx(
        second["residual_std_pct"] - first["residual_std_pct"]
    )
    assert cmp["corner_tags_detected"]["previous"] == len(first["corner_baseline_tags"])
    assert cmp["corner_tags_detected"]["current"] == len(second["corner_baseline_tags"])
    assert cmp["calibration_tag_size_mm"]["previous"] == first["calibration_tag_size_mm"]
    assert cmp["calibration_tag_size_mm"]["current"] == 30.02
    assert cmp["calibration_tag_size_mm"]["delta"] == pytest.approx(
        30.02 - first["calibration_tag_size_mm"]
    )
    assert cmp["lens_position"]["previous"] == first["lens_position"]
    assert cmp["lens_position"]["current"] == second["lens_position"]


def test_run_calibration_delta_present_even_when_not_promoted(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    # promote=False is explicitly a comparison run -- it should still see a delta against
    # whatever the live baseline currently is, that's the whole point of comparing.
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + CORNER_TAGS)
    client = TestClient(app)

    client.post("/calibration/run")
    second = client.post("/calibration/run", params={"promote": "false"}).json()
    assert second["previous_calibration_comparison"] is not None


def test_calibration_list_and_files_are_downloadable(monkeypatch: pytest.MonkeyPatch) -> None:
    # Deliberately not isolated_calibration_dir: /calibration/files is a StaticFiles mount bound
    # to a fixed directory at app import time (same pattern as /photos), so it serves whatever
    # NPEC_RIG_CALIBRATION_DIR conftest.py set at import -- a per-test env override wouldn't be
    # visible to it.
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + CORNER_TAGS)
    client = TestClient(app)
    run = client.post("/calibration/run").json()

    listing = client.get("/calibration/list").json()
    entry = next(e for e in listing if e["url"] == f"/calibration/files/{Path(run['artifact_path']).name}")
    assert entry["frame_url"] == run["frame_url"]
    assert entry["frame_url"].startswith("/photos/")

    artifact_response = client.get(entry["url"])
    assert artifact_response.status_code == 200
    assert artifact_response.json()["version"] == 3

    frame_response = client.get(entry["frame_url"])
    assert frame_response.status_code == 200
    assert frame_response.content[:2] == b"\xff\xd8"


# --- Calibration-history browser: per-entry stats, promote, delete ---


def test_calibration_list_includes_per_entry_stats_and_marks_the_active_one(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + CORNER_TAGS)
    client = TestClient(app)

    first = client.post("/calibration/run").json()
    second = client.post("/calibration/run", params={"promote": "false"}).json()

    first_stem = Path(first["artifact_path"]).stem
    second_stem = Path(second["artifact_path"]).stem

    listing = client.get("/calibration/list").json()
    by_stem = {e["stem"]: e for e in listing}

    assert by_stem[first_stem]["is_current"] is True
    assert by_stem[first_stem]["residual_std_pct"] == first["residual_std_pct"]
    assert by_stem[first_stem]["calibration_tag_size_mm"] == first["calibration_tag_size_mm"]
    assert by_stem[first_stem]["corner_tag_count"] == len(first["corner_baseline_tags"])

    assert by_stem[second_stem]["is_current"] is False
    assert by_stem[second_stem]["residual_std_pct"] == second["residual_std_pct"]


def test_promote_calibration_makes_it_the_active_one(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + CORNER_TAGS)
    client = TestClient(app)

    old = client.post("/calibration/run").json()
    client.post("/calibration/run")  # a second, newer run promotes over it

    old_stem = Path(old["artifact_path"]).stem
    old_entry = next(
        e for e in client.get("/calibration/list").json() if e["stem"] == old_stem
    )
    assert old_entry["is_current"] is False

    response = client.post(f"/calibration/{old_stem}/promote")
    assert response.status_code == 200
    assert response.json()["promoted"] == old_stem

    current_after = client.get("/calibration/current").json()
    assert current_after["created_at"] == old_entry["created_at"]

    listing_after = client.get("/calibration/list").json()
    assert next(e for e in listing_after if e["stem"] == old_stem)["is_current"] is True


def test_promote_unknown_stem_returns_404(isolated_calibration_dir: None) -> None:
    client = TestClient(app)
    response = client.post("/calibration/does-not-exist/promote")
    assert response.status_code == 404


def test_delete_calibration_removes_its_files(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + CORNER_TAGS)
    client = TestClient(app)

    old = client.post("/calibration/run").json()
    client.post("/calibration/run")  # promotes a second run so `old` is no longer active

    old_stem = Path(old["artifact_path"]).stem
    assert Path(old["artifact_path"]).exists()
    assert Path(old["frame_path"]).exists()
    # Heatmaps left by runs from before the plot review (issue #53) are still cleaned up.
    (calibration_root() / "heatmaps").mkdir()
    legacy_heatmap = calibration_root() / "heatmaps" / f"{old_stem}.jpg"
    legacy_heatmap.write_bytes(b"\xff\xd8")
    legacy_area_shape = calibration_root() / "heatmaps" / f"{old_stem}_area-shape.jpg"
    legacy_area_shape.write_bytes(b"\xff\xd8")
    assert client.get(f"/calibration/{old_stem}/radial-plot").status_code == 200
    radial_dir = images.derived_root() / "calibration_radial_plot"
    assert len(list(radial_dir.iterdir())) == 1

    response = client.delete(f"/calibration/{old_stem}")
    assert response.status_code == 200
    assert response.json()["deleted"] == old_stem

    assert not Path(old["artifact_path"]).exists()
    # The photo stays with the other rig photos: originals are never changed.
    assert Path(old["frame_path"]).exists()
    assert not legacy_heatmap.exists()
    assert not legacy_area_shape.exists()
    assert list(radial_dir.iterdir()) == []  # its derived plots are forgotten too

    listing = client.get("/calibration/list").json()
    assert all(e["stem"] != old_stem for e in listing)


def test_delete_refuses_to_remove_the_active_calibration(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + CORNER_TAGS)
    client = TestClient(app)
    run = client.post("/calibration/run").json()
    stem = Path(run["artifact_path"]).stem

    response = client.delete(f"/calibration/{stem}")
    assert response.status_code == 409
    assert Path(run["artifact_path"]).exists()


def test_delete_unknown_stem_returns_404(isolated_calibration_dir: None) -> None:
    client = TestClient(app)
    response = client.delete("/calibration/does-not-exist")
    assert response.status_code == 404


def test_saved_calibration_path_rejects_traversal_and_the_current_pointer(
    isolated_calibration_dir: None,
) -> None:
    with pytest.raises(CalibrationNotFoundError):
        saved_calibration_path("../../../etc/passwd")

    with pytest.raises(CalibrationNotFoundError):
        saved_calibration_path("current")


def _write_corrupt_calibration(stem: str) -> None:
    """A file that parses as JSON but fails `calibration_artifact_from_dict` with a TypeError,
    not the ValueError/KeyError the rest of this file's corrupt-artifact tests use -- exercises
    the same code path a genuinely malformed-but-version-matching artifact would hit."""
    root = calibration_root()
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{stem}.json").write_text(
        json.dumps({"version": 3, "created_at": "2026-01-01T00:00:00+00:00", "scale_field": None})
    )


def test_calibration_list_survives_a_structurally_malformed_entry(
    isolated_calibration_dir: None,
) -> None:
    _write_corrupt_calibration("20260101T000000000000")
    listing = TestClient(app).get("/calibration/list").json()
    assert len(listing) == 1
    assert listing[0]["stem"] == "20260101T000000000000"
    assert listing[0]["residual_std_pct"] is None
    assert listing[0]["is_current"] is False


def test_promote_unreadable_calibration_returns_422(isolated_calibration_dir: None) -> None:
    _write_corrupt_calibration("20260101T000000000000")
    client = TestClient(app)
    response = client.post("/calibration/20260101T000000000000/promote")
    assert response.status_code == 422


def test_delete_unreadable_calibration_succeeds_when_no_current_exists(
    isolated_calibration_dir: None,
) -> None:
    _write_corrupt_calibration("20260101T000000000000")
    client = TestClient(app)
    response = client.delete("/calibration/20260101T000000000000")
    assert response.status_code == 200
    assert not (calibration_root() / "20260101T000000000000.json").exists()


def test_delete_unreadable_calibration_is_refused_when_current_exists(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")  # a real, valid, promoted calibration

    _write_corrupt_calibration("20260101T000000000000")
    response = client.delete("/calibration/20260101T000000000000")
    assert response.status_code == 409
    assert (calibration_root() / "20260101T000000000000.json").exists()


def test_delete_refuses_everything_when_current_json_itself_is_corrupt(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + CORNER_TAGS)
    client = TestClient(app)
    run = client.post("/calibration/run").json()
    stem = Path(run["artifact_path"]).stem

    (calibration_root() / "current.json").write_text(
        json.dumps({"version": 3, "created_at": "2026-01-01T00:00:00+00:00", "scale_field": None})
    )

    response = client.delete(f"/calibration/{stem}")
    assert response.status_code == 409
    assert Path(run["artifact_path"]).exists()


# --- Calibration plots: radial plot and tag map, through images.py ---


@pytest.mark.parametrize("plot", ["radial-plot", "tag-map"])
def test_calibration_plot_without_a_calibration_is_refused(plot: str, isolated_calibration_dir: None) -> None:
    client = TestClient(app)
    assert client.get(f"/calibration/current/{plot}").status_code == 409


def test_radial_plot_returns_a_jpeg(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")

    response = client.get("/calibration/current/radial-plot")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content[:2] == b"\xff\xd8"


def test_radial_plot_refused_with_too_few_tags_in_the_saved_frame(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")

    # The stored tags of an older calibration, worked out from its photo, found only one tag.
    photo = Path(client.get("/calibration/current").json()["frame_url"])
    images.store_tag_detections(f"{photo.parent.name}/{photo.stem}", CALIBRATION_TAGS[:1] + CORNER_TAGS)
    response = client.get("/calibration/current/radial-plot")
    assert response.status_code == 409


def test_calibration_tags_are_worked_out_once_from_an_older_calibrations_photo(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    # A calibration from before its run stored its tags: the photo is searched once, then stored.
    detect_calls = 0

    def counting_detect_tags(frame):
        nonlocal detect_calls
        detect_calls += 1
        return CALIBRATION_TAGS + CORNER_TAGS

    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + CORNER_TAGS)
    monkeypatch.setattr(images, "store_tag_detections", lambda source, detections: None)
    client = TestClient(app)
    client.post("/calibration/run")
    monkeypatch.setattr(photo_tags, "detect_tags", counting_detect_tags)
    for _ in range(2):
        assert client.get("/calibration/current/radial-plot?t=1").status_code == 200
    assert detect_calls == 1


def test_calibration_plots_use_the_runs_own_tags_and_keep_the_plots(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    # Searching a 64MP photo for tags is the expensive part (and several at once got the worker
    # OOM-killed, 2026-09-22): a run stores the tags it fitted to, so the plots search the photo
    # not even once, and each plot is drawn once and then read from the store.
    detect_calls = 0

    def counting_detect_tags(frame):
        nonlocal detect_calls
        detect_calls += 1
        return CALIBRATION_TAGS + FOUR_CORNER_TAGS

    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + FOUR_CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")

    monkeypatch.setattr(photo_tags, "detect_tags", counting_detect_tags)
    renders = []
    real_render = calibration_routes.render_radial_residual_plot
    monkeypatch.setattr(
        calibration_routes,
        "render_radial_residual_plot",
        lambda *a, **k: (renders.append(1), real_render(*a, **k))[1],
    )
    for _ in range(2):
        for plot in ("radial-plot", "tag-map"):
            assert client.get(f"/calibration/current/{plot}").status_code == 200

    assert detect_calls == 0
    assert len(renders) == 1


def test_diagnostics_readout_shows_the_numbers_the_plots_are_drawn_from(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + FOUR_CORNER_TAGS)
    client = TestClient(app)
    stem = Path(client.post("/calibration/run").json()["artifact_path"]).stem
    plotted = []
    real_render = calibration_routes.render_radial_residual_plot
    monkeypatch.setattr(
        calibration_routes,
        "render_radial_residual_plot",
        lambda points, **k: (plotted.append(points), real_render(points, **k))[1],
    )
    assert client.get(f"/calibration/{stem}/radial-plot").status_code == 200
    slope, _intercept, r_squared = calibration_routes.radial_fit(plotted[0])
    residuals = [p[1] for p in plotted[0]]
    median = float(np.median(residuals))

    for path in ("/calibration/current/diagnostics", f"/calibration/{stem}/diagnostics"):
        body = client.get(path).json()
        assert body["tags"] == len(plotted[0]), path
        assert body["slope_pct_per_1000px"] == pytest.approx(slope * 1000)
        assert body["r_squared"] == pytest.approx(r_squared)
        assert body["median_pct"] == pytest.approx(median)
        assert body["far_pct"] == calibration_routes.TAG_MAP_FAR_PCT
        assert body["tags_far"] == sum(abs(r - median) > calibration_routes.TAG_MAP_FAR_PCT for r in residuals)
        assert abs(body["worst_tag"]["from_median_pct"]) == pytest.approx(max(abs(r - median) for r in residuals))
        assert body["tag_map"] is True


def test_diagnostics_readout_for_an_unknown_calibration_is_not_found(isolated_calibration_dir: None) -> None:
    assert TestClient(app).get("/calibration/20260101T000000000000/diagnostics").status_code == 404


def test_current_plots_come_from_current_json_not_the_history_file(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + FOUR_CORNER_TAGS)
    client = TestClient(app)
    run = client.post("/calibration/run").json()
    Path(run["artifact_path"]).unlink()  # only current.json is left

    for plot in ("radial-plot", "tag-map"):
        assert client.get(f"/calibration/current/{plot}").status_code == 200, plot


def test_radial_plot_refuses_a_removed_metric(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    # Only the scale residual is plotted since the plot review (issue #53): an old
    # ?metric=shape_distortion link is refused, not silently answered with the other plot.
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")
    assert client.get("/calibration/current/radial-plot?metric=shape_distortion").status_code == 422
    assert client.get("/calibration/current/radial-plot?metric=scale_residual").status_code == 200


@pytest.mark.parametrize("plot", ["rank-plot", "best-worst-photo", "certainty-dome-plot"])
def test_removed_calibration_plots_are_gone(
    plot: str, monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    # Removed in the plot review (issue #53).
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + CORNER_TAGS)
    client = TestClient(app)
    stem = Path(client.post("/calibration/run").json()["artifact_path"]).stem
    assert client.get(f"/calibration/current/{plot}").status_code == 404
    assert client.get(f"/calibration/{stem}/{plot}").status_code == 404


# --- Stem-scoped diagnostics (calibration-history drill-down) ---


@pytest.mark.parametrize("path", ["radial-plot", "tag-map"])
def test_stem_diagnostics_unknown_stem_returns_404(path: str, isolated_calibration_dir: None) -> None:
    client = TestClient(app)
    response = client.get(f"/calibration/does-not-exist/{path}")
    assert response.status_code == 404


@pytest.mark.parametrize("path", ["radial-plot", "tag-map"])
def test_stem_diagnostics_unreadable_calibration_returns_422(
    path: str, isolated_calibration_dir: None
) -> None:
    _write_corrupt_calibration("20260101T000000000000")
    client = TestClient(app)
    response = client.get(f"/calibration/20260101T000000000000/{path}")
    assert response.status_code == 422


def test_stem_diagnostics_serve_an_old_run_not_whatever_is_current(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    # The whole point of the drill-down: an old, no-longer-active stem must still be viewable,
    # and must reflect *its own* saved frame, not whatever `current.json` now points at.
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + FOUR_CORNER_TAGS)
    client = TestClient(app)

    old = client.post("/calibration/run").json()
    client.post("/calibration/run")  # a second, newer run promotes over it
    old_stem = Path(old["artifact_path"]).stem

    for path in ("radial-plot", "tag-map"):
        response = client.get(f"/calibration/{old_stem}/{path}")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert response.content[:2] == b"\xff\xd8"


def test_stem_diagnostics_actually_load_the_requested_stems_own_photo(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    # A weaker version of this test (same monkeyed detect_tags for both runs) would still pass
    # even if the stem route silently read load_current_calibration() instead of the requested
    # stem -- this spies on which photo's tags are read to catch exactly that regression.
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + CORNER_TAGS)
    client = TestClient(app)

    old = client.post("/calibration/run").json()
    current = client.post("/calibration/run").json()
    old_stem = Path(old["artifact_path"]).stem
    assert old_stem != Path(current["artifact_path"]).stem

    sources = []
    real_stored = images.stored_tag_detections
    monkeypatch.setattr(
        images, "stored_tag_detections", lambda source: (sources.append(source), real_stored(source))[1]
    )

    response = client.get(f"/calibration/{old_stem}/radial-plot")
    assert response.status_code == 200
    old_photo = Path(old["frame_path"])
    assert sources == [f"{old_photo.parent.name}/{old_photo.stem}"]


# --- Certainty map ---


def _write_capture(ref: str) -> None:
    """A capture JPEG on disk at `ref` ("YYYY-MM-DD/HHMMSS_ffffff"); its content is irrelevant
    because the tests monkeypatch `detect_tags`."""
    path = photos_root() / f"{ref}.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(array_to_jpeg(np.zeros((120, 160, 3), dtype=np.uint8)))


def test_certainty_map_without_a_calibration_is_refused(isolated_calibration_dir: None) -> None:
    response = TestClient(app).get(
        "/calibration/current/certainty-map", params={"captures": "2026-09-29/143629_456239"}
    )
    assert response.status_code == 409


def test_certainty_map_needs_at_least_one_capture(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: tray_layout_detections() + CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")
    assert client.get("/calibration/current/certainty-map").status_code == 422


@pytest.mark.parametrize("ref", ["../../etc/passwd", "2026-09-29/143629", "143629_456239"])
def test_certainty_map_rejects_anything_but_a_capture_reference(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None, ref: str
) -> None:
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: tray_layout_detections() + CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")
    response = client.get("/calibration/current/certainty-map", params={"captures": ref})
    assert response.status_code == 422


def test_certainty_map_missing_capture_is_not_found(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: tray_layout_detections() + CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")
    response = client.get(
        "/calibration/current/certainty-map", params={"captures": "2000-01-01/000000_000000"}
    )
    assert response.status_code == 404


def test_certainty_map_returns_a_jpeg_for_current_and_by_stem(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: tray_layout_detections() + CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")
    stem = client.get("/calibration/list").json()[0]["stem"]
    refs = ["2026-09-29/143629_456239", "2026-09-29/143756_789335"]
    for ref in refs:
        _write_capture(ref)

    for url in ("/calibration/current/certainty-map", f"/calibration/{stem}/certainty-map"):
        response = client.get(url, params={"captures": refs})
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert response.content[:2] == b"\xff\xd8"


def test_certainty_map_refuses_a_calibration_without_12_tray_sheets(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")
    _write_capture("2026-09-29/143629_456239")
    response = client.get(
        "/calibration/current/certainty-map", params={"captures": "2026-09-29/143629_456239"}
    )
    assert response.status_code == 409
    assert "expected 12" in response.json()["detail"]


def test_certainty_map_caps_the_number_of_captures(
    monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None
) -> None:
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: tray_layout_detections() + CORNER_TAGS)
    client = TestClient(app)
    client.post("/calibration/run")
    refs = [f"2026-09-29/1436{i:02d}_000000" for i in range(13)]
    response = client.get("/calibration/current/certainty-map", params={"captures": refs})
    assert response.status_code == 422
