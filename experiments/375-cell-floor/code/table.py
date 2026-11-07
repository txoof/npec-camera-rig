import json,sys
d=json.load(sys.stdin); print("missing rows", d["missing_rows"])
for g,v in d["percent_by_group"].items():
    print(f"{g:50s} n={v['n']:5d} plant={v['plant']:5.1f}% possible={v['possible']:5.1f}%")
