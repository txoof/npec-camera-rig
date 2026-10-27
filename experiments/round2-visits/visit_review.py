"""People at the table in photos already taken: metrology log 17.9 (#288).

Reads rig.db read-only. For each capture photo of the experiment with no light exclusion (17.8)
and trays read: each tray's area against its usual level (the median of its areas in the 10
photos before), and the trays found in the photos before and after but missing from this one.
Prints the tables of 17.9's questions 1 to 4 and writes one CSV row per photo.

    python3 visit_review.py /var/lib/npec-rig/rig.db --experiment 18 --out DIR
"""

import argparse
import csv
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

USUAL = 10  # photos before, for a tray's usual level
NEAR = timedelta(minutes=10)  # either side of a visit Aaron gave as one time
LATER = (10, 30)  # photos after a jump in which a step that stays is looked for (question 4)
THRESHOLDS_MM2 = [100, 150, 200, 250, 500]
# The rule chosen (Aaron, 2026-10-27, 17.9): a jump of more than JUMP_MM2 and JUMP_RATIO times,
# up or down; photos between two marked photos at most GAP photos apart are marked too.
JUMP_MM2, JUMP_RATIO, GAP = 250, 2, 4
RATIOS = [1.5, 2, 3]  # a jump counts when it is larger than the mm2 threshold and this ratio, up or down


def t(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


# Known visits, UTC (17.9). A single time gets NEAR either side.
KNOWN = [
    ("benchmark on tray 8", t("2026-10-22T09:33:00+00:00") - NEAR, t("2026-10-22T09:33:00+00:00") + NEAR),
    ("shuffle 1", t("2026-10-23T08:43:00+00:00"), t("2026-10-23T08:56:00+00:00") + NEAR),
    ("23 Oct 10:56 local", t("2026-10-23T08:56:00+00:00") - NEAR, t("2026-10-23T08:56:00+00:00") + NEAR),
    ("target on tray 10", t("2026-10-23T14:02:00+00:00") - NEAR, t("2026-10-23T14:02:00+00:00") + NEAR),
    ("sheets on the pots", t("2026-10-26T08:25:00+00:00") - NEAR, t("2026-10-26T08:25:00+00:00") + NEAR),
    ("tray moved", t("2026-10-26T10:30:00+00:00") - NEAR, t("2026-10-26T10:35:00+00:00") + NEAR),
    ("27 Oct 09:45 local", t("2026-10-27T08:45:00+00:00") - NEAR, t("2026-10-27T08:45:00+00:00") + NEAR),
    ("27 Oct 10:49 local", t("2026-10-27T09:49:00+00:00") - NEAR, t("2026-10-27T09:49:00+00:00") + NEAR),
]
MONDAY = (t("2026-10-26T00:00:00+00:00"), t("2026-10-27T00:00:00+00:00"))


def photos(db: Path, experiment: int) -> list[dict]:
    """Capture photos with trays read and no light exclusion, oldest first: time and areas."""
    import sqlite3

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = conn.execute(
        "SELECT c.id, c.taken_at FROM capture c JOIN tray_read r ON r.capture_id = c.id"
        " LEFT JOIN exclusion x ON x.capture_id = c.id"
        " WHERE c.experiment_id = ? AND c.purpose = 'capture' AND r.status = 'read' AND x.name IS NULL"
        " ORDER BY c.taken_at", (experiment,)).fetchall()
    areas = defaultdict(dict)
    for cid, tray, area in conn.execute(
        "SELECT tr.capture_id, tr.tray_id, tr.area_mm2 FROM tray_reading tr JOIN capture c ON c.id = tr.capture_id"
        " WHERE c.experiment_id = ? AND tr.area_mm2 IS NOT NULL", (experiment,)):
        areas[cid][tray] = area
    return [{"t": t(taken), "areas": areas.get(cid, {})} for cid, taken in rows]


def where(when: datetime) -> str:
    for name, a, b in KNOWN:
        if a <= when <= b:
            return name
    return "Monday" if MONDAY[0] <= when < MONDAY[1] else ""


def review(ps: list[dict]) -> list[dict]:
    history = defaultdict(list)
    out = []
    for i, p in enumerate(ps):
        jumps = {}
        for tray, area in p["areas"].items():
            before = history[tray][-USUAL:]
            if len(before) == USUAL:
                usual = statistics.median(before)
                jumps[tray] = (area - usual, area / usual if usual > 0 else float("inf"), usual)
        missing = []
        if 0 < i < len(ps) - 1:
            missing = sorted(set(ps[i - 1]["areas"]) & set(ps[i + 1]["areas"]) - set(p["areas"]))
        top = max(jumps.items(), key=lambda kv: abs(kv[1][0]), default=(None, (0.0, 1.0, None)))
        out.append({"t": p["t"], "where": where(p["t"]), "jumps": jumps, "missing": missing,
                    "top_tray": top[0], "top_mm2": top[1][0], "top_ratio": top[1][1], "top_usual": top[1][2]})
        for tray, area in p["areas"].items():
            history[tray].append(area)
    return out


def pct(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(q * len(s)))] if s else float("nan")


def big(jump: tuple, threshold: float, ratio: float) -> bool:
    mm2, r, _usual = jump
    return abs(mm2) > threshold and (r > ratio or r < 1 / ratio)


def marked(r: dict, threshold: float, ratio: float) -> bool:
    return bool(r["missing"]) or any(big(j, threshold, ratio) for j in r["jumps"].values())


def stays(rows: list[dict], threshold: float, ratio: float) -> int:
    """Question 4: jumps over the threshold after which the same tray is still over it, the same
    way, in every photo LATER[0] to LATER[1] photos on."""
    count = 0
    for i, r in enumerate(rows):
        for tray, (mm2, _ratio, usual) in r["jumps"].items():
            if not big((mm2, _ratio, usual), threshold, ratio):
                continue
            later = [rows[j]["jumps"].get(tray) for j in range(i + LATER[0], min(len(rows), i + LATER[1] + 1))]
            later_areas = [rows[j]["t"] for j in range(i + LATER[0], min(len(rows), i + LATER[1] + 1))]
            if later and len(later_areas) == LATER[1] - LATER[0] + 1:
                # the area itself against the usual level before the jump
                if all(v is not None and big((v[2] + v[0] - usual, (v[2] + v[0]) / usual if usual else float("inf"), usual), threshold, ratio)
                       for v in later):
                    count += 1
                    break
    return count


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("db", type=Path)
    ap.add_argument("--experiment", type=int, default=18)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    rows = review(photos(a.db, a.experiment))
    away = [r for r in rows if r["where"] == "" and r["top_usual"] is not None]
    print(f"{len(rows)} photos used (trays read, no light exclusion), {len(away)} away from known visits and Monday\n")

    print("Q1. Largest jump per photo, away from known visits and Monday")
    up = [r["top_mm2"] for r in away]
    print(f"  |jump| mm2: median {pct([abs(v) for v in up], 0.5):.0f}, 99% {pct([abs(v) for v in up], 0.99):.0f},"
          f" 99.9% {pct([abs(v) for v in up], 0.999):.0f}, largest {max(abs(v) for v in up):.0f}")
    print(f"  up: largest {max(up):.0f}; down: largest {min(up):.0f}")
    print(f"  ratio: 99% {pct([r['top_ratio'] for r in away], 0.99):.2f}, largest {max(r['top_ratio'] for r in away):.2f}\n")

    print("Q2. Photos with a tray missing (found before and after)")
    print(f"  away: {sum(1 for r in away if r['missing'])} of {len(away)}")
    for name, _a, _b in KNOWN + [("Monday", None, None)]:
        here = [r for r in rows if r["where"] == name]
        if here:
            print(f"  {name}: {sum(1 for r in here if r['missing'])} of {len(here)}")
    print()

    print("Q1/Q3. Each known visit: photos, largest jump, photos missing a tray, first to last photo marked at 100 mm2 and 2x")
    for name, _a, _b in KNOWN:
        here = [r for r in rows if r["where"] == name]
        if not here:
            print(f"  {name}: no photos used")
            continue
        worst = max(here, key=lambda r: abs(r["top_mm2"]))
        m = [r for r in here if marked(r, 100, 2)]
        span = f"{m[0]['t']:%H:%M} to {m[-1]['t']:%H:%M}, {len(m)} photos" if m else "none marked"
        print(f"  {name}: {len(here)} photos, largest jump {worst['top_mm2']:+.0f} mm2 (tray {worst['top_tray']},"
              f" usual {worst['top_usual'] or 0:.0f}) at {worst['t']:%H:%M}, missing in {sum(1 for r in here if r['missing'])}; {span}")
    print()

    print("Rules: photos marked (a tray missing, or a jump larger than both the mm2 and the ratio)")
    print("   mm2 | ratio | away | Monday | known visits caught | steps that stay (Q4)")
    for th in THRESHOLDS_MM2:
        for ratio in RATIOS:
            caught = [n for n, _a, _b in KNOWN if any(marked(r, th, ratio) for r in rows if r["where"] == n)]
            print(f"  {th:>4} | {ratio:>5} | {sum(1 for r in away if marked(r, th, ratio)):>4} |"
                  f" {sum(1 for r in rows if r['where'] == 'Monday' and marked(r, th, ratio)):>6} | {len(caught)} of {len(KNOWN)} | {stays(rows, th, ratio)}")
    print(f"  a tray missing only: away {sum(1 for r in away if r['missing'])}, trays: "
          + str(__import__("collections").Counter(tuple(r["missing"]) for r in away if r["missing"]).most_common(6)))
    print("  away, a tray missing, by UTC day and hour: " + ", ".join(
        f"{h} ({n})" for h, n in sorted(__import__("collections").Counter(f"{r['t']:%d %H}h" for r in away if r["missing"]).items())))
    jumps_away = [r for r in away if any(big(j, 100, 2) for j in r["jumps"].values())]
    print("  away, jump at 100 mm2 and 2x, by UTC hour: " + ", ".join(
        f"{h} ({n})" for h, n in sorted(__import__("collections").Counter(f"{r['t']:%d %H}h" for r in jumps_away).items())))

    flags = [any(big(j, JUMP_MM2, JUMP_RATIO) for j in r["jumps"].values()) for r in rows]
    marks = [i for i, f in enumerate(flags) if f]
    filled = set(marks)
    for i, j in zip(marks, marks[1:]):
        if j - i <= GAP:
            filled.update(range(i, j))
    print(f"\nChosen rule, {JUMP_MM2} mm2 and {JUMP_RATIO}x, gaps of up to {GAP} photos filled:"
          f" {len(marks)} photos marked, {len(filled)} with the gaps filled")
    for name in [n for n, _a, _b in KNOWN] + ["Monday", ""]:
        here = [i for i, r in enumerate(rows) if r["where"] == name]
        m = sorted(i for i in here if i in filled)
        span = f", {rows[m[0]]['t']:%H:%M} to {rows[m[-1]]['t']:%H:%M} UTC" if m else ""
        print(f"  {name or 'away from known visits and Monday'}: {len(m)} of {len(here)} photos{span}")
    print(f"  steps that stay (Q4): {stays(rows, JUMP_MM2, JUMP_RATIO)}")
    for r_i in sorted(filled):
        r = rows[r_i]
        r["visit"] = True

    a.out.mkdir(parents=True, exist_ok=True)
    path = a.out / f"visits-e{a.experiment}.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["taken_at", "known", "top_tray", "top_jump_mm2", "top_ratio", "top_usual_mm2", "missing_trays", "visit"])
        for r in rows:
            w.writerow([r["t"].isoformat(), r["where"], r["top_tray"] if r["top_tray"] is not None else "",
                        f"{r['top_mm2']:.1f}", f"{r['top_ratio']:.3f}", "" if r["top_usual"] is None else f"{r['top_usual']:.1f}",
                        " ".join(map(str, r["missing"])), "visit" if r.get("visit") else ""])
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
