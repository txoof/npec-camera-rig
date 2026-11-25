"""Export an experiment in parts: its photos and their records, experiment.json, the CSVs,
copies of the calibration and validation records the photos used, a README and a checksum list
per part (#119, #65; parts zipped while they download, #368, Aaron 2026-11-06). A running
experiment can be exported too: the export holds its photos up to the moment it was made, and the
README says it is partial.

**Every table with rows for an experiment is added to its export when that table is built**
(Aaron, 2026-10-09; PLAN.md, *CSV export*).

Export records what was ticked and the time the photos stop at, and builds part 0 in the
background into the experiment's exports folder (#437): the README and, with Data ticked, the
data, a few tens of MB for a long experiment. One export is built at a time on the rig, it can be
stopped, and the page may be closed meanwhile; the experiment's older data files are deleted when
a new one is done. Parts 1 and on hold the photos, at most PART_BYTES each, a photo always with
its record, each zipped while it downloads, straight from the photos, so the rig needs no free
space for them and a half-full card can still be downloaded. Every part unzips into the same
folder and holds its own checksum list, MANIFEST-partNN.sha256 (`sha256sum -c` in that folder).

The experiment's photo rows are read exactly once, at the start of the build, and that one list is
used for captures.csv, the readings and the photo parts (#482): a photo whose row appears only
later (adopted, #439, or saved while the build was already running) never joins a part already
fixed. The list each part actually holds, with every file's size and capture id, is written to
`export_part_file` then, so a download reads the stored list rather than recomputing it from disk;
it refuses with 409, recording nothing sent, when a stored file has gone missing or changed size
since. A part is recorded sent once the bytes actually handed to the download equal its exact
length, not merely once the last chunk was yielded. Purge (`purge_status` below) checks every
current capture row against this stored list of one export whose part 0 was also sent from a Data
export, and refuses, with a short reason, when a photo is not covered or a Reprocess has run
since.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import tempfile
import textwrap
import threading
import time
import unicodedata
import zipfile
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import yaml

from npec_rig import database, dwell, timelapse, tray_readings
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
    """Record a new export of the data, the photos or both, of the photos taken up to now, and
    build its data file, part 0, in the background (#437): the page may be closed meanwhile. One
    export is built at a time on the rig: Export again while this experiment's is built returns
    that one. Refused, raising ExperimentError, while a time lapse video is being made: one job
    that reads every photo at a time (#503). Returns the export with its parts."""
    if timelapse.being_made() is not None:
        raise database.ExperimentError("A time lapse video is being made. Export when it is done.")
    try:
        export = database.create_export(experiment_id, now=_now(), data=data, photos=photos)
    except database.ExperimentError:
        busy = database.unfinished_export()
        if busy is not None and busy["experiment_id"] == experiment_id:
            return export_with_parts(busy["id"])
        raise
    stop = threading.Event()
    thread = threading.Thread(target=_build, args=(export["id"], stop), name=f"export-{export['id']}", daemon=True)
    with _progress_lock:
        _builds[export["id"]] = (thread, stop)
    thread.start()
    return export_with_parts(export["id"])


class _Stopped(Exception):
    """Stop was tapped while the data file was built."""


# The data files being built in this process: export id -> (its thread, its stop signal).
_builds: dict[int, tuple[threading.Thread, threading.Event]] = {}

_BUILDING = ".building"


def _build(export_id: int, stop: threading.Event) -> None:
    """Build the export's part 0 into the experiment's exports folder, under a name ending
    .building until it is whole, then mark the export ready and delete the experiment's older data
    files: one a experiment is kept (#437). Stopped or failed, no part-built file is left.

    The experiment's photo rows are read once, here, at the start (#482): the same list is used
    for captures.csv, the readings and the photo parts, so a photo whose row appears only later
    (adopted, #439, or saved while this was already building) never retroactively joins what was
    already fixed."""
    export = database.get_export(export_id)
    experiment = database.get_experiment(export["experiment_id"])
    folder = experiments_root() / experiment["folder"] / "exports"
    top = _top(export)
    final = folder / f"{top}_part00.zip"
    building = final.with_name(final.name + _BUILDING)
    captures = database.captures_for_experiment(experiment["id"], until=export["started_at"])
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with building.open("wb") as out:
            for chunk in _part_zero(export, top, stop, captures):
                out.write(chunk)
        if export["photos"]:
            parts = _build_parts(captures, experiment["folder"])
            database.save_export_part_files(export_id, parts)
            photo_parts = len(parts)
        else:
            photo_parts = 0
        building.replace(final)
        file = f"experiments/{final.relative_to(experiments_root())}"
        if database.ready_export(export_id, now=_now(), photo_parts=photo_parts, file=file, bytes=final.stat().st_size):
            for older in folder.glob("*_part00.zip"):
                if older != final:
                    older.unlink(missing_ok=True)
        else:
            final.unlink(missing_ok=True)
    except _Stopped:
        building.unlink(missing_ok=True)
        database.fail_export(export_id, now=_now(), error="it was stopped")
    except Exception as exc:
        building.unlink(missing_ok=True)
        database.fail_export(export_id, now=_now(), error=f"the data file could not be made: {exc}")
        raise
    finally:
        with _progress_lock:
            _builds.pop(export_id, None)


def stop_export(export_id: int) -> dict:
    """Stop building the export's data file: it ends within one photo, is marked stopped and its
    part-built file deleted. An export not being built is left as it is."""
    with _progress_lock:
        build = _builds.get(export_id)
    if build is not None:
        thread, stop = build
        stop.set()
        thread.join(timeout=60)
    return export_with_parts(export_id)


def fail_unfinished_exports() -> int:
    """At app start: an export still marked as being built was cut off by a restart. It is marked
    failed and its part-built file deleted. Returns how many there were."""
    failed = database.fail_unfinished_exports(now=_now())
    # Only in tests is a build still running here; it ends without changing the export.
    with _progress_lock:
        builds = list(_builds.values())
    for thread, stop in builds:
        stop.set()
        thread.join(timeout=60)
    for leftover in experiments_root().glob(f"*/exports/*{_BUILDING}"):
        leftover.unlink(missing_ok=True)
    return failed


def export_with_parts(export_id: int) -> dict:
    """The export row and its parts: n, photos, and bytes (the exact size of a photo part's zip;
    for part 0, the expected size of the data), and whether each was sent in full."""
    export = database.get_export(export_id)
    sent = database.parts_sent(export_id)
    if export["file"]:
        made = export["bytes"]
    else:
        made = _expected_data_bytes(export) if export["data"] else 2_000
    parts = [{"n": 0, "photos": 0, "bytes": made}]
    # The photo parts are listed once the data file is built, from the stored list (#482): reading
    # it is a plain query, not every photo file's size read again each time the page asks (#437).
    if export["photos"] and export["finished_at"]:
        top = _top(export)
        for i in range(1, (export["photo_parts"] or 0) + 1):
            rows = _part_files(export, i)
            present = [(row["name"], row["path"], row["bytes"]) for row in rows if row["bytes"] is not None]
            parts.append({"n": i, "photos": len({row["capture_id"] for row in rows}),
                          "bytes": _zip_length(top, i, present)})
    for part in parts:
        part["sent"] = part["n"] in sent
    parts[0]["making"] = _making(export_id)
    return {**export, "parts": parts}


# Part 0 of each export being sent: its photos read so far, all its photos, and when it started
# (time.monotonic), so the page can say how far it is (#430). Held only while it is sent.
_progress: dict[int, tuple[int, int, float]] = {}
_progress_lock = threading.Lock()


def _making(export_id: int) -> dict | None:
    """How far part 0 of the export is, while it is sent: photos done, all photos, and the seconds
    left at the rate so far (None until a photo is done). None when it is not being sent."""
    with _progress_lock:
        progress = _progress.get(export_id)
    if progress is None:
        return None
    done, total, started = progress
    elapsed = time.monotonic() - started
    left = round(elapsed / done * (total - done)) if done else None
    return {"photos_done": done, "photos": total, "seconds_left": left}


def _top(export: dict) -> str:
    """The folder every part unzips into: the experiment's name and folder and the export's time."""
    experiment = database.get_experiment(export["experiment_id"])
    slug = slugify(experiment["name"])
    stamp = datetime.fromisoformat(export["started_at"]).strftime("%Y%m%dT%H%M%S")
    return f"{slug + '_' if slug else ''}{experiment['folder']}_export_{stamp}"


def _build_parts(captures: list[dict], experiment_folder: str) -> list[list[tuple[int, str, int | None]]]:
    """The export's fixed list of captures, oldest first, packed into parts of at most PART_BYTES
    of existing photo bytes each (a photo larger than that alone): for every file of every
    capture, (its capture id, its name in the zip, its size, or None when it is missing on the
    rig). Written once, at build (#482): a file missing then and a part's size are never read
    again to answer what is in a part."""
    folder = experiments_root() / experiment_folder
    parts: list[list[tuple[int, str, int | None]]] = [[]]
    size = 0
    for row in captures:
        rel = _stills_relative(row["path"], experiment_folder)
        pair = []
        pair_size = 0
        for suffix in (".jpg", ".json"):
            name = f"stills/{rel}{suffix}"
            source = folder / name
            if source.exists():
                file_size = source.stat().st_size
                pair.append((row["id"], name, file_size))
                pair_size += file_size
            else:
                pair.append((row["id"], name, None))
        if parts[-1] and size + pair_size > PART_BYTES:
            parts.append([])
            size = 0
        parts[-1].extend(pair)
        size += pair_size
    return [part for part in parts if part]


def _part_files(export: dict, n: int) -> list[dict]:
    """The photo part's stored files (#482): each one's capture id, name, its path on the rig and
    the size recorded when the export was built (None: missing then)."""
    experiment = database.get_experiment(export["experiment_id"])
    folder = experiments_root() / experiment["folder"]
    rows = database.export_part_files(export["id"], n)
    for row in rows:
        row["path"] = folder / row["name"]
    return rows


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


def _file_chunks(path: Path) -> Iterator[bytes]:
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            yield chunk


def part_download(export_id: int, n: int) -> tuple[str, int, Iterator[bytes]]:
    """A part's file name, exact length and contents: part 0 from its file, built when the export
    was made (#437), the photo parts zipped from the stored list fixed then (#482). Streams only
    files whose current size on the rig still matches what was stored; refused with 409 (not
    `LookupError`, a no-such-part 404) when one is missing or has changed size, and nothing is
    recorded as sent. Recorded as sent once as many bytes as the part's exact length have actually
    been handed on, not merely once the last chunk was."""
    export = database.get_export(export_id)
    if database.get_experiment(export["experiment_id"])["state"] == "purged":
        raise database.ExperimentError("this experiment was purged: its photos are gone")
    top = _top(export)
    if n == 0:
        if not export["finished_at"]:
            raise database.ExperimentError("the data file is still being prepared: download it when it is ready")
        if export["error"]:
            raise database.ExperimentError(f"this export did not finish: {export['error']}")
        path = zip_path(export) if export["file"] else None
        if path is None or not path.exists():
            raise LookupError("this data file is no longer on the rig: export again")
        if path.stat().st_size != export["bytes"]:
            raise database.ExperimentError(
                "this export's data file has changed on the rig since it was built: export again"
            )
        length = export["bytes"]
        chunks: Iterator[bytes] = _file_chunks(path)
    else:
        if not 1 <= n <= (export["photo_parts"] or 0):
            raise LookupError(f"export {export_id} has no part {n}")
        rows = _part_files(export, n)
        files = []
        for row in rows:
            if row["bytes"] is None:
                continue  # missing on the rig when the export was built: left out then too
            if not row["path"].exists() or row["path"].stat().st_size != row["bytes"]:
                raise database.ExperimentError(
                    "this part's photos have changed on the rig since the export was built: export again"
                )
            files.append((row["name"], row["path"], row["bytes"]))
        length = _zip_length(top, n, files)
        chunks = _photo_zip(top, n, files)

    def body_then_record() -> Iterator[bytes]:
        sent = 0
        for chunk in chunks:
            sent += len(chunk)
            yield chunk
        if sent == length:
            database.record_part_sent(export_id, n, now=_now())

    return f"{top}_part{n:02d}.zip", length, body_then_record()


# --- Purge (#482) ---
# database.complete_export is the simple yes/no gate `captures.purge_experiment` checks on its
# own; this is the richer one behind the Purge route and the Experiments/Data pages' reading of
# "can Purge happen", with a reason the two can never disagree about (one candidate export, the
# newest that finished without error and was not removed, checked the same way both times).

PART0_UNSENT = "part0_unsent"
PHOTOS_ADDED = "photos_added"
REPROCESSED = "reprocessed"


def purge_status(experiment_id: int) -> dict:
    """Whether the experiment's captures are all covered by parts verifiably sent from one export,
    so Purge can go ahead (#482): `export`, the export this was checked against (None: none
    exists), and `blocked`, None when Purge can go ahead, else a dict with a short `reason`
    (`part0_unsent`, `photos_added`, `reprocessed`), a `count` where one applies (else None), and
    a plain `message`."""
    database.get_experiment(experiment_id)  # LookupError (404) for no such experiment
    export = database.newest_export_for_purge(experiment_id)
    if export is None or export["data"] != 1 or 0 not in database.parts_sent(export["id"]):
        return {"export": export, "blocked": {
            "reason": PART0_UNSENT, "count": None,
            "message": "part 0 has not been sent in full, from an export with Data ticked",
        }}
    if database.reprocessed_since(experiment_id, export["finished_at"]):
        return {"export": export, "blocked": {
            "reason": REPROCESSED, "count": None,
            "message": "a Reprocess finished after this export was built: export again",
        }}
    all_ids = {row["id"] for row in database.captures_for_experiment(experiment_id)}
    coverage = database.export_sent_coverage(export["id"])
    covered = set(coverage["sent_capture_ids"])
    experiment = database.get_experiment(experiment_id)
    folder = experiments_root() / experiment["folder"]
    for missing in coverage["missing_at_build"]:
        if not (folder / missing["name"]).exists():
            # Still missing: there is nothing on the rig this export failed to cover.
            covered.add(missing["capture_id"])
    uncovered = all_ids - covered
    if uncovered:
        count = len(uncovered)
        return {"export": export, "blocked": {
            "reason": PHOTOS_ADDED, "count": count,
            "message": f"{count} photos were added after this export: export again",
        }}
    return {"export": export, "blocked": None}


class _Hashed:
    """A file being written into the zip that also works out its SHA-256 for the manifest."""

    def __init__(self, raw) -> None:
        self.raw = raw
        self.digest = hashlib.sha256()

    def write(self, data: bytes) -> int:
        self.digest.update(data)
        return self.raw.write(data)


class _Lines:
    """CSV lines written as UTF-8 into a `_Hashed` file (csv writes text, the zip takes bytes)."""

    def __init__(self, out: _Hashed) -> None:
        self.out = out

    def write(self, text: str) -> int:
        return self.out.write(text.encode())


def _part_zero(export: dict, top: str, stop: threading.Event, captures: list[dict]) -> Iterator[bytes]:
    """Part 0, made while it is sent: the README and, with Data ticked, the data, for the export's
    fixed list of `captures` (#482: the same list the photo parts are packed from). Each photo's
    readings are worked out once, written and let go, so its memory does not grow with the
    experiment (production's experiment 18 reached 13 GB made whole, #430). The cell lines, most of
    the part, are sent as they are made, so the download grows from the start; the tray lines wait
    in a temporary file on the card until they are in: a zip takes one file at a time. Not /tmp,
    which is held in memory on the rigs. While it is made, `export_with_parts` says how far it is."""
    experiment = database.get_experiment(export["experiment_id"])
    folder = experiments_root() / experiment["folder"]
    until = export["started_at"]
    pipe = _Pipe()
    sums: list[str] = []
    names: set[str] = set()
    missing: list[str] = []
    with zipfile.ZipFile(pipe, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:

        def whole(name: str, data: bytes) -> None:
            zf.writestr(f"{top}/{name}", data)
            sums.append(f"{hashlib.sha256(data).hexdigest()}  {name}\n")
            names.add(name)

        if export["data"]:
            whole("experiment.json", (folder / "experiment.json").read_bytes())
            whole("captures.csv", _captures_csv(captures, experiment["folder"]))
            whole("time-in-table-location.csv", _time_in_table_location_csv(experiment["id"], until))
            yield pipe.take()
            experiments_root().mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=experiments_root()) as waiting:
                trays = _Hashed(waiting)
                tray_writer = csv.DictWriter(_Lines(trays), fieldnames=TRAY_READING_COLUMNS, lineterminator="\n")
                tray_writer.writeheader()
                with zf.open(f"{top}/cell-readings.csv", "w", force_zip64=True) as raw:
                    cells = _Hashed(raw)
                    cell_writer = csv.DictWriter(_Lines(cells), fieldnames=CELL_READING_COLUMNS, lineterminator="\n")
                    cell_writer.writeheader()
                    # Each photo's readings worked out once, for both files (review of #374).
                    started = time.monotonic()
                    locations = dwell.LocationFinder()
                    try:
                        for done, row in enumerate(captures):
                            if stop.is_set():
                                raise _Stopped
                            with _progress_lock:
                                _progress[export["id"]] = (done, len(captures), started)
                            readings = tray_readings.capture_readings(row, history=False, locations=locations)
                            if readings is None:
                                continue
                            tray_writer.writerows(_tray_rows(row, readings, experiment["folder"]))
                            cell_writer.writerows(_cell_rows(row, readings, experiment["folder"]))
                            if pipe.chunks:
                                yield pipe.take()
                    finally:
                        with _progress_lock:
                            _progress.pop(export["id"], None)
                sums.append(f"{cells.digest.hexdigest()}  cell-readings.csv\n")
                names.add("cell-readings.csv")
                yield pipe.take()
                waiting.seek(0)
                with zf.open(f"{top}/tray-readings.csv", "w", force_zip64=True) as dst:
                    while chunk := waiting.read(_CHUNK):
                        dst.write(chunk)
                        if len(pipe.chunks) > 4:
                            yield pipe.take()
                sums.append(f"{trays.digest.hexdigest()}  tray-readings.csv\n")
                names.add("tray-readings.csv")
            records, missing = _records(captures)
            for name, data in records:
                whole(name, data)
            whole("datapackage.json", _data_package(_fields(), names))
        held = names | ({"stills/"} if export["photos"] else set())
        parts = 1 + (export["photo_parts"] or 0)
        whole("README.txt", _readme(experiment, len(captures), missing, until, held, parts).encode())
        zf.writestr(f"{top}/MANIFEST-part00.sha256", "".join(sums))
    yield pipe.take()


# Bytes per CSV line in the download (the zip compresses the CSVs), and for the README,
# datapackage.json, manifest and experiment.json, for the expected size of an export's data: an
# order of magnitude is all it needs (Aaron, 2026-11-06). From export 4 on npec-rig-01
# (2026-11-06, 4303 photos), a development check: captures 19, tray-readings 17, cell-readings 16
# compressed bytes a line; the other files 7 kB. Records are stored uncompressed.
_BYTES_PER_LINE = 20
_BYTES_FIXED = 7_000


# Photos whose file sizes are read for the expected size of the photos (#437): a decision, enough
# for the order of magnitude the dialog needs.
_SIZE_SAMPLE = 500


def expected_sizes(experiment_id: int) -> dict:
    """How large an export of the experiment's data and of its photos would be, without making
    it, so the user knows whether it takes minutes or hours (#65)."""
    experiment = database.get_experiment(experiment_id)
    folder = experiments_root() / experiment["folder"]
    captures = database.captures_for_experiment(experiment_id)
    # Every photo's size took several seconds for production's 41,740 photos before the dialog
    # opened (#437): photos spread evenly through the experiment stand for the rest.
    step = max(1, len(captures) // _SIZE_SAMPLE)
    sample = captures[::step]
    sample_bytes = 0
    for row in sample:
        rel = _stills_relative(row["path"], experiment["folder"])
        for suffix in (".jpg", ".json"):
            source = folder / "stills" / f"{rel}{suffix}"
            if source.exists():
                sample_bytes += source.stat().st_size
    photos_bytes = round(sample_bytes * len(captures) / len(sample)) if sample else 0
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
    """Where an export's file is on the rig: the whole export before #368, its data file (part 0)
    since #437."""
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


def _rounded(value: float | None, digits: int) -> float | None:
    """`value` rounded to `digits` decimals; None stays None (an empty CSV cell)."""
    return None if value is None else round(value, digits)


# The columns of tray-readings.csv, one line per tray per photo read (#76): the plant area by both
# methods side by side, named as in the Gallery (Aaron, 2026-11-11, #363), how each number was
# made only at the end.
TRAY_READING_COLUMNS = [
    "file", "taken_at", "tray", "location", "plant_area_grow_from_leaf_cores_mm2",
    "plant_area_fixed_green_cutoff_mm2", "not_counted", "photo_excluded", "partly_outside", "scale_error_pct",
    "validation_slot", "no_scale_error_because", "fixed_green_cutoff_floor_mm2", "grow_from_leaf_cores_soil_level",
    "grow_from_leaf_cores_cutoff", "cells_flagged", "cells_flagged_grown_area_mm2",
]


def _rounded(value: float | None, digits: int) -> float | None:
    """`value` rounded to `digits` decimals; None stays None (an empty CSV cell)."""
    return None if value is None else round(value, digits)


def _tray_rows(row: dict, readings: dict, folder: str) -> Iterator[dict]:
    """tray-readings.csv's lines for one photo read for its trays (`row`: its rig.db row,
    `readings`: its `tray_readings.capture_readings`): one per tray, with its plant area by both
    methods as stored, and the band of its validation slot, or the reason it has none (#76).
    Photos not read for trays have no lines."""
    for tray in sorted(readings["trays"], key=lambda t: (t["tray_id"] is None, t["tray_id"] or 0)):
        band = tray["uncertainty"]
        yield {
            "file": f"stills/{_stills_relative(row['path'], folder)}.jpg",
            "taken_at": row["taken_at"],
            "tray": "no tag" if tray["tray_id"] is None else tray["tray_id"],
            "location": tray["location"],
            "plant_area_grow_from_leaf_cores_mm2": _rounded(tray.get("grown_area_mm2"), 1),
            "plant_area_fixed_green_cutoff_mm2": _rounded(tray["area_mm2"], 1),
            "not_counted": "; ".join(tray["not_counted"]),
            "photo_excluded": readings["exclusion"],
            "partly_outside": tray["partly_outside"],
            "scale_error_pct": _rounded(band["band_pct"], 1),
            "validation_slot": band["slot"],
            "no_scale_error_because": band["reason"],
            "fixed_green_cutoff_floor_mm2": tray["floor_mm2"],
            # Greenness levels are histogram bin centres, 0.01 apart: 3 decimals hold them exactly.
            "grow_from_leaf_cores_soil_level": _rounded(tray.get("grown_soil_level"), 3),
            "grow_from_leaf_cores_cutoff": _rounded(tray.get("grown_lower_cutoff"), 3),
            "cells_flagged": tray.get("cells_flagged", 0),
            "cells_flagged_grown_area_mm2": round(float(tray.get("cells_flagged_grown_area_mm2", 0.0)), 1),
        }


# What cell-readings.csv says of a flagged cell (#484): only what was measured, no cause.
GROWN_FIXED_DISAGREE = "grown and fixed areas disagree, check the cell"

# The columns of cell-readings.csv, one line per cell of each tray per photo read (#364): the plant
# area and status by both methods side by side (Aaron, 2026-11-11, #363).
CELL_READING_COLUMNS = [
    "file", "taken_at", "tray", "cell", "location", "plant_area_grow_from_leaf_cores_mm2",
    "plant_area_fixed_green_cutoff_mm2", "status_grow_from_leaf_cores", "status_fixed_green_cutoff",
    "tray_not_counted", "photo_excluded", "names_unsure_since", "scale_error_pct", "validation_slot",
    "no_scale_error_because", "grown_fixed_disagree",
]


def _cell_rows(row: dict, readings: dict, folder: str) -> Iterator[dict]:
    """cell-readings.csv's lines for one photo read for its trays (as `_tray_rows`): one per cell
    of each tray, for the researcher's own map of trays and cells to treatments (#364): the cell's
    plant area and status by both methods, no area when it has none, and its tray's location and
    validation band."""
    for tray in sorted(readings["trays"], key=lambda t: (t["tray_id"] is None, t["tray_id"] or 0)):
        band = tray["uncertainty"]
        for cell in tray["cells"]:
            yield {
                "file": f"stills/{_stills_relative(row['path'], folder)}.jpg",
                "taken_at": row["taken_at"],
                "tray": tray["tray_id"],
                "cell": cell["cell"],
                "location": tray["location"],
                "plant_area_grow_from_leaf_cores_mm2": _rounded(cell.get("grown_area_mm2"), 1),
                "plant_area_fixed_green_cutoff_mm2": _rounded(cell["area_mm2"], 1),
                "status_grow_from_leaf_cores": cell.get("grown_status"),
                "status_fixed_green_cutoff": cell["status"],
                "tray_not_counted": "; ".join(tray["not_counted"]),
                "photo_excluded": readings["exclusion"],
                "names_unsure_since": tray["names_unsure_since"],
                "grown_fixed_disagree": GROWN_FIXED_DISAGREE if cell.get("flagged") else "",
                "scale_error_pct": _rounded(band["band_pct"], 1),
                "validation_slot": band["slot"],
                "no_scale_error_because": band["reason"],
            }


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
