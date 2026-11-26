"""Run the real Reprocess per-photo call over a list of photo paths.

Calls `tray_readings.read_photo(path, reuse_mask=True)` -- the exact call `_run_reprocess` makes
for every photo -- so the method is the app's, unchanged. Used for Part 3's sample and, with
`--slice i/n`, for Part 4's parallel workers (each worker takes contiguous block i of n -- NOT
every n-th photo: see the comment in main()).

Progress is appended to the log as JSON lines so it can be read while the run is going.

Usage: run_photos.py <paths file> <log file> [--slice i/n]
"""

import json
import os
import sys
import time
from datetime import UTC, datetime


def main() -> int:
    paths_file, log_path = sys.argv[1], sys.argv[2]
    index, workers = 0, 1
    if "--slice" in sys.argv:
        index, workers = (int(x) for x in sys.argv[sys.argv.index("--slice") + 1].split("/"))

    from npec_rig import tray_readings

    # Contiguous blocks, not every n-th photo: the exclusion "visit" rule reads the photos before
    # this one, so slicing must keep neighbours together. Blocks break that order only where two
    # workers meet (workers - 1 places); interleaving would break it at every photo.
    all_paths = [line.strip() for line in open(paths_file) if line.strip()]
    size = -(-len(all_paths) // workers)  # round up, so the last block is the short one
    paths = all_paths[index * size:(index + 1) * size]

    log = open(log_path, "a", buffering=1)

    def record(**fields):
        log.write(json.dumps({"at": datetime.now(UTC).isoformat(), **fields}) + "\n")

    record(event="start", slice=f"{index}/{workers}", photos=len(paths), pid=os.getpid())
    started = time.monotonic()
    done = failed = 0
    for path in paths:
        photo_started = time.monotonic()
        try:
            tray_readings.read_photo(path, reuse_mask=True)
        except Exception as exc:
            failed += 1
            record(event="failed", path=path, reason=f"{type(exc).__name__}: {exc}")
        done += 1
        if done % 10 == 0 or done == len(paths):
            elapsed = time.monotonic() - started
            record(event="progress", done=done, of=len(paths), failed=failed,
                   s_per_photo=round(elapsed / done, 2),
                   last_photo_s=round(time.monotonic() - photo_started, 2))
    record(event="end", done=done, failed=failed,
           total_s=round(time.monotonic() - started, 1))
    log.close()
    print(f"slice {index}/{workers}: {done} photos, {failed} failed, "
          f"{round(time.monotonic() - started, 1)} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
