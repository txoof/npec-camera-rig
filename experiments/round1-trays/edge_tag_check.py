"""20 mm edge tags against their 30 mm A1 partner, from #164's full run (no photo decoded).
Metrology log 15.5c, "20 mm edge tags against their 30 mm partner" (issue #192). Reads #164's
records beside this script and its cached tag detections in ~/scratch/round1-trays/tags/ (setting C).
Run from the repo root: python3 experiments/round1-trays/edge_tag_check.py"""
import csv, collections, json
from pathlib import Path
R = Path("experiments/round1-trays"); C = Path.home() / "scratch/round1-trays/tags"
EDGE = {0: 4, 14: 5, 16: 6, 17: 7, 13: 8, 15: 11}  # edge tag -> A1 tag of its tray (log 15.3a)
steps = {r["still"]: r["step"] for r in csv.DictReader(open(R / "fastsam-full176.csv"))}
masks = collections.defaultdict(list)
for r in csv.DictReader(open(R / "fastsam-full176-masks.csv")):
    ids = {int(t) for t in r["tag_ids"].replace(";", " ").replace(",", " ").split()} if r["tag_ids"] else set()
    masks[r["still"]].append((r["verdict"], ids))
out = csv.writer(open(Path(__file__).parent / "edge-tags.csv", "w", newline=""))
out.writerow(["step", "still", "edge_tag", "partner_a1_tag", "outcome"])
count = collections.Counter()
for still, ms in sorted(masks.items()):
    st = steps.get(still, "")
    if not (st.startswith("R2") or st == "R3"):
        continue
    seen = {t["id"] for t in json.load(open(C / f"{still}.json"))}
    for e, a in EDGE.items():
        holding = [m for m in ms if e in m[1]]
        if e not in seen: k = "edge tag not read"
        elif not holding: k = "linked to no tray (ambiguous)"
        elif len(holding) > 1: k = "on 2 masks"
        elif a not in holding[0][1]: k = "WRONG tray"
        elif holding[0][0] == "one tray" and not (holding[0][1] - {e, a}): k = "right tray"
        else: k = "right tray, but outline merged with a neighbour"
        count[k] += 1; out.writerow([st, still, e, a, k])
print(sum(count.values()), "edge-tag sightings:", dict(count.most_common()))
