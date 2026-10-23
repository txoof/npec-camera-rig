from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from npec_rig import database, health, segmentation
from npec_rig.camera import CameraManager, array_to_jpeg, lens_check
from npec_rig.settings import load_settings, save_setting

logger = logging.getLogger(__name__)

# A decision, not a measurement (docs/metrology-log.md): photos taken while the Pi has been up
# less than this are flagged as not covered by the validation bands. Measured 2026-10-06: a cold
# start recovered over about an hour. Stays a placeholder until a cold-start run on SN001.
COLD_START_WINDOW_S = 3600.0

# Focus-lock position must match the calibration's to this many dioptres (the lens reports
# positions to 0.01; a real refocus moves it by far more).
CALIBRATION_LENS_TOLERANCE = 0.005

# Purposes judged against a validation's bands. Validation and calibration photos make the bands,
# and a tripwire check only finds tags, so none of them is measured against the bands.
_MEASURED_PURPOSES = ("capture",)

_app_start: dict | None = None


def read_boot_id() -> str | None:
    """Linux's random ID for this boot. A new value means the Pi rebooted since it was stored."""
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return None


def read_uptime_s() -> float | None:
    """Seconds since the Pi booted, from the kernel. Does not depend on the wall clock."""
    try:
        return round(time.clock_gettime(time.CLOCK_BOOTTIME), 2)
    except OSError:
        return None


def _save_tick(now: dict) -> None:
    """Store the last tick. A failure is logged, never raised: a photo already taken is still
    saved, and the app still starts."""
    try:
        save_setting("LastTick", now)
    except sqlite3.Error:
        logger.exception("Could not store the last tick")


def _load_tick() -> dict | None:
    try:
        return load_settings().get("LastTick")
    except sqlite3.Error:
        logger.exception("Could not read the last tick")
        return None


def _clock_now() -> dict:
    return {
        "boot_id": read_boot_id(),
        "uptime_s": read_uptime_s(),
        "wall": datetime.now(timezone.utc).isoformat(),
    }


def _gap_since(last: dict | None, now: dict) -> dict:
    """Time since the last tick before `now`. Ticks are written at app start, at each photo and
    at a clean app stop, so after a crash or power cut this is time since the last photo or
    start, not how long the app was down (a regular tick is #62, M3). In the same boot this
    comes from the kernel's uptime and is exact. After a reboot only the wall clock is left,
    which can be wrong after a power cut until the network sets it, so it is recorded for
    information and flags nothing; a negative wall-clock gap is recorded as unknown."""
    if not last:
        return {"same_boot": None, "gap_s": None, "gap_source": None}
    same_boot = last.get("boot_id") is not None and last.get("boot_id") == now["boot_id"]
    if same_boot and last.get("uptime_s") is not None and now["uptime_s"] is not None:
        gap_s = round(now["uptime_s"] - last["uptime_s"], 2)
        return {"same_boot": True, "gap_s": gap_s, "gap_source": "uptime"}
    try:
        gap_s = (
            datetime.fromisoformat(now["wall"]) - datetime.fromisoformat(last["wall"])
        ).total_seconds()
    except (KeyError, TypeError, ValueError):
        gap_s = None
    if gap_s is not None:
        gap_s = round(gap_s, 2) if gap_s >= 0 else None
    if last.get("boot_id") is None or now["boot_id"] is None:
        same_boot = None
    return {"same_boot": same_boot, "gap_s": gap_s, "gap_source": "wall clock"}


def record_app_start() -> dict:
    """Called once when the app starts: the gap since the last tick, then a new tick."""
    global _app_start
    now = _clock_now()
    _app_start = {**now, **_gap_since(_load_tick(), now)}
    _save_tick(now)
    return _app_start


def record_app_stop() -> None:
    """Called when the app stops cleanly, so the next start measures the time it was down."""
    _save_tick(_clock_now())


def uptime_record() -> dict:
    """Pi and app uptime for a photo's sidecar, flagged inside the cold-start window. Also a tick.

    Flags on Pi uptime alone, so a reboot without a power cut is flagged too: the camera may
    have lost power with the Pi. The gap is recorded so a later measurement can narrow this.
    """
    start = _app_start or record_app_start()
    now = _clock_now()
    pi_up_s = now["uptime_s"]
    app_up_s = None
    if pi_up_s is not None and start["uptime_s"] is not None and now["boot_id"] == start["boot_id"]:
        app_up_s = round(pi_up_s - start["uptime_s"], 2)
    if pi_up_s is None:
        reason = "the Pi uptime could not be read"
    elif pi_up_s < COLD_START_WINDOW_S:
        reason = (
            f"taken {pi_up_s / 60:.0f} min after the Pi started, inside the "
            f"{COLD_START_WINDOW_S / 60:.0f} min cold-start window"
        )
    else:
        reason = None
    _save_tick(now)
    return {
        "boot_id": now["boot_id"],
        "pi_up_s": pi_up_s,
        "app_up_s": app_up_s,
        "app_start": start,
        "cold_start_window_s": COLD_START_WINDOW_S,
        "flagged": reason is not None,
        "reason": reason,
    }


# Every full-resolution still has one of these purposes, recorded in its sidecar.
PURPOSES = ("capture", "validation", "calibration", "tripwire")


def photos_root() -> Path:
    """Directory rig photos are written under, one subdirectory per UTC day. Photos are stored
    by owner, not by purpose (#55): until experiments exist, every photo is a rig photo."""
    return Path(os.environ.get("NPEC_RIG_PHOTOS_DIR", "/var/lib/npec-rig/rig"))


def experiments_root() -> Path:
    """Directory each experiment's own folder is made under (`<start date>_<uuid[:8]>`)."""
    return Path(os.environ.get("NPEC_RIG_EXPERIMENTS_DIR", "/var/lib/npec-rig/experiments"))


def _photo_dir(timestamp: datetime, experiment: dict | None) -> tuple[Path, str, str]:
    """The one place a photo's folder is picked: `(folder, path prefix, url prefix)`. The path
    prefix is relative to the data folder, as the `capture` table stores it."""
    day = timestamp.strftime("%Y-%m-%d")
    if experiment is None:
        return photos_root() / day, f"rig/{day}", f"/photos/{day}"
    stills = f"{experiment['folder']}/stills/{day}"
    return experiments_root() / stills, f"experiments/{stills}", f"/experiment-files/{stills}"


def _photo_owner(purpose: str) -> dict | None:
    """The running experiment a photo belongs to, or None for a rig photo. Only Capture photos
    belong to an experiment: calibration, validation and tripwire photos stay in rig/, where
    their pages look for them, and no experiment's purge can reach them."""
    if purpose not in _MEASURED_PURPOSES:
        return None
    try:
        return database.running_experiment()
    except (sqlite3.Error, RuntimeError):
        logger.exception("Could not read the running experiment, saving as a rig photo")
        return None


def take_photo(purpose: str, extra: dict | None = None) -> tuple[np.ndarray, dict]:
    """The one way to take a full-resolution still: take it, build its sidecar, save both.

    Every still (Capture, validation round, calibration, tripwire check) comes through here, so
    a check added to the sidecar reaches every photo. `extra` adds caller fields to the sidecar
    (e.g. the validation session). Returns the frame and the saved record; the caller drops the
    frame as soon as it can (a 64MP frame is about 190 MB). CameraBusyError and CameraFaultError
    (the camera stopped responding, camera_process.py) are not caught.
    """
    if purpose not in PURPOSES:
        raise ValueError(f"unknown photo purpose {purpose!r}, expected one of {PURPOSES}")
    manager = CameraManager.instance()
    # Read before the capture, so the lens check compares the photo against the lock it was
    # taken under.
    focus = manager.focus_status()
    with health.photo_purpose(purpose):
        array, sensor_metadata = manager._capture_full_res()
    health.record_good_photo()
    checks = {
        "lens_check": lens_check(sensor_metadata.get("LensPosition"), focus["lens_position"]),
        "uptime": uptime_record(),
        "camera_fault": health.camera_fault_check(),
    }
    if purpose in _MEASURED_PURPOSES:
        # Imported here: validation.py imports this module (take_photo).
        from npec_rig.validation import photo_check

        checks["validation"] = photo_check(focus)
    sidecar = {
        "purpose": purpose,
        "lens_position": manager.get_lens_position(),
        "roi": manager.get_roi(),
        "focus": focus,
        "sensor_metadata": sensor_metadata,
        **checks,
        # Every reason this photo is not covered by the validation bands, one list for the pages.
        "flags": [check["reason"] for check in checks.values() if check["flagged"]],
        **(extra or {}),
    }
    # Read once, so the folder and the database row cannot disagree if Stop is pressed meanwhile.
    owner = _photo_owner(purpose)
    sidecar["experiment"] = (
        None if owner is None else {k: owner[k] for k in ("id", "uuid", "name", "folder")}
    )
    record = _save_photo(array, sidecar, owner)
    record["capture_id"] = _record_in_database(record)
    return array, record


def _active_calibration():
    # Imported here: calibration_store imports this module (photos_root).
    from npec_rig.calibration_store import load_current_calibration

    return load_current_calibration()


def _active_calibration_stem() -> str | None:
    artifact = _active_calibration()
    return artifact.frame_stem if artifact is not None else None


def _record_in_database(record: dict) -> int | None:
    """Add the photo's `capture` row, return its id. A failure is logged, never raised: the
    photo and its sidecar are already saved, and the sidecar is the full record."""
    sensor = record["sensor_metadata"]
    try:
        return database.record_capture(
            taken_at=record["timestamp"],
            path=record["path"],
            purpose=record["purpose"],
            experiment_id=(record["experiment"] or {}).get("id"),
            calibration=_active_calibration_stem(),
            validation=record.get("validation", {}).get("session"),
            lens_position=sensor.get("LensPosition"),
            focus_locked_at=record["focus"]["lens_position"],
            exposure_us=sensor.get("ExposureTime"),
            analogue_gain=sensor.get("AnalogueGain"),
            flags=record["flags"],
        )
    except (sqlite3.Error, RuntimeError):
        logger.exception("Could not add the photo %s to the database", record["filename"])
        return None


def _save_photo(image: np.ndarray, metadata: dict, experiment: dict | None = None) -> dict:
    """Write a full-res JPEG plus a JSON sidecar of `metadata`, return the combined record.

    Both are written under temporary names and renamed, sidecar first, so a crash never leaves
    half a file and a JPEG the gallery can see always has its sidecar."""
    timestamp = datetime.now(timezone.utc)
    day_dir, path_prefix, url_prefix = _photo_dir(timestamp, experiment)
    day_dir.mkdir(parents=True, exist_ok=True)

    stem = timestamp.strftime("%H%M%S_%f")
    jpeg_path = day_dir / f"{stem}.jpg"
    json_path = day_dir / f"{stem}.json"
    record = {"timestamp": timestamp.isoformat(), **metadata}

    jpeg_tmp = day_dir / f".{stem}.jpg.tmp"
    json_tmp = day_dir / f".{stem}.json.tmp"
    jpeg_tmp.write_bytes(array_to_jpeg(image))
    json_tmp.write_text(json.dumps(record, indent=2, default=str))
    json_tmp.replace(json_path)
    jpeg_tmp.replace(jpeg_path)

    return {
        "date": timestamp.strftime("%Y-%m-%d"),
        "filename": jpeg_path.name,
        "url": f"{url_prefix}/{jpeg_path.name}",
        "path": f"{path_prefix}/{stem}",
        **record,
    }


def _photo_roots(experiment_id: int | None = None) -> list[tuple[Path, str, str]]:
    """Every folder of day folders: `(folder, path prefix, url prefix)`, rig first. With
    `experiment_id`, only that experiment's stills (none before its first start); LookupError
    for an unknown experiment."""
    if experiment_id is not None:
        folder = database.get_experiment(experiment_id)["folder"]
        if folder is None:
            return []
        stills = f"{folder}/stills"
        return [(experiments_root() / stills, f"experiments/{stills}", f"/experiment-files/{stills}")]
    roots = [(photos_root(), "rig", "/photos")]
    if experiments_root().exists():
        for folder in sorted(p for p in experiments_root().iterdir() if p.is_dir()):
            stills = f"{folder.name}/stills"
            roots.append((folder / "stills", f"experiments/{stills}", f"/experiment-files/{stills}"))
    return roots


# A photo's place in time, `YYYY-MM-DDTHHMMSS_ffffff` (its UTC day folder, "T", its file stem).
# Keys sort in time order as plain strings, so the gallery pages back with `before=<key>`.
PHOTO_KEY = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{6}_\d{6}$")
# A gallery `path`: a photo under rig/ or under one experiment's stills.
_PHOTO_PATH = re.compile(r"^(rig|experiments/[A-Za-z0-9_-]+/stills)/(\d{4}-\d{2}-\d{2})/(\d{6}_\d{6})$")


def list_recent_captures(
    limit: int = 12, before: str | None = None, experiment_id: int | None = None
) -> list[dict]:
    """Most recent photos first, from rig/ and every experiment's stills, or only one
    experiment's with `experiment_id`. With `before` (a PHOTO_KEY), only photos taken before it:
    the next page back in time."""
    found: list[tuple[str, str, Path, str, str]] = []
    for root, path_prefix, url_prefix in _photo_roots(experiment_id):
        if not root.exists():
            continue
        newest: list[tuple[str, str, Path, str, str]] = []
        for day_dir in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
            if before is not None and day_dir.name > before[:10]:
                continue
            for jpeg_path in sorted(day_dir.glob("*.jpg"), reverse=True):
                if before is not None and f"{day_dir.name}T{jpeg_path.stem}" >= before:
                    continue
                newest.append((day_dir.name, jpeg_path.stem, jpeg_path, path_prefix, url_prefix))
            if len(newest) >= limit:
                break
        found += newest[:limit]
    found.sort(key=lambda f: (f[0], f[1]), reverse=True)

    entries: list[dict] = []
    for day, stem, jpeg_path, path_prefix, url_prefix in found[:limit]:
        json_path = jpeg_path.with_suffix(".json")
        record: dict = {}
        if json_path.exists():
            try:
                record = json.loads(json_path.read_text())
            except json.JSONDecodeError:
                logger.warning("Corrupt sidecar JSON, skipping metadata: %s", json_path)
        entries.append(
            {
                "date": day,
                "filename": jpeg_path.name,
                "url": f"{url_prefix}/{day}/{jpeg_path.name}",
                "path": f"{path_prefix}/{day}/{stem}",
                "key": f"{day}T{stem}",
                **record,
            }
        )
    return _with_database_rows(entries)


def capture_hours(experiment_id: int | None = None) -> list[dict]:
    """How many photos each UTC hour holds, newest first, as `{"hour": "YYYY-MM-DDTHH", "count",
    "first"}`, `first` being the gallery path of the hour's earliest photo (the gallery's day and
    week tiles). By hour, not day, so the browser can count them by its own local day. With
    `experiment_id`, only that experiment's photos."""
    counts: dict[str, int] = {}
    first: dict[str, tuple[str, str]] = {}  # hour: (stem, path) of its earliest photo
    for root, path_prefix, _url_prefix in _photo_roots(experiment_id):
        if not root.exists():
            continue
        for day_dir in (p for p in root.iterdir() if p.is_dir()):
            for jpeg_path in day_dir.glob("*.jpg"):
                stem = jpeg_path.stem
                hour = f"{day_dir.name}T{stem[:2]}"
                counts[hour] = counts.get(hour, 0) + 1
                if hour not in first or stem < first[hour][0]:
                    first[hour] = (stem, f"{path_prefix}/{day_dir.name}/{stem}")
    return [
        {"hour": h, "count": counts[h], "first": first[h][1]} for h in sorted(counts, reverse=True)
    ]


def photo_file(path: str) -> Path | None:
    """The JPEG for a gallery `path` (as list_recent_captures gives it), or None if there is no
    such photo. Raises ValueError for anything not shaped like a gallery path."""
    match = _PHOTO_PATH.match(path)
    if match is None:
        raise ValueError(f"not a photo path: {path!r}")
    prefix, day, stem = match.groups()
    for root, path_prefix, _url_prefix in _photo_roots():
        if path_prefix == prefix:
            jpeg_path = root / day / f"{stem}.jpg"
            return jpeg_path if jpeg_path.exists() else None
    return None


def _with_database_rows(entries: list[dict]) -> list[dict]:
    """Add each photo's `capture` row as `record` (None for photos from before the database)."""
    paths = [e["path"] for e in entries]
    try:
        rows = database.captures_by_path(paths)
    except (sqlite3.Error, RuntimeError):
        logger.exception("Could not read the capture rows for the gallery")
        rows = {}
    for entry, path in zip(entries, paths):
        entry["record"] = rows.get(path)
    return entries


# Tray heights offered on the experiments page, (label, mm), table surface upward
# to the growing medium (docs/metrology-log.md, section 3). The 4x5 by callipers (its lip is 5 mm
# higher); the others by tape to their top edge, which is the growing medium, one reading each, by
# Aaron, 2026-10-09. Any other value can be typed in.
KNOWN_TRAY_HEIGHTS_MM = (
    ("Black tray", 40.0),
    ("4x5 tray", 100.0),
    ("4x4 tray", 150.0),
    ("1x1 tray", 175.0),
)


# --- Experiment folders ---
# The rules (one running, Resume, what can be edited) are in database.py. This part makes the
# folder at the first start and keeps experiment.json in it, so a copied folder says what it is.


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_experiment(**fields: object) -> dict:
    return database.create_experiment(uuid=str(uuid.uuid4()), created_at=_now(), **fields)


def _write_experiment_json(experiment: dict) -> None:
    folder = experiments_root() / experiment["folder"]
    tmp = folder / ".experiment.json.tmp"
    tmp.write_text(json.dumps(experiment, indent=2))
    tmp.replace(folder / "experiment.json")


def start_experiment(experiment_id: int, *, stop_running: bool = False) -> dict:
    """Start or resume. The first start makes `experiments/<start date>_<uuid[:8]>/` and refuses
    one that already exists, so two experiments can never share a folder."""
    now = _now()
    experiment = database.get_experiment(experiment_id)
    folder = None
    if experiment["state"] == "set up":
        folder = f"{now[:10]}_{experiment['uuid'][:8]}"
        try:
            (experiments_root() / folder).mkdir(parents=True)
        except FileExistsError as exc:
            raise database.ExperimentError(f"the folder {folder} already exists") from exc
    try:
        experiment = database.start_experiment(
            experiment_id,
            now=now,
            folder=folder,
            stop_running=stop_running,
        )
    except BaseException:
        if folder is not None:
            (experiments_root() / folder).rmdir()
        raise
    _write_experiment_json(experiment)
    return experiment


def stop_experiment(experiment_id: int) -> dict:
    experiment = database.stop_experiment(experiment_id, now=_now())
    _write_experiment_json(experiment)
    return experiment


def update_experiment(experiment_id: int, **fields: object) -> dict:
    experiment = database.update_experiment(experiment_id, now=_now(), **fields)
    # A purged experiment's folder is gone; its record is only in the database.
    if experiment["folder"] and experiment["state"] != "purged":
        _write_experiment_json(experiment)
    return experiment


def purge_confirmation(experiment: dict) -> str:
    """The text the user types to purge: the name, or the folder name for an unnamed experiment."""
    return experiment["name"] or experiment["folder"]


def purge_experiment(experiment_id: int, *, confirm: str, override_no_export: bool = False) -> dict:
    """Purge a stopped experiment (PLAN.md, *Purging an experiment*): delete its folder (photos
    and export zips) and its photo rows; its row stays as the record. Refused unless `confirm`
    matches, and, without `override_no_export`, unless a complete export exists."""
    experiment = database.get_experiment(experiment_id)
    if experiment["state"] != "stopped":
        raise database.ExperimentError("only a stopped experiment can be purged")
    if confirm.strip() != purge_confirmation(experiment):
        typed = confirm.strip() or "nothing"
        raise database.ExperimentError(
            f'Nothing was purged: you typed "{typed}", and purging needs exactly '
            f'"{purge_confirmation(experiment)}"'
        )
    if not override_no_export and database.complete_export(experiment_id) is None:
        raise database.ExperimentError(
            "Nothing was purged: this experiment has no complete export"
        )
    # Rows first: if deleting files then fails, no row points at a missing photo.
    experiment = database.purge_experiment(experiment_id, now=_now())
    folder = experiments_root() / experiment["folder"]
    try:
        shutil.rmtree(folder)
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.exception("Purged experiment %s, but its folder could not be deleted", experiment_id)
        raise database.ExperimentError(
            f"the experiment is purged, but its folder {folder} could not be deleted: {exc}"
        ) from exc
    # Its plant masks (#75) are kept apart from the photos, under the same folder name.
    masks = segmentation.masks_root() / "experiments" / experiment["folder"]
    try:
        shutil.rmtree(masks)
    except FileNotFoundError:
        pass
    except OSError:
        logger.exception("Purged experiment %s, but its plant masks in %s could not be deleted", experiment_id, masks)
    return experiment
