"""Tables of the cell-level grown/fixed ratio for log 46.8 from data/cell_ratio*.csv."""
import csv, collections
import numpy as np
D = __file__.rsplit("/code/", 1)[0] + "/data"
rows = list(csv.DictReader(open(D + "/cell_ratio.csv")))
for x in rows: x["fixed"] = float(x["fixed"]); x["grown"] = float(x["grown"])
def pct(v, ps=(0, 1, 5, 50, 95, 99, 100)): return " ".join("%s=%.3g" % (p, np.percentile(v, p)) for p in ps)
groups = {"plant cells, fixed >= 20 mm2": [x for x in rows if x["state"] == "tray with plants" and x["fixed"] >= 20],
          "plant-tray cells, fixed 1 to 20 mm2": [x for x in rows if x["state"] == "tray with plants" and 1 <= x["fixed"] < 20],
          "plant-tray cells, fixed < 1 mm2": [x for x in rows if x["state"] == "tray with plants" and x["fixed"] < 1],
          "emptied-tray cells (production, 23 Nov)": [x for x in rows if x["state"] == "emptied tray"],
          "experiment 20, cells without the target": [x for x in rows if x["state"] == "exp 20 tray"]}
for k, v in groups.items():
    r = [x["grown"] / x["fixed"] for x in v if x["fixed"] > 0]
    print(k, len(v), "cells; with grown>0:", sum(1 for x in v if x["grown"] > 0), "| ratio", pct(r) if r else "-", "| fixed", pct([x["fixed"] for x in v]), "| grown", pct([x["grown"] for x in v]))
print()
print("flagged = grown > R x fixed AND grown - fixed >= A mm2")
for A in (0, 20, 50):
    for R in (2, 2.5, 3, 5):
        out = []
        for k, v in groups.items():
            n = sum(1 for x in v if x["grown"] > R * x["fixed"] and x["grown"] - x["fixed"] >= A and x["grown"] > 0)
            out.append("%d" % n)
        print("A=%2d R=%.1f | " % (A, R) + " | ".join(out))
print("cells of emptied trays holding false plant (grown >= 20 mm2):", sum(1 for x in groups["emptied-tray cells (production, 23 Nov)"] if x["grown"] >= 20), "of", len(groups["emptied-tray cells (production, 23 Nov)"]))
# plant cells: what are the flagged ones (R=2, A=0)?
bad = sorted([x for x in groups["plant cells, fixed >= 20 mm2"] if x["grown"] > 2 * x["fixed"]], key=lambda x: -x["grown"] / x["fixed"])[:8]
for x in bad: print(x["photo"], x["tray"], x["cell"], round(x["fixed"], 1), round(x["grown"], 1))
print("\nreference cells by stratum (grown/fixed, recomputed on the crop)")
ref = list(csv.DictReader(open(D + "/cell_ratio_ref.csv")))
by = collections.defaultdict(list)
for x in ref:
    s = x["stratum"].split(",")[-1].strip() if "blue mat" in x["stratum"] else x["stratum"]
    by[(x["rig"], x["stratum"])].append(x)
for (rig, s), v in sorted(by.items()):
    print(rig, s, len(v), "ratio", " ".join("%.2f" % (float(x["grown_mm2"]) / float(x["fixed_mm2"])) if float(x["fixed_mm2"]) > 0 else "inf(%.0f/%.0f)" % (float(x["grown_mm2"]), float(x["fixed_mm2"])) for x in v), "| fixed mm2", " ".join("%.0f" % float(x["fixed_mm2"]) for x in v))

print("\n=== candidate flags: cells flagged wrongly (a, c) and rightly (b) ===")
refm = {x["id"]: x for x in ref}
def refcells(rig, plant_only=True):
    out = []
    for x in ref:
        if x["rig"] != rig: continue
        st = x["stratum"]
        if st == "empty" or st.startswith("not plant"): continue
        out.append((float(x["fixed_mm2"]), float(x["grown_mm2"])))
    return out
mature = [(x["fixed"], x["grown"]) for x in groups["plant cells, fixed >= 20 mm2"]]
seed_prod = refcells("prod"); seed_dev = refcells("dev")
empt = [(x["fixed"], x["grown"]) for x in groups["emptied-tray cells (production, 23 Nov)"] if x["grown"] >= 20]
empt_all = [(x["fixed"], x["grown"]) for x in groups["emptied-tray cells (production, 23 Nov)"]]
tot_false = sum(g for f, g in empt_all)
sets = [("a1 mature plant cells (production 16-23 Nov, fixed >= 20 mm2)", mature), ("a2 plant cells of the reference set, production (26)", seed_prod), ("c  plant cells of the reference set, development (30)", seed_dev),
        ("b  emptied-tray cells holding false plant (grown >= 20 mm2)", empt)]
print("sizes:", [(n, len(v)) for n, v in sets], "emptied cells all", len(empt_all), "false grown total mm2 %.0f" % tot_false)
for A in (0, 20, 50, 100):
    for R in (2, 2.5, 3, 5):
        fl = lambda v: sum(1 for f, g in v if g > R * f and g - f >= A and g > 0)
        share = sum(g for f, g in empt_all if g > R * f and g - f >= A) / tot_false
        print("A=%3d R=%.1f | " % (A, R) + " | ".join("%d" % fl(v) for n, v in sets) + " | false grown flagged %.0f%%" % (100 * share))
