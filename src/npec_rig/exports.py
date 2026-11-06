"""Export an experiment as one zip: its photos and sidecars, experiment.json, a CSV of its photos,
copies of the calibration and validation records they used, a README and a checksum manifest
(#119, first version agreed with Aaron 2026-10-09). A running experiment can be exported too: the
zip holds its photos up to the moment the export started, and the README says it is partial.

**Every table with rows for an experiment is added to its export when that table is built**
(Aaron, 2026-10-09; PLAN.md, *CSV export*): the tray positions (`detection`, M4) and the areas
(`measurement`, M5) each become a CSV here, next to captures.csv.

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
import json
import logging
import re
import shutil
import textwrap
import threading
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from npec_rig import database, dwell, tray_readings
from npec_rig.calibration_store import calibration_root
from npec_rig.captures import experiments_root
from npec_rig.validation_store import validations_root

logger = logging.getLogger(__name__)

_CHUNK = 1 << 20

# What every file and CSV column in an export means. Read at each export, so its wording can
# change without a restart (#65).
FIELDS_FILE = Path(__file__).with_name("export_fields.yaml")


def _fields() -> dict:
    return yaml.safe_load(FIELDS_FILE.read_text(encoding="utf-8"))


def _data_package(fields: dict, held: set[str]) -> bytes:
    """datapackage.json: the Frictionless Data Package with the resources of the CSVs held."""
    package = dict(fields["package"])
    package["resources"] = [r for r in package["resources"] if r["path"] in held]
    return json.dumps(package, indent=2, ensure_ascii=False).encode() + b"\n"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Free space an export must leave on the disk (#65, Aaron, 2026-11-06): the running experiment's
# next COVER_DAYS of photos, at its interval and its photos' average size, and never less than
# MIN_FREE_BYTES. Both are decisions, not measurements: 2 days covers a weekend morning before
# someone notices; 10 GB until the disk monitoring of M3 sets one.
COVER_DAYS = 2
MIN_FREE_BYTES = 10 * 10**9


def _reserve() -> int:
    """Bytes to keep free for the running experiment's photos."""
    running = database.running_experiment()
    if not running or not running.get("interval_s"):
        return MIN_FREE_BYTES
    sizes = expected_sizes(running["id"])
    per_photo = sizes["photos_bytes"] / sizes["photos"] if sizes["photos"] else 0
    per_day = 86_400 / running["interval_s"] * per_photo
    return max(MIN_FREE_BYTES, int(COVER_DAYS * per_day))


def _size(n: float) -> str:
    """As the Experiments page shows sizes: kB, MB to 0.1, GB to 0.01."""
    if n < 1e6:
        return f"{max(1, round(n / 1e3))} kB"
    if n < 1e9:
        return f"{n / 1e6:.1f} MB"
    return f"{n / 1e9:.2f} GB"


def start_export(experiment_id: int, *, data: bool = True, photos: bool = True) -> dict:
    """Record a new export of the data, the photos or both, and build it in the background.
    Returns the export row. Refused when it would leave less free space than `_reserve`."""
    sizes = expected_sizes(experiment_id)
    needed = (sizes["data_bytes"] if data else 0) + (sizes["photos_bytes"] if photos else 0)
    free = shutil.disk_usage(experiments_root()).free
    reserve = _reserve()
    if free - needed < reserve:
        raise database.ExperimentError(
            f"Not enough free space on the rig. This export needs about {_size(needed)}, {_size(free)}"
            f" is free, and {_size(reserve)} must stay free for photos still to come. Export Data"
            " only, or free space first."
        )
    export = database.create_export(experiment_id, now=_now(), data=data, photos=photos)
    threading.Thread(
        target=_build, args=(export["id"], experiment_id), name=f"export-{export['id']}", daemon=True
    ).start()
    return export


# Rough bytes per CSV line and for the README and datapackage.json, for the expected size of an
# export's data: an order of magnitude is all it needs (Aaron, 2026-11-06), from the line lengths
# of a test export, not measured on a real experiment.
_BYTES_PER_PHOTO_LINE = 300
_BYTES_PER_TRAY_LINE = 200
_BYTES_FIXED = 25_000


def expected_sizes(experiment_id: int) -> dict:
    """How large an export of the experiment's data and of its photos would be, without making
    it, so the user knows whether it takes minutes or hours (#65)."""
    experiment = database.get_experiment(experiment_id)
    folder = experiments_root() / experiment["folder"]
    captures = database.captures_for_experiment(experiment_id)
    photos_bytes = 0
    for row in captures:
        rel = _stills_relative(row["path"], experiment["folder"])
        for suffix in (".jpg", ".json"):
            source = folder / "stills" / f"{rel}{suffix}"
            if source.exists():
                photos_bytes += source.stat().st_size
    records = [calibration_root() / f"{stem}.json" for stem in {r["calibration"] for r in captures if r["calibration"]}]
    records += [validations_root() / f"{s}.json" for s in {r["validation"] for r in captures if r["validation"]}]
    data_bytes = (
        _BYTES_FIXED
        + len(captures) * _BYTES_PER_PHOTO_LINE
        + database.tray_reading_count(experiment_id) * _BYTES_PER_TRAY_LINE
        + database.cell_reading_count(experiment_id) * _BYTES_PER_TRAY_LINE
        + sum(path.stat().st_size for path in records if path.exists())
    )
    return {"photos": len(captures), "photos_bytes": photos_bytes, "data_bytes": data_bytes}


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
    # Photos up to the export's start: a running experiment keeps taking them meanwhile.
    export = database.get_export(export_id)
    until = export["started_at"]
    captures = database.captures_for_experiment(experiment_id, until=until)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    slug = slugify(experiment["name"])
    name = f"{slug + '_' if slug else ''}{experiment['folder']}_export_{stamp}"
    out_dir = folder / "exports"
    out_dir.mkdir(exist_ok=True)
    tmp = out_dir / f".{name}.zip.tmp"
    final = out_dir / f"{name}.zip"

    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        z = _Zip(zf)
        missing: list[str] = []
        if export["photos"]:
            for row in captures:
                rel = _stills_relative(row["path"], experiment["folder"])
                for suffix in (".jpg", ".json"):
                    source = folder / "stills" / f"{rel}{suffix}"
                    if source.exists():
                        z.add_file(f"{name}/stills/{rel}{suffix}", source)
        if export["data"]:
            z.add_file(f"{name}/experiment.json", folder / "experiment.json")
            z.add_bytes(f"{name}/captures.csv", _captures_csv(captures, experiment["folder"]))
            z.add_bytes(f"{name}/time-in-table-location.csv", _time_in_table_location_csv(experiment_id, until))
            # Each photo's readings worked out once, for both files (review of #374).
            read = [(row, tray_readings.capture_readings(row)) for row in captures]
            z.add_bytes(f"{name}/tray-readings.csv", _tray_readings_csv(read, experiment["folder"]))
            z.add_bytes(f"{name}/cell-readings.csv", _cell_readings_csv(read, experiment["folder"]))
            missing = _add_records(z, name, captures)
            held = {path.removeprefix(name + "/") for _digest, path in z.sums}
            z.add_bytes(f"{name}/datapackage.json", _data_package(_fields(), held))
        held = {path.removeprefix(name + "/") for _digest, path in z.sums}
        z.add_bytes(f"{name}/README.txt", _readme(experiment, len(captures), missing, until, held).encode())
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


def _time_in_table_location_csv(experiment_id: int, until: str) -> bytes:
    """One line per tray: its hours in each table location (`dwell.hours_per_location`, #332) in
    the photos up to `until`, to 0.01 h."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["tray", *(f"{location}_h" for location in dwell.LOCATIONS)])
    for tray_id, hours in dwell.hours_per_location(experiment_id, until).items():
        writer.writerow([tray_id, *(f"{hours[location]:.2f}" for location in dwell.LOCATIONS)])
    return buffer.getvalue().encode()


# The columns of tray-readings.csv, one line per tray per photo read (#76).
TRAY_READING_COLUMNS = [
    "file", "taken_at", "tray", "location", "plant_area_mm2", "segmenter", "floor_mm2", "not_counted",
    "photo_excluded", "partly_outside", "scale_error_at_tray_top_pct", "band_slot", "no_band_reason",
]


def _tray_readings_csv(read: list[tuple[dict, dict | None]], folder: str) -> bytes:
    """One line per tray in each photo read for its trays (`read`: each photo's rig.db row and its
    `tray_readings.capture_readings`), with
    its plant area as stored and the band of its validation slot, or the reason it has none (#76).
    Photos not read for trays have no lines."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=TRAY_READING_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row, readings in read:
        if readings is None:
            continue
        for tray in sorted(readings["trays"], key=lambda t: (t["tray_id"] is None, t["tray_id"] or 0)):
            band = tray["uncertainty"]
            writer.writerow({
                "file": f"stills/{_stills_relative(row['path'], folder)}.jpg",
                "taken_at": row["taken_at"],
                "tray": "no tag" if tray["tray_id"] is None else tray["tray_id"],
                "location": tray["location"],
                "plant_area_mm2": tray["area_mm2"],
                "segmenter": tray["segmenter"],
                "floor_mm2": tray["floor_mm2"],
                "not_counted": "; ".join(tray["not_counted"]),
                "photo_excluded": readings["exclusion"],
                "partly_outside": tray["partly_outside"],
                "scale_error_at_tray_top_pct": band["band_pct"],
                "band_slot": band["slot"],
                "no_band_reason": band["reason"],
            })
    return buffer.getvalue().encode()


# The columns of cell-readings.csv, one line per cell of each tray per photo read (#364).
CELL_READING_COLUMNS = [
    "file", "taken_at", "tray", "location", "cell", "status", "plant_area_mm2", "segmenter", "cell_rule",
    "tray_not_counted", "photo_excluded", "scale_error_at_tray_top_pct", "band_slot", "no_band_reason",
]


def _cell_readings_csv(read: list[tuple[dict, dict | None]], folder: str) -> bytes:
    """One line per cell of each tray in each photo read for its trays
    (`tray_readings.capture_readings`), for the researcher's own map of trays and cells to
    treatments (#364): the cell's status and plant area, no area when it has none, and its tray's
    location and validation band."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CELL_READING_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row, readings in read:
        if readings is None:
            continue
        for tray in sorted(readings["trays"], key=lambda t: (t["tray_id"] is None, t["tray_id"] or 0)):
            band = tray["uncertainty"]
            for cell in tray["cells"]:
                writer.writerow({
                    "file": f"stills/{_stills_relative(row['path'], folder)}.jpg",
                    "taken_at": row["taken_at"],
                    "tray": tray["tray_id"],
                    "location": tray["location"],
                    "cell": cell["cell"],
                    "status": cell["status"],
                    "plant_area_mm2": cell["area_mm2"],
                    "segmenter": cell["segmenter"],
                    "cell_rule": cell["cell_rule"],
                    "tray_not_counted": "; ".join(tray["not_counted"]),
                    "photo_excluded": readings["exclusion"],
                    "scale_error_at_tray_top_pct": band["band_pct"],
                    "band_slot": band["slot"],
                    "no_band_reason": band["reason"],
                })
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


def _readme(experiment: dict, photos: int, missing: list[str], until: str, held: set[str]) -> str:
    """The README: the experiment, then what each file holds and what each CSV column means, from
    `export_fields.yaml`, for the files `held` only."""
    title = experiment["name"] or f"Experiment started {experiment['periods'][0]['started_at']}"
    periods = "\n".join(
        f"  {p['started_at']} to {p['ended_at'] or 'still running'}" for p in experiment["periods"]
    )
    partial = (
        [f"PARTIAL EXPORT: photos up to {until}. The experiment was still running.", ""]
        if experiment["state"] == "running"
        else []
    )
    lines = partial + [
        f"Export of: {title}",
        f"Researcher: {experiment['researcher'] or 'not recorded'}",
        f"Experiment ID: {experiment['uuid']}",
        f"Exported: {_now()}",
        f"Photos: {photos}",
        "Running periods (UTC):",
        periods,
        "",
    ]
    fields = _fields()
    lines += _wrapped(fields["package"]["description"], "")
    resources = [r for r in fields["package"]["resources"] if r["path"] in held]
    lines += ["", "What is in this folder", ""]
    for entry in resources + fields["other_files"]:
        path = entry["path"]
        if path in held or any(h.startswith(path) for h in held if path.endswith("/")) or path == "MANIFEST.sha256":
            lines += [f"  {path}"] + _wrapped(entry["description"], "      ")
    for resource in resources:
        lines += ["", f"What each column of {resource['path']} means", ""]
        for field in resource["schema"]["fields"]:
            lines += _wrapped(f"{field['name']}: {field['description']}", "  ", "      ")
    if resources and fields.get("table_drawing"):
        lines += [""] + fields["table_drawing"].rstrip("\n").split("\n")
    if missing:
        lines += ["", "Records that were not found on the rig when exporting:"]
        lines += [f"  {m}" for m in missing]
    return "\n".join(lines) + "\n"


def _wrapped(text: str, indent: str, later: str | None = None) -> list[str]:
    return textwrap.wrap(" ".join(text.split()), width=96, initial_indent=indent,
                         subsequent_indent=indent if later is None else later,
                         break_on_hyphens=False, break_long_words=False)
