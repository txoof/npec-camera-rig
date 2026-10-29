"""How far the light moves in photos already taken: metrology log 17.8 (#288).

Reads rig.db read-only. For each experiment: E = exposure (us) x analogue gain per capture photo,
lights off at E >= 200,000 (17.7). Prints the tables of 17.8's questions 1 to 4 and writes one
CSV per experiment (time, E, ratio to previous, ratio to the first day's steady median).

    python3 light_review.py /var/lib/npec-rig/rig.db --experiment 16 18 --out DIR
"""

import argparse
import csv
import math
import sqlite3
import statistics
from datetime import datetime, timedelta
from pathlib import Path

DARK = 200_000
NEAR_DARK = timedelta(minutes=60)  # photos this close to a lights-off photo may be in a fade
SHUFFLE_1 = (datetime.fromisoformat("2026-10-23T08:43:00+00:00"), datetime.fromisoformat("2026-10-23T08:56:00+00:00"))


def photos(db: Path, experiment: int) -> list[dict]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = conn.execute(
        "SELECT taken_at, exposure_us, analogue_gain FROM capture WHERE experiment_id = ? AND purpose = 'capture'"
        " ORDER BY taken_at", (experiment,)).fetchall()
    return [{"t": datetime.fromisoformat(t), "e": x * g, "x": x, "g": g} for t, x, g in rows]


def pct(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(q * len(s)))]


def runs(flags: list[bool]) -> list[tuple[int, int]]:
    out, start = [], None
    for i, f in enumerate(flags + [False]):
        if f and start is None:
            start = i
        if not f and start is not None:
            out.append((start, i - 1))
            start = None
    return out


def review(db: Path, experiment: int, out: Path) -> None:
    p = photos(db, experiment)
    dark_times = [q["t"] for q in p if q["e"] >= DARK]
    for i, q in enumerate(p):
        q["step"] = q["e"] / p[i - 1]["e"] if i else 1.0
        q["near_dark"] = any(abs(q["t"] - t) <= NEAR_DARK for t in dark_times)
    first_day = [q for q in p if q["t"] < p[0]["t"] + timedelta(hours=24)]
    steady = [q for q in first_day if q["e"] < DARK and not q["near_dark"]]
    norm = statistics.median(q["e"] for q in steady)
    for q in p:
        q["to_norm"] = q["e"] / norm
    gaps = [(b["t"] - a["t"]).total_seconds() for a, b in zip(p, p[1:])]
    print(f"\n## Experiment {experiment}: {len(p)} photos, {p[0]['t']:%d %b %H:%M} to {p[-1]['t']:%d %b %H:%M} UTC,"
          f" interval median {statistics.median(gaps):.0f} s")

    lstep = [abs(math.log(q["step"])) for q in steady[1:]]
    lnorm = [abs(math.log(q["to_norm"])) for q in steady]
    f = lambda v: f"{(math.exp(v) - 1) * 100:.1f}%"
    print(f"Q1 steady, first 24 h: {len(steady)} photos, norm E = {norm:,.0f}"
          f" (exposure {statistics.median(q['x'] for q in steady):,.0f} us, gain {statistics.median(q['g'] for q in steady)})")
    print(f"   step to previous: median {f(statistics.median(lstep))}, 99th {f(pct(lstep, 0.99))}, largest {f(max(lstep))}")
    print(f"   off the norm:     median {f(statistics.median(lnorm))}, 99th {f(pct(lnorm, 0.99))}, largest {f(max(lnorm))}")
    later = [q for q in p if q not in first_day and q["e"] < DARK and not q["near_dark"]]
    if later:
        ln = [abs(math.log(q["to_norm"])) for q in later]
        print(f"   after 24 h, steady photos off the first day's norm: median {f(statistics.median(ln))},"
              f" 99th {f(pct(ln, 0.99))}, largest {f(max(ln))}; median E {statistics.median(q['e'] for q in later):,.0f}")

    print("Q2 fades (photos within 60 min of lights off, E off the norm by more than the steady largest):")
    limit = max(lnorm)
    off = [q["e"] < DARK and abs(math.log(q["to_norm"])) > limit for q in p]
    for a, b in runs(off):
        seg = p[a:b + 1]
        steps = [abs(math.log(q["step"])) for q in seg[1:]] or [0.0]
        kind = "next to lights off" if any(q["near_dark"] for q in seg) else "away from lights off"
        print(f"   {seg[0]['t']:%d %b %H:%M:%S} to {seg[-1]['t']:%H:%M:%S}: {len(seg)} photos, "
              f"{(seg[-1]['t'] - seg[0]['t']).total_seconds() / 60:.0f} min, E {min(q['e'] for q in seg):,.0f} to "
              f"{max(q['e'] for q in seg):,.0f}, step median {f(statistics.median(steps))} largest {f(max(steps))}, {kind}")

    s1 = [q for q in p if SHUFFLE_1[0] - timedelta(minutes=10) <= q["t"] <= SHUFFLE_1[1] + timedelta(minutes=10)]
    if s1:
        print("Q3 shuffle 1, 08:33 to 09:06 UTC on 23 October (people at the table 08:43 to 08:56):")
        for q in s1:
            inside = "*" if SHUFFLE_1[0] <= q["t"] <= SHUFFLE_1[1] else " "
            print(f"   {inside} {q['t']:%H:%M:%S} E {q['e']:>9,.0f}  step {(q['step'] - 1) * 100:+6.1f}%  to norm {(q['to_norm'] - 1) * 100:+6.1f}%")

    levels = sorted({round(math.log(q["e"]) / math.log(1.25)) for q in p if q["e"] < DARK and not q["near_dark"]})
    print(f"Q4 steady lit levels (E bands of 25%, photos away from lights off): {len(levels)} bands, E "
          + ", ".join(f"{1.25 ** l:,.0f}" for l in levels))

    out.mkdir(parents=True, exist_ok=True)
    with open(out / f"light-e{experiment}.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["taken_at", "exposure_us", "analogue_gain", "e", "ratio_to_previous", "ratio_to_norm"])
        for q in p:
            w.writerow([q["t"].isoformat(), q["x"], q["g"], q["e"], f"{q['step']:.4f}", f"{q['to_norm']:.4f}"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("db", type=Path)
    ap.add_argument("--experiment", type=int, nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    for e in a.experiment:
        review(a.db, e, a.out)
