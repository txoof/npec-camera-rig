"""The tray randomization page and its API (#343).

The scene is a table drawn by the camera: blue trays (305 x 366 mm, portrait) at an even 3 px/mm,
wherever the test stands them, and tag detection returns each tray's tag: a 4 x 5 tray's in cell
A1 (south-west of the centre, or north-east when turned), a 2 x 2 or 1 x 1 tray's in the middle at
the angle given. Trays stand wherever the researcher puts them (Aaron, 2026-11-04), so the scene
is not on any grid. The tray finder reads the drawn trays as it reads a photo.
"""

import pytest
from fastapi.testclient import TestClient

from npec_rig import captures, database, photo_tags
from npec_rig.app import app
from npec_rig.calibration import CalibrationArtifact, scale_field_from_dict
from npec_rig.calibration_store import save_calibration
from npec_rig.camera import CameraManager, SyntheticBackend
from npec_rig.tags import TagDetection
from tests.helpers import draw_tray, rotate_detection, square_detection

pytestmark = pytest.mark.unit

PX_PER_MM = 3.0
TRAY_PX = (305 * PX_PER_MM, 366 * PX_PER_MM)
TAG_PX = 40 * PX_PER_MM
# Cell A1's centre from the tray's centre with A1 at SW, mm (tray_placement.A1_TAG_TO_CENTRE_MM
# turned round): west and south.
A1_FROM_CENTRE_MM = (-104.0, 141.6)
STEM = "20270101T000000000000"

# Where the trays stand, photo pixels: three along the north, two along the south with the middle
# spot empty, not in straight lines.
SPOTS = [(700, 700), (1700, 760), (2750, 690), (730, 1950), (2720, 2010)]


def _tag(tray_id: int, centre: tuple[float, float], heading) -> TagDetection:
    """The tray's tag: in cell A1 for a 4 x 5 tray (heading "SW" or "NE"), else in the middle at
    `heading` degrees."""
    x, y = centre
    if 1 <= tray_id <= 75:
        sign = 1 if heading == "SW" else -1
        x, y = x + sign * A1_FROM_CENTRE_MM[0] * PX_PER_MM, y + sign * A1_FROM_CENTRE_MM[1] * PX_PER_MM
        return square_detection(tray_id, x, y, TAG_PX)
    return rotate_detection(square_detection(tray_id, x, y, TAG_PX), (x, y), heading)


class Table:
    """The calibration saved; `stand(trays)` puts trays {id: (centre, heading)} on the table for
    the next photo."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        save_calibration(
            CalibrationArtifact(
                created_at="2027-01-01T00:00:00+00:00",
                scale_field=scale_field_from_dict({"coeffs": [1.0, 0.0, 0.0], "mean_px_per_mm": PX_PER_MM, "residual_std_pct": 0.0}),
                frame_stem=STEM,
                lens_position=6.05,
            ),
            stem=STEM,
        )
        self.trays: dict = {}
        monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: [_tag(t, c, h) for t, (c, h) in self.trays.items()])
        table = self

        class Scene(SyntheticBackend):
            def capture_full_res(self):
                frame, metadata = super().capture_full_res()
                frame[:] = 128
                for (x, y), _h in table.trays.values():
                    draw_tray(frame, round(x - TRAY_PX[0] / 2), round(y - TRAY_PX[1] / 2),
                              round(x + TRAY_PX[0] / 2), round(y + TRAY_PX[1] / 2))
                return frame, metadata

        CameraManager.set_instance(CameraManager(Scene(width=3400, height=2700)))

    def stand(self, trays: dict) -> None:
        self.trays = dict(trays)


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch, isolated_calibration_dir: None) -> Table:
    # Its own calibration folder: a calibration saved in the shared one stays the active one for
    # every later test on this worker.
    return Table(monkeypatch)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _running_experiment() -> dict:
    return captures.start_experiment(captures.create_experiment(name="Round 3")["id"])


def _where_told(suggestion: dict, first: dict) -> dict:
    """Every tray stood where the suggestion puts it: at its place's centre, at the heading given
    (a 4 x 5 tray), turned round where it says so (a 2 x 2 tray), any angle otherwise."""
    centres = {p["name"]: tuple(p["centre"]) for p in suggestion["places"]}
    out = {}
    for t in suggestion["trays"]:
        tray = t["tray_id"]
        if t["tray_type"] == "4x5":
            heading = t["heading"]
        elif t["tray_type"] == "2x2":
            heading = first[tray][1] + (180 if t["turn"] else 0)
        else:
            heading = 250
        out[tray] = (centres[t["place"]], heading)
    return out


FOUR_BY_FIVE = {1: (SPOTS[0], "SW"), 2: (SPOTS[1], "NE"), 3: (SPOTS[2], "SW"), 4: (SPOTS[3], "NE"), 5: (SPOTS[4], "SW")}


def test_suggest_reads_where_each_tray_stands_and_which_way_round(table, client) -> None:
    experiment = _running_experiment()
    table.stand(FOUR_BY_FIVE)
    assert client.post("/capture").status_code == 200

    response = client.post("/api/randomize/suggest")

    assert response.status_code == 200, response.text
    suggestion = response.json()
    assert suggestion["experiment_id"] == experiment["id"]
    trays = {t["tray_id"]: t for t in suggestion["trays"]}
    assert {t: v["last"]["heading"] for t, v in trays.items()} == {t: h for t, (_c, h) in FOUR_BY_FIVE.items()}
    # A place where each tray stands, and the empty spot in the south row: two rows of three.
    places = {p["occupant"]: p for p in suggestion["places"]}
    for tray, (centre, _h) in FOUR_BY_FIVE.items():
        assert abs(places[tray]["centre"][0] - centre[0]) < 20
        assert abs(places[tray]["centre"][1] - centre[1]) < 20
    assert set(places[1]["sides"]) == {"north", "west"} and places[1]["label"] == "North row, 1st from west"
    assert [p["label"] for p in suggestion["places"] if p["occupant"] is None] == ["South row, 2nd from west"]
    assert len({t["place"] for t in trays.values()}) == len(FOUR_BY_FIVE)


def test_trays_moved_and_turned_as_suggested_are_all_in_place(table, client) -> None:
    _running_experiment()
    table.stand(FOUR_BY_FIVE)
    client.post("/capture")
    suggestion = client.post("/api/randomize/suggest").json()
    table.stand(_where_told(suggestion, FOUR_BY_FIVE))

    check = client.post("/api/randomize/check").json()

    assert {t["tray_id"]: t["status"] for t in check["trays"]} == {t: "in place" for t in FOUR_BY_FIVE}
    assert not [t for t in check["trays"] if t["breaks_rule"]]


def test_check_with_no_tray_moved_finds_every_tray_out_of_place_and_on_the_same_edge(table, client) -> None:
    experiment = _running_experiment()
    table.stand(FOUR_BY_FIVE)  # and it stays so: nobody moves a tray
    client.post("/capture")
    suggestion = client.post("/api/randomize/suggest").json()

    response = client.post("/api/randomize/check")

    assert response.status_code == 200, response.text
    check = response.json()
    assert check["suggestion_id"] == suggestion["id"]
    trays = {t["tray_id"]: t for t in check["trays"]}
    assert sorted(trays) == sorted(FOUR_BY_FIVE)
    # Every place here has an outer side, so a tray left as it was has its edge row on the edge again.
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
    table.stand(FOUR_BY_FIVE)
    assert client.post("/api/randomize/suggest").status_code == 409
    assert client.post("/api/randomize/check").status_code == 409
    assert client.get("/api/randomize").json() == {"experiment": None, "suggestion": None, "check": None}


def test_the_next_suggestion_starts_from_where_the_check_found_the_trays(table, client) -> None:
    _running_experiment()
    table.stand(FOUR_BY_FIVE)
    client.post("/capture")
    client.post("/api/randomize/suggest")
    # The trays end up elsewhere: tray 1 and tray 5 swap spots, tray 2 is turned.
    moved = {**FOUR_BY_FIVE, 1: (SPOTS[4], "NE"), 5: (SPOTS[0], "SW"), 2: (SPOTS[1], "SW")}
    table.stand(moved)
    client.post("/api/randomize/check")

    trays = client.post("/api/randomize/suggest").json()["trays"]

    assert {t["tray_id"]: t["last"]["heading"] for t in trays} == {t: h for t, (_c, h) in moved.items()}


TWO_BY_TWO = {76: (SPOTS[0], 0), 77: (SPOTS[1], 45), 78: (SPOTS[2], 135), 79: (SPOTS[3], 200), 80: (SPOTS[4], 315)}


def test_two_by_two_trays_moved_and_turned_as_suggested_are_all_in_place(table, client) -> None:
    # Five 2 x 2 trays, their tags fixed in the middle at assorted angles, as on the development
    # table on 4 November.
    _running_experiment()
    table.stand(TWO_BY_TWO)
    client.post("/capture")
    suggestion = client.post("/api/randomize/suggest").json()
    assert {t["tray_type"] for t in suggestion["trays"]} == {"2x2"}
    done = _where_told(suggestion, TWO_BY_TWO)
    table.stand(done)

    check = client.post("/api/randomize/check").json()
    assert {t["tray_id"]: t["status"] for t in check["trays"]} == {t: "in place" for t in TWO_BY_TWO}

    # One tray is put down the other way round from what the page says.
    forgot = sorted(TWO_BY_TWO)[0]
    centre, angle = done[forgot]
    table.stand({**done, forgot: (centre, angle - 180)})

    check = client.post("/api/randomize/check").json()
    assert {t["tray_id"]: t["status"] for t in check["trays"]} == {
        t: "turned" if t == forgot else "in place" for t in TWO_BY_TWO
    }


def test_one_by_one_trays_get_a_place_only_and_are_judged_by_their_place(table, client) -> None:
    # 1 x 1 trays (tag IDs 160, 161) have one well: no heading is suggested or read, and the edge
    # rule does not apply.
    first = {160: (SPOTS[0], 30), 161: (SPOTS[3], 0)}
    _running_experiment()
    table.stand(first)
    client.post("/capture")
    suggestion = client.post("/api/randomize/suggest").json()
    trays = {t["tray_id"]: t for t in suggestion["trays"]}
    assert {t["tray_type"] for t in trays.values()} == {"1x1"}
    assert all(t["heading"] is None and t["turn"] is None for t in trays.values())

    table.stand(_where_told(suggestion, first))
    check = client.post("/api/randomize/check").json()
    assert {t["tray_id"]: t["status"] for t in check["trays"]} == {160: "in place", 161: "in place"}


def test_when_no_layout_keeps_the_rule_the_one_breaking_it_least_is_given_and_marked(table, client) -> None:
    # Two 2 x 2 trays side by side: each has both the north and the south border, so one of its
    # end rows is on the edge again whatever is done. A gate needs a way past (Aaron): the page
    # gets a layout, with the trays that repeat an edge row marked.
    _running_experiment()
    table.stand({76: (SPOTS[0], 0), 77: (SPOTS[1], 90)})
    client.post("/capture")

    response = client.post("/api/randomize/suggest")

    assert response.status_code == 200, response.text
    suggestion = response.json()
    assert suggestion["rule_kept"] is False
    assert all(t["breaks_rule"] for t in suggestion["trays"])

