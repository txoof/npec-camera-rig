import pytest
from fastapi.testclient import TestClient

from npec_rig.app import app

pytestmark = pytest.mark.unit

client = TestClient(app)


def test_without_a_saved_setting_photos_are_saved_at_85_with_full_colour() -> None:
    """Aaron, 2026-11-05: the default is 85 with full colour, which read plant area 0.4% low
    against 1.4% at Pillow's 75 with half colour (metrology log 26.1)."""
    response = client.get("/api/photo-quality")

    assert response.status_code == 200
    assert response.json()["quality"] == 85
    assert response.json()["chroma"] == "4:4:4"


def test_a_changed_setting_is_kept() -> None:
    # Not the default (85, "4:4:4"), so the test fails if nothing is saved.
    response = client.post("/api/photo-quality", json={"quality": 60, "chroma": "4:2:0"})

    assert response.status_code == 200
    now = client.get("/api/photo-quality").json()
    assert (now["quality"], now["chroma"]) == (60, "4:2:0")


@pytest.mark.parametrize(
    "body",
    [
        {"quality": 0, "chroma": "4:4:4"},
        {"quality": 96, "chroma": "4:4:4"},
        {"quality": 85, "chroma": "4:2:2"},
        {"quality": 85},
    ],
)
def test_a_setting_outside_the_choices_is_refused_and_nothing_changes(body) -> None:
    client.post("/api/photo-quality", json={"quality": 90, "chroma": "4:4:4"})

    response = client.post("/api/photo-quality", json=body)

    assert response.status_code == 422
    now = client.get("/api/photo-quality").json()
    assert (now["quality"], now["chroma"]) == (90, "4:4:4")


def test_every_change_is_recorded_with_its_time_newest_first() -> None:
    from datetime import UTC, datetime

    before = datetime.now(UTC)
    client.post("/api/photo-quality", json={"quality": 85, "chroma": "4:4:4"})
    client.post("/api/photo-quality", json={"quality": 95, "chroma": "4:2:0"})
    after = datetime.now(UTC)

    changes = client.get("/api/photo-quality").json()["changes"]

    assert [(c["quality"], c["chroma"]) for c in changes] == [(95, "4:2:0"), (85, "4:4:4")]
    for c in changes:
        assert before <= datetime.fromisoformat(c["changed_at"]) <= after


def test_the_default_taking_effect_is_recorded_as_a_change_at_the_first_photo() -> None:
    """Review of #359: a rig updated to this version switches from 75 with half colour to the
    default at its first photo; the change list says when."""
    from npec_rig.captures import take_photo

    assert client.get("/api/photo-quality").json()["changes"] == []
    _array, _record = take_photo("capture")
    del _array
    take_photo("capture")

    changes = client.get("/api/photo-quality").json()["changes"]
    assert [(c["quality"], c["chroma"]) for c in changes] == [(85, "4:4:4")]


def test_the_same_setting_again_is_not_a_change() -> None:
    client.post("/api/photo-quality", json={"quality": 60, "chroma": "4:2:0"})
    client.post("/api/photo-quality", json={"quality": 60, "chroma": "4:2:0"})

    assert len(client.get("/api/photo-quality").json()["changes"]) == 1


def test_a_stored_setting_photos_cannot_be_saved_at_does_not_stop_a_photo() -> None:
    """Review of #359: a hand-edited row must not lose every scheduled photo after its capture.
    The photo is saved at the default, and the change list says so."""
    from npec_rig.captures import take_photo
    from npec_rig.settings import save_setting

    save_setting("PhotoQuality", {"quality": 85, "chroma": "4:2:2"})
    _array, record = take_photo("capture")
    del _array

    assert record["photo_quality"] == {"quality": 85, "chroma": "4:4:4"}
    changes = client.get("/api/photo-quality").json()["changes"]
    assert [(c["quality"], c["chroma"]) for c in changes] == [(85, "4:4:4")]
