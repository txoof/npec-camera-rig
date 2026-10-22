"""Read an experiment's photos for trays with the app's own code (tray_readings.read_photo, #222),
into a COPY of rig.db, never the live one (metrology log 16.4).

    python read_photos.py WORKDIR --experiment 16

WORKDIR gets `rig.db` (a copy made with the sqlite backup API from a read-only connection),
`calibration/` (a copy of the calibration folder) and `derived/`. The environment is pointed at
them before npec_rig is imported, so the live rig.db, derived and calibration folders are only
read, while the copy is made. Photos are read from the experiments folder, never written. Photos
already read in the copy are skipped, so a stopped run can be started again.
"""

import argparse
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

LIVE_DB = Path("/var/lib/npec-rig/rig.db")
LIVE_CALIBRATION = Path("/var/lib/npec-rig/calibration")


def copy_live(workdir: Path) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{LIVE_DB}?mode=ro", uri=True)
    target = sqlite3.connect(workdir / "rig.db")
    with target:
        source.backup(target)
    source.close()
    target.close()
    shutil.copytree(LIVE_CALIBRATION, workdir / "calibration", dirs_exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workdir", type=Path)
    parser.add_argument("--experiment", type=int, required=True)
    args = parser.parse_args()
    workdir = args.workdir.resolve()
    if workdir == LIVE_DB.parent or not str(workdir).startswith(str(Path.home())):
        sys.exit("WORKDIR must be a folder under your home, not the live data folder")
    # The copy is made once: copying again would replace the readings already made in it.
    # For photos taken since, use a new WORKDIR.
    if not (workdir / "rig.db").exists():
        copy_live(workdir)

    os.environ["NPEC_RIG_DB_PATH"] = str(workdir / "rig.db")
    os.environ["NPEC_RIG_CALIBRATION_DIR"] = str(workdir / "calibration")
    os.environ["NPEC_RIG_DERIVED_DIR"] = str(workdir / "derived")
    from npec_rig import tray_readings

    conn = sqlite3.connect(workdir / "rig.db")
    paths = [
        row[0]
        for row in conn.execute(
            "SELECT c.path FROM capture c LEFT JOIN tray_read r ON r.capture_id = c.id"
            " WHERE c.experiment_id = ? AND r.capture_id IS NULL ORDER BY c.taken_at",
            (args.experiment,),
        )
    ]
    conn.close()
    print(f"{len(paths)} photos to read", flush=True)
    for n, path in enumerate(paths, 1):
        start = time.monotonic()
        try:
            reading = tray_readings.read_photo(path)
            status = reading.get("status") if reading else None
        except Exception as exc:  # one bad photo (capture 725 has no image) must not stop the run
            status = f"failed: {type(exc).__name__}: {exc}"
        print(f"{n}/{len(paths)} {path} {status} {time.monotonic() - start:.1f}s", flush=True)


if __name__ == "__main__":
    main()
