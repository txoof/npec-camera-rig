"""Tables for metrology log 26 (#355) from frame<i>_results.json written by analyse.py.

    python compare.py RESULTS_DIR

Every setting is compared with the uncompressed array A of the same still; the yardstick compares
A of stills 1 and 2 with A of still 0 (the camera's own change from photo to photo).
"""
import json
import math
import statistics as st
import sys
from pathlib import Path

d = Path(sys.argv[1])
frames = [json.loads(p.read_text()) for p in sorted(d.glob("frame*_results.json"))]
A = "A uncompressed"


def side_px(c):
    return st.mean(math.dist(c[k], c[(k + 1) % 4]) for k in range(4))


def compare(ref, other):
    common = sorted(set(ref["tags"]) & set(other["tags"]), key=int)
    shift = [max(math.dist(p, q) for p, q in zip(ref["tags"][t], other["tags"][t])) for t in common]
    side = [100 * (side_px(other["tags"][t]) / side_px(ref["tags"][t]) - 1) for t in common]
    area = []
    for r, o in zip(ref["trays"], other["trays"], strict=True):
        if r["area_mm2"] > 0:
            area.append(100 * (o["area_mm2"] / r["area_mm2"] - 1))
    return {
        "tags": f'{len(other["tags"])} ({len(set(ref["tags"]) ^ set(other["tags"]))} differ)',
        "shift_med": st.median(shift), "shift_max": max(shift),
        "side_max": max(map(abs, side)),
        "area_med": st.median(map(abs, area)), "area_max": max(map(abs, area)),
        "area_signed_mean": st.mean(area),
    }


rows = []
for f in frames:
    ref = f["settings"][A]
    for name, s in f["settings"].items():
        if name == A:
            continue
        rows.append((name, f["frame"], s["file_bytes"], compare(ref, s)))
for f in frames[1:]:
    rows.append(("yardstick: uncompressed still vs still 0", f["frame"], None,
                 compare(frames[0]["settings"][A], f["settings"][A])))

print("| Setting | Still | File MB | Tags found | Corner shift median px | max px | "
      "Tag side max change % | Tray area median abs change % | max abs % | mean signed % |")
print("|---|---|---|---|---|---|---|---|---|---|")
for name, i, size, c in rows:
    mb = "" if size is None else f"{size / 1e6:.1f}"
    print(f'| {name} | {i} | {mb} | {c["tags"]} | {c["shift_med"]:.3f} | {c["shift_max"]:.3f} | '
          f'{c["side_max"]:.3f} | {c["area_med"]:.2f} | {c["area_max"]:.2f} | {c["area_signed_mean"]:+.2f} |')

print("\nPlant area per tray, uncompressed (A), mm2, by still; and each setting's change, still 0:")
names = list(frames[0]["settings"])
print("| Tray | " + " | ".join(f"A still {f['frame']}" for f in frames) + " | "
      + " | ".join(n.split(" ", 1)[0] + " % (still 0)" for n in names[1:]) + " |")
print("|" + "---|" * (1 + len(frames) + len(names) - 1))
for k, t in enumerate(frames[0]["settings"][A]["trays"]):
    a = [f["settings"][A]["trays"][k]["area_mm2"] for f in frames]
    ch = [100 * (frames[0]["settings"][n]["trays"][k]["area_mm2"] / a[0] - 1) if a[0] else float("nan")
          for n in names[1:]]
    print(f'| {t["tray_id"]} | ' + " | ".join(f"{x:.0f}" for x in a) + " | "
          + " | ".join(f"{x:+.2f}" for x in ch) + " |")

# One row per setting over all stills. Tag 79 is left out of the corner figures: it moves by up
# to 10 px between two uncompressed stills too (a leaf over it, log 26.1), so it says nothing
# about the encoding. Tags seen in one version and not the other are not compared.
SKIP = {"79"}
print("\nSummary over all stills (corner figures without tag 79):")
print("| Setting | File MB | Corner shift max px | Tag side max change % | Tray area mean signed % "
      "| Tray area max abs % | Small trays (<3000 mm2) mean signed % |")
print("|---|---|---|---|---|---|---|")
groups = {}
for f in frames:
    ref = f["settings"][A]
    for name, s in f["settings"].items():
        if name != A:
            groups.setdefault(name, []).append((ref, s))
for f in frames[1:]:
    groups.setdefault("yardstick: uncompressed still vs still 0", []).append((frames[0]["settings"][A], f["settings"][A]))
for name, pairs in groups.items():
    shifts, sides, areas, small = [], [], [], []
    for ref, s in pairs:
        for t in set(ref["tags"]) & set(s["tags"]) - SKIP:
            shifts.append(max(math.dist(p, q) for p, q in zip(ref["tags"][t], s["tags"][t])))
            sides.append(abs(100 * (side_px(s["tags"][t]) / side_px(ref["tags"][t]) - 1)))
        for r, o in zip(ref["trays"], s["trays"], strict=True):
            if r["area_mm2"] > 0:
                c = 100 * (o["area_mm2"] / r["area_mm2"] - 1)
                areas.append(c)
                if r["area_mm2"] < 3000:
                    small.append(c)
    sizes = [s["file_bytes"] for _r, s in pairs if s["file_bytes"]]
    mb = f"{st.mean(sizes) / 1e6:.1f}" if sizes else ""
    print(f"| {name} | {mb} | {max(shifts):.2f} | {max(sides):.3f} | {st.mean(areas):+.2f} | "
          f"{max(map(abs, areas)):.2f} | {st.mean(small):+.2f} |")
