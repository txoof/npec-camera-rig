"""Export an experiment in parts: its photos and their records, experiment.json, the CSVs,
copies of the calibration and validation records the photos used, a README and a checksum list
per part (#119, #65; parts zipped while they download, #368, Aaron 2026-11-06). A running
experiment can be exported too: the export holds its photos up to the moment it was made, and the
README says it is partial.

**Every table with rows for an experiment is added to its export when that table is built**
(Aaron, 2026-10-09; PLAN.md, *CSV export*).

Nothing is stored on the rig. Export records what was ticked and the time the photos stop at;
each part is zipped while it downloads, straight from the photos, so the rig needs no free space
for it and a half-full card can still be downloaded. Part 0 holds the README and, with Data
ticked, the data; parts 1 and on hold the photos, at most PART_BYTES each, a photo always with its
record. Every part unzips into the same folder and holds its own checksum list,
MANIFEST-partNN.sha256 (`sha256sum -c` in that folder). A part sent in full is recorded, and an
export with the photos is complete for Purge once every photo part was sent in full.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import textwrap
import unicodedata
import zipfile
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import yaml

from npec_rig import database, dwell, tray_readings
from npec_rig.calibration_store import calibration_root
from npec_rig.captures import experiments_root
from npec_rig.validation_store import validations_root


_CHUNK = 1 << 20

# The most photo bytes in one part (Aaron, 2026-11-06): a decision. A failed download costs at
# most this much again.
PART_BYTES = 10**9

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


def start_export(experiment_id: int, *, data: bool = True, photos: bool = True) -> dict:
    """Record a new export of the data, the photos or both, of the photos taken up to now. Ready
    at once: its parts are zipped as they download. Returns the export with its parts."""
    export = database.create_export(experiment_id, now=_now(), data=data, photos=photos)
    photo_parts = len(_photo_parts(export)) if photos else 0
    database.ready_export(export["id"], now=_now(), photo_parts=photo_parts)
    return export_with_parts(export["id"])


def export_with_parts(export_id: int) -> dict:
    """The export row and its parts: n, photos, and bytes (the exact size of a photo part's zip;
    for part 0, the expected size of the data), and whether each was sent in full."""
    export = database.get_export(export_id)
    sent = database.parts_sent(export_id)
    parts = [{"n": 0, "photos": 0, "bytes": _expected_data_bytes(export) if export["data"] else 2_000}]
    if export["photos"]:
        top = _top(export)
        for i, files in enumerate(_photo_parts(export), start=1):
            parts.append({"n": i, "photos": len({name.rsplit(".", 1)[0] for name, _p, _s in files}),
                          "bytes": _zip_length(top, i, files)})
    for part in parts:
        part["sent"] = part["n"] in sent
    return {**export, "parts": parts}


def _top(export: dict) -> str:
    """The folder every part unzips into: the experiment's name and folder and the export's time."""
    experiment = database.get_experiment(export["experiment_id"])
    slug = slugify(experiment["name"])
    stamp = datetime.fromisoformat(export["started_at"]).strftime("%Y%m%dT%H%M%S")
    return f"{slug + '_' if slug else ''}{experiment['folder']}_export_{stamp}"


def _photo_parts(export: dict) -> list[list[tuple[str, Path, int]]]:
    """The photos up to the export's time, oldest first, with their records, in parts of at most
    PART_BYTES (a photo larger than that alone): (name in the zip, file, size)."""
    experiment = database.get_experiment(export["experiment_id"])
    folder = experiments_root() / experiment["folder"]
    parts: list[list] = [[]]
    size = 0
    for row in database.captures_for_experiment(experiment["id"], until=export["started_at"]):
        rel = _stills_relative(row["path"], experiment["folder"])
        pair = []
        for suffix in (".jpg", ".json"):
            source = folder / "stills" / f"{rel}{suffix}"
            if source.exists():
                pair.append((f"stills/{rel}{suffix}", source, source.stat().st_size))
        pair_size = sum(entry[2] for entry in pair)
        if parts[-1] and size + pair_size > PART_BYTES:
            parts.append([])
            size = 0
        parts[-1].extend(pair)
        size += pair_size
    return [part for part in parts if part]


class _Pipe:
    """A write-only stream the zip writes into: the download takes what was written so far. With
    `keep` False it only counts, for the zip's exact length."""

    def __init__(self, keep: bool = True) -> None:
        self.chunks: list[bytes] = []
        self.position = 0
        self.keep = keep

    def write(self, data: bytes) -> int:
        if self.keep:
            self.chunks.append(bytes(data))
        self.position += len(data)
        return len(data)

    def tell(self) -> int:
        return self.position

    def flush(self) -> None:
        pass

    def take(self) -> bytes:
        out = b"".join(self.chunks)
        self.chunks.clear()
        return out


def _photo_zip(top: str, n: int, files: list[tuple[str, Path, int]], pipe: _Pipe | None = None) -> Iterator[bytes]:
    """A photo part's zip, as it is written: photos stored as they are (already compressed), each
    file's SHA-256 worked out while it is sent, and the part's checksum list last. With a
    counting `pipe`, the files are left empty: only the zip's own bytes are counted."""
    count_only = pipe is not None
    pipe = pipe or _Pipe()
    sums = []
    with zipfile.ZipFile(pipe, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        for name, source, size in files:
            digest = hashlib.sha256()
            with zf.open(f"{top}/{name}", "w", force_zip64=True) as dst:
                if not count_only:
                    with source.open("rb") as src:
                        while chunk := src.read(_CHUNK):
                            digest.update(chunk)
                            dst.write(chunk)
                            if len(pipe.chunks) > 4:
                                yield pipe.take()
            sums.append(f"{digest.hexdigest()}  {name}\n")
            yield pipe.take()
        zf.writestr(f"{top}/MANIFEST-part{n:02d}.sha256", "".join(sums))
    yield pipe.take()


def _zip_length(top: str, n: int, files: list[tuple[str, Path, int]]) -> int:
    """The part's exact length, sent ahead so the browser shows progress: the zip's own bytes,
    counted with the files left empty, plus the files. The zip's bytes do not depend on the files'
    sizes while the part stays under 4 GiB (no zip64 sizes or offsets in its directory), which
    PART_BYTES keeps it well under."""
    pipe = _Pipe(keep=False)
    for _ in _photo_zip(top, n, files, pipe):
        pass
    return pipe.position + sum(size for _name, _path, size in files)


def part_download(export_id: int, n: int) -> tuple[str, int, Iterator[bytes]]:
    """A part's file name, exact length and contents as they are made. Recorded as sent once its
    last byte has been handed on."""
    export = database.get_export(export_id)
    if database.get_experiment(export["experiment_id"])["state"] == "purged":
        raise database.ExperimentError("this experiment was purged: its photos are gone")
    top = _top(export)
    if n == 0:
        body = _part_zero(export, top)
        chunks: Iterator[bytes] = iter([body])
        length = len(body)
    else:
        parts = _photo_parts(export) if export["photos"] else []
        if not 1 <= n <= len(parts):
            raise LookupError(f"export {export_id} has no part {n}")
        files = parts[n - 1]
        length = _zip_length(top, n, files)
        chunks = _photo_zip(top, n, files)

    def body_then_record() -> Iterator[bytes]:
        yield from chunks
        database.record_part_sent(export_id, n, now=_now())

    return f"{top}_part{n:02d}.zip", length, body_then_record()


def _part_zero(export: dict, top: str) -> bytes:
    """Part 0, made whole before it is sent: the README and, with Data ticked, the data."""
    experiment = database.get_experiment(export["experiment_id"])
    folder = experiments_root() / experiment["folder"]
    until = export["started_at"]
    captures = database.captures_for_experiment(experiment["id"], until=until)
    entries: list[tuple[str, bytes]] = []
    missing: list[str] = []
    if export["data"]:
        entries.append(("experiment.json", (folder / "experiment.json").read_bytes()))
        entries.append(("captures.csv", _captures_csv(captures, experiment["folder"])))
        entries.append(("time-in-table-location.csv", _time_in_table_location_csv(experiment["id"], until)))
        # Each photo's readings worked out once, for both files (review of #374).
        read = [(row, tray_readings.capture_readings(row)) for row in captures]
        entries.append(("tray-readings.csv", _tray_readings_csv(read, experiment["folder"])))
        entries.append(("cell-readings.csv", _cell_readings_csv(read, experiment["folder"])))
        records, missing = _records(captures)
        entries += records
        entries.append(("datapackage.json", _data_package(_fields(), {name for name, _ in entries})))
    held = {name for name, _ in entries} | ({"stills/"} if export["photos"] else set())
    parts = 1 + (export["photo_parts"] or 0)
    entries.append(("README.txt", _readme(experiment, len(captures), missing, until, held, parts).encode()))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            zf.writestr(f"{top}/{name}", data)
        sums = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in entries)
        zf.writestr(f"{top}/MANIFEST-part00.sha256", sums)
    return buffer.getvalue()


# Bytes per CSV line in the download (the zip compresses the CSVs), and for the README,
# datapackage.json, manifest and experiment.json, for the expected size of an export's data: an
# order of magnitude is all it needs (Aaron, 2026-11-06). From export 4 on npec-rig-01
# (2026-11-06, 4303 photos), a development check: captures 19, tray-readings 17, cell-readings 16
# compressed bytes a line; the other files 7 kB. Records are stored uncompressed.
_BYTES_PER_LINE = 20
_BYTES_FIXED = 7_000


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
    return {"photos": len(captures), "photos_bytes": photos_bytes, "data_bytes": _data_bytes(experiment_id, captures)}


def _data_bytes(experiment_id: int, captures: list[dict]) -> int:
    records = [calibration_root() / f"{stem}.json" for stem in {r["calibration"] for r in captures if r["calibration"]}]
    records += [validations_root() / f"{s}.json" for s in {r["validation"] for r in captures if r["validation"]}]
    return (
        _BYTES_FIXED
        + (len(captures) + database.tray_reading_count(experiment_id) + database.cell_reading_count(experiment_id))
        * _BYTES_PER_LINE
        + sum(path.stat().st_size for path in records if path.exists())
    )


def _expected_data_bytes(export: dict) -> int:
    captures = database.captures_for_experiment(export["experiment_id"], until=export["started_at"])
    return _data_bytes(export["experiment_id"], captures)


def zip_path(export: dict) -> Path:
    """Where an export stored on the rig before #368 is on disk."""
    return experiments_root() / export["file"].removeprefix("experiments/")


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


def _records(captures: list[dict]) -> tuple[list[tuple[str, bytes]], list[str]]:
    """Every calibration and validation the photos used, as (name, contents); and the ones not
    found."""
    entries, missing = [], []
    for stem in sorted({r["calibration"] for r in captures if r["calibration"]}):
        source = calibration_root() / f"{stem}.json"
        if source.exists():
            entries.append((f"records/calibrations/{stem}.json", source.read_bytes()))
        else:
            missing.append(f"calibration {stem}")
    for session in sorted({r["validation"] for r in captures if r["validation"]}):
        source = validations_root() / f"{session}.json"
        if source.exists():
            entries.append((f"records/validations/{session}.json", source.read_bytes()))
        else:
            missing.append(f"validation {session}")
    return entries, missing


def _readme(experiment: dict, photos: int, missing: list[str], until: str, held: set[str], parts: int) -> str:
    """The README: the experiment, how to put its `parts` together, then what each file holds and
    what each CSV column means, from `export_fields.yaml`, for the files `held` only."""
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
    lines += [""] + fields["parts_note"].format(parts=parts, last=f"{parts - 1:02d}").rstrip("\n").split("\n")
    resources = [r for r in fields["package"]["resources"] if r["path"] in held]
    lines += ["", "What is in this folder", ""]
    for entry in resources + fields["other_files"]:
        path = entry["path"]
        if path in held or any(h.startswith(path) for h in held if path.endswith("/")) or path.startswith("MANIFEST"):
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
