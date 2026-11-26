"""Issue #511, Part 3A: pick the photos to compare Pi against AMD.

The Pi finished `done` photos of its run, oldest first. Those, and only those, hold a Pi result
to compare against. This picks at least 300 of them from the experiment's first days, and makes
sure the hard cases are in: the photos the Pi listed as failed, photos whose readings were
flagged (the soil-hidden rule's trigger: top soil-level bin and a cutoff above the floor), tray 1
(plants under mats), the benchmark trays 7, 8 and 10, and both lit and dark photos.

Writes one capture path per line. Reads only; changes nothing.

Usage: pick_sample.py <rig.db> <experiment_id> <done_count> <out file> [min_sample]
"""

import sqlite3
import sys
from collections import Counter

FLAG_SOIL_LEVEL = 0.045   # top bin, log 41
FLAG_FLOOR = -0.045       # cutoff above this counts as flagged
WANT_TRAYS = (1, 7, 8, 10)


def main() -> int:
    db_path, experiment_id, done, out_path = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    min_sample = int(sys.argv[5]) if len(sys.argv) > 5 else 300

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # The Reprocess order: captures of the experiment, purpose 'capture', oldest first.
    captures = conn.execute(
        "SELECT id, path, taken_at, exposure_us, analogue_gain FROM capture"
        " WHERE experiment_id = ? AND purpose = 'capture' ORDER BY taken_at, id",
        (experiment_id,),
    ).fetchall()
    pi_done = captures[:done]
    if not pi_done:
        print("no photos the Pi finished", file=sys.stderr)
        return 1
    done_ids = {c["id"] for c in pi_done}
    by_id = {c["id"]: c for c in pi_done}

    picked: dict[int, set[str]] = {}

    def take(capture_id: int, why: str) -> None:
        if capture_id in done_ids:
            picked.setdefault(capture_id, set()).add(why)

    # 1. Every photo the Pi listed as failed.
    for row in conn.execute(
        "SELECT path FROM reprocess_failure WHERE run_id ="
        " (SELECT id FROM reprocess_run WHERE experiment_id = ? ORDER BY id DESC LIMIT 1)",
        (experiment_id,),
    ):
        hit = conn.execute("SELECT id FROM capture WHERE path = ?", (row["path"],)).fetchone()
        if hit:
            take(hit["id"], "pi-failed")

    # 2. Photos holding a flagged reading (what the soil-hidden rule regrows).
    for row in conn.execute(
        "SELECT DISTINCT capture_id FROM tray_reading"
        " WHERE grown_soil_level >= ? AND grown_lower_cutoff > ?",
        (FLAG_SOIL_LEVEL, FLAG_FLOOR),
    ):
        take(row["capture_id"], "flagged")

    # 3. The trays that matter: 1 (plants under mats), 7/8/10 (benchmark objects).
    for tray_id in WANT_TRAYS:
        for row in conn.execute(
            "SELECT DISTINCT capture_id FROM tray_reading WHERE tray_id = ? LIMIT 40", (tray_id,)
        ):
            take(row["capture_id"], f"tray-{tray_id}")

    # 4. Lit and dark photos, by the exposure the camera used.
    lit_dark = sorted(pi_done, key=lambda c: (c["exposure_us"] or 0))
    for c in lit_dark[:25]:
        take(c["id"], "lit")          # shortest exposure = brightest scene
    for c in lit_dark[-25:]:
        take(c["id"], "dark")         # longest exposure = darkest scene

    # 5. Top up from the first days, evenly spaced, until the sample is big enough.
    if len(picked) < min_sample:
        need = min_sample - len(picked)
        pool = [c for c in pi_done if c["id"] not in picked]
        step = max(1, len(pool) // max(1, need))
        for c in pool[::step][:need]:
            take(c["id"], "spread")

    chosen = sorted(picked, key=lambda i: (by_id[i]["taken_at"], i))
    with open(out_path, "w") as fh:
        for capture_id in chosen:
            fh.write(by_id[capture_id]["path"] + "\n")

    reasons = Counter(why for whys in picked.values() for why in whys)
    print(f"Pi finished {done} photos; sample = {len(chosen)}")
    print(f"first: {by_id[chosen[0]]['taken_at']}   last: {by_id[chosen[-1]]['taken_at']}")
    for why, n in sorted(reasons.items()):
        print(f"  {why:<12} {n}")
    print(f"written: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
