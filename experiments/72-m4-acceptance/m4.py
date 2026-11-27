#!/usr/bin/env python3
"""Read-only checks for the M4 acceptance test (#72) on the development rig npec-rig-01.

Only GET requests (plus an optional ssh read of the version and disk). It never changes the rig.
Every run is appended, with its UTC time, to session-log.txt beside this file: that log is what the
write-up in docs/metrology-log.md is made from.

    m4 preflight                      can the session start now?
    m4 spares 1,2,3,4,5,6             once: the tag IDs of spare trays A to F, in that order
    m4 plan [--layout 1|2]            slot, tag and rotation of every tray
    m4 snapshot --exp 4               before: where experiment 4's trays are (saves a picture)
    m4 look [--layout 1|2] [--photos 5] [--focus TAG]   what the rig reads, against the layout
    m4 dwell                          the Table locations panel, against the swap
    m4 restore --exp 4 --test-exp N   after: trays back, experiment 4 running
    m4 note "swapped trays E and F"   a timestamped line in the session log

`m4` is the wrapper next to this file. Spare tags are any six unused IDs (not 8, 9, 11, 12, 25, 51).
Slots: N1..N6 and S1..S6, west to east, north (the top of the photo) is N.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

RIG = "http://10.248.49.102:8000"
HERE = Path(__file__).resolve().parent
LOG = HERE / "session-log.txt"
CHAMBER = ZoneInfo("Europe/Amsterdam")  # the chamber keeps Dutch time; rig times are UTC

# The 6 trays of experiment 4 on the development table (read 2026-11-27); tag IDs.
FIXED = {"X8": 8, "X9": 9, "X11": 11, "X12": 12, "X25": 25, "X51": 51}
LOC_OF_SLOT = {f"{row}{n}": row + ("W" if n <= 2 else "M" if n <= 4 else "E") for row in "NS" for n in range(1, 7)}
SLOTS = [f"{row}{n}" for row in "NS" for n in range(1, 7)]
# slot: (tray, rotation in degrees). Rotation 0: cell A1 at the south-west corner; 180: north-east.
LAYOUT_1 = {"N1": ("A", 0), "N2": ("B", 180), "N3": ("C", 180), "N4": ("X8", 0), "N5": ("X12", 0), "N6": ("D", 0),
            "S1": ("X51", 0), "S2": ("X25", 0), "S3": ("E", 180), "S4": ("X11", 0), "S5": ("X9", 0), "S6": ("F", 0)}
# After the swap: E and F trade places and each is turned 180 degrees (E 180 -> 0, F 0 -> 180).
LAYOUT_2 = {**LAYOUT_1, "S3": ("F", 180), "S6": ("E", 0)}
LAYOUTS = {1: LAYOUT_1, 2: LAYOUT_2}
MOVE_AFTER = timedelta(hours=1)  # dwell.MOVE_AFTER: a tray counts as moved after this long in another location

_out: list[str] = []


def say(line: str = "") -> None:
    print(line)
    _out.append(line)


def now() -> datetime:
    return datetime.now(timezone.utc)


def stamp(t: datetime) -> str:
    return f"{t:%H:%M:%S}Z ({t.astimezone(CHAMBER):%H:%M} chamber)"


def get(path: str, *, raw: bool = False, timeout: int = 90):
    with urllib.request.urlopen(RIG + path, timeout=timeout) as r:
        body = r.read()
    return body if raw else json.loads(body)


def post(path: str, body: dict | None = None, timeout: int = 60):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(RIG + path, data=data, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def sleep(seconds: float) -> None:
    import time
    time.sleep(seconds)


def flush_log() -> None:
    """Write what has been said so far to the session log (the guide runs for hours)."""
    if _out:
        with LOG.open("a") as f:
            f.write("\n".join(_out) + "\n")
        _out.clear()


def experiments() -> list[dict]:
    return get("/api/experiments")


def pick_experiment(arg: int | None) -> dict:
    exps = experiments()
    if arg is not None:
        return next(e for e in exps if e["id"] == arg)
    running = [e for e in exps if e["state"] == "running"]
    if not running:
        sys.exit("No experiment is running. Pass --exp N.")
    return running[0]


def captures(exp_id: int | None, limit: int, before: str | None = None) -> list[dict]:
    q = f"/api/captures?limit={limit}" + (f"&experiment={exp_id}" if exp_id is not None else "")
    return get(q + (f"&before={before}" if before else ""))


def full_reading(item: dict) -> dict | None:
    return get("/api/captures/trays/" + item["path"])


def a1_side(tray: dict) -> str | None:
    """Which corner of the tray cell A1 is in, seen from above with north up the photo."""
    a1 = next((c for c in tray.get("cells") or [] if c["cell"] == "A1"), None)
    outline = tray.get("outline_px")
    if not a1 or not outline:
        return None
    cx = sum(p[0] for p in outline) / len(outline)
    cy = sum(p[1] for p in outline) / len(outline)
    dx, dy = a1["centre_px"][0] - cx, a1["centre_px"][1] - cy
    return ("S" if dy > 0 else "N") + ("W" if dx < 0 else "E")


def rotation_of(side: str | None) -> str:
    return {"SW": "0", "NE": "180", None: "?"}.get(side, "90/270?")


def expected(layout: int, spares: list[int]) -> dict[int, dict]:
    """tag ID -> {slot, loc, rot, name} for a layout."""
    names = dict(FIXED)
    names.update({letter: tag for letter, tag in zip("ABCDEF", spares)})
    return {names[name]: {"name": name, "slot": slot, "loc": LOC_OF_SLOT[slot], "rot": str(rot)}
            for slot, (name, rot) in LAYOUTS[layout].items()}


SPARES_FILE = HERE / "spares.txt"


def parse_spares(text: str | None, need: bool = True) -> list[int]:
    if not text and SPARES_FILE.exists():
        text = SPARES_FILE.read_text().strip()
    if not text:
        if need:
            sys.exit("Say which tags the 6 spare trays carry, A to F in order, once:  m4 spares 1,2,3,4,5,6")
        return []
    try:
        ids = [int(x) for x in text.split(",")]
    except ValueError:
        sys.exit(f"--spares wants six whole numbers separated by commas, got {text!r}")
    if len(ids) != 6 or len(set(ids)) != 6 or set(ids) & set(FIXED.values()):
        sys.exit("--spares needs 6 different IDs, none of them 8, 9, 11, 12, 25 or 51 (experiment 4's trays).")
    return ids


# ----------------------------------------------------------------------------------------------
def cmd_spares(args) -> None:
    ids = parse_spares(args.ids)
    SPARES_FILE.write_text(",".join(map(str, ids)))
    say("Spare trays: " + ", ".join(f"{letter} = tag {tag}" for letter, tag in zip("ABCDEF", ids)))


def cmd_plan(args) -> None:
    plan = expected(args.layout, parse_spares(args.spares))
    by_slot = {v["slot"]: (tid, v) for tid, v in plan.items()}
    say(f"Layout {args.layout}: slot, tag, tray, rotation (0 = A1 south-west, 180 = A1 north-east), table location")
    for row in "NS":
        say(f"  {row} row, west to east:")
        for n in range(1, 7):
            tid, v = by_slot[f"{row}{n}"]
            say(f"    {row}{n}  tag {tid:>3}  {v['name']:<4} {v['rot']:>3} deg  {v['loc']}")


def cmd_preflight(args) -> None:
    ready, why = True, []
    try:
        exps = experiments()
    except Exception as exc:  # noqa: BLE001
        say(f"NOT READY: the rig does not answer at {RIG}: {exc}")
        return
    running = [e for e in exps if e["state"] == "running"]
    for e in running:
        say(f"Running experiment: #{e['id']} {e['name']!r}, a photo every {e['interval_s'] / 60:g} min, "
            f"{e['schedule']['photos_taken']} photos since the last start, next at {e['schedule']['next_photo_at'][11:19]}Z")
    if not running:
        say("No experiment is running (fine: nothing is photographing now).")
    for e in exps:
        if e["state"] == "set up":
            say(f"Set up, not started: #{e['id']} {e['name']!r}")
    items = captures(None, 1)
    if items:
        it = items[0]
        t = datetime.fromisoformat(it["timestamp"])
        age = (now() - t).total_seconds()
        ex = (it.get("trays") or {}).get("exclusion")
        lights = "ON" if ex is None else {"lights off": "OFF", "light changing": "CHANGING"}.get(ex, f"on, but {ex}")
        say(f"Newest photo: {stamp(t)}, {age / 60:.1f} min ago. Lights: {lights}.")
        rec = it.get("record") or {}
        say(f"Calibration {rec.get('calibration')}, validation {rec.get('validation')}, lens {it.get('lens_position')}, "
            f"focus locked {it.get('focus', {}).get('locked')}")
        if ex in ("lights off", "light changing"):
            ready = False
            why.append("lights are not fully on (they are on about 08:35 to 00:00 UTC)")
        if running and age > 2.5 * running[0]["interval_s"]:
            ready = False
            why.append("the running experiment has not taken a photo for 2.5 intervals")
        flags = [name for name in ("lens_check", "uptime", "camera_fault", "validation", "clock") if it.get(name, {}).get("flagged")]
        if it.get("flags"):
            flags += it["flags"]
        if not (it.get("clock") or {}).get("synchronized", True):
            flags.append("clock not synchronised")
        if flags:
            ready = False
            why.append("the newest photo carries flags: " + ", ".join(map(str, flags)))
        tr = it.get("trays") or {}
        if tr.get("status") == "read":
            ids = sorted(t["tray_id"] for t in tr["trays"] if t["tray_id"] is not None)
            say(f"Trays read in it: {ids}" + ("" if set(ids) == set(FIXED.values()) else
                f"   NOTE: experiment 4's trays were {sorted(FIXED.values())}; the layouts name them as X8 ... X51"))
    try:
        v = subprocess.run(["ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes", "pi@npec-rig-01",
                            "git -C ~/npec_camera_rig log --oneline -1; df -h /var/lib/npec-rig | tail -1; systemctl is-active npec-rig"],
                           capture_output=True, text=True, timeout=30).stdout.strip().splitlines()
        say("App version: " + v[0] + " | disk: " + " ".join(v[1].split()[3:5]) + " free of " + v[1].split()[1] + " | service: " + v[2])
    except Exception as exc:  # noqa: BLE001
        say(f"(ssh read of the version and disk skipped: {exc})")
    try:
        label = subprocess.run(["gh", "api", "repos/txoof/npec-camera-rig/issues?labels=hardware&state=open", "--jq",
                                '.[] | "#\\(.number) \\(.title)"'], capture_output=True, text=True, timeout=30).stdout.strip()
        say("Issues holding the hardware label: " + (label or "none"))
        if label and not label.startswith("#72"):
            ready = False
            why.append("another issue holds the hardware label")
    except Exception as exc:  # noqa: BLE001
        say(f"(hardware label read skipped: {exc})")
    say("READY" if ready else "NOT READY: " + "; ".join(why))


def annotate(jpg: Path, trays: dict) -> None:
    """Write each tray's tag number large on its centre, and a small square at its A1 corner."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.open(jpg).convert("RGB")
    k = img.width / 9152  # the 64MP photo is 9152 px wide
    d = ImageDraw.Draw(img)
    big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64)
    for tid, t in trays.items():
        x, y = t["centre_px"][0] * k, t["centre_px"][1] * k
        text = str(tid)
        w = d.textlength(text, font=big)
        d.rectangle([x - w / 2 - 14, y - 44, x + w / 2 + 14, y + 44], fill=(0, 0, 0))
        d.text((x - w / 2, y - 40), text, font=big, fill=(255, 255, 255))
    img.save(jpg, quality=90)


def cmd_snapshot(args) -> None:
    exp = pick_experiment(args.exp)
    for it in captures(exp["id"], 40, args.before):
        tr = it.get("trays") or {}
        if tr.get("status") == "read" and tr.get("exclusion") is None:
            break
    else:
        sys.exit("No lit, read photo among the newest 40.")
    reading = full_reading(it)
    out = {"exp": exp["id"], "name": exp["name"], "photo": it["path"], "taken_at": it["timestamp"], "trays": {}}
    say(f"Experiment #{exp['id']} {exp['name']!r}, photo {stamp(datetime.fromisoformat(it['timestamp']))}")
    say("tray  location  A1 corner (rotation)  centre_px")
    for t in sorted(reading["trays"], key=lambda t: (t["tray_id"] is None, t["tray_id"])):
        side = a1_side(t)
        out["trays"][str(t["tray_id"])] = {"location": t.get("location"), "a1": side, "centre_px": [round(c) for c in t["centre_px"]]}
        say(f"{t['tray_id']!s:>4}  {t.get('location')}        {side} ({rotation_of(side)})  {[round(c) for c in t['centre_px']]}")
    folder = HERE / "before"
    folder.mkdir(exist_ok=True)
    (folder / "before.json").write_text(json.dumps(out, indent=1))
    jpg = folder / "before-exp4-layout.jpg"
    jpg.write_bytes(get("/gallery/image/screen/" + it["path"], raw=True))
    annotate(jpg, out["trays"])
    say(f"Saved {folder / 'before.json'} and the picture {jpg}")
    say("Show it: http://testpi-02:8001/72-m4-acceptance/before/before-exp4-layout.jpg")


def swapped() -> bool:
    return LOG.exists() and any(" NOTE swap" in ln for ln in LOG.read_text().splitlines())


def cmd_look(args) -> None:
    exp = pick_experiment(args.exp)
    auto = args.layout is None
    args.layout = args.layout or (2 if swapped() else 1)
    plan = expected(args.layout, parse_spares(args.spares)) if args.layout else {}
    items = captures(exp["id"], max(args.photos * 4, 12), args.before)
    say(f"Experiment #{exp['id']} {exp['name']!r}. Layout {args.layout}{(' (automatic: ' + ('after' if swapped() else 'before') + ' the swap note)') if auto else ''}. Looking at the newest {args.photos} photos.")
    verdicts = []
    shown = 0
    for it in items:
        if shown >= args.photos:
            break
        shown += 1
        t = datetime.fromisoformat(it["timestamp"])
        tr = it.get("trays")
        if not tr:
            say(f"\n{stamp(t)}  not read for trays yet (wait a minute and run again)")
            verdicts.append(("unread", []))
            continue
        ex = tr.get("exclusion")
        if tr["status"] != "read":
            say(f"\n{stamp(t)}  status: {tr['status']}" + (f", {ex}" if ex else ""))
            verdicts.append((tr["status"], []))
            continue
        reading = full_reading(it)
        trays = reading["trays"]
        problems = []
        found = {}
        say(f"\n{stamp(t)}  {len(trays)} trays read" + (f"  [excluded: {ex}]" if ex else "") + f"  [{it['key']}]")
        for tray in sorted(trays, key=lambda x: (x["tray_id"] is None, x["tray_id"] or 0)):
            side = a1_side(tray)
            tid = tray["tray_id"]
            line = f"  tray {tid if tid is not None else 'NO TAG':>6}  in {tray.get('location')}  A1 {side} (rot {rotation_of(side)})  {tray['found']}"
            if tray.get("warnings"):
                line += "  WARN: " + "; ".join(w[:80] for w in tray["warnings"])
            if tid is not None:
                found[tid] = tray
            say(line)
        if plan:
            for tid, want in sorted(plan.items(), key=lambda kv: SLOTS.index(kv[1]["slot"])):
                tray = found.get(tid)
                if tray is None:
                    problems.append(f"tray {tid} ({want['name']}, {want['slot']}) not read")
                    continue
                if tray["found"] != "photo + tag":
                    problems.append(f"tray {tid} found only as '{tray['found']}'")
                if tray.get("location") != want["loc"]:
                    problems.append(f"tray {tid} in {tray.get('location')}, planned {want['slot']} = {want['loc']}")
                rot = rotation_of(a1_side(tray))
                if rot != want["rot"]:
                    problems.append(f"tray {tid} turned {rot}, planned {want['rot']}")
            for tid in found:
                if tid not in plan:
                    problems.append(f"UNEXPECTED tag {tid}: not in the layout (a misread, or a tray not on the sheet)")
            if sum(1 for tr_ in trays if tr_["tray_id"] is None):
                problems.append("a tray outline with no tag")
        for nf in reading.get("not_found", []):
            say(f"  NOT SEEN in this photo: tray {nf['tray_id']} (last seen {nf.get('location')}, {nf['photos']} photos missed)")
            if plan and nf["tray_id"] not in plan:
                pass
        for mv in reading.get("moved", []):
            say(f"  MOVED since the previous photo: tray {mv['tray_id']} {mv['from']} to {mv['to']}")
        if args.focus is not None:
            tray = found.get(args.focus)
            nf = [n for n in reading.get("not_found", []) if n["tray_id"] == args.focus]
            unknown = [t_ for t_ in found if plan and t_ not in plan]
            untagged = [x for x in trays if x["tray_id"] is None]
            if tray and tray["found"] == "photo + tag":
                say(f"  FOCUS tray {args.focus}: READ correctly")
            elif unknown:
                say(f"  FOCUS tray {args.focus}: MISREAD? tag(s) {unknown} read that are not in the layout  <-- a lie, FAIL")
            elif untagged or nf:
                say(f"  FOCUS tray {args.focus}: degraded as expected ({'outlined with no tag' if untagged else ''}"
                    f"{' and ' if untagged and nf else ''}{'reported not seen' if nf else ''})")
            else:
                say(f"  FOCUS tray {args.focus}: ABSENT and NOT REPORTED  <-- check by eye, possible FAIL")
        if plan:
            say(f"  => {'PASS' if not problems else 'DIFFERS'}: " + (f"all {len(plan)} trays as planned" if not problems else "; ".join(problems)))
        verdicts.append((ex or "lit", problems))
    if plan:
        lit = [(k, p) for k, p in verdicts if k not in ("unread", "light changing", "lights off") and k != "no trays found"]
        clean = [k for k, p in lit if not p]
        say(f"\nSUMMARY: {len(clean)} of {len(verdicts)} photos match layout {args.layout} exactly "
            f"({'CHECK PASSES if every photo since the last move is among them' if clean else 'none match'}).")


def panel_trays(exp_id: int) -> tuple[list[str], dict[int, dict]]:
    text = get(f"/experiments/{exp_id}/table-locations", raw=True).decode()
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", text, flags=re.S)
    lines = [ln.strip() for ln in html.unescape(re.sub(r"<[^>]+>", "\n", text)).splitlines() if ln.strip()]
    head = [ln for ln in lines[:2]]
    trays: dict[int, dict] = {}
    cur = None
    for i, ln in enumerate(lines):
        m = re.fullmatch(r"Tray (\d+)", ln)
        if m and any(x in ("Hide", "Show") for x in lines[i + 1:i + 3]):
            cur = trays.setdefault(int(m.group(1)), {"now": None, "moves": [], "warning": None})
            continue
        if cur is None:
            continue
        if m := re.match(r"Now in (\w\w), (.*)", ln):
            cur["now"] = (m.group(1), m.group(2))
        elif m := re.match(r"\d+\. (\w\w) to (\w\w), (.*)", ln):
            cur["moves"].append((m.group(1), m.group(2), m.group(3)))
        elif ln.startswith("Too long"):
            cur["warning"] = ln
    return head, trays


def cmd_dwell(args) -> None:
    exp = pick_experiment(args.exp)
    plan = expected(args.layout, parse_spares(args.spares)) if args.layout else {}
    head, trays = panel_trays(exp["id"])
    say(f"Experiment #{exp['id']} {exp['name']!r}: Table locations panel")
    say("  " + head[0])
    notes = [ln for ln in (LOG.read_text().splitlines() if LOG.exists() else []) if " NOTE swap" in ln]
    if notes:
        swap_at = datetime.strptime(notes[-1].split()[0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        ready_at = swap_at + MOVE_AFTER + timedelta(minutes=4, seconds=exp["interval_s"] or 60)
        say(f"  Swap noted at {stamp(swap_at)}; the move shows from about {stamp(ready_at)} (1 hour in the new location, plus a few photos).")
    for tid, d in sorted(trays.items()):
        moves = "; ".join(f"{a} to {b}, {when}" for a, b, when in d["moves"]) or "no moves"
        say(f"  tray {tid:>3}: now {d['now'][0] if d['now'] else '?'} ({d['now'][1] if d['now'] else ''}); moves: {moves}")
    if args.layout == 2:
        spares = parse_spares(args.spares)
        a, f = spares[4], spares[5]  # trays E and F
        ok = True
        for tid, frm, to in ((a, "SM", "SE"), (f, "SE", "SM")):
            d = trays.get(tid)
            hit = d and (frm, to) in [(x, y) for x, y, _ in d["moves"]] and d["now"] and d["now"][0] == to
            ok &= bool(hit)
            say(f"  tray {tid}: planned {frm} to {to}: " + ("PASS, the table follows it" if hit else
                "NOT YET (wait until the time above, then run again)"))
        others = [tid for tid, d in trays.items() if tid not in (a, f) and d["moves"] and tid in plan]
        if others:
            say(f"  NOTE: other trays also show moves: {others}. Check whether a tray was bumped.")
        say("CHECK 2 PASSES" if ok and not others else "CHECK 2 NOT YET PASSED" if not ok else "CHECK 2 passes for A and F; see the NOTE above")


def cmd_restore(args) -> None:
    before = json.loads((HERE / "before" / "before.json").read_text())
    say(f"Comparing experiment {args.exp} now against the snapshot of {before['taken_at'][:19]}Z")
    exp = pick_experiment(args.exp)
    say(f"Experiment #{exp['id']} state: {exp['state']}" + ("" if exp["state"] == "running" else "   <-- RESUME IT (Experiments page, Resume)"))
    if args.test_exp:
        te = pick_experiment(args.test_exp)
        say(f"Test experiment #{te['id']} state: {te['state']}" + ("   <-- STOP IT" if te["state"] == "running" else ""))
    items = captures(exp["id"], 6)
    newest = items[0]
    t = datetime.fromisoformat(newest["timestamp"])
    age = (now() - t).total_seconds() / 60
    say(f"Newest photo of experiment {exp['id']}: {stamp(t)}, {age:.1f} min ago")
    taken_after_snapshot = [i for i in items if i["timestamp"] > before["taken_at"]]
    lit = next((i for i in taken_after_snapshot if (i.get("trays") or {}).get("status") == "read" and (i["trays"].get("exclusion") is None)), None)
    if not lit:
        say("No lit, read photo of the experiment since the snapshot yet. Wait for one and run again.")
        return
    reading = full_reading(lit)
    now_trays = {str(t_["tray_id"]): t_ for t_ in reading["trays"]}
    bad = []
    for tid, was in before["trays"].items():
        cur = now_trays.get(tid)
        if cur is None:
            bad.append(f"tray {tid} not read")
            continue
        side = a1_side(cur)
        dx = ((cur["centre_px"][0] - was["centre_px"][0]) ** 2 + (cur["centre_px"][1] - was["centre_px"][1]) ** 2) ** 0.5
        ok = cur.get("location") == was["location"] and side == was["a1"]
        say(f"  tray {tid}: {was['location']} A1 {was['a1']} -> {cur.get('location')} A1 {side}, centre moved {dx:.0f} px"
            f" ({dx / 4.85:.0f} mm){'' if ok else '   <-- DIFFERS'}")
        if not ok:
            bad.append(f"tray {tid}")
    extra = [t_ for t_ in now_trays if t_ not in before["trays"]]
    if extra:
        bad.append(f"extra trays still on the table: {extra}")
        say(f"  EXTRA trays read: {extra}")
    say("RESTORED: experiment 4's trays are where they were and it is running." if not bad and exp["state"] == "running"
        else "NOT RESTORED: " + ("; ".join(bad) or "experiment not running"))


def cmd_note(args) -> None:
    line = f"{now():%Y-%m-%dT%H:%M:%SZ} NOTE {args.text}"
    say(line)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preflight").set_defaults(fn=cmd_preflight)
    s = sub.add_parser("snapshot"); s.add_argument("--exp", type=int); s.add_argument("--before"); s.set_defaults(fn=cmd_snapshot)
    s = sub.add_parser("spares"); s.add_argument("ids"); s.set_defaults(fn=cmd_spares)
    s = sub.add_parser("plan"); s.add_argument("--layout", type=int, choices=(1, 2), default=1); s.add_argument("--spares"); s.set_defaults(fn=cmd_plan)
    s = sub.add_parser("look")
    s.add_argument("--exp", type=int); s.add_argument("--layout", type=int, choices=(1, 2)); s.add_argument("--spares")
    s.add_argument("--photos", type=int, default=5); s.add_argument("--focus", type=int); s.add_argument("--before")
    s.set_defaults(fn=cmd_look)
    s = sub.add_parser("dwell")
    s.add_argument("--exp", type=int); s.add_argument("--layout", type=int, choices=(1, 2), default=2); s.add_argument("--spares")
    s.set_defaults(fn=cmd_dwell)
    s = sub.add_parser("restore"); s.add_argument("--exp", type=int, required=True); s.add_argument("--test-exp", type=int)
    s.set_defaults(fn=cmd_restore)
    s = sub.add_parser("note"); s.add_argument("text"); s.set_defaults(fn=cmd_note)
    args = p.parse_args()
    try:
        args.fn(args)
    finally:
        if _out:
            with LOG.open("a") as f:
                f.write(f"\n=== {now():%Y-%m-%dT%H:%M:%SZ} {' '.join(sys.argv[1:])} ===\n" if args.cmd != "note" else "")
                f.write("\n".join(_out) + "\n")


if __name__ == "__main__":
    main()
