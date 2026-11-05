import pytest
from fastapi.testclient import TestClient

from npec_rig.app import app

pytestmark = pytest.mark.unit

client = TestClient(app)


def test_without_a_saved_setting_photos_are_saved_at_pillows_default() -> None:
    """75 with colour at half resolution: what every photo was saved at before #359 (Pillow's
    defaults, metrology log 26)."""
    response = client.get("/api/photo-quality")

    assert response.status_code == 200
    assert response.json()["quality"] == 75
    assert response.json()["chroma"] == "4:2:0"


def test_a_changed_setting_is_kept() -> None:
    response = client.post("/api/photo-quality", json={"quality": 85, "chroma": "4:4:4"})

    assert response.status_code == 200
    now = client.get("/api/photo-quality").json()
    assert (now["quality"], now["chroma"]) == (85, "4:4:4")


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
