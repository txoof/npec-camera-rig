import pytest
from fastapi.testclient import TestClient

from npec_rig.app import app

pytestmark = pytest.mark.unit


def test_capture_saves_jpeg_and_sidecar_and_appears_in_gallery() -> None:
    client = TestClient(app)
    response = client.post("/capture")
    assert response.status_code == 200
    record = response.json()
    assert record["filename"].endswith(".jpg")
    assert "timestamp" in record

    response = client.get(record["url"])
    assert response.status_code == 200
    assert response.content[:2] == b"\xff\xd8"

    response = client.get("/api/captures")
    assert response.status_code == 200
    filenames = [item["filename"] for item in response.json()]
    assert record["filename"] in filenames


def test_api_captures_respects_a_non_default_limit() -> None:
    client = TestClient(app)
    for _ in range(3):
        assert client.post("/capture").status_code == 200

    response = client.get("/api/captures", params={"limit": 2})
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_gallery_thumb_and_screen_are_reduced_copies_made_once() -> None:
    from PIL import Image
    import io

    client = TestClient(app)
    path = client.post("/capture").json()["path"]
    thumb = client.get(f"/gallery/image/thumb/{path}")
    screen = client.get(f"/gallery/image/screen/{path}")
    assert thumb.status_code == screen.status_code == 200
    assert thumb.headers["content-type"] == "image/jpeg"
    original = client.get(client.get("/api/captures", params={"limit": 1}).json()[0]["url"]).content
    full_width = Image.open(io.BytesIO(original)).width
    assert Image.open(io.BytesIO(thumb.content)).width == min(480, full_width)
    assert Image.open(io.BytesIO(screen.content)).width == min(1600, full_width)
    assert client.get(f"/gallery/image/thumb/{path}").content == thumb.content


def test_gallery_image_rejects_bad_paths_and_sizes() -> None:
    client = TestClient(app)
    path = client.post("/capture").json()["path"]
    assert client.get(f"/gallery/image/huge/{path}").status_code == 404
    assert client.get("/gallery/image/thumb/rig/2020-01-01/000000_000000").status_code == 404
    assert client.get("/gallery/image/thumb/rig/../etc/passwd").status_code in (404, 422)
    assert client.get("/gallery/image/thumb/etc/2026-10-14/000000_000000").status_code == 422


def test_api_captures_pages_back_with_before() -> None:
    client = TestClient(app)
    for _ in range(3):
        assert client.post("/capture").status_code == 200
    newest = client.get("/api/captures", params={"limit": 2}).json()
    older = client.get("/api/captures", params={"limit": 2, "before": newest[-1]["key"]}).json()
    assert older and older[0]["key"] < newest[-1]["key"]
    assert client.get("/api/captures", params={"before": "yesterday"}).status_code == 422
    hours = client.get("/api/captures/hours").json()
    assert hours and all(set(h) == {"hour", "count"} for h in hours)
