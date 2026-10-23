"""The Round 2 run's analysis (metrology log 16): undisturbed pairs, steadiness, tag detection and
tray tracking, from the rig's own tray readings. Plain rows in, tables out; reading them from a
copy of rig.db is left to the script that calls these.
"""

import math
from datetime import time
from zoneinfo import ZoneInfo

# The chamber keeps Dutch local time (UTC+2 in summer time, UTC+1 from 25 October 2026).
CHAMBER = ZoneInfo("Europe/Amsterdam")

# Trays may be moved from 09:30 to 17:00 chamber time, nothing is moved from 17:00 to 09:30 (16.3).
MOVING_FROM, MOVING_TO = time(9, 30), time(17, 0)

# Two photo intervals at one photo a minute (16.3, rule 4), a decision. Photos come 59.4 to 60.9 s
# apart (22 October), so the limit is 2.5 intervals: one missed photo keeps the pair, two do not.
MAX_PAIR_S = 150.0


def window(taken_at):
    """(chamber day, movement window) of a photo taken at UTC `taken_at` (16.3)."""
    local = taken_at.astimezone(CHAMBER)
    moving = MOVING_FROM <= local.time() < MOVING_TO
    return local.date().isoformat(), "trays may move" if moving else "nothing moved"


def pairs(photos, breaks, camera_events):
    """Each pair of consecutive photos, with `reason` None when undisturbed (16.3)."""
    ordered = sorted(photos, key=lambda p: p["taken_at"])
    return [
        {"before": a["capture_id"], "after": b["capture_id"], "reason": _reason(a, b, breaks, camera_events)}
        for a, b in zip(ordered, ordered[1:])
    ]


def _reason(a, b, breaks, camera_events):
    # A break (start, end) disturbs the pair when it overlaps the time after `a`, up to `b`.
    if any(start <= b["taken_at"] and end > a["taken_at"] for start, end in breaks):
        return "shuffle or event"
    if (a["calibration"], a["lens_position"]) != (b["calibration"], b["lens_position"]):
        return "calibration or lens changed"
    if a["flags"] or b["flags"]:
        return "flagged"
    if a["status"] != "read" or b["status"] != "read":
        return "not read"
    apart_s = (b["taken_at"] - a["taken_at"]).total_seconds()
    if apart_s > MAX_PAIR_S:
        return "photos missed"
    if b["app_up_s"] is None:
        return "app uptime unknown"
    if b["app_up_s"] <= apart_s:
        return "app restarted"
    if any(a["taken_at"] < t <= b["taken_at"] for t in camera_events):
        return "camera event"
    return None


def steadiness(photos, pairs, centres, mm_per_px):
    """Per tray and movement window: undisturbed pairs, rms and largest change of the placed
    centre in mm (16.4, question 1). `centres` is {capture_id: {tray: (x_px, y_px)}};
    `mm_per_px(x, y)` is the calibration's scale at a point. A pair's window is its later photo's."""
    taken = {p["capture_id"]: p["taken_at"] for p in photos}
    changes = {}
    for pair in pairs:
        if pair["reason"] is not None:
            continue
        before, after = centres.get(pair["before"], {}), centres.get(pair["after"], {})
        _, win = window(taken[pair["after"]])
        for tray in before.keys() & after.keys():
            (x0, y0), (x1, y1) = before[tray], after[tray]
            mm = math.hypot(x1 - x0, y1 - y0) * mm_per_px((x0 + x1) / 2, (y0 + y1) / 2)
            changes.setdefault((tray, win), []).append(mm)
    return [
        {"tray": tray, "window": win, "pairs": len(mm), "rms_mm": math.sqrt(sum(c * c for c in mm) / len(mm)),
         "max_mm": max(mm)}
        for (tray, win), mm in sorted(changes.items())
    ]


def detection(photos, found, trays):
    """Tag detection (16.4, question 2). `found` is {capture_id: set of tray IDs placed}.

    "trays": per tray, chamber day and window, the photos read (status "read") and those with
    its tag found. "not read": photos with another status (dark is "no tags found"), counted apart.
    "misses": every read photo where a tray was missed while others were found."""
    counts, unread, misses = {}, {}, []
    for p in sorted(photos, key=lambda p: p["taken_at"]):
        day, win = window(p["taken_at"])
        if p["status"] != "read":
            unread[(day, win, p["status"])] = unread.get((day, win, p["status"]), 0) + 1
            continue
        here = found.get(p["capture_id"], set())
        for tray in trays:
            n = counts.setdefault((tray, day, win), [0, 0])
            n[0] += 1
            n[1] += tray in here
        missing = sorted(set(trays) - here)
        if missing and here:
            misses.append({"capture_id": p["capture_id"], "taken_at": p["taken_at"], "missing": missing})
    return {
        "trays": [
            {"tray": tray, "day": day, "window": win, "photos": n, "found": f, "share": f / n}
            for (tray, day, win), (n, f) in sorted(counts.items())
        ],
        "not read": [
            {"day": day, "window": win, "status": status, "photos": n}
            for (day, win, status), n in sorted(unread.items())
        ],
        "misses": misses,
    }


def tracking(photos, readings, shuffles):
    """Tray tracking (16.4, question 3). Each shuffle's layout is `slots` ({slot: {"tray", "a1"}},
    as in the shuffle maps), in place from its `finish` to the next shuffle's `start` (the last to
    the end). `readings` is {capture_id: {tray: (slot, a1, placement)}}. Per shuffle: read photos,
    and each tray right (slot and corner as the layout), wrong, doubtful (the app marked the
    placement other than "placed", for example "two trays in one slot", listed apart) or not found;
    photos with another status are counted as not read. Photos during a shuffle belong to none."""
    ordered = sorted(shuffles, key=lambda s: s["finish"])
    by_time = sorted(photos, key=lambda p: p["taken_at"])
    rows, wrong, doubtful = [], [], []
    for n, shuffle in enumerate(ordered):
        until = ordered[n + 1]["start"] if n + 1 < len(ordered) else None
        planned = {v["tray"]: (slot, v["a1"]) for slot, v in shuffle["slots"].items()}
        row = {"shuffle": shuffle["shuffle"], "photos": 0, "right": 0, "wrong": 0, "doubtful": 0,
               "not found": 0, "not read": 0}
        for p in by_time:
            if p["taken_at"] < shuffle["finish"]:
                continue
            if until is not None and p["taken_at"] >= until:
                break
            if p["status"] != "read":
                row["not read"] += 1
                continue
            row["photos"] += 1
            read = readings.get(p["capture_id"], {})
            for tray, place in sorted(planned.items()):
                if tray not in read:
                    row["not found"] += 1
                    continue
                slot, a1, placement = read[tray]
                seen = {"shuffle": shuffle["shuffle"], "capture_id": p["capture_id"], "taken_at": p["taken_at"],
                        "tray": tray, "read": (slot, a1), "map": place}
                if placement != "placed":
                    row["doubtful"] += 1
                    doubtful.append(seen | {"placement": placement})
                elif (slot, a1) == place:
                    row["right"] += 1
                else:
                    row["wrong"] += 1
                    wrong.append(seen)
        rows.append(row)
    return {"shuffles": rows, "wrong": wrong, "doubtful": doubtful}


def misses(photos, readings, shuffles, trays=None):
    """Every read photo where a tray's tag was missed while others were found, with the slot the rig
    last read that tray in ("not read yet" before its first reading), and whether the photo was
    taken during a shuffle (between a shuffle's start and finish; the start layout has no start).
    `readings` is {capture_id: {tray: (slot, a1, placement)}}; `trays` defaults to every tray read.
    Also counted by tray and by slot, outside and during shuffles."""
    if trays is None:
        trays = sorted({t for found in readings.values() for t in found})
    moving = [(s["start"], s["finish"]) for s in shuffles if s["start"] is not None]
    last_slot, found, by_tray, by_slot = {}, [], {}, {}
    for p in sorted(photos, key=lambda p: p["taken_at"]):
        if p["status"] != "read":
            continue
        here = readings.get(p["capture_id"], {})
        during = any(start <= p["taken_at"] <= finish for start, finish in moving)
        for tray in trays:
            if tray in here or not here:
                continue
            slot = last_slot.get(tray, "not read yet")
            found.append({"capture_id": p["capture_id"], "taken_at": p["taken_at"], "tray": tray,
                          "slot": slot, "during_shuffle": during})
            key = "during shuffles" if during else "outside shuffles"
            for counts, name in ((by_tray, tray), (by_slot, slot)):
                counts.setdefault(name, {"outside shuffles": 0, "during shuffles": 0})[key] += 1
        for tray, (slot, _, _) in here.items():
            last_slot[tray] = slot
    return {"misses": found, "by_tray": by_tray, "by_slot": by_slot}
