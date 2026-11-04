"""The tray randomization page and its API (#343).

The scene is the 20 October shuffles (tests/fixtures/trays/shuffles-2026-10-20.json): its
calibration, scale field and 12 slots are saved, and tag detection returns the tags of one of its
stills, whose layouts Aaron recorded by hand (tests/test_tray_placement.py).
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from npec_rig import captures, database, photo_tags, validation_store
from npec_rig.app import app
from npec_rig.calibration import CalibrationArtifact, scale_field_from_dict
from npec_rig.calibration_store import save_calibration
from npec_rig.tags import TagDetection

pytestmark = pytest.mark.unit

FIXTURE = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "trays" / "shuffles-2026-10-20.json").read_text()
)

# Layout 2 and layout 12 of 20 October, as Aaron recorded them.
LAYOUT_2 = {
    3: ("North 1", "SW"), 10: ("North 2", "SW"), 6: ("North 3", "SW"), 1: ("North 4", "NE"),
    4: ("North 5", "SW"), 12: ("North 6", "NE"), 9: ("South 1", "NE"), 11: ("South 2", "SW"),
    7: ("South 3", "NE"), 8: ("South 4", "SW"), 5: ("South 5", "SW"), 2: ("South 6", "SW"),
}


def _detections(still: str) -> list[TagDetection]:
    out = []
    for tag in FIXTURE["stills"][still]:
        corners = tuple(tuple(c) for c in tag["corners"])
        centre = (sum(c[0] for c in corners) / 4, sum(c[1] for c in corners) / 4)
        out.append(TagDetection(tag_id=tag["id"], corners=corners, centre=centre))
    return out


class Table:
    """The shuffles calibration and slots saved; `show(still)` sets which still's tags the next
    photo shows."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stem = FIXTURE["calibration"]
        save_calibration(
            CalibrationArtifact(
                created_at="2026-10-14T11:11:47+00:00",
                scale_field=scale_field_from_dict(FIXTURE["scale_field"]),
                frame_stem=stem,
                lens_position=6.05,
            ),
            stem=stem,
        )
        validation_store.save_slot_layout(stem, FIXTURE["slots"], [])
        self.still = None
        monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: _detections(self.still))

    def show(self, still: str) -> None:
        self.still = still


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> Table:
    return Table(monkeypatch)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _running_experiment() -> dict:
    return captures.start_experiment(captures.create_experiment(name="Round 3")["id"])


def test_suggest_reads_the_last_layout_from_the_latest_experiment_photo(table, client) -> None:
    experiment = _running_experiment()
    table.show("080357_563754")  # layout 2
    assert client.post("/capture").status_code == 200

    response = client.post("/api/randomize/suggest")

    assert response.status_code == 200, response.text
    trays = {t["tray_id"]: t for t in response.json()["trays"]}
    assert sorted(trays) == sorted(LAYOUT_2)
    assert {t: (v["last"]["slot"], v["last"]["a1_corner"]) for t, v in trays.items()} == LAYOUT_2
    assert sorted(t["slot"] for t in trays.values()) == sorted(s["name"] for s in FIXTURE["slots"])
    assert response.json()["experiment_id"] == experiment["id"]


def test_check_with_no_tray_moved_finds_every_tray_out_of_place_and_on_the_same_edge(table, client) -> None:
    experiment = _running_experiment()
    table.show("080357_563754")  # layout 2, and it stays so: nobody moves a tray
    client.post("/capture")
    suggestion = client.post("/api/randomize/suggest").json()

    response = client.post("/api/randomize/check")

    assert response.status_code == 200, response.text
    check = response.json()
    assert check["suggestion_id"] == suggestion["id"]
    trays = {t["tray_id"]: t for t in check["trays"]}
    assert sorted(trays) == sorted(LAYOUT_2)
    assert all(t["breaks_rule"] for t in trays.values())
    assert not [t for t in trays.values() if t["status"] == "in place"]
    # The check's photo is a rig photo, not one of the experiment's stills.
    assert len(database.captures_for_experiment(experiment["id"])) == 1
    # Saved with the experiment: the page reads it back.
    assert client.get("/api/randomize").json()["check"]["id"] == check["id"]
    overlay = client.get(check["overlay"])
    assert overlay.status_code == 200
    assert overlay.headers["content-type"] == "image/jpeg"


def test_suggest_and_check_are_refused_with_no_experiment_running(table, client) -> None:
    table.show("080357_563754")
    assert client.post("/api/randomize/suggest").status_code == 409
    assert client.post("/api/randomize/check").status_code == 409
    assert client.get("/api/randomize").json() == {"experiment": None, "suggestion": None, "check": None}


def test_the_next_suggestion_starts_from_where_the_check_found_the_trays(table, client) -> None:
    _running_experiment()
    table.show("080357_563754")  # layout 2
    client.post("/capture")
    client.post("/api/randomize/suggest")
    table.show("103957_586168")  # the trays moved: layout 12
    client.post("/api/randomize/check")

    trays = client.post("/api/randomize/suggest").json()["trays"]

    layout_12 = {
        1: ("North 1", "NE"), 7: ("North 2", "NE"), 6: ("North 3", "NE"), 11: ("North 4", "SW"),
        8: ("North 5", "NE"), 12: ("North 6", "NE"), 4: ("South 1", "NE"), 5: ("South 2", "NE"),
        9: ("South 3", "SW"), 3: ("South 4", "NE"), 10: ("South 5", "NE"), 2: ("South 6", "NE"),
    }
    assert {t["tray_id"]: (t["last"]["slot"], t["last"]["a1_corner"]) for t in trays} == layout_12
