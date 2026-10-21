"""Summary of tag_detector_check.py's output for metrology log section 15.3e (issue #156).

Reads only the CSV and JSON files beside it; decodes no photo. Run: python3 tag_detector_summary.py
"""

import csv
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = 3

S1_T20, S1_T30 = [1, 2, 3], list(range(4, 13))
R2_T20, R2_T30 = [0, 1, 2, 3, 13, 14, 15, 16, 17], list(range(4, 13))
R2_PAIRS = {4: 0, 5: 14, 6: 16, 7: 17, 8: 13, 11: 15}  # 30 mm : 20 mm, 15.3a


def ids(text):
    return {int(i) for i in text.split()} if text else set()


def describe(values):
    return (f"mean {st.mean(values):.2f} s (SD {st.stdev(values):.2f}), "
            f"{min(values):.2f} to {max(values):.2f}, n {len(values)}")


rows = list(csv.DictReader(open(HERE / "tag-detector-stills.csv")))

print("== Part 1: timing (per still, mean of its 3 runs) ==")
for group in ("round2", "calibration", None):
    sel = [r for r in rows if r["secs_A2"] and (group is None or r["group"] == group)]
    a = [st.mean(float(r[f"secs_A{k}"]) for k in range(1, RUNS + 1)) for r in sel]
    c = [st.mean(float(r[f"secs_C{k}"]) for k in range(1, RUNS + 1)) for r in sel]
    every_a = [float(r[f"secs_A{k}"]) for r in sel for k in range(1, RUNS + 1)]
    every_c = [float(r[f"secs_C{k}"]) for r in sel for k in range(1, RUNS + 1)]
    print(f"-- {group or 'all timed'} ({len(sel)} stills)")
    print("  A          ", describe(a))
    print("  C          ", describe(c))
    print("  A then C   ", describe([x + y for x, y in zip(a, c)]))
    print("  C minus A  ", describe([y - x for x, y in zip(a, c)]))
    print("  every run A", describe(every_a), "| C", describe(every_c))
    print("  run-to-run SD within a still, median: A",
          f"{st.median(st.stdev(float(r[f'secs_A{k}']) for k in range(1, RUNS + 1)) for r in sel):.3f}",
          "C", f"{st.median(st.stdev(float(r[f'secs_C{k}']) for k in range(1, RUNS + 1)) for r in sel):.3f}")
print("load average 1 min during run:", sorted(float(r["loadavg_1min"]) for r in rows)[::10])

print("\n== Part 2: tray tags on 53 stills ==")
for group, t20, t30 in (("session1", S1_T20, S1_T30), ("round2", R2_T20, R2_T30)):
    sel = [r for r in rows if r["group"] == group]
    expected = set(t20) | set(t30)
    for s in "AC":
        found = [(r["step"], r["still"], ids(r[f"found_{s}"])) for r in sel]
        m20 = sum(t not in f for _, _, f in found for t in t20)
        m30 = sum(t not in f for _, _, f in found for t in t30)
        per_tag = defaultdict(int)
        per_step_tag = defaultdict(int)
        for step, _, f in found:
            for t in t20 + t30:
                if t not in f:
                    per_tag[t] += 1
                    per_step_tag[(step, t)] += 1
        steps = sorted({st_ for st_, _, _ in found}, key=lambda x: (len(x), x))
        persistent = []
        for step in steps:
            fs = [f for st_, _, f in found if st_ == step]
            if group == "round2":
                for g30, t20_ in R2_PAIRS.items():
                    if all(t20_ not in f for f in fs) and any(g30 in f for f in fs):
                        persistent.append(f"{step}:{t20_}({len(fs)} stills)")
            else:
                for t in t20:
                    if all(t not in f for f in fs) and any(set(t30) & f for f in fs):
                        persistent.append(f"{step}:{t}({len(fs)} stills{', flagged' if len(fs) < 3 else ''})")
        rule_b = ""
        if group == "round2":
            pairs = [(g30 in f, t20_ in f) for _, _, f in found for g30, t20_ in R2_PAIRS.items()]
            miss20 = sum(a and not b for a, b in pairs)
            miss30 = sum(b and not a for a, b in pairs)
            rule_b = f"; rule B: 20 mm missed with partner read {miss20} of {len(pairs)}, reverse {miss30}"
        unexpected = [(step, still, sorted(i for i in f if i not in expected and not 450 <= i < 500))
                      for step, still, f in found]
        unexpected = [u for u in unexpected if u[2]]
        print(f"-- {group} setting {s}: {len(sel)} stills; 20 mm missed {m20} of {len(sel) * len(t20)}, "
              f"30 mm missed {m30} of {len(sel) * len(t30)}{rule_b}")
        print("   misses per tag:", dict(sorted(per_tag.items())))
        print("   misses per step and tag:", {f"{k[0]}:{k[1]}": v for k, v in sorted(per_step_tag.items())})
        print("   rule A persistent:", persistent or "none")
        print("   unexpected IDs:", unexpected or "none")

print("\n== Part 3: calibration and corner tags, A against C ==")
corners = json.load(open(HERE / "tag-detector-corners.json"))
overall = 0.0
for still, d in corners.items():
    a, c = d["A"], d["C"]
    cal_a = sorted(int(i) for i in a if 300 <= int(i) < 450)
    cal_c = sorted(int(i) for i in c if 300 <= int(i) < 450)
    cor_a = sorted(int(i) for i in a if 450 <= int(i) < 500)
    cor_c = sorted(int(i) for i in c if 450 <= int(i) < 500)
    common = set(a) & set(c)
    diff = max((abs(pa - pc) for i in common for qa, qc in zip(a[i], c[i]) for pa, pc in zip(qa, qc)),
               default=0.0)
    overall = max(overall, diff)
    print(f"{still}: calibration tags A {len(cal_a)} C {len(cal_c)} same {cal_a == cal_c}; "
          f"corner tags A {cor_a} C {cor_c}; largest corner difference {diff:.6f} px; "
          f"only in A {sorted(set(a) - set(c))} only in C {sorted(set(c) - set(a))}")
print(f"largest corner difference over all stills: {overall:.6f} px")
print("\nrun:", json.load(open(HERE / "tag-detector-run.json")))
