"""Shuffle and event times as written on the maps and on #221, in chamber time (metrology log
16.2), turned into the UTC files analyse.py reads.

    python chamber_times.py sessions/chamber-times-2026-10-22.csv \
        --maps sessions/shuffle-maps-2026-10-22.json \
        --shuffles sessions/shuffles-2026-10-22.csv --events sessions/events-2026-10-22.csv

The chamber-times file has columns kind, map, date, start, finish, note, copied from Aaron's posts
on #221 as written. The two UTC files are made from it and never edited by hand.
"""

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from analysis import CHAMBER, MOVING_FROM, MOVING_TO


def _utc(date, clock):
    local = datetime.fromisoformat(f"{date}T{clock}").replace(tzinfo=CHAMBER)
    return local.astimezone(UTC)


def to_utc(row, maps):
    """One row of the chamber-times file (kind, map, date, start, finish, note) in UTC. A shuffle
    has a map from `maps`, a start (except map 0, the start layout) and a finish, inside the
    shuffling window; an event has its time in `start`. Anything else raises ValueError naming
    the row."""
    where = f"{row['kind']} {row['map']} on {row['date']} {row['start']} to {row['finish']}".strip()
    if row["kind"] == "shuffle":
        if not row["map"] or int(row["map"]) not in maps:
            raise ValueError(f"{where}: no map {row['map']} in the maps file")
        if not row["finish"] or (not row["start"] and row["map"] != "0"):
            raise ValueError(f"{where}: no start or no finish")
        for clock in (row["start"], row["finish"]):
            if clock and not MOVING_FROM <= datetime.fromisoformat(f"{row['date']}T{clock}").time() < MOVING_TO:
                raise ValueError(f"{where}: {clock} is outside the shuffling window")
        if row["start"] and _utc(row["date"], row["finish"]) < _utc(row["date"], row["start"]):
            raise ValueError(f"{where}: finish before start")
    elif row["kind"] == "event":
        if not row["start"]:
            raise ValueError(f"{where}: an event needs its time in start")
    else:
        raise ValueError(f"{where}: kind must be shuffle or event")
    return {
        "kind": row["kind"], "map": row["map"],
        "start_utc": _utc(row["date"], row["start"]) if row["start"] else None,
        "finish_utc": _utc(row["date"], row["finish"]) if row["finish"] else None,
        "note": row["note"],
    }


def convert(rows, maps):
    """(shuffles, events) of a whole chamber-times file, in UTC. Shuffles must be written in the
    order they were done, use each map once and not overlap; otherwise ValueError names them."""
    shuffles, events = [], []
    for row in rows:
        converted = to_utc(row, maps)
        if converted["kind"] == "event":
            events.append({"time_utc": converted["start_utc"], "event": converted["note"]})
            continue
        for done in shuffles:
            if done["map"] == converted["map"]:
                raise ValueError(f"map {converted['map']} used twice ({row['date']})")
        if shuffles:
            last = shuffles[-1]
            begins = converted["start_utc"] or converted["finish_utc"]
            if converted["finish_utc"] < last["finish_utc"]:
                raise ValueError(f"map {converted['map']} on {row['date']} is out of order after map {last['map']}")
            if begins < last["finish_utc"]:
                raise ValueError(f"map {converted['map']} on {row['date']} overlaps map {last['map']}")
        shuffles.append(converted)
    events.sort(key=lambda e: e["time_utc"])
    return shuffles, events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("chamber_times", type=Path)
    parser.add_argument("--maps", type=Path, required=True)
    parser.add_argument("--shuffles", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    args = parser.parse_args()
    maps = {m["map"] for m in json.loads(args.maps.read_text())["maps"]}
    shuffles, events = convert(list(csv.DictReader(args.chamber_times.open())), maps)
    with args.shuffles.open("w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["shuffle", "map", "start_utc", "finish_utc"])
        for s in shuffles:
            start = s["start_utc"].isoformat() if s["start_utc"] else ""
            writer.writerow([s["map"], s["map"], start, s["finish_utc"].isoformat()])
    with args.events.open("w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["time_utc", "event"])
        for e in events:
            writer.writerow([e["time_utc"].isoformat(), e["event"]])
    print(f"{len(shuffles)} shuffles, {len(events)} events")


if __name__ == "__main__":
    main()
