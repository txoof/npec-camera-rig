"""Time lapse videos of a tray or a cell over an experiment (#64).

The plan is in issue #64 (2026-11-20). Nothing is segmented again: each frame is drawn from a
photo and what its reading stored (outline, cells, areas, masks), and its numbers are those of
`tray_readings.capture_readings`, the same the Gallery shows.
"""
from __future__ import annotations

import json
import logging
import multiprocessing
import os
import re
import resource
import secrets
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import cv2
import numpy as np
from PIL import Image

from npec_rig import captures, database, dwell, images, tray_readings
from npec_rig.text_render import text_layer
from npec_rig.tray_placement import TRAY_SIZE_MM

logger = logging.getLogger(__name__)

# Rig times are UTC; the chamber keeps Dutch local time (CLAUDE.md).
CHAMBER_TIME = ZoneInfo("Europe/Amsterdam")
# Frames per hour a request may ask for (Aaron, 2026-11-20).
PER_HOUR = (1, 2, 5)
# A tray with one of these is not where its reading says, or is not one tray (the trial of
# 2026-11-17, #64).
_NOT_USABLE = {"no tag", "tag seen, tray not found in the photo", "two tags in one tray outline"}
# Whole-tray frames: 2 px/mm, enough to see each plant (the trial: 610 x 732 px).
TRAY_PX_PER_MM = 2.0
# The label under each frame: its lines, their height.
LABEL_LINES, LINE_PX = 4, 26
LABEL_SCALE = 0.55  # text_render's size: about 19 px


def _step(taken_at: str, per_hour: int) -> tuple:
    """The step of the clock a photo falls in: steps of 60 / per_hour minutes from each UTC hour."""
    t = datetime.fromisoformat(taken_at)
    return t.date(), t.hour, t.minute * per_hour // 60


def usable_tray(readings: dict | None, tray_id: int) -> dict | None:
    """Tray `tray_id` of a photo's readings (`capture_readings`) when a frame can be made of it:
    the photo has no exclusion, and the tray is placed by its own tag with an outline and cells.
    None otherwise."""
    if readings is None or readings["status"] != "read" or readings["exclusion"] is not None:
        return None
    trays = [t for t in readings["trays"] if t["tray_id"] == tray_id]
    if len(trays) != 1:
        return None
    tray = trays[0]
    if (tray["placement"] != "placed" or not tray["outline_px"] or not tray["cells"] or tray["not_counted"]
            or _NOT_USABLE & set(tray["warnings"]) or upright(tray) is None):
        return None
    return tray


def upright(tray: dict) -> tuple[np.ndarray, tuple[int, int]] | None:
    """The homography from full-size photo pixels to tray `tray` upright, cell A1 at the bottom
    left, at TRAY_PX_PER_MM, and the frame's size; None when it cannot be worked out. The corners
    of the tray's outline are matched one to one with its corner cells (A1, D1, D5 and A5 on a
    4 x 5 tray), so a turn in a shuffle does not turn the picture. A tray of one column or one row
    has no corner cells to turn it by, and a match that would mirror the picture is refused."""
    cells = {c["cell"]: c["centre_px"] for c in tray["cells"]}
    cols = sorted({name[0] for name in cells})
    rows = sorted({int(name[1:]) for name in cells})
    corner_names = [f"{cols[0]}{rows[0]}", f"{cols[-1]}{rows[0]}", f"{cols[-1]}{rows[-1]}", f"{cols[0]}{rows[-1]}"]
    if len(cols) < 2 or len(rows) < 2 or not set(corner_names) <= cells.keys():
        return None
    outline = np.asarray(tray["outline_px"], dtype=np.float64)
    order = [int(np.argmin(np.hypot(*(outline - cells[name]).T))) for name in corner_names]
    if len(set(order)) != 4:
        return None
    # In photo pixels (y down), A1 to D1 then A1 to A5 must turn the way right then up do.
    a1, d1, _, a5 = (np.asarray(cells[name], dtype=np.float64) for name in corner_names)
    u, v = d1 - a1, a5 - a1
    if u[0] * v[1] - u[1] * v[0] >= 0:
        return None
    w, h = TRAY_SIZE_MM[0] * TRAY_PX_PER_MM, TRAY_SIZE_MM[1] * TRAY_PX_PER_MM
    target = np.float32([[0, h], [w, h], [w, 0], [0, 0]])
    return cv2.getPerspectiveTransform(np.float32(outline[order]), target), (round(w), round(h))


def choose_frames(experiment_id: int, *, tray_id: int, start: datetime, end: datetime, per_hour: int) -> dict:
    """The photos of tray `tray_id` that become frames, from `start` up to `end`: in each step of
    the clock (`per_hour` steps an hour), the first photo with a usable tray (`usable_tray`).
    `frames`: one dict per frame, oldest first, with the photo's `capture` row, its `readings` and
    the `tray`. `skipped`: the steps that had photos but none usable, not counting steps with the
    lights off in every photo."""
    if per_hour not in PER_HOUR:
        raise ValueError(f"per_hour must be one of {PER_HOUR}")
    captures = {c["id"]: c for c in database.captures_for_experiment(experiment_id)}
    first, last = start.isoformat(), end.isoformat()
    by_step: dict[tuple, list[dict]] = {}
    for p in database.experiment_tray_positions(experiment_id):
        if p["tray_id"] == tray_id and first <= p["taken_at"] < last:
            by_step.setdefault(_step(p["taken_at"], per_hour), []).append(captures[p["capture_id"]])
    locations = dwell.LocationFinder()
    frames, skipped = [], 0
    for step in sorted(by_step):
        dark = True
        for capture in by_step[step]:
            readings = tray_readings.capture_readings(capture, history=False, locations=locations)
            tray = usable_tray(readings, tray_id)
            if tray is not None:
                frames.append({"capture": capture, "readings": readings, "tray": tray})
                break
            dark = dark and readings is not None and readings["exclusion"] == "lights off"
        else:
            skipped += 0 if dark else 1
    return {"frames": frames, "skipped": skipped}


def frame_values(experiment: dict, frame: dict, *, method: str) -> dict:
    """What frame `frame` (from `choose_frames`) of `experiment` says, in the Gallery's words: the
    time in UTC and in chamber time, the day of the experiment (day 1 is its first 24 h), the area
    method's name, the tray's plant area by it, and the band of the tray's slot or the reason there
    is none. `method` is the key of one of `tray_readings.AREA_METHODS`."""
    m = next(m for m in tray_readings.AREA_METHODS if m["key"] == method)
    taken = datetime.fromisoformat(frame["capture"]["taken_at"])
    started = datetime.fromisoformat(experiment["periods"][0]["started_at"])
    tray = frame["tray"]
    area = tray[m["area"]]
    floor = tray[m["floor"]] if m["floor"] else None
    if area is None:
        area_text = "not worked out"
    elif floor is not None and area < floor:
        area_text = f"under {floor} mm²"
    else:
        area_text = f"{round(area):,} mm²"
    band = tray["uncertainty"]
    band_text = f"±{band['band_pct']:.1f}%, {band['slot']}" if band["band_pct"] is not None else band["reason"]
    return {
        # An experiment with no name is named by its start, as researchers need not type one.
        "experiment": experiment.get("name") or f"Experiment of {started:%Y-%m-%d %H:%M} UTC",
        "utc": f"{taken:%Y-%m-%d %H:%M} UTC",
        "chamber": f"{taken.astimezone(CHAMBER_TIME):%H:%M} chamber time",
        "day": (taken - started).days + 1,
        "tray_id": tray["tray_id"],
        "method": m["name"],
        "area": area_text,
        "band": band_text,
    }


def draw_frame(frame: dict, values: dict) -> Image.Image:
    """Frame `frame` (from `choose_frames`) as a picture: its tray upright (`upright`) and, under
    it, the label of `values` (`frame_values`). The photo is decoded at half size, enough for
    2 px/mm and a quarter of the memory of a full-size decode."""
    homography, (w, h) = upright(frame["tray"])
    with Image.open(captures.photo_file(frame["capture"]["path"])) as photo:
        full_w, _ = photo.size
        photo.draft("RGB", (photo.width // 2, photo.height // 2))
        rgb = np.asarray(photo.convert("RGB"))
    scale = rgb.shape[1] / full_w
    homography = homography @ np.diag([1 / scale, 1 / scale, 1.0])
    tray = cv2.warpPerspective(rgb, homography, (w, h), flags=cv2.INTER_AREA)
    canvas = np.full((h + LABEL_LINES * LINE_PX + 8, w, 3), 255, dtype=np.uint8)
    canvas[:h] = tray
    lines = [
        f"{values['experiment']}   Tray {values['tray_id']}   Day {values['day']}",
        f"{values['utc']}   {values['chamber']}",
        f"{values['method']}: {values['area']}",
        f"Scale error at tray top: {values['band']}",
    ]
    with text_layer(canvas) as text:
        for i, line in enumerate(lines):
            text.text(line, (8, h + (i + 1) * LINE_PX), LABEL_SCALE, (20, 20, 20))
    return Image.fromarray(canvas)


# The trays offered for a video: those found in the experiment's latest photos. A full scan of a
# long experiment's readings would make the page slow to open.
RECENT_PHOTOS = 200


def experiment_trays(experiment_id: int) -> list[int]:
    """The tray IDs found in the experiment's latest RECENT_PHOTOS photos, lowest first."""
    ids = [c["id"] for c in database.captures_for_experiment(experiment_id)[-RECENT_PHOTOS:]]
    return sorted({p["tray_id"] for p in database.experiment_tray_positions(experiment_id, ids)})


# --- The video job ---------------------------------------------------------------------------------
# Frames per second of every video, as the trial's (#64): 417 hourly frames play in about 35 s.
FPS = 12
# The trial's whole-tray video: 17,924,271 bytes for 417 frames (#64, 2026-11-17). An estimate
# from that one video, not a measurement of this one.
TRIAL_BYTES_PER_FRAME = 42_984
# The child making a video may reserve at most this much memory, so a large request fails alone
# and never stops the camera (#430). A starting value, to be measured on development (#64).
MEMORY_LIMIT_BYTES = 2 * 1024**3
_ID = re.compile(r"^\d{8}T\d{6}-[0-9a-f]{6}$")


class VideoBusy(RuntimeError):
    """A video is being made: one at a time, so another person's is never cancelled."""


class VideoUnavailable(RuntimeError):
    """Videos cannot be made on this rig: the reason, in words."""


def videos_root() -> Path:
    """Where videos are made and kept until downloaded: beside the derived images, not in their
    store, whose start-up sweep removes every file its index does not know (images.py)."""
    return images.derived_root().parent / "timelapse"


def unavailable() -> str | None:
    """Why no video can be made on this rig, or None when one can."""
    return None if shutil.which("ffmpeg") else "ffmpeg is not installed on this rig, so videos cannot be made."


_lock = threading.Lock()
_running: dict = {}


def start(request: dict) -> dict:
    """Start making the video of `request` (experiment_id, tray_id, start, end, per_hour,
    method) in a child process: its id. The finished video of an earlier request is removed
    first, so the rig holds one at a time. Raises VideoUnavailable, VideoBusy, or ValueError for a
    request that cannot be made."""
    if request["per_hour"] not in PER_HOUR:
        raise ValueError(f"per_hour must be one of {PER_HOUR}")
    if not any(m["key"] == request["method"] for m in tray_readings.AREA_METHODS):
        raise ValueError(f"unknown area method {request['method']!r}")
    database.get_experiment(request["experiment_id"])  # LookupError when there is none
    reason = unavailable()
    if reason:
        raise VideoUnavailable(reason)
    with _lock:
        if _being_made() is not None:
            raise VideoBusy("A video is being made. Try again when it is done.")
        clear()
        video_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{secrets.token_hex(3)}"
        folder = videos_root() / video_id
        folder.mkdir(parents=True)
        _write_progress(folder, {"state": "choosing"})
        # Spawned, never forked: the server runs threads (camera_process.py).
        process = multiprocessing.get_context("spawn").Process(
            target=_make, args=(request, str(folder)), name=f"timelapse-{video_id}", daemon=True)
        process.start()
        _running.update(id=video_id, process=process)
    return {"id": video_id}


def progress(video_id: str) -> dict:
    """Where video `video_id` is: `state` choosing, drawing, ready, failed, or gone (removed, or
    replaced by a newer video), with the frames chosen, done and skipped, and the estimated size."""
    folder = _folder(video_id)
    try:
        state = json.loads((folder / "progress.json").read_text())
    except (OSError, ValueError):
        return {"state": "gone"}
    if state["state"] in ("choosing", "drawing"):
        process = _running.get("process") if _running.get("id") == video_id else None
        if process is None or not process.is_alive():
            state = {**state, "state": "failed", "error": "The video was stopped before it was finished."}
    return state


def video_file(video_id: str) -> Path | None:
    """The finished video `video_id`, or None."""
    file = _folder(video_id) / "video.mp4"
    return file if progress(video_id)["state"] == "ready" and file.exists() else None


def remove(video_id: str) -> None:
    """Remove video `video_id`: it has been downloaded in full."""
    shutil.rmtree(_folder(video_id), ignore_errors=True)


def clear() -> None:
    """Remove every video and every unfinished one (at app start, and before a new one): the rig
    keeps as few as possible (Aaron, 2026-11-20). One still being made is left alone."""
    root = videos_root()
    if not root.exists():
        return
    making = _being_made()
    for folder in root.iterdir():
        if folder.name != making:
            shutil.rmtree(folder, ignore_errors=True) if folder.is_dir() else folder.unlink(missing_ok=True)


def _being_made() -> str | None:
    """The id of the video being made, or None. Its process may outlive its last frame by a moment:
    a video is being made while its progress says so and its process is alive."""
    process, video_id = _running.get("process"), _running.get("id")
    if process is None or not process.is_alive():
        return None
    try:
        state = json.loads((_folder(video_id) / "progress.json").read_text())["state"]
    except (OSError, ValueError, KeyError):
        return None
    return video_id if state in ("choosing", "drawing") else None


def _folder(video_id: str) -> Path:
    if not _ID.match(video_id):
        return videos_root() / "not-a-video"
    return videos_root() / video_id


def _write_progress(folder: Path, state: dict) -> None:
    tmp = folder / "progress.json.tmp"
    tmp.write_text(json.dumps(state))
    os.replace(tmp, folder / "progress.json")


def _make(request: dict, folder: str) -> None:
    """In the child process: choose the frames, draw each one and pipe it to ffmpeg, then rename
    the finished file. Frames never touch the disk."""
    out = Path(folder)
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
    os.nice(10)
    cv2.setNumThreads(1)
    try:
        experiment = database.get_experiment(request["experiment_id"])
        chosen = choose_frames(
            request["experiment_id"], tray_id=request["tray_id"], start=datetime.fromisoformat(request["start"]),
            end=datetime.fromisoformat(request["end"]), per_hour=request["per_hour"])
        frames = chosen["frames"]
        state = {"state": "drawing", "frames": len(frames), "done": 0, "skipped": chosen["skipped"],
                 "estimated_bytes": len(frames) * TRIAL_BYTES_PER_FRAME}
        _write_progress(out, state)
        if not frames:
            _write_progress(out, {**state, "state": "failed", "error": "No usable photo of this tray in this time."})
            return
        encoder = None
        for i, frame in enumerate(frames):
            image = draw_frame(frame, frame_values(experiment, frame, method=request["method"]))
            if encoder is None:
                encoder = subprocess.Popen(
                    ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                     "-s", f"{image.width}x{image.height}", "-r", str(FPS), "-i", "-", "-threads", "2",
                     "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                     "-f", "mp4", str(out / "video.part")],
                    stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            encoder.stdin.write(image.tobytes())
            _write_progress(out, {**state, "done": i + 1})
        _, err = encoder.communicate()
        if encoder.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {err.decode(errors='replace')[-300:]}")
        os.replace(out / "video.part", out / "video.mp4")
        _write_progress(out, {**state, "done": len(frames), "state": "ready",
                              "bytes": (out / "video.mp4").stat().st_size})
    except Exception as exc:  # noqa: BLE001 -- every failure is shown on the page, in words
        logger.exception("Time lapse %s failed", out.name)
        try:
            _write_progress(out, {"state": "failed", "error": str(exc) or type(exc).__name__})
        except OSError:
            pass
