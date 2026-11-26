"""Issue #511, Part 2 step 4: every capture path of the experiment must exist as a file under the
copied photos. A missing file makes Reprocess keep the old values and list the photo as failed,
so an incomplete HDD copy would look like a real result -- this must read 0 missing before the
full run starts.

Usage: check_capture_files.py <rig.db path> <photos dir> <experiments dir> <experiment_id>
Exit 0 and prints "0 missing" when every path resolves to a file on disk; otherwise exits 1 and
lists every missing path.
"""

import re
import sqlite3
import sys
from pathlib import Path

_PHOTO_PATH = re.compile(r"^(rig|experiments/[A-Za-z0-9_-]+/stills)/(\d{4}-\d{2}-\d{2})/(\d{6}_\d{6})$")


def resolve(path: str, photos_dir: Path, experiments_dir: Path) -> Path | None:
    match = _PHOTO_PATH.match(path)
    if match is None:
        return None
    prefix, day, stem = match.groups()
    if prefix == "rig":
        return photos_dir / day / f"{stem}.jpg"
    # prefix is "experiments/<folder>/stills"
    folder = prefix.split("/")[1]
    return experiments_dir / folder / "stills" / day / f"{stem}.jpg"


def main() -> int:
    db_path, photos_dir, experiments_dir, experiment_id = sys.argv[1:5]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT path FROM capture WHERE experiment_id = ? ORDER BY taken_at", (experiment_id,)
    ).fetchall()
    total = len(rows)
    missing = []
    for row in rows:
        file_path = resolve(row["path"], Path(photos_dir), Path(experiments_dir))
        if file_path is None or not file_path.exists():
            missing.append((row["path"], file_path))

    print(f"{total} capture rows for experiment {experiment_id}, {len(missing)} missing")
    for path, resolved in missing[:50]:
        print(f"  MISSING  {path}  ->  {resolved}")
    if len(missing) > 50:
        print(f"  ... and {len(missing) - 50} more")
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
