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
