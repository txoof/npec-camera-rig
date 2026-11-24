"""Tables for log 46 from the sweep CSVs: one row per form, method and level."""
import csv, glob, json, collections, statistics as st, sys
D = __file__.rsplit("/code/", 1)[0] + "/data"
TRUTH = __file__.rsplit("/code/", 1)[0] + "/../round3-classifier/data/truth/truth_index.csv"

def fixed_area():  # (set, photo, tray) -> stored fixed-cutoff area, mm2
    out = {}
    for f in glob.glob(D + "/api/*.json"):
        d = json.load(open(f)); n = f.rsplit("/", 1)[1][:-5]
        s, _, stem = n.partition("_")
        photo = stem.split("_", 1)[1] if s == "e18" else stem
        for t in d.get("trays", []):
            out[(s, photo, str(t["tray_id"]))] = (t["area_mm2"] or 0, t["grown_area_mm2"] or 0)
    return out

FIX = fixed_area()

def load(form):
    rows = []
    for s in ("e18", "e20"):
        for r in csv.DictReader(open(f"{D}/sweep_{s}_{form}.csv")):
            r["fixed"], r["grown_stored"] = FIX.get((r["set"], r["photo"], r["tray"]), (None, None))
            rows.append(r)
    return rows

def table(form):
    rows = load(form)
    base = {(r["photo"], r["tray"]): r for r in rows if r["method"] == "app"}
    out = []
    ref = list(csv.DictReader(open(f"{D}/sweep_ref_{form}.csv")))
    corrected = None
    for method in ("c", "b"):
        for lev in range(13):
            e_mm2, e_left, e_base = [], 0, 0
            t_chg, t_rest = [], []
            c_rem = []
            for r in rows:
                if r["method"] != method or int(r["level"]) != lev:
                    continue
                b = base[(r["photo"], r["tray"])]; px = int(r["px"]); bpx = int(b["px"]); m = float(r["mm2_per_px"])
                fx = r["fixed"]
                if r["tray"] in ("4", "5", "6") and r["set"] == "e18" and fx is not None and fx < 100:
                    e_mm2.append((px * m, r["photo"], r["tray"])); e_left += px; e_base += bpx
                elif r["tray"] == "10":
                    t_chg.append(100 * (int(r["main_px"]) - int(b["main_px"])) / int(b["main_px"])); t_rest.append(int(r["rest_px"]) * m)
                elif fx and fx >= 100 and r["tray"] in ("4", "5", "6", "7"):
                    c_rem.append(100 * (1 - px / bpx))
            rr = [x for x in ref if x["method"] == method and int(x["level"]) == lev]
            iou = st.mean(float(x["iou"]) for x in rr)
            pool = sum(int(x["px"]) for x in rr if int(x["truth_px"])) / sum(int(x["truth_px"]) for x in rr if int(x["truth_px"]))
            out.append(dict(form=form, method=method, level=lev,
                            empty_max_mm2=max(e_mm2)[0], empty_left_pct=100 * e_left / e_base,
                            target_chg_min=min(t_chg), target_chg_max=max(t_chg), rest_max_mm2=max(t_rest),
                            canopy_removed_max=max(c_rem), canopy_removed_mean=st.mean(c_rem),
                            ref_iou=iou, ref_ratio=pool, sigma_ref_median=st.median(float(x["sigma_b"]) for x in rr)))
    return out

def ref_groups():
    """Mean IoU and pooled area ratio of the reference cells by group (all 60, the 38 corrected by Aaron, 30
    production, 30 development), with no rule, floor N = 1 to 5 and k = 1 to 3, rule B. Writes data/ref_iou_by_group.csv."""
    ti = {r["id"]: r for r in csv.DictReader(open(TRUTH))}
    ref = list(csv.DictReader(open(D + "/sweep_ref_B.csv")))
    groups = {"all 60": lambda x: True, "38 corrected by Aaron": lambda x: ti[x["id"]]["truth_source"].startswith("corrected"),
              "30 production": lambda x: x["rig"] == "prod", "30 development": lambda x: x["rig"] == "dev"}
    out = []
    for g, f in groups.items():
        for m, lev in [("app", "-")] + [("c", str(i)) for i in range(1, 6)] + [("b", str(i)) for i in range(1, 4)]:
            rr = [x for x in ref if x["method"] == m and x["level"] == lev and f(x)]
            nz = [x for x in rr if int(x["truth_px"])]
            out.append(dict(group=g, method=m, level=lev, cells=len(rr), mean_iou=round(st.mean(float(x["iou"]) for x in rr), 4),
                            area_ratio=round(sum(int(x["px"]) for x in nz) / sum(int(x["truth_px"]) for x in nz), 3)))
    with open(D + "/ref_iou_by_group.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)


if __name__ == "__main__":
    ref_groups()
    allrows = []
    for form in "AB":
        t = table(form); allrows += t
        print(form)
        for r in t:
            print(" %s %2d empty<= %7.1f mm2 left %5.2f%% | target %+.2f..%+.2f%% rest<=%6.1f | canopy -%5.1f%% (mean %4.1f) | refIoU %.4f ratio %.3f" % (
                r["method"], r["level"], r["empty_max_mm2"], r["empty_left_pct"], r["target_chg_min"], r["target_chg_max"], r["rest_max_mm2"], r["canopy_removed_max"], r["canopy_removed_mean"], r["ref_iou"], r["ref_ratio"]))
    with open(D + "/summary_levels.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(allrows[0])); w.writeheader(); w.writerows(allrows)
