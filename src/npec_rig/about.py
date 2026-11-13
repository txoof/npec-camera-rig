"""The About page's facts (#390): what the rig runs and the state it is in.

`facts()` reads each fact once, when asked; nothing is stored. `sections()` lays them out for
the page as titled cards of rows, so a new card (manuals, documents) is a new entry there."""

import functools
import re
from datetime import datetime, timedelta, timezone
import os
import shutil
import socket
import subprocess
from pathlib import Path

from npec_rig import database, health, validation
from npec_rig.calibration_store import load_current_calibration
from npec_rig.camera import CameraManager
from npec_rig.captures import read_uptime_s
from npec_rig.settings import db_path

_CHECKOUT = Path(__file__).parent


@functools.cache
def version() -> dict:
    """The code this app runs: its commit, the commit's date, and the branches that point at it
    (a rig is a git checkout, often detached at a branch, #390). Read once: new code needs a
    restart anyway. None for each part git cannot give."""

    def git(*args: str) -> str | None:
        try:
            out = subprocess.run(["git", "-C", str(_CHECKOUT), *args], capture_output=True,
                                 text=True, timeout=5, check=True).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
        return out or None

    commit = git("rev-parse", "--short", "HEAD")
    branches = git("branch", "--all", "--points-at", "HEAD", "--format=%(refname:short)") or ""
    names = sorted({b.removeprefix("origin/") for b in branches.splitlines()
                    if b and not b.startswith("(") and b not in ("origin/HEAD", "origin")})
    return {
        "commit": commit,
        "committed_at": git("log", "-1", "--format=%cI") if commit else None,
        "branches": names,
    }


def facts() -> dict:
    """Every fact, for GET /api/about and the page."""
    focus = CameraManager.instance().focus_status()
    artifact = load_current_calibration()
    status = validation.status(focus)
    current = validation.current_session(artifact.frame_stem) if artifact else None
    starts = database.app_starts("")
    running = database.running_experiment()
    disk = shutil.disk_usage(db_path().parent)
    headroom = health.disk_status()
    camera = health.camera_health()
    return {
        "version": version(),
        "schema_version": database.SCHEMA_VERSION,
        "rig": {"name": socket.gethostname(), "environment": os.environ.get("NPEC_RIG_ENVIRONMENT")},
        "camera": {"state": camera["state"], "detail": camera["detail"]},
        "ai_accelerator": any(Path("/dev").glob("hailo*")),
        "disk": {
            "free_bytes": disk.free, "total_bytes": disk.total,
            **{k: headroom[k] for k in ("bytes_per_day", "days_left", "level")},
        },
        "pi_up_s": read_uptime_s(),
        "app_started_at": starts[-1] if starts else None,
        "experiment": (
            {"id": running["id"], "name": running["name"], "started_at": running["periods"][-1]["started_at"]}
            if running
            else None
        ),
        "focus": focus,
        "calibration": (
            {"stem": artifact.frame_stem, "created_at": artifact.created_at} if artifact else None
        ),
        "validation": {
            "state": status["state"],
            "text": status["text"],
            "completed_at": current["completed_at"] if current else None,
        },
    }


def _gb(n: int) -> str:
    return f"{n / 1e9:.0f} GB"


_DISK_CHIPS = {"ok": ("ok", "Enough"), "yellow": ("warn", "Low"), "red": ("fail", "Very low")}


def _disk_left(disk: dict) -> dict:
    """Days of space left at the rate files were written in the last day (health.disk_status)."""
    days = disk["days_left"]
    value = (f"About {days:,.0f} days at the last day's rate" if days is not None
             else "No files written in the last day")
    return {"label": "Disk space left", "value": value, "status": _DISK_CHIPS[disk["level"]]}


def _time(label: str, iso: str | None, missing: str = "Not known") -> dict:
    """A row whose value is a time: the page shows it in the browser's time zone, with how long
    ago; the UTC text is what shows without JavaScript."""
    if iso is None:
        return {"label": label, "value": missing}
    utc = datetime.fromisoformat(iso).astimezone(timezone.utc)
    return {"label": label, "value": f"{utc:%d %b %Y %H:%M} UTC", "time": iso}


def _without_device_paths(text: str) -> str:
    """The camera's text without the device paths libcamera adds after the model name
    ("arducam_64mp /base/axi/...@1a" reads "arducam_64mp")."""
    return re.sub(r"\s+/\S*[^\s).]", "", text)


def _beside_chip(text: str, word: str) -> str:
    """A status text shown next to its chip, without repeating the chip's word or the date
    the "Validation finished" row already gives ("Validated 2026-11-03" next to a Validated
    chip reads ""; "Not consistent: North 1" next to a Not consistent chip reads "North 1")."""
    rest = text[len(word):] if text.startswith(word) else text
    rest = re.sub(r"^\s*\d{4}-\d{2}-\d{2}", "", rest).lstrip(":; ").strip()
    return rest[:1].upper() + rest[1:]


_CAMERA_CHIPS = {health.CAMERA_OK: ("ok", "Working"), health.CAMERA_OPENING: ("info", "Opening")}


def sections(f: dict) -> list[dict]:
    """The page's cards, from `facts()`. Each is {"title", "status", "rows", "links"}: status a
    (chip kind, word) or None, each row {"label", "value"} with an optional "status" chip and
    "time" (ISO, shown in local time), each link {"label", "href", "new_tab"}. Manuals and links
    to documents (#390) are added here as further cards."""
    v = f["version"]
    branch = ", ".join(v["branches"]) or "no branch"
    version = f"{v['commit']}, {branch}" if v["commit"] else "Not known (not a git checkout)"
    env = f["rig"]["environment"]
    pi_started = (
        (datetime.now(timezone.utc) - timedelta(seconds=f["pi_up_s"])).isoformat()
        if f["pi_up_s"] is not None
        else None
    )
    focus = f["focus"]
    lens = f["focus"]["lens_position"]
    val = f["validation"]
    val_chip = {"validated": ("ok", "Validated"), "not_consistent": ("fail", "Not consistent")}.get(
        val["state"], ("warn", "Not validated")
    )
    exp = f["experiment"]
    return [
        {"title": "Software", "rows": [
            {"label": "Version", "value": version},
            _time("Version date", v["committed_at"]),
            {"label": "Database", "value": f"schema {f['schema_version']}"},
        ]},
        {"title": "Rig", "rows": [
            {"label": "Name", "value": f["rig"]["name"] + (f", {env}" if env else "")},
            {"label": "Camera", "value": _without_device_paths(f["camera"]["detail"]),
             "status": _CAMERA_CHIPS.get(f["camera"]["state"], ("fail", "Fault"))},
            {"label": "AI accelerator", "value": "Found" if f["ai_accelerator"] else "Not found"},
            {"label": "Free disk space",
             "value": f"{_gb(f['disk']['free_bytes'])} of {_gb(f['disk']['total_bytes'])}"},
            _disk_left(f["disk"]),
        ]},
        {"title": "Running", "rows": [
            _time("App started", f["app_started_at"]),
            _time("Pi started", pi_started),
            {"label": "Experiment", "value": exp["name"] if exp else "None running"},
            *([_time("Experiment started", exp["started_at"])] if exp else []),
        ]},
        {"title": "Focus",
         "status": ("ok", "Locked") if focus["locked"] else ("warn", "Not locked"),
         "rows": [{"label": "Lens position", "value": f"{lens:.2f}" if lens is not None else "Not set"}],
         "links": [{"label": "Go to Focus", "href": "/setup/focus", "new_tab": False}]},
        {"title": "Calibration and validation", "rows": [
            _time("Calibration made", f["calibration"]["created_at"] if f["calibration"] else None,
                  "No calibration yet"),
            {"label": "Validation", "value": _beside_chip(val["text"], val_chip[1]), "status": val_chip},
            _time("Validation finished", val["completed_at"], "No finished validation"),
        ], "links": [{"label": "Go to Validation", "href": "/setup/validation", "new_tab": False}]},
    ]
