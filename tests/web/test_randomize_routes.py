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
from tests.helpers import rotate_detection, square_detection

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
        self.tags: list[TagDetection] = []
        monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: list(self.tags))

    def show(self, still: str) -> None:
        self.tags = _detections(still)

    def show_tags(self, tags: list[TagDetection]) -> None:
        self.tags = tags


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
    assert {t: (v["last"]["slot"], v["last"]["heading"]) for t, v in trays.items()} == LAYOUT_2
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
    assert {t["tray_id"]: (t["last"]["slot"], t["last"]["heading"]) for t in trays} == layout_12


SLOT_CENTRE = {s["name"]: s["centre"] for s in FIXTURE["slots"]}


def _two_by_two(tray_id: int, slot: str, angle: float) -> TagDetection:
    """A 2 x 2 tray's 40 mm tag (about 195 px), fixed in the middle of the tray, at `angle`."""
    x, y = SLOT_CENTRE[slot]
    return rotate_detection(square_detection(tray_id, x, y, 195), (x, y), angle)


def test_two_by_two_trays_moved_and_turned_as_suggested_are_all_in_place(table, client) -> None:
    # Nine 2 x 2 trays (tag IDs 76 to 84), their tags fixed at assorted angles, as on the
    # development table on 4 November.
    first = {76: ("North 1", 0), 77: ("North 2", 45), 78: ("North 3", 90), 79: ("North 4", 135),
             80: ("North 5", 200), 81: ("South 1", 260), 82: ("South 2", 30), 83: ("South 3", 315),
             84: ("South 4", 170)}
    _running_experiment()
    table.show_tags([_two_by_two(t, slot, a) for t, (slot, a) in first.items()])
    client.post("/capture")

    suggestion = client.post("/api/randomize/suggest").json()

    trays = {t["tray_id"]: t for t in suggestion["trays"]}
    assert sorted(trays) == sorted(first)
    assert {t["tray_type"] for t in trays.values()} == {"2x2"}
    # The researcher does what the page says: each tray to its slot, turned round where told.
    done = {t: (trays[t]["slot"], a + (180 if trays[t]["turn"] else 0)) for t, (_s, a) in first.items()}
    table.show_tags([_two_by_two(t, slot, a) for t, (slot, a) in done.items()])

    check = client.post("/api/randomize/check").json()
    assert {t["tray_id"]: t["status"] for t in check["trays"]} == {t: "in place" for t in first}

    # One tray that had to be turned is put down the same way round as before.
    forgot = next(t for t in sorted(first) if trays[t]["turn"])
    slot, angle = done[forgot]
    table.show_tags([_two_by_two(t, *done[t]) for t in first if t != forgot] + [_two_by_two(forgot, slot, angle - 180)])

    check = client.post("/api/randomize/check").json()
    assert {t["tray_id"]: t["status"] for t in check["trays"]} == {
        t: "turned" if t == forgot else "in place" for t in first
    }


def test_a_one_by_one_tray_gets_a_slot_only_and_is_judged_by_its_slot(table, client) -> None:
    # A 1 x 1 tray (tag ID 160) has one well: no heading is suggested or read.
    _running_experiment()
    table.show_tags([_two_by_two(160, "North 2", 30), _two_by_two(76, "South 5", 0)])
    client.post("/capture")
    trays = {t["tray_id"]: t for t in client.post("/api/randomize/suggest").json()["trays"]}
    assert trays[160]["tray_type"] == "1x1"
    assert trays[160]["heading"] is None and trays[160]["turn"] is None

    # Put in its slot at another angle: in place.
    table.show_tags([_two_by_two(160, trays[160]["slot"], 250),
                     _two_by_two(76, trays[76]["slot"], 180 if trays[76]["turn"] else 0)])
    check = client.post("/api/randomize/check").json()
    assert {t["tray_id"]: t["status"] for t in check["trays"]} == {160: "in place", 76: "in place"}
