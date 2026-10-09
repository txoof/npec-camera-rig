"""Export a stopped experiment as one zip: its photos and sidecars, experiment.json, a CSV of its
photos, copies of the calibration and validation records they used, a README and a checksum
manifest (#119, first version agreed with Aaron 2026-10-09).

The zip is built in a background thread and kept in the experiment's own `exports/` folder, so it
uses twice the disk space of the photos: fine for short test experiments. Downloads in parts are
#121. Every file's SHA-256 is computed while it is written into the zip, and the list goes in
MANIFEST.sha256, which `sha256sum -c MANIFEST.sha256` checks after unzipping. The manifest's own
checksum is stored in the database, for the purge task to check against.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
import threading
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from npec_rig import database
from npec_rig.calibration_store import calibration_root
from npec_rig.captures import experiments_root
from npec_rig.validation_store import validations_root

logger = logging.getLogger(__name__)

_CHUNK = 1 << 20


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def start_export(experiment_id: int) -> dict:
    """Record a new export and build it in the background. Returns the export row."""
    export = database.create_export(experiment_id, now=_now())
    threading.Thread(
        target=_build, args=(export["id"], experiment_id), name=f"export-{export['id']}", daemon=True
    ).start()
    return export


def zip_path(export: dict) -> Path:
    """Where a finished export's zip is on disk."""
    return experiments_root() / export["file"].removeprefix("experiments/")


def _build(export_id: int, experiment_id: int) -> None:
    try:
        _write_zip(export_id, experiment_id)
    except Exception as exc:  # noqa: BLE001 -- recorded on the export, so the page can say why
        logger.exception("Export %s failed", export_id)
        database.fail_export(export_id, now=_now(), error=str(exc) or type(exc).__name__)


class _Zip:
    """A zip being written, keeping each file's SHA-256 for the manifest."""

    def __init__(self, zf: zipfile.ZipFile) -> None:
        self.zf = zf
        self.sums: list[tuple[str, str]] = []

    def add_bytes(self, name: str, data: bytes) -> None:
        self.zf.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
        self.sums.append((hashlib.sha256(data).hexdigest(), name))

    def add_file(self, name: str, path: Path) -> None:
        # Photos are already compressed: stored as they are, read once.
        digest = hashlib.sha256()
        with path.open("rb") as src, self.zf.open(name, "w", force_zip64=True) as dst:
            while chunk := src.read(_CHUNK):
                digest.update(chunk)
                dst.write(chunk)
        self.sums.append((digest.hexdigest(), name))


def _write_zip(export_id: int, experiment_id: int) -> None:
    experiment = database.get_experiment(experiment_id)
    folder = experiments_root() / experiment["folder"]
    captures = database.captures_for_experiment(experiment_id)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    slug = slugify(experiment["name"])
    name = f"{slug + '_' if slug else ''}{experiment['folder']}_export_{stamp}"
    out_dir = folder / "exports"
    out_dir.mkdir(exist_ok=True)
    tmp = out_dir / f".{name}.zip.tmp"
    final = out_dir / f"{name}.zip"

    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        z = _Zip(zf)
        z.add_file(f"{name}/experiment.json", folder / "experiment.json")
        photos = 0
        for row in captures:
            rel = _stills_relative(row["path"], experiment["folder"])
            for suffix in (".jpg", ".json"):
                source = folder / "stills" / f"{rel}{suffix}"
                if source.exists():
                    z.add_file(f"{name}/stills/{rel}{suffix}", source)
            photos += 1
        z.add_bytes(f"{name}/captures.csv", _captures_csv(captures, experiment["folder"]))
        missing = _add_records(z, name, captures)
        z.add_bytes(f"{name}/README.txt", _readme(experiment, photos, missing).encode())
        manifest = "".join(f"{digest}  {path.removeprefix(name + '/')}\n" for digest, path in z.sums)
        zf.writestr(f"{name}/MANIFEST.sha256", manifest, compress_type=zipfile.ZIP_DEFLATED)

    tmp.replace(final)
    database.finish_export(
        export_id,
        now=_now(),
        file=f"experiments/{experiment['folder']}/exports/{final.name}",
        bytes=final.stat().st_size,
        files=len(z.sums),
        manifest_sha256=hashlib.sha256(manifest.encode()).hexdigest(),
    )


def slugify(text: str | None, limit: int = 40) -> str:
    """`A. thaliana Flash Drought!` -> `a-thaliana-flash-drought`: lower case, ASCII letters and
    digits joined by hyphens, at most `limit` characters. Empty for no name."""
    ascii_text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:limit].rstrip("-")


def _stills_relative(path: str, folder: str) -> str:
    """`experiments/<folder>/stills/2026-10-09/123555_307074` -> `2026-10-09/123555_307074`."""
    return path.removeprefix(f"experiments/{folder}/stills/")


def _captures_csv(captures: list[dict], folder: str) -> bytes:
    """One line per photo, every `capture` column plus the photo's file in the zip."""
    buffer = io.StringIO()
    columns = ["file"] + (list(captures[0]) if captures else ["id", "taken_at", "purpose"])
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in captures:
        writer.writerow({"file": f"stills/{_stills_relative(row['path'], folder)}.jpg", **row})
    return buffer.getvalue().encode()


def _add_records(z: _Zip, name: str, captures: list[dict]) -> list[str]:
    """Copy every calibration and validation the photos used; return the ones not found."""
    missing = []
    for stem in sorted({r["calibration"] for r in captures if r["calibration"]}):
        source = calibration_root() / f"{stem}.json"
        if source.exists():
            z.add_file(f"{name}/records/calibrations/{stem}.json", source)
        else:
            missing.append(f"calibration {stem}")
    for session in sorted({r["validation"] for r in captures if r["validation"]}):
        source = validations_root() / f"{session}.json"
        if source.exists():
            z.add_file(f"{name}/records/validations/{session}.json", source)
        else:
            missing.append(f"validation {session}")
    return missing


def _readme(experiment: dict, photos: int, missing: list[str]) -> str:
    title = experiment["name"] or f"Experiment started {experiment['periods'][0]['started_at']}"
    periods = "\n".join(
        f"  {p['started_at']} to {p['ended_at']}" for p in experiment["periods"]
    )
    lines = [
        f"Export of: {title}",
        f"Researcher: {experiment['researcher'] or 'not recorded'}",
        f"Experiment ID: {experiment['uuid']}",
        f"Exported: {_now()}",
        f"Photos: {photos}",
        "Running periods (UTC):",
        periods,
        "",
        "All times are UTC. The chamber's local time is UTC+2.",
        "",
        "What is in this folder",
        "  stills/              every photo (.jpg) and its record (.json), by UTC day",
        "  captures.csv         one line per photo: time, purpose, calibration, validation, lens,",
        "                       focus lock, exposure, gain, flags. Open it in Excel",
        "  experiment.json      the experiment's name, researcher, tray height, notes and periods",
        "  records/             the calibration and validation records the photos were taken under,",
        "                       so every number can be traced",
        "  MANIFEST.sha256      a fingerprint (SHA-256) of every file. To check the copy is",
        "                       complete and unchanged, run in this folder: sha256sum -c MANIFEST.sha256",
        "",
        "A photo with flags in captures.csv is not covered by the validation's uncertainty bands;",
        "the flag says why.",
    ]
    if missing:
        lines += ["", "Records that were not found on the rig when exporting:"]
        lines += [f"  {m}" for m in missing]
    return "\n".join(lines) + "\n"
