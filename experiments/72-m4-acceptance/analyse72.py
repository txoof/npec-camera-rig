"""Read-only analysis of the #72 session: every photo of experiment 4 from 08:50 to 10:30 UTC on 2026-11-27.
Fetches each photo's tray reading from the rig's API (GET only), checks it against the layout in force,
maps it to the state it was taken in (from Aaron's messages and the burst times), and writes
data72.json, photos72.csv and a summary. State windows are inferred, see STATES."""
import csv, json, sys
from datetime import datetime, timezone
import m4

START, END = "2026-11-27T08:50:00", "2026-11-27T10:30:00"
SWAP_FIRST = "2026-11-27T09:01:18"   # first photo after the swap (both trays MOVED)
PLAN = {1: m4.expected(1, m4.parse_spares(None)), 2: m4.expected(2, m4.parse_spares(None))}
EVERY = set(m4.expected(1, m4.parse_spares(None)))  # the 12 tags on the layout
# (from, to, state): UTC clock times of 2026-11-27, inferred from Aaron's messages and the bursts of hand-taken photos.
STATES = [
    ("08:50:00", "08:55:00", "before the spares (6 trays)"),
    ("08:55:00", "09:01:10", "layout 1, nothing on tag 49"),
    ("09:01:10", "09:01:40", "after the swap, nothing on tag 49"),
    ("09:01:40", "09:06:30", "clear plastic on tag 49 (no marker)"),
    ("09:06:30", "09:07:10", "plastic off, nothing on tag 49"),
    ("09:07:10", "09:07:55", "black piece 1 on tag 49: 13.99 x 10.65 mm, 9.3%, centre"),
    ("09:08:20", "09:09:00", "black piece 2: 21.29 x 20.8 mm, 27.7%"),
    ("09:09:50", "09:10:20", "black piece 3: 31.92 x 29.64 mm, 59.1%"),
    ("09:10:40", "09:11:30", "black piece 4: 40.45 x 39.36 mm, 99.5%"),
    ("09:12:00", "09:12:40", "black piece 1 again: 9.3%, just inside the black edge"),
    ("09:13:00", "10:18:30", "no cover on tag 49 (all covers removed)"),
    ("10:18:50", "10:19:20", "small piece: 4.83 x 4.85 mm, 1.5%"),
    ("10:19:40", "10:20:10", "medium piece: 6.71 x 7.34 mm, 3.1%"),
    ("10:20:30", "10:21:30", "large piece: 9.65 x 9.44 mm, 5.7%"),
    ("10:21:30", "10:30:00", "spares being removed, trays put back"),
]


def state_of(ts: str) -> str:
    t = ts[11:19]
    for a, b, name in STATES:
        if a <= t < b:
            return name
    return "between bursts (state not mapped)"


def main() -> None:
    items = [i for i in m4.captures(4, 200) if START <= i["timestamp"][:19] <= END]
    items.sort(key=lambda i: i["timestamp"])
    rows, raw = [], []
    for it in items:
        ts = it["timestamp"]
        reading = m4.full_reading(it)
        raw.append({"key": it["key"], "timestamp": ts, "reading": reading and {k: reading[k] for k in ("status", "exclusion", "not_found", "moved") if k in reading}})
        layout = 2 if ts[:19] >= SWAP_FIRST else 1
        plan = PLAN[layout]
        trays = reading["trays"] if reading else []
        ids = [t["tray_id"] for t in trays if t["tray_id"] is not None]
        found = {t["tray_id"]: t for t in trays if t["tray_id"] is not None}
        notag = sum(1 for t in trays if t["tray_id"] is None)
        problems = []
        for tid, want in plan.items():
            if tid == 49:
                continue
            t = found.get(tid)
            if t is None:
                problems.append(f"{tid} not read")
                continue
            if t["found"] != "photo + tag":
                problems.append(f"{tid} {t['found']}")
            if t.get("location") != want["loc"]:
                problems.append(f"{tid} in {t.get('location')} not {want['loc']}")
            if m4.rotation_of(m4.a1_side(t)) != want["rot"]:
                problems.append(f"{tid} turned {m4.rotation_of(m4.a1_side(t))}")
        unexpected = sorted(set(ids) - EVERY)
        dup = sorted({i for i in ids if ids.count(i) > 1})
        t49 = found.get(49)
        if t49 and t49["found"] == "photo + tag":
            c49 = "read"
        elif any(n["tray_id"] == 49 for n in (reading or {}).get("not_found", [])):
            c49 = "not read, reported not seen" + (", outline with no tag" if notag else "")
        else:
            c49 = "not read, not reported"
        six_only = len(trays) == 6 and ts[:19] < "2026-11-27T08:55:00"
        rows.append({
            "time_utc": ts[:19].replace("T", " "), "key": it["key"], "layout": layout,
            "state": state_of(ts), "status": (it.get("trays") or {}).get("status"), "exclusion": (it.get("trays") or {}).get("exclusion") or "",
            "trays_read": len(ids), "tag49": c49, "other_trays_as_planned": "yes" if not problems else "no: " + "; ".join(problems),
            "unexpected_tags": ",".join(map(str, unexpected)), "duplicate_tags": ",".join(map(str, dup)),
            "moved": "; ".join(f"{m['tray_id']} {m['from']} to {m['to']}" for m in (reading or {}).get("moved", [])),
        })
        if six_only:
            rows[-1]["other_trays_as_planned"] = "n/a (spares not yet placed)"
    json.dump(raw, open("data72.json", "w"), indent=1)
    with open("photos72.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(len(rows), "photos", rows[0]["time_utc"], "to", rows[-1]["time_utc"])


if __name__ == "__main__":
    main()
