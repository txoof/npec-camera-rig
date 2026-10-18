"""Round 1 (issue #164): count a fastsam.py run against the decision rule in metrology-log 15.5c.

    python3 experiments/round1-trays/summarise.py fastsam-full176.csv

Per still, a pass needs all three:
  1. every tray is one shape: each of the 12 A1 trays is in exactly one mask;
  2. every shape holds exactly one tray: no mask with tags of two trays;
  3. every tray is in the right slot (provisional reference, see below).
Tray-shaped masks with no tag are counted, not failed: they hold no tray.

Slot reference (provisional, not yet chosen by Aaron): row and order. The slot of a tray from its
mask is its mask centre's row (North: the 6 smallest y) and its place 1 to 6 from the west; the
slot from the tags is the same rule on the A1 tag centres. They must agree.

Writes summary-<name>.csv (per still) next to this file and prints the table.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict

import trays


def row_order(points: dict[int, tuple[float, float]]) -> dict[int, str]:
    """Slot names for 12 points by row (6 smallest y are North) and order from the west."""
    if len(points) != 12:
        return {}
    by_y = sorted(points, key=lambda k: points[k][1])
    out = {}
    for row, ids in (("North", by_y[:6]), ("South", by_y[6:])):
        for i, k in enumerate(sorted(ids, key=lambda k: points[k][0])):
            out[k] = f"{row} {i + 1}"
    return out


def main(argv: list[str]) -> None:
    argv = trays.session_argv(argv)
    name = argv[0].removeprefix("fastsam-").removesuffix(".csv")
    res = list(csv.DictReader(open(trays.HERE / argv[0])))
    masks = defaultdict(list)
    for m in csv.DictReader(open(trays.HERE / argv[0].replace(".csv", "-masks.csv"))):
        masks[m["still"]].append(m)
    out = []
    for r in res:
        still = r["still"]
        tags = {t["id"]: (t["cx"], t["cy"]) for t in trays.detect(still, None) if t["id"] in trays.SESSION.trays}
        ms = masks[still]
        count = defaultdict(int)
        for m in ms:
            for t in m["trays"].split():
                count[int(t)] += 1
        one_shape = sum(count[t] == 1 for t in tags)
        several = sum(m["verdict"] == "several trays" for m in ms)
        right = {int(m["trays"]): (float(m["cx_full"]), float(m["cy_full"])) for m in ms if m["verdict"] == "one tray"}
        slot_mask, slot_tag = row_order(right), row_order(tags)
        slots_agree = sum(1 for t in slot_tag if slot_mask.get(t) == slot_tag[t])
        rule1, rule2, rule3 = one_shape == 12, several == 0, slots_agree == 12
        out.append({"still": still, "step": r["step"], "set": "touching" if r["step"] in trays.SESSION.sets["touching"] else "gaps",
                    "a1_tags": len(tags), "trays_one_shape": one_shape, "masks_several_trays": several,
                    "masks_no_tag": r["no_tag_masks"], "slots_agree": slots_agree,
                    "first_pass_ok": r["first_pass_ok"], "fallback_found": r["fallback_found"],
                    "fallback_tags": r["fallback_tags"], "rule1": rule1, "rule2": rule2, "rule3": rule3,
                    "pass": rule1 and rule2 and rule3, "t_total_s": r["t_total_s"], "t_tags_s": r["t_tags_s"],
                    "tags_cached": r["tags_cached"]})
    trays.write_csv(trays.HERE / f"summary-{name}.csv", out)

    def line(label, rows):
        n = len(rows)
        if not n:
            return
        f = lambda k: sum(int(x[k]) for x in rows)
        print(f"{label:9s} stills {n:3d} | pass {sum(x['pass'] for x in rows):3d} | "
              f"trays one shape {f('trays_one_shape')}/{12 * n} | first pass {f('first_pass_ok')}/{12 * n} | "
              f"fallback {f('fallback_found')}/{f('fallback_tags')} | several-tray masks {f('masks_several_trays')} | "
              f"no-tag masks {f('masks_no_tag')} | slots agree {f('slots_agree')}/{12 * n} | "
              f"rule1 {sum(x['rule1'] for x in rows)} rule2 {sum(x['rule2'] for x in rows)} rule3 {sum(x['rule3'] for x in rows)}")

    line("gaps", [x for x in out if x["set"] == "gaps"])
    line("touching", [x for x in out if x["set"] == "touching"])
    for step in dict.fromkeys(x["step"] for x in out):
        line(f"  {step}", [x for x in out if x["step"] == step])
    un = [x for x in out if x["tags_cached"] == "False"]
    ca = [x for x in out if x["tags_cached"] == "True"]
    if un:
        print(f"time per still with tag detection ({len(un)}): {sum(float(x['t_total_s']) for x in un) / len(un):.2f} s")
    if ca:
        print(f"time per still, tags cached ({len(ca)}): {sum(float(x['t_total_s']) for x in ca) / len(ca):.2f} s")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
