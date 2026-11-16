"""Pairs that span an app restart before 2 Nov 2026 16:19 UTC, from the photos' sidecar files (metrology log 16.9 results).

rig.db records app starts (`app_start`) only from 2 Nov 16:19 UTC, so rule 5 of 16.3 cannot be checked from
the database before then. Each photo's sidecar JSON holds `uptime.app_up_s`: a pair spans a restart when the
later photo's app uptime is no longer than the time between the two photos.

    python restarts.py SIDECARS PAIRS_CSV OUT_JSON

SIDECARS: a folder holding the experiment's `stills/<day>/<time>.json` files, copied read-only from the rig
(`stills/` itself, so its children are the day folders). PAIRS_CSV: script_a.py's `tray_pairs_all.csv`.
OUT_JSON: the list of [before_id, after_id] that span a restart. Read-only; writes only OUT_JSON.
"""
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

APP_START_FROM = "2026-11-02T16:19"  # first app_start row of production's rig.db


def main(sidecars, pairs_csv, out):
    sidecars = Path(sidecars)
    up = {}
    for f in sidecars.glob("*/*.json"):
        key = "experiments/2026-10-22_df206967/stills/" + str(f.relative_to(sidecars).with_suffix(""))
        up[key] = (json.loads(f.read_text()).get("uptime") or {}).get("app_up_s")
    spanning, unknown = set(), set()
    for r in csv.DictReader(open(pairs_csv)):
        if r["after_utc"] >= APP_START_FROM:
            continue
        pair = (r["before_id"], r["after_id"])
        gap = (datetime.fromisoformat(r["after_utc"]) - datetime.fromisoformat(r["before_utc"])).total_seconds()
        u = up.get(r["after_path"])
        if u is None:
            unknown.add(pair)
        elif u <= gap:
            spanning.add(pair)
    Path(out).write_text(json.dumps(sorted(spanning)))
    print(f"photo pairs spanning a restart: {len(spanning)}; with no sidecar uptime: {len(unknown)}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
