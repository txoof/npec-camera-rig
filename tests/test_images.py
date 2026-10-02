import threading
import time

import numpy as np
import pytest
from PIL import Image

from npec_rig import images
from tests.helpers import square_detection

pytestmark = pytest.mark.unit


def _counting_recipe(name: str, version: int = 1, delay_s: float = 0.0) -> list:
    calls: list = []

    def render(inputs: dict) -> bytes:
        calls.append(inputs)
        time.sleep(delay_s)
        return f"{name} v{version} {inputs}".encode()

    images.register(images.Recipe(name, version, render))
    return calls


def test_an_image_is_made_once_and_then_read_from_disk() -> None:
    calls = _counting_recipe("t_once")
    first, media_type = images.get("t_once", "source-a", {"x": 1})
    second, _ = images.get("t_once", "source-a", {"x": 1})
    assert first == second and media_type == "image/jpeg"
    assert len(calls) == 1


def test_different_inputs_and_a_new_version_are_new_images() -> None:
    calls = _counting_recipe("t_inputs")
    images.get("t_inputs", "s", {"x": 1})
    images.get("t_inputs", "s", {"x": 2})  # e.g. a round counted anyway: different inputs
    assert len(calls) == 2
    calls_v2 = _counting_recipe("t_inputs", version=2)
    images.get("t_inputs", "s", {"x": 1})  # same inputs, renderer changed
    assert len(calls_v2) == 1


def test_a_missing_file_is_made_again_not_an_error() -> None:
    calls = _counting_recipe("t_missing")
    images.get("t_missing", "s", {"x": 1})
    for path in (images.derived_root() / "t_missing").iterdir():
        path.unlink()
    content, _ = images.get("t_missing", "s", {"x": 1})
    assert content and len(calls) == 2


def test_two_requests_for_the_same_image_make_it_once() -> None:
    calls = _counting_recipe("t_threads", delay_s=0.2)
    threads = [threading.Thread(target=images.get, args=("t_threads", "s", {"x": 1})) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1


def test_pruning_removes_the_least_recently_used() -> None:
    _counting_recipe("t_prune")
    for x in (1, 2, 3):
        images.get("t_prune", "s", {"x": x})
        time.sleep(0.01)
    images.get("t_prune", "s", {"x": 1})  # 1 is now the most recently used
    size = len(b"t_prune v1 {'x': 1}")
    images.prune(max_bytes=2 * size)
    left = sorted(p.name for p in (images.derived_root() / "t_prune").iterdir())
    assert len(left) == 2
    assert images.key_for("t_prune", {"x": 2}) + ".bin" not in left  # the oldest used went


def test_forgetting_a_source_removes_its_images() -> None:
    calls = _counting_recipe("t_forget")
    images.get("t_forget", "validation:abc", {"x": 1})
    images.forget_source("validation:abc")
    images.get("t_forget", "validation:abc", {"x": 1})
    assert len(calls) == 2


def test_tag_detections_are_found_once_per_photograph(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "capture.jpg"
    Image.new("RGB", (64, 48), "white").save(path)
    found = [square_detection(300, 10.5, 20.25, 12.0)]
    runs: list = []

    def detect(frame):
        runs.append(frame.shape)
        return found

    assert images.tag_detections("2026-10-01/000000_000000", path, detect=detect) == found
    assert images.tag_detections("2026-10-01/000000_000000", path, detect=detect) == found  # stored, exact
    assert len(runs) == 1
    monkeypatch.setattr(images, "TAG_DETECTOR_VERSION", images.TAG_DETECTOR_VERSION + 1)
    images.tag_detections("2026-10-01/000000_000000", path, detect=detect)  # a new detector: again
    assert len(runs) == 2


def test_two_requests_for_the_same_photographs_tags_search_it_once(tmp_path) -> None:
    path = tmp_path / "capture.jpg"
    Image.new("RGB", (64, 48), "white").save(path)
    runs: list = []

    def slow_detect(frame):
        runs.append(1)
        time.sleep(0.2)
        return []

    threads = [
        threading.Thread(target=images.tag_detections, args=("2026-10-01/000001_000000", path, slow_detect))
        for _ in range(3)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(runs) == 1


def test_files_the_index_does_not_know_are_swept_once(monkeypatch: pytest.MonkeyPatch) -> None:
    # A crash between writing a file and recording it would otherwise leave it outside the cap.
    _counting_recipe("t_sweep")
    stray = images.derived_root() / "t_sweep" / "left-by-a-crash.bin"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(b"x")
    monkeypatch.setattr(images, "_swept_roots", set())
    images.get("t_sweep", "s", {"x": 1})
    assert not stray.exists()
    assert len(list(stray.parent.iterdir())) == 1  # the image just made


def test_a_reduced_frame_comes_straight_out_at_the_asked_width(tmp_path) -> None:
    path = tmp_path / "big.jpg"
    Image.fromarray(np.full((3000, 4000, 3), 128, dtype=np.uint8)).save(path)
    frame, scale = images.reduced_frame(path, 500)
    assert frame.shape[1] == 500
    assert scale == pytest.approx(500 / 4000)  # against the full width, not the draft's
