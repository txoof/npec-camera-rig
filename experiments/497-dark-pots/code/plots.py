"""Charts for log 46 from the CSVs in data/. Run with a Python that has matplotlib:
python3 experiments/497-dark-pots/code/plots.py"""
import csv, collections, statistics as st
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
D = "experiments/497-dark-pots/data"; OUT = "docs/figures/46"
BLUE, ORANGE, GREY, GREEN = "#0072B2", "#D55E00", "#666666", "#009E73"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})

# 46a: cumulative share against the margin
h = collections.defaultdict(dict)
for r in csv.DictReader(open(f"{D}/margin_hist.csv")): h[r["group"]][int(r["margin"])] = int(r["count"])
fig, ax = plt.subplots(figsize=(7.2, 4.2))
names = {"false plant, emptied trays": ("False plant in emptied trays 4 to 6", ORANGE, "-"),
         "reference leaf pixels (truth masks, also in the app mask)": ("Leaf pixels of the 60 reference cells", BLUE, "-"),
         "app mask in dense canopy trays 4-7 (upper bound on leaf)": ("App's mask in canopy trays 4 to 7 (leaf and some false plant)", GREEN, "--")}
xs = list(range(0, 31))
for g, (lab, col, ls) in names.items():
    tot = sum(h[g].values()); y = [100 * sum(v for k, v in h[g].items() if k <= x) / tot for x in xs]
    ax.plot(xs, y, color=col, ls=ls, lw=2, label=lab)
ax.axvline(3, color=GREY, lw=1, ls=":"); ax.text(3.3, 50, "floor of 3 levels", color=GREY, fontsize=9)
ax.set_xlabel("Margin of the pixel over the greenness cutoff, in code levels   (2G - R - B) - cutoff x (R + G + B)")
ax.set_ylabel("Pixels with margin at or below, %"); ax.set_ylim(0, 101); ax.set_xlim(0, 30)
ax.legend(frameon=False, loc="center right", fontsize=9)
ax.set_title("What a floor on the margin removes: false plant against leaf", loc="left", fontsize=11)
fig.tight_layout(); fig.savefig(f"{OUT}/margin-cdf.png", dpi=130); plt.close(fig)

# 46b: sweep, form B, c against b
S = [r for r in csv.DictReader(open(f"{D}/summary_levels.csv")) if r["form"] == "B"]
def col(m, key): return [float(r[key]) for r in S if r["method"] == m]
fig, axs = plt.subplots(2, 2, figsize=(9.5, 6.4))
L = list(range(13))
ax = axs[0, 0]
for m, c, lab in (("c", BLUE, "(c) fixed floor, N levels"), ("b", ORANGE, "(b) k x noise of the photo")):
    ax.plot(L, [max(v, 0.1) for v in col(m, "empty_max_mm2")], "o-", color=c, label=lab, ms=4)
ax.axhline(60, color=GREY, ls=":"); ax.text(8.2, 70, "60 mm² limit (placeholder)", color=GREY, fontsize=8)
ax.set_yscale("log"); ax.set_ylabel("Emptied tray, largest reading, mm²"); ax.set_xlabel("N or k"); ax.legend(frameon=False, fontsize=8, loc="lower left")
ax = axs[0, 1]
for m, c in (("c", BLUE), ("b", ORANGE)): ax.plot(L, col(m, "ref_iou"), "o-", color=c, ms=4)
ax.axhline(0.9263, color=GREY, ls="--"); ax.text(6.2, 0.935, "same cells, no rule 0.926", color=GREY, fontsize=8)
ax.axhline(0.869, color=GREY, ls=":"); ax.text(6.2, 0.875, "0.869 (0.874 - 0.005)", color=GREY, fontsize=8)
ax.set_ylabel("Reference cells, mean IoU"); ax.set_xlabel("N or k"); ax.set_ylim(0, 1)
ax = axs[1, 0]
for m, c in (("c", BLUE), ("b", ORANGE)): ax.plot(L, col(m, "canopy_removed_mean"), "o-", color=c, ms=4); ax.plot(L, col(m, "canopy_removed_max"), "s--", color=c, ms=4, alpha=0.6)
ax.axhline(1, color=GREY, ls=":"); ax.text(8.2, 1.4, "1% limit (placeholder)", color=GREY, fontsize=8)
ax.set_ylabel("Canopy trays 4 to 7: share of mask removed, %\n(solid mean, dashed worst photo)"); ax.set_xlabel("N or k"); ax.set_ylim(0, 15)
ax = axs[1, 1]
T = [r for r in csv.DictReader(open(f"{D}/target_zone_B.csv"))]
for m, c in (("c", BLUE), ("b", ORANGE)):
    lo = [min(float(r["change_pct"]) for r in T if r["method"] == m and int(r["level"]) == l) for l in L]
    hi = [max(float(r["change_pct"]) for r in T if r["method"] == m and int(r["level"]) == l) for l in L]
    ax.fill_between(L, lo, hi, color=c, alpha=0.25); ax.plot(L, [(a + b) / 2 for a, b in zip(lo, hi)], color=c)
ax.set_ylabel("Green target on tray 10: change in area, %\n(band: 17 photos, both experiments)"); ax.set_xlabel("N or k")
fig.suptitle("Rule B: floor on the greenness margin, swept from 0 to 12", x=0.01, ha="left", fontsize=11)
fig.tight_layout(); fig.savefig(f"{OUT}/sweep-rule-b.png", dpi=120); plt.close(fig)

# 46c: noise estimate of (b) by condition
G = collections.defaultdict(list)
import glob
for s in ("e18", "e20"):
    for r in csv.DictReader(open(f"{D}/sweep_{s}_B.csv")):
        if r["method"] == "app" and r["tray"] in ("10",) or (r["method"] == "app" and r["tray"] == "4"):
            pass
seen = {}
for s in ("e18", "e20"):
    for r in csv.DictReader(open(f"{D}/sweep_{s}_B.csv")):
        seen[(s, r["photo"], r["day"])] = float(r["sigma_b"])
groups = collections.defaultdict(list)
for (s, p, day), v in seen.items():
    if s == "e20": groups["Experiment 20\n(blue tray, target)"].append(v)
    elif day == "2026-11-23" and p[:2] in ("11", "12", "13", "14"): groups["Experiment 18\nemptied trays"].append(v)
    else: groups["Experiment 18\ncanopy"].append(v)
ref = list(csv.DictReader(open(f"{D}/sweep_ref_B.csv")))
sig = {}
for r in ref:
    if r["method"] == "app": sig[r["id"]] = (r["rig"], float(r["sigma_b"]))
groups["Reference crops\nproduction"] = [v for rg, v in sig.values() if rg == "prod"]
groups["Reference crops\ndevelopment"] = [v for rg, v in sig.values() if rg == "dev"]
order = ["Experiment 18\nemptied trays", "Experiment 20\n(blue tray, target)", "Experiment 18\ncanopy", "Reference crops\nproduction", "Reference crops\ndevelopment"]
fig, ax = plt.subplots(figsize=(7.4, 4))
for i, k in enumerate(order):
    v = groups[k]; ax.scatter([i] * len(v), v, color=BLUE, alpha=0.6, s=18)
    ax.plot([i - 0.25, i + 0.25], [st.median(v)] * 2, color=ORANGE, lw=2)
ax.set_xticks(range(len(order))); ax.set_xticklabels(order, fontsize=8)
ax.set_ylabel("Noise of the photo by method (b), code levels"); ax.set_ylim(0, None)
ax.set_title("Method (b) reads 0.8 to 1.1 with pots only, 2.8 to 9.3 with plants", loc="left", fontsize=10)
fig.tight_layout(); fig.savefig(f"{OUT}/noise-estimate-by-condition.png", dpi=130); plt.close(fig)
print({k.replace("\n", " "): (round(min(v), 2), round(st.median(v), 2), round(max(v), 2), len(v)) for k, v in groups.items()})
